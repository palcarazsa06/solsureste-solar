import os
import secrets
import time
import hmac as hmac_lib
import hashlib
import uuid as uuid_module
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File
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
from database import set_contenido as db_set_contenido, get_historial_contenido as db_get_historial_contenido, borrar_contenido as db_borrar_contenido
from database import get_faq as db_get_faq, crear_faq as db_crear_faq, actualizar_faq as db_actualizar_faq, borrar_faq as db_borrar_faq
from database import get_redireccion_articulo as db_get_redireccion_articulo, registrar_redireccion_articulo as db_registrar_redireccion_articulo
from database import crear_articulo as db_crear_articulo, actualizar_articulo as db_actualizar_articulo, borrar_articulo as db_borrar_articulo
import cms
import cms_blog
import cms_campos
import cms_faq
import cms_imagenes
import cms_sanitize
import cms_traduccion
from tools.crm_tools import enviar_lead_crm
from tools.rag_tools import collection as rag_collection
from google_reviews import refrescar_resenas_cache, obtener_resenas_cache
from templates_engine import templates
from logging_config import get_logger

logger = get_logger(__name__)

# Sin /docs, /redoc ni /openapi.json: en producción daban a cualquiera el mapa completo de la
# API, endpoints del panel de administración incluidos (auditoría 2026-11). Nada del proyecto
# consume el esquema.
app = FastAPI(title="Agencia IA - Motor de Ventas", docs_url=None, redoc_url=None, openapi_url=None)

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
    # `preload` solo declara que el dominio acepta entrar en la lista de precarga de los
    # navegadores; no tiene efecto hasta que alguien lo envía a hstspreload.org (paso manual
    # y difícil de deshacer, fuera de este repo).
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = _CSP
    return response

# --- CACHE-CONTROL PARA ESTÁTICOS ---
_CACHE_RULES = (
    ("/images/", "public, max-age=604800, immutable"),
    # Las imágenes subidas desde el panel llevan el hash del contenido en el nombre, así que
    # cachearlas para siempre es seguro: cambiar la foto cambia la URL.
    ("/uploads/", "public, max-age=604800, immutable"),
    ("/videos/", "public, max-age=604800, immutable"),
    ("/icon-", "public, max-age=604800, immutable"),
    ("/fonts/", "public, max-age=604800, immutable"),
    ("/styles.css", "public, max-age=3600"),
    ("/script.js", "public, max-age=3600"),
    ("/consent.js", "public, max-age=3600"),
    ("/fonts.css", "public, max-age=86400"),
    ("/api/reviews", "public, max-age=3600"),
)

# CSS/JS pedidos con huella (`?v=...`, la pone templates_engine.asset): su URL cambia cuando
# cambia el contenido, así que se pueden cachear un año. Sin huella (páginas estáticas que
# los enlazan a pelo) siguen con la regla corta de arriba.
_CACHE_VERSIONADO = "public, max-age=31536000, immutable"

@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if "v" in request.query_params and path.endswith((".css", ".js")) and response.status_code == 200:
        response.headers["Cache-Control"] = _CACHE_VERSIONADO
        return response
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
# El panel de administración necesita un límite mucho más alto que el público: editar una
# página del CMS son decenas de peticiones legítimas en pocos segundos (cargar los campos,
# guardar uno a uno, subir imágenes) mientras la vista de leads sigue haciendo polling cada
# 10 s. Con el límite público de 20/60s el editor se autobloquearía a media edición.
RATE_LIMIT_ADMIN_MAX_PETICIONES = 200
_peticiones_por_ip = defaultdict(deque)
_peticiones_admin_por_ip = defaultdict(deque)

def _verificar_ventana(registro: deque, maximo: int) -> bool:
    ahora = time.time()
    while registro and ahora - registro[0] > RATE_LIMIT_VENTANA_SEGUNDOS:
        registro.popleft()
    if len(registro) >= maximo:
        return False
    registro.append(ahora)
    return True

def verificar_rate_limit(ip: str) -> bool:
    return _verificar_ventana(_peticiones_por_ip[ip], RATE_LIMIT_MAX_PETICIONES)

def rate_limit_dep(request: Request):
    ip = _client_ip(request)
    if not verificar_rate_limit(ip):
        logger.warning(f"Rate limit excedido para IP {ip}")
        raise HTTPException(status_code=429, detail="Demasiadas peticiones, espera un momento.")

