"""
Servicio desacoplado para el Análisis Fundamental en Profundidad (Deep Dive - Spec 003).
Implementa la extracción de estados contables históricos (3-4 años), el motor determinista
del Piotroski F-Score (0-9 puntos) y el cálculo de métricas de Flujo de Caja Libre (FCF).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import yfinance as yf

from backend.domain.schemas.deepdive import (
    DeepDiveResponse,
    FinancialStatementYear,
    PiotroskiCriterion,
    PiotroskiScore,
)

logger = logging.getLogger(__name__)


def _safe_float(val: Any) -> Optional[float]:
    """Convierte de forma segura un valor numérico a float redondeado o None si es inválido/NaN."""
    if val is None or pd.isna(val):
        return None
    try:
        fval = float(val)
        if pd.isna(fval):
            return None
        return round(fval, 2)
    except (ValueError, TypeError):
        return None


def _get_row_value(df: Optional[pd.DataFrame], row_names: List[str], col: Any) -> Optional[float]:
    """Busca el primer nombre de fila coincidente en el DataFrame y devuelve el valor numérico."""
    if df is None or df.empty or col not in df.columns:
        return None
    for name in row_names:
        if name in df.index:
            val = df.loc[name, col]
            # Si hay duplicados de índice, pandas devuelve una Serie
            if isinstance(val, pd.Series):
                val = val.iloc[0]
            parsed = _safe_float(val)
            if parsed is not None:
                return parsed
    return None


def fetch_historical_financials(ticker: str) -> Tuple[Dict[str, Any], List[FinancialStatementYear], bool]:
    """
    Extrae los estados financieros históricos anuales (Balance, Resultados, Cash Flow)
    y el perfil de cotización de la empresa mediante yfinance.
    
    Retorna una tupla: (info_dict, statements_list, is_financial_institution).
    """
    clean_ticker = ticker.strip().upper()
    ticker_obj = yf.Ticker(clean_ticker)

    try:
        info = ticker_obj.info or {}
    except Exception as exc:
        logger.warning("Fallo al obtener info de yfinance para %s: %s", clean_ticker, exc)
        info = {}

    sector = info.get("sector") or ""
    industry = info.get("industry") or ""
    is_bank = (
        sector.lower() == "financial services"
        or "bank" in industry.lower()
        or "insurance" in industry.lower()
    )

    financials_df = None
    balance_df = None
    cashflow_df = None

    try:
        financials_df = ticker_obj.financials
    except Exception as exc:
        logger.warning("No se pudo extraer la cuenta de resultados para %s: %s", clean_ticker, exc)

    try:
        balance_df = ticker_obj.balance_sheet
    except Exception as exc:
        logger.warning("No se pudo extraer el balance de situación para %s: %s", clean_ticker, exc)

    try:
        cashflow_df = ticker_obj.cashflow
    except Exception as exc:
        logger.warning("No se pudo extraer el estado de flujos de caja para %s: %s", clean_ticker, exc)

    # Identificar las columnas de ejercicios anuales disponibles
    all_cols = []
    for df in [financials_df, balance_df, cashflow_df]:
        if df is not None and not df.empty:
            all_cols.extend(list(df.columns))

    if not all_cols:
        logger.warning("No se encontraron estados contables anuales para %s", clean_ticker)
        return info, [], is_bank

    # Deduplicar columnas temporales y ordenar descendente (ejercicio más reciente primero)
    unique_cols = sorted(list(set(all_cols)), reverse=True)[:4]

    statements: List[FinancialStatementYear] = []
    for col in unique_cols:
        try:
            year = col.year if hasattr(col, "year") else int(str(col)[:4])
        except Exception as exc:
            logger.warning("Error interpretando fecha de columna contable %s para %s: %s", col, clean_ticker, exc)
            continue

        revenue = _get_row_value(financials_df, ["Total Revenue", "Operating Revenue"], col) or 0.0
        gross_profit = _get_row_value(financials_df, ["Gross Profit"], col)
        operating_income = _get_row_value(financials_df, ["Operating Income", "Total Operating Income As Reported"], col)
        net_income = _get_row_value(financials_df, ["Net Income", "Net Income Common Stockholders"], col) or 0.0
        diluted_eps = _get_row_value(financials_df, ["Diluted EPS"], col)

        total_assets = _get_row_value(balance_df, ["Total Assets"], col) or 0.0
        current_assets = _get_row_value(balance_df, ["Current Assets"], col)
        current_liabilities = _get_row_value(balance_df, ["Current Liabilities"], col)
        long_term_debt = _get_row_value(balance_df, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], col)
        total_debt = _get_row_value(balance_df, ["Total Debt"], col)
        cash_and_equiv = _get_row_value(
            balance_df,
            ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash Financial"],
            col,
        )
        shares_out = _get_row_value(balance_df, ["Ordinary Shares Number", "Share Issued"], col)
        if shares_out is None and financials_df is not None:
            shares_out = _get_row_value(financials_df, ["Diluted Average Shares", "Basic Average Shares"], col)

        cfo = _get_row_value(cashflow_df, ["Operating Cash Flow"], col) or 0.0
        raw_capex = _get_row_value(cashflow_df, ["Capital Expenditure"], col) or 0.0
        capex = abs(raw_capex)

        fcf = _get_row_value(cashflow_df, ["Free Cash Flow"], col)
        if fcf is None:
            fcf = cfo - capex

        stmt = FinancialStatementYear(
            year=year,
            revenue=revenue,
            gross_profit=gross_profit,
            operating_income=operating_income,
            net_income=net_income,
            diluted_eps=diluted_eps,
            total_assets=total_assets,
            current_assets=current_assets,
            current_liabilities=current_liabilities,
            long_term_debt=long_term_debt,
            total_debt=total_debt,
            cash_and_equivalents=cash_and_equiv,
            operating_cash_flow=cfo,
            capital_expenditure=capex,
            free_cash_flow=fcf,
            shares_outstanding=shares_out,
        )
        statements.append(stmt)

    # Asegurar orden cronológico descendente (último año en índice 0)
    statements.sort(key=lambda s: s.year, reverse=True)
    return info, statements, is_bank


def calculate_piotroski_score(
    statements: List[FinancialStatementYear], is_bank: bool = False
) -> PiotroskiScore:
    """
    Calcula determinísticamente los 9 criterios del Piotroski F-Score a partir de los
    estados financieros de los dos últimos ejercicios fiscales disponibles.
    
    Para instituciones bancarias, se adaptan omitiendo Margen Bruto y Ratio Corriente,
    ajustando la puntuación máxima a 7 puntos.
    """
    criteria: List[PiotroskiCriterion] = []
    max_score = 7 if is_bank else 9

    if not statements:
        logger.warning("No hay estados contables disponibles para calcular el Piotroski F-Score.")
        return PiotroskiScore(
            total_score=0,
            max_score=max_score,
            rating="Riesgo Contable",
            criteria=[],
        )

    t = statements[0]
    t_prev = statements[1] if len(statements) > 1 else None

    # --- BLOQUE A: RENTABILIDAD (4 PUNTOS) ---
    # 1. ROA > 0
    roa_t = (t.net_income / t.total_assets) if t.total_assets > 0 else 0.0
    p1 = 1 if roa_t > 0 else 0
    criteria.append(
        PiotroskiCriterion(
            code="ROA",
            category="profitability",
            description="Retorno sobre Activos (ROA) positivo en el último ejercicio fiscal",
            points=p1,
            current_value=round(roa_t * 100.0, 2),
            previous_value=None,
        )
    )

    # 2. CFO > 0
    p2 = 1 if t.operating_cash_flow > 0 else 0
    criteria.append(
        PiotroskiCriterion(
            code="CFO",
            category="profitability",
            description="Flujo de caja operativo (CFO) positivo",
            points=p2,
            current_value=round(t.operating_cash_flow, 2),
            previous_value=None,
        )
    )

    # 3. Delta ROA > 0 (ROA_t > ROA_t-1)
    if t_prev and t_prev.total_assets > 0:
        roa_prev = t_prev.net_income / t_prev.total_assets
        p3 = 1 if roa_t > roa_prev else 0
        prev_val_p3 = round(roa_prev * 100.0, 2)
    else:
        p3 = 0
        prev_val_p3 = None
    criteria.append(
        PiotroskiCriterion(
            code="DELTA_ROA",
            category="profitability",
            description="Mejora interanual en el Retorno sobre Activos (ROA)",
            points=p3,
            current_value=round(roa_t * 100.0, 2),
            previous_value=prev_val_p3,
        )
    )

    # 4. Calidad del devengo contable: CFO > Beneficio Neto
    p4 = 1 if t.operating_cash_flow > t.net_income else 0
    criteria.append(
        PiotroskiCriterion(
            code="ACCRUAL",
            category="profitability",
            description="Calidad de devengo: el Flujo de Caja Operativo supera al Beneficio Neto",
            points=p4,
            current_value=round(t.operating_cash_flow, 2),
            previous_value=round(t.net_income, 2),
        )
    )

    # --- BLOQUE B: APALANCAMIENTO, LIQUIDEZ Y FONDOS (3 PUNTOS) ---
    # 5. Reducción de apalancamiento a largo plazo: (Deuda / Activos)_t <= (Deuda / Activos)_t-1
    if t_prev and t.total_assets > 0 and t_prev.total_assets > 0:
        debt_t = t.long_term_debt if t.long_term_debt is not None else (t.total_debt or 0.0)
        debt_prev = t_prev.long_term_debt if t_prev.long_term_debt is not None else (t_prev.total_debt or 0.0)
        lev_t = debt_t / t.total_assets
        lev_prev = debt_prev / t_prev.total_assets
        p5 = 1 if lev_t <= lev_prev else 0
        cur_val_p5 = round(lev_t * 100.0, 2)
        prev_val_p5 = round(lev_prev * 100.0, 2)
    else:
        p5 = 0
        cur_val_p5 = None
        prev_val_p5 = None
    criteria.append(
        PiotroskiCriterion(
            code="DELTA_LEVER",
            category="leverage_liquidity",
            description="Reducción o estabilidad en el ratio de apalancamiento financiero sobre activos",
            points=p5,
            current_value=cur_val_p5,
            previous_value=prev_val_p5,
        )
    )

    # 6. Mejora del Current Ratio: (Current Assets / Current Liabilities)_t > _prev
    if not is_bank:
        if (
            t_prev
            and t.current_assets is not None
            and t.current_liabilities
            and t.current_liabilities > 0
            and t_prev.current_assets is not None
            and t_prev.current_liabilities
            and t_prev.current_liabilities > 0
        ):
            cr_t = t.current_assets / t.current_liabilities
            cr_prev = t_prev.current_assets / t_prev.current_liabilities
            p6 = 1 if cr_t > cr_prev else 0
            cur_val_p6 = round(cr_t, 2)
            prev_val_p6 = round(cr_prev, 2)
        else:
            p6 = 0
            cur_val_p6 = None
            prev_val_p6 = None
        criteria.append(
            PiotroskiCriterion(
                code="DELTA_LIQUID",
                category="leverage_liquidity",
                description="Mejora en el ratio de liquidez corriente (Current Ratio)",
                points=p6,
                current_value=cur_val_p6,
                previous_value=prev_val_p6,
            )
        )

    # 7. Cero dilución accionarial: Shares_t <= Shares_t-1
    if t_prev and t.shares_outstanding is not None and t_prev.shares_outstanding is not None:
        p7 = 1 if t.shares_outstanding <= t_prev.shares_outstanding else 0
        cur_val_p7 = round(t.shares_outstanding, 0)
        prev_val_p7 = round(t_prev.shares_outstanding, 0)
    else:
        # Si no hay datos de acciones, no penalizar con 0 si recompró acciones en Cash Flow
        p7 = 1 if t_prev else 0
        cur_val_p7 = None
        prev_val_p7 = None
    criteria.append(
        PiotroskiCriterion(
            code="EQ_OFFER",
            category="leverage_liquidity",
            description="Ausencia de dilución accionarial (número de acciones igual o inferior al ejercicio anterior)",
            points=p7,
            current_value=cur_val_p7,
            previous_value=prev_val_p7,
        )
    )

    # --- BLOQUE C: EFICIENCIA OPERATIVA (2 PUNTOS) ---
    # 8. Mejora de margen bruto: (Gross Profit / Revenue)_t > _prev
    if not is_bank:
        if (
            t_prev
            and t.gross_profit is not None
            and t.revenue > 0
            and t_prev.gross_profit is not None
            and t_prev.revenue > 0
        ):
            gm_t = t.gross_profit / t.revenue
            gm_prev = t_prev.gross_profit / t_prev.revenue
            p8 = 1 if gm_t > gm_prev else 0
            cur_val_p8 = round(gm_t * 100.0, 2)
            prev_val_p8 = round(gm_prev * 100.0, 2)
        else:
            p8 = 0
            cur_val_p8 = None
            prev_val_p8 = None
        criteria.append(
            PiotroskiCriterion(
                code="DELTA_MARGIN",
                category="operating_efficiency",
                description="Mejora en el margen de beneficio bruto",
                points=p8,
                current_value=cur_val_p8,
                previous_value=prev_val_p8,
            )
        )

    # 9. Mejora de rotación de activos: (Revenue / Total Assets)_t > _prev
    if t_prev and t.total_assets > 0 and t_prev.total_assets > 0:
        turn_t = t.revenue / t.total_assets
        turn_prev = t_prev.revenue / t_prev.total_assets
        p9 = 1 if turn_t > turn_prev else 0
        cur_val_p9 = round(turn_t, 2)
        prev_val_p9 = round(turn_prev, 2)
    else:
        p9 = 0
        cur_val_p9 = None
        prev_val_p9 = None
    criteria.append(
        PiotroskiCriterion(
            code="DELTA_TURN",
            category="operating_efficiency",
            description="Aumento en la rotación de activos (eficiencia en la generación de ventas)",
            points=p9,
            current_value=cur_val_p9,
            previous_value=prev_val_p9,
        )
    )

    total_score = sum(c.points for c in criteria)

    # Clasificación cualitativa
    if is_bank:
        # Denominador 7
        if total_score >= 5:
            rating = "Excelente"
        elif total_score >= 3:
            rating = "Aceptable"
        else:
            rating = "Riesgo Contable"
    else:
        # Denominador 9
        if total_score >= 7:
            rating = "Excelente"
        elif total_score >= 4:
            rating = "Aceptable"
        else:
            rating = "Riesgo Contable"

    return PiotroskiScore(
        total_score=total_score,
        max_score=max_score,
        rating=rating,
        criteria=criteria,
    )


def calculate_fcf_metrics(
    statements: List[FinancialStatementYear],
    market_cap: Optional[float] = None,
    info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Calcula las métricas anuales y acumuladas de Flujo de Caja Libre (FCF),
    conversión de beneficios, rendimiento de FCF y diagnóstico preliminar de foso defensivo.
    """
    if not statements:
        return {
            "fcf_yield": None,
            "fcf_conversion_ratio": None,
            "reinvestment_rate": None,
            "fcf_avg_3y": None,
            "roe": None,
            "roic": None,
            "has_moat": False,
            "fcf_history": [],
        }

    latest = statements[0]
    info_dict = info or {}

    # Historial anual de FCF
    fcf_history = [
        {
            "year": s.year,
            "cfo": s.operating_cash_flow,
            "capex": s.capital_expenditure,
            "fcf": s.free_cash_flow,
            "net_income": s.net_income,
            "conversion": round((s.free_cash_flow / s.net_income), 2) if s.net_income > 0 else None,
        }
        for s in statements
    ]

    # FCF Yield
    fcf_yield = None
    if market_cap and market_cap > 0 and latest.free_cash_flow is not None:
        fcf_yield = round((latest.free_cash_flow / market_cap) * 100.0, 2)

    # Tasa de conversión de beneficio a caja en el último ejercicio
    fcf_conversion = None
    if latest.net_income > 0:
        fcf_conversion = round(latest.free_cash_flow / latest.net_income, 2)

    # Ratio de reinversión en CapEx sobre CFO
    reinvestment_rate = None
    if latest.operating_cash_flow > 0:
        reinvestment_rate = round((latest.capital_expenditure / latest.operating_cash_flow) * 100.0, 2)

    # Promedio FCF últimos 3 años disponibles
    recent_fcf = [s.free_cash_flow for s in statements[:3]]
    fcf_avg_3y = round(sum(recent_fcf) / len(recent_fcf), 2) if recent_fcf else None

    # ROE (Return on Equity)
    roe = _safe_float(info_dict.get("returnOnEquity"))
    if roe is not None and abs(roe) <= 1.0:
        roe = round(roe * 100.0, 2)
    elif roe is None and latest.total_assets > 0:
        # Estimación aproximada si no viene en info
        equity_est = latest.total_assets - (latest.total_debt or 0.0)
        if equity_est > 0:
            roe = round((latest.net_income / equity_est) * 100.0, 2)

    # ROIC (Return on Invested Capital estimado)
    roic = None
    ebit = latest.operating_income
    invested_capital = (latest.total_assets - (latest.current_liabilities or 0.0)) if latest.total_assets > 0 else 0.0
    if ebit is not None and invested_capital > 0:
        nopat = ebit * 0.75  # Asumiendo tipo impositivo efectivo medio del 25%
        roic = round((nopat / invested_capital) * 100.0, 2)

    # Diagnóstico de foso defensivo (Moat): ROE sostenido >= 15% o ROIC >= 12% y conversión de caja sólida
    has_moat = False
    if roe is not None and roe >= 15.0:
        has_moat = True
    elif roic is not None and roic >= 12.0:
        has_moat = True

    return {
        "fcf_yield": fcf_yield,
        "fcf_conversion_ratio": fcf_conversion,
        "reinvestment_rate": reinvestment_rate,
        "fcf_avg_3y": fcf_avg_3y,
        "roe": roe,
        "roic": roic,
        "has_moat": has_moat,
        "fcf_history": fcf_history,
    }


