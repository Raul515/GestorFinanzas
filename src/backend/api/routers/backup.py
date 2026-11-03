"""
Router REST para la Gestión y Copias de Seguridad de Base de Datos (Backup & Restore).
Implementa endpoints fuertemente tipados para diagnóstico de salud, copias atómicas en caliente,
descargas binarias en streaming, restauración segura con snapshot previo y rollback en 1 clic.
"""

import logging
from pathlib import Path
import shutil
import tempfile
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.domain.schemas.backup import (
    BackupListResponse,
    BackupMetadata,
    BackupScheduleResponse,
    BackupScheduleUpdate,
    BackupValidationResult,
    DatabaseHealthResponse,
    RestoreResponse,
)
from backend.services import backup_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get("/health", response_model=DatabaseHealthResponse)
def get_database_health():
    """Retorna el diagnóstico de salud, integridad SQLite y aviso de tiempo sin respaldo."""
    return backup_service.get_database_health()


@router.post("/create", response_model=BackupMetadata, status_code=status.HTTP_201_CREATED)
def create_backup(custom_name: Optional[str] = Query(None, description="Nombre personalizado opcional")):
    """Crea una instantánea local en caliente (MANUAL) en el directorio backups/."""
    try:
        return backup_service.create_backup(backup_type="MANUAL", custom_name=custom_name)
    except Exception as exc:
        logger.error("Fallo al crear copia de seguridad: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando la copia de seguridad: {str(exc)}",
        )


@router.get("/download")
def download_backup():
    """Genera una copia consistente en caliente al vuelo y la devuelve como descarga binaria (.db)."""
    try:
        meta = backup_service.create_backup(backup_type="MANUAL")
        file_path = backup_service.get_backup_dir() / meta.filename
        return FileResponse(
            path=str(file_path),
            filename=meta.filename,
            media_type="application/x-sqlite3",
            headers={"Content-Disposition": f'attachment; filename="{meta.filename}"'},
        )
    except Exception as exc:
        logger.error("Error preparando la descarga de la copia de seguridad: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo generar la copia para descarga: {str(exc)}",
        )


@router.get("/list", response_model=BackupListResponse)
def list_backups():
    """Retorna la lista de todas las instantáneas locales disponibles en el servidor."""
    return backup_service.list_backups()


@router.post("/validate", response_model=BackupValidationResult)
async def validate_backup_upload(file: UploadFile = File(...)):
    """Inspecciona y valida la integridad de un archivo de copia subido sin aplicarlo."""
    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe tener extensión .db de SQLite válida.",
        )

    token = uuid.uuid4().hex[:8]
    temp_dir = Path(tempfile.gettempdir())
    temp_path = temp_dir / f"validate_{token}_{file.filename}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return backup_service.validate_backup_file(temp_path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


@router.post("/restore/upload", response_model=RestoreResponse)
async def restore_from_upload(file: UploadFile = File(...)):
    """Sube un archivo .db, valida su integridad estructural y restaura creando snapshot previo."""
    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe tener extensión .db de SQLite válida.",
        )

    # Guardar en archivo temporal con token único para inspección segura
    token = uuid.uuid4().hex[:8]
    temp_dir = Path(tempfile.gettempdir())
    temp_path = temp_dir / f"upload_{token}_{file.filename}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        validation = backup_service.validate_backup_file(temp_path)
        if not validation.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archivo de copia inválido o corrupto: {validation.error_message}",
            )

        # Restaurar sobre la base activa
        return backup_service.restore_backup(backup_file_path=temp_path)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Fallo durante la restauración del archivo subido %s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante la restauración: {str(exc)}",
        )
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


@router.post("/restore/local/{filename}", response_model=RestoreResponse)
def restore_from_local(filename: str):
    """Restaura una copia de seguridad existente en el directorio local backups/."""
    b_dir = backup_service.get_backup_dir()
    backup_path = (b_dir / filename).resolve()

    if backup_path.parent != b_dir.resolve():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: ruta no permitida.",
        )

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró la copia de seguridad '{filename}'.",
        )

    try:
        return backup_service.restore_backup(backup_file_path=backup_path)
    except ValueError as val_exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_exc),
        )
    except Exception as exc:
        logger.error("Error al restaurar copia local %s: %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error restaurando la copia local: {str(exc)}",
        )


@router.post("/restore/rollback", response_model=RestoreResponse)
def rollback_restore():
    """Deshace en 1 clic la última restauración aplicando el snapshot previo de seguridad."""
    try:
        return backup_service.rollback_last_restore()
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf),
        )
    except ValueError as val_exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_exc),
        )
    except Exception as exc:
        logger.error("Error al ejecutar rollback: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo revertir la restauración: {str(exc)}",
        )


@router.delete("/local/{filename}")
def delete_local_backup(filename: str):
    """Elimina permanentemente una copia de seguridad local."""
    try:
        backup_service.delete_local_backup(filename)
        return {"deleted": True, "filename": filename}
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf),
        )
    except PermissionError as perm_err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(perm_err),
        )
    except Exception as exc:
        logger.error("Error al eliminar la copia %s: %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.get("/schedule", response_model=BackupScheduleResponse)
def get_schedule(db: Session = Depends(get_db)):
    """Obtiene la configuración y fecha estimada de la próxima copia programada."""
    config = backup_service.get_or_create_schedule_config(db)
    return backup_service.update_schedule_config(
        db,
        BackupScheduleUpdate(
            enabled=config.enabled,
            frequency_days=config.frequency_days,
            keep_max_copies=config.keep_max_copies,
        ),
    )


@router.put("/schedule", response_model=BackupScheduleResponse)
def update_schedule(update: BackupScheduleUpdate, db: Session = Depends(get_db)):
    """Actualiza la frecuencia y límite de retención de las copias automáticas."""
    return backup_service.update_schedule_config(db, update)
