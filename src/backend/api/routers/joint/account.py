"""Sub-router de onboarding, configuración y catálogo de subcategorías de cuenta conjunta."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.routers.joint.deps import get_repo, get_sync_service
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.componentes.sqlite_db import get_db
from backend.domain.models.joint import JointAppliedSyncEvent
from backend.domain.schemas import joint as schemas
from backend.services.joint_sync_service import JointSyncService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=schemas.JointStatusResponse)
def get_joint_status(repo: SQLiteRepository = Depends(get_repo)) -> schemas.JointStatusResponse:
    """Retorna si la cuenta conjunta está configurada o si el usuario se encuentra en Estado Cero."""
    account = repo.get_joint_account()
    if not account:
        return schemas.JointStatusResponse(is_configured=False)

    try:
        stage = schemas.CohabitationStage(account.cohabitation_stage)
    except (ValueError, KeyError):
        stage = schemas.CohabitationStage.PRE_COHABITATION

    try:
        loc_prof = schemas.ProfileIdentifier(account.local_profile)
    except (ValueError, KeyError):
        loc_prof = schemas.ProfileIdentifier.MEMBER_A

    return schemas.JointStatusResponse(
        is_configured=True,
        household_name=account.household_name,
        cohabitation_stage=stage,
        local_profile=loc_prof,
    )


@router.post("/setup", response_model=schemas.JointAccountResponse, status_code=status.HTTP_201_CREATED)
def setup_joint_account(
    setup_req: schemas.JointAccountSetupRequest,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointAccountResponse:
    """Ejecuta el Asistente de Configuración Inicial (Onboarding) y siembra las subcategorías base."""
    existing = repo.get_joint_account()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta conjunta configurada en este dispositivo.",
        )

    try:
        account = repo.create_joint_account(setup_req)
        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.ACCOUNT,
            action=schemas.SyncAction.UPSERT,
            payload=setup_req.model_dump(mode="json"),
            origin_device_id=sync_service.local_device_id,
        )
        return schemas.JointAccountResponse.model_validate(account)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/account", response_model=schemas.JointAccountResponse)
def get_joint_account(repo: SQLiteRepository = Depends(get_repo)) -> schemas.JointAccountResponse:
    """Consulta la configuración y parámetros del hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La cuenta conjunta aún no ha sido configurada en este dispositivo.",
        )
    return schemas.JointAccountResponse.model_validate(account)


@router.put("/account", response_model=schemas.JointAccountResponse)
def update_joint_account(
    update_req: schemas.JointAccountUpdate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointAccountResponse:
    """Actualiza los parámetros de convivencia, split o ingresos de referencia del hogar."""
    account = repo.update_joint_account(update_req)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La cuenta conjunta no existe para ser actualizada.",
        )

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.ACCOUNT,
        action=schemas.SyncAction.UPSERT,
        payload=update_req.model_dump(exclude_unset=True, mode="json"),
        origin_device_id=sync_service.local_device_id,
    )
    return schemas.JointAccountResponse.model_validate(account)


@router.post("/resend-invitation")
def resend_joint_invitation(
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Re-emite el evento delta de invitación de cuenta conjunta para que Syncthing lo entregue a la pareja."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay una cuenta conjunta configurada para invitar.",
        )

    event = sync_service.emit_event(
        entity_type=schemas.SyncEntityType.ACCOUNT,
        action=schemas.SyncAction.UPSERT,
        payload={
            "household_name": account.household_name,
            "cohabitation_stage": account.cohabitation_stage,
            "contribution_strategy": account.contribution_strategy,
            "split_mode": account.split_mode,
            "member_a_reference_income": account.member_a_reference_income,
            "member_b_reference_income": account.member_b_reference_income,
            "member_a_contribution_pct": account.member_a_contribution_pct,
            "member_b_contribution_pct": account.member_b_contribution_pct,
            "member_a_name": account.member_a_name,
            "member_b_name": account.member_b_name,
            "local_profile": account.local_profile,
            "remote_profile": account.remote_profile,
            "custom_total_monthly_budget": getattr(account, "custom_total_monthly_budget", 0.0),
        },
        origin_device_id=sync_service.local_device_id,
    )
    return {
        "success": True,
        "message": "Invitación re-emitida con éxito a sync/outbox/.",
        "event_id": event.event_id,
    }


