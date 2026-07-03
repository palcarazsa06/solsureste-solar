import os
import json
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

from logging_config import get_logger
logger = get_logger(__name__)

load_dotenv()

# =====================================================================
# CONFIGURACIÓN CRÍTICA
# =====================================================================
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "palcarazsa06@gmail.com")
CREDENTIALS_FILE = "credenciales_google.json"
SCOPES = ['https://www.googleapis.com/auth/calendar']

def obtener_servicio_calendar():
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(f"❌ No se encontró el archivo {CREDENTIALS_FILE} en la raíz del proyecto.")
        
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=creds)

def _reservar_cita_sync(fecha: str, hora: str, nombre: str, telefono: str, ciudad: str) -> str:
    """Lógica síncrona de reserva (googleapiclient no tiene API async)."""
    try:
        logger.info(f"[GOOGLE CALENDAR] Agendando a {nombre} ({ciudad}) el {fecha} a las {hora}...")
        service = obtener_servicio_calendar()

        inicio_str = f"{fecha}T{hora}:00"
        formato = "%Y-%m-%dT%H:%M:%S"

        datetime_inicio = datetime.strptime(inicio_str, formato)
        datetime_fin = datetime_inicio + timedelta(hours=1)

        start_iso = datetime_inicio.isoformat()
        end_iso = datetime_fin.isoformat()

        evento = {
            'summary': f'📞 Cita: {nombre} ({ciudad}) - {telefono}',
            'description': f'👤 Nombre: {nombre}\n📞 Teléfono: {telefono}\n📍 Ciudad: {ciudad}\n\n🤖 Cita agendada de forma automática por el Asistente de IA. Revisa el panel para más detalles.',
            'start': {'dateTime': start_iso, 'timeZone': 'Europe/Madrid'},
            'end': {'dateTime': end_iso, 'timeZone': 'Europe/Madrid'},
            'reminders': {'useDefault': True},
        }

        evento_creado = service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        link_evento = evento_creado.get('htmlLink')
        logger.info(f"[GOOGLE CALENDAR] ¡Cita creada! Link: {link_evento}")

        return json.dumps({
            "status": "success",
            "mensaje": f"Cita agendada correctamente para el día {fecha} a las {hora}.",
            "htmlLink": link_evento,
        })

    except Exception as e:
        logger.error(f"[GOOGLE CALENDAR ERROR]: {str(e)}", exc_info=True)
        return json.dumps({"status": "error", "mensaje": "No se pudo agendar la cita debido a un error técnico."})


async def reservar_cita(fecha: str, hora: str, nombre: str, telefono: str, ciudad: str) -> str:
    """Wrapper async: ejecuta la llamada síncrona a Google Calendar en un thread pool."""
    return await asyncio.to_thread(_reservar_cita_sync, fecha, hora, nombre, telefono, ciudad)

# =====================================================================
# ESQUEMA DE LA HERRAMIENTA
# =====================================================================
tool_reservar_cita = {
    "type": "function",
    "function": {
        "name": "reservar_cita",
        "description": "Agenda una reunión real en el calendario de la empresa cuando el usuario confirma una fecha y hora específicas. Debes extraer los datos del cliente del historial para crear el evento.",
        "parameters": {
            "type": "object", 
            "properties": {
                "fecha": {
                    "type": "string", 
                    "description": "La fecha elegida en formato estricto YYYY-MM-DD (ej: 2026-06-25)."
                },
                "hora": {
                    "type": "string", 
                    "description": "La hora elegida en formato estricto HH:MM (ej: 10:00)."
                },
                "nombre": {
                    "type": "string",
                    "description": "Nombre del cliente extraído del historial de la conversación."
                },
                "telefono": {
                    "type": "string",
                    "description": "Teléfono del cliente extraído del historial."
                },
                "ciudad": {
                    "type": "string",
                    "description": "Ciudad o ubicación del cliente extraída del historial."
                }
            },
            "required": ["fecha", "hora", "nombre", "telefono", "ciudad"]
        }
    }
}