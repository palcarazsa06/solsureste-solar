import os
import secrets
import time
import hmac as hmac_lib
import hashlib
import uuid as uuid_module
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, EmailStr, field_validator
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import uvicorn

from main import procesar_mensaje
from database import get_all_conversaciones, guardar_lead_directo, toggle_gestionado, eliminar_conversacion, get_coste_historico, get_coste_sesion, purgar_conversaciones_antiguas
from tools.crm_tools import enviar_lead_crm
from tools.rag_tools import collection as rag_collection
from google_reviews import refrescar_resenas_cache, obtener_resenas_cache
from logging_config import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Agencia IA - Motor de Ventas")

# --- SESIONES HMAC ---
# Si SECRET_KEY no está definida (dev), se acepta cualquier user_id.
_SECRET = os.getenv("SECRET_KEY", "").encode()

def _generar_session() -> str:
    sid = str(uuid_module.uuid4())
    sig = hmac_lib.new(_SECRET, sid.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{sid}.{sig}"

def _validar_session(token: str) -> str | None:
    """Devuelve el UUID si el token es válido, None si no.
    En modo dev (sin SECRET_KEY) acepta cualquier valor."""
    if not _SECRET:
        return token
    sid, _, sig = token.partition(".")
    if not sig:
        return None
    expected = hmac_lib.new(_SECRET, sid.encode(), hashlib.sha256).hexdigest()[:16]
    return sid if hmac_lib.compare_digest(sig, expected) else None

# --- SECURITY HEADERS ---
# style-src necesita 'unsafe-inline': las páginas autocontenidas (ciudades/legales/faq/404)
# usan bloques <style> internos y no hay build step para generar nonces — es una decisión
# permanente, no un paso temporal a quitar cuando se termine de limpiar index.html.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://www.googletagmanager.com https://www.clarity.ms; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "img-src 'self' data: https://www.google-analytics.com https://www.googletagmanager.com https://lh3.googleusercontent.com; "
    "connect-src 'self' https://www.google-analytics.com https://region1.google-analytics.com "
    "https://www.clarity.ms; "
    "frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'"
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = _CSP
    return response

# --- CACHE-CONTROL PARA ESTÁTICOS ---
_CACHE_RULES = (
    ("/images/", "public, max-age=604800, immutable"),
    ("/videos/", "public, max-age=604800, immutable"),
    ("/icon-", "public, max-age=604800, immutable"),
    ("/fonts/", "public, max-age=604800, immutable"),
    ("/styles.css", "public, max-age=3600"),
    ("/script.js", "public, max-age=3600"),
    ("/consent.js", "public, max-age=3600"),
    ("/api/reviews", "public, max-age=3600"),
)

@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    for prefix, value in _CACHE_RULES:
        if request.url.path.startswith(prefix):
            response.headers["Cache-Control"] = value
            break
    return response

# --- BLOQUEO DE ESTÁTICOS SENSIBLES ---
# static/ se sirve entero como archivos estáticos (ver mount al final del archivo). Si algún
# archivo sensible (base de datos, credenciales, .env) termina ahí por error humano — ya
# pasó una vez con un static/agencia.db residual —, esto evita que quede servido sin auth
# a cualquiera que adivine la URL, sin depender de que nadie se acuerde de borrarlo.
_PATRONES_ESTATICO_BLOQUEADO = (".db", ".sqlite", ".sqlite3", ".env", "credenciales_google")

@app.middleware("http")
async def bloquear_estaticos_sensibles(request: Request, call_next):
    path_lower = request.url.path.lower()
    if any(patron in path_lower for patron in _PATRONES_ESTATICO_BLOQUEADO):
        return Response(status_code=404)
    return await call_next(request)

# --- IP REAL DEL CLIENTE ---
# En Render (y otros hosts detrás de proxy), request.client.host es la IP del proxy, no la del
# visitante. TRUST_PROXY=true habilita leer X-Forwarded-For — solo activar si el proxy delante
# realmente lo rellena (si no, es spoofable por cualquier cliente).
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"

def _client_ip(request: Request) -> str:
    if TRUST_PROXY:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"

# --- RATE LIMIT ---
# Contador en memoria del proceso — correcto mientras Render corra 1 solo worker/instancia
# (el arranque de producción documentado, `uvicorn api:app --host 0.0.0.0 --port $PORT`,
# no lleva `--workers`, por lo que hoy siempre es así). Si en el futuro se escala a
# `--workers > 1` o a más de una instancia, cada proceso llevaría su propio contador y
# el límite efectivo total se multiplicaría sin control — habría que migrar a un backend
# compartido (p. ej. Redis) para que vuelva a ser un límite global real.
RATE_LIMIT_MAX_PETICIONES = 20
RATE_LIMIT_VENTANA_SEGUNDOS = 60
_peticiones_por_ip = defaultdict(deque)

def verificar_rate_limit(ip: str) -> bool:
    ahora = time.time()
    peticiones = _peticiones_por_ip[ip]
    while peticiones and ahora - peticiones[0] > RATE_LIMIT_VENTANA_SEGUNDOS:
        peticiones.popleft()
    if len(peticiones) >= RATE_LIMIT_MAX_PETICIONES:
        return False
    peticiones.append(ahora)
    return True

def rate_limit_dep(request: Request):
    ip = _client_ip(request)
    if not verificar_rate_limit(ip):
        logger.warning(f"Rate limit excedido para IP {ip}")
        raise HTTPException(status_code=429, detail="Demasiadas peticiones, espera un momento.")

# --- AUTENTICACIÓN DEL PANEL DE ADMIN ---
security = HTTPBasic()

def verificar_admin(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    """Protege los endpoints de admin con usuario/contraseña definidos en .env."""
    usuario_correcto = secrets.compare_digest(credentials.username, os.getenv("ADMIN_USER", ""))
    password_correcta = secrets.compare_digest(credentials.password, os.getenv("ADMIN_PASSWORD", ""))
    if not (usuario_correcto and password_correcta):
        ip = _client_ip(request)
        logger.warning(f"Intento de acceso admin fallido desde {ip} — usuario: '{credentials.username}'")
        raise HTTPException(
            status_code=401,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic"},
        )

# --- CORS ---
# Si ALLOWED_ORIGINS no está definida, NO se cae a "*" (auditoría de seguridad): el fallback es
# el dominio real de producción, para que un despiste al configurar el entorno de Render no deje
# la API abierta a cualquier origen. Desarrollo local sigue funcionando porque .env.example ya
# documenta ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000.
_ORIGINS_PRODUCCION = "https://solsurestesolar.com,https://www.solsurestesolar.com"
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", _ORIGINS_PRODUCCION).split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)

# --- 0. ENDPOINT DE SESIÓN ---
@app.post("/session")
def crear_session(_rl=Depends(rate_limit_dep)):
    """Genera un token de sesión firmado por el servidor."""
    return {"session_id": _generar_session()}

# --- 1. ENDPOINT DEL CHATBOT WEB ---
class MensajeEntrante(BaseModel):
    user_id: str = Field(max_length=200)
    mensaje: str = Field(min_length=1, max_length=2000)

CHAT_MAX_COSTE_USD = float(os.getenv("CHAT_MAX_COSTE_USD", "0.50"))
RETENCION_DIAS = int(os.getenv("RETENCION_DIAS", "730"))
MENSAJE_LIMITE_COSTE = (
    "Hemos llegado al límite de esta conversación automática. "
    "Llámanos al 968 869 532 y seguimos encantados por teléfono."
)

@app.post("/chat")
async def chat_endpoint(req: MensajeEntrante, request: Request, _rl=Depends(rate_limit_dep)):
    user_id = _validar_session(req.user_id)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Sesión inválida. Recarga la página.")

    if get_coste_sesion(user_id) >= CHAT_MAX_COSTE_USD:
        return {"status": "success", "user_id": req.user_id, "respuesta": MENSAJE_LIMITE_COSTE}

    try:
        respuesta_ia = await procesar_mensaje(user_id, req.mensaje)
        return {"status": "success", "user_id": req.user_id, "respuesta": respuesta_ia}
    except Exception as e:
        logger.error(f"Error procesando mensaje de {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo procesar el mensaje, inténtalo de nuevo.")

# --- 2. ENDPOINT DEL FORMULARIO DIRECTO ---
# TELEFONO_ES_RE vive en validadores.py: main.py también lo necesita para validar el
# teléfono que extrae el LLM del chat antes de enviarlo al CRM (ver auditoría de robustez).
from validadores import TELEFONO_ES_RE

class FormularioPresupuesto(BaseModel):
    nombre: str = Field(max_length=100)
    apellido: str = Field(max_length=100)
    telefono: str = Field(max_length=20)
    correo: EmailStr
    ciudad: str = Field(max_length=100)
    tipo_instalacion: str = Field(max_length=200)
    mensaje: str = Field(default="", max_length=2000)

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: str) -> str:
        if not TELEFONO_ES_RE.match(v.strip()):
            raise ValueError("Teléfono no válido. Usa un móvil o fijo español (ej: 666 123 456).")
        return v

@app.post("/presupuesto")
async def presupuesto_endpoint(req: FormularioPresupuesto, _rl=Depends(rate_limit_dep)):
    try:
        user_id = guardar_lead_directo(
            nombre=req.nombre,
            apellido=req.apellido,
            telefono=req.telefono,
            correo=str(req.correo),
            ciudad=req.ciudad,
            tipo_instalacion=req.tipo_instalacion,
            mensaje=req.mensaje,
        )
        try:
            necesidad = f"{req.tipo_instalacion} — {req.mensaje}" if req.mensaje else req.tipo_instalacion
            await enviar_lead_crm(
                nombre=f"{req.nombre} {req.apellido}",
                telefono=req.telefono,
                ubicacion=req.ciudad,
                necesidad=necesidad,
            )
        except Exception:
            pass
        try:
            from tools.email_tools import enviar_alerta_lead_email
            import asyncio
            asyncio.create_task(enviar_alerta_lead_email(
                nombre=f"{req.nombre} {req.apellido}",
                telefono=req.telefono,
                correo=str(req.correo),
                ciudad=req.ciudad,
                fuente="formulario"
            ))
        except Exception as e_email:
            logger.warning(f"No se pudo lanzar la alerta email del formulario: {e_email}")
        logger.info(f"Nuevo lead directo: {req.nombre} {req.apellido} | {req.telefono} | {req.ciudad}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error guardando formulario: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo guardar la solicitud.")

# --- 3. PANEL DE CONTROL Y RUTAS WEB ---
@app.get("/api/leads")
def api_get_leads(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_dep)):
    return {"status": "success", "data": get_all_conversaciones(), "coste_historico": get_coste_historico()}

