"""Sub-router de aportaciones mensuales, salud financiera y resumen anual del hogar."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.routers.joint.deps import (
    AssistedContributionRequest,
    get_repo,
    get_sync_service,
)
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.schemas import joint as schemas
from backend.services.joint_application_service import (
    JointForbiddenError,
    JointNotFoundError,
    JointValidationError,
    get_joint_annual_summary_report,
    get_joint_contribution_calculation_summary,
    get_joint_health_diagnostic,
    record_assisted_contribution_flow,
)
from backend.services.joint_sync_service import JointSyncService

router = APIRouter()


@router.get("/contributions", response_model=List[schemas.JointMonthlyContributionResponse])
def get_joint_contributions(
    year: Optional[int] = None,
    month: Optional[str] = None,
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointMonthlyContributionResponse]:
    """Obtiene el historial de aportaciones realizadas por ambos miembros."""
    return [schemas.JointMonthlyContributionResponse.model_validate(c) for c in repo.get_joint_contributions(year=year, month=month)]


@router.get("/contributions/calculation")
def get_joint_contribution_calculation(
    repo: SQLiteRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Calcula de forma pura las cuotas mensuales a aportar por cada miembro según las reglas del hogar."""
    try:
        return get_joint_contribution_calculation_summary(repo)
    except JointNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/contributions/asentar-asistida", status_code=status.HTTP_201_CREATED)
def record_assisted_contribution(
    req: AssistedContributionRequest,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Ejecuta el asiento en 1 clic de inicio de mes."""
    try:
        return record_assisted_contribution_flow(
            repo=repo,
            sync_service=sync_service,
            month=req.month,
            amount=req.amount,
            contributor_profile=req.contributor_profile,
            personal_subcategory_id=req.personal_subcategory_id,
            contribution_date=req.contribution_date,
            target_sinking_fund_id=req.target_sinking_fund_id,
        )
    except JointValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except JointForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.delete("/contributions/{contribution_id}")
def delete_joint_contribution(
    contribution_id: int,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Elimina físicamente una aportación conjunta y emite tombstone de sincronización a la pareja."""
    del_info = repo.delete_joint_contribution(contribution_id)
    if not del_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aportación conjunta no encontrada.",
        )

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.CONTRIBUTION,
        action=schemas.SyncAction.DELETE,
        payload={
            "uuid": del_info["uuid"],
            "month": del_info["month"],
            "contributor_profile": del_info["contributor_profile"],
        },
        origin_device_id=sync_service.local_device_id,
    )

    for fund_data in (del_info.get("reverted_funds") or {}).values():
        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.SINKING_FUND,
            action=schemas.SyncAction.UPSERT,
            payload=fund_data,
            origin_device_id=sync_service.local_device_id,
        )

    return {"success": True, "deleted_uuid": del_info["uuid"]}


@router.get("/health", response_model=schemas.JointHealthDiagnosticResponse)
def get_joint_health(repo: SQLiteRepository = Depends(get_repo)) -> schemas.JointHealthDiagnosticResponse:
    """Calcula la Tasa de Esfuerzo Familiar y el semáforo determinista de sostenibilidad."""
    try:
        return get_joint_health_diagnostic(repo)
    except JointNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/annual-summary", response_model=schemas.JointAnnualSummaryResponse)
def get_joint_annual_summary(
    year: int = Query(..., ge=2000, le=2100),
    repo: SQLiteRepository = Depends(get_repo),
) -> schemas.JointAnnualSummaryResponse:
    """Retorna el Resumen Anual consolidado del hogar."""
    try:
        return get_joint_annual_summary_report(repo, year=year)
    except JointNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
