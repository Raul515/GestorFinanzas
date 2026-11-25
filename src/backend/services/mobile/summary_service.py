"""Cálculo de resumen mensual móvil, presupuestos y búsqueda histórica."""

from collections import defaultdict
from datetime import date, datetime, timedelta
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from backend.domain.constants import (
    CategoryBlock,
    classify_category_block,
    is_income_category as is_income_cat_canonical,
)
from backend.domain.models.budgets import MonthlyBudget
from backend.domain.models.categories import Category, Subcategory
from backend.domain.models.emergency_fund import EmergencyFund
from backend.domain.models.transactions import Transaction
from backend.domain.schemas.mobile import (
    MobileBudgetUpdate,
    MobileCategorySummary,
    MobileEmergencyFundSummary,
    MobileHistoricalTransactionItem,
    MobileMonthlySummaryResponse,
    MobileSearchResponse,
)
from backend.services.financial_calculator import calculate_503020_targets
from backend.services.safety_guard import (
    evaluate_safety_status,
    get_effective_monthly_budgets,
    resolve_monthly_needs,
)
from backend.utils.dates import month_date_range

logger = logging.getLogger(__name__)


def _to_historical_transaction_item(tx: Transaction) -> MobileHistoricalTransactionItem:
    """Convierte un modelo Transaction ORM en MobileHistoricalTransactionItem."""
    sub = tx.subcategory
    cat_name = sub.category.name if sub and sub.category else "Sin Categoría"
    r_fn = getattr(tx, "receipt_filename", None)
    tx_type = "INCOME" if is_income_cat_canonical(sub.category if sub else None) else "EXPENSE"
    return MobileHistoricalTransactionItem(
        id=tx.id,
        date=str(tx.date),
        amount=float(tx.amount),
        description=tx.description or "",
        type=tx_type,
        subcategory_id=tx.subcategory_id,
        subcategory_name=sub.name if sub else "",
        category_name=cat_name,
        receipt_filename=r_fn,
        receipt_url=f"/api/mobile/receipts/{r_fn}" if r_fn else None,
        mobile_event_id=getattr(tx, "mobile_event_id", None),
    )


