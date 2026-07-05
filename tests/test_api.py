import api


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
