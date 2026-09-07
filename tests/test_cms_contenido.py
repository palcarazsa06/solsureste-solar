"""Panel de contenido: modelo de datos y API.

Cubre el contrato que usa el panel (`/api/cms/*`) y las salvaguardas que impiden que
alguien de la empresa deje la web en un estado roto desde el formulario."""
import pytest
from fastapi.testclient import TestClient

import api
import cms
import cms_campos
import cms_traduccion
import database as db

client = TestClient(api.app)
_AUTH = ("test-admin", "test-pass")

_CLAVE = "hero_h1"
_CLAVE_TABLA = "financiacion_tabla"


@pytest.fixture(autouse=True)
def _sin_traduccion_automatica(monkeypatch):
    """Este fichero prueba el contenido, no la traducción (que tiene la suya en
    test_cms_traduccion.py). Sin este stub cada guardado en español intentaría salir a
    OpenAI de verdad, que con --disable-socket falla y además ensucia la salida."""
    monkeypatch.setattr(cms_traduccion, "traducir", lambda texto, contexto="": None)


@pytest.fixture(autouse=True)
def _sin_contenido_guardado():
    """Cada test arranca con la tabla de contenido vacía: el estado por defecto del
    sistema es 'nadie ha tocado nada todavía'."""
    conn = db.get_connection()
    conn.execute("DELETE FROM contenido")
    conn.execute("DELETE FROM contenido_versiones")
    conn.commit()
    conn.close()
    yield


# --- Autenticación ---

def test_los_endpoints_del_cms_exigen_credenciales():
    assert client.get("/api/cms/campos").status_code == 401
    assert client.put("/api/cms/contenido", json={"clave": _CLAVE, "idioma": "es", "valor": "x"}).status_code == 401
    assert client.post(f"/api/cms/contenido/{_CLAVE}/restaurar").status_code == 401


# --- Lectura y escritura ---

def test_campos_devuelve_el_valor_original_cuando_no_hay_nada_guardado():
    datos = client.get("/api/cms/campos", auth=_AUTH).json()
    campo = next(c for c in datos["campos"] if c["clave"] == _CLAVE)

    assert campo["valor"] == cms_campos.defecto(_CLAVE, "es")
    assert campo["modificado"] is False


def test_guardar_y_releer_un_campo():
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE, "idioma": "es", "valor": "Titular nuevo"})
    assert r.status_code == 200

    datos = client.get("/api/cms/campos", auth=_AUTH).json()
    campo = next(c for c in datos["campos"] if c["clave"] == _CLAVE)

    assert campo["valor"] == "Titular nuevo"
    assert campo["modificado"] is True


def test_cada_idioma_se_guarda_por_separado():
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "es", "valor": "Solo en español"})

    campos_en = client.get("/api/cms/campos?idioma=en", auth=_AUTH).json()["campos"]
    campo_en = next(c for c in campos_en if c["clave"] == _CLAVE)

    assert campo_en["valor"] == cms_campos.defecto(_CLAVE, "en")


# --- Validación: lo que evita que rompan la web ---

def test_no_se_puede_dejar_un_campo_vacio():
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE, "idioma": "es", "valor": "   "})

    assert r.status_code == 400
    assert "vac" in r.json()["detail"].lower()


def test_no_se_puede_exceder_la_longitud_maxima():
    largo = "x" * (cms_campos.CAMPOS[_CLAVE]["max_length"] + 1)
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE, "idioma": "es", "valor": largo})

    assert r.status_code == 400
    assert "máximo" in r.json()["detail"]


def test_un_campo_numerico_rechaza_texto():
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": "stat_1_valor", "idioma": "es", "valor": "muchos"})

    assert r.status_code == 400


def test_clave_inexistente_se_rechaza():
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": "campo_inventado", "idioma": "es", "valor": "x"})

    assert r.status_code == 400


def test_idioma_no_soportado_se_rechaza():
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE, "idioma": "fr", "valor": "Bonjour"})

    assert r.status_code == 400


def test_tabla_con_numero_de_celdas_incorrecto_se_rechaza():
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE_TABLA, "idioma": "es", "valor": [["5 kW", "10"]]})

    assert r.status_code == 400
    assert "celdas" in r.json()["detail"]


def test_tabla_valida_se_guarda():
    filas = [["9 kW", "18", "11.000,00 €", "180,00 €", "130,00 €", "9.000,00 €", "50.000,00 €"]]
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE_TABLA, "idioma": "es", "valor": filas})

    assert r.status_code == 200
    assert cms.contenido("es")[_CLAVE_TABLA] == filas


# --- Historial y deshacer ---

def test_el_historial_guarda_el_valor_anterior_a_cada_cambio():
    client.put("/api/cms/contenido", auth=_AUTH, json={"clave": _CLAVE, "idioma": "es", "valor": "Primero"})
    client.put("/api/cms/contenido", auth=_AUTH, json={"clave": _CLAVE, "idioma": "es", "valor": "Segundo"})

    versiones = client.get(f"/api/cms/contenido/{_CLAVE}/historial", auth=_AUTH).json()["versiones"]

    # Solo hay una versión archivada: el primer guardado no tenía nada anterior que archivar.
    assert [v["valor"] for v in versiones] == ["Primero"]


