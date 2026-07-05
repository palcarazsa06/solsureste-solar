import sqlite3
import json
import os
from datetime import datetime, timedelta

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

def append_mensaje(user_id, role, content):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT historial FROM conversaciones WHERE user_id = ?", (user_id,)).fetchone()
    historial = json.loads(row[0]) if row else []
    historial.append({"role": role, "content": content})
    cursor.execute("UPDATE conversaciones SET historial = ? WHERE user_id = ?", (json.dumps(historial), user_id))
    conn.commit()
    conn.close()

def append_mensaje_dict(user_id, mensaje_dict):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT historial FROM conversaciones WHERE user_id = ?", (user_id,)).fetchone()
    historial = json.loads(row[0]) if row else []
    historial.append(mensaje_dict)
    cursor.execute("UPDATE conversaciones SET historial = ? WHERE user_id = ?", (json.dumps(historial), user_id))
    conn.commit()
    conn.close()

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

def get_all_conversaciones():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, estado, historial, nombre, correo, telefono, ciudad,
               tokens_prompt, tokens_completion, coste_usd, gestionado, created_at
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
        })
    return resultados