def rate_limit_admin_dep(request: Request):
    """Límite propio para los endpoints del panel. Contador separado del público, para que
    el trabajo del panel no consuma la cuota de los visitantes ni al revés."""
    ip = _client_ip(request)
    if not _verificar_ventana(_peticiones_admin_por_ip[ip], RATE_LIMIT_ADMIN_MAX_PETICIONES):
        logger.warning(f"Rate limit de admin excedido para IP {ip}")
        raise HTTPException(status_code=429, detail="Demasiadas peticiones, espera un momento.")

# --- AUTENTICACIÓN DEL PANEL DE ADMIN ---
security = HTTPBasic()

# Bloqueo por intentos fallidos: con solo el rate limit de 200/60s cabían decenas de miles de
# contraseñas al día por IP. Tras ADMIN_MAX_FALLOS fallos dentro de la ventana, esa IP queda
# bloqueada ADMIN_BLOQUEO_SEGUNDOS aunque luego acierte. Contador en memoria por proceso (mismas
# limitaciones que el rate limit: se reinicia con el proceso y exige 1 solo worker). Ojo: depende
# de que _client_ip vea la IP real (TRUST_PROXY); si no, todo el tráfico comparte una IP y un
# atacante bloquearía también al personal.
ADMIN_MAX_FALLOS = 5
ADMIN_BLOQUEO_SEGUNDOS = 15 * 60
_fallos_admin_por_ip = defaultdict(deque)

def _admin_bloqueada(ip: str) -> bool:
    fallos = _fallos_admin_por_ip[ip]
    ahora = time.time()
    while fallos and ahora - fallos[0] > ADMIN_BLOQUEO_SEGUNDOS:
        fallos.popleft()
    return len(fallos) >= ADMIN_MAX_FALLOS

def verificar_admin(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    """Protege los endpoints de admin con usuario/contraseña definidos en .env."""
    ip = _client_ip(request)
    if _admin_bloqueada(ip):
        logger.warning(f"Acceso admin rechazado: IP {ip} bloqueada por intentos fallidos")
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Espera 15 minutos.",
        )
    usuario_correcto = secrets.compare_digest(credentials.username, os.getenv("ADMIN_USER", ""))
    password_correcta = secrets.compare_digest(credentials.password, os.getenv("ADMIN_PASSWORD", ""))
    if not (usuario_correcto and password_correcta):
        _fallos_admin_por_ip[ip].append(time.time())
        logger.warning(f"Intento de acceso admin fallido desde {ip} — usuario: '{credentials.username}'")
        raise HTTPException(
            status_code=401,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic"},
        )
    _fallos_admin_por_ip.pop(ip, None)

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
    # Honeypot antispam: campo invisible en el formulario. Solo lo rellenan bots.
    web: str = Field(default="", max_length=500)

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: str) -> str:
        if not TELEFONO_ES_RE.match(v.strip()):
            raise ValueError("Teléfono no válido. Usa un móvil o fijo español (ej: 666 123 456).")
        return v

@app.post("/presupuesto")
async def presupuesto_endpoint(req: FormularioPresupuesto, request: Request, _rl=Depends(rate_limit_dep)):
    if req.web.strip():
        # Se responde igual que un envío válido para no darle pistas al bot, pero no se
        # guarda ni se envía al CRM/email: cada envío real crea una fila en la hoja de clientes.
        logger.warning(f"Formulario descartado por honeypot desde IP {_client_ip(request)}")
        return {"status": "success"}
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

_URL_BASE = "https://solsurestesolar.com"

