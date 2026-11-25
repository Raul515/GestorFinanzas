"""Gestión de tokens maestros y emparejamiento por PIN de un solo uso para móvil."""

from datetime import datetime, timedelta, timezone
import hmac
import json
import logging
from pathlib import Path
import secrets
from typing import Any, Dict, Optional, Tuple

from backend.utils.files import atomic_write_json

logger = logging.getLogger(__name__)


def get_or_create_pairing_token(pairing_file: Path) -> str:
    """Obtiene o genera de forma persistente el token secreto de emparejamiento."""
    if pairing_file.exists():
        try:
            with open(pairing_file, "r", encoding="utf-8") as f:
                token = f.read().strip()
            if token:
                return token
        except Exception as exc:
            logger.warning("Error leyendo pairing_secret.txt: %s", exc)

    new_token = f"sec_{secrets.token_hex(16)}"
    try:
        pairing_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pairing_file, "w", encoding="utf-8") as f:
            f.write(new_token)
        logger.info("Nuevo token de emparejamiento móvil generado y guardado")
    except Exception as exc:
        logger.error("No se pudo persistir el pairing token: %s", exc)
    return new_token


def validate_pairing_token(pairing_file: Path, token: Optional[str]) -> bool:
    """Valida que el token proporcionado por el cliente coincida con el token maestro."""
    if not token:
        return False
    master_token = get_or_create_pairing_token(pairing_file)
    return hmac.compare_digest(token.strip(), master_token)


def generate_pairing_pin(pin_file: Path, ttl_seconds: int = 600) -> Dict[str, Any]:
    """Genera un PIN de 6 dígitos aleatorio criptográfico y lo persiste con fecha de expiración."""
    pin = f"{secrets.randbelow(1000000):06d}"
    now_dt = datetime.now(timezone.utc)
    expires_at_dt = now_dt + timedelta(seconds=ttl_seconds)

    pin_data = {
        "pin": pin,
        "expires_at_timestamp": expires_at_dt.timestamp(),
        "expires_at_utc": expires_at_dt.isoformat(),
        "failed_attempts": 0,
    }
    try:
        atomic_write_json(pin_file, pin_data)
        logger.info("Nuevo PIN de emparejamiento móvil generado: [***%s]", pin[-2:])
    except Exception as exc:
        logger.error("Error guardando active_pin.json: %s", exc)
        raise
    return {
        "pin": pin,
        "expires_in_seconds": ttl_seconds,
        "expires_at_utc": expires_at_dt.isoformat(),
    }


def pair_with_pin(
    pin_file: Path,
    pairing_file: Path,
    candidate_pin: str,
) -> Tuple[bool, Optional[str], str]:
    """Valida un PIN suministrado por el cliente móvil con protección anti-fuerza bruta."""
    if not pin_file.exists():
        return False, None, "No hay ningún PIN de vinculación activo. Genéralo en tu ordenador."

    try:
        with open(pin_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.error("Error leyendo active_pin.json: %s", exc)
        return False, None, "Error de lectura del PIN activo."

    now_ts = datetime.now(timezone.utc).timestamp()
    if now_ts > data.get("expires_at_timestamp", 0):
        try:
            pin_file.unlink(missing_ok=True)
        except OSError:
            pass
        return False, None, "El código PIN ha caducado. Genera uno nuevo en tu ordenador."

    failed = data.get("failed_attempts", 0)
    if failed >= 5:
        try:
            pin_file.unlink(missing_ok=True)
        except OSError:
            pass
        return False, None, "Demasiados intentos erróneos. El PIN ha sido invalidado por seguridad."

    stored_pin = str(data.get("pin", "")).strip()
    if hmac.compare_digest(candidate_pin.strip(), stored_pin):
        try:
            pin_file.unlink(missing_ok=True)
        except OSError:
            pass
        master_token = get_or_create_pairing_token(pairing_file)
        logger.info("Emparejamiento por PIN exitoso")
        return True, master_token, "✓ Dispositivo emparejado con éxito."

    failed += 1
    data["failed_attempts"] = failed
    remaining = max(0, 5 - failed)
    try:
        atomic_write_json(pin_file, data)
    except OSError:
        pass

    if remaining == 0:
        try:
            pin_file.unlink(missing_ok=True)
        except OSError:
            pass
        return False, None, "PIN incorrecto. Has superado el límite de 5 intentos. Genera uno nuevo en tu ordenador."

    return False, None, f"PIN incorrecto. Te quedan {remaining} intentos."
