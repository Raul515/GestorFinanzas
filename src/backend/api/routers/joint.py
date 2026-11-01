"""
Router REST para el espacio conjunto del hogar y finanzas compartidas (Spec 010).
Proporciona endpoints fuertemente tipados con observabilidad estructurada, validaciones Pydantic v2
y control de transacciones para onboarding, configuración, huchas, aportaciones y sincronización.
"""

from datetime import date, datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.componentes.sqlite_db import get_db
from backend.domain.models import transactions as personal_trans_model
from backend.domain.models.joint import JointAppliedSyncEvent
from backend.domain.schemas import joint as schemas
from backend.services.joint_accounting_service import (
    calculate_joint_annual_summary,
    evaluate_household_health,
    prepare_assisted_contribution,
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


# ==========================================
# 1. ESTADO DE CONFIGURACIÓN Y ONBOARDING
# ==========================================

@router.get("/status", response_model=schemas.JointStatusResponse)
def get_joint_status(repo: SQLiteRepository = Depends(get_repo)):
    """Retorna si la cuenta conjunta está configurada o si el usuario se encuentra en Estado Cero."""
    account = repo.get_joint_account()
    if not account:
        return schemas.JointStatusResponse(is_configured=False)

    return schemas.JointStatusResponse(
        is_configured=True,
        household_name=account.household_name,
        cohabitation_stage=schemas.CohabitationStage(account.cohabitation_stage),
        local_profile=schemas.ProfileIdentifier(account.local_profile),
    )


@router.post("/setup", response_model=schemas.JointAccountResponse, status_code=status.HTTP_201_CREATED)
def setup_joint_account(
    setup_req: schemas.JointAccountSetupRequest,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
):
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
        return account
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/account", response_model=schemas.JointAccountResponse)
def get_joint_account(repo: SQLiteRepository = Depends(get_repo)):
    """Consulta la configuración y parámetros del hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La cuenta conjunta aún no ha sido configurada en este dispositivo.",
        )
    return account


@router.put("/account", response_model=schemas.JointAccountResponse)
def update_joint_account(
    update_req: schemas.JointAccountUpdate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
):
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
    return account


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
):
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

    setup_req = schemas.JointAccountSetupRequest(
        household_name=invitation["household_name"],
        cohabitation_stage=schemas.CohabitationStage(stage_val) if hasattr(schemas.CohabitationStage, stage_val) else schemas.CohabitationStage.PRE_COHABITATION,
        contribution_strategy=schemas.ContributionStrategy(strategy_val) if hasattr(schemas.ContributionStrategy, strategy_val) else schemas.ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=schemas.SplitMode(split_val) if hasattr(schemas.SplitMode, split_val) else schemas.SplitMode.EQUAL_50_50,
        member_a_reference_income=float(invitation.get("member_a_reference_income", 0.0)),
        member_b_reference_income=float(invitation.get("member_b_reference_income", 0.0)),
        member_a_contribution_pct=50.0,
        member_b_contribution_pct=50.0,
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

    return account


@router.post("/reset")
def reset_joint_account(
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """
    Purga la cuenta conjunta completa y limpia las carpetas de sincronización,
    devolviendo el sistema al Estado Cero de monousuario.
    """
    repo.reset_joint_account()
    sync_service.clear_sync_folders()
    logger.info("Cuenta conjunta reseteada al Estado Cero exitosamente.")
    return {"status": "success", "message": "Cuenta conjunta purgada y restablecida al Estado Cero."}



# ==========================================
# 2. CATEGORÍAS Y SUBCATEGORÍAS COMUNES
# ==========================================

@router.get("/categories", response_model=List[schemas.JointCategoryResponse])
def get_joint_categories(repo: SQLiteRepository = Depends(get_repo)):
    """Obtiene el catálogo de conceptos comunes (sin ocio)."""
    return repo.get_joint_categories()


@router.get("/subcategories", response_model=List[schemas.JointSubcategoryResponse])
def get_joint_subcategories(
    category_id: Optional[int] = None,
    repo: SQLiteRepository = Depends(get_repo),
):
    """Obtiene las subcategorías de necesidades del hogar."""
    return repo.get_joint_subcategories(category_id=category_id)


# ==========================================
# 3. HUCHAS DE AMORTIZACIÓN (SINKING FUNDS)
# ==========================================

@router.get("/sinking-funds", response_model=List[schemas.JointSinkingFundResponse])
def get_joint_sinking_funds(
    fund_status: Optional[str] = Query(default=None, alias="status"),
    repo: SQLiteRepository = Depends(get_repo),
):
    """Consulta las huchas de amortización del hogar."""
    return repo.get_joint_sinking_funds(status=fund_status)


@router.post("/sinking-funds", response_model=schemas.JointSinkingFundResponse, status_code=status.HTTP_201_CREATED)
def create_joint_sinking_fund(
    fund_create: schemas.JointSinkingFundCreate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
):
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
    return fund


@router.put("/sinking-funds/{fund_id}", response_model=schemas.JointSinkingFundResponse)
def update_joint_sinking_fund(
    fund_id: int,
    fund_update: schemas.JointSinkingFundUpdate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
):
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
    return fund


@router.delete("/sinking-funds/{fund_id}")
def delete_joint_sinking_fund(
    fund_id: int,
    reallocate_to_fund_id: Optional[int] = Query(default=None),
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
):
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
    return {"deleted": True, "fund_id": fund_id}


# ==========================================
# 4. TRANSACCIONES Y GASTOS DEL HOGAR
# ==========================================

@router.get("/transactions", response_model=List[schemas.JointTransactionResponse])
def get_joint_transactions(
    year: Optional[int] = None,
    month: Optional[str] = None,
    repo: SQLiteRepository = Depends(get_repo),
):
    """Obtiene transacciones de necesidades o cargos a huchas comunes."""
    return repo.get_joint_transactions(year=year, month=month)


@router.post("/transactions", response_model=schemas.JointTransactionResponse, status_code=status.HTTP_201_CREATED)
def create_joint_transaction(
    tx_create: schemas.JointTransactionCreate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
):
    """Registra un nuevo gasto común del hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cuenta conjunta no configurada.",
        )

    tx = repo.create_joint_transaction(tx_create)

    # Emitir delta para sync
    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.TRANSACTION,
        action=schemas.SyncAction.UPSERT,
        payload={
            "uuid": tx.uuid,
            "date": tx.date.isoformat(),
            "amount": tx.amount,
            "description": tx.description,
            "joint_subcategory_id": tx.joint_subcategory_id,
            "joint_sinking_fund_id": tx.joint_sinking_fund_id,
            "created_by_profile": tx.created_by_profile,
        },
        origin_device_id=sync_service.local_device_id,
    )
    return tx


