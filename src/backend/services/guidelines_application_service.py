"""
Servicio de Aplicación para Pautas Deterministas y Compensación Presupuestaria (Spec 008 / Spec 017).
Orquesta la persistencia de estrategias aplicadas, transacciones vinculadas,
barrido de fin de mes y compensaciones de déficit desacoplado del router HTTP.
"""

import calendar
import datetime
import json
import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.domain.constants import (
    CategoryBlock,
    classify_category_block,
    is_emergency_fund_subcategory,
)
from backend.domain.models import (
    budgets as pres_models,
    categories as cat_models,
    emergency_fund as ef_models,
    guidelines as guideline_models,
    transactions as tx_models,
)
from backend.domain.schemas.guidelines import (
    CompensateDeficitRequest,
    CompensateDeficitResponse,
    DeficitActionType,
    MonthlyGuidelineReport,
    StrategyApplyRequest,
    StrategyApplyResponse,
    StrategyRevertRequest,
    StrategyRevertResponse,
    SweepRequest,
    SweepResponse,
)
from backend.services.guidelines_service import evaluate_monthly_guidelines
from backend.services.safety_guard import resolve_monthly_needs, sync_fund_state

logger = logging.getLogger(__name__)


def resolve_tx_date(month_key: str) -> datetime.date:
    """Calcula una fecha válida dentro del mes indicado."""
    try:
        parts = month_key.split("-")
        year, month = int(parts[0]), int(parts[1])
        today = datetime.date.today()
        if today.year == year and today.month == month:
            return today
        return datetime.date(year, month, 28)
    except Exception:
        return datetime.date.today()


def get_next_month_key(month_key: str) -> str:
    """Calcula la clave YYYY-MM del mes inmediato posterior."""
    try:
        parts = month_key.split("-")
        y, m = int(parts[0]), int(parts[1])
        if m == 12:
            return f"{y + 1}-01"
        return f"{y}-{m + 1:02d}"
    except Exception:
        return month_key


def _month_date_bounds(month_key: str) -> Optional[Tuple[datetime.date, datetime.date]]:
    """Retorna (primer_dia, ultimo_dia) para una clave YYYY-MM válida."""
    try:
        y_str, m_str = month_key.split("-")
        y, m = int(y_str), int(m_str)
        last_day = calendar.monthrange(y, m)[1]
        return datetime.date(y, m, 1), datetime.date(y, m, last_day)
    except Exception:
        return None


def _extract_split_config(
    db: Session,
    applied_record: guideline_models.AppliedGuidelineStrategy,
    include_names: bool = False,
) -> Optional[Dict[str, Any]]:
    """Lee o reconstruye la configuración de reparto (savings/wants) de una estrategia aplicada."""
    raw_cfg = getattr(applied_record, "split_config", None)
    if raw_cfg:
        try:
            return json.loads(raw_cfg)
        except Exception as err:
            logger.warning("Error deserializando split_config: %s", err)

    if not applied_record.transactions:
        return None

    s_items = []
    w_items = []
    for tx in applied_record.transactions:
        sub = (
            db.query(cat_models.Subcategory)
            .filter(cat_models.Subcategory.id == tx.subcategory_id)
            .first()
        )
        is_savings = bool(
            sub and sub.category and classify_category_block(sub.category) == CategoryBlock.SAVINGS
        )
        item_data: Dict[str, Any] = {"subcategory_id": tx.subcategory_id, "amount": tx.amount}
        if include_names:
            item_data["name"] = sub.name if sub else f"Subcat {tx.subcategory_id}"
        if is_savings:
            s_items.append(item_data)
        else:
            w_items.append(item_data)
    return {"savings": s_items, "wants": w_items}