@app.patch("/api/leads/{user_id}/gestionado")
def api_toggle_gestionado(user_id: str, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_dep)):
    toggle_gestionado(user_id)
    return {"status": "ok"}

@app.delete("/api/leads/{user_id}")
def api_eliminar_lead(user_id: str, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_dep)):
    eliminar_conversacion(user_id)
    return {"status": "ok"}

@app.post("/api/admin/purgar-antiguos")
def api_purgar_antiguos(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_dep)):
    """Dispara manualmente la purga RGPD (la misma que corre a diario vía scheduler)."""
    filas = purgar_conversaciones_antiguas(RETENCION_DIAS)
    return {"status": "ok", "filas_borradas": filas}

@app.post("/api/admin/refrescar-resenas")
def api_refrescar_resenas(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_dep)):
    """Fuerza el refresco del caché de reseñas de Google (el mismo que corre a diario vía scheduler)."""
    refrescar_resenas_cache()
    return {
        "status": "ok",
        "es": obtener_resenas_cache("es").get("fetched_at"),
        "en": obtener_resenas_cache("en").get("fetched_at"),
    }

@app.get("/api/reviews")
def api_get_reviews(lang: str = "es"):
    lang = lang if lang in ("es", "en") else "es"
    return obtener_resenas_cache(lang)