@router.delete("/transactions/{transaction_id}")
def delete_joint_transaction(
    transaction_id: int,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
):
    """Elimina un gasto común y emite el tombstone correspondiente a Syncthing."""
    tx_uuid = repo.delete_joint_transaction(transaction_id)
    if not tx_uuid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transacción no encontrada.")

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.TRANSACTION,
        action=schemas.SyncAction.DELETE,
        payload={"uuid": tx_uuid},
        origin_device_id=sync_service.local_device_id,
    )
    return {"deleted": True, "uuid": tx_uuid}


# ==========================================
# 5. APORTACIONES MENSUALES Y FLUJO ASISTIDO
# ==========================================

@router.get("/contributions", response_model=List[schemas.JointMonthlyContributionResponse])
def get_joint_contributions(
    year: Optional[int] = None,
    month: Optional[str] = None,
    repo: SQLiteRepository = Depends(get_repo),
):
    """Obtiene el historial de aportaciones realizadas por ambos miembros."""
    return repo.get_joint_contributions(year=year, month=month)


@router.post("/contributions/asentar-asistida", status_code=status.HTTP_201_CREATED)
def record_assisted_contribution(
    req: AssistedContributionRequest,
    db: Session = Depends(get_db),
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
):
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

    eff_subcat_id = req.personal_subcategory_id
    if not eff_subcat_id:
        # Buscar por defecto la subcategoría personal adecuada
        subcats = repo.get_subcategories()
        # Buscar "Aportación a Cuenta Conjunta" o "Ahorro Futuro Común"
        target_name = "Aportación a Cuenta Conjunta"
        match = next((s for s in subcats if target_name.lower() in s.name.lower()), None)
        if match:
            eff_subcat_id = match.id
        elif subcats:
            eff_subcat_id = subcats[0].id
        else:
            eff_subcat_id = 1

    stage = schemas.CohabitationStage(account.cohabitation_stage)
    res_plan = prepare_assisted_contribution(
        month=req.month,
        contributor_profile=req.contributor_profile,
        contribution_amount=req.amount,
        cohabitation_stage=stage,
        personal_subcategory_id=eff_subcat_id,
        contribution_date=req.contribution_date,
        device_id=sync_service.local_device_id,
    )

    try:
        # 1. Asentar gasto en el perfil personal
        p_tx = res_plan["personal_transaction"]
        personal_tx = personal_trans_model.Transaction(
            date=p_tx["date"],
            amount=p_tx["amount"],
            description=p_tx["description"],
            subcategory_id=p_tx["subcategory_id"],
        )
        db.add(personal_tx)

        # 2. Asentar aportación en la cuenta conjunta
        j_cb = res_plan["joint_contribution"]
        joint_contrib = schemas.JointMonthlyContributionCreate(
            month=j_cb["month"],
            contributor_profile=j_cb["contributor_profile"],
            amount=j_cb["amount"],
            contribution_date=j_cb["contribution_date"],
        )
        repo.create_joint_contribution(joint_contrib)

        # 3. Emitir evento delta en outbox
        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.CONTRIBUTION,
            action=schemas.SyncAction.UPSERT,
            payload=res_plan["sync_event"]["payload"],
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


