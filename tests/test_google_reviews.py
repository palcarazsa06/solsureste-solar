import json

import pytest

import google_reviews as gr


@pytest.fixture(autouse=True)
def _estado_limpio(monkeypatch, tmp_path):
    """Aísla cada test de _cache y del fichero de disco real — nunca debe tocar
    google_reviews_cache.json ni los static/*.html reales del repo."""
    gr._cache.clear()
    monkeypatch.setattr(gr, "CACHE_FILE", str(tmp_path / "cache.json"))
    yield
    gr._cache.clear()


class _RespuestaFake:
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise gr.requests.HTTPError("fallo simulado")

    def json(self):
        return self._payload


def _payload_places_api(rating=4.8, count=23, texto_review="Muy buen servicio"):
    return {
        "rating": rating,
        "userRatingCount": count,
        "googleMapsUri": "https://maps.google.com/?cid=123",
        "reviews": [
            {
                "authorAttribution": {"displayName": "Cliente Test", "photoUri": None, "uri": None},
                "rating": 5,
                "relativePublishTimeDescription": "hace 1 semana",
                "text": {"text": texto_review},
            }
        ],
    }


def test_fetch_place_details_parsea_la_respuesta_de_la_places_api(monkeypatch):
    monkeypatch.setattr(gr, "PLACE_ID", "place-test")
    monkeypatch.setattr(gr, "API_KEY", "key-test")

    def _get_mock(url, params=None, headers=None, timeout=None):
        return _RespuestaFake(_payload_places_api())

    monkeypatch.setattr(gr.requests, "get", _get_mock)

    datos = gr._fetch_place_details("es")

    assert datos["rating"] == 4.8
    assert datos["user_rating_count"] == 23
    assert len(datos["reviews"]) == 1
    assert datos["reviews"][0]["text"] == "Muy buen servicio"


def test_fetch_place_details_sin_credenciales_devuelve_none(monkeypatch):
    monkeypatch.setattr(gr, "PLACE_ID", None)
    monkeypatch.setattr(gr, "API_KEY", None)

    assert gr._fetch_place_details("es") is None


def test_refrescar_resenas_cache_actualiza_cache_y_aggregate_rating(monkeypatch, tmp_path):
    html_es = tmp_path / "index.html"
    html_en = tmp_path / "en_index.html"
    contenido = (
        '<script type="application/ld+json">{"@type":"HomeAndConstructionBusiness",'
        '"aggregateRating": {"@type":"AggregateRating","ratingValue":"4.0","reviewCount":"10"}}</script>'
    )
    html_es.write_text(contenido, encoding="utf-8")
    html_en.write_text(contenido, encoding="utf-8")
    monkeypatch.setattr(gr, "_AGGREGATE_RATING_FILES", (str(html_es), str(html_en)))

    # _fetch_place_details devuelve el dict ya "aplanado" (rating/user_rating_count/...),
    # no el payload crudo de la API — replicamos esa forma exacta aquí.
    def _fetch_mock(lang):
        return {
            "rating": 4.9,
            "user_rating_count": 30,
            "maps_uri": "https://maps.google.com/?cid=123",
            "reviews": [],
        }

    monkeypatch.setattr(gr, "_fetch_place_details", _fetch_mock)

    gr.refrescar_resenas_cache(langs=("es", "en"))

    assert gr.obtener_resenas_cache("es")["status"] == "ok"
    assert gr.obtener_resenas_cache("es")["rating"] == 4.9
    assert gr.obtener_resenas_cache("en")["rating"] == 4.9

    html_actualizado = html_es.read_text(encoding="utf-8")
    assert '"ratingValue":"4.9"' in html_actualizado
    assert '"reviewCount":"30"' in html_actualizado


def test_refrescar_resenas_cache_conserva_el_caché_previo_si_un_idioma_falla(monkeypatch, tmp_path):
    monkeypatch.setattr(gr, "_AGGREGATE_RATING_FILES", ())
    gr._cache["en"] = {"status": "ok", "rating": 4.5, "user_rating_count": 12, "reviews": []}

    def _fetch_mock(lang):
        if lang == "es":
            return {"rating": 4.9, "user_rating_count": 30, "maps_uri": "", "reviews": []}
        return None  # "en" falla

    monkeypatch.setattr(gr, "_fetch_place_details", _fetch_mock)

    gr.refrescar_resenas_cache(langs=("es", "en"))

    assert gr.obtener_resenas_cache("es")["rating"] == 4.9
    # "en" conserva el valor anterior en vez de vaciarse por el fallo puntual.
    assert gr.obtener_resenas_cache("en")["rating"] == 4.5


def test_obtener_resenas_cache_con_idioma_no_cacheado_devuelve_unavailable():
    resultado = gr.obtener_resenas_cache("fr")

    assert resultado == {"status": "unavailable", "reviews": []}
