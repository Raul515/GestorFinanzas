"""
Catálogo de Herramientas Desacopladas para el Copiloto Patrimonial (Spec 004).
Define las funciones de consulta bajo demanda (Function Calling estilo MCP)
a las que el Copiloto tiene acceso exclusivamente cuando el usuario lo solicita.
"""

import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.database.interfaz.db_interface import IRepository
from backend.domain.models import categories as cat_models
from backend.domain.models import budgets as pres_models
from backend.domain.models import transactions as trans_models
from backend.services.safety_guard import evaluate_safety_status, sync_fund_state
from backend.services.financial_calculator import (
    calculate_category_totals,
    calculate_503020_percentages,
)

logger = logging.getLogger(__name__)

DEFAULT_KNOWLEDGE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "knowledge"
)


def get_financial_profile(
    repo: IRepository,
    db: Optional[Session] = None,
    month: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Obtiene el perfil financiero consolidado del usuario para el mes especificado o el mes en curso.
    Calcula ingresos netos, necesidades básicas, deseos, ahorro/inversión, saldo 'Sin Asignar'
    y la cobertura actual del Fondo de Emergencia con la autorización de inversión con riesgo.
    """
    logger.info("Ejecutando herramienta 'get_financial_profile' para mes: %s", month)
    try:
        target_month = month or datetime.date.today().strftime("%Y-%m")

        # 1. Recuperar categorías y subcategorías
        categories = repo.get_categories()
        subcategories = repo.get_subcategories()

        cat_dicts = [
            {"id": c.id, "nombre": c.name, "tipo": c.type} for c in categories
        ]
        subcat_dicts = [
            {"id": s.id, "nombre": s.name, "categoria_id": s.category_id}
            for s in subcategories
        ]

        # 2. Recuperar presupuestos del mes (o plantilla BASE como respaldo)
        budgets_raw = repo.get_budgets(target_month)
        if not budgets_raw and target_month != "BASE":
            budgets_raw = repo.get_budgets("BASE")

        budget_dicts = [
            {"subcategoria_id": b.subcategory_id, "cantidad": b.amount}
            for b in budgets_raw
        ]

        # 3. Recuperar transacciones reales del mes (las transacciones siempre son fechadas YYYY-MM)
        trans_raw = (
            repo.get_transactions(target_month)
            if target_month and target_month != "BASE" and "-" in target_month
            else []
        )
        trans_dicts = [
            {"subcategoria_id": t.subcategory_id, "cantidad": t.amount}
            for t in trans_raw
        ]

        # 4. Calcular totales contables por bloque 50/30/20
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
        real_nec = totales_m.get(necesidades_name, {}).get("real", 0.0)
        pres_nec = totales_m.get(necesidades_name, {}).get("presupuesto", 0.0)
        real_des = totales_m.get(deseos_name, {}).get("real", 0.0)
        pres_des = totales_m.get(deseos_name, {}).get("presupuesto", 0.0)
        real_aho = totales_m.get(ahorro_name, {}).get("real", 0.0)
        pres_aho = totales_m.get(ahorro_name, {}).get("presupuesto", 0.0)

        # Si el ingreso real del mes aún no se ha registrado, usar el ingreso presupuestado como referencia
        base_ing = real_ing if real_ing > 0.0 else pres_ing
        _, _, _, _, real_sin_asignar = calculate_503020_percentages(
            base_ing, real_nec, real_des, real_aho
        )

        # 5. Evaluar Salvaguarda del Fondo de Emergencia
        fund = repo.get_or_create_emergency_fund()

        # Determinar gasto mensual de referencia en necesidades básicas
        monthly_needs_ref = pres_nec if pres_nec > 0.0 else real_nec

        # Sincronizar estado
        fund = sync_fund_state(fund, monthly_needs_ref)
        safety = evaluate_safety_status(fund, monthly_needs_ref)

        return {
            "month": target_month,
            "income": {
                "budgeted": round(pres_ing, 2),
                "actual": round(real_ing, 2),
            },
            "needs_50pct": {
                "budgeted": round(pres_nec, 2),
                "actual": round(real_nec, 2),
                "target_cap": round(base_ing * 0.50, 2),
            },
            "wants_30pct": {
                "budgeted": round(pres_des, 2),
                "actual": round(real_des, 2),
                "target_cap": round(base_ing * 0.30, 2),
            },
            "savings_20pct": {
                "budgeted": round(pres_aho, 2),
                "actual": round(real_aho, 2),
                "target_cap": round(base_ing * 0.20, 2),
            },
            "unallocated_surplus": round(real_sin_asignar, 2),
            "emergency_fund": {
                "current_balance": safety.current_balance,
                "target_amount": safety.target_amount,
                "coverage_months": safety.coverage_months,
                "target_months": safety.target_months,
                "monthly_needs_reference": safety.monthly_needs_reference,
                "is_completed": safety.is_completed,
                "gap_to_target": safety.gap,
                "diagnostic": safety.message,
            },
            "risk_investment_allowed": safety.can_invest,
            "constitutional_warning": (
                None
                if safety.can_invest
                else "ADVERTENCIA CONSTITUCIONAL: El fondo de emergencia no cubre los 3 meses mínimos requeridos. "
                "Queda terminantemente prohibido sugerir o asignar capital a instrumentos con riesgo (renta variable, acciones o ETFs volátiles). "
                "El excedente debe canalizarse a completar el fondo de seguridad o instrumentos de liquidez sin volatilidad."
            ),
        }
    except Exception as exc:
        logger.error("Error al obtener el perfil financiero: %s", exc, exc_info=True)
        return {
            "error": True,
            "message": f"No se pudo consultar el perfil financiero debido a un error: {exc}",
        }


def get_watchlist_items(repo: IRepository) -> Dict[str, Any]:
    """
    Obtiene la lista completa de activos guardados en la lista de seguimiento (Watchlist) del usuario.
    """
    logger.info("Ejecutando herramienta 'get_watchlist_items'")
    try:
        items = repo.get_watchlist()
        if not items:
            return {
                "count": 0,
                "items": [],
                "message": "Tu lista de seguimiento está vacía actualmente. Puedes añadir valores desde el Screener o el Análisis Fundamental.",
            }

        serialized = [
            {
                "ticker": item.ticker,
                "name": item.name,
                "sector": item.sector,
                "currency": item.currency,
                "price_at_addition": item.price_at_addition,
                "notes": item.notes,
                "added_at": item.created_at.strftime("%Y-%m-%d %H:%M") if item.created_at else None,
            }
            for item in items
        ]

        return {
            "count": len(serialized),
            "items": serialized,
        }
    except Exception as exc:
        logger.error("Error al obtener la watchlist: %s", exc, exc_info=True)
        return {
            "error": True,
            "message": f"Error al consultar la lista de seguimiento: {exc}",
        }


def get_cached_deepdive(repo: IRepository, ticker: str) -> Dict[str, Any]:
    """
    Recupera el informe contable fundamental y la tesis Quality Value ya almacenados
    en la caché SQLite de 24 horas para el ticker indicado, sin volver a consumir la API de IA.
    """
    clean_ticker = ticker.strip().upper()
    logger.info("Ejecutando herramienta 'get_cached_deepdive' para ticker: %s", clean_ticker)
    cache_key = f"deepdive_{clean_ticker}"

    try:
        cached = repo.get_market_cache(cache_key)
        if not cached:
            return {
                "ticker": clean_ticker,
                "found_in_cache": False,
                "message": (
                    f"No existe un análisis fundamental en caché para el ticker '{clean_ticker}'. "
                    f"Para analizarlo en detalle, el usuario debe abrir la pestaña '🔬 Análisis Fundamental (Deep Dive)' "
                    f"e introducir '{clean_ticker}' para generar los estados contables y el reporte Quality Value."
                ),
            }

        # Extraer campos esenciales para el razonamiento del Copiloto
        piotroski = cached.get("piotroski", {})
        quality_report = cached.get("quality_value_report", {})
        fcf = cached.get("fcf_metrics", {})

        return {
            "ticker": cached.get("ticker", clean_ticker),
            "name": cached.get("name"),
            "sector": cached.get("sector"),
            "industry": cached.get("industry"),
            "country": cached.get("country"),
            "currency": cached.get("currency", "EUR"),
            "current_price": cached.get("current_price"),
            "market_cap": cached.get("market_cap"),
            "pe_trailing": cached.get("pe_trailing"),
            "pe_forward": cached.get("pe_forward"),
            "dividend_yield": cached.get("dividend_yield"),
            "piotroski_f_score": {
                "score": piotroski.get("total_score"),
                "max_score": piotroski.get("max_score", 9),
                "rating": piotroski.get("rating"),
            },
            "fcf_quality": {
                "fcf_yield": fcf.get("fcf_yield"),
                "conversion_ratio": fcf.get("fcf_conversion_ratio"),
                "roe": fcf.get("roe"),
                "roic": fcf.get("roic"),
                "has_moat": fcf.get("has_moat"),
            },
            "quality_value_thesis": {
                "quadrant": quality_report.get("quadrant") if quality_report else None,
                "summary": quality_report.get("summary_thesis") if quality_report else None,
                "six_ingredients": quality_report.get("six_ingredients", {}) if quality_report else {},
                "bearish_risks": quality_report.get("bearish_risks", []) if quality_report else [],
                "target_irr_entry_zone": quality_report.get("target_irr_entry_zone") if quality_report else None,
            },
            "updated_at": cached.get("updated_at"),
            "found_in_cache": True,
        }
    except Exception as exc:
        logger.error("Error al consultar deepdive en caché para %s: %s", clean_ticker, exc, exc_info=True)
        return {
            "error": True,
            "message": f"Error al consultar el análisis fundamental de '{clean_ticker}': {exc}",
        }


def get_cached_macro_overview(repo: IRepository) -> Dict[str, Any]:
    """
    Recupera los indicadores macroeconómicos clave (tipos BCE, prima de riesgo, deuda soberana)
    ya almacenados en la caché SQLite del Radar Macroeconómico.
    """
    logger.info("Ejecutando herramienta 'get_cached_macro_overview'")
    cache_key = "macro_overview_indicators"

    try:
        cached = repo.get_market_cache(cache_key)
        if not cached or "indicators" not in cached:
            return {
                "found_in_cache": False,
                "message": (
                    "Los indicadores del Radar Macroeconómico no están disponibles en la caché local. "
                    "El usuario puede visitar la pestaña '🌐 Radar Macro y Noticias' para actualizarlos."
                ),
            }

        indicators = cached.get("indicators", [])
        return {
            "found_in_cache": True,
            "updated_at": cached.get("updated_at"),
            "indicators": indicators,
        }
    except Exception as exc:
        logger.error("Error al consultar macro en caché: %s", exc, exc_info=True)
        return {
            "error": True,
            "message": f"Error al consultar el contexto macroeconómico: {exc}",
        }


def search_local_knowledge(
    query: str,
    knowledge_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Busca fragmentos relevantes en documentos, notas de inversión o resúmenes locales
    (exportaciones de NotebookLM, notas en Markdown o texto) en la carpeta de conocimiento.
    """
    clean_query = query.strip().lower()
    target_dir = knowledge_dir or DEFAULT_KNOWLEDGE_DIR
    logger.info("Ejecutando herramienta 'search_local_knowledge' con query '%s' en dir: %s", clean_query, target_dir)

    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        return {
            "count": 0,
            "matches": [],
            "message": (
                f"La carpeta de conocimiento local ({target_dir}) está vacía. "
                "Puedes colocar allí archivos de notas (.md, .txt) o exportaciones de NotebookLM."
            ),
        }

    results: List[Dict[str, Any]] = []

    try:
        query_words = [w for w in clean_query.split() if len(w) > 2]
        if not query_words:
            query_words = [clean_query]

        for root, _, files in os.walk(target_dir):
            for file_name in files:
                if file_name.endswith((".txt", ".md", ".json")):
                    file_path = os.path.join(root, file_name)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        # Comprobar coincidencias
                        content_lower = content.lower()
                        if any(w in content_lower for w in query_words):
                            # Extraer fragmentos con contexto
                            snippets = []
                            lines = content.splitlines()
                            for idx, line in enumerate(lines):
                                if any(w in line.lower() for w in query_words):
                                    start = max(0, idx - 1)
                                    end = min(len(lines), idx + 2)
                                    snippets.append("\n".join(lines[start:end]))
                                    if len(snippets) >= 3:
                                        break

                            results.append(
                                {
                                    "file": file_name,
                                    "excerpt": "\n---\n".join(snippets) if snippets else content[:300],
                                }
                            )
                    except Exception as read_exc:
                        logger.warning("No se pudo leer el archivo %s: %s", file_path, read_exc)

        return {
            "query": query,
            "count": len(results),
            "matches": results,
            "message": None if results else f"No se encontraron notas o documentos locales que contengan '{query}'.",
        }
    except Exception as exc:
        logger.error("Error al buscar en conocimiento local: %s", exc, exc_info=True)
        return {
            "error": True,
            "message": f"Error al buscar en notas locales: {exc}",
        }


# ==============================================================================
# Declaración de Esquemas de Funciones para Gemini Function Calling
# ==============================================================================

COPILOT_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "get_financial_profile",
        "description": (
            "Consulta el perfil financiero personal del usuario para el mes actual o especificado: "
            "ingresos, distribución 50/30/20, saldo 'Sin Asignar', estado y cobertura del Fondo de Emergencia "
            "y si está constitucionalmente permitido invertir en activos con riesgo. "
            "USAR SÓLO si el usuario pregunta por su estado financiero, saldo para invertir o situación personal."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "month": {
                    "type": "string",
                    "description": "Mes a consultar en formato 'YYYY-MM' o 'BASE'. Opcional, por defecto mes actual.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_watchlist_items",
        "description": (
            "Obtiene la lista de seguimiento (Watchlist) del usuario con los activos guardados, "
            "precios de adición y notas personales. "
            "USAR SÓLO si el usuario pregunta por sus activos en seguimiento o su cartera vigilada."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_cached_deepdive",
        "description": (
            "Consulta el diagnóstico de análisis fundamental en profundidad previamente analizado y guardado en caché: "
            "Piotroski F-Score (0-9), métricas FCF, cuadrante Quality Value, 6 ingredientes y matriz de riesgos bajistas. "
            "Lee los datos de la caché local sin regenerar costes de IA. "
            "USAR cuando el usuario pregunte por el análisis o tesis de un ticker concreto (ej. 'ITX.MC', 'AAPL')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Símbolo bursátil de la empresa a consultar (ej. 'ITX.MC', 'AAPL', 'SAN.MC').",
                }
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_cached_macro_overview",
        "description": (
            "Consulta los indicadores macroeconómicos clave guardados en caché: tipos del BCE, "
            "prima de riesgo de España, rendimiento de la deuda soberana y principales índices bursátiles. "
            "USAR si el usuario pregunta sobre la situación macroeconómica o de tipos de interés."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "search_local_knowledge",
        "description": (
            "Busca en las notas de inversión personales, resúmenes o documentos locales exportados (tipo NotebookLM). "
            "USAR si el usuario hace referencia a sus notas personales, resúmenes guardados o documentos propios."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Palabras clave o concepto financiero a buscar en las notas locales.",
                }
            },
            "required": ["query"],
        },
    },
]


def execute_copilot_tool(
    tool_name: str,
    args: Dict[str, Any],
    repo: IRepository,
    db: Optional[Session] = None,
    knowledge_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Enrutador desacoplado para ejecutar una herramienta solicitada por el agente y retornar su resultado.
    """
    logger.info("Enrutando ejecución de tool '%s' con argumentos: %s", tool_name, args)

    if tool_name == "get_financial_profile":
        month = args.get("month")
        return get_financial_profile(repo=repo, db=db, month=month)

    elif tool_name == "get_watchlist_items":
        return get_watchlist_items(repo=repo)

    elif tool_name == "get_cached_deepdive":
        ticker = args.get("ticker", "")
        return get_cached_deepdive(repo=repo, ticker=ticker)

    elif tool_name == "get_cached_macro_overview":
        return get_cached_macro_overview(repo=repo)

    elif tool_name == "search_local_knowledge":
        query = args.get("query", "")
        return search_local_knowledge(query=query, knowledge_dir=knowledge_dir)

    else:
        logger.warning("Herramienta desconocida solicitada: %s", tool_name)
        return {
            "error": True,
            "message": f"Herramienta '{tool_name}' no reconocida en el catálogo del Copiloto.",
        }
