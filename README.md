# Solsureste Solar

Landing page + motor de ventas conversacional para Solsureste Solar (instalación de placas solares y
huertos solares en Murcia y Alicante). Backend FastAPI con arquitectura multi-agente (router
supervisor → Cualificador/Agendador), RAG sobre ChromaDB, integración con Google Calendar y webhook
CRM. Desplegado en Render, dominio de producción `solsurestesolar.com`.

El frontend (HTML/CSS/JS estático, sin build step) vive en `static/` y se sirve desde el propio
FastAPI junto con la API.

Para arquitectura completa, comandos, variables de entorno y detalles de implementación, ver
[`CLAUDE.md`](CLAUDE.md) — es la fuente de verdad de este repo y se mantiene actualizado con cada
cambio relevante.

## Arranque rápido

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # rellenar OPENAI_API_KEY, ADMIN_USER/PASSWORD, CRM_WEBHOOK_URL, etc.
python api.py          # servidor dev en localhost:8000
```

## Tests

```bash
pip install pytest pytest-asyncio pytest-socket   # una vez, no están en requirements.txt
pytest -q                                          # tests unitarios (recorte de historial, sesiones HMAC, guardrails)
./test_conversacion.sh                             # regresión end-to-end vía curl+jq contra un servidor ya corriendo
```

Los tests de `pytest` corren también en cada push/PR vía GitHub Actions
(`.github/workflows/tests.yml`), sin necesidad de configurar ningún secret.
