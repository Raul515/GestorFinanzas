"""Utilidades transversales de fechas y períodos mensuales en UTC/ISO (Spec 017 - Fase 3)."""

import calendar
from datetime import date, datetime, timezone
from typing import Optional, Tuple


def month_date_range(month_str: str) -> Tuple[date, date]:
    """Devuelve (primer_dia, ultimo_dia) para un mes en formato YYYY-MM."""
    year, month = map(int, month_str.split("-"))
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, 1), date(year, month, last_day)


def get_next_month_key(month_str: str) -> str:
    """Devuelve la clave YYYY-MM del mes inmediatamente posterior."""
    year, month = map(int, month_str.split("-"))
    if month == 12:
        return f"{year + 1}-01"
    return f"{year}-{month + 1:02d}"


def parse_utc_iso(value: str) -> datetime:
    """Parsea un timestamp ISO-8601 (con o sin sufijo 'Z') normalizado a UTC."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_utc_iso(dt: Optional[datetime] = None) -> str:
    """Formatea un datetime en ISO-8601 UTC con sufijo 'Z'."""
    target = dt or datetime.now(timezone.utc)
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    else:
        target = target.astimezone(timezone.utc)
    return target.isoformat().replace("+00:00", "Z")
