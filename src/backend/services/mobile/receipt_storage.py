"""Almacenamiento seguro y validación de comprobantes (tickets) de gastos móviles."""

import base64
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_RECEIPT_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_RECEIPT_MIMES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
}


def _has_valid_image_magic_bytes(raw_bytes: bytes) -> bool:
    """Comprueba la cabecera binaria mágica de formatos de imagen soportados."""
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return True  # JPEG
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return True  # PNG
    if raw_bytes.startswith((b"GIF87a", b"GIF89a")):
        return True  # GIF
    if len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return True  # WEBP
    if len(raw_bytes) >= 12 and raw_bytes[4:8] == b"ftyp":
        return True  # HEIC / HEIF / AVIF
    return False


def _sanitize_event_id(event_id: str) -> str:
    return "".join(c for c in event_id if c.isalnum() or c in ("-", "_"))


def save_receipt_base64(receipts_dir: Path, event_id: str, base64_str: str) -> Optional[str]:
    """Decodifica, valida tamaño/MIME y guarda una imagen de ticket en sync/mobile/receipts/."""
    if not base64_str or not event_id:
        return None
    try:
        data_str = base64_str.strip()
        if "," in data_str:
            header, data_str = data_str.split(",", 1)
            header_lower = header.lower()
            if header_lower.startswith("data:"):
                mime = header_lower[5:].split(";", 1)[0].strip()
                if mime not in ALLOWED_RECEIPT_MIMES:
                    logger.warning("Tipo MIME de ticket rechazado (%s) para %s", mime, event_id)
                    return None

        if len(data_str) > int(MAX_RECEIPT_BYTES * 1.4):
            logger.warning("Comprobante base64 excede el límite de 5 MB para %s", event_id)
            return None

        raw_bytes = base64.b64decode(data_str, validate=True)
        if not raw_bytes or len(raw_bytes) > MAX_RECEIPT_BYTES:
            logger.warning("Tamaño decodificado inválido (%d bytes) para %s", len(raw_bytes), event_id)
            return None

        if not _has_valid_image_magic_bytes(raw_bytes):
            logger.warning("Firma binaria de imagen no válida en ticket para %s", event_id)
            return None

        safe_id = _sanitize_event_id(event_id)
        filename = f"receipt_{safe_id}.jpg"
        receipts_dir.mkdir(parents=True, exist_ok=True)
        target_path = receipts_dir / filename
        target_path.write_bytes(raw_bytes)
        logger.info("Comprobante de ticket guardado en disco: %s (%d bytes)", filename, len(raw_bytes))
        return filename
    except Exception as exc:
        logger.error("Error guardando comprobante base64 para %s: %s", event_id, exc)
        return None


def save_receipt_file(receipts_dir: Path, event_id: str, file_bytes: bytes) -> Optional[str]:
    """Guarda un archivo de imagen recibido vía multipart en sync/mobile/receipts/."""
    if not file_bytes or not event_id:
        return None
    if len(file_bytes) > MAX_RECEIPT_BYTES:
        logger.warning("Archivo de ticket excede 5 MB para %s", event_id)
        return None
    try:
        safe_id = _sanitize_event_id(event_id)
        filename = f"receipt_{safe_id}.jpg"
        receipts_dir.mkdir(parents=True, exist_ok=True)
        target_path = receipts_dir / filename
        target_path.write_bytes(file_bytes)
        logger.info("Comprobante de ticket subido guardado en disco: %s (%d bytes)", filename, len(file_bytes))
        return filename
    except Exception as exc:
        logger.error("Error guardando archivo de ticket para %s: %s", event_id, exc)
        return None


def get_receipt_path(receipts_dir: Path, filename: str) -> Optional[Path]:
    """Retorna la ruta física del comprobante si existe y está dentro de receipts_dir."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return None
    target = receipts_dir / filename
    if target.exists() and target.is_file():
        return target
    return None


def delete_receipt_file(receipts_dir: Path, filename: Optional[str]) -> bool:
    """Elimina físicamente el archivo de comprobante de la carpeta receipts si existe."""
    if not filename:
        return False
    path = get_receipt_path(receipts_dir, filename)
    if path and path.is_file():
        try:
            path.unlink(missing_ok=True)
            logger.info("Comprobante físico eliminado del disco: %s", filename)
            return True
        except Exception as exc:
            logger.warning("No se pudo eliminar el comprobante físico %s: %s", filename, exc)
    return False