def _apply_emergency_fund_delta(db: Session, delta: float) -> Tuple[bool, Optional[float]]:
    """Actualiza el saldo del Fondo de Emergencia con redondeo consistente a 2 decimales."""
    ef = db.query(ef_models.EmergencyFund).first()
    if not ef:
        return False, None
    ef.current_balance = round(max(0.0, float(ef.current_balance or 0.0) + float(delta)), 2)
    if ef.target_amount and ef.target_amount > 0 and ef.current_balance >= ef.target_amount:
        ef.is_completed = True
    return True, ef.current_balance


def _decrement_budget_with_base_fallback(
    db: Session, target_month: str, subcategory_id: int, delta_amount: float
) -> float:
    """Reduce el presupuesto mensual de una subcategoría usando BASE como respaldo si no existe fila."""
    b = (
        db.query(pres_models.MonthlyBudget)
        .filter(
            pres_models.MonthlyBudget.month == target_month,
            pres_models.MonthlyBudget.subcategory_id == subcategory_id,
        )
        .first()
    )
    if b:
        b.amount = round(max(0.0, float(b.amount) - float(delta_amount)), 2)
        return b.amount

    base_b = (
        db.query(pres_models.MonthlyBudget)
        .filter(
            pres_models.MonthlyBudget.month == "BASE",
            pres_models.MonthlyBudget.subcategory_id == subcategory_id,
        )
        .first()
    )
    base_val = float(base_b.amount) if base_b else 0.0
    new_amount = round(max(0.0, base_val - float(delta_amount)), 2)
    db.add(
        pres_models.MonthlyBudget(
            month=target_month,
            subcategory_id=subcategory_id,
            amount=new_amount,
        )
    )
    return new_amount


def get_monthly_guidelines_report(
    db: Session,
    month_key: str,
    month_name: str,
    real_income: float,
    budget_income: float,
    real_needs: float,
    real_wants: float,
    real_savings: float,
    safety_status: Optional[Dict[str, Any]] = None,
) -> MonthlyGuidelineReport:
    """Evalúa las pautas mensuales resolviendo estrategias aplicadas y huérfanas en BD."""
    bounds = _month_date_bounds(month_key)
    applied_records = (
        db.query(guideline_models.AppliedGuidelineStrategy)
        .filter(guideline_models.AppliedGuidelineStrategy.month == month_key)
        .all()
    )
    applied_strategies_map: Dict[str, Any] = {}
    for applied_record in applied_records:
        linked_txs = (
            db.query(tx_models.Transaction)
            .filter(tx_models.Transaction.applied_strategy_id == applied_record.id)
            .all()
        )
        pauta_q = db.query(tx_models.Transaction).filter(
            tx_models.Transaction.description.like(f"[Pauta {applied_record.strategy_type}%")
        )
        if bounds:
            pauta_q = pauta_q.filter(tx_models.Transaction.date.between(bounds[0], bounds[1]))
        else:
            pauta_q = pauta_q.filter(tx_models.Transaction.date.like(f"{month_key}%"))
        pauta_txs = pauta_q.all()

        if not linked_txs and not pauta_txs:
            logger.info(
                "Estrategia huérfana %s detectada sin transacciones en mes %s; limpiando registro.",
                applied_record.scenario_type,
                month_key,
            )
            db.delete(applied_record)
            db.commit()
        else:
            split_cfg = _extract_split_config(db, applied_record, include_names=True)
            applied_strategies_map[applied_record.scenario_type] = {
                "month": applied_record.month,
                "scenario_type": applied_record.scenario_type,
                "strategy_type": applied_record.strategy_type,
                "is_partial": applied_record.is_partial,
                "allocated_amount": applied_record.allocated_amount,
                "cushion_amount": applied_record.cushion_amount,
                "split_config": split_cfg,
            }

    if not applied_strategies_map:
        fallback_q = db.query(tx_models.Transaction).filter(
            tx_models.Transaction.description.like("[Pauta %")
        )
        if bounds:
            fallback_q = fallback_q.filter(tx_models.Transaction.date.between(bounds[0], bounds[1]))
        else:
            fallback_q = fallback_q.filter(tx_models.Transaction.date.like(f"{month_key}%"))
        pauta_txs = fallback_q.all()
        if pauta_txs:
            total_alloc = sum(t.amount for t in pauta_txs)
            strat_name = "HYBRID_80_20"
            scen_name = "NEEDS_SURPLUS"
            for t in pauta_txs:
                if "FIRE" in t.description:
                    strat_name = "FIRE"
                    break
                if "SINKING" in t.description:
                    strat_name = "SINKING_FUND"
                    break
                if "EXTRAORDINARY" in t.description or "Bonus" in t.description:
                    strat_name = "EXTRAORDINARY_INCOME"
                    scen_name = "EXTRAORDINARY_INCOME"
                    break
            applied_strategies_map[scen_name] = {
                "month": month_key,
                "scenario_type": scen_name,
                "strategy_type": strat_name,
                "is_partial": False,
                "allocated_amount": total_alloc,
                "cushion_amount": 0.0,
            }

    applied_strategy_dict = applied_strategies_map.get("NEEDS_SURPLUS") or (
        next(iter(applied_strategies_map.values())) if applied_strategies_map else None
    )

    report = evaluate_monthly_guidelines(
        month_key=month_key,
        month_name=month_name,
        real_income=real_income,
        budget_income=budget_income,
        real_needs=real_needs,
        real_wants=real_wants,
        real_savings=real_savings,
        safety_status=safety_status,
        applied_strategy=applied_strategy_dict,
        applied_strategies=applied_strategies_map,
    )
    report.applied_strategy = applied_strategy_dict
    report.applied_strategies = applied_strategies_map
    return report


