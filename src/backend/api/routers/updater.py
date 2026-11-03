"""
Router REST para el actualizador del sistema en 1 clic (In-App OTA Updater).
Expone endpoints fuertemente tipados bajo /api/updater para consulta de versión,
comprobación de actualizaciones remotas en GitHub, aplicación con validación previa
y reversión atómica de código (rollback).
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.domain.schemas.updater import (
    CodeRollbackResponse,
    UpdateApplyRequest,
    UpdateApplyResponse,
    UpdateCheckResponse,
    VersionInfo,
)
from backend.services import updater_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/updater", tags=["updater"])


@router.get("/version", response_model=VersionInfo)
def get_version():
    """Devuelve la versión actualmente instalada, rama activa y disponibilidad de rollback."""
    try:
        return updater_service.get_current_version()
    except Exception as exc:
        logger.error("Error al obtener la versión del sistema: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo versión: {str(exc)}",
        )


@router.get("/check", response_model=UpdateCheckResponse)
def check_updates(
    force: bool = Query(default=False, description="Forzar comprobación ignorando la caché"),
    branch: Optional[str] = Query(default=None, description="Rama específica a consultar en GitHub"),
):
    """Comprueba en GitHub API si existen actualizaciones disponibles con soporte de caché en RAM."""
    try:
        return updater_service.check_remote_updates(force=force, branch=branch)
    except Exception as exc:
        logger.error("Error durante la comprobación de actualizaciones: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error comprobando actualizaciones: {str(exc)}",
        )


@router.post("/apply", response_model=UpdateApplyResponse)
def apply_update(payload: Optional[UpdateApplyRequest] = None):
    """
    Ejecuta el ciclo de actualización en staging, validando sintaxis, respaldando
    la base de datos y el código previo, reemplazando ficheros y purgando bytecode.
    """
    branch = payload.branch if payload else None
    remote_commit = payload.remote_commit if payload else None

    logger.info("Recibida solicitud para aplicar actualización (rama: %s, commit: %s)", branch, remote_commit)
    try:
        return updater_service.apply_update(branch=branch, remote_commit=remote_commit)
    except ValueError as exc:
        logger.warning("Validación previa o anti-tar-slip rechazada: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        logger.error("Error operativo al actualizar: %s", exc)
        status_code = status.HTTP_409_CONFLICT if "en curso" in str(exc) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=status_code,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Fallo inesperado al aplicar actualización: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error inesperado al aplicar actualización: {str(exc)}",
        )


@router.post("/rollback", response_model=CodeRollbackResponse)
def rollback_update():
    """Restaura el código y requerimientos previos desde backups/code_snapshot_prev.tar.gz."""
    logger.info("Recibida solicitud de reversión de código (rollback)")
    try:
        return updater_service.rollback_code()
    except FileNotFoundError as exc:
        logger.warning("Intento de rollback sin instantánea previa: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except RuntimeError as exc:
        logger.error("Error de concurrencia en rollback: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except ValueError as exc:
        logger.error("Fallo de seguridad al descomprimir snapshot previo: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Fallo inesperado durante el rollback de código: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error inesperado al revertir código: {str(exc)}",
        )

