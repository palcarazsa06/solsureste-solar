import asyncio
import time
import types

import pytest

import database as db
import main
from agentes.supervisor import DecisionRuta
from main import recortar_historial


def test_recortar_historial_no_trunca_si_ya_es_corto():
    historial = [{"role": "user", "content": f"m{i}"} for i in range(5)]
    assert recortar_historial(historial, max_mensajes=12) == historial


def test_recortar_historial_no_parte_un_tool_call_a_medias():
    historial = [{"role": "user", "content": f"m{i}"} for i in range(2)]
    historial.append({"role": "assistant", "tool_calls": [{"id": "call_1"}]})
    historial.append({"role": "tool", "tool_call_id": "call_1", "content": "resultado"})
    historial += [{"role": "user", "content": f"m{i}"} for i in range(4, 14)]

    # indice_corte "ingenuo" = len(14) - 12 = 2, que caería justo en el mensaje
    # assistant con tool_calls — debe retroceder hasta el mensaje anterior en vez
    # de partir el par tool_calls/tool.
    recortado = recortar_historial(historial, max_mensajes=12)

    assert recortado[0] == historial[1]
    assert recortado[1]["role"] == "assistant" and "tool_calls" in recortado[1]
    assert recortado[2]["role"] == "tool"


def test_recortar_historial_retrocede_si_el_corte_cae_justo_en_un_tool():
    historial = [
        {"role": "user", "content": "m0"},
        {"role": "assistant", "tool_calls": [{"id": "call_1"}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "resultado"},
        {"role": "user", "content": "m3"},
    ]
    # indice_corte ingenuo = 4 - 2 = 2, que aterriza justo en el mensaje "tool" —
    # debe retroceder (tool -> assistant con tool_calls -> user) hasta el índice 0.
    recortado = recortar_historial(historial, max_mensajes=2)

    assert recortado[0] == historial[0]


def test_recortar_historial_con_multiples_pares_tool_calls_retrocede_solo_sobre_el_ultimo():
    historial = [
        {"role": "user", "content": "m0"},
        {"role": "user", "content": "m1"},
        {"role": "assistant", "tool_calls": [{"id": "call_1"}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "resultado_1"},
    ]
    historial += [{"role": "user", "content": f"m{i}"} for i in range(4, 7)]
    historial += [
        {"role": "assistant", "tool_calls": [{"id": "call_2"}]},
        {"role": "tool", "tool_call_id": "call_2", "content": "resultado_2"},
    ]
    historial += [{"role": "user", "content": f"m{i}"} for i in range(9, 20)]

    # len(historial) == 20; indice_corte ingenuo = 20 - 12 = 8, que aterriza justo en
    # el "tool" del SEGUNDO par (índice 8) — debe retroceder sobre ESE par (tool ->
    # assistant con tool_calls -> índice 6, un "user" normal), sin verse afectado por
    # el primer par (call_1), que queda fuera del recorte y no debe causar más retroceso.
    recortado = recortar_historial(historial, max_mensajes=12)

    assert len(recortado) == 14
    assert recortado[0] == historial[6]
    assert recortado[1]["role"] == "assistant" and recortado[1]["tool_calls"][0]["id"] == "call_2"
    assert recortado[2]["role"] == "tool" and recortado[2]["tool_call_id"] == "call_2"


@pytest.mark.asyncio
async def test_guardrail_y_supervisor_se_ejecutan_en_paralelo(monkeypatch):
    """Auditoría de latencia: antes, el guardrail de entrada y el supervisor se
    esperaban de forma secuencial. Si ambos tardan DEMORA segundos, el turno debía
    tardar ~2*DEMORA antes del fix y ~1*DEMORA después (se solapan vía asyncio.gather)."""
    user_id = "test_paralelismo_latencia"
    db.get_conversacion(user_id)

    DEMORA = 0.3

    async def _guardrail_lento(mensaje, historial):
        await asyncio.sleep(DEMORA)
        # Bloqueado a propósito: así procesar_mensaje retorna justo después del
        # gather, sin arrastrar mocks del resto del flujo del especialista.
        return False, "bloqueado por el test", 0, 0

    async def _supervisor_lento(*args, **kwargs):
        await asyncio.sleep(DEMORA)
        decision = DecisionRuta(razonamiento="n/a", hay_fecha_y_hora_exacta=False, siguiente_agente="CUALIFICADOR")
        return _RespuestaParsed(decision)

    monkeypatch.setattr(main, "verificar_input", _guardrail_lento)
    monkeypatch.setattr(main.client.beta.chat.completions, "parse", _supervisor_lento)

    inicio = time.monotonic()
    resultado = await main.procesar_mensaje(user_id, "mensaje de prueba de latencia")
    duracion = time.monotonic() - inicio

    assert resultado == "bloqueado por el test"
    assert duracion < DEMORA * 1.5, f"tardó {duracion:.2f}s — ¿se están ejecutando en serie otra vez?"


class _RespuestaSimple:
    def __init__(self, contenido, tool_calls=None, prompt_tokens=0, completion_tokens=0):
        mensaje = types.SimpleNamespace(content=contenido, tool_calls=tool_calls)
        self.choices = [types.SimpleNamespace(message=mensaje)]
        self.usage = types.SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


class _RespuestaParsed:
    def __init__(self, parsed, prompt_tokens=0, completion_tokens=0):
        mensaje = types.SimpleNamespace(parsed=parsed)
        self.choices = [types.SimpleNamespace(message=mensaje)]
        self.usage = types.SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


@pytest.mark.asyncio
async def test_extraccion_de_lead_recibe_el_historial_completo_no_solo_los_ultimos_12(monkeypatch):
    """Auditoría de seguridad/robustez: si el cliente da su nombre al principio de una
    conversación larga, el recorte a 12 mensajes lo dejaba fuera de la ventana que se
    mandaba a la extracción del lead. _extraer_y_guardar_lead debe recibir el historial
    completo, no el recorte usado para el prompt del supervisor/agente."""
    user_id = "test_lead_historial_completo"

    # Crea la fila (get_conversacion la crea si no existe) y siembra 15 mensajes: el
    # nombre solo aparece en el primero, fuera de la ventana de recorte de 12.
    db.get_conversacion(user_id)
    db.append_mensaje(user_id, "user", "Hola, soy Marisol Contacto")
    for i in range(14):
        db.append_mensaje(user_id, "assistant" if i % 2 else "user", f"mensaje de relleno {i}")

    async def _guardrail_ok(mensaje, historial):
        return True, None, 0, 0
    monkeypatch.setattr(main, "verificar_input", _guardrail_ok)

    decision = DecisionRuta(
        razonamiento="Todos los datos presentes y fecha/hora explícitas",
        hay_fecha_y_hora_exacta=True,
        siguiente_agente="AGENDADOR",
    )

    async def _parse_mock(*args, **kwargs):
        return _RespuestaParsed(decision)

    llamada = {}

    async def _extraer_mock(uid, historial):
        llamada["historial"] = historial
        return 0, 0
    monkeypatch.setattr(main, "_extraer_y_guardar_lead", _extraer_mock)

    async def _create_mock(*args, **kwargs):
        return _RespuestaSimple("Perfecto, tu cita queda confirmada.")

    monkeypatch.setattr(main.client.beta.chat.completions, "parse", _parse_mock)
    monkeypatch.setattr(main.client.chat.completions, "create", _create_mock)

    await main.procesar_mensaje(user_id, "el jueves a las 10, gracias")

    assert "historial" in llamada
    historial_recibido = llamada["historial"]
    # 15 mensajes sembrados + el mensaje nuevo de este turno = 16, muy por encima
    # de los 12 que permitía pasar el recorte usado antes del fix.
    assert len(historial_recibido) >= 16
    assert any("Marisol Contacto" in (m.get("content") or "") for m in historial_recibido)


def _mock_extraccion_json(monkeypatch, contenido_json):
    """Mockea la llamada de extracción JSON que hace _extraer_y_guardar_lead."""
    async def _create_mock(*args, **kwargs):
        return _RespuestaSimple(contenido_json)
    monkeypatch.setattr(main.client.chat.completions, "create", _create_mock)


@pytest.mark.asyncio
async def test_extraccion_de_lead_envia_al_crm_si_los_datos_son_validos(monkeypatch):
    user_id = "test_lead_datos_validos"
    db.get_conversacion(user_id)

    _mock_extraccion_json(monkeypatch, (
        '{"nombre": "Ana Garcia", "correo": "ana@example.com", '
        '"telefono": "666123456", "ciudad": "Murcia"}'
    ))

    llamadas_crm = []

    async def _crm_mock(**kwargs):
        llamadas_crm.append(kwargs)
        return {"status": "ok"}
    monkeypatch.setattr(main, "enviar_lead_crm", _crm_mock)

    import tools.email_tools as email_tools
    monkeypatch.setattr(email_tools, "enviar_alerta_lead_email", lambda **kw: _noop_coro())

    await main._extraer_y_guardar_lead(user_id, [{"role": "user", "content": "hola"}])

    assert len(llamadas_crm) == 1
    assert llamadas_crm[0]["telefono"] == "666123456"
    assert db.crm_ya_enviado(user_id) is True


@pytest.mark.asyncio
async def test_extraccion_de_lead_no_envia_al_crm_si_el_telefono_es_invalido(monkeypatch, caplog):
    user_id = "test_lead_datos_invalidos"
    db.get_conversacion(user_id)

    _mock_extraccion_json(monkeypatch, (
        '{"nombre": "Luis Perez", "correo": "luis@example.com", '
        '"telefono": "N/A", "ciudad": "Alicante"}'
    ))

    llamadas_crm = []

    async def _crm_mock(**kwargs):
        llamadas_crm.append(kwargs)
        return {"status": "ok"}
    monkeypatch.setattr(main, "enviar_lead_crm", _crm_mock)

    import tools.email_tools as email_tools
    monkeypatch.setattr(email_tools, "enviar_alerta_lead_email", lambda **kw: _noop_coro())

    with caplog.at_level("WARNING"):
        await main._extraer_y_guardar_lead(user_id, [{"role": "user", "content": "hola"}])

    # No se llama al CRM con un teléfono inválido...
    assert llamadas_crm == []
    # ...pero el dato sigue guardado en SQLite, no se pierde el lead.
    _, historial = db.get_conversacion(user_id)
    fila = db.get_all_conversaciones()
    lead = next(l for l in fila if l["user_id"] == user_id)
    assert lead["nombre"] == "Luis Perez"
    assert lead["telefono"] == "N/A"
    assert "no se envía al CRM" in caplog.text.lower() or "no válidos" in caplog.text.lower()


async def _noop_coro(*args, **kwargs):
    return None