def apply_guideline_strategy(db: Session, request: StrategyApplyRequest) -> StrategyApplyResponse:
    """Ejecuta atómicamente una estrategia de asignación de capital y sincroniza el Fondo de Emergencia."""
    tx_date = resolve_tx_date(request.month_key)
    created_txs = 0
    ef_updated = False
    new_ef_balance = None

    total_allocated = sum(item.amount for item in request.savings_allocations if item.amount > 0) + sum(
        item.amount for item in request.wants_allocations if item.amount > 0
    )
    cushion = total_allocated if request.is_partial else 0.0
    target_scenario = "EXTRAORDINARY_INCOME" if request.strategy_type == "EXTRAORDINARY_INCOME" else "NEEDS_SURPLUS"

    applied_entry = (
        db.query(guideline_models.AppliedGuidelineStrategy)
        .filter(
            guideline_models.AppliedGuidelineStrategy.month == request.month_key,
            guideline_models.AppliedGuidelineStrategy.scenario_type == target_scenario,
        )
        .first()
    )
    split_dict = {
        "savings": [
            {"subcategory_id": item.subcategory_id, "amount": item.amount, "percentage": item.percentage}
            for item in request.savings_allocations
            if item.amount > 0
        ],
        "wants": [
            {"subcategory_id": item.subcategory_id, "amount": item.amount, "percentage": item.percentage}
            for item in request.wants_allocations
            if item.amount > 0
        ],
    }
    split_json = json.dumps(split_dict)

    if applied_entry:
        applied_entry.strategy_type = request.strategy_type
        applied_entry.is_partial = request.is_partial
        applied_entry.allocated_amount = total_allocated
        applied_entry.cushion_amount = cushion
        applied_entry.split_config = split_json
    else:
        applied_entry = guideline_models.AppliedGuidelineStrategy(
            month=request.month_key,
            scenario_type=target_scenario,
            strategy_type=request.strategy_type,
            is_partial=request.is_partial,
            allocated_amount=total_allocated,
            cushion_amount=cushion,
            split_config=split_json,
        )
        db.add(applied_entry)
    db.flush()

    desc_suffix = "Bonus Extraordinario" if target_scenario == "EXTRAORDINARY_INCOME" else "Asignación de Excedente"

    for item in request.savings_allocations:
        if item.amount <= 0:
            continue
        sub = db.query(cat_models.Subcategory).filter(cat_models.Subcategory.id == item.subcategory_id).first()
        if sub and is_emergency_fund_subcategory(sub):
            updated, bal = _apply_emergency_fund_delta(db, item.amount)
            if updated:
                ef_updated = True
                new_ef_balance = bal

        db.add(
            tx_models.Transaction(
                date=tx_date,
                subcategory_id=item.subcategory_id,
                amount=item.amount,
                description=f"[Pauta {request.strategy_type}] {desc_suffix}",
                applied_strategy_id=applied_entry.id,
            )
        )
        created_txs += 1

    for item in request.wants_allocations:
        if item.amount <= 0:
            continue
        db.add(
            tx_models.Transaction(
                date=tx_date,
                subcategory_id=item.subcategory_id,
                amount=item.amount,
                description=f"[Pauta {request.strategy_type}] {desc_suffix} a Deseos",
                applied_strategy_id=applied_entry.id,
            )
        )
        created_txs += 1

    db.commit()
    logger.info(
        "Estrategia %s aplicada con éxito en mes %s: %d transacciones creadas vinculadas a ID %s.",
        request.strategy_type,
        request.month_key,
        created_txs,
        applied_entry.id,
    )
    return StrategyApplyResponse(
        success=True,
        message=f"Estrategia {request.strategy_type} aplicada exitosamente.",
        month_key=request.month_key,
        transactions_created=created_txs,
        budgets_updated=0,
        emergency_fund_updated=ef_updated,
        new_emergency_fund_balance=new_ef_balance,
    )


