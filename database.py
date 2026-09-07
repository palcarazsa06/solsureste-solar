import sqlite3
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DATA_DIR = os.getenv("DATA_DIR", ".")
DB_NAME = os.path.join(DATA_DIR, "agencia.db")

def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    """Crea la tabla con columnas independientes para los datos del cliente."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversaciones (
            user_id TEXT PRIMARY KEY,
            estado TEXT DEFAULT 'INICIO',
            historial TEXT DEFAULT '[]',
            nombre TEXT DEFAULT '',
            correo TEXT DEFAULT '',
            telefono TEXT DEFAULT '',
            ciudad TEXT DEFAULT '',
            crm_enviado INTEGER DEFAULT 0,
            tokens_prompt INTEGER DEFAULT 0,
            tokens_completion INTEGER DEFAULT 0,
            coste_usd REAL DEFAULT 0.0,
            gestionado INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            clave TEXT PRIMARY KEY,
            valor REAL DEFAULT 0.0
        )
    ''')
    cursor.execute(
        "INSERT OR IGNORE INTO stats (clave, valor) VALUES ('coste_historico', 0.0)"
    )
    # --- Panel de contenido (CMS) ---
    # Solo se guardan aquí los campos que alguien ha cambiado desde el panel; los que no
    # están en esta tabla se renderizan con el valor de cms_campos.CAMPOS. Por eso una base
    # de datos recién creada produce exactamente la web original.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contenido (
            clave TEXT NOT NULL,
            idioma TEXT NOT NULL,
            valor TEXT NOT NULL,
            revisar INTEGER DEFAULT 0,
            actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (clave, idioma)
        )
    ''')
    # Historial para el botón "deshacer" del panel. Guarda el valor ANTERIOR a cada
    # guardado, no el nuevo, que es lo que hace falta para poder volver atrás.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contenido_versiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT NOT NULL,
            idioma TEXT NOT NULL,
            valor_anterior TEXT NOT NULL,
            creado_en TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_contenido_versiones ON contenido_versiones (clave, idioma, id DESC)"
    )
    # Preguntas frecuentes de /faq. Antes el texto estaba escrito DOS veces en faq.html (el
    # acordeón visible y el JSON-LD FAQPage) sin nada que los sincronizara: editar uno y
    # olvidar el otro publicaba unos rich results que no coincidían con la página. Ahora los
    # dos se generan del mismo bucle sobre esta tabla.
    # Artículos del blog. Antes cada uno era un .html suelto en static/blog/articulos/ que
    # había que crear duplicando una plantilla, enlazar a mano en el índice y dar de alta en
    # el sitemap. Ahora se escriben desde el panel y las tres cosas salen solas.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            titulo TEXT NOT NULL,
            meta_description TEXT NOT NULL DEFAULT '',
            eyebrow TEXT NOT NULL DEFAULT '',
            imagen_portada TEXT NOT NULL DEFAULT '',
            alt_portada TEXT NOT NULL DEFAULT '',
            pie_portada TEXT NOT NULL DEFAULT '',
            cuerpo_html TEXT NOT NULL DEFAULT '',
            publicado INTEGER NOT NULL DEFAULT 0,
            publicado_en TEXT NOT NULL DEFAULT '',
            actualizado_en TEXT NOT NULL DEFAULT ''
        )
    ''')
    # Slugs antiguos de artículos renombrados, para poder redirigir con 301 y no perder el
    # posicionamiento de una URL que Google ya tenía indexada.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articulos_redirecciones (
            slug_antiguo TEXT PRIMARY KEY,
            slug_nuevo TEXT NOT NULL,
            creado_en TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Imágenes subidas desde el panel. El fichero vive en DATA_DIR/uploads (disco
    # persistente); aquí solo se guarda el registro para poder listarlas y borrarlas.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS imagenes (
            nombre_fichero TEXT PRIMARY KEY,
            nombre_original TEXT NOT NULL DEFAULT '',
            bytes INTEGER NOT NULL DEFAULT 0,
            ancho INTEGER NOT NULL DEFAULT 0,
            alto INTEGER NOT NULL DEFAULT 0,
            subida_en TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden INTEGER NOT NULL DEFAULT 0,
            pregunta TEXT NOT NULL,
            respuesta TEXT NOT NULL,
            activa INTEGER NOT NULL DEFAULT 1,
            actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    # Migraciones para bases de datos existentes
    migraciones = [
        "ALTER TABLE conversaciones ADD COLUMN crm_enviado INTEGER DEFAULT 0",
        "ALTER TABLE conversaciones ADD COLUMN tokens_prompt INTEGER DEFAULT 0",
        "ALTER TABLE conversaciones ADD COLUMN tokens_completion INTEGER DEFAULT 0",
        "ALTER TABLE conversaciones ADD COLUMN coste_usd REAL DEFAULT 0.0",
        "ALTER TABLE conversaciones ADD COLUMN gestionado INTEGER DEFAULT 0",
        "ALTER TABLE conversaciones ADD COLUMN created_at TEXT",
    ]
    for sql in migraciones:
        try:
            cursor.execute(sql)
            conn.commit()
        except Exception:
            pass  # La columna ya existe
    conn.close()

def get_conversacion(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT estado, historial FROM conversaciones WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO conversaciones (user_id, estado, historial, created_at) VALUES (?, 'INICIO', '[]', datetime('now'))",
            (user_id,)
        )
        conn.commit()
        estado, historial = 'INICIO', []
    else:
        estado = row[0]
        historial = json.loads(row[1])

    conn.close()
    return estado, historial

def update_estado(user_id, nuevo_estado):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE conversaciones SET estado = ? WHERE user_id = ?", (nuevo_estado, user_id))
    conn.commit()
    conn.close()

def update_datos_cliente(user_id, nombre, correo, telefono, ciudad):
    """Guarda los datos limpios en sus respectivas columnas."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE conversaciones
        SET nombre = ?, correo = ?, telefono = ?, ciudad = ?
        WHERE user_id = ?
    """, (nombre, correo, telefono, ciudad, user_id))
    conn.commit()
    conn.close()

def _append_historial(user_id, nuevo_mensaje):
    """Lee, modifica y escribe el historial dentro de UNA transacción (BEGIN IMMEDIATE
    adquiere el lock de escritura antes del SELECT). Sin esto, dos escrituras
    concurrentes para el mismo user_id (doble clic, retry del frontend) pueden pisarse
    un mensaje: ambas leen el mismo historial "viejo" antes de que la otra escriba
    (auditoría de robustez). isolation_level=None cede el control de la transacción por
    completo al BEGIN/COMMIT explícitos de abajo, en vez del autocommit implícito de
    sqlite3 en INSERT/UPDATE."""
    conn = get_connection()
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        row = cursor.execute("SELECT historial FROM conversaciones WHERE user_id = ?", (user_id,)).fetchone()
        historial = json.loads(row[0]) if row else []
        historial.append(nuevo_mensaje)
        cursor.execute("UPDATE conversaciones SET historial = ? WHERE user_id = ?", (json.dumps(historial), user_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def append_mensaje(user_id, role, content):
    _append_historial(user_id, {"role": role, "content": content})

def append_mensaje_dict(user_id, mensaje_dict):
    _append_historial(user_id, mensaje_dict)

def guardar_lead_directo(nombre, apellido, telefono, correo, ciudad, tipo_instalacion, mensaje):
    """Guarda un lead enviado desde el formulario web directo."""
    import time
    user_id = f"form_{int(time.time() * 1000)}"
    historial = [{"role": "user", "content": f"[FORMULARIO DIRECTO] Tipo: {tipo_instalacion}. Apellido: {apellido}. Mensaje: {mensaje}"}]
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO conversaciones (user_id, estado, historial, nombre, correo, telefono, ciudad, created_at)
        VALUES (?, 'LEAD_DIRECTO', ?, ?, ?, ?, ?, datetime('now'))
    """, (user_id, json.dumps(historial), nombre, correo, telefono, ciudad))
    conn.commit()
    conn.close()
    return user_id

