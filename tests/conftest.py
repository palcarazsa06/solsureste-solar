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
