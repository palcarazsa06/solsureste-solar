import os
import tempfile

# Debe ejecutarse antes de que cualquier test importe main/api/database/guardrails/tools —
# esos módulos construyen clientes (OpenAI, ChromaDB) a nivel de import. Los valores son
# cadenas falsas: solo sirven para que la construcción no falle, nunca se usa una API key
# real (los tests mockean las llamadas a OpenAI, no las ejecutan).
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-not-a-real-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault("ADMIN_USER", "test-admin")
os.environ.setdefault("ADMIN_PASSWORD", "test-pass")
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="sss-test-")

import sys

import pytest


@pytest.fixture(autouse=True)
def _limpiar_bloqueo_admin():
    """El bloqueo por intentos fallidos de /admin es un contador global en memoria: sin
    limpiarlo, los tests que prueban credenciales incorrectas acabarían bloqueando la IP
    del TestClient para los tests siguientes. Solo actúa si `api` ya está importado, para
    no forzar su import (y el de ChromaDB/OpenAI) en tests que no lo necesitan."""
    api = sys.modules.get("api")
    if api is not None:
        api._fallos_admin_por_ip.clear()
    yield
    api = sys.modules.get("api")
    if api is not None:
        api._fallos_admin_por_ip.clear()
