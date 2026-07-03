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
# 🔌 HUECO PENDIENTE: CRM_WEBHOOK_URL se lee de .env. Hoy apunta a un webhook.site
# de pruebas (los leads ya quedan guardados en agencia.db de todas formas). Cuando
# tengáis el CRM real (Make, Zapier, HubSpot...), cambia solo el valor en .env.
WEBHOOK_URL = os.getenv("CRM_WEBHOOK_URL")

async def enviar_lead_crm(nombre: str, telefono: str, ubicacion: str, necesidad: str) -> str:
    """
    Envía los datos de un cliente cualificado al webhook para procesarlo en Make/Zapier.
    """
    if not WEBHOOK_URL:
        logger.warning("[CRM] CRM_WEBHOOK_URL no está configurada en .env — el lead se queda solo en agencia.db.")
        return json.dumps({"status": "skipped", "mensaje": "CRM externo no configurado todavía."})

    try:
        logger.info(f"[CRM] Disparando Webhook para guardar a: {nombre}...")

        datos_cliente = {
            "nombre": nombre,
            "telefono": telefono,
            "ubicacion": ubicacion,
            "necesidad": necesidad,
            "origen": "Asistente IA"
        }

        async with httpx.AsyncClient(timeout=10.0) as http:
            respuesta = await http.post(WEBHOOK_URL, json=datos_cliente)

        if respuesta.status_code in [200, 201]:
            logger.info("[CRM] ¡Datos enviados con éxito al Webhook!")
            return json.dumps({
                "status": "success",
                "mensaje": "Los datos han sido guardados en el sistema corporativo."
            })
        else:
            logger.warning(f"[CRM] Error del servidor destino: {respuesta.status_code}")
            return json.dumps({
                "status": "error",
                "mensaje": "No se pudo guardar el contacto en el CRM."
            })

    except Exception as e:
        logger.error(f"[CRM ERROR]: {str(e)}", exc_info=True)
        return json.dumps({"status": "error", "mensaje": "Fallo técnico de conexión."})

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