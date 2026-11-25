"""Utilidades compartidas de almacenamiento en disco para buzones de sincronización (Spec 017 - Fase 3)."""

import logging
import os
from pathlib import Path
import platform
import shutil
from typing import Optional
import uuid

logger = logging.getLogger(__name__)


def resolve_sync_dir(base_sync_dir: Optional[str] = None) -> Path:
    """Resuelve el directorio raíz de sincronización (parámetro -> BASE_SYNC_DIR -> ./sync)."""
    if base_sync_dir:
        return Path(base_sync_dir)
    env_sync_dir = os.environ.get("BASE_SYNC_DIR")
    if env_sync_dir and env_sync_dir.strip():
        return Path(env_sync_dir.strip())
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    return root_dir / "sync"


def get_or_create_device_id(data_dir: Optional[Path] = None) -> str:
    """Obtiene o genera de forma persistente un identificador único de dispositivo."""
    env_id = os.environ.get("DEVICE_ID")
    if env_id and env_id.strip():
        return env_id.strip()

    if data_dir is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"

    data_dir.mkdir(parents=True, exist_ok=True)
    device_id_file = data_dir / "device_id.txt"
    if device_id_file.exists():
        try:
            stored_id = device_id_file.read_text(encoding="utf-8").strip()
            if stored_id:
                return stored_id
        except Exception as exc:
            logger.warning("No se pudo leer device_id.txt: %s", exc)

    node_name = platform.node() or "device"
    clean_node = "".join(c for c in node_name if c.isalnum() or c in ("-", "_"))[:12] or "device"
    new_id = f"{clean_node}_{uuid.uuid4().hex[:8]}"
    try:
        device_id_file.write_text(new_id, encoding="utf-8")
    except Exception as exc:
        logger.warning("No se pudo persistir device_id.txt en disco: %s", exc)
    return new_id


def is_sync_event_file(file_path: Path, require_json: bool = True) -> bool:
    """Determina si un archivo es un artefacto de sincronización válido."""
    if not file_path.is_file():
        return False
    name = file_path.name
    if name.startswith(".") or name == ".gitkeep" or name.endswith(".tmp"):
        return False
    if require_json and file_path.suffix.lower() != ".json":
        return False
    return True


def archive_processed_file(file_path: Path, processed_dir: Path) -> Optional[Path]:
    """Mueve un archivo procesado al directorio processed/ de forma segura."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    dest = processed_dir / file_path.name
    try:
        shutil.move(str(file_path), str(dest))
        return dest
    except OSError as exc:
        logger.warning("No se pudo archivar %s en %s: %s", file_path, processed_dir, exc)
        return None


def quarantine_error_file(file_path: Path, error_dir: Path) -> Optional[Path]:
    """Mueve un archivo corrupto o fallido al directorio error/ para inspección."""
    error_dir.mkdir(parents=True, exist_ok=True)
    dest = error_dir / file_path.name
    try:
        shutil.move(str(file_path), str(dest))
        return dest
    except OSError as exc:
        logger.warning("No se pudo mover %s a cuarentena %s: %s", file_path, error_dir, exc)
        return None