def crm_ya_enviado(user_id) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT crm_enviado FROM conversaciones WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row[0])

def marcar_crm_enviado(user_id):
    conn = get_connection()
    conn.execute("UPDATE conversaciones SET crm_enviado = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def acumular_tokens(user_id, prompt: int, completion: int):
    """Suma tokens al acumulador de la conversación y actualiza el coste estimado."""
    # gpt-4o-mini: $0.15/1M input, $0.60/1M output
    coste = prompt * 0.15 / 1_000_000 + completion * 0.60 / 1_000_000
    conn = get_connection()
    conn.execute("""
        UPDATE conversaciones
        SET tokens_prompt = tokens_prompt + ?,
            tokens_completion = tokens_completion + ?,
            coste_usd = coste_usd + ?
        WHERE user_id = ?
    """, (prompt, completion, coste, user_id))
    conn.commit()
    conn.close()

def toggle_gestionado(user_id):
    """Alterna el estado 'gestionado' entre 0 y 1."""
    conn = get_connection()
    conn.execute(
        "UPDATE conversaciones SET gestionado = 1 - gestionado WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()

def get_coste_historico() -> float:
    conn = get_connection()
    row = conn.execute("SELECT valor FROM stats WHERE clave = 'coste_historico'").fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

def get_coste_sesion(user_id) -> float:
    """Coste acumulado (USD) de la conversación de un user_id. 0.0 si aún no existe."""
    conn = get_connection()
    row = conn.execute("SELECT coste_usd FROM conversaciones WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

def eliminar_conversacion(user_id):
    """Elimina permanentemente una conversación/lead, rescatando su coste al histórico."""
    conn = get_connection()
    row = conn.execute("SELECT coste_usd FROM conversaciones WHERE user_id = ?", (user_id,)).fetchone()
    if row and row[0]:
        conn.execute(
            "UPDATE stats SET valor = valor + ? WHERE clave = 'coste_historico'",
            (row[0],)
        )
    conn.execute("DELETE FROM conversaciones WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def purgar_conversaciones_antiguas(dias: int = 730) -> int:
    """Borra conversaciones más antiguas que `dias`, rescatando su coste al histórico
    (mismo patrón que eliminar_conversacion). Devuelve el número de filas borradas."""
    conn = get_connection()
    corte = (datetime.utcnow() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    coste_rescatado = conn.execute(
        "SELECT COALESCE(SUM(coste_usd), 0) FROM conversaciones WHERE created_at < ?", (corte,)
    ).fetchone()[0]
    if coste_rescatado:
        conn.execute(
            "UPDATE stats SET valor = valor + ? WHERE clave = 'coste_historico'",
            (coste_rescatado,)
        )
    cursor = conn.execute("DELETE FROM conversaciones WHERE created_at < ?", (corte,))
    filas_borradas = cursor.rowcount
    conn.commit()
    conn.close()
    return filas_borradas

def reset_conversacion(user_id):
    """Reinicia completamente la sesión de un usuario (estado, historial y datos)."""
    conn = get_connection()
    conn.execute(
        "UPDATE conversaciones SET estado='INICIO', historial='[]', nombre='', correo='', telefono='', ciudad='', crm_enviado=0 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()

# --- PANEL DE CONTENIDO (CMS) ---
# Los valores se guardan siempre serializados como JSON, para que un campo de tipo tabla
# (lista de listas) y uno de texto se lean y escriban igual desde el resto del código.

MAX_VERSIONES_POR_CAMPO = 20


def get_contenido(idioma):
    """Devuelve {clave: valor} con lo que hay guardado para ese idioma.

    Solo trae lo modificado desde el panel: quien renderiza completa las claves que
    falten con el valor por defecto de cms_campos."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT clave, valor FROM contenido WHERE idioma = ?", (idioma,))
    filas = cursor.fetchall()
    conn.close()
    return {clave: json.loads(valor) for clave, valor in filas}


def get_contenido_meta(idioma):
    """Como get_contenido, pero con los metadatos que necesita el panel (no la web)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT clave, valor, revisar, actualizado_en FROM contenido WHERE idioma = ?", (idioma,)
    )
    filas = cursor.fetchall()
    conn.close()
    return {
        fila[0]: {
            "valor": json.loads(fila[1]),
            "revisar": bool(fila[2]),
            "actualizado_en": fila[3] or "",
        }
        for fila in filas
    }


def set_contenido(clave, idioma, valor, revisar=False):
    """Guarda un valor y archiva el anterior para poder deshacer.

    Se hace en una sola transacción: si algo falla a mitad, no queda ni el valor nuevo
    guardado ni una entrada de historial huérfana."""
    conn = get_connection()
    conn.isolation_level = None
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            "SELECT valor FROM contenido WHERE clave = ? AND idioma = ?", (clave, idioma)
        )
        anterior = cursor.fetchone()
        if anterior:
            cursor.execute(
                "INSERT INTO contenido_versiones (clave, idioma, valor_anterior) VALUES (?, ?, ?)",
                (clave, idioma, anterior[0]),
            )
            # Poda: el historial es para deshacer un despiste reciente, no un archivo
            # histórico. Sin esto crecería sin límite con cada guardado.
            cursor.execute(
                """DELETE FROM contenido_versiones
                   WHERE clave = ? AND idioma = ? AND id NOT IN (
                       SELECT id FROM contenido_versiones
                       WHERE clave = ? AND idioma = ? ORDER BY id DESC LIMIT ?
                   )""",
                (clave, idioma, clave, idioma, MAX_VERSIONES_POR_CAMPO),
            )
        cursor.execute(
            """INSERT INTO contenido (clave, idioma, valor, revisar, actualizado_en)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(clave, idioma) DO UPDATE SET
                   valor = excluded.valor,
                   revisar = excluded.revisar,
                   actualizado_en = excluded.actualizado_en""",
            (clave, idioma, json.dumps(valor, ensure_ascii=False), 1 if revisar else 0),
        )
        cursor.execute("COMMIT")
    except Exception:
        cursor.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def get_historial_contenido(clave, idioma, limite=MAX_VERSIONES_POR_CAMPO):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, valor_anterior, creado_en FROM contenido_versiones
           WHERE clave = ? AND idioma = ? ORDER BY id DESC LIMIT ?""",
        (clave, idioma, limite),
    )
    filas = cursor.fetchall()
    conn.close()
    return [
        {"id": fila[0], "valor": json.loads(fila[1]), "creado_en": fila[2] or ""}
        for fila in filas
    ]


def borrar_contenido(clave, idioma):
    """Elimina el valor guardado para que vuelva a renderizarse el original del código.

    El historial se conserva a propósito: restaurar el original no debería impedir
    recuperar después un texto que se había escrito antes."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM contenido WHERE clave = ? AND idioma = ?", (clave, idioma))
    anterior = cursor.fetchone()
    if anterior:
        cursor.execute(
            "INSERT INTO contenido_versiones (clave, idioma, valor_anterior) VALUES (?, ?, ?)",
            (clave, idioma, anterior[0]),
        )
    cursor.execute("DELETE FROM contenido WHERE clave = ? AND idioma = ?", (clave, idioma))
    conn.commit()
    conn.close()


# --- ARTÍCULOS DEL BLOG ---

_MADRID = ZoneInfo("Europe/Madrid")


def hoy_madrid() -> str:
    """Fecha de hoy en la zona horaria de la empresa, en formato YYYY-MM-DD.

    No se usa `date('now')` de SQLite porque devuelve la fecha UTC: entre medianoche y las
    01:00 (02:00 en verano) hora española, un artículo publicado se fecharía con el día
    anterior, y esa fecha va al JSON-LD y al sitemap que lee Google."""
    return datetime.now(_MADRID).date().isoformat()

_COLS_ARTICULO = (
    "id, slug, titulo, meta_description, eyebrow, imagen_portada, alt_portada, "
    "pie_portada, cuerpo_html, publicado, publicado_en, actualizado_en"
)


def _fila_a_articulo(fila):
    return {
        "id": fila[0], "slug": fila[1], "titulo": fila[2], "meta_description": fila[3],
        "eyebrow": fila[4], "imagen_portada": fila[5], "alt_portada": fila[6],
        "pie_portada": fila[7], "cuerpo_html": fila[8], "publicado": bool(fila[9]),
        "publicado_en": fila[10], "actualizado_en": fila[11],
    }


def get_articulos(solo_publicados=True):
    conn = get_connection()
    sql = f"SELECT {_COLS_ARTICULO} FROM articulos"
    if solo_publicados:
        sql += " WHERE publicado = 1"
    # Orden por fecha real de publicación, descendente. El índice del blog se ordenaba a
    # mano y había dos artículos compartiendo fecha; el id desempata de forma estable.
    sql += " ORDER BY publicado_en DESC, id DESC"
    filas = conn.execute(sql).fetchall()
    conn.close()
    return [_fila_a_articulo(f) for f in filas]


def get_articulo_por_slug(slug):
    conn = get_connection()
    fila = conn.execute(
        f"SELECT {_COLS_ARTICULO} FROM articulos WHERE slug = ?", (slug,)
    ).fetchone()
    conn.close()
    return _fila_a_articulo(fila) if fila else None


def get_articulo(articulo_id):
    conn = get_connection()
    fila = conn.execute(
        f"SELECT {_COLS_ARTICULO} FROM articulos WHERE id = ?", (articulo_id,)
    ).fetchone()
    conn.close()
    return _fila_a_articulo(fila) if fila else None


def crear_articulo(datos):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO articulos
           (slug, titulo, meta_description, eyebrow, imagen_portada, alt_portada,
            pie_portada, cuerpo_html, publicado, publicado_en, actualizado_en)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (datos["slug"], datos["titulo"], datos.get("meta_description", ""),
         datos.get("eyebrow", ""), datos.get("imagen_portada", ""), datos.get("alt_portada", ""),
         datos.get("pie_portada", ""), datos.get("cuerpo_html", ""),
         int(datos.get("publicado", 0)), datos.get("publicado_en", ""),
         # La migración pasa la fecha real de modificación del artículo importado: marcarlos
         # todos como modificados hoy le diría a Google que se han reescrito, que es falso.
         datos.get("actualizado_en") or hoy_madrid()),
    )
    nuevo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return nuevo_id


def actualizar_articulo(articulo_id, datos):
    campos = [c for c in ("slug", "titulo", "meta_description", "eyebrow", "imagen_portada",
                          "alt_portada", "pie_portada", "cuerpo_html", "publicado",
                          "publicado_en") if c in datos]
    if not campos:
        return
    asignaciones = ", ".join(f"{c} = ?" for c in campos) + ", actualizado_en = ?"
    valores = [int(datos[c]) if c == "publicado" else datos[c] for c in campos]
    valores.append(datos.get("actualizado_en") or hoy_madrid())
    conn = get_connection()
    conn.execute(f"UPDATE articulos SET {asignaciones} WHERE id = ?", (*valores, articulo_id))
    conn.commit()
    conn.close()


def borrar_articulo(articulo_id):
    conn = get_connection()
    conn.execute("DELETE FROM articulos WHERE id = ?", (articulo_id,))
    conn.commit()
    conn.close()


def registrar_redireccion_articulo(slug_antiguo, slug_nuevo):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO articulos_redirecciones (slug_antiguo, slug_nuevo) VALUES (?, ?)",
        (slug_antiguo, slug_nuevo),
    )
    # Si el slug antiguo era a su vez destino de otra redirección, se reapunta para no
    # encadenar saltos 301 (Google penaliza las cadenas largas).
    conn.execute(
        "UPDATE articulos_redirecciones SET slug_nuevo = ? WHERE slug_nuevo = ?",
        (slug_nuevo, slug_antiguo),
    )
    conn.commit()
    conn.close()


def get_redireccion_articulo(slug):
    conn = get_connection()
    fila = conn.execute(
        "SELECT slug_nuevo FROM articulos_redirecciones WHERE slug_antiguo = ?", (slug,)
    ).fetchone()
    conn.close()
    return fila[0] if fila else None


# --- IMÁGENES SUBIDAS DESDE EL PANEL ---

def registrar_imagen(nombre_fichero, nombre_original, bytes_, ancho, alto):
    """INSERT OR REPLACE: subir dos veces la misma foto da el mismo nombre (el hash es del
    contenido), y eso debe refrescar el registro en vez de fallar por clave duplicada."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO imagenes
           (nombre_fichero, nombre_original, bytes, ancho, alto, subida_en)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (nombre_fichero, nombre_original, bytes_, ancho, alto),
    )
    conn.commit()
    conn.close()


def get_imagenes():
    conn = get_connection()
    filas = conn.execute(
        """SELECT nombre_fichero, nombre_original, bytes, ancho, alto, subida_en
           FROM imagenes ORDER BY subida_en DESC"""
    ).fetchall()
    conn.close()
    return [
        {"nombre_fichero": f[0], "nombre_original": f[1], "bytes": f[2],
         "ancho": f[3], "alto": f[4], "subida_en": f[5] or ""}
        for f in filas
    ]


def borrar_imagen(nombre_fichero):
    conn = get_connection()
    conn.execute("DELETE FROM imagenes WHERE nombre_fichero = ?", (nombre_fichero,))
    conn.commit()
    conn.close()


# --- PREGUNTAS FRECUENTES ---

def get_faq(solo_activas=True):
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT id, orden, pregunta, respuesta, activa FROM faq"
    if solo_activas:
        sql += " WHERE activa = 1"
    sql += " ORDER BY orden, id"
    filas = cursor.execute(sql).fetchall()
    conn.close()
    return [
        {"id": f[0], "orden": f[1], "pregunta": f[2], "respuesta": f[3], "activa": bool(f[4])}
        for f in filas
    ]


def crear_faq(pregunta, respuesta):
    conn = get_connection()
    cursor = conn.cursor()
    siguiente = (cursor.execute("SELECT COALESCE(MAX(orden), 0) + 1 FROM faq").fetchone()[0])
    cursor.execute(
        "INSERT INTO faq (orden, pregunta, respuesta) VALUES (?, ?, ?)",
        (siguiente, pregunta, respuesta),
    )
    nuevo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return nuevo_id


def actualizar_faq(faq_id, pregunta=None, respuesta=None, activa=None, orden=None):
    campos, valores = [], []
    for nombre, valor in (("pregunta", pregunta), ("respuesta", respuesta),
                          ("activa", None if activa is None else int(activa)), ("orden", orden)):
        if valor is not None:
            campos.append(f"{nombre} = ?")
            valores.append(valor)
    if not campos:
        return
    campos.append("actualizado_en = datetime('now')")
    conn = get_connection()
    conn.execute(f"UPDATE faq SET {', '.join(campos)} WHERE id = ?", (*valores, faq_id))
    conn.commit()
    conn.close()


def borrar_faq(faq_id):
    conn = get_connection()
    conn.execute("DELETE FROM faq WHERE id = ?", (faq_id,))
    conn.commit()
    conn.close()


def get_all_conversaciones():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, estado, historial, nombre, correo, telefono, ciudad,
               tokens_prompt, tokens_completion, coste_usd, gestionado, created_at, crm_enviado
        FROM conversaciones
        ORDER BY created_at DESC
    """)
    filas = cursor.fetchall()
    conn.close()

    resultados = []
    for fila in filas:
        resultados.append({
            "user_id": fila[0],
            "estado": fila[1],
            "historial": json.loads(fila[2]),
            "nombre": fila[3],
            "correo": fila[4],
            "telefono": fila[5],
            "ciudad": fila[6],
            "tokens_prompt": fila[7] or 0,
            "tokens_completion": fila[8] or 0,
            "coste_usd": fila[9] or 0.0,
            "gestionado": bool(fila[10]),
            "created_at": fila[11] or "",
            "crm_enviado": bool(fila[12]),
        })
    return resultados