@app.get("/health")
def health(_rl=Depends(rate_limit_dep)):
    """Chequeo barato para uptime-checkers externos: confirma que el proceso responde y que
    ChromaDB (el vector store del RAG) es accesible. No comprueba Google Calendar (requiere leer
    credenciales de disco + red) ni OpenAI (costaría dinero en cada ping) — ver CLAUDE.md."""
    try:
        chroma_count = rag_collection.count()
    except Exception as e:
        logger.error(f"[HEALTH] ChromaDB no responde: {e}", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "error", "detalle": "chroma no disponible"})
    return {"status": "ok", "chroma_count": chroma_count}

@app.get("/admin")
def read_admin(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_dep)):
    return FileResponse("admin_panel/admin.html")

@app.get("/admin.js")
def read_admin_js(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_dep)):
    # Fuera de static/ a propósito: si viviera ahí, StaticFiles lo serviría sin pasar
    # por verificar_admin (ver auditoría de seguridad, "admin.html/admin.js sin auth").
    return FileResponse("admin_panel/admin.js", media_type="application/javascript")

@app.get("/en")
def home_en_page():
    return FileResponse("static/en/index.html")

@app.get("/faq")
def faq_page():
    return FileResponse("static/faq.html")

@app.get("/aviso-legal")
def aviso_legal_page():
    return FileResponse("static/aviso-legal.html")

@app.get("/privacidad")
def privacidad_page():
    return FileResponse("static/privacidad.html")

@app.get("/cookies")
def cookies_page():
    return FileResponse("static/cookies.html")