def revert_guideline_strategy(db: Session, request: StrategyRevertRequest) -> StrategyRevertResponse:
    """Revierte atómicamente una estrategia aplicada, sus transacciones y su efecto en el Fondo de Emergencia."""
    applied_entry = (
        db.query(guideline_models.AppliedGuidelineStrategy)
        .filter(
            guideline_models.AppliedGuidelineStrategy.month == request.month_key,
            guideline_models.AppliedGuidelineStrategy.scenario_type == request.scenario_type,
        )
        .first()
    )
    if not applied_entry:
        return StrategyRevertResponse(
            success=False,
            message=f"No existe ninguna estrategia {request.scenario_type} aplicada en el mes {request.month_key}.",
            month_key=request.month_key,
            transactions_reverted=0,
            emergency_fund_reverted=0.0,
        )

    linked_txs = (
        db.query(tx_models.Transaction)
        .filter(tx_models.Transaction.applied_strategy_id == applied_entry.id)
        .all()
    )

    ef_reverted = 0.0
    fund = db.query(ef_models.EmergencyFund).first()
    sub_ef = (
        db.query(cat_models.Subcategory)
        .filter(cat_models.Subcategory.name.ilike("%fondo de emergencia%"))
        .first()
    )
    ef_sub_id = sub_ef.id if sub_ef else None

    for tx in linked_txs:
        if fund and ef_sub_id and tx.subcategory_id == ef_sub_id:
            fund.current_balance = round(max(0.0, float(fund.current_balance) - float(tx.amount)), 2)
            ef_reverted = round(ef_reverted + float(tx.amount), 2)
        db.delete(tx)

    reverted_count = len(linked_txs)
    db.delete(applied_entry)
    db.commit()

    if fund and ef_reverted > 0:
        monthly_needs = resolve_monthly_needs(db, request.month_key)
        sync_fund_state(fund, monthly_needs)
        db.commit()

    logger.info(
        "Estrategia en mes %s revertida exitosamente: %d transacciones eliminadas, %.2f € descontados del fondo de emergencia.",
        request.month_key,
        reverted_count,
        ef_reverted,
    )
    return StrategyRevertResponse(
        success=True,
        message="Estrategia revertida exitosamente. El excedente vuelve a estar disponible.",
        month_key=request.month_key,
        transactions_reverted=reverted_count,
        emergency_fund_reverted=ef_reverted,
    )


