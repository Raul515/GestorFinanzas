"""
Servicio de aplicación para la Cuenta Conjunta y Economía del Hogar (Spec 017 - Fase 2C).
Centraliza la orquestación de reglas contables, emisión de payloads de sincronización,
liquidación de huchas con reparto proporcional y asientos asistidos mensuales.
"""

from datetime import date, datetime, timezone
import json
import logging
from typing import Any, Dict, Optional
import uuid

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.models import joint as joint_models
from backend.domain.models.transactions import Transaction as PersonalTransaction
from backend.domain.schemas import categories as personal_cat_schemas
from backend.domain.schemas import joint as schemas
from backend.domain.schemas import transactions as personal_tx_schemas
from backend.services.joint_accounting_service import (
    calculate_joint_annual_summary,
    calculate_member_shares,
    calculate_monthly_contributions,
    evaluate_household_health,
    prepare_assisted_contribution,
)
from backend.services.joint_sync_service import JointSyncService

logger = logging.getLogger(__name__)


class JointNotFoundError(LookupError):
    """Recurso de cuenta conjunta no encontrado."""


class JointValidationError(ValueError):
    """Regla de negocio o validación incumplida en cuenta conjunta."""


class JointForbiddenError(PermissionError):
    """Operación no permitida para el perfil local actual."""


def build_sinking_fund_sync_payload(fund: Any) -> Dict[str, Any]:
    """Construye el payload estándar de sincronización para una hucha de amortización."""
    return {
        "name": fund.name,
        "target_amount": fund.target_amount,
        "current_balance": fund.current_balance,
        "monthly_target_amount": fund.monthly_target_amount,
        "allocation_percentage": fund.allocation_percentage,
        "status": fund.status,
        "priority": fund.priority,
    }


def build_joint_transaction_sync_payload(repo: SQLiteRepository, tx: Any) -> Dict[str, Any]:
    """Construye el payload estándar de sincronización para una transacción común."""
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

    return {
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
    }


def _record_personal_sinking_fund_refund(
    repo: SQLiteRepository,
    fund_name: str,
    local_share: float,
    refund_date: date,
) -> None:
    """Asienta en el libro personal el reintegro correspondiente al cierre de una hucha."""
    try:
        cats = repo.get_categories()
        income_cat = next((c for c in cats if getattr(c, "type", "") == "ingreso"), None)
        if not income_cat:
            income_cat = repo.create_category(
                personal_cat_schemas.CategoryCreate(name="Ingresos Netos", type="ingreso")
            )
        if income_cat:
            subcats = repo.get_subcategories(category_id=income_cat.id)
            target_subcat = next(
                (
                    s
                    for s in subcats
                    if s.name in (
                        "Reintegros por Cierres de Huchas Conjuntas",
                        "Reintegro Hucha Conjunta",
                    )
                    or "reintegro" in s.name.lower()
                    or "cierre" in s.name.lower()
                ),
                None,
            )
            if not target_subcat:
                target_subcat = repo.create_subcategory(
                    personal_cat_schemas.SubcategoryCreate(
                        name="Reintegros por Cierres de Huchas Conjuntas",
                        category_id=income_cat.id,
                    )
                )
            repo.create_transaction(
                personal_tx_schemas.TransactionCreate(
                    date=refund_date,
                    amount=local_share,
                    description=f"Reintegro por cierre hucha '{fund_name}'",
                    subcategory_id=target_subcat.id,
                )
            )
    except Exception as exc:
        logger.warning("No se pudo asentar el reintegro personal para el miembro local: %s", exc)


