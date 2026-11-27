"""
Router REST para el Companion Móvil Quick-Capture (Spec 016).
Expone endpoints fuertemente tipados bajo /api/mobile para catálogo,
sincronización de transacciones e informes de estado.
"""

import ipaddress
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.domain.schemas.mobile import (
    MobileAdminPairingTokenResponse,
    MobileBudgetUpdate,
    MobileCatalogResponse,
    MobileMonthlySummaryResponse,
    MobilePinGenerateResponse,
    MobilePinPairRequest,
    MobilePinPairResponse,
    MobileSubcategoryCreate,
    MobileSubcategoryResponse,
    MobileSyncRequest,
    MobileSyncResponse,
    MobileSyncStatusResponse,
    MobileVersionResponse,
    MobileHistoricalTransactionItem,
    MobileSearchResponse,
    MobileReceiptUploadResponse,
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
    x_mobile_pairing_token: Optional[str] = Header(None, alias="X-Mobile-Pairing-Token"),
    token: Optional[str] = Query(None),
    service: MobileSyncService = Depends(get_sync_service),
) -> MobileSyncStatusResponse:
    """
    Verifica la conectividad y métricas de sincronización para clientes móviles.
    Indica si la sesión o cabecera actual está autenticada sin filtrar el token maestro (SEC-01).
    """
    provided_token = x_mobile_pairing_token or token
    is_authenticated = bool(provided_token and service.validate_pairing_token(provided_token))
    return service.get_sync_status(db, authenticated=is_authenticated)


_PROXY_FORWARDING_HEADERS = (
    "x-forwarded-for",
    "forwarded",
    "x-real-ip",
    "tailscale-user-login",
    "tailscale-user-name",
)


def _verify_admin_network_access(request: Request, endpoint_name: str) -> None:
    """Verifica que la petición administrativa provenga de loopback o red interna directa sin proxy (SEC-01)."""
    # Si la petición trae cabeceras de proxy inverso (ej. Tailscale Serve, Caddy, Nginx),
    # proviene de un cliente externo reenviado y debe ser rechazada aunque el socket llegue por 127.0.0.1 o bridge Docker.
    try:
        req_headers = request.headers
    except (KeyError, AttributeError):
        req_headers = {}
    for hdr in _PROXY_FORWARDING_HEADERS:
        if str(req_headers.get(hdr, "")).strip():
            logger.warning(
                "Acceso administrativo denegado en %s por cabecera de proxy (%s)",
                endpoint_name,
                hdr,
            )
            raise HTTPException(
                status_code=403,
                detail="Acceso denegado. Los endpoints administrativos no están permitidos a través de proxy o túnel.",
            )

    client_ip = request.client.host if request.client else "unknown"
    is_allowed = client_ip in ("127.0.0.1", "::1", "localhost", "testclient")
    if not is_allowed:
        try:
            ip_obj = ipaddress.ip_address(client_ip)
            # Permitir loopback y subred bridge interna de Docker (172.16.0.0/12)
            # Excluyendo explícitamente la subred universal de Hotspot de iPhone (172.20.10.0/24)
            is_docker_internal = (
                ip_obj in ipaddress.ip_network("172.16.0.0/12")
                and ip_obj not in ipaddress.ip_network("172.20.10.0/24")
            )
            if ip_obj.is_loopback or is_docker_internal:
                is_allowed = True
        except ValueError:
            pass

    if not is_allowed:
        logger.warning("Intento de acceso denegado a %s desde IP no autorizada: %s", endpoint_name, client_ip)
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado. Este endpoint está reservado exclusivamente al host local o red interna.",
        )


