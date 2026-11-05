"""
Router REST para el espacio conjunto del hogar y finanzas compartidas (Spec 010).
Proporciona endpoints fuertemente tipados con observabilidad estructurada, validaciones Pydantic v2
y control de transacciones para onboarding, configuración, huchas, aportaciones y sincronización.
"""

from datetime import date, datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.componentes.sqlite_db import get_db
from backend.domain.models.joint import JointAppliedSyncEvent
from backend.domain.models.transactions import Transaction as PersonalTransaction
from backend.domain.schemas import joint as schemas
from backend.services.joint_accounting_service import (
    calculate_joint_annual_summary,
    generate_household_excel_export,
    calculate_monthly_contributions,
    evaluate_household_health,
    prepare_assisted_contribution,
    calculate_settlement_summary,
)
from backend.services.joint_sync_service import JointSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/joint", tags=["joint"])


def get_repo(db: Session = Depends(get_db)) -> SQLiteRepository:
    return SQLiteRepository(db)


def get_sync_service() -> JointSyncService:
    return JointSyncService()


class AssistedContributionRequest(BaseModel):
    """Petición para el asiento asistido en 1 clic de inicio de mes."""
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: float = Field(gt=0.0)
    contributor_profile: schemas.ProfileIdentifier
    personal_subcategory_id: Optional[int] = None
    contribution_date: Optional[date] = None
    target_sinking_fund_id: Optional[int] = None


# ==========================================
# 1. ESTADO DE CONFIGURACIÓN Y ONBOARDING
# ==========================================

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
        # Emitir evento delta de cuenta inicializada
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
    """
    Comprueba si existe una invitación entrante en sync/inbox/ para unirse a un hogar
    creado previamente por la pareja.
    """
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
    """
    Acepta la invitación detectada en sync/inbox/ y configura la cuenta conjunta local
    con los perfiles complementarios invertidos (Opción A).
    """
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
        local_profile=schemas.ProfileIdentifier.MEMBER_B,
        remote_profile=schemas.ProfileIdentifier.MEMBER_A,
    )

    account = repo.create_joint_account(setup_req)

    # Registrar evento de cuenta como aplicado
    applied = JointAppliedSyncEvent(
        event_id=invitation["event_id"],
        entity_type="ACCOUNT",
        action="UPSERT",
        applied_at=datetime.now(timezone.utc),
    )
    db.add(applied)
    db.commit()

    # Procesar cualquier otro evento en espera en inbox (huchas, etc.)
    sync_service.process_inbox(db)

    return schemas.JointAccountResponse.model_validate(account)


