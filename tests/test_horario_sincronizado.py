"""Auditoría de mantenibilidad: el horario laboral vive en 3 sitios independientes
(tools/calendar_tools.py::HORARIO_LABORAL, y el JSON-LD openingHoursSpecification de
static/index.html y static/en/index.html), con solo un comentario en el código
recordando mantenerlos sincronizados. Este test convierte esa promesa en una
comprobación real de CI: si alguien edita el horario en un solo sitio, el test falla."""
import json
import re

from tools.calendar_tools import HORARIO_LABORAL

_DIAS_EN_A_INDICE = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}


def _extraer_horario_jsonld(ruta_html: str) -> dict:
    html = open(ruta_html, encoding="utf-8").read()
    bloque = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    ).group(1)
    doc = json.loads(bloque)
    negocio = next(nodo for nodo in doc["@graph"] if "openingHoursSpecification" in nodo)

    horario = {i: [] for i in range(7)}
    for entrada in negocio["openingHoursSpecification"]:
        dias = entrada["dayOfWeek"]
        dias = dias if isinstance(dias, list) else [dias]
        for dia in dias:
            horario[_DIAS_EN_A_INDICE[dia]].append((entrada["opens"], entrada["closes"]))
    return horario


def test_horario_jsonld_index_es_coincide_con_horario_laboral():
    assert _extraer_horario_jsonld("static/index.html") == HORARIO_LABORAL


def test_horario_jsonld_index_en_coincide_con_horario_laboral():
    assert _extraer_horario_jsonld("static/en/index.html") == HORARIO_LABORAL
