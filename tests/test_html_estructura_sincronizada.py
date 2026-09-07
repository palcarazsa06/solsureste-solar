"""Auditoría de mantenibilidad: templates/en/index.html es una traducción manual e
independiente de templates/index.html (no usa el mecanismo data-i18n/setLang() de script.js,
que solo sirve para un toggle de texto post-carga). CLAUDE.md ya advierte del coste de
mantenimiento de mantener ambos sincronizados en estructura; este test lo convierte en una
comprobación real de CI: si alguien añade/quita una sección con id en un solo fichero, el
test falla.

Se comprueba sobre el HTML **renderizado** (vía TestClient) y no sobre la plantilla en
disco, para que también detecte una divergencia introducida por la propia lógica de
plantilla (un `{% if %}` que emita un bloque solo en un idioma, por ejemplo)."""
import re

from fastapi.testclient import TestClient

import api

client = TestClient(api.app)

_EXCEPCIONES = {"sss-lang-es", "sss-lang-en"}  # par de enlaces de idioma, distinto a propósito


def _extraer_ids(ruta: str) -> set:
    html = client.get(ruta).text
    return set(re.findall(r'id="([^"]+)"', html)) - _EXCEPCIONES


def test_ids_de_index_es_y_en_estan_sincronizados():
    ids_es = _extraer_ids("/")
    ids_en = _extraer_ids("/en")

    solo_en_es = ids_es - ids_en
    solo_en_en = ids_en - ids_es

    assert not solo_en_es, f"IDs presentes solo en la home ES: {solo_en_es}"
    assert not solo_en_en, f"IDs presentes solo en la home EN: {solo_en_en}"