def delete_joint_sinking_fund_with_refund(
    repo: SQLiteRepository,
    sync_service: JointSyncService,
    fund_id: int,
    reallocate_to_fund_id: Optional[int] = None,
    action_on_balance: Optional[str] = None,
    refund_personal_entry: bool = True,
) -> Dict[str, Any]:
    """Elimina una hucha aplicando el destino obligatorio sobre su saldo remanente."""
    fund = repo.get_joint_sinking_fund(fund_id)
    if not fund:
        raise JointNotFoundError("Hucha no encontrada.")

    fund_name = fund.name
    fund_balance = round(float(fund.current_balance or 0.0), 2)
    account = repo.get_joint_account()
    if not account:
        raise JointValidationError("Cuenta conjunta no configurada.")

    stage_str = account.cohabitation_stage.value if hasattr(account.cohabitation_stage, "value") else account.cohabitation_stage
    split_str = account.split_mode.value if hasattr(account.split_mode, "value") else account.split_mode

    share_a = 0.0
    share_b = 0.0
    if fund_balance > 0.0:
        if not action_on_balance:
            if reallocate_to_fund_id:
                action_on_balance = "REALLOCATE"
            else:
                raise JointValidationError(
                    f"Esta hucha tiene un saldo remanente de {fund_balance:,.2f} €. Debe seleccionar el destino obligatorio de los fondos (action_on_balance: REALLOCATE, RELEASE_TO_TREASURY o REFUND_MEMBERS)."
                )

        if action_on_balance == "REALLOCATE":
            if not reallocate_to_fund_id or reallocate_to_fund_id == fund_id:
                raise JointValidationError(
                    "Debe seleccionar una hucha receptora válida distinta de la que se elimina."
                )
            target_fund = repo.get_joint_sinking_fund(reallocate_to_fund_id)
            if not target_fund:
                raise JointNotFoundError("Hucha de destino no encontrada.")

            target_fund.current_balance = round(float(target_fund.current_balance) + fund_balance, 2)
            repo.db.commit()

            sync_service.emit_event(
                entity_type=schemas.SyncEntityType.SINKING_FUND,
                action=schemas.SyncAction.UPSERT,
                payload=build_sinking_fund_sync_payload(target_fund),
                origin_device_id=sync_service.local_device_id,
            )

        elif action_on_balance == "RELEASE_TO_TREASURY":
            if stage_str == "PRE_COHABITATION":
                raise JointValidationError(
                    "En modo pre-convivencia no existe tesorería general; debe reasignar a otra hucha o devolver a los miembros."
                )

        elif action_on_balance == "REFUND_MEMBERS":
            share_a, share_b = calculate_member_shares(
                total_amount=fund_balance,
                split_mode=split_str,
                member_a_income=float(getattr(account, "member_a_reference_income", 0.0) or 0.0),
                member_b_income=float(getattr(account, "member_b_reference_income", 0.0) or 0.0),
                member_a_pct=float(getattr(account, "member_a_contribution_pct", 50.0) or 50.0),
                member_b_pct=float(getattr(account, "member_b_contribution_pct", 50.0) or 50.0),
            )

            today_date = datetime.now().date()
            for profile_key, member_name, member_share in (
                ("MEMBER_A", account.member_a_name, share_a),
                ("MEMBER_B", account.member_b_name, share_b),
            ):
                if member_share <= 0:
                    continue
                tx = joint_models.JointTransaction(
                    uuid=str(uuid.uuid4()),
                    joint_account_id=account.id,
                    date=today_date,
                    amount=member_share,
                    description=f"Devolución liquidación hucha '{fund_name}' a {member_name}",
                    paid_by="COMMON",
                    created_by_profile=profile_key,
                    settlement_mechanism="COMMON_REIMBURSEMENT",
                    settlement_status="SETTLED",
                    settled_at=datetime.now(timezone.utc),
                )
                repo.db.add(tx)
                repo.db.commit()
                repo.db.refresh(tx)
                sync_service.emit_event(
                    entity_type=schemas.SyncEntityType.TRANSACTION,
                    action=schemas.SyncAction.UPSERT,
                    payload=build_joint_transaction_sync_payload(repo, tx),
                    origin_device_id=sync_service.local_device_id,
                )

            if refund_personal_entry:
                local_prof_str = account.local_profile.value if hasattr(account.local_profile, "value") else account.local_profile
                local_share = share_a if local_prof_str == "MEMBER_A" else share_b
                if local_share > 0:
                    _record_personal_sinking_fund_refund(repo, fund_name, local_share, today_date)

        else:
            raise JointValidationError(
                f"Acción no reconocida '{action_on_balance}'. Debe ser REALLOCATE, RELEASE_TO_TREASURY o REFUND_MEMBERS."
            )

    success = repo.delete_joint_sinking_fund(fund_id)
    if not success:
        raise JointValidationError("No se pudo eliminar la hucha.")

    delete_payload: Dict[str, Any] = {"name": fund_name}
    if action_on_balance:
        delete_payload["action_on_balance"] = action_on_balance
        if action_on_balance == "REFUND_MEMBERS":
            delete_payload["refund_shares"] = {
                "MEMBER_A": share_a,
                "MEMBER_B": share_b,
            }

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SINKING_FUND,
        action=schemas.SyncAction.DELETE,
        payload=delete_payload,
        origin_device_id=sync_service.local_device_id,
    )

    return {"deleted": True, "fund_id": fund_id, "action_on_balance": action_on_balance}


