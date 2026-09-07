"""Traducción automática ES→EN del panel de contenido.

La llamada real a OpenAI está siempre mockeada: pytest.ini corre con --disable-socket, así
que un test que intentase salir a la red fallaría en vez de colgarse (y además costaría
dinero). Lo que se comprueba aquí es el comportamiento alrededor de esa llamada, que es
donde está el riesgo real: que un fallo de OpenAI no se lleve por delante el texto español.
"""
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


@pytest.fixture(autouse=True)
def _sin_contenido_guardado():
    conn = db.get_connection()
    conn.execute("DELETE FROM contenido")
    conn.execute("DELETE FROM contenido_versiones")
    conn.commit()
    conn.close()
    yield


@pytest.fixture
def traductor_ok(monkeypatch):
    """Sustituye la llamada a OpenAI por una traducción falsa pero determinista."""
    llamadas = []

    def _fake(texto, contexto=""):
        llamadas.append(texto)
        return "TRADUCIDO: " + texto

    monkeypatch.setattr(cms_traduccion, "traducir", _fake)
    return llamadas


@pytest.fixture
def traductor_caido(monkeypatch):
    """OpenAI no responde: traducir() devuelve None, que es su contrato ante cualquier fallo."""
    monkeypatch.setattr(cms_traduccion, "traducir", lambda texto, contexto="": None)


# --- Camino feliz ---

def test_guardar_en_espanol_traduce_el_ingles(traductor_ok):
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE, "idioma": "es", "valor": "Titular nuevo"})

    assert r.status_code == 200
    assert cms.contenido("en")[_CLAVE] == "TRADUCIDO: Titular nuevo"
    assert traductor_ok == ["Titular nuevo"]


def test_la_traduccion_queda_marcada_para_revisar(traductor_ok):
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "es", "valor": "Titular nuevo"})

    campos = client.get("/api/cms/campos?idioma=en", auth=_AUTH).json()["campos"]
    campo = next(c for c in campos if c["clave"] == _CLAVE)

    assert campo["revisar"] is True


def test_editar_el_ingles_a_mano_quita_la_marca_de_revisar(traductor_ok):
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "es", "valor": "Titular nuevo"})
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "en", "valor": "A proper headline"})

    campos = client.get("/api/cms/campos?idioma=en", auth=_AUTH).json()["campos"]
    campo = next(c for c in campos if c["clave"] == _CLAVE)

    assert campo["revisar"] is False
    assert campo["valor"] == "A proper headline"


def test_la_traduccion_llega_a_la_web_inglesa(traductor_ok):
    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "es", "valor": "Titular nuevo"})

    assert "TRADUCIDO: Titular nuevo" in client.get("/en").text


# --- Lo importante: que un fallo no se lleve por delante el español ---

def test_si_falla_la_traduccion_el_espanol_se_guarda_igual(traductor_caido):
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE, "idioma": "es", "valor": "Titular que sí se guarda"})

    assert r.status_code == 200
    assert cms.contenido("es")[_CLAVE] == "Titular que sí se guarda"
    assert "Titular que sí se guarda" in client.get("/").text


def test_si_falla_la_traduccion_el_ingles_conserva_lo_que_tenia(traductor_caido):
    db.set_contenido(_CLAVE, "en", "Texto inglés anterior")

    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "es", "valor": "Nuevo español"})

    assert cms.contenido("en")[_CLAVE] == "Texto inglés anterior"


def test_si_falla_la_traduccion_se_avisa_en_la_respuesta(traductor_caido):
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE, "idioma": "es", "valor": "Nuevo español"})

    assert r.json()["valor_en"] is None
    assert "español sí se ha guardado" in r.json()["traduccion"]


# --- Reglas por tipo de campo ---

def test_las_tablas_no_se_traducen_automaticamente(traductor_ok):
    """Las cifras cambian de formato entre idiomas; traducirlas a máquina es la vía rápida
    a publicar un precio equivocado."""
    filas = [["5 kW", "10", "6.957,50 €", "103,85 €", "80,60 €", "3.687,09 €", "27.283,69 €"]]

    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": "financiacion_tabla", "idioma": "es", "valor": filas})

    assert r.json()["valor_en"] is None
    assert traductor_ok == []
    assert cms.contenido("en")["financiacion_tabla"] == cms_campos.defecto("financiacion_tabla", "en")


def test_los_numeros_se_copian_sin_gastar_una_llamada(traductor_ok):
    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": "stat_2_valor", "idioma": "es", "valor": "620"})

    assert r.json()["valor_en"] == "620"
    assert cms.contenido("en")["stat_2_valor"] == "620"
    assert traductor_ok == []


def test_una_traduccion_demasiado_larga_se_descarta(monkeypatch):
    """Antes que descuadrar la maqueta inglesa, se deja el inglés como estaba."""
    monkeypatch.setattr(cms_traduccion, "traducir",
                        lambda texto, contexto="": "x" * (cms_campos.CAMPOS[_CLAVE]["max_length"] + 1))

    r = client.put("/api/cms/contenido", auth=_AUTH,
                   json={"clave": _CLAVE, "idioma": "es", "valor": "Titular"})

    assert r.json()["valor_en"] is None
    assert "demasiado larga" in r.json()["traduccion"]


# --- Reintento manual ---

def test_reintentar_traduccion_funciona(traductor_ok):
    db.set_contenido(_CLAVE, "es", "Texto en español")

    r = client.post(f"/api/cms/contenido/{_CLAVE}/traducir", auth=_AUTH)

    assert r.status_code == 200
    assert cms.contenido("en")[_CLAVE] == "TRADUCIDO: Texto en español"


def test_reintentar_traduccion_con_openai_caido_devuelve_error_legible(traductor_caido):
    r = client.post(f"/api/cms/contenido/{_CLAVE}/traducir", auth=_AUTH)

    assert r.status_code == 502
    assert "no se ha podido traducir" in r.json()["detail"].lower()


def test_reintentar_traduccion_exige_credenciales():
    assert client.post(f"/api/cms/contenido/{_CLAVE}/traducir").status_code == 401


# --- Toggle ES/EN de la home ---

def test_el_bloque_i18n_lleva_los_textos_ingleses_del_panel(traductor_ok):
    """El diccionario que tenía script.js a mano se quedaba viejo en cuanto alguien editaba
    la home; ahora sale del mismo sitio que la web inglesa."""
    import json
    import re

    client.put("/api/cms/contenido", auth=_AUTH,
               json={"clave": _CLAVE, "idioma": "es", "valor": "Titular nuevo"})

    html = client.get("/").text
    bloque = re.search(r'<script type="application/json" id="sss-i18n">(.*?)</script>', html, re.DOTALL)
    datos = json.loads(bloque.group(1))

    assert datos["hero.h1"] == "TRADUCIDO: Titular nuevo"
    assert datos["hero.h1.destacado"] == cms_campos.defecto("hero_h1_destacado", "en")


def test_el_bloque_i18n_no_puede_romper_la_pagina():
    """Un texto con </script> dentro tiene que salir escapado o partiría el HTML en dos."""
    db.set_contenido("hero_h1", "en", '</script><script>alert(1)</script>')

    html = client.get("/").text

    assert "</script><script>alert(1)" not in html