@router.post("/reset")
def reset_joint_account(
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """
    Purga la cuenta conjunta completa y limpia las carpetas de sincronización,
    devolviendo el sistema al Estado Cero de monousuario.
    Emite un evento ACCOUNT (DELETE) para propagar el reset a la pareja.
    """
    account = repo.get_joint_account()
    had_account = account is not None
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
    sync_service.clear_sync_folders(keep_outbox=had_account)
    logger.info("Cuenta conjunta reseteada al Estado Cero exitosamente.")
    return {"status": "success", "message": "Cuenta conjunta purgada y restablecida al Estado Cero."}


# ==========================================
# 2. CATEGORÍAS Y SUBCATEGORÍAS COMUNES
# ==========================================

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


# ==========================================
# 3. HUCHAS DE AMORTIZACIÓN (SINKING FUNDS)
# ==========================================

@router.get("/sinking-funds", response_model=List[schemas.JointSinkingFundResponse])
def get_joint_sinking_funds(
    fund_status: Optional[str] = Query(default=None, alias="status"),
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointSinkingFundResponse]:
    """Consulta las huchas de amortización del hogar."""
    return [schemas.JointSinkingFundResponse.model_validate(f) for f in repo.get_joint_sinking_funds(status=fund_status)]


@router.post("/sinking-funds", response_model=schemas.JointSinkingFundResponse, status_code=status.HTTP_201_CREATED)
def create_joint_sinking_fund(
    fund_create: schemas.JointSinkingFundCreate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointSinkingFundResponse:
    """Crea una nueva meta de amortización para el hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe configurar la cuenta conjunta antes de añadir huchas.",
        )

    fund = repo.create_joint_sinking_fund(fund_create)
    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SINKING_FUND,
        action=schemas.SyncAction.UPSERT,
        payload=fund_create.model_dump(mode="json"),
        origin_device_id=sync_service.local_device_id,
    )
    return schemas.JointSinkingFundResponse.model_validate(fund)


@router.put("/sinking-funds/{fund_id}", response_model=schemas.JointSinkingFundResponse)
def update_joint_sinking_fund(
    fund_id: int,
    fund_update: schemas.JointSinkingFundUpdate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointSinkingFundResponse:
    """Edita las metas, cuotas o estado de una hucha de amortización."""
    fund = repo.update_joint_sinking_fund(fund_id, fund_update)
    if not fund:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hucha no encontrada.")

    payload = fund_update.model_dump(exclude_unset=True, mode="json")
    payload["name"] = fund.name
    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SINKING_FUND,
        action=schemas.SyncAction.UPSERT,
        payload=payload,
        origin_device_id=sync_service.local_device_id,
    )
    return schemas.JointSinkingFundResponse.model_validate(fund)


@router.delete("/sinking-funds/{fund_id}")
def delete_joint_sinking_fund(
    fund_id: int,
    reallocate_to_fund_id: Optional[int] = Query(default=None),
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Elimina una hucha de amortización, reasignando su saldo remanente a otra hucha activa si procede."""
    fund = repo.get_joint_sinking_fund(fund_id)
    if not fund:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hucha no encontrada.")

    fund_name = fund.name
    success = repo.delete_joint_sinking_fund(fund_id, reallocate_to_fund_id=reallocate_to_fund_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se pudo eliminar la hucha.")

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SINKING_FUND,
        action=schemas.SyncAction.DELETE,
        payload={"name": fund_name},
        origin_device_id=sync_service.local_device_id,
    )

    # Si se reasignó saldo a otra hucha activa, sincronizar el nuevo saldo de la receptora (BUG-4)
    if reallocate_to_fund_id:
        target_fund = repo.get_joint_sinking_fund(reallocate_to_fund_id)
        if target_fund:
            sync_service.emit_event(
                entity_type=schemas.SyncEntityType.SINKING_FUND,
                action=schemas.SyncAction.UPSERT,
                payload={
                    "name": target_fund.name,
                    "target_amount": target_fund.target_amount,
                    "current_balance": target_fund.current_balance,
                    "monthly_target_amount": target_fund.monthly_target_amount,
                    "allocation_percentage": target_fund.allocation_percentage,
                    "status": target_fund.status,
                    "priority": target_fund.priority,
                },
                origin_device_id=sync_service.local_device_id,
            )

    return {"deleted": True, "fund_id": fund_id}


@router.post("/sinking-funds/transfer", response_model=schemas.JointSinkingFundTransferResponse, status_code=status.HTTP_201_CREATED)
def transfer_joint_sinking_fund(
    transfer_req: schemas.JointSinkingFundTransferCreate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointSinkingFundTransferResponse:
    """Ejecuta un traspaso/rebalanceo directo de saldo entre dos huchas de amortización del hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cuenta conjunta no configurada.",
        )

    if transfer_req.source_fund_id == transfer_req.target_fund_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La hucha de origen y de destino no pueden ser la misma.",
        )

    try:
        transfer = repo.transfer_sinking_fund_balance(transfer_req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    source_fund = repo.get_joint_sinking_fund(transfer.source_fund_id)
    target_fund = repo.get_joint_sinking_fund(transfer.target_fund_id)

    # Emitir deltas de actualización de saldo para ambas huchas
    if source_fund:
        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.SINKING_FUND,
            action=schemas.SyncAction.UPSERT,
            payload={
                "name": source_fund.name,
                "target_amount": source_fund.target_amount,
                "current_balance": source_fund.current_balance,
                "monthly_target_amount": source_fund.monthly_target_amount,
                "allocation_percentage": source_fund.allocation_percentage,
                "status": source_fund.status,
                "priority": source_fund.priority,
            },
            origin_device_id=sync_service.local_device_id,
        )

    if target_fund:
        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.SINKING_FUND,
            action=schemas.SyncAction.UPSERT,
            payload={
                "name": target_fund.name,
                "target_amount": target_fund.target_amount,
                "current_balance": target_fund.current_balance,
                "monthly_target_amount": target_fund.monthly_target_amount,
                "allocation_percentage": target_fund.allocation_percentage,
                "status": target_fund.status,
                "priority": target_fund.priority,
            },
            origin_device_id=sync_service.local_device_id,
        )

    # Emitir delta de la transferencia para trazabilidad histórica en la réplica
    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SINKING_FUND_TRANSFER,
        action=schemas.SyncAction.UPSERT,
        payload={
            "uuid": transfer.uuid,
            "source_fund_id": transfer.source_fund_id,
            "source_fund_name": source_fund.name if source_fund else None,
            "target_fund_id": transfer.target_fund_id,
            "target_fund_name": target_fund.name if target_fund else None,
            "amount": transfer.amount,
            "date": transfer.date.isoformat() if hasattr(transfer.date, "isoformat") else str(transfer.date),
            "notes": transfer.notes,
            "created_by_profile": transfer.created_by_profile,
        },
        origin_device_id=sync_service.local_device_id,
    )

    resp = schemas.JointSinkingFundTransferResponse.model_validate(transfer)
    if source_fund:
        resp.source_fund_name = source_fund.name
    if target_fund:
        resp.target_fund_name = target_fund.name
    return resp


@router.get("/sinking-funds/transfers", response_model=List[schemas.JointSinkingFundTransferResponse])
def get_joint_sinking_fund_transfers(
    limit: int = Query(default=100, ge=1, le=500),
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointSinkingFundTransferResponse]:
    """Obtiene el historial cronológico de traspasos y rebalanceos entre huchas."""
    transfers = repo.get_joint_sinking_fund_transfers(limit=limit)
    funds_all = {f.id: f.name for f in repo.get_joint_sinking_funds()}
    result = []
    for t in transfers:
        item = schemas.JointSinkingFundTransferResponse.model_validate(t)
        item.source_fund_name = funds_all.get(t.source_fund_id, f"Hucha #{t.source_fund_id}")
        item.target_fund_name = funds_all.get(t.target_fund_id, f"Hucha #{t.target_fund_id}")
        result.append(item)
    return result


# ==========================================
# 4. TRANSACCIONES Y GASTOS DEL HOGAR
# ==========================================

@router.get("/transactions", response_model=List[schemas.JointTransactionResponse])
def get_joint_transactions(
    year: Optional[int] = None,
    month: Optional[str] = None,
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointTransactionResponse]:
    """Obtiene transacciones de necesidades o cargos a huchas comunes."""
    return [schemas.JointTransactionResponse.model_validate(t) for t in repo.get_joint_transactions(year=year, month=month)]


@router.get("/transactions/search", response_model=List[schemas.JointTransactionResponse])
def search_joint_transactions(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    query: Optional[str] = None,
    joint_subcategory_id: Optional[int] = None,
    paid_by: Optional[str] = None,
    settlement_status: Optional[str] = None,
    is_sinking_fund: Optional[bool] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointTransactionResponse]:
    """Búsqueda global y filtrado multicriterio de transacciones del hogar."""
    txs = repo.search_joint_transactions(
        start_date=start_date,
        end_date=end_date,
        query_text=query,
        joint_subcategory_id=joint_subcategory_id,
        paid_by=paid_by,
        settlement_status=settlement_status,
        is_sinking_fund=is_sinking_fund,
        min_amount=min_amount,
        max_amount=max_amount,
    )
    return [schemas.JointTransactionResponse.model_validate(t) for t in txs]


@router.post("/transactions", response_model=schemas.JointTransactionResponse, status_code=status.HTTP_201_CREATED)
def create_joint_transaction(
    tx_create: schemas.JointTransactionCreate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointTransactionResponse:
    """Registra un nuevo gasto común del hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cuenta conjunta no configurada.",
        )

    tx = repo.create_joint_transaction(tx_create)

    # Resolver nombres descriptivos para tolerancia ante IDs discordantes en sincronización (BUG-3)
    subcat_name = None
    if tx.joint_subcategory_id:
        subcat = repo.get_joint_subcategory(tx.joint_subcategory_id)
        if subcat:
            subcat_name = subcat.name

    sinking_name = None
    if tx.joint_sinking_fund_id:
        fund = repo.get_joint_sinking_fund(tx.joint_sinking_fund_id)
        if fund:
            sinking_name = fund.name

    # Emitir delta para sync (solo TRANSACTION, evitando doble deducción en el receptor)
    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.TRANSACTION,
        action=schemas.SyncAction.UPSERT,
        payload={
            "uuid": tx.uuid,
            "date": tx.date.isoformat() if hasattr(tx.date, "isoformat") else str(tx.date),
            "amount": tx.amount,
            "description": tx.description,
            "joint_subcategory_id": tx.joint_subcategory_id,
            "subcategory_name": subcat_name,
            "joint_sinking_fund_id": tx.joint_sinking_fund_id,
            "sinking_fund_name": sinking_name,
            "sinking_fund_deduction": float(getattr(tx, "sinking_fund_deduction", 0.0) or 0.0),
            "created_by_profile": tx.created_by_profile,
            "paid_by": tx.paid_by,
            "settlement_mechanism": tx.settlement_mechanism,
            "settlement_status": tx.settlement_status,
            "settled_at": tx.settled_at.isoformat() if tx.settled_at else None,
        },
        origin_device_id=sync_service.local_device_id,
    )
    return schemas.JointTransactionResponse.model_validate(tx)


@router.delete("/transactions/{transaction_id}")
def delete_joint_transaction(
    transaction_id: int,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Elimina un gasto común y emite el tombstone correspondiente a Syncthing."""
    tx_uuid = repo.delete_joint_transaction(transaction_id)
    if not tx_uuid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transacción no encontrada.")

    # Emitir tombstone de borrado (el receptor revertirá la deducción de la hucha a partir de la transacción)
    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.TRANSACTION,
        action=schemas.SyncAction.DELETE,
        payload={"uuid": tx_uuid},
        origin_device_id=sync_service.local_device_id,
    )

    return {"deleted": True, "uuid": tx_uuid}


# ==========================================
# 4.1 LIQUIDACIÓN Y REEMBOLSO DE GASTOS (SETTLEMENT)
# ==========================================

@router.get("/settlement/summary", response_model=schemas.JointSettlementSummaryResponse)
def get_joint_settlement_summary(
    repo: SQLiteRepository = Depends(get_repo),
) -> schemas.JointSettlementSummaryResponse:
    """Obtiene el resumen consolidado de deudas y saldos pendientes de reembolso para gastos pagados con tarjeta personal."""
    account = repo.get_joint_account()
    transactions = repo.get_joint_transactions()
    summary = calculate_settlement_summary(transactions, account)
    return schemas.JointSettlementSummaryResponse.model_validate(summary)


@router.post("/settlement/settle-transaction/{transaction_id}", response_model=schemas.JointTransactionResponse)
def settle_joint_transaction(
    transaction_id: int,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointTransactionResponse:
    """Marca un gasto común adelantado como liquidado/reembolsado y emite el delta de sincronización."""
    tx = repo.settle_joint_transaction(transaction_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transacción {transaction_id} no encontrada.",
        )

    subcat_name = None
    if tx.joint_subcategory_id:
        subcat = repo.get_joint_subcategory(tx.joint_subcategory_id)
        if subcat:
            subcat_name = subcat.name

    sinking_name = None
    if tx.joint_sinking_fund_id:
        fund = repo.get_joint_sinking_fund(tx.joint_sinking_fund_id)
        if fund:
            sinking_name = fund.name

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.TRANSACTION,
        action=schemas.SyncAction.UPSERT,
        payload={
            "uuid": tx.uuid,
            "date": tx.date.isoformat() if hasattr(tx.date, "isoformat") else str(tx.date),
            "amount": tx.amount,
            "description": tx.description,
            "joint_subcategory_id": tx.joint_subcategory_id,
            "subcategory_name": subcat_name,
            "joint_sinking_fund_id": tx.joint_sinking_fund_id,
            "sinking_fund_name": sinking_name,
            "sinking_fund_deduction": float(getattr(tx, "sinking_fund_deduction", 0.0) or 0.0),
            "created_by_profile": tx.created_by_profile,
            "paid_by": tx.paid_by,
            "settlement_mechanism": tx.settlement_mechanism,
            "settlement_status": tx.settlement_status,
            "settled_at": tx.settled_at.isoformat() if tx.settled_at else None,
        },
        origin_device_id=sync_service.local_device_id,
    )

    return schemas.JointTransactionResponse.model_validate(tx)


@router.post("/settlement/settle-all", response_model=List[schemas.JointTransactionResponse])
def settle_all_joint_transactions(
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> List[schemas.JointTransactionResponse]:
    """Marca en bloque todas las transacciones pendientes como liquidadas/reembolsadas y emite sus deltas."""
    settled_txs = repo.settle_all_joint_transactions()
    for tx in settled_txs:
        subcat_name = None
        if tx.joint_subcategory_id:
            subcat = repo.get_joint_subcategory(tx.joint_subcategory_id)
            if subcat:
                subcat_name = subcat.name

        sinking_name = None
        if tx.joint_sinking_fund_id:
            fund = repo.get_joint_sinking_fund(tx.joint_sinking_fund_id)
            if fund:
                sinking_name = fund.name

        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.TRANSACTION,
            action=schemas.SyncAction.UPSERT,
            payload={
                "uuid": tx.uuid,
                "date": tx.date.isoformat() if hasattr(tx.date, "isoformat") else str(tx.date),
                "amount": tx.amount,
                "description": tx.description,
                "joint_subcategory_id": tx.joint_subcategory_id,
                "subcategory_name": subcat_name,
                "joint_sinking_fund_id": tx.joint_sinking_fund_id,
                "sinking_fund_name": sinking_name,
                "sinking_fund_deduction": float(getattr(tx, "sinking_fund_deduction", 0.0) or 0.0),
                "created_by_profile": tx.created_by_profile,
                "paid_by": tx.paid_by,
                "settlement_mechanism": tx.settlement_mechanism,
                "settlement_status": tx.settlement_status,
                "settled_at": tx.settled_at.isoformat() if tx.settled_at else None,
            },
            origin_device_id=sync_service.local_device_id,
        )

    return [schemas.JointTransactionResponse.model_validate(tx) for tx in settled_txs]


# ==========================================
# 5. APORTACIONES MENSUALES Y FLUJO ASISTIDO
# ==========================================

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
    """
    Calcula de forma pura las cuotas mensuales a aportar por cada miembro según las reglas del hogar (Mejora 1).
    """
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta conjunta no configurada.",
        )

    subcats = repo.get_joint_subcategories()
    needs_budget = sum(float(s.monthly_budget) for s in subcats) if subcats else 0.0

    funds = repo.get_joint_sinking_funds()
    funds_dicts = [
        {
            "id": f.id,
            "status": f.status,
            "current_balance": f.current_balance,
            "target_amount": f.target_amount,
            "monthly_target_amount": f.monthly_target_amount,
            "allocation_percentage": f.allocation_percentage,
        }
        for f in funds
    ]

    try:
        stage_val = schemas.CohabitationStage(account.cohabitation_stage)
    except (ValueError, KeyError):
        stage_val = schemas.CohabitationStage.PRE_COHABITATION

    try:
        strat_val = schemas.ContributionStrategy(account.contribution_strategy)
    except (ValueError, KeyError):
        strat_val = schemas.ContributionStrategy.NOMINAL_TEMPLATE

    try:
        split_val = schemas.SplitMode(account.split_mode)
    except (ValueError, KeyError):
        split_val = schemas.SplitMode.EQUAL_50_50

    calc = calculate_monthly_contributions(
        cohabitation_stage=stage_val,
        contribution_strategy=strat_val,
        split_mode=split_val,
        needs_budget=needs_budget,
        sinking_funds=funds_dicts,
        member_a_income=account.member_a_reference_income,
        member_b_income=account.member_b_reference_income,
        member_a_contribution_pct=account.member_a_contribution_pct,
        member_b_contribution_pct=account.member_b_contribution_pct,
    )
    calc["local_profile"] = account.local_profile
    calc["remote_profile"] = account.remote_profile
    calc["member_a_name"] = account.member_a_name
    calc["member_b_name"] = account.member_b_name
    return calc


@router.post("/contributions/asentar-asistida", status_code=status.HTTP_201_CREATED)
def record_assisted_contribution(
    req: AssistedContributionRequest,
    db: Session = Depends(get_db),
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """
    Ejecuta el asiento en 1 clic de inicio de mes:
    1. Inserta el gasto en el perfil personal (en Necesidades Básicas o Ahorro).
    2. Inserta la aportación en la cuenta conjunta.
    3. Emite el evento delta en sync/outbox/.
    """
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cuenta conjunta no configurada.",
        )

    try:
        stage = schemas.CohabitationStage(account.cohabitation_stage)
    except (ValueError, KeyError):
        stage = schemas.CohabitationStage.PRE_COHABITATION
    eff_subcat_id = req.personal_subcategory_id

    if not eff_subcat_id:
        from backend.domain.schemas import categories as personal_cat_schemas

        # Determinar categoría y nombre objetivo según la etapa de convivencia
        if stage == schemas.CohabitationStage.PRE_COHABITATION:
            target_subcat_name = "Aportación Cuenta Conjunta (Ahorro Futuro)"
        else:
            target_subcat_name = "Aportación Cuenta Conjunta (Gastos del Hogar)"

        subcats = repo.get_subcategories()
        match = next(
            (s for s in subcats if target_subcat_name.lower() in s.name.lower() or "cuenta conjunta" in s.name.lower()),
            None
        )
        if match:
            eff_subcat_id = match.id
        else:
            # Buscar categoría padre adecuada
            cats = repo.get_categories()
            if stage == schemas.CohabitationStage.PRE_COHABITATION:
                parent_cat = next((c for c in cats if getattr(c, "type", "") == "ahorro" or "ahorro" in getattr(c, "name", "").lower()), None)
            else:
                parent_cat = next((c for c in cats if (getattr(c, "type", "") == "gasto" and "necesidad" in getattr(c, "name", "").lower()) or "necesidad" in getattr(c, "name", "").lower()), None)

            if not parent_cat:
                parent_cat = next((c for c in cats if getattr(c, "type", "") in ("ahorro", "gasto")), cats[0] if cats else None)

            if parent_cat:
                created_subcat = repo.create_subcategory(
                    personal_cat_schemas.SubcategoryCreate(
                        name=target_subcat_name,
                        category_id=parent_cat.id,
                    )
                )
                eff_subcat_id = created_subcat.id
            else:
                eff_subcat_id = subcats[0].id if subcats else 1

    c_uuid = str(uuid.uuid4())
    allocations_dict: Dict[str, float] = {}
    target_fund_name: Optional[str] = None

    if req.target_sinking_fund_id:
        target_fund = repo.get_joint_sinking_fund(req.target_sinking_fund_id)
        if target_fund:
            target_fund_name = target_fund.name
            target_fund.current_balance = round(float(target_fund.current_balance) + float(req.amount), 2)
            allocations_dict[str(target_fund.id)] = round(float(req.amount), 2)
    else:
        # Reparto ordinario de ahorro entre huchas activas según sus ponderaciones
        subcats = repo.get_joint_subcategories()
        needs_budget = sum(float(s.monthly_budget) for s in subcats) if subcats else 0.0
        funds = repo.get_joint_sinking_funds()
        funds_dicts = [
            {
                "id": f.id,
                "status": f.status,
                "current_balance": f.current_balance,
                "target_amount": f.target_amount,
                "monthly_target_amount": f.monthly_target_amount,
                "allocation_percentage": f.allocation_percentage,
            }
            for f in funds
        ]
        try:
            eff_strat = schemas.ContributionStrategy(account.contribution_strategy)
        except (ValueError, KeyError):
            eff_strat = schemas.ContributionStrategy.NOMINAL_TEMPLATE

        try:
            eff_split = schemas.SplitMode(account.split_mode)
        except (ValueError, KeyError):
            eff_split = schemas.SplitMode.EQUAL_50_50

        calc = calculate_monthly_contributions(
            cohabitation_stage=stage,
            contribution_strategy=eff_strat,
            split_mode=eff_split,
            needs_budget=needs_budget,
            sinking_funds=funds_dicts,
            member_a_income=account.member_a_reference_income,
            member_b_income=account.member_b_reference_income,
            member_a_contribution_pct=account.member_a_contribution_pct,
            member_b_contribution_pct=account.member_b_contribution_pct,
        )
        total_budget = float(calc.get("total_household_budget", 0.0))
        fund_allocs = calc.get("fund_allocations", {})
        if total_budget > 0 and fund_allocs:
            ratio = min(1.0, float(req.amount) / total_budget)
            for fid, target_amount in fund_allocs.items():
                part = round(float(target_amount) * ratio, 2)
                if part > 0:
                    f_obj = repo.get_joint_sinking_fund(int(fid))
                    if f_obj:
                        f_obj.current_balance = round(float(f_obj.current_balance) + part, 2)
                        allocations_dict[str(fid)] = part

    eff_subcat_id_int = eff_subcat_id if eff_subcat_id is not None else 1

    res_plan = prepare_assisted_contribution(
        month=req.month,
        contributor_profile=req.contributor_profile,
        contribution_amount=req.amount,
        cohabitation_stage=stage,
        personal_subcategory_id=eff_subcat_id_int,
        contribution_date=req.contribution_date,
        device_id=sync_service.local_device_id,
        contribution_uuid=c_uuid,
        target_sinking_fund_name=target_fund_name,
    )

    try:
        # 1. Asentar gasto en el perfil personal
        p_tx = res_plan["personal_transaction"]
        personal_tx = PersonalTransaction(
            date=p_tx["date"],
            amount=p_tx["amount"],
            description=p_tx["description"],
            subcategory_id=p_tx["subcategory_id"],
            joint_contribution_uuid=c_uuid,
        )
        db.add(personal_tx)
        db.flush()

        # 2. Asentar aportación en la cuenta conjunta con UUID y enlace a transacción personal
        eff_contrib_date = req.contribution_date or date.today()
        joint_contrib = schemas.JointMonthlyContributionCreate(
            uuid=c_uuid,
            month=req.month,
            contributor_profile=req.contributor_profile,
            amount=round(float(req.amount), 2),
            contribution_date=eff_contrib_date,
            personal_transaction_id=personal_tx.id,
            sinking_fund_allocations=json.dumps(allocations_dict) if allocations_dict else None,
        )
        repo.create_joint_contribution(joint_contrib)

        # 3. Emitir evento delta de aportación en outbox
        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.CONTRIBUTION,
            action=schemas.SyncAction.UPSERT,
            payload=res_plan["sync_event"]["payload"],
            origin_device_id=sync_service.local_device_id,
        )

        # 4. Emitir deltas SINKING_FUND (UPSERT) para huchas cuyo saldo creció
        for fid_str in allocations_dict:
            f_obj = repo.get_joint_sinking_fund(int(fid_str))
            if f_obj:
                sync_service.emit_event(
                    entity_type=schemas.SyncEntityType.SINKING_FUND,
                    action=schemas.SyncAction.UPSERT,
                    payload={
                        "name": f_obj.name,
                        "target_amount": f_obj.target_amount,
                        "current_balance": f_obj.current_balance,
                        "monthly_target_amount": f_obj.monthly_target_amount,
                        "allocation_percentage": f_obj.allocation_percentage,
                        "status": f_obj.status,
                        "priority": f_obj.priority,
                    },
                    origin_device_id=sync_service.local_device_id,
                )

        return {
            "success": True,
            "month": req.month,
            "amount": req.amount,
            "contributor_profile": req.contributor_profile.value,
            "message": f"Aportación de {req.amount:.2f} € asentada con éxito para {req.month}.",
        }
    except Exception as exc:
        db.rollback()
        logger.error("Error asentando aportación asistida (%s): %s", req.month, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error asentando aportación mensual: {exc}",
        )


@router.delete("/contributions/{contribution_id}")
def delete_joint_contribution(
    contribution_id: int,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """
    Elimina físicamente una aportación conjunta, revierte el saldo incrementado en huchas,
    elimina en cascada la transacción personal y emite tombstone de sincronización a la pareja.
    """
    del_info = repo.delete_joint_contribution(contribution_id)
    if not del_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aportación conjunta no encontrada.",
        )

    # Emitir tombstone CONTRIBUTION (DELETE)
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

    # Emitir SINKING_FUND (UPSERT) para huchas revertidas
    for fund_data in (del_info.get("reverted_funds") or {}).values():
        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.SINKING_FUND,
            action=schemas.SyncAction.UPSERT,
            payload=fund_data,
            origin_device_id=sync_service.local_device_id,
        )

    return {"success": True, "deleted_uuid": del_info["uuid"]}


# ==========================================
# 6. DIAGNÓSTICO DE SALUD Y RESUMEN ANUAL CONSOLIDADO
# ==========================================

@router.get("/health", response_model=schemas.JointHealthDiagnosticResponse)
def get_joint_health(repo: SQLiteRepository = Depends(get_repo)) -> schemas.JointHealthDiagnosticResponse:
    """Calcula la Tasa de Esfuerzo Familiar y el semáforo determinista de sostenibilidad."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta conjunta no configurada.",
        )

    # En Pre-Convivencia, los costes fijos de necesidades son 0.0 €
    if account.cohabitation_stage == schemas.CohabitationStage.PRE_COHABITATION.value:
        needs_budget = 0.0
    else:
        subcats = repo.get_joint_subcategories()
        needs_budget = sum(float(s.monthly_budget) for s in subcats)

    combined_income = account.member_a_reference_income + account.member_b_reference_income
    return evaluate_household_health(needs_budget, combined_income)


@router.get("/annual-summary", response_model=schemas.JointAnnualSummaryResponse)
def get_joint_annual_summary(
    year: int = Query(..., ge=2000, le=2100),
    repo: SQLiteRepository = Depends(get_repo),
) -> schemas.JointAnnualSummaryResponse:
    """
    Retorna el Resumen Anual consolidado del hogar.
    Prohíbe estrictamente comparativas individuales Member A vs Member B.
    """
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta conjunta no configurada.",
        )

    txs = repo.get_joint_transactions(year=year)
    contribs = repo.get_joint_contributions(year=year)
    funds = repo.get_joint_sinking_funds()

    combined_monthly_income = account.member_a_reference_income + account.member_b_reference_income
    annual_combined_income = combined_monthly_income * 12.0

    return calculate_joint_annual_summary(
        year=year,
        transactions=txs,
        contributions=contribs,
        sinking_funds=funds,
        annual_combined_income=annual_combined_income,
        account=account,
    )


# ==========================================
# 7. CONTROL DE SINCRONIZACIÓN ASÍNCRONA
# ==========================================

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


# ==========================================
# 8. EXPORTACIÓN Y DIAGNÓSTICO AVANZADO (FASE 7.2)
# ==========================================

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