def _resolve_assisted_personal_subcategory_id(
    repo: SQLiteRepository,
    stage: schemas.CohabitationStage,
    requested_subcat_id: Optional[int],
) -> int:
    """Resuelve o crea la subcategoría personal adecuada para la aportación conjunta."""
    if requested_subcat_id:
        return requested_subcat_id

    if stage == schemas.CohabitationStage.PRE_COHABITATION:
        target_subcat_name = "Aportación Cuenta Conjunta (Ahorro Futuro)"
    else:
        target_subcat_name = "Aportación Cuenta Conjunta (Gastos del Hogar)"

    subcats = repo.get_subcategories()
    match = next(
        (s for s in subcats if target_subcat_name.lower() in s.name.lower() or "cuenta conjunta" in s.name.lower()),
        None,
    )
    if match:
        return match.id

    cats = repo.get_categories()
    if stage == schemas.CohabitationStage.PRE_COHABITATION:
        parent_cat = next(
            (c for c in cats if getattr(c, "type", "") == "ahorro" or "ahorro" in getattr(c, "name", "").lower()),
            None,
        )
    else:
        parent_cat = next(
            (
                c
                for c in cats
                if (getattr(c, "type", "") == "gasto" and "necesidad" in getattr(c, "name", "").lower())
                or "necesidad" in getattr(c, "name", "").lower()
            ),
            None,
        )

    if not parent_cat:
        parent_cat = next((c for c in cats if getattr(c, "type", "") in ("ahorro", "gasto")), cats[0] if cats else None)

    if parent_cat:
        created_subcat = repo.create_subcategory(
            personal_cat_schemas.SubcategoryCreate(
                name=target_subcat_name,
                category_id=parent_cat.id,
            )
        )
        return created_subcat.id

    return subcats[0].id if subcats else 1


