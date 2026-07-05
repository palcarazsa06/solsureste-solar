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