def sweep_month_surplus(db: Session, request: SweepRequest) -> SweepResponse:
    """Ejecuta el barrido de fin de mes (INHERIT_STRATEGY o DEFAULT_SAVINGS)."""
    tx_date = resolve_tx_date(request.month_key)
    ef_updated = False
    new_ef_balance = None
    created_txs = 0

    applied_entry = (
        db.query(guideline_models.AppliedGuidelineStrategy)
        .filter(
            guideline_models.AppliedGuidelineStrategy.month == request.month_key,
            guideline_models.AppliedGuidelineStrategy.cushion_amount > 0,
        )
        .first()
    ) or (
        db.query(guideline_models.AppliedGuidelineStrategy)
        .filter(guideline_models.AppliedGuidelineStrategy.month == request.month_key)
        .first()
    )

    mode_applied = request.mode

    if mode_applied == "INHERIT_STRATEGY" and applied_entry:
        split_cfg = _extract_split_config(db, applied_entry, include_names=False)
        if split_cfg:
            orig_savings = split_cfg.get("savings", [])
            orig_wants = split_cfg.get("wants", [])
            total_orig = sum(float(x.get("amount", 0.0)) for x in orig_savings + orig_wants)

            if total_orig > 0:
                allocated_so_far = 0.0
                items_to_create = []
                all_orig_items = [("savings", x) for x in orig_savings] + [("wants", x) for x in orig_wants]
                for idx, (kind, item) in enumerate(all_orig_items):
                    share = float(item.get("amount", 0.0)) / total_orig
                    if idx == len(all_orig_items) - 1:
                        item_amt = round(request.amount - allocated_so_far, 2)
                    else:
                        item_amt = round(request.amount * share, 2)
                        allocated_so_far += item_amt
                    if item_amt > 0:
                        items_to_create.append((kind, int(item["subcategory_id"]), item_amt))

                for kind, sub_id, amt in items_to_create:
                    sub = db.query(cat_models.Subcategory).filter(cat_models.Subcategory.id == sub_id).first()
                    if kind == "savings" and sub and is_emergency_fund_subcategory(sub):
                        updated, bal = _apply_emergency_fund_delta(db, amt)
                        if updated:
                            ef_updated = True
                            new_ef_balance = bal

                    strat_code = applied_entry.strategy_type or "Estrategia"
                    db.add(
                        tx_models.Transaction(
                            date=tx_date,
                            subcategory_id=sub_id,
                            amount=amt,
                            description=f"[Pauta] Barrido Fin de Mes ({strat_code})",
                            applied_strategy_id=applied_entry.id,
                        )
                    )
                    created_txs += 1
            else:
                mode_applied = "DEFAULT_SAVINGS"
        else:
            mode_applied = "DEFAULT_SAVINGS"

    if mode_applied == "DEFAULT_SAVINGS":
        target_sub_id = request.target_subcategory_id
        if not target_sub_id:
            sub_ef = (
                db.query(cat_models.Subcategory)
                .filter(cat_models.Subcategory.name.ilike("%emergencia%"))
                .first()
            )
            if sub_ef:
                target_sub_id = sub_ef.id
            else:
                first_sav = (
                    db.query(cat_models.Subcategory)
                    .join(cat_models.Category)
                    .filter(cat_models.Category.type == "ahorro")
                    .first()
                )
                if not first_sav:
                    raise ValueError("No se encontró ninguna subcategoría de Ahorro destino.")
                target_sub_id = first_sav.id

        sub = db.query(cat_models.Subcategory).filter(cat_models.Subcategory.id == target_sub_id).first()
        if sub and is_emergency_fund_subcategory(sub):
            updated, bal = _apply_emergency_fund_delta(db, request.amount)
            if updated:
                ef_updated = True
                new_ef_balance = bal

        db.add(
            tx_models.Transaction(
                date=tx_date,
                subcategory_id=target_sub_id,
                amount=request.amount,
                description="[Pauta] Barrido Cierre de Mes",
                applied_strategy_id=applied_entry.id if applied_entry else None,
            )
        )
        created_txs += 1

    if applied_entry:
        applied_entry.allocated_amount += request.amount
        applied_entry.cushion_amount = max(0.0, applied_entry.cushion_amount - request.amount)
        if applied_entry.cushion_amount <= 0:
            applied_entry.is_partial = False

    db.commit()
    logger.info(
        "Barrido de fin de mes ejecutado en %s (Modo: %s): %.2f € transferidos en %d transacciones.",
        request.month_key,
        mode_applied,
        request.amount,
        created_txs,
    )
    return SweepResponse(
        success=True,
        message=f"Barrido de fin de mes ejecutado exitosamente ({mode_applied}).",
        amount_swept=request.amount,
        mode_applied=mode_applied,
        transactions_created=created_txs,
        emergency_fund_updated=ef_updated,
        new_emergency_fund_balance=new_ef_balance,
    )