def get_equity_deepdive_data(ticker: str) -> Optional[DeepDiveResponse]:
    """
    Función orquestadora principal que extrae la información financiera histórica,
    calcula el Piotroski F-Score y genera las métricas de flujo de caja libre para un ticker.
    """
    clean_ticker = ticker.strip().upper()
    info, statements, is_bank = fetch_historical_financials(clean_ticker)

    price = _safe_float(
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or info.get("previousClose")
    )

    if price is None or price <= 0.0:
        # Si no hay cotización en info pero tenemos estados contables, intentar obtener precio del último día
        logger.warning("No se pudo obtener precio de cotización para %s", clean_ticker)
        if not statements:
            return None
        price = 1.0  # Fallback simbólico para evitar caída si hay estados

    # Variación diaria
    day_change_pct = _safe_float(info.get("regularMarketChangePercent"))
    if day_change_pct is not None and abs(day_change_pct) < 0.2 and abs(day_change_pct) > 0.0:
        day_change_pct = round(day_change_pct * 100.0, 2)

    market_cap = _safe_float(info.get("marketCap"))
    pe_trailing = _safe_float(info.get("trailingPE"))
    pe_forward = _safe_float(info.get("forwardPE"))
    ev_to_ebitda = _safe_float(info.get("enterpriseToEbitda"))
    price_to_book = _safe_float(info.get("priceToBook"))
    div_yield = _safe_float(info.get("dividendYield"))
    if div_yield is not None and abs(div_yield) <= 1.0:
        div_yield = round(div_yield * 100.0, 2)
    beta = _safe_float(info.get("beta"))

    piotroski = calculate_piotroski_score(statements, is_bank=is_bank)
    fcf_metrics = calculate_fcf_metrics(statements, market_cap=market_cap, info=info)

    return DeepDiveResponse(
        ticker=clean_ticker,
        name=info.get("shortName") or info.get("longName") or clean_ticker,
        sector=info.get("sector"),
        industry=info.get("industry"),
        country=info.get("country"),
        currency=info.get("currency") or "EUR",
        description=info.get("longBusinessSummary"),
        current_price=price,
        day_change_pct=day_change_pct,
        market_cap=market_cap,
        pe_trailing=pe_trailing,
        pe_forward=pe_forward,
        ev_to_ebitda=ev_to_ebitda,
        price_to_book=price_to_book,
        dividend_yield=div_yield,
        beta=beta,
        statements=statements,
        piotroski=piotroski,
        fcf_metrics=fcf_metrics,
        quality_value_report=None,
        is_financial_institution=is_bank,
        from_cache=False,
        updated_at=datetime.now(timezone.utc),
    )
