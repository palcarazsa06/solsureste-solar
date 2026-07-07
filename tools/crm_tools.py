import os
import json
import httpx
import asyncio
from dotenv import load_dotenv

from logging_config import get_logger
logger = get_logger(__name__)

load_dotenv()

# =====================================================================
# CONFIGURACIÓN DEL WEBHOOK
# =====================================================================
# CRM_WEBHOOK_URL se lee de .env. Apunta al escenario REAL de Make.com que escribe en la
# Google Sheet de clientes de verdad (ver CLAUDE.md) — no es un endpoint de pruebas. Cualquier
# script o test que invoque enviar_lead_crm() sin mockear esta URL crea un lead real ahí.
WEBHOOK_URL = os.getenv("CRM_WEBHOOK_URL")

# Reintentos ante fallos transitorios (timeout, 5xx puntual). El lead nunca se pierde
# de todas formas (siempre se guarda antes en agencia.db) — esto solo reduce los casos
# en los que un fallo de red pasajero obliga a esperar al siguiente turno de la
# conversación para que se reintente el envío al CRM.
MAX_INTENTOS = 2
ESPERA_ENTRE_INTENTOS_S = 1

async def enviar_lead_crm(nombre: str, telefono: str, ubicacion: str, necesidad: str) -> str:
    """
    Envía los datos de un cliente cualificado al webhook para procesarlo en Make/Zapier.
    """
    if not WEBHOOK_URL:
        logger.warning("[CRM] CRM_WEBHOOK_URL no está configurada en .env — el lead se queda solo en agencia.db.")
        return json.dumps({"status": "skipped", "mensaje": "CRM externo no configurado todavía."})

    datos_cliente = {
        "nombre": nombre,
        "telefono": telefono,
        "ubicacion": ubicacion,
        "necesidad": necesidad,
        "origen": "Asistente IA"
    }

    for intento in range(1, MAX_INTENTOS + 1):
        try:
            logger.info(f"[CRM] Disparando Webhook para guardar a: {nombre} (intento {intento}/{MAX_INTENTOS})...")

            async with httpx.AsyncClient(timeout=10.0) as http:
                respuesta = await http.post(WEBHOOK_URL, json=datos_cliente)

            if respuesta.status_code in [200, 201]:
                logger.info("[CRM] ¡Datos enviados con éxito al Webhook!")
                return json.dumps({
                    "status": "success",
                    "mensaje": "Los datos han sido guardados en el sistema corporativo."
                })

            logger.warning(f"[CRM] Error del servidor destino (intento {intento}/{MAX_INTENTOS}): {respuesta.status_code}")

        except Exception as e:
            logger.warning(f"[CRM] Fallo de conexión (intento {intento}/{MAX_INTENTOS}): {e}")

        if intento < MAX_INTENTOS:
            await asyncio.sleep(ESPERA_ENTRE_INTENTOS_S)

    logger.error(f"[CRM ERROR] Todos los intentos fallaron para: {nombre}")
    return json.dumps({"status": "error", "mensaje": "No se pudo guardar el contacto en el CRM."})

# =====================================================================
# ESQUEMA DE LA HERRAMIENTA
# =====================================================================
tool_enviar_lead = {
    "type": "function",
    "function": {
        "name": "enviar_lead_crm",
        "description": "Envía los datos de un cliente al CRM. Úsala ÚNICAMENTE cuando estés en la fase de cualificación y el cliente ya te haya proporcionado su nombre, teléfono y hayas entendido su necesidad de instalación.",
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "El nombre del cliente."
                },
                "telefono": {
                    "type": "string",
                    "description": "El teléfono de contacto del cliente."
                },
                "ubicacion": {
                    "type": "string",
                    "description": "La ciudad, municipio o código postal de la instalación."
                },
                "necesidad": {
                    "type": "string",
                    "description": "Un resumen muy breve de lo que necesita (ej: Instalación de 8 placas solares, Urgencia alta)."
                }
            },
            "required": ["nombre", "telefono", "ubicacion", "necesidad"]
        }
    }
}