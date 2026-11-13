"""
Router REST para el Companion Móvil Quick-Capture (Spec 016).
Expone endpoints fuertemente tipados bajo /api/mobile para catálogo,
sincronización de transacciones e informes de estado.
"""

import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.domain.schemas.mobile import (
    MobileCatalogResponse,
    MobileSyncRequest,
    MobileSyncResponse,
    MobileSyncStatusResponse,
)
from backend.services.mobile_sync_service import MobileSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mobile", tags=["mobile"])


def get_sync_service() -> MobileSyncService:
    return MobileSyncService()


@router.get("/catalog", response_model=MobileCatalogResponse)
def get_catalog(
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
) -> MobileCatalogResponse:
    """Retorna el catálogo completo con categorías, subcategorías frecuentes y sugerencias para el móvil."""
    return service.get_mobile_catalog(db)


@router.post("/sync", response_model=MobileSyncResponse)
def sync_transactions(
    request: MobileSyncRequest,
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
) -> MobileSyncResponse:
    """Ingesta de forma atómica e idempotente un lote de transacciones personales enviadas desde el móvil."""
    return service.process_mobile_sync(db, request)


@router.get("/status", response_model=MobileSyncStatusResponse)
def get_status(
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
) -> MobileSyncStatusResponse:
    """Verifica la conectividad y métricas de sincronización para clientes móviles."""
    return service.get_sync_status(db)


@router.post("/process-folder", response_model=Dict[str, Any])
def process_folder(
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Procesa manualmente deltas JSON pendientes en la carpeta sync/mobile/inbox/."""
    processed = service.process_mobile_inbox_folder(db)
    return {"success": True, "processed_count": processed}