@app.get("/placas-solares-murcia")
def placas_solares_murcia_page():
    return FileResponse("static/placas-solares-murcia.html")

@app.get("/placas-solares-alicante")
def placas_solares_alicante_page():
    return FileResponse("static/placas-solares-alicante.html")

@app.get("/placas-solares-lorca")
def placas_solares_lorca_page():
    return FileResponse("static/placas-solares-lorca.html")

@app.get("/placas-solares-cartagena")
def placas_solares_cartagena_page():
    return FileResponse("static/placas-solares-cartagena.html")

@app.get("/placas-solares-molina-de-segura")
def placas_solares_molina_de_segura_page():
    return FileResponse("static/placas-solares-molina-de-segura.html")

@app.get("/placas-solares-orihuela")
def placas_solares_orihuela_page():
    return FileResponse("static/placas-solares-orihuela.html")

@app.get("/placas-solares-torrevieja")
def placas_solares_torrevieja_page():
    return FileResponse("static/placas-solares-torrevieja.html")

@app.get("/placas-solares-orihuela-costa")
def placas_solares_orihuela_costa_page():
    return FileResponse("static/placas-solares-orihuela-costa.html")

@app.get("/placas-solares-pilar-de-la-horadada")
def placas_solares_pilar_de_la_horadada_page():
    return FileResponse("static/placas-solares-pilar-de-la-horadada.html")

@app.get("/blog")
def blog_index_page():
    return FileResponse("static/blog/index.html")

@app.get("/blog/index.html")
def redirect_blog_index_html():
    return RedirectResponse(url="/blog", status_code=301)

@app.on_event("startup")
def _iniciar_scheduler_purga():
    """Purga diaria de conversaciones más antiguas que RETENCION_DIAS (RGPD) y refresco
    diario del caché de reseñas de Google. Un solo worker (ver CLAUDE.md) => sin riesgo
    de ejecuciones duplicadas."""
    scheduler = BackgroundScheduler(timezone="Europe/Madrid")
    scheduler.add_job(
        lambda: purgar_conversaciones_antiguas(RETENCION_DIAS),
        CronTrigger(hour=4, minute=0),
    )
    scheduler.add_job(refrescar_resenas_cache, CronTrigger(hour=4, minute=5))
    scheduler.start()
    # Poblado inmediato al arrancar: el filesystem de Render es efímero entre redeploys,
    # no conviene esperar al cron de las 4:05 para tener reseñas frescas tras un deploy.
    refrescar_resenas_cache()

# Rutas .html duplicadas: StaticFiles(html=True) sirve cada página también por su ruta
# literal con extensión (p. ej. /placas-solares-murcia.html), en paralelo a la ruta limpia
# ya registrada arriba. Cada página lleva su <link rel="canonical"> a la versión limpia, pero
# eso no evita que Google gaste crawl budget rastreando ambas — se redirige con 301 para
# consolidar señales en una sola URL. Debe registrarse antes del mount para tener prioridad.
_REDIRECTS_HTML_LIMPIAS = {
    "index": "/",
    "faq": "/faq",
    "aviso-legal": "/aviso-legal",
    "privacidad": "/privacidad",
    "cookies": "/cookies",
    "placas-solares-murcia": "/placas-solares-murcia",
    "placas-solares-alicante": "/placas-solares-alicante",
    "placas-solares-lorca": "/placas-solares-lorca",
    "placas-solares-cartagena": "/placas-solares-cartagena",
    "placas-solares-molina-de-segura": "/placas-solares-molina-de-segura",
    "placas-solares-orihuela": "/placas-solares-orihuela",
    "placas-solares-torrevieja": "/placas-solares-torrevieja",
    "placas-solares-orihuela-costa": "/placas-solares-orihuela-costa",
    "placas-solares-pilar-de-la-horadada": "/placas-solares-pilar-de-la-horadada",
}

@app.get("/en/index.html")
def redirect_en_index_html():
    return RedirectResponse(url="/en", status_code=301)

@app.get("/{nombre_pagina}.html")
def redirect_html_a_ruta_limpia(nombre_pagina: str):
    destino = _REDIRECTS_HTML_LIMPIAS.get(nombre_pagina)
    if destino is None:
        raise HTTPException(status_code=404)
    return RedirectResponse(url=destino, status_code=301)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    logger.info("🚀 Servidor Web listo en http://localhost:8000")
    logger.info("👉 Abre http://localhost:8000 en tu navegador para probar el chat.")
    logger.info("👉 Abre http://localhost:8000/admin para ver tu panel de control.")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
