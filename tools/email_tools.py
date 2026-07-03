import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
from dotenv import load_dotenv

from logging_config import get_logger

logger = get_logger(__name__)
load_dotenv()

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _enviar_email_sync(nombre: str, telefono: str, correo: str, ciudad: str, fuente: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Nuevo lead Solsureste — {nombre} ({fuente})"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_DESTINATARIO

    cuerpo = (
        f"Nuevo lead recibido vía {fuente}:\n\n"
        f"  Nombre:    {nombre}\n"
        f"  Teléfono:  {telefono}\n"
        f"  Email:     {correo}\n"
        f"  Ciudad:    {ciudad}\n"
        f"  Fuente:    {fuente}\n\n"
        f"Ver panel: http://localhost:8000/admin\n"
    )
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.sendmail(EMAIL_SENDER, EMAIL_DESTINATARIO, msg.as_string())


async def enviar_alerta_lead_email(
    nombre: str,
    telefono: str,
    correo: str,
    ciudad: str,
    fuente: str,
) -> None:
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_DESTINATARIO]):
        logger.warning("[EMAIL] Variables de entorno no configuradas — alerta omitida.")
        return
    try:
        await asyncio.to_thread(_enviar_email_sync, nombre, telefono, correo, ciudad, fuente)
        logger.info(f"[EMAIL] Alerta enviada para lead: {nombre} ({fuente})")
    except Exception as e:
        logger.error(f"[EMAIL] Error enviando alerta: {e}", exc_info=True)