def test_el_historial_no_crece_sin_limite():
    for i in range(db.MAX_VERSIONES_POR_CAMPO + 5):
        client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE, "idioma": "es", "valor": f"Version {i}"})

    versiones = db.get_historial_contenido(_CLAVE, "es", limite=100)

    assert len(versiones) == db.MAX_VERSIONES_POR_CAMPO


def test_restaurar_devuelve_el_texto_original():
    client.put("/api/cms/contenido", auth=_AUTH, json={"clave": _CLAVE, "idioma": "es", "valor": "Algo raro"})

    r = client.post(f"/api/cms/contenido/{_CLAVE}/restaurar", auth=_AUTH)

    assert r.status_code == 200
    assert r.json()["valor"] == cms_campos.defecto(_CLAVE, "es")
    assert cms.contenido("es")[_CLAVE] == cms_campos.defecto(_CLAVE, "es")


def test_restaurar_conserva_el_historial_para_poder_volver_atras():
    client.put("/api/cms/contenido", auth=_AUTH, json={"clave": _CLAVE, "idioma": "es", "valor": "Texto bueno"})
    client.post(f"/api/cms/contenido/{_CLAVE}/restaurar", auth=_AUTH)

    versiones = client.get(f"/api/cms/contenido/{_CLAVE}/historial", auth=_AUTH).json()["versiones"]

    assert "Texto bueno" in [v["valor"] for v in versiones]


# --- Registro de campos ---

def test_todos_los_campos_tienen_valor_original_en_los_dos_idiomas():
    """Si a un campo le falta el original en un idioma, esa parte de la web saldría vacía."""
    faltan = [
        (clave, idioma)
        for clave in cms_campos.CAMPOS
        for idioma in cms_campos.IDIOMAS
        if cms_campos.defecto(clave, idioma) in (None, "")
    ]

    assert not faltan, f"Campos sin texto original: {faltan}"


def test_el_texto_original_de_cada_campo_respeta_su_propio_limite():
    """Un original más largo que su max_length haría imposible volver a guardarlo."""
    problemas = [
        (clave, idioma)
        for clave in cms_campos.CAMPOS
        for idioma in cms_campos.IDIOMAS
        if cms_campos.validar(clave, cms_campos.defecto(clave, idioma)) is not None
    ]

    assert not problemas, f"Originales que no pasarían su propia validación: {problemas}"


# --- El circuito completo: lo editado sale en la web ---

def test_lo_guardado_en_el_panel_sale_en_el_html_servido():
    """Debe venir en el HTML que devuelve el servidor, no inyectado por JavaScript:
    si Google no lo ve en la respuesta, para SEO es como si no existiera."""
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "es", "valor": "Placas solares a medida"})

    html = client.get("/").text

    assert "Placas solares a medida" in html
    assert cms_campos.defecto(_CLAVE, "es") not in html


def test_editar_el_espanol_no_toca_la_pagina_inglesa():
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "es", "valor": "Cambio solo en español"})

    assert "Cambio solo en español" not in client.get("/en").text
    assert cms_campos.defecto(_CLAVE, "en") in client.get("/en").text


def test_las_negritas_del_panel_se_renderizan_como_negritas():
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": "caso_1_texto", "idioma": "es", "valor": "Ahorro de **€2.000** al año."})

    html = client.get("/").text

    assert '<strong style="color:#f4f3f0">€2.000</strong>' in html


def test_html_pegado_en_un_campo_no_se_ejecuta_en_la_web():
    """Aunque quien edita esté autenticado, un copiar-pegar desde otra web no debe poder
    inyectar etiquetas en la página pública."""
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "es", "valor": '<img src=x onerror=alert(1)>'})

    html = client.get("/").text

    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_la_tabla_de_financiacion_editada_se_pinta_entera():
    filas = [
        ["3 kW", "6", "4.000,00 €", "60,00 €", "50,00 €", "2.000,00 €", "15.000,00 €"],
        ["4 kW", "8", "5.000,00 €", "70,00 €", "60,00 €", "2.500,00 €", "18.000,00 €"],
    ]
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE_TABLA, "idioma": "es", "valor": filas})

    html = client.get("/").text

    assert "3 kW" in html and "4 kW" in html
    # Las 5 filas originales desaparecen: la tabla es la que hay guardada, no un añadido.
    assert "6.957,50 €" not in html


def test_con_la_base_de_datos_vacia_la_web_muestra_los_textos_originales():
    html = client.get("/").text

    for clave in ("hero_h1", "hero_subtitulo", "caso_1_titulo"):
        assert cms_campos.defecto(clave, "es") in html


# --- Filtro de negritas ---

def test_destacar_convierte_negritas_y_escapa_el_resto():
    resultado = str(cms.destacar("Ahorra **€1.800** al año"))

    assert '<strong style="color:#f4f3f0">€1.800</strong>' in resultado


def test_destacar_neutraliza_html_pegado_por_el_usuario():
    resultado = str(cms.destacar('<script>alert(1)</script> y <b>negrita</b>'))

    assert "<script>" not in resultado
    assert "<b>" not in resultado
    assert "&lt;script&gt;" in resultado
