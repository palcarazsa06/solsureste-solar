import json

import httpx
import pytest

import tools.crm_tools as crm_tools


class _RespuestaFake:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.fixture(autouse=True)
def _sin_espera_real(monkeypatch):
    # Los reintentos usan asyncio.sleep(1) entre intentos — en los tests no queremos
    # esperar de verdad, solo confirmar que el reintento ocurre.
    monkeypatch.setattr(crm_tools, "ESPERA_ENTRE_INTENTOS_S", 0)


@pytest.mark.asyncio
async def test_enviar_lead_crm_reintenta_tras_fallo_transitorio_y_acaba_en_exito(monkeypatch):
    monkeypatch.setattr(crm_tools, "WEBHOOK_URL", "https://webhook.example/test")

    llamadas = []

    async def _post_mock(self, url, json=None):
        llamadas.append(json)
        if len(llamadas) == 1:
            raise httpx.ConnectTimeout("timeout simulado")
        return _RespuestaFake(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_mock)

    resultado = await crm_tools.enviar_lead_crm("Ana", "666123456", "Murcia", "placas")

    assert json.loads(resultado)["status"] == "success"
    assert len(llamadas) == 2


@pytest.mark.asyncio
async def test_enviar_lead_crm_devuelve_error_tras_agotar_los_intentos(monkeypatch):
    monkeypatch.setattr(crm_tools, "WEBHOOK_URL", "https://webhook.example/test")

    llamadas = []

    async def _post_mock(self, url, json=None):
        llamadas.append(json)
        return _RespuestaFake(500)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_mock)

    resultado = await crm_tools.enviar_lead_crm("Ana", "666123456", "Murcia", "placas")

    assert json.loads(resultado)["status"] == "error"
    assert len(llamadas) == crm_tools.MAX_INTENTOS


@pytest.mark.asyncio
async def test_enviar_lead_crm_sin_webhook_configurado_no_hace_ninguna_llamada(monkeypatch):
    monkeypatch.setattr(crm_tools, "WEBHOOK_URL", None)

    llamadas = []

    async def _post_mock(self, url, json=None):
        llamadas.append(json)
        return _RespuestaFake(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_mock)

    resultado = await crm_tools.enviar_lead_crm("Ana", "666123456", "Murcia", "placas")

    assert json.loads(resultado)["status"] == "skipped"
    assert llamadas == []
