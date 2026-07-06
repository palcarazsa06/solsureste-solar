import os
import re
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from logging_config import get_logger

logger = get_logger(__name__)

PLACE_ID = os.getenv("GOOGLE_PLACE_ID")
API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
FIELD_MASK = "id,displayName,rating,userRatingCount,googleMapsUri,reviews"

DATA_DIR = os.getenv("DATA_DIR", ".")
CACHE_FILE = os.path.join(DATA_DIR, "google_reviews_cache.json")

_cache: dict[str, dict] = {}


def _fetch_place_details(lang: str) -> dict | None:
    """Llamada cruda a Places API (New). None si falla o faltan credenciales."""
    if not (PLACE_ID and API_KEY):
        logger.error("GOOGLE_PLACE_ID o GOOGLE_PLACES_API_KEY no configurados.")
        return None

    try:
        r = requests.get(
            f"https://places.googleapis.com/v1/places/{PLACE_ID}",
            params={"languageCode": lang},
            headers={"X-Goog-Api-Key": API_KEY, "X-Goog-FieldMask": FIELD_MASK},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        logger.error(f"[google_reviews] Fallo llamando a Places API ({lang}): {e}")
        return None

    reviews = [
        {
            "author_name": rv.get("authorAttribution", {}).get("displayName", "Cliente"),
            "author_photo_url": rv.get("authorAttribution", {}).get("photoUri"),
            "author_profile_url": rv.get("authorAttribution", {}).get("uri"),
            "rating": rv.get("rating", 5),
            "relative_time": rv.get("relativePublishTimeDescription", ""),
            "text": rv.get("text", {}).get("text", "").strip(),
        }
        for rv in data.get("reviews", [])
    ][:5]

    return {
        "rating": data.get("rating"),
        "user_rating_count": data.get("userRatingCount"),
        "maps_uri": data.get("googleMapsUri"),
        "reviews": reviews,
    }


def _cargar_cache_disco() -> None:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _cache.update(json.load(f))
        except Exception as e:
            logger.warning(f"[google_reviews] No se pudo leer {CACHE_FILE}: {e}")


def _guardar_cache_disco() -> None:
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_FILE)


_cargar_cache_disco()

# Ficheros estáticos cuyo JSON-LD lleva un nodo "aggregateRating" a mantener sincronizado
# con el rating/nº de reseñas real de Google. No hay templating server-side (se sirven tal
# cual vía FileResponse/StaticFiles), así que se reescribe el fragmento en disco tras cada
# refresco con éxito.
_AGGREGATE_RATING_FILES = ("static/index.html", "static/en/index.html")
_AGGREGATE_RATING_PATTERN = re.compile(r'"aggregateRating":\s*\{[^{}]*\}')


def _actualizar_aggregate_rating_html(path: str, rating, review_count) -> None:
    if not os.path.exists(path):
        logger.warning(f"[google_reviews] {path} no existe, no se actualiza aggregateRating.")
        return
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    fragmento = '"aggregateRating": {"@type":"AggregateRating","ratingValue":"%s","reviewCount":"%s"}' % (rating, review_count)
    html_nuevo, n = _AGGREGATE_RATING_PATTERN.subn(fragmento, html, count=1)
    if n == 0:
        logger.error(f"[google_reviews] No se encontró el nodo aggregateRating en {path}; no se modifica el fichero.")
        return
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html_nuevo)
    os.replace(tmp, path)


def _actualizar_aggregate_rating_estaticos(rating, review_count) -> None:
    if rating is None or review_count is None:
        return
    for path in _AGGREGATE_RATING_FILES:
        try:
            _actualizar_aggregate_rating_html(path, rating, review_count)
        except Exception as e:
            logger.error(f"[google_reviews] Fallo actualizando aggregateRating en {path}: {e}")


def refrescar_resenas_cache(langs=("es", "en")) -> None:
    """Refresca el caché de reseñas. Si una llamada falla, conserva el valor anterior
    de ese idioma en vez de vaciarlo — un fallo puntual de Google nunca debe hacer
    desaparecer reseñas que ya se estaban mostrando bien."""
    for i, lang in enumerate(langs):
        datos = _fetch_place_details(lang)
        if datos:
            datos["fetched_at"] = datetime.now(ZoneInfo("Europe/Madrid")).isoformat()
            datos["status"] = "ok"
            _cache[lang] = datos
            if i == 0:
                # rating/nº de reseñas son del negocio, no dependen del idioma pedido
                _actualizar_aggregate_rating_estaticos(datos.get("rating"), datos.get("user_rating_count"))
        else:
            logger.warning(f"[google_reviews] Fallo refrescando '{lang}' — se conserva el caché anterior si existe.")
    _guardar_cache_disco()


def obtener_resenas_cache(lang: str) -> dict:
    return _cache.get(lang, {"status": "unavailable", "reviews": []})
