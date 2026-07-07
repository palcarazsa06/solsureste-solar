import os

from fastapi.testclient import TestClient

import api

client = TestClient(api.app)

_PRESUPUESTO_VALIDO = {
    "nombre": "Ana",
    "apellido": "Garcia",
    "telefono": "666123456",
    "correo": "ana@example.com",
    "ciudad": "Murcia",
    "tipo_instalacion": "Residencial",
    "mensaje": "Test automatizado",
}


def test_generar_y_validar_session_token_valido():
    token = api._generar_session()
    sid, _, sig = token.partition(".")

    assert sig
    assert api._validar_session(token) == sid


def test_validar_session_firma_manipulada_devuelve_none():
    token = api._generar_session()
    sid, _, _ = token.partition(".")
    token_manipulado = f"{sid}.0000000000000000"

    assert api._validar_session(token_manipulado) is None


def test_validar_session_sin_punto_devuelve_none():
    assert api._validar_session("token-sin-firma") is None


def test_validar_session_modo_dev_sin_secret_key(monkeypatch):
    """Si SECRET_KEY no está definida, el sistema acepta cualquier user_id (modo dev)."""
    monkeypatch.setattr(api, "_SECRET", b"")
    assert api._validar_session("cualquier-cosa") == "cualquier-cosa"


def test_allowed_origins_fallback_no_es_wildcard_abierto(monkeypatch):
    """Auditoría de seguridad: si ALLOWED_ORIGINS no está definida en el entorno, el
    fallback debe ser el dominio real de producción, nunca '*' (que dejaría la API
    abierta a cualquier origen si se olvida configurar la variable en Render).
    Verificado también end-to-end contra un servidor real: sin ALLOWED_ORIGINS, un
    Origin ajeno no recibe Access-Control-Allow-Origin, y el dominio real sí."""
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    origenes_fallback = os.getenv("ALLOWED_ORIGINS", api._ORIGINS_PRODUCCION).split(",")

    assert "*" not in origenes_fallback
    assert "https://solsurestesolar.com" in origenes_fallback
    assert "https://www.solsurestesolar.com" in origenes_fallback


def _mockear_efectos_secundarios(monkeypatch):
    """CRM y email son best-effort en /presupuesto: se mockean para no depender de red
    real (los tests corren con --disable-socket) ni de credenciales SMTP."""
    llamadas_crm = []

    async def _crm_mock(**kwargs):
        llamadas_crm.append(kwargs)
        return "ok"
    monkeypatch.setattr(api, "enviar_lead_crm", _crm_mock)

    import tools.email_tools as email_tools

    async def _email_mock(**kwargs):
        return None
    monkeypatch.setattr(email_tools, "enviar_alerta_lead_email", _email_mock)

    return llamadas_crm


def test_presupuesto_con_datos_validos_devuelve_200_y_envia_al_crm(monkeypatch):
    llamadas_crm = _mockear_efectos_secundarios(monkeypatch)

    respuesta = client.post("/presupuesto", json=_PRESUPUESTO_VALIDO)

    assert respuesta.status_code == 200
    assert len(llamadas_crm) == 1
    assert llamadas_crm[0]["telefono"] == "666123456"


def test_presupuesto_con_telefono_invalido_devuelve_422_y_no_llama_al_crm(monkeypatch):
    llamadas_crm = _mockear_efectos_secundarios(monkeypatch)

    payload = {**_PRESUPUESTO_VALIDO, "telefono": "123"}
    respuesta = client.post("/presupuesto", json=payload)

    assert respuesta.status_code == 422
    assert llamadas_crm == []
