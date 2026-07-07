"""Auditoría de mantenibilidad: static/en/index.html es una traducción manual e
independiente de static/index.html (no usa el mecanismo data-i18n/setLang() de script.js,
que solo sirve para un toggle de texto post-carga). CLAUDE.md ya advierte del coste de
mantenimiento de mantener ambos sincronizados en estructura; este test lo convierte en una
comprobación real de CI: si alguien añade/quita una sección con id en un solo fichero, el
test falla."""
import re

_EXCEPCIONES = {"sss-lang-es", "sss-lang-en"}  # par de enlaces de idioma, distinto a propósito


def _extraer_ids(ruta_html: str) -> set:
    html = open(ruta_html, encoding="utf-8").read()
    return set(re.findall(r'id="([^"]+)"', html)) - _EXCEPCIONES


def test_ids_de_index_es_y_en_estan_sincronizados():
    ids_es = _extraer_ids("static/index.html")
    ids_en = _extraer_ids("static/en/index.html")

    solo_en_es = ids_es - ids_en
    solo_en_en = ids_en - ids_es

    assert not solo_en_es, f"IDs presentes solo en static/index.html: {solo_en_es}"
    assert not solo_en_en, f"IDs presentes solo en static/en/index.html: {solo_en_en}"
