"""
Router REST para el Companion Móvil Quick-Capture (Spec 016).
Expone endpoints fuertemente tipados bajo /api/mobile para catálogo,
sincronización de transacciones e informes de estado.
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
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
    MobileVersionResponse,
    MobileHistoricalTransactionItem,
    MobileSearchResponse,
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


@router.delete("/transactions/{identifier}", response_model=Dict[str, Any])
@router.delete("/transaction/{identifier}", response_model=Dict[str, Any])
def delete_transaction(
    identifier: str,
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
    _auth: str = Depends(verify_mobile_token),
) -> Dict[str, Any]:
    """Elimina de forma segura una transacción móvil identificada por ID numérico o mobile_event_id."""
    deleted_id = service.delete_mobile_transaction(db, identifier)
    if not deleted_id:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró la transacción con identificador '{identifier}' para eliminar.",
        )
    return {"success": True, "deleted_id": deleted_id, "identifier": identifier}


@router.get("/transactions/search", response_model=MobileSearchResponse)
def search_transactions(
    q: str = Query(..., min_length=1, description="Texto a buscar en conceptos o subcategorías"),
    limit: int = Query(50, ge=1, le=200, description="Máximo número de resultados"),
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
    _auth: str = Depends(verify_mobile_token),
) -> MobileSearchResponse:
    """Buscador instantáneo de transacciones históricas en SQLite para el teléfono."""
    return service.search_transactions(db, query_text=q, limit=limit)


@router.get("/transactions/history-cache", response_model=List[MobileHistoricalTransactionItem])
def get_history_cache(
    months: int = Query(12, ge=1, le=60, description="Meses hacia atrás a sincronizar"),
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
    _auth: str = Depends(verify_mobile_token),
) -> List[MobileHistoricalTransactionItem]:
    """Retorna un paquete compacto de transacciones de los últimos N meses para la caché offline del móvil."""
    return service.get_historical_cache(db, months=months)




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


@router.get("/version", response_model=MobileVersionResponse)
def get_version(
    service: MobileSyncService = Depends(get_sync_service),
) -> MobileVersionResponse:
    """Retorna la versión publicada más reciente del APK para auto-actualizaciones in-app (OTA)."""
    return service.get_mobile_version_info()


@router.get("/download-apk")
def download_apk(
    service: MobileSyncService = Depends(get_sync_service),
):
    """Descarga directa del binario APK de Android para instalación o actualización."""
    apk_path = service.get_latest_apk_path()
    if not apk_path or not apk_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No se encontró ningún binario APK disponible para descarga. Compílalo o deposítalo en sync/mobile/apk/.",
        )
    return FileResponse(
        path=str(apk_path),
        media_type="application/vnd.android.package-archive",
        filename=apk_path.name,
    )


@router.post("/upload-apk", response_model=MobileVersionResponse)
async def upload_apk(
    apk_file: UploadFile = File(...),
    version_code: int = Form(...),
    version_name: str = Form(...),
    release_notes: str = Form(""),
    service: MobileSyncService = Depends(get_sync_service),
) -> MobileVersionResponse:
    """Permite publicar una nueva release de la APK de Android desde el panel de control."""
    content = await apk_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo APK subido está vacío.")
    filename = apk_file.filename or "app-release.apk"
    return service.publish_apk_release(
        apk_bytes=content,
        filename=filename,
        version_code=version_code,
        version_name=version_name,
        release_notes=release_notes,
    )