def get_mobile_monthly_summary(
    db: Session,
    month_key: Optional[str] = None,
    month: Optional[str] = None,
) -> MobileMonthlySummaryResponse:
    """Calcula el resumen de ejecución presupuestaria del mes (50/30/20) y fondo de seguridad."""
    current_m = month_key or month or date.today().strftime("%Y-%m")
    categories = db.query(Category).order_by(Category.id).all()

    effective_budgets = get_effective_monthly_budgets(db, current_m)
    effective_map = {b.subcategory_id: float(b.amount or 0.0) for b in effective_budgets}

    start_d, end_d = month_date_range(current_m)
    txs = db.query(Transaction).filter(Transaction.date.between(start_d, end_d)).all()

    spent_by_subcat: Dict[int, float] = defaultdict(float)
    income_total = 0.0
    subcat_to_cat = {
        s.id: s.category
        for s in db.query(Subcategory).join(Category).all()
    }

    unassigned_spent = 0.0
    for t in txs:
        if not t.amount:
            continue
        amt = float(t.amount)
        cat = subcat_to_cat.get(t.subcategory_id)
        if is_income_cat_canonical(cat):
            income_total += amt
        elif t.subcategory_id:
            spent_by_subcat[t.subcategory_id] += amt
        else:
            unassigned_spent += amt

    subcats = db.query(Subcategory).all()
    cat_budgeted: Dict[int, float] = defaultdict(float)
    cat_spent: Dict[int, float] = defaultdict(float)
    subcat_summary_list: List[Dict[str, Any]] = []

    if unassigned_spent > 0:
        subcat_summary_list.append({
            "subcategory_id": -1,
            "subcategory_name": "Sin Subcategoría",
            "category_name": "General",
            "spent": round(unassigned_spent, 2),
            "budget": 0.0,
        })

    income_budgeted = 0.0
    for s in subcats:
        cat = subcat_to_cat.get(s.id)
        amt_budgeted = float(effective_map.get(s.id, 0.0))
        amt_spent = float(spent_by_subcat.get(s.id, 0.0))
        if is_income_cat_canonical(cat):
            income_budgeted += amt_budgeted
            continue
        cat_id = s.category_id
        subcat_real = amt_budgeted + amt_spent
        cat_budgeted[cat_id] += amt_budgeted
        cat_spent[cat_id] += subcat_real
        subcat_summary_list.append({
            "subcategory_id": s.id,
            "subcategory_name": s.name,
            "category_name": cat.name if cat else "General",
            "spent": round(subcat_real, 2),
            "budget": round(amt_budgeted, 2),
        })

    total_income_real = round(income_budgeted + income_total, 2)

    has_income_category = any(is_income_cat_canonical(c) for c in categories)
    if has_income_category:
        rule_target_needs, rule_target_wants, rule_target_savings = calculate_503020_targets(total_income_real)
    else:
        rule_target_needs = None
        rule_target_wants = None
        rule_target_savings = None

    categories_summary: List[MobileCategorySummary] = []
    total_b = 0.0
    total_s = 0.0

    needs_summary = None
    wants_summary = None
    savings_summary = None

    for cat in categories:
        if is_income_cat_canonical(cat):
            continue
        b_amt = round(float(cat_budgeted[cat.id]), 2)
        s_amt = round(float(cat_spent[cat.id]), 2)
        block = classify_category_block(cat)

        rule_pct = 0.0
        rule_budget = b_amt
        if block == CategoryBlock.NEEDS:
            rule_pct = 50.0
            if rule_target_needs is not None:
                rule_budget = rule_target_needs
        elif block == CategoryBlock.WANTS:
            rule_pct = 30.0
            if rule_target_wants is not None:
                rule_budget = rule_target_wants
        elif block == CategoryBlock.SAVINGS:
            rule_pct = 20.0
            if rule_target_savings is not None:
                rule_budget = rule_target_savings

        r_amt = round(rule_budget - s_amt, 2)
        prog = round((s_amt / rule_budget * 100) if rule_budget > 0 else (100.0 if s_amt > 0 else 0.0), 1)

        cat_sum = MobileCategorySummary(
            category_id=cat.id,
            category_name=cat.name,
            budgeted_amount=b_amt,
            spent_amount=s_amt,
            remaining_amount=r_amt,
            rule_percentage=rule_pct,
            spent=s_amt,
            budget=rule_budget,
            remaining=r_amt,
            progress_percentage=prog,
        )
        total_b += b_amt
        total_s += s_amt
        categories_summary.append(cat_sum)

        if rule_pct == 50.0:
            needs_summary = cat_sum
        elif rule_pct == 30.0:
            wants_summary = cat_sum
        elif rule_pct == 20.0:
            savings_summary = cat_sum

    if not needs_summary:
        needs_summary = MobileCategorySummary(
            category_id=0,
            category_name="Necesidades Básicas (50%)",
            budgeted_amount=0,
            spent_amount=0,
            remaining_amount=0,
            rule_percentage=50.0,
            budget=rule_target_needs if rule_target_needs is not None else 0.0,
        )
    if not wants_summary:
        wants_summary = MobileCategorySummary(
            category_id=0,
            category_name="Deseos (30%)",
            budgeted_amount=0,
            spent_amount=0,
            remaining_amount=0,
            rule_percentage=30.0,
            budget=rule_target_wants if rule_target_wants is not None else 0.0,
        )
    if not savings_summary:
        savings_summary = MobileCategorySummary(
            category_id=0,
            category_name="Ahorro e Inversión (20%)",
            budgeted_amount=0,
            spent_amount=0,
            remaining_amount=0,
            rule_percentage=20.0,
            budget=rule_target_savings if rule_target_savings is not None else 0.0,
        )

    if unassigned_spent > 0:
        total_s += unassigned_spent
        if wants_summary:
            wants_summary.spent_amount = round(wants_summary.spent_amount + unassigned_spent, 2)
            wants_summary.spent = wants_summary.spent_amount
            wants_summary.remaining_amount = round(wants_summary.budget - wants_summary.spent_amount, 2)
            wants_summary.remaining = wants_summary.remaining_amount
            wants_summary.progress_percentage = round(
                (wants_summary.spent / wants_summary.budget * 100)
                if wants_summary.budget > 0
                else (100.0 if wants_summary.spent > 0 else 0.0),
                1,
            )

    total_remaining = round(total_income_real - total_s, 2)
    remaining_budget = total_remaining

    ef = db.query(EmergencyFund).first()
    ef_obj = ef if ef else EmergencyFund(current_balance=0.0, target_months=3, target_amount=0.0)
    monthly_needs = resolve_monthly_needs(db, current_m)
    if monthly_needs <= 0 and not (ef_obj.target_amount and ef_obj.target_amount > 0):
        monthly_needs = 1000.0
    safety = evaluate_safety_status(ef_obj, monthly_needs)

    emergency_fund_obj = MobileEmergencyFundSummary(
        current_amount=safety.current_balance,
        target_amount=safety.target_amount,
        months_covered=safety.coverage_months,
        is_funded=safety.is_completed,
    )

    return MobileMonthlySummaryResponse(
        month=current_m,
        total_budgeted=round(total_b, 2),
        total_spent=round(total_s, 2),
        total_remaining=total_remaining,
        total_income=total_income_real,
        remaining_budget=remaining_budget,
        categories=categories_summary,
        emergency_fund_balance=round(safety.current_balance, 2),
        emergency_fund_target_months=safety.target_months,
        emergency_fund_months_covered=safety.coverage_months,
        emergency_fund=emergency_fund_obj,
        needs=needs_summary,
        wants=wants_summary,
        savings=savings_summary,
        subcategories=subcat_summary_list,
    )