# ==========================================
# 6. DIAGNÓSTICO DE SALUD Y RESUMEN ANUAL CONSOLIDADO
# ==========================================

@router.get("/health", response_model=schemas.JointHealthDiagnosticResponse)
def get_joint_health(repo: SQLiteRepository = Depends(get_repo)):
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

    combined_income = float(account.member_a_reference_income) + float(account.member_b_reference_income)
    return evaluate_household_health(needs_budget, combined_income)


@router.get("/annual-summary", response_model=schemas.JointAnnualSummaryResponse)
def get_joint_annual_summary(
    year: int = Query(..., ge=2000, le=2100),
    repo: SQLiteRepository = Depends(get_repo),
):
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

    combined_monthly_income = float(account.member_a_reference_income) + float(account.member_b_reference_income)
    annual_combined_income = combined_monthly_income * 12.0

    return calculate_joint_annual_summary(
        year=year,
        transactions=txs,
        contributions=contribs,
        sinking_funds=funds,
        annual_combined_income=annual_combined_income,
    )


# ==========================================
# 7. CONTROL DE SINCRONIZACIÓN ASÍNCRONA
# ==========================================

@router.post("/sync/process-inbox")
def trigger_process_inbox(
    db: Session = Depends(get_db),
    sync_service: JointSyncService = Depends(get_sync_service),
):
    """Dispara el procesamiento de los ficheros delta depositados por Syncthing en sync/inbox/."""
    result = sync_service.process_inbox(db)
    return {"status": "ok", "summary": result}


@router.get("/sync/status")
def get_sync_status(
    db: Session = Depends(get_db),
    sync_service: JointSyncService = Depends(get_sync_service),
):
    """Retorna las métricas y estado del buzón de sincronización."""
    return sync_service.get_sync_status(db)
