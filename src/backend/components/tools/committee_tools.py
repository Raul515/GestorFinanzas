"""
Herramientas Deterministas del Comité de Inversión (Spec 005 - components/tools).
Encapsula el acceso a datos contables, de salvaguarda patrimonial, de mercado y documentos locales,
garantizando cómputos deterministas en Python puro sin coste de tokens de IA.
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.database.interfaz.db_interface import IRepository
from backend.services.safety_guard import evaluate_safety_status, sync_fund_state
from backend.services.financial_calculator import (
    calculate_category_totals,
    calculate_503020_percentages,
)
from backend.services.market_data import get_macro_overview
from backend.services.equity_deepdive import get_equity_deepdive_data
from backend.external_components.data_ingestion.local_doc_loader import LocalDocLoader

logger = logging.getLogger(__name__)


def fetch_safety_status(
    repo: IRepository,
    db: Optional[Session] = None,
    month: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evalúa matemáticamente la salud financiera del usuario y la salvaguarda de seguridad (Principio 9).
    Calcula meses de cobertura del fondo de emergencia, saldo 'Sin Asignar' y estado del veto.
    """
    target_month = month or "BASE"
    try:
        # 1. Recuperar categorías y subcategorías
        categories = repo.get_categories()
        subcategories = repo.get_subcategories()

        cat_dicts = [{"id": c.id, "nombre": c.name, "tipo": c.type} for c in categories]
        subcat_dicts = [
            {"id": s.id, "nombre": s.name, "categoria_id": s.category_id}
            for s in subcategories
        ]

        # 2. Presupuestos y transacciones
        budgets_raw = repo.get_budgets(target_month)
        if not budgets_raw and target_month != "BASE":
            budgets_raw = repo.get_budgets("BASE")

        budget_dicts = [
            {"subcategoria_id": b.subcategory_id, "cantidad": b.amount}
            for b in budgets_raw
        ]

        trans_raw = (
            repo.get_transactions(target_month)
            if target_month and target_month != "BASE" and "-" in target_month
            else []
        )
        trans_dicts = [
            {"subcategoria_id": t.subcategory_id, "cantidad": t.amount}
            for t in trans_raw
        ]

        # 3. Totales 50/30/20 y saldo Sin Asignar
        ingresos_name = "Ingresos Netos"
        necesidades_name = "Necesidades Básicas"
        deseos_name = "Deseos"
        ahorro_name = "Ahorro e Inversión"

        totales_m = calculate_category_totals(
            categorias=cat_dicts,
            todas_subcats=subcat_dicts,
            presupuestos_m=budget_dicts,
            transacciones_m=trans_dicts,
            ingresos_name=ingresos_name,
            necesidades_name=necesidades_name,
            deseos_name=deseos_name,
            ahorro_name=ahorro_name,
        )

        real_ing = totales_m.get(ingresos_name, {}).get("real", 0.0)
        pres_ing = totales_m.get(ingresos_name, {}).get("presupuesto", 0.0)
        effective_ing = real_ing if real_ing > 0 else pres_ing

        real_nec = totales_m.get(necesidades_name, {}).get("real", 0.0)
        pres_nec = totales_m.get(necesidades_name, {}).get("presupuesto", 0.0)
        effective_nec = real_nec if real_nec > 0 else pres_nec

        real_des = totales_m.get(deseos_name, {}).get("real", 0.0)
        real_aho = totales_m.get(ahorro_name, {}).get("real", 0.0)

        # Saldo Sin Asignar
        sin_asignar = max(0.0, effective_ing - (real_nec + real_des + real_aho))

        # 4. Estado formal del fondo de emergencia
        fund = repo.get_or_create_emergency_fund()
        monthly_needs_ref = pres_nec if pres_nec > 0.0 else real_nec
        fund = sync_fund_state(fund, monthly_needs_ref)
        safety = evaluate_safety_status(fund, monthly_needs_ref)

        coverage_months = safety.coverage_months
        investing_allowed = safety.can_invest

        return {
            "month": target_month,
            "coverage_months": round(coverage_months, 2),
            "investing_allowed": investing_allowed,
            "monthly_needs": round(monthly_needs_ref, 2),
            "target_3m": round(safety.target_amount, 2),
            "current_balance": round(safety.current_balance, 2),
            "gap_to_target": round(safety.gap, 2),
            "unassigned_balance": round(sin_asignar, 2),
            "effective_income": round(effective_ing, 2),
            "error": False,
        }
    except Exception as exc:
        logger.error("Error determinista al evaluar salvaguarda patrimonial: %s", exc)
        return {
            "month": target_month,
            "coverage_months": 0.0,
            "investing_allowed": False,
            "monthly_needs": 0.0,
            "target_3m": 0.0,
            "current_balance": 0.0,
            "gap_to_target": 0.0,
            "unassigned_balance": 0.0,
            "effective_income": 0.0,
            "error": True,
            "message": str(exc),
        }


def fetch_macro_overview() -> Dict[str, Any]:
    """
    Obtiene los indicadores macroeconómicos clave (tipos BCE, deuda soberana, prima de riesgo).
    Lee de caché de 24 horas o consulta las APIs públicas sin consumo de tokens de IA.
    """
    try:
        indicators = get_macro_overview()
        return {
            "indicators": indicators,
            "total_indicators": len(indicators),
            "error": False,
        }
    except Exception as exc:
        logger.error("Error al obtener indicadores macroeconómicos: %s", exc)
        return {
            "indicators": [],
            "total_indicators": 0,
            "error": True,
            "message": str(exc),
        }


def fetch_fundamental_deepdive(
    ticker: str,
    repo: Optional[IRepository] = None,
) -> Optional[Dict[str, Any]]:
    """
    Recupera el diagnóstico contable en profundidad de una empresa cotizada:
    Piotroski Score (0-9), métricas FCF, solvencia y márgenes a 4 años.
    Aplica política de caché SQLite de 24 horas si repo está disponible.
    """
    clean_ticker = ticker.strip().upper()

    # Intentar leer de caché SQLite si repo está disponible
    if repo is not None:
        cache_key = f"deepdive_{clean_ticker}"
        cached = repo.get_market_cache(cache_key)
        if isinstance(cached, dict):
            return cached

    # Extracción contable cuantitativa en Python puro
    try:
        data = get_equity_deepdive_data(clean_ticker)
        if data is not None:
            data_dict = data.model_dump()
            if repo is not None:
                repo.set_market_cache(f"deepdive_{clean_ticker}", data_dict)
            return data_dict
        return None
    except Exception as exc:
        logger.error("Error al extraer diagnóstico contable para '%s': %s", clean_ticker, exc)
        return None


def search_local_notes(
    query: str,
    max_results: int = 3,
    notes_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Busca fragmentos relevantes en notas de inversión locales vía LocalDocLoader.
    """
    try:
        loader = LocalDocLoader(knowledge_dir=notes_dir) if notes_dir else LocalDocLoader()
        return loader.search_documents(query, max_results=max_results)
    except Exception as exc:
        logger.error("Error al buscar en notas locales: %s", exc)
        return []