def compensate_guideline_deficit(
    db: Session, request: CompensateDeficitRequest
) -> CompensateDeficitResponse:
    """Ejecuta atómicamente compensaciones y contención presupuestaria de déficit."""
    budgets_updated = 0
    new_budget_amount = None

    if request.action_type == DeficitActionType.WANTS_COMPENSATION_NEXT_MONTH:
        target_month = get_next_month_key(request.month_key)
        if not request.target_subcategory_id:
            raise ValueError("Se requiere target_subcategory_id para compensación en Deseos.")
        new_budget_amount = _decrement_budget_with_base_fallback(
            db, target_month, request.target_subcategory_id, request.amount
        )
        budgets_updated = 1
        msg = f"Ajuste compensatorio programado para {target_month}: presupuesto reducido en {request.amount:.2f} €."

    elif request.action_type == DeficitActionType.NEEDS_ABSORPTION_CURRENT_WANTS:
        target_month = request.month_key
        if not request.target_subcategory_id:
            raise ValueError("Se requiere target_subcategory_id para amortiguar desde Deseos.")
        new_budget_amount = _decrement_budget_with_base_fallback(
            db, target_month, request.target_subcategory_id, request.amount
        )
        budgets_updated = 1
        msg = f"Amortiguación aplicada en {target_month}: presupuesto de Deseos reducido en {request.amount:.2f} € para cubrir Necesidades."

    elif request.action_type == DeficitActionType.FREEZE_WANTS:
        target_month = request.month_key
        sub_ids = request.target_subcategory_ids or (
            [request.target_subcategory_id] if request.target_subcategory_id else []
        )
        if not sub_ids:
            raise ValueError("Se requiere al menos una subcategoría para congelar Deseos.")
        for s_id in sub_ids:
            b = (
                db.query(pres_models.MonthlyBudget)
                .filter(
                    pres_models.MonthlyBudget.month == target_month,
                    pres_models.MonthlyBudget.subcategory_id == s_id,
                )
                .first()
            )
            if b:
                b.amount = 0.0
            else:
                db.add(
                    pres_models.MonthlyBudget(
                        month=target_month,
                        subcategory_id=s_id,
                        amount=0.0,
                    )
                )
            budgets_updated += 1
        new_budget_amount = 0.0
        msg = f"Congelación aplicada en {target_month}: {budgets_updated} partidas de Deseos fijadas a 0.00 €."
    else:
        raise ValueError(f"Acción no reconocida: {request.action_type}")

    db.commit()
    logger.info("Acción de déficit %s completada en %s: %s", request.action_type, target_month, msg)
    return CompensateDeficitResponse(
        success=True,
        message=msg,
        target_month=target_month,
        budgets_updated=budgets_updated,
        new_budget_amount=new_budget_amount,
    )
