"""
Router REST para el Companion Móvil Quick-Capture (Spec 016).
Expone endpoints fuertemente tipados bajo /api/mobile para catálogo,
sincronización de transacciones e informes de estado.
"""

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.domain.schemas.mobile import (
    MobileBudgetUpdate,
    MobileCatalogResponse,
    MobileMonthlySummaryResponse,
    MobileSubcategoryCreate,
    MobileSubcategoryResponse,
    MobileSyncRequest,
    MobileSyncResponse,
    MobileSyncStatusResponse,
)
from backend.services.mobile_sync_service import MobileSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mobile", tags=["mobile"])


def get_sync_service() -> MobileSyncService:
    return MobileSyncService()


def verify_mobile_token(
    x_mobile_pairing_token: Optional[str] = Header(None, alias="X-Mobile-Pairing-Token"),
    token: Optional[str] = Query(None),
    service: MobileSyncService = Depends(get_sync_service),
) -> str:
    """Verifica que la petición contenga el token secreto de emparejamiento maestro."""
    provided_token = x_mobile_pairing_token or token
    if not service.validate_pairing_token(provided_token):
        logger.warning("Intento de acceso móvil no autorizado o con token no coincidente")
        raise HTTPException(
            status_code=403,
            detail="Token de emparejamiento móvil no válido o ausente (Dispositivo no vinculado)",
        )
    return provided_token or ""


@router.get("/catalog", response_model=MobileCatalogResponse)
def get_catalog(
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
    _auth: str = Depends(verify_mobile_token),
) -> MobileCatalogResponse:
    """Retorna el catálogo completo con categorías, subcategorías frecuentes y sugerencias para el móvil."""
    return service.get_mobile_catalog(db)


@router.post("/sync", response_model=MobileSyncResponse)
def sync_transactions(
    request: MobileSyncRequest,
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
    _auth: str = Depends(verify_mobile_token),
) -> MobileSyncResponse:
    """Ingesta de forma atómica e idempotente un lote de transacciones personales enviadas desde el móvil."""
    return service.process_mobile_sync(db, request)


@router.post("/subcategory", response_model=MobileSubcategoryResponse)
def create_subcategory(
    payload: MobileSubcategoryCreate,
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
    _auth: str = Depends(verify_mobile_token),
) -> MobileSubcategoryResponse:
    """Crea una nueva subcategoría sobre la marcha desde el cliente móvil."""
    subcat, is_new = service.create_or_get_subcategory(
        db, payload.name, payload.category_name, payload.category_id
    )
    cat_name = (subcat.category.name if subcat.category else payload.category_name) or "Deseos (30%)"
    return MobileSubcategoryResponse(
        id=subcat.id,
        name=subcat.name,
        category_id=subcat.category_id,
        category_name=cat_name,
        is_new=is_new,
    )


@router.get("/summary", response_model=MobileMonthlySummaryResponse)
def get_monthly_summary(
    month: Optional[str] = Query(None, description="Mes en formato YYYY-MM"),
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
    _auth: str = Depends(verify_mobile_token),
) -> MobileMonthlySummaryResponse:
    """Retorna el resumen presupuestario 50/30/20 y fondo de emergencia del mes para 'Mi Mes'."""
    return service.get_mobile_monthly_summary(db, month)


@router.post("/budget", response_model=Dict[str, Any])
def update_budget(
    payload: MobileBudgetUpdate,
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
    _auth: str = Depends(verify_mobile_token),
) -> Dict[str, Any]:
    """Ajusta la asignación presupuestaria de una subcategoría para un mes determinado."""
    success = service.update_mobile_budget(db, payload)
    return {"success": success}


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
