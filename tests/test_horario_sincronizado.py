"""Auditoría de mantenibilidad: el horario laboral vive en 3 sitios independientes
(tools/calendar_tools.py::HORARIO_LABORAL, y el JSON-LD openingHoursSpecification de
templates/index.html y templates/en/index.html), con solo un comentario en el código
recordando mantenerlos sincronizados. Este test convierte esa promesa en una
comprobación real de CI: si alguien edita el horario en un solo sitio, el test falla.

Se comprueba sobre el HTML **renderizado** (vía TestClient), no sobre la plantilla en
disco: desde que la home se sirve con Jinja2 la plantilla contiene `{{ }}` y no es JSON
parseable, y además lo que importa es lo que realmente ve Google."""
import json
import re

from fastapi.testclient import TestClient

import api
from tools.calendar_tools import HORARIO_LABORAL

client = TestClient(api.app)

_DIAS_EN_A_INDICE = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}


def _extraer_horario_jsonld(ruta: str) -> dict:
    html = client.get(ruta).text
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
    assert _extraer_horario_jsonld("/") == HORARIO_LABORAL


def test_horario_jsonld_index_en_coincide_con_horario_laboral():
    assert _extraer_horario_jsonld("/en") == HORARIO_LABORAL
