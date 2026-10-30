import datetime
import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.domain.models import (
    budgets as pres_models,
    categories as cat_models,
    emergency_fund as ef_models,
    guidelines as guideline_models,
    transactions as tx_models,
)
from backend.domain.schemas.guidelines import (
    AnnualGuidelineReport,
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
from backend.services.guidelines_service import (
    evaluate_annual_guidelines,
    evaluate_monthly_guidelines,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guidelines", tags=["guidelines"])


def _resolve_tx_date(month_key: str) -> datetime.date:
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


class MonthlyGuidelineRequest(BaseModel):
    month_key: str = Field(..., description="Identificador del mes en formato YYYY-MM")
    month_name: str = Field(..., description="Nombre del mes en español (ej. Enero)")
    real_income: float = Field(0.0, description="Ingresos reales del mes en euros")
    budget_income: float = Field(0.0, description="Ingresos presupuestados en euros")
    real_needs: float = Field(0.0, description="Gasto real en Necesidades Básicas")
    real_wants: float = Field(0.0, description="Gasto real en Deseos / Ocio")
    real_savings: float = Field(0.0, description="Ahorro real asignado en el mes")
    safety_status: Optional[Dict[str, Any]] = Field(
        None, description="Estado del Fondo de Emergencia (Safety Guard) si está disponible"
    )


class AnnualGuidelineRequest(BaseModel):
    metrics: Dict[str, Any] = Field(
        ..., description="Diccionario con métricas anuales calculadas por financial_calculator"
    )


@router.post("/monthly", response_model=MonthlyGuidelineReport)
def get_monthly_guidelines_endpoint(
    request: MonthlyGuidelineRequest,
    db: Session = Depends(get_db),
) -> MonthlyGuidelineReport:
    """Evalúa las pautas y compensaciones deterministas para un mes específico."""
    try:
        applied_records = (
            db.query(guideline_models.AppliedGuidelineStrategy)
            .filter(
                guideline_models.AppliedGuidelineStrategy.month == request.month_key,
            )
            .all()
        )
        applied_strategies_map: Dict[str, Any] = {}
        for applied_record in applied_records:
            # Verificar si las transacciones vinculadas a la estrategia aún existen
            linked_txs = (
                db.query(tx_models.Transaction)
                .filter(tx_models.Transaction.applied_strategy_id == applied_record.id)
                .all()
            )
            pauta_txs = (
                db.query(tx_models.Transaction)
                .filter(
                    tx_models.Transaction.date.like(f"{request.month_key}%"),
                    tx_models.Transaction.description.like(f"[Pauta {applied_record.strategy_type}%"),
                )
                .all()
            )
            if not linked_txs and not pauta_txs:
                logger.info("Estrategia huérfana %s detectada sin transacciones en mes %s; limpiando registro.", applied_record.scenario_type, request.month_key)
                db.delete(applied_record)
                db.commit()
            else:
                split_cfg = None
                if getattr(applied_record, "split_config", None):
                    try:
                        split_cfg = json.loads(applied_record.split_config)
                    except Exception as err:
                        logger.warning("Error deserializando split_config: %s", err)
                if not split_cfg and applied_record.transactions:
                    s_items = []
                    w_items = []
                    for tx in applied_record.transactions:
                        sub = db.query(cat_models.Subcategory).filter(cat_models.Subcategory.id == tx.subcategory_id).first()
                        is_savings = sub and sub.category and sub.category.type == "ahorro"
                        item_data = {
                            "subcategory_id": tx.subcategory_id,
                            "amount": tx.amount,
                            "name": sub.name if sub else f"Subcat {tx.subcategory_id}",
                        }
                        if is_savings:
                            s_items.append(item_data)
                        else:
                            w_items.append(item_data)
                    split_cfg = {"savings": s_items, "wants": w_items}

                strat_data = {
                    "month": applied_record.month,
                    "scenario_type": applied_record.scenario_type,
                    "strategy_type": applied_record.strategy_type,
                    "is_partial": applied_record.is_partial,
                    "allocated_amount": applied_record.allocated_amount,
                    "cushion_amount": applied_record.cushion_amount,
                    "split_config": split_cfg,
                }
                applied_strategies_map[applied_record.scenario_type] = strat_data

        if not applied_strategies_map:
            # Fallback de seguridad: detectar si ya existen transacciones con [Pauta ...
            pauta_txs = (
                db.query(tx_models.Transaction)
                .filter(
                    tx_models.Transaction.date.like(f"{request.month_key}%"),
                    tx_models.Transaction.description.like("[Pauta %"),
                )
                .all()
            )
            if pauta_txs:
                total_alloc = sum(t.amount for t in pauta_txs)
                strat_name = "HYBRID_80_20"
                scen_name = "NEEDS_SURPLUS"
                for t in pauta_txs:
                    if "FIRE" in t.description:
                        strat_name = "FIRE"
                        break
                    elif "SINKING" in t.description:
                        strat_name = "SINKING_FUND"
                        break
                    elif "EXTRAORDINARY" in t.description or "Bonus" in t.description:
                        strat_name = "EXTRAORDINARY_INCOME"
                        scen_name = "EXTRAORDINARY_INCOME"
                        break
                applied_strategies_map[scen_name] = {
                    "month": request.month_key,
                    "scenario_type": scen_name,
                    "strategy_type": strat_name,
                    "is_partial": False,
                    "allocated_amount": total_alloc,
                    "cushion_amount": 0.0,
                }

        applied_strategy_dict = applied_strategies_map.get("NEEDS_SURPLUS") or (next(iter(applied_strategies_map.values())) if applied_strategies_map else None)

        report = evaluate_monthly_guidelines(
            month_key=request.month_key,
            month_name=request.month_name,
            real_income=request.real_income,
            budget_income=request.budget_income,
            real_needs=request.real_needs,
            real_wants=request.real_wants,
            real_savings=request.real_savings,
            safety_status=request.safety_status,
            applied_strategy=applied_strategy_dict,
            applied_strategies=applied_strategies_map,
        )
        report.applied_strategy = applied_strategy_dict
        report.applied_strategies = applied_strategies_map
        return report
    except Exception as exc:
        logger.error(
            "Error evaluando pautas mensuales para mes %s: %s",
            request.month_key,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error interno evaluando pautas mensuales: {str(exc)}",
        ) from exc


@router.post("/annual", response_model=AnnualGuidelineReport)
def get_annual_guidelines_endpoint(request: AnnualGuidelineRequest) -> AnnualGuidelineReport:
    """Evalúa el diagnóstico estructural y pautas anuales consolidadas."""
    try:
        report = evaluate_annual_guidelines(request.metrics)
        return report
    except Exception as exc:
        logger.error(
            "Error evaluando pautas anuales: %s",
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
        ) from exc


@router.post("/apply-strategy", response_model=StrategyApplyResponse)
def apply_guideline_strategy_endpoint(
    request: StrategyApplyRequest,
    db: Session = Depends(get_db),
) -> StrategyApplyResponse:
    """
    Ejecuta de forma atómica la estrategia de asignación de capital:
    - Registra el estado de la estrategia en AppliedGuidelineStrategy para obtener su ID.
    - Crea transacciones de aporte en las subcategorías de Ahorro vinculadas a la estrategia.
    - Sincroniza el saldo del Fondo de Emergencia si alguna asignación apunta a él.
    - Crea transacciones reales en las subcategorías de Deseos seleccionadas vinculadas a la estrategia.
    """
    tx_date = _resolve_tx_date(request.month_key)
    created_txs = 0
    updated_budgets = 0
    ef_updated = False
    new_ef_balance = None

    try:
        # 1. Registrar o actualizar la estrategia aplicada en la base de datos para obtener su ID
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
        # Serializar la configuración de partición para poder heredarla en el barrido de fin de mes
        split_dict = {
            "savings": [
                {"subcategory_id": item.subcategory_id, "amount": item.amount, "percentage": item.percentage}
                for item in request.savings_allocations if item.amount > 0
            ],
            "wants": [
                {"subcategory_id": item.subcategory_id, "amount": item.amount, "percentage": item.percentage}
                for item in request.wants_allocations if item.amount > 0
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

        # 2. Procesar asignaciones a Ahorro/Inversión (Transacciones vinculadas a la estrategia)
        for item in request.savings_allocations:
            if item.amount <= 0:
                continue

            sub = (
                db.query(cat_models.Subcategory)
                .filter(cat_models.Subcategory.id == item.subcategory_id)
                .first()
            )
            sub_name = sub.name.lower() if sub else ""

            # Verificar si corresponde al Fondo de Emergencia para actualizar saldo
            if "emergencia" in sub_name:
                ef = db.query(ef_models.EmergencyFund).first()
                if ef:
                    ef.current_balance += item.amount
                    if ef.target_amount > 0 and ef.current_balance >= ef.target_amount:
                        ef.is_completed = True
                    ef_updated = True
                    new_ef_balance = ef.current_balance

            tx = tx_models.Transaction(
                date=tx_date,
                subcategory_id=item.subcategory_id,
                amount=item.amount,
                description=f"[Pauta {request.strategy_type}] {desc_suffix}",
                applied_strategy_id=applied_entry.id,
            )
            db.add(tx)
            created_txs += 1

        # 3. Procesar asignaciones a Deseos (Transacciones reales vinculadas a la estrategia, sin inflar presupuesto)
        for item in request.wants_allocations:
            if item.amount <= 0:
                continue

            tx = tx_models.Transaction(
                date=tx_date,
                subcategory_id=item.subcategory_id,
                amount=item.amount,
                description=f"[Pauta {request.strategy_type}] {desc_suffix} a Deseos",
                applied_strategy_id=applied_entry.id,
            )
            db.add(tx)
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
            budgets_updated=updated_budgets,
            emergency_fund_updated=ef_updated,
            new_emergency_fund_balance=new_ef_balance,
        )
    except Exception as exc:
        db.rollback()
        logger.error(
            "Error aplicando estrategia %s en mes %s: %s",
            request.strategy_type,
            request.month_key,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error interno aplicando la estrategia: {str(exc)}",
        ) from exc


@router.post("/revert-strategy", response_model=StrategyRevertResponse)
def revert_guideline_strategy_endpoint(
    request: StrategyRevertRequest,
    db: Session = Depends(get_db),
) -> StrategyRevertResponse:
    """
    Revierte atómicamente una estrategia de asignación de capital aplicada:
    - Encuentra la estrategia en AppliedGuidelineStrategy.
    - Elimina todas las transacciones vinculadas (ahorro y deseos).
    - Descuenta del Fondo de Emergencia el saldo aportado si correspondía.
    - Elimina el registro de la estrategia aplicada.
    """
    try:
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
                fund.current_balance = max(0.0, fund.current_balance - tx.amount)
                ef_reverted += tx.amount
            db.delete(tx)

        reverted_count = len(linked_txs)
        db.delete(applied_entry)
        db.commit()

        # Resincronizar estado del fondo de emergencia si se alteró el saldo
        if fund and ef_reverted > 0:
            from backend.api.routers.safety_guard import _resolve_monthly_needs
            from backend.services.safety_guard import sync_fund_state
            monthly_needs = _resolve_monthly_needs(db, request.month_key)
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
    except Exception as exc:
        db.rollback()
        logger.error("Error al revertir estrategia en mes %s: %s", request.month_key, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al revertir la estrategia: {str(exc)}",
        ) from exc


@router.post("/sweep", response_model=SweepResponse)
def sweep_month_surplus_endpoint(
    request: SweepRequest,
    db: Session = Depends(get_db),
) -> SweepResponse:
    """
    Ejecuta el barrido de fin de mes:
    - Modo INHERIT_STRATEGY: Liquida el colchón prudencial repartiendo el remanente con las mismas
      proporciones y subcategorías que la estrategia original (ej. 80/20).
    - Modo DEFAULT_SAVINGS: Transfiere el 100% del remanente hacia la subcategoría de Ahorro destino.
    - Sincroniza el Fondo de Emergencia si alguna subcategoría destino corresponde a él.
    - Vincula las transacciones generadas a la estrategia aplicada y reduce cushion_amount a 0.
    """
    tx_date = _resolve_tx_date(request.month_key)
    ef_updated = False
    new_ef_balance = None
    created_txs = 0

    try:
        # 1. Buscar si hay una estrategia aplicada en el mes (priorizando las que tengan colchón pendiente)
        applied_entry = (
            db.query(guideline_models.AppliedGuidelineStrategy)
            .filter(
                guideline_models.AppliedGuidelineStrategy.month == request.month_key,
                guideline_models.AppliedGuidelineStrategy.cushion_amount > 0,
            )
            .first()
        ) or (
            db.query(guideline_models.AppliedGuidelineStrategy)
            .filter(
                guideline_models.AppliedGuidelineStrategy.month == request.month_key,
            )
            .first()
        )

        mode_applied = request.mode

        if mode_applied == "INHERIT_STRATEGY" and applied_entry:
            # Reconstruir las asignaciones proporcionales a partir de split_config o linked transactions
            split_cfg = None
            if applied_entry.split_config:
                try:
                    split_cfg = json.loads(applied_entry.split_config)
                except Exception as err:
                    logger.warning("Error leyendo split_config en sweep: %s", err)

            # Si no hay split_config, reconstruir a partir de transacciones existentes vinculadas
            if not split_cfg and applied_entry.transactions:
                s_items = []
                w_items = []
                for tx in applied_entry.transactions:
                    sub = db.query(cat_models.Subcategory).filter(cat_models.Subcategory.id == tx.subcategory_id).first()
                    is_savings = sub and sub.category and sub.category.type == "ahorro"
                    item_data = {"subcategory_id": tx.subcategory_id, "amount": tx.amount}
                    if is_savings:
                        s_items.append(item_data)
                    else:
                        w_items.append(item_data)
                split_cfg = {"savings": s_items, "wants": w_items}

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
                        sub_name = sub.name.lower() if sub else ""

                        if kind == "savings" and "emergencia" in sub_name:
                            ef = db.query(ef_models.EmergencyFund).first()
                            if ef:
                                ef.current_balance += amt
                                if ef.target_amount > 0 and ef.current_balance >= ef.target_amount:
                                    ef.is_completed = True
                                ef_updated = True
                                new_ef_balance = ef.current_balance

                        strat_code = applied_entry.strategy_type or "Estrategia"
                        tx = tx_models.Transaction(
                            date=tx_date,
                            subcategory_id=sub_id,
                            amount=amt,
                            description=f"[Pauta] Barrido Fin de Mes ({strat_code})",
                            applied_strategy_id=applied_entry.id,
                        )
                        db.add(tx)
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
                    if first_sav:
                        target_sub_id = first_sav.id
                    else:
                        raise HTTPException(status_code=400, detail="No se encontró ninguna subcategoría de Ahorro destino.")

            sub = db.query(cat_models.Subcategory).filter(cat_models.Subcategory.id == target_sub_id).first()
            sub_name = sub.name.lower() if sub else ""

            if "emergencia" in sub_name:
                ef = db.query(ef_models.EmergencyFund).first()
                if ef:
                    ef.current_balance += request.amount
                    if ef.target_amount > 0 and ef.current_balance >= ef.target_amount:
                        ef.is_completed = True
                    ef_updated = True
                    new_ef_balance = ef.current_balance

            tx = tx_models.Transaction(
                date=tx_date,
                subcategory_id=target_sub_id,
                amount=request.amount,
                description="[Pauta] Barrido Cierre de Mes",
                applied_strategy_id=applied_entry.id if applied_entry else None,
            )
            db.add(tx)
            created_txs += 1

        # Actualizar la estrategia aplicada si tenía colchón activo
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
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            "Error ejecutando barrido en mes %s: %s",
            request.month_key,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error interno ejecutando el barrido: {str(exc)}",
        ) from exc


def _get_next_month_key(month_key: str) -> str:
    """Calcula la clave YYYY-MM del mes inmediato posterior."""
    try:
        parts = month_key.split("-")
        y, m = int(parts[0]), int(parts[1])
        if m == 12:
            return f"{y + 1}-01"
        return f"{y}-{m + 1:02d}"
    except Exception:
        return month_key


@router.post("/compensate-deficit", response_model=CompensateDeficitResponse)
def compensate_guideline_deficit_endpoint(
    request: CompensateDeficitRequest,
    db: Session = Depends(get_db),
) -> CompensateDeficitResponse:
    """
    Ejecuta de forma atómica acciones de compensación y contención presupuestaria:
    1. WANTS_COMPENSATION_NEXT_MONTH: Reduce el presupuesto de Deseos del mes siguiente (YYYY-(M+1))
       en la cantidad exacta del sobregasto (excess_wants).
    2. NEEDS_ABSORPTION_CURRENT_WANTS: Reduce el presupuesto de Deseos del mes en curso para absorber
       el déficit de Necesidades sin tocar el Fondo de Emergencia.
    3. FREEZE_WANTS: Congela a cero las partidas de ocio/estilo de vida en el mes ante caída de ingresos.
    """
    budgets_updated = 0
    new_budget_amount = None

    try:
        if request.action_type == DeficitActionType.WANTS_COMPENSATION_NEXT_MONTH:
            target_month = _get_next_month_key(request.month_key)
            if not request.target_subcategory_id:
                raise HTTPException(
                    status_code=400,
                    detail="Se requiere target_subcategory_id para compensación en Deseos.",
                )

            b = (
                db.query(pres_models.MonthlyBudget)
                .filter(
                    pres_models.MonthlyBudget.month == target_month,
                    pres_models.MonthlyBudget.subcategory_id == request.target_subcategory_id,
                )
                .first()
            )
            if b:
                b.amount = max(0.0, b.amount - request.amount)
                new_budget_amount = b.amount
            else:
                base_b = (
                    db.query(pres_models.MonthlyBudget)
                    .filter(
                        pres_models.MonthlyBudget.month == "BASE",
                        pres_models.MonthlyBudget.subcategory_id == request.target_subcategory_id,
                    )
                    .first()
                )
                base_val = base_b.amount if base_b else 0.0
                new_budget_amount = max(0.0, base_val - request.amount)
                new_b = pres_models.MonthlyBudget(
                    month=target_month,
                    subcategory_id=request.target_subcategory_id,
                    amount=new_budget_amount,
                )
                db.add(new_b)
            budgets_updated = 1
            msg = f"Ajuste compensatorio programado para {target_month}: presupuesto reducido en {request.amount:.2f} €."

        elif request.action_type == DeficitActionType.NEEDS_ABSORPTION_CURRENT_WANTS:
            target_month = request.month_key
            if not request.target_subcategory_id:
                raise HTTPException(
                    status_code=400,
                    detail="Se requiere target_subcategory_id para amortiguar desde Deseos.",
                )

            b = (
                db.query(pres_models.MonthlyBudget)
                .filter(
                    pres_models.MonthlyBudget.month == target_month,
                    pres_models.MonthlyBudget.subcategory_id == request.target_subcategory_id,
                )
                .first()
            )
            if b:
                b.amount = max(0.0, b.amount - request.amount)
                new_budget_amount = b.amount
            else:
                base_b = (
                    db.query(pres_models.MonthlyBudget)
                    .filter(
                        pres_models.MonthlyBudget.month == "BASE",
                        pres_models.MonthlyBudget.subcategory_id == request.target_subcategory_id,
                    )
                    .first()
                )
                base_val = base_b.amount if base_b else 0.0
                new_budget_amount = max(0.0, base_val - request.amount)
                new_b = pres_models.MonthlyBudget(
                    month=target_month,
                    subcategory_id=request.target_subcategory_id,
                    amount=new_budget_amount,
                )
                db.add(new_b)
            budgets_updated = 1
            msg = f"Amortiguación aplicada en {target_month}: presupuesto de Deseos reducido en {request.amount:.2f} € para cubrir Necesidades."

        elif request.action_type == DeficitActionType.FREEZE_WANTS:
            target_month = request.month_key
            sub_ids = request.target_subcategory_ids or (
                [request.target_subcategory_id] if request.target_subcategory_id else []
            )
            if not sub_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Se requiere al menos una subcategoría para congelar Deseos.",
                )

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
                    new_b = pres_models.MonthlyBudget(
                        month=target_month,
                        subcategory_id=s_id,
                        amount=0.0,
                    )
                    db.add(new_b)
                budgets_updated += 1
            new_budget_amount = 0.0
            msg = f"Congelación aplicada en {target_month}: {budgets_updated} partidas de Deseos fijadas a 0.00 €."

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Acción no reconocida: {request.action_type}",
            )

        db.commit()
        logger.info(
            "Acción de déficit %s completada en %s: %s",
            request.action_type,
            target_month,
            msg,
        )
        return CompensateDeficitResponse(
            success=True,
            message=msg,
            target_month=target_month,
            budgets_updated=budgets_updated,
            new_budget_amount=new_budget_amount,
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            "Error ejecutando acción de compensación %s en mes %s: %s",
            request.action_type,
            request.month_key,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error interno en compensación presupuestaria: {str(exc)}",
        ) from exc


