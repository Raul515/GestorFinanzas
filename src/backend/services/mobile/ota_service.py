"""Gestión de versiones OTA y binarios APK para la micro-app móvil."""

import json
import logging
from pathlib import Path
from typing import Optional

from backend.domain.schemas.mobile import MobileVersionResponse
from backend.utils.dates import format_utc_iso
from backend.utils.files import atomic_write_json

logger = logging.getLogger(__name__)


def get_latest_apk_path(apk_dir: Path, preferred_filename: Optional[str] = None) -> Optional[Path]:
    """Obtiene la ruta al archivo APK disponible para distribución."""
    if preferred_filename:
        candidate = apk_dir / preferred_filename
        if candidate.exists():
            return candidate

    apks = sorted(apk_dir.glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True)
    return apks[0] if apks else None


def get_mobile_version_info(apk_dir: Path) -> MobileVersionResponse:
    """Retorna la versión más reciente publicada de la APK móvil para actualizaciones OTA."""
    version_file = apk_dir / "version.json"
    code = 1
    name = "1.0.0"
    notes = "Versión inicial estable Quick-Capture"
    released_utc = None
    apk_filename = None

    if version_file.exists():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                code = int(data.get("version_code", 1))
                name = str(data.get("version_name", "1.0.0"))
                notes = data.get("release_notes", notes)
                released_utc = data.get("released_at_utc")
                apk_filename = data.get("apk_filename")
        except Exception as exc:
            logger.warning("Error leyendo version.json: %s", exc)

    apk_path = get_latest_apk_path(apk_dir, apk_filename)
    apk_available = apk_path is not None and apk_path.exists()
    apk_size = apk_path.stat().st_size if apk_available and apk_path else None
    final_filename = apk_path.name if apk_available and apk_path else None

    return MobileVersionResponse(
        version_code=code,
        version_name=name,
        apk_available=apk_available,
        apk_url="/api/mobile/download-apk" if apk_available else None,
        apk_filename=final_filename,
        apk_size_bytes=apk_size,
        release_notes=notes,
        released_at_utc=released_utc,
    )


def publish_apk_release(
    apk_dir: Path,
    apk_bytes: bytes,
    filename: str = "app-release.apk",
    version_code: int = 2,
    version_name: str = "1.1.0",
    release_notes: str = "",
) -> MobileVersionResponse:
    """Guarda un nuevo binario APK en disco y actualiza su metadata para actualizaciones OTA."""
    apk_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = Path(filename).name
    target_apk = apk_dir / safe_filename
    with open(target_apk, "wb") as f:
        f.write(apk_bytes)

    metadata = {
        "version_code": version_code,
        "version_name": version_name,
        "release_notes": release_notes or f"Actualización versión {version_name}",
        "apk_filename": safe_filename,
        "released_at_utc": format_utc_iso(),
    }
    atomic_write_json(apk_dir / "version.json", metadata)

    logger.info("Nueva versión de APK móvil publicada: %s (v%s, código %d)", safe_filename, version_name, version_code)
    return get_mobile_version_info(apk_dir)
