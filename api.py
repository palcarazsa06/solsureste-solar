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
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, EmailStr
import uvicorn

from main import procesar_mensaje
from database import get_all_conversaciones, guardar_lead_directo, toggle_gestionado, eliminar_conversacion, get_coste_historico
from tools.crm_tools import enviar_lead_crm
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
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# --- CACHE-CONTROL PARA ESTÁTICOS ---
_CACHE_RULES = (
    ("/images/", "public, max-age=604800, immutable"),
    ("/videos/", "public, max-age=604800, immutable"),
    ("/icon-", "public, max-age=604800, immutable"),
    ("/styles.css", "public, max-age=3600"),
    ("/script.js", "public, max-age=3600"),
    ("/consent.js", "public, max-age=3600"),
)

@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    for prefix, value in _CACHE_RULES:
        if request.url.path.startswith(prefix):
            response.headers["Cache-Control"] = value
            break
    return response

# --- RATE LIMIT ---
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
    ip = request.client.host if request.client else "desconocida"
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
        ip = request.client.host if request.client else "desconocida"
        logger.warning(f"Intento de acceso admin fallido desde {ip} — usuario: '{credentials.username}'")
        raise HTTPException(
            status_code=401,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic"},
        )

# --- CORS ---
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)

# --- 0. ENDPOINT DE SESIÓN ---
@app.post("/session")
def crear_session():
    """Genera un token de sesión firmado por el servidor."""
    return {"session_id": _generar_session()}

# --- 1. ENDPOINT DEL CHATBOT WEB ---
class MensajeEntrante(BaseModel):
    user_id: str = Field(max_length=200)
    mensaje: str = Field(min_length=1, max_length=2000)

@app.post("/chat")
async def chat_endpoint(req: MensajeEntrante, request: Request, _rl=Depends(rate_limit_dep)):
    user_id = _validar_session(req.user_id)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Sesión inválida. Recarga la página.")

    try:
        respuesta_ia = await procesar_mensaje(user_id, req.mensaje)
        return {"status": "success", "user_id": req.user_id, "respuesta": respuesta_ia}
    except Exception as e:
        logger.error(f"Error procesando mensaje de {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo procesar el mensaje, inténtalo de nuevo.")

# --- 2. ENDPOINT DEL FORMULARIO DIRECTO ---
class FormularioPresupuesto(BaseModel):
    nombre: str = Field(max_length=100)
    apellido: str = Field(max_length=100)
    telefono: str = Field(max_length=20)
    correo: EmailStr
    ciudad: str = Field(max_length=100)
    tipo_instalacion: str = Field(max_length=200)
    mensaje: str = Field(default="", max_length=2000)

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

@app.get("/admin")
def read_admin(_auth=Depends(verificar_admin)):
    return FileResponse("static/admin.html")

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

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    logger.info("🚀 Servidor Web listo en http://localhost:8000")
    logger.info("👉 Abre http://localhost:8000 en tu navegador para probar el chat.")
    logger.info("👉 Abre http://localhost:8000/admin para ver tu panel de control.")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