@router.get("/invitation")
def check_joint_invitation(
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Comprueba si existe una invitación entrante en sync/inbox/ para unirse a un hogar."""
    account = repo.get_joint_account()
    if account:
        return {"has_invitation": False, "invitation": None}

    invitation = sync_service.get_pending_invitation()
    if invitation:
        return {"has_invitation": True, "invitation": invitation}
    return {"has_invitation": False, "invitation": None}


@router.post("/accept-invitation", response_model=schemas.JointAccountResponse, status_code=status.HTTP_201_CREATED)
def accept_joint_invitation(
    db: Session = Depends(get_db),
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointAccountResponse:
    """Acepta la invitación detectada en sync/inbox/ y configura la cuenta conjunta local."""
    existing = repo.get_joint_account()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta conjunta configurada en este dispositivo.",
        )

    invitation = sync_service.get_pending_invitation()
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró ninguna invitación pendiente en la bandeja de entrada.",
        )

    stage_val = invitation.get("cohabitation_stage", "PRE_COHABITATION")
    strategy_val = invitation.get("contribution_strategy", "NOMINAL_TEMPLATE")
    split_val = invitation.get("split_mode", "EQUAL_50_50")

    try:
        cohab_stage = schemas.CohabitationStage(stage_val)
    except (ValueError, KeyError):
        cohab_stage = schemas.CohabitationStage.PRE_COHABITATION

    try:
        contrib_strategy = schemas.ContributionStrategy(strategy_val)
    except (ValueError, KeyError):
        contrib_strategy = schemas.ContributionStrategy.NOMINAL_TEMPLATE

    try:
        split_mode = schemas.SplitMode(split_val)
    except (ValueError, KeyError):
        split_mode = schemas.SplitMode.EQUAL_50_50

    setup_req = schemas.JointAccountSetupRequest(
        household_name=invitation["household_name"],
        member_a_name=invitation.get("member_a_name", "Miembro A"),
        member_b_name=invitation.get("member_b_name", "Miembro B"),
        cohabitation_stage=cohab_stage,
        contribution_strategy=contrib_strategy,
        split_mode=split_mode,
        member_a_reference_income=float(invitation.get("member_a_reference_income", 0.0)),
        member_b_reference_income=float(invitation.get("member_b_reference_income", 0.0)),
        member_a_contribution_pct=float(invitation.get("member_a_contribution_pct", 50.0)),
        member_b_contribution_pct=float(invitation.get("member_b_contribution_pct", 50.0)),
        custom_total_monthly_budget=float(invitation.get("custom_total_monthly_budget", 0.0)),
        local_profile=schemas.ProfileIdentifier.MEMBER_B,
        remote_profile=schemas.ProfileIdentifier.MEMBER_A,
    )

    account = repo.create_joint_account(setup_req)

    applied = JointAppliedSyncEvent(
        event_id=invitation["event_id"],
        entity_type="ACCOUNT",
        action="UPSERT",
        applied_at=datetime.now(timezone.utc),
    )
    db.add(applied)
    db.commit()

    sync_service.process_inbox(db)
    return schemas.JointAccountResponse.model_validate(account)


@router.post("/reset")
def reset_joint_account(
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Purga la cuenta conjunta completa y limpia las carpetas de sincronización."""
    account = repo.get_joint_account()
    sync_service.clear_sync_folders(keep_outbox=False)

    if account:
        try:
            sync_service.emit_event(
                entity_type=schemas.SyncEntityType.ACCOUNT,
                action=schemas.SyncAction.DELETE,
                payload={"household_name": account.household_name},
                origin_device_id=sync_service.local_device_id,
            )
        except Exception as exc:
            logger.warning("No se pudo emitir evento ACCOUNT DELETE en reset: %s", exc)

    repo.reset_joint_account()
    logger.info("Cuenta conjunta reseteada al Estado Cero exitosamente.")
    return {"status": "success", "message": "Cuenta conjunta purgada y restablecida al Estado Cero."}


@router.get("/categories", response_model=List[schemas.JointCategoryResponse])
def get_joint_categories(repo: SQLiteRepository = Depends(get_repo)) -> List[schemas.JointCategoryResponse]:
    """Obtiene el catálogo de conceptos comunes (sin ocio)."""
    return [schemas.JointCategoryResponse.model_validate(c) for c in repo.get_joint_categories()]


@router.get("/subcategories", response_model=List[schemas.JointSubcategoryResponse])
def get_joint_subcategories(
    category_id: Optional[int] = None,
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointSubcategoryResponse]:
    """Obtiene las subcategorías de necesidades del hogar."""
    return [schemas.JointSubcategoryResponse.model_validate(s) for s in repo.get_joint_subcategories(category_id=category_id)]


@router.post("/subcategories", response_model=schemas.JointSubcategoryResponse, status_code=status.HTTP_201_CREATED)
def create_joint_subcategory(
    subcat_create: schemas.JointSubcategoryCreate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointSubcategoryResponse:
    """Crea una nueva subcategoría de necesidades comunes y emite evento delta a la pareja."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe configurar la cuenta conjunta antes de añadir subcategorías.",
        )

    try:
        subcat = repo.create_joint_subcategory(subcat_create)
    except ValueError as val_err:
        err_str = str(val_err)
        status_code = status.HTTP_400_BAD_REQUEST if "Pre-Convivencia" in err_str else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=err_str)

    cat = repo.get_joint_category(subcat.joint_category_id)
    cat_name = cat.name if cat else None

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SUBCATEGORY,
        action=schemas.SyncAction.UPSERT,
        payload={
            "name": subcat.name,
            "monthly_budget": subcat.monthly_budget,
            "category_name": cat_name,
        },
        origin_device_id=sync_service.local_device_id,
    )
    return schemas.JointSubcategoryResponse.model_validate(subcat)


@router.put("/subcategories/{subcategory_id}", response_model=schemas.JointSubcategoryResponse)
def update_joint_subcategory(
    subcategory_id: int,
    subcat_update: schemas.JointSubcategoryUpdate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointSubcategoryResponse:
    """Actualiza una subcategoría de necesidades comunes y propaga el cambio a la pareja."""
    try:
        subcat = repo.update_joint_subcategory(subcategory_id, subcat_update)
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    if not subcat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcategoría no encontrada.")

    cat = repo.get_joint_category(subcat.joint_category_id)
    cat_name = cat.name if cat else None

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SUBCATEGORY,
        action=schemas.SyncAction.UPSERT,
        payload={
            "name": subcat.name,
            "monthly_budget": subcat.monthly_budget,
            "category_name": cat_name,
        },
        origin_device_id=sync_service.local_device_id,
    )
    return schemas.JointSubcategoryResponse.model_validate(subcat)


@router.get("/subcategories/{subcategory_id}/usage")
def check_joint_subcategory_usage(
    subcategory_id: int,
    repo: SQLiteRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """Comprueba el número de transacciones comunes que dependen de una subcategoría conjunta."""
    subcat = repo.get_joint_subcategory(subcategory_id)
    if not subcat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcategoría conjunta no encontrada.")
    return repo.check_joint_subcategory_usage(subcategory_id)


@router.delete("/subcategories/{subcategory_id}")
def delete_joint_subcategory(
    subcategory_id: int,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Elimina una subcategoría de necesidades comunes y propaga el tombstone a la pareja si no tiene uso."""
    subcat = repo.get_joint_subcategory(subcategory_id)
    if not subcat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcategoría no encontrada.")

    usage = repo.check_joint_subcategory_usage(subcategory_id)
    if not usage.get("can_delete", False):
        if usage.get("is_base", False):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No se puede eliminar la subcategoría base del hogar '{subcat.name}'.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede eliminar la subcategoría conjunta '{subcat.name}': "
                f"tiene {usage.get('transactions_count', 0)} transacciones del hogar vinculadas."
            ),
        )

    subcat_name = subcat.name
    try:
        success = repo.delete_joint_subcategory(subcategory_id)
    except ValueError as v_err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(v_err))
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se pudo eliminar la subcategoría.")

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SUBCATEGORY,
        action=schemas.SyncAction.DELETE,
        payload={"name": subcat_name},
        origin_device_id=sync_service.local_device_id,
    )
    return {"deleted": True, "subcategory_id": subcategory_id}
