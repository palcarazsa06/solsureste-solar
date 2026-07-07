"""Validadores de datos de contacto compartidos entre api.py (formulario /presupuesto) y
main.py (datos de contacto extraídos por el LLM del chat antes de enviarlos al CRM)."""
import re

from pydantic import EmailStr, TypeAdapter

TELEFONO_ES_RE = re.compile(r"^(?:\+34|0034)?[\s.-]?[6789]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}$")

_EMAIL_ADAPTER = TypeAdapter(EmailStr)


def telefono_valido(valor: str) -> bool:
    return bool(TELEFONO_ES_RE.match((valor or "").strip()))


def email_valido(valor: str) -> bool:
    try:
        _EMAIL_ADAPTER.validate_python((valor or "").strip())
        return True
    except Exception:
        return False
