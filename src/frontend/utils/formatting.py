"""Formateadores unificados de fechas, horas e importes en estándar español (DD/MM/YYYY)."""

from datetime import date, datetime
from typing import Any


def format_date_es(value: Any, fallback: str = "-") -> str:
    """Convierte una fecha/timestamp (date, datetime o string ISO) al formato DD/MM/YYYY."""
    if value is None or value == "":
        return fallback
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    raw = str(value).strip()
    if not raw or raw.lower() in ("none", "null", "n/a", "-"):
        return fallback

    date_part = raw.split("T", 1)[0].split(" ", 1)[0]
    parts = date_part.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2][:2]}/{parts[1]}/{parts[0]}"

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return raw


def format_datetime_es(value: Any, include_seconds: bool = False, fallback: str = "-") -> str:
    """Convierte un timestamp ISO o datetime al formato DD/MM/YYYY HH:MM(:SS)."""
    if value is None or value == "":
        return fallback

    fmt = "%d/%m/%Y %H:%M:%S" if include_seconds else "%d/%m/%Y %H:%M"
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    raw = str(value).strip()
    if not raw or raw.lower() in ("none", "null", "n/a", "-"):
        return fallback

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime(fmt)
    except ValueError:
        return raw[:19].replace("T", " ")


def format_eur(amount: Any, decimals: int = 2) -> str:
    """Formatea una magnitud monetaria en euros con separador estándar."""
    try:
        val = float(amount or 0.0)
    except (TypeError, ValueError):
        val = 0.0
    return f"{val:,.{decimals}f} €"
