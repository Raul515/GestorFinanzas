"""Sub-router de sincronización asíncrona, exportación Excel y borrado remoto."""

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.api.routers.joint.deps import get_repo, get_sync_service
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.componentes.sqlite_db import get_db
from backend.services.joint_accounting_service import generate_household_excel_export
from backend.services.joint_sync_service import JointSyncService

router = APIRouter()


@router.post("/sync/process-inbox")
def trigger_process_inbox(
    db: Session = Depends(get_db),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Dispara el procesamiento de los ficheros delta depositados por Syncthing en sync/inbox/."""
    result = sync_service.process_inbox(db)
    return {"status": "ok", "summary": result}


@router.get("/sync/status")
def get_sync_status(
    db: Session = Depends(get_db),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Retorna las métricas y estado del buzón de sincronización."""
    return sync_service.get_sync_status(db)


@router.get("/export/excel")
def export_joint_data_excel(
    db: Session = Depends(get_db),
    repo: SQLiteRepository = Depends(get_repo),
) -> Response:
    """Genera y descarga el archivo Excel (.xlsx) estructurado con los datos del hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta conjunta no configurada.",
        )
    excel_bytes = generate_household_excel_export(db, account.id)
    today_str = datetime.now().strftime("%Y%m%d")
    filename = f"finanzas_hogar_{account.id}_{today_str}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/sync/events")
def get_sync_events_detail(
    max_processed: int = Query(default=30, ge=1, le=100),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Retorna la inspección detallada de deltas en outbox, inbox, processed y error."""
    return sync_service.get_sync_events_detail(max_processed=max_processed)


@router.post("/sync/retry-errors")
def retry_sync_errors(
    db: Session = Depends(get_db),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Mueve los deltas de sync/error/ a sync/inbox/ y dispara el procesamiento inmediato."""
    return sync_service.retry_failed_events(db)


@router.post("/sync/clear-errors")
def clear_sync_errors(
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Elimina permanentemente los eventos delta fallidos de la carpeta sync/error/."""
    deleted_count = sync_service.clear_failed_events()
    return {"status": "ok", "deleted_count": deleted_count}


@router.get("/remote-deletion/pending")
def get_pending_remote_deletion(
    db: Session = Depends(get_db),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Consulta si existe una solicitud pendiente de borrado remoto del hogar emitida por la pareja."""
    pending = sync_service.get_pending_account_deletion(db)
    return {"pending": pending is not None, "data": pending}


@router.post("/remote-deletion/accept")
def accept_remote_deletion(
    db: Session = Depends(get_db),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Acepta el borrado remoto: purga la cuenta conjunta local y vuelve a Estado Cero."""
    return sync_service.resolve_remote_account_deletion(db, accept=True)


@router.post("/remote-deletion/reject")
def reject_remote_deletion(
    db: Session = Depends(get_db),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Rechaza el borrado remoto: conserva los datos locales intactos y archiva la solicitud."""
    return sync_service.resolve_remote_account_deletion(db, accept=False)
