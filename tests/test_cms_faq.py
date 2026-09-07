"""Preguntas frecuentes editables desde el panel.

El test que de verdad importa aquí es el de sincronización: hasta ahora el texto de /faq
estaba escrito dos veces (acordeón visible y JSON-LD FAQPage) sin nada que lo comprobara, y
editar uno solo publicaba en Google unos rich results que no coincidían con la página. Ese
fallo pasa a ser imposible de introducir sin que CI se entere.
"""
import html as html_lib
import json
import re

import pytest
from fastapi.testclient import TestClient

import api
import cms_faq
import database as db

client = TestClient(api.app)
_AUTH = ("test-admin", "test-pass")


@pytest.fixture(autouse=True)
def _faq_limpia():
    conn = db.get_connection()
    conn.execute("DELETE FROM faq")
    conn.commit()
    conn.close()
    yield


def _preguntas_del_jsonld(html):
    bloque = re.search(
        r'<script type="application/ld\+json">\s*\{\s*"@context".*?"FAQPage".*?</script>',
        html, re.DOTALL,
    ).group(0)
    doc = json.loads(bloque.split(">", 1)[1].rsplit("</script>", 1)[0])
    return [(q["name"], q["acceptedAnswer"]["text"]) for q in doc["mainEntity"]]


def _preguntas_visibles(html):
    cuerpo = html.split('<main class="faq-body">')[1].split("</main>")[0]
    preguntas = re.findall(r'<summary class="faq-question">\s*<span>(.*?)</span>', cuerpo, re.DOTALL)
    respuestas = re.findall(r'<p class="faq-answer">(.*?)</p>', cuerpo, re.DOTALL)
    return [(html_lib.unescape(p), html_lib.unescape(r)) for p, r in zip(preguntas, respuestas)]


# --- La razón de ser de este objetivo ---

def test_el_jsonld_y_el_acordeon_dicen_exactamente_lo_mismo():
    html = client.get("/faq").text

    assert _preguntas_del_jsonld(html) == _preguntas_visibles(html)


def test_editar_una_respuesta_la_cambia_en_los_dos_sitios_a_la_vez():
    cms_faq.sembrar_si_vacia()
    primera = db.get_faq()[0]

    client.put(f"/api/cms/faq/{primera['id']}", auth=_AUTH,
               json={"pregunta": "¿Trabajáis en Almería?",
                     "respuesta": "De momento no: solo Murcia y Alicante."})

    html = client.get("/faq").text
    jsonld, visible = _preguntas_del_jsonld(html), _preguntas_visibles(html)

    assert jsonld == visible
    assert ("¿Trabajáis en Almería?", "De momento no: solo Murcia y Alicante.") in visible


# --- Estado inicial ---

def test_con_la_tabla_vacia_se_pintan_las_nueve_preguntas_originales():
    html = client.get("/faq").text

    assert len(_preguntas_visibles(html)) == len(cms_faq.PREGUNTAS_ORIGINALES)


def test_la_siembra_es_idempotente():
    assert cms_faq.sembrar_si_vacia() == len(cms_faq.PREGUNTAS_ORIGINALES)
    assert cms_faq.sembrar_si_vacia() == 0
    assert len(db.get_faq()) == len(cms_faq.PREGUNTAS_ORIGINALES)


# --- Gestión desde el panel ---

def test_los_endpoints_de_faq_exigen_credenciales():
    assert client.get("/api/cms/faq").status_code == 401
    assert client.post("/api/cms/faq", json={"pregunta": "a", "respuesta": "b"}).status_code == 401
    assert client.delete("/api/cms/faq/1").status_code == 401


def test_crear_pregunta_la_anade_al_final():
    cms_faq.sembrar_si_vacia()

    client.post("/api/cms/faq", auth=_AUTH,
                json={"pregunta": "¿Financiáis la instalación?", "respuesta": "Sí, el 100%."})

    visibles = _preguntas_visibles(client.get("/faq").text)
    assert visibles[-1] == ("¿Financiáis la instalación?", "Sí, el 100%.")


def test_ocultar_una_pregunta_la_quita_de_la_pagina_y_del_jsonld():
    cms_faq.sembrar_si_vacia()
    primera = db.get_faq()[0]

    client.patch(f"/api/cms/faq/{primera['id']}?activa=false", auth=_AUTH)

    html = client.get("/faq").text
    assert primera["pregunta"] not in html
    assert len(_preguntas_del_jsonld(html)) == len(cms_faq.PREGUNTAS_ORIGINALES) - 1


def test_reordenar_cambia_el_orden_en_la_pagina():
    cms_faq.sembrar_si_vacia()
    preguntas = db.get_faq()

    client.patch(f"/api/cms/faq/{preguntas[2]['id']}?orden=0", auth=_AUTH)

    assert _preguntas_visibles(client.get("/faq").text)[0][0] == preguntas[2]["pregunta"]


def test_no_se_puede_dejar_la_faq_sin_ninguna_pregunta():
    faq_id = db.crear_faq("Única", "Respuesta")

    r = client.delete(f"/api/cms/faq/{faq_id}", auth=_AUTH)

    assert r.status_code == 400
    assert "al menos una" in r.json()["detail"]


def test_no_se_puede_guardar_una_pregunta_vacia():
    cms_faq.sembrar_si_vacia()
    primera = db.get_faq()[0]

    r = client.put(f"/api/cms/faq/{primera['id']}", auth=_AUTH,
                   json={"pregunta": "  ", "respuesta": "Algo"})

    assert r.status_code == 400


def test_una_respuesta_demasiado_larga_se_rechaza():
    cms_faq.sembrar_si_vacia()
    primera = db.get_faq()[0]

    r = client.put(f"/api/cms/faq/{primera['id']}", auth=_AUTH,
                   json={"pregunta": "¿Y esto?", "respuesta": "x" * (cms_faq.MAX_RESPUESTA + 1)})

    assert r.status_code == 422 or r.status_code == 400


def test_html_escrito_en_una_pregunta_no_se_ejecuta_ni_rompe_el_jsonld():
    db.crear_faq('¿Y si escribo </script><script>alert(1)</script>?', "Pues nada.")

    html = client.get("/faq").text

    assert "<script>alert(1)</script>" not in html
    # El JSON-LD sigue siendo parseable: el texto no ha podido cerrar el bloque.
    assert _preguntas_del_jsonld(html) == _preguntas_visibles(html)