@router.get("/admin/pairing-token", response_model=MobileAdminPairingTokenResponse)
def get_admin_pairing_token(
    request: Request,
    service: MobileSyncService = Depends(get_sync_service),
) -> MobileAdminPairingTokenResponse:
    """
    Retorna el pairing token maestro exclusivamente para la administración local (Streamlit en el PC).
    Rechaza peticiones originadas desde direcciones IP externas / no loopback (SEC-01).
    """
    _verify_admin_network_access(request, "/api/mobile/admin/pairing-token")
    return MobileAdminPairingTokenResponse(pairing_token=service.get_or_create_pairing_token())


@router.post("/admin/generate-pin", response_model=MobilePinGenerateResponse)
def generate_admin_pairing_pin(
    request: Request,
    ttl_seconds: int = Query(600, ge=60, le=3600),
    service: MobileSyncService = Depends(get_sync_service),
) -> MobilePinGenerateResponse:
    """
    Genera un código PIN de 6 dígitos temporal para vincular un dispositivo móvil sin cámara (SEC-01).
    Solo accesible desde loopback o red local interna de administración.
    """
    _verify_admin_network_access(request, "/api/mobile/admin/generate-pin")
    pin_data = service.generate_pairing_pin(ttl_seconds=ttl_seconds)
    return MobilePinGenerateResponse(**pin_data)


@router.post("/pair-pin", response_model=MobilePinPairResponse)
def pair_device_with_pin(
    payload: MobilePinPairRequest,
    service: MobileSyncService = Depends(get_sync_service),
) -> MobilePinPairResponse:
    """
    Canjea un PIN temporal de 6 dígitos por el token maestro de emparejamiento.
    Accesible desde cualquier cliente en la red Wi-Fi; protegido contra fuerza bruta.
    """
    success, token, message = service.pair_with_pin(payload.pin)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return MobilePinPairResponse(
        success=True,
        pairing_token=token,
        message=message,
    )


@router.post("/process-folder", response_model=Dict[str, Any])
def process_folder(
    db: Session = Depends(get_db),
    service: MobileSyncService = Depends(get_sync_service),
    _auth: str = Depends(verify_mobile_token),
) -> Dict[str, Any]:
    """Procesa manualmente deltas JSON pendientes en la carpeta sync/mobile/inbox/ (Protegido SEC-05)."""
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
    _auth: str = Depends(verify_mobile_token),
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


@router.post("/receipts", response_model=MobileReceiptUploadResponse)
async def upload_mobile_receipt(
    event_id: str = Form(...),
    receipt_file: UploadFile = File(...),
    token: str = Depends(verify_mobile_token),
    service: MobileSyncService = Depends(get_sync_service),
) -> MobileReceiptUploadResponse:
    """Permite subir una imagen de comprobante o ticket vinculada a un gasto móvil."""
    if not receipt_file.content_type or not receipt_file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Tipo de archivo no permitido. Solo se aceptan imágenes (JPEG, PNG, WebP).",
        )

    content = await receipt_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo de imagen está vacío.")

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="La imagen no puede exceder los 5 MB de tamaño.")

    saved_fn = service.save_receipt_file(event_id=event_id, file_bytes=content)
    if not saved_fn:
        raise HTTPException(status_code=500, detail="Error al guardar la imagen en disco.")

    return MobileReceiptUploadResponse(
        success=True,
        event_id=event_id,
        receipt_filename=saved_fn,
        receipt_url=f"/api/mobile/receipts/{saved_fn}",
    )


@router.get("/receipts/{filename}")
def get_mobile_receipt(
    filename: str,
    token: str = Depends(verify_mobile_token),
    service: MobileSyncService = Depends(get_sync_service),
):
    """Sirve una imagen de comprobante de ticket almacenada en disco."""
    receipt_path = service.get_receipt_path(filename)
    if not receipt_path:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado.")

    # Deducir media type
    suffix = receipt_path.suffix.lower()
    media_type = "image/jpeg"
    if suffix == ".png":
        media_type = "image/png"
    elif suffix == ".webp":
        media_type = "image/webp"

    return FileResponse(path=str(receipt_path), media_type=media_type)