def record_assisted_contribution_flow(
    repo: SQLiteRepository,
    sync_service: JointSyncService,
    *,
    month: str,
    amount: float,
    contributor_profile: schemas.ProfileIdentifier,
    personal_subcategory_id: Optional[int] = None,
    contribution_date: Optional[date] = None,
    target_sinking_fund_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Ejecuta el asiento asistido de aportación mensual y sus eventos de sincronización."""
    account = repo.get_joint_account()
    if not account:
        raise JointValidationError("Cuenta conjunta no configurada.")

    req_profile_str = contributor_profile.value if hasattr(contributor_profile, "value") else str(contributor_profile)
    acc_local_str = account.local_profile.value if hasattr(account.local_profile, "value") else account.local_profile
    if req_profile_str != acc_local_str:
        raise JointForbiddenError(
            f"Solo puedes asentar aportaciones desde tu propio perfil local ({acc_local_str}). No es posible debitar la cuenta personal de tu pareja."
        )

    try:
        stage = schemas.CohabitationStage(account.cohabitation_stage)
    except (ValueError, KeyError):
        stage = schemas.CohabitationStage.PRE_COHABITATION

    eff_subcat_id = _resolve_assisted_personal_subcategory_id(repo, stage, personal_subcategory_id)
    c_uuid = str(uuid.uuid4())
    allocations_dict: Dict[str, float] = {}
    target_fund_name: Optional[str] = None

    if target_sinking_fund_id:
        target_fund = repo.get_joint_sinking_fund(target_sinking_fund_id)
        if target_fund:
            target_fund_name = target_fund.name
            target_fund.current_balance = round(float(target_fund.current_balance) + float(amount), 2)
            allocations_dict[str(target_fund.id)] = round(float(amount), 2)
    else:
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
            custom_total_monthly_budget=getattr(account, "custom_total_monthly_budget", 0.0),
        )
        total_budget = float(calc.get("total_household_budget", 0.0))
        fund_allocs = calc.get("fund_allocations", {})
        if total_budget > 0 and fund_allocs:
            ratio = min(1.0, float(amount) / total_budget)
            for fid, target_amount in fund_allocs.items():
                part = round(float(target_amount) * ratio, 2)
                if part > 0:
                    f_obj = repo.get_joint_sinking_fund(int(fid))
                    if f_obj:
                        f_obj.current_balance = round(float(f_obj.current_balance) + part, 2)
                        allocations_dict[str(fid)] = part

    res_plan = prepare_assisted_contribution(
        month=month,
        contributor_profile=contributor_profile,
        contribution_amount=amount,
        cohabitation_stage=stage,
        personal_subcategory_id=eff_subcat_id,
        contribution_date=contribution_date,
        device_id=sync_service.local_device_id,
        contribution_uuid=c_uuid,
        target_sinking_fund_name=target_fund_name,
    )

    try:
        p_tx = res_plan["personal_transaction"]
        personal_tx = PersonalTransaction(
            date=p_tx["date"],
            amount=p_tx["amount"],
            description=p_tx["description"],
            subcategory_id=p_tx["subcategory_id"],
            joint_contribution_uuid=c_uuid,
        )
        repo.db.add(personal_tx)
        repo.db.flush()

        eff_contrib_date = contribution_date or date.today()
        joint_contrib = schemas.JointMonthlyContributionCreate(
            uuid=c_uuid,
            month=month,
            contributor_profile=contributor_profile,
            amount=round(float(amount), 2),
            contribution_date=eff_contrib_date,
            personal_transaction_id=personal_tx.id,
            sinking_fund_allocations=json.dumps(allocations_dict) if allocations_dict else None,
        )
        repo.create_joint_contribution(joint_contrib)

        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.CONTRIBUTION,
            action=schemas.SyncAction.UPSERT,
            payload=res_plan["sync_event"]["payload"],
            origin_device_id=sync_service.local_device_id,
        )

        for fid_str in allocations_dict:
            f_obj = repo.get_joint_sinking_fund(int(fid_str))
            if f_obj:
                sync_service.emit_event(
                    entity_type=schemas.SyncEntityType.SINKING_FUND,
                    action=schemas.SyncAction.UPSERT,
                    payload=build_sinking_fund_sync_payload(f_obj),
                    origin_device_id=sync_service.local_device_id,
                )

        return {
            "success": True,
            "month": month,
            "amount": amount,
            "contributor_profile": contributor_profile.value,
            "message": f"Aportación de {amount:.2f} € asentada con éxito para {month}.",
        }
    except Exception as exc:
        repo.db.rollback()
        logger.error("Error asentando aportación asistida (%s): %s", month, exc)
        raise RuntimeError(f"Error asentando aportación mensual: {exc}") from exc


def get_joint_contribution_calculation_summary(repo: SQLiteRepository) -> Dict[str, Any]:
    """Calcula las cuotas mensuales de aportación por miembro para la cuenta conjunta."""
    account = repo.get_joint_account()
    if not account:
        raise JointNotFoundError("Cuenta conjunta no configurada.")

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
        custom_total_monthly_budget=getattr(account, "custom_total_monthly_budget", 0.0),
    )
    calc["local_profile"] = account.local_profile
    calc["remote_profile"] = account.remote_profile
    calc["member_a_name"] = account.member_a_name
    calc["member_b_name"] = account.member_b_name
    return calc


def get_joint_health_diagnostic(repo: SQLiteRepository) -> schemas.JointHealthDiagnosticResponse:
    """Calcula la Tasa de Esfuerzo Familiar y el semáforo determinista de sostenibilidad."""
    account = repo.get_joint_account()
    if not account:
        raise JointNotFoundError("Cuenta conjunta no configurada.")

    if account.cohabitation_stage == schemas.CohabitationStage.PRE_COHABITATION.value:
        needs_budget = 0.0
    else:
        subcats = repo.get_joint_subcategories()
        needs_budget = sum(float(s.monthly_budget) for s in subcats)

    combined_income = account.member_a_reference_income + account.member_b_reference_income
    return evaluate_household_health(needs_budget, combined_income)


def get_joint_annual_summary_report(
    repo: SQLiteRepository,
    year: int,
) -> schemas.JointAnnualSummaryResponse:
    """Retorna el resumen anual consolidado del hogar."""
    account = repo.get_joint_account()
    if not account:
        raise JointNotFoundError("Cuenta conjunta no configurada.")

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
