import os
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

# El nodo "aggregateRating" del JSON-LD de la home (ES y EN) se alimenta de este caché.
# Antes se reescribía a mano el fragmento dentro de static/index.html con un regex y
# os.replace; ya no hace falta: esas páginas se renderizan con Jinja2 y api.py pasa
# `rating`/`user_rating_count` como variables (ver _contexto_publico). Eso elimina la única
# escritura del servidor sobre static/, que en Render es efímero y se pisaba en cada deploy.


def refrescar_resenas_cache(langs=("es", "en")) -> None:
    """Refresca el caché de reseñas. Si una llamada falla, conserva el valor anterior
    de ese idioma en vez de vaciarlo — un fallo puntual de Google nunca debe hacer
    desaparecer reseñas que ya se estaban mostrando bien."""
    for lang in langs:
        datos = _fetch_place_details(lang)
        if datos:
            datos["fetched_at"] = datetime.now(ZoneInfo("Europe/Madrid")).isoformat()
            datos["status"] = "ok"
            _cache[lang] = datos
        else:
            logger.warning(f"[google_reviews] Fallo refrescando '{lang}' — se conserva el caché anterior si existe.")
    _guardar_cache_disco()


def obtener_resenas_cache(lang: str) -> dict:
    return _cache.get(lang, {"status": "unavailable", "reviews": []})