def update_mobile_budget(
    db: Session,
    update: Any,
    amount: Optional[float] = None,
    month: Optional[str] = None,
) -> bool:
    """Actualiza o inserta la asignación presupuestaria de una subcategoría para un mes."""
    if isinstance(update, MobileBudgetUpdate):
        target_subcat_id = update.subcategory_id
        target_amount = update.amount
        target_month = update.month or datetime.now().strftime("%Y-%m")
    elif isinstance(update, dict):
        target_subcat_id = update.get("subcategory_id", 0)
        target_amount = float(update.get("amount") or update.get("allocated_amount") or 0.0)
        target_month = update.get("month") or datetime.now().strftime("%Y-%m")
    else:
        target_subcat_id = int(update)
        target_amount = float(amount or 0.0)
        target_month = month or datetime.now().strftime("%Y-%m")

    budget_entry = (
        db.query(MonthlyBudget)
        .filter(
            MonthlyBudget.month == target_month,
            MonthlyBudget.subcategory_id == target_subcat_id,
        )
        .first()
    )
    if budget_entry:
        budget_entry.amount = target_amount
    else:
        budget_entry = MonthlyBudget(
            month=target_month,
            subcategory_id=target_subcat_id,
            amount=target_amount,
        )
        db.add(budget_entry)
    db.commit()
    logger.info("Presupuesto móvil actualizado: mes %s, subcat %d, cantidad %.2f", target_month, target_subcat_id, target_amount)
    return True


def search_transactions(
    db: Session,
    query_text: str,
    limit: int = 50,
) -> MobileSearchResponse:
    """Buscador instantáneo de transacciones históricas en SQLite."""
    clean_q = (query_text or "").strip()
    if not clean_q:
        return MobileSearchResponse(query="", total_found=0, items=[])

    search_filter = f"%{clean_q}%"
    results = (
        db.query(Transaction)
        .options(joinedload(Transaction.subcategory).joinedload(Subcategory.category))
        .join(Subcategory, Transaction.subcategory_id == Subcategory.id)
        .join(Category, Subcategory.category_id == Category.id)
        .filter(
            (Transaction.description.ilike(search_filter))
            | (Subcategory.name.ilike(search_filter))
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    items = [_to_historical_transaction_item(tx) for tx in results]
    return MobileSearchResponse(query=clean_q, total_found=len(items), items=items)


def get_historical_cache(
    db: Session,
    months: int = 12,
) -> List[MobileHistoricalTransactionItem]:
    """Exporta las transacciones de los últimos N meses para caché local del teléfono."""
    cutoff_date = date.today() - timedelta(days=months * 31)
    results = (
        db.query(Transaction)
        .options(joinedload(Transaction.subcategory).joinedload(Subcategory.category))
        .join(Subcategory, Transaction.subcategory_id == Subcategory.id)
        .join(Category, Subcategory.category_id == Category.id)
        .filter(Transaction.date >= cutoff_date)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(1000)
        .all()
    )
    return [_to_historical_transaction_item(tx) for tx in results]