# Páginas fijas del sitemap (todo menos los artículos del blog, que salen de la base
# de datos). Al añadir una página estática nueva hay que darla de alta aquí.
_SITEMAP_PAGINAS_FIJAS = (
    {"loc": "/", "lastmod": "2026-07-24", "changefreq": "monthly", "priority": "1.0"},
    {"loc": "/en", "lastmod": "2026-07-05", "changefreq": "monthly", "priority": "0.9"},
    {"loc": "/faq", "lastmod": "2026-07-04", "changefreq": "monthly", "priority": "0.7"},
    {"loc": "/aviso-legal", "lastmod": "2026-11-10", "changefreq": "yearly", "priority": "0.3"},
    {"loc": "/privacidad", "lastmod": "2026-11-10", "changefreq": "yearly", "priority": "0.3"},
    {"loc": "/cookies", "lastmod": "2026-11-10", "changefreq": "yearly", "priority": "0.3"},
    {"loc": "/placas-solares-murcia", "lastmod": "2026-07-14", "changefreq": "monthly", "priority": "0.6"},
    {"loc": "/placas-solares-alicante", "lastmod": "2026-07-14", "changefreq": "monthly", "priority": "0.6"},
    {"loc": "/placas-solares-lorca", "lastmod": "2026-07-14", "changefreq": "monthly", "priority": "0.6"},
    {"loc": "/placas-solares-cartagena", "lastmod": "2026-09-03", "changefreq": "monthly", "priority": "0.6"},
    {"loc": "/placas-solares-molina-de-segura", "lastmod": "2026-07-14", "changefreq": "monthly", "priority": "0.6"},
    {"loc": "/placas-solares-orihuela", "lastmod": "2026-07-05", "changefreq": "monthly", "priority": "0.6"},
    {"loc": "/placas-solares-torrevieja", "lastmod": "2026-07-14", "changefreq": "monthly", "priority": "0.6"},
    {"loc": "/placas-solares-orihuela-costa", "lastmod": "2026-07-14", "changefreq": "monthly", "priority": "0.6"},
    {"loc": "/placas-solares-pilar-de-la-horadada", "lastmod": "2026-07-14", "changefreq": "monthly", "priority": "0.6"},
    {"loc": "/blog", "lastmod": "2026-09-03", "changefreq": "weekly", "priority": "0.7"},
)

# --- 3b. PANEL DE CONTENIDO (CMS) ---
# Todo bajo /api/cms exige las mismas credenciales que el resto del panel y usa el contador
# de rate limit de admin, no el público (ver rate_limit_admin_dep).

class ContenidoEntrante(BaseModel):
    clave: str = Field(max_length=100)
    idioma: str = Field(max_length=2)
    valor: str | list = Field(union_mode="left_to_right")

