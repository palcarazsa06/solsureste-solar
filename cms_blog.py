"""Artículos del blog gestionados desde el panel.

Antes cada artículo era un fichero suelto en `static/blog/articulos/`, creado duplicando una
plantilla, enlazado a mano en el índice y dado de alta a mano en el sitemap. Eran tres pasos
manuales que había que recordar y que nadie fuera del desarrollador podía hacer.

Lo importante al tocar esto: **las URLs terminan en `.html`**
(`/blog/articulos/mi-articulo.html`). Las tres que ya existían están indexadas en Google y
listadas en el sitemap; cambiarlas costaría el posicionamiento ganado. Por eso las rutas
mantienen la extensión aunque el contenido ya no venga de un fichero.
"""

import json
import os
import re
import unicodedata

import database as db
from logging_config import get_logger

logger = get_logger(__name__)

# Texto de los artículos que existían cuando el blog eran ficheros sueltos. Viaja en el repo
# por el mismo motivo que cms_faq.PREGUNTAS_ORIGINALES y los valores de cms_campos: la base
# de datos de producción vive en un disco persistente que arranca vacío, así que el contenido
# original tiene que poder sembrarse solo. Si dependiera de los .html de static/ no
# funcionaría — esos ficheros ya no existen desde que las rutas los sustituyeron.
_SEMILLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "documentos", "blog_semilla.json")

MAX_TITULO = 140
MAX_META = 200
MAX_EYEBROW = 80
MAX_CUERPO = 80_000

# Longitud a partir de la cual Google recorta la descripción en los resultados. No es un
# error, solo un aviso en el panel.
META_RECOMENDADA = 160

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")

_SLUG_VALIDO = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugificar(titulo: str) -> str:
    base = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return base[:90] or "articulo"


def fecha_legible(iso: str) -> str:
    """2026-09-03 -> «3 de septiembre de 2026», que es como se escriben en la web."""
    try:
        y, m, d = (int(p) for p in iso.split("-"))
        return f"{d} de {_MESES[m - 1]} de {y}"
    except Exception:
        return iso


def _decorar(articulo: dict) -> dict:
    articulo["fecha_legible"] = fecha_legible(articulo["publicado_en"])
    articulo["url"] = f"/blog/articulos/{articulo['slug']}.html"
    return articulo


def sembrar_si_vacia() -> int:
    """Carga los artículos originales la primera vez. Idempotente: si ya hay alguno en la
    base de datos no toca nada, así que puede llamarse en cada arranque sin miedo.

    Se comprueba también slug a slug: si alguien borró un artículo desde el panel a
    propósito, no debe reaparecer en el siguiente reinicio."""
    if db.get_articulos(solo_publicados=False):
        return 0
    try:
        with open(_SEMILLA, encoding="utf-8") as f:
            articulos = json.load(f)
    except Exception as e:
        logger.error(f"[CMS] No se pudo leer la semilla del blog ({_SEMILLA}): {e}")
        return 0

    creados = 0
    for articulo in articulos:
        if db.get_articulo_por_slug(articulo["slug"]):
            continue
        db.crear_articulo(articulo)
        creados += 1
    if creados:
        logger.info(f"[CMS] Sembrados {creados} artículos originales del blog.")
    return creados


def publicados() -> list:
    return [_decorar(a) for a in db.get_articulos(solo_publicados=True)]


def todos() -> list:
    return [_decorar(a) for a in db.get_articulos(solo_publicados=False)]


def por_slug(slug: str, incluir_borradores=False):
    articulo = db.get_articulo_por_slug(slug)
    if not articulo:
        return None
    if not articulo["publicado"] and not incluir_borradores:
        return None
    return _decorar(articulo)


def por_id(articulo_id: int):
    articulo = db.get_articulo(articulo_id)
    return _decorar(articulo) if articulo else None


def validar(datos: dict, articulo_id=None) -> str | None:
    """Mensaje de error en castellano listo para el panel, o None si todo está bien."""
    titulo = (datos.get("titulo") or "").strip()
    if not titulo:
        return "El artículo necesita un título."
    if len(titulo) > MAX_TITULO:
        return f"El título es demasiado largo (máximo {MAX_TITULO} caracteres)."

    slug = (datos.get("slug") or "").strip()
    if not slug:
        return "La dirección del artículo no puede quedarse vacía."
    if not _SLUG_VALIDO.match(slug):
        return ("La dirección solo puede llevar letras minúsculas sin acentos, números y "
                "guiones. Por ejemplo: placas-solares-en-lorca")

    existente = db.get_articulo_por_slug(slug)
    if existente and existente["id"] != articulo_id:
        return "Ya hay otro artículo con esa dirección. Cambia el título o la dirección."

    if len(datos.get("meta_description") or "") > MAX_META:
        return f"La descripción es demasiado larga (máximo {MAX_META} caracteres)."
    if len(datos.get("eyebrow") or "") > MAX_EYEBROW:
        return f"La etiqueta superior es demasiado larga (máximo {MAX_EYEBROW} caracteres)."
    if len(datos.get("cuerpo_html") or "") > MAX_CUERPO:
        return "El artículo es larguísimo. Pártelo en dos entregas."

    if datos.get("publicado"):
        if not (datos.get("meta_description") or "").strip():
            return ("Para publicar hace falta la descripción: es el texto que Google enseña "
                    "debajo del título en los resultados de búsqueda.")
        if not (datos.get("cuerpo_html") or "").strip():
            return "No se puede publicar un artículo sin contenido."
    return None


def hoy() -> str:
    """Delegado en database para que las fechas que se guardan y las que se calculan aquí
    salgan siempre del mismo reloj (hora española, no UTC)."""
    return db.hoy_madrid()