@app.get("/api/cms/campos")
def api_cms_campos(idioma: str = "es", _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    """Todo lo que el panel necesita para pintarse: definición de cada campo y su valor."""
    if idioma not in cms_campos.IDIOMAS:
        raise HTTPException(status_code=400, detail="Idioma no soportado.")
    return {
        "status": "ok",
        "grupos": [{"id": g[0], "nombre": g[1], "descripcion": g[2]} for g in cms_campos.GRUPOS],
        "campos": cms.contenido_para_panel(idioma),
    }

@app.put("/api/cms/contenido")
def api_cms_guardar(dato: ContenidoEntrante, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    if dato.idioma not in cms_campos.IDIOMAS:
        raise HTTPException(status_code=400, detail="Idioma no soportado.")
    error = cms_campos.validar(dato.clave, dato.valor)
    if error:
        # 400 con el mensaje ya redactado para el usuario final: el panel lo muestra tal cual.
        raise HTTPException(status_code=400, detail=error)
    # El español se guarda SIEMPRE primero y por su cuenta. Lo que venga después (traducir
    # al inglés) no puede deshacerlo ni impedirlo: si OpenAI falla, el cambio ya está
    # publicado y lo único que queda pendiente es la versión inglesa.
    db_set_contenido(dato.clave, dato.idioma, dato.valor)
    logger.info(f"[CMS] Campo '{dato.clave}' ({dato.idioma}) actualizado desde el panel.")

    if dato.idioma != "es":
        # Editar el inglés a mano es la corrección de una traducción automática: deja de
        # estar pendiente de revisión.
        return {"status": "ok"}

    valor_en, motivo = cms_traduccion.traducir_campo(dato.clave, dato.valor)
    if valor_en is not None:
        db_set_contenido(dato.clave, "en", valor_en, revisar=True)
    return {"status": "ok", "traduccion": motivo, "valor_en": valor_en}

@app.post("/api/cms/contenido/{clave}/traducir")
def api_cms_traducir(clave: str, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    """Reintenta la traducción al inglés de un campo (botón del panel cuando falla)."""
    definicion = cms_campos.campo(clave)
    if not definicion:
        raise HTTPException(status_code=404, detail="Ese campo no existe.")

    valor_es = cms.contenido("es").get(clave)
    valor_en, motivo = cms_traduccion.traducir_campo(clave, valor_es)
    if valor_en is None:
        raise HTTPException(status_code=502, detail=motivo)
    db_set_contenido(clave, "en", valor_en, revisar=True)
    return {"status": "ok", "traduccion": motivo, "valor_en": valor_en}

@app.get("/api/cms/contenido/{clave}/historial")
def api_cms_historial(clave: str, idioma: str = "es", _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    if idioma not in cms_campos.IDIOMAS:
        raise HTTPException(status_code=400, detail="Idioma no soportado.")
    if not cms_campos.campo(clave):
        raise HTTPException(status_code=404, detail="Ese campo no existe.")
    return {
        "status": "ok",
        "original": cms_campos.defecto(clave, idioma),
        "versiones": db_get_historial_contenido(clave, idioma),
    }

@app.post("/api/cms/contenido/{clave}/restaurar")
def api_cms_restaurar(clave: str, idioma: str = "es", _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    """Vuelve al texto original del código borrando el valor guardado."""
    if idioma not in cms_campos.IDIOMAS:
        raise HTTPException(status_code=400, detail="Idioma no soportado.")
    if not cms_campos.campo(clave):
        raise HTTPException(status_code=404, detail="Ese campo no existe.")
    db_borrar_contenido(clave, idioma)
    logger.info(f"[CMS] Campo '{clave}' ({idioma}) restaurado al original.")
    return {"status": "ok", "valor": cms_campos.defecto(clave, idioma)}

# --- 3c. PREGUNTAS FRECUENTES ---

class FaqEntrante(BaseModel):
    pregunta: str = Field(max_length=cms_faq.MAX_PREGUNTA + 1)
    respuesta: str = Field(max_length=cms_faq.MAX_RESPUESTA + 1)

@app.get("/api/cms/faq")
def api_faq_listar(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    cms_faq.sembrar_si_vacia()
    return {"status": "ok", "preguntas": db_get_faq(solo_activas=False)}

@app.post("/api/cms/faq")
def api_faq_crear(dato: FaqEntrante, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    cms_faq.sembrar_si_vacia()
    error = cms_faq.validar(dato.pregunta, dato.respuesta)
    if error:
        raise HTTPException(status_code=400, detail=error)
    nuevo_id = db_crear_faq(dato.pregunta, dato.respuesta)
    return {"status": "ok", "id": nuevo_id}

@app.put("/api/cms/faq/{faq_id}")
def api_faq_actualizar(faq_id: int, dato: FaqEntrante, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    error = cms_faq.validar(dato.pregunta, dato.respuesta)
    if error:
        raise HTTPException(status_code=400, detail=error)
    db_actualizar_faq(faq_id, pregunta=dato.pregunta, respuesta=dato.respuesta)
    return {"status": "ok"}

@app.patch("/api/cms/faq/{faq_id}")
def api_faq_estado(faq_id: int, activa: bool | None = None, orden: int | None = None,
                   _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    """Activar/desactivar una pregunta o cambiarla de sitio en la lista."""
    db_actualizar_faq(faq_id, activa=activa, orden=orden)
    return {"status": "ok"}

@app.delete("/api/cms/faq/{faq_id}")
def api_faq_borrar(faq_id: int, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    if len(db_get_faq(solo_activas=False)) <= 1:
        raise HTTPException(status_code=400, detail="Tiene que quedar al menos una pregunta.")
    db_borrar_faq(faq_id)
    return {"status": "ok"}

# --- 3d. ARTÍCULOS DEL BLOG ---

class ArticuloEntrante(BaseModel):
    titulo: str = Field(max_length=cms_blog.MAX_TITULO + 1)
    slug: str = Field(default="", max_length=120)
    meta_description: str = Field(default="", max_length=cms_blog.MAX_META + 1)
    eyebrow: str = Field(default="", max_length=cms_blog.MAX_EYEBROW + 1)
    imagen_portada: str = Field(default="", max_length=300)
    alt_portada: str = Field(default="", max_length=300)
    pie_portada: str = Field(default="", max_length=300)
    cuerpo_html: str = Field(default="", max_length=cms_blog.MAX_CUERPO + 1000)
    publicado: bool = False
    publicado_en: str = Field(default="", max_length=10)

def _preparar_articulo(dato: ArticuloEntrante) -> dict:
    datos = dato.model_dump()
    datos["titulo"] = datos["titulo"].strip()
    datos["slug"] = (datos["slug"].strip() or cms_blog.slugificar(datos["titulo"]))
    # El cuerpo pasa SIEMPRE por el saneador antes de tocar la base de datos: es lo único
    # del CMS que luego se inserta en una página pública sin escapar.
    datos["cuerpo_html"] = cms_sanitize.sanear(datos["cuerpo_html"])
    if datos["publicado"] and not datos["publicado_en"]:
        datos["publicado_en"] = cms_blog.hoy()
    return datos

@app.get("/api/cms/articulos")
def api_articulos_listar(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    return {"status": "ok", "articulos": cms_blog.todos()}

@app.get("/api/cms/articulos/{articulo_id}")
def api_articulo_leer(articulo_id: int, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    articulo = cms_blog.por_id(articulo_id)
    if not articulo:
        raise HTTPException(status_code=404, detail="Ese artículo no existe.")
    return {"status": "ok", "articulo": articulo}

@app.post("/api/cms/articulos")
def api_articulo_crear(dato: ArticuloEntrante, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    datos = _preparar_articulo(dato)
    error = cms_blog.validar(datos)
    if error:
        raise HTTPException(status_code=400, detail=error)
    nuevo_id = db_crear_articulo(datos)
    logger.info(f"[CMS] Artículo creado: {datos['slug']}")
    return {"status": "ok", "id": nuevo_id, "slug": datos["slug"]}

@app.put("/api/cms/articulos/{articulo_id}")
def api_articulo_actualizar(articulo_id: int, dato: ArticuloEntrante,
                            _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    anterior = cms_blog.por_id(articulo_id)
    if not anterior:
        raise HTTPException(status_code=404, detail="Ese artículo no existe.")

    datos = _preparar_articulo(dato)
    error = cms_blog.validar(datos, articulo_id=articulo_id)
    if error:
        raise HTTPException(status_code=400, detail=error)

    db_actualizar_articulo(articulo_id, datos)

    # Si cambia la dirección de un artículo que ya estaba publicado, la antigua puede estar
    # indexada en Google: se deja redirigiendo con un 301 en vez de convertirla en un 404.
    if anterior["publicado"] and anterior["slug"] != datos["slug"]:
        db_registrar_redireccion_articulo(anterior["slug"], datos["slug"])
        logger.info(f"[CMS] Artículo renombrado: {anterior['slug']} -> {datos['slug']} (301 registrado)")

    return {"status": "ok", "slug": datos["slug"]}

@app.delete("/api/cms/articulos/{articulo_id}")
def api_articulo_borrar(articulo_id: int, _auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    articulo = cms_blog.por_id(articulo_id)
    if not articulo:
        raise HTTPException(status_code=404, detail="Ese artículo no existe.")
    db_borrar_articulo(articulo_id)
    logger.info(f"[CMS] Artículo eliminado: {articulo['slug']}")
    return {"status": "ok"}

# --- 3e. IMÁGENES ---

@app.get("/api/cms/imagenes")
def api_imagenes_listar(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    return {"status": "ok", "imagenes": cms_imagenes.listar()}

@app.post("/api/cms/imagenes")
async def api_imagenes_subir(archivo: UploadFile = File(...), _auth=Depends(verificar_admin),
                             _rl=Depends(rate_limit_admin_dep)):
    # Se lee de golpe porque el límite son 8 MB y hay que tener el fichero entero en memoria
    # de todas formas para comprobar su firma y reprocesarlo con Pillow.
    datos = await archivo.read()
    try:
        return {"status": "ok", **cms_imagenes.guardar(datos, archivo.filename or "imagen")}
    except cms_imagenes.ImagenInvalida as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[CMS] Error subiendo imagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se ha podido guardar la imagen.")

@app.delete("/api/cms/imagenes/{nombre_fichero}")
def api_imagenes_borrar(nombre_fichero: str, _auth=Depends(verificar_admin),
                        _rl=Depends(rate_limit_admin_dep)):
    if not cms_imagenes.borrar(nombre_fichero):
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido.")
    return {"status": "ok"}

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

@app.get("/cms.js")
def read_cms_js(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    # Mismo motivo que admin.js: fuera de static/ y detrás de verificar_admin.
    return FileResponse("admin_panel/cms.js", media_type="application/javascript")

# Quill, el editor de texto del blog, servido desde el propio dominio. No se puede usar su
# CDN: la CSP es `script-src 'self'` y un <script> de fuera se descarta sin dar ningún error
# (ya pasó con el CDN de Tailwind y con Clarity). Actualizar la versión = volver a descargar
# el fichero a admin_panel/vendor/, no cambiar una URL.
@app.get("/admin/vendor/quill.js")
def read_quill_js(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    return FileResponse("admin_panel/vendor/quill.js", media_type="application/javascript")

@app.get("/admin/vendor/quill.snow.css")
def read_quill_css(_auth=Depends(verificar_admin), _rl=Depends(rate_limit_admin_dep)):
    return FileResponse("admin_panel/vendor/quill.snow.css", media_type="text/css")

# --- PÁGINAS RENDERIZADAS (contenido editable desde el panel) ---
# Home ES/EN y FAQ se renderizan con Jinja2 en cada petición en vez de servirse como
# ficheros: sus textos viven en la base de datos y los edita el personal desde /admin.
# El resto del sitio (ciudades, legales, 404) sigue siendo estático vía el mount final.
def _contexto_publico(idioma: str = "es") -> dict:
    """Contexto común de las páginas públicas renderizadas."""
    resenas = obtener_resenas_cache("es")
    contenido_en = cms.contenido("en")
    return {
        # Textos ingleses del toggle ES/EN de script.js. Salen del mismo sitio que la web
        # inglesa, así que editar la home desde el panel ya no deja el toggle desfasado.
        "i18n_en": {
            "hero.h1": contenido_en["hero_h1"],
            "hero.h1.destacado": contenido_en["hero_h1_destacado"],
            "hero.p": contenido_en["hero_subtitulo"],
            "form.title": contenido_en["hero_form_titulo"],
        },
        # `c` son los textos editables desde el panel. Las claves que nadie ha tocado salen
        # con su valor original (ver cms_campos), así que la web nunca queda a medias.
        "c": cms.contenido(idioma),
        # El aggregateRating del JSON-LD sale del caché de reseñas de Google. Antes se
        # reescribía el HTML en disco (google_reviews.py); ahora es una variable más, así
        # que no hay escrituras sobre static/ ni riesgo de que un redeploy las pise.
        "resenas_rating": resenas.get("rating"),
        "resenas_num": resenas.get("user_rating_count"),
    }

@app.get("/")
def home_page(request: Request):
    return templates.TemplateResponse(request, "index.html", _contexto_publico())

@app.get("/en")
def home_en_page(request: Request):
    return templates.TemplateResponse(request, "en/index.html", _contexto_publico("en"))

@app.get("/faq")
def faq_page(request: Request):
    # `faq` alimenta a la vez el acordeón visible y el JSON-LD FAQPage de la plantilla, que
    # es justo lo que impide que vuelvan a desincronizarse.
    contexto = _contexto_publico()
    contexto["faq"] = cms_faq.preguntas()
    return templates.TemplateResponse(request, "faq.html", contexto)

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
def blog_index_page(request: Request):
    # Ordenado por fecha real de publicación. Antes las tarjetas estaban escritas a mano en
    # el HTML y el orden dependía de acordarse de pegar la nueva arriba del todo.
    contexto = _contexto_publico()
    contexto["articulos"] = cms_blog.publicados()
    return templates.TemplateResponse(request, "blog_index.html", contexto)

@app.get("/blog/index.html")
def redirect_blog_index_html():
    return RedirectResponse(url="/blog", status_code=301)

@app.get("/blog/articulos/{slug}.html")
def blog_articulo_page(request: Request, slug: str):
    """Las URLs conservan el `.html` de cuando eran ficheros: están indexadas en Google."""
    articulo = cms_blog.por_slug(slug)
    if not articulo:
        # Si el artículo se renombró, se manda a su dirección nueva en vez de dar un 404 y
        # perder el posicionamiento que tuviera la antigua.
        destino = db_get_redireccion_articulo(slug)
        if destino:
            return RedirectResponse(url=f"/blog/articulos/{destino}.html", status_code=301)
        raise HTTPException(status_code=404)

    contexto = _contexto_publico()
    contexto.update({
        "a": articulo,
        "url_articulo": f"{_URL_BASE}{articulo['url']}",
        "url_portada": (f"{_URL_BASE}{articulo['imagen_portada']}"
                        if articulo["imagen_portada"] else f"{_URL_BASE}/images/og-cover.jpg"),
    })
    return templates.TemplateResponse(request, "blog_articulo.html", contexto)

@app.get("/blog/articulos/{slug}")
def redirect_articulo_sin_extension(slug: str):
    """La dirección canónica lleva `.html`; sin ella se redirige para no duplicar contenido."""
    return RedirectResponse(url=f"/blog/articulos/{slug}.html", status_code=301)

@app.get("/admin/preview/blog/{articulo_id}")
def blog_preview(request: Request, articulo_id: int, _auth=Depends(verificar_admin),
                 _rl=Depends(rate_limit_admin_dep)):
    """Vista previa de un borrador. Solo con credenciales: los borradores dan 404 en público."""
    articulo = cms_blog.por_id(articulo_id)
    if not articulo:
        raise HTTPException(status_code=404)
    contexto = _contexto_publico()
    contexto.update({
        "a": articulo,
        "url_articulo": f"{_URL_BASE}{articulo['url']}",
        "url_portada": (f"{_URL_BASE}{articulo['imagen_portada']}"
                        if articulo["imagen_portada"] else f"{_URL_BASE}/images/og-cover.jpg"),
    })
    return templates.TemplateResponse(request, "blog_articulo.html", contexto)

@app.get("/sitemap.xml")
def sitemap(request: Request):
    """Sitemap generado, no escrito a mano.

    Antes había que acordarse de añadir cada artículo nuevo y de tocar el `lastmod` a mano
    cada vez que se editaba una página; en la práctica las fechas se quedaban viejas. Ahora
    los artículos y sus fechas salen de la base de datos."""
    contexto = {"urls": list(_SITEMAP_PAGINAS_FIJAS), "base": _URL_BASE}
    for articulo in cms_blog.publicados():
        contexto["urls"].append({
            "loc": articulo["url"],
            "lastmod": articulo["actualizado_en"] or articulo["publicado_en"],
            "changefreq": "monthly",
            "priority": "0.6",
        })
    return templates.TemplateResponse(request, "sitemap.xml", contexto,
                                      media_type="application/xml")

@app.get("/llms.txt")
def llms_txt(request: Request):
    """Resumen para buscadores de IA. Era un fichero estático y se quedó con 3 artículos
    cuando ya había 5; ahora la lista del blog sale de la base de datos, como el sitemap."""
    contexto = {"articulos": cms_blog.publicados(), "base": _URL_BASE}
    return templates.TemplateResponse(request, "llms.txt", contexto,
                                      media_type="text/plain; charset=utf-8")

@app.on_event("startup")
def _iniciar_scheduler_purga():
    """Purga diaria de conversaciones más antiguas que RETENCION_DIAS (RGPD) y refresco
    diario del caché de reseñas de Google. Un solo worker (ver CLAUDE.md) => sin riesgo
    de ejecuciones duplicadas."""
    # Contenido original del blog y de la FAQ. Ambas siembras son idempotentes y solo actúan
    # con la tabla vacía, es decir, la primera vez que arranca contra una base de datos
    # nueva. Va en el arranque a propósito: si dependiera de un comando manual tras el
    # deploy, entre el despliegue y ese comando las URLs de los artículos —indexadas en
    # Google— estarían devolviendo 404.
    try:
        cms_blog.sembrar_si_vacia()
        cms_faq.sembrar_si_vacia()
    except Exception as e:
        logger.error(f"[CMS] Fallo sembrando el contenido inicial: {e}", exc_info=True)

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

# Imágenes subidas desde el panel. Van en DATA_DIR (disco persistente en Render), no en
# static/, que se regenera desde git en cada deploy y se llevaría las fotos por delante.
# El directorio se crea aquí porque StaticFiles falla al arrancar si no existe.
os.makedirs(cms_imagenes.UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=cms_imagenes.UPLOADS_DIR), name="uploads")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    logger.info("🚀 Servidor Web listo en http://localhost:8000")
    logger.info("👉 Abre http://localhost:8000 en tu navegador para probar el chat.")
    logger.info("👉 Abre http://localhost:8000/admin para ver tu panel de control.")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
