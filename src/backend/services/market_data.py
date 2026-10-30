"""
Servicio de Datos Macroeconómicos de Mercado.
Extrae indicadores macroeconómicos con foco prioritario en España, la Eurozona y referencias globales.
Cubre:
- Renta Variable: IBEX 35, EuroStoxx 50, S&P 500, Nasdaq 100
- Deuda Soberana y Diferenciales: Bono Español 10A, Bund Alemán 10A, Prima de Riesgo de España, Bono EE.UU. 10A
Proporciona series sparkline de 30 días y degradación elegante con datos base de contingencia.
"""

from datetime import datetime
import logging
from typing import List, Optional, Tuple
import requests
import yfinance as yf

from backend.domain.schemas.latency_metrics import ExternalProviderEnum
from backend.domain.schemas.market import MacroIndicator, MacroOverviewResponse
from backend.services.latency_profiler import track_external_latency

logger = logging.getLogger(__name__)


def _extract_ticker_data(
    symbol: str,
    indicator_id: str,
    name: str,
    region: str,
    unit: str = "pts",
) -> MacroIndicator:
    """Extrae datos de cotización de Yahoo Finance: precio actual, variación porcentual y sparkline a 30 días."""
    try:
        with track_external_latency(ExternalProviderEnum.YAHOO_FINANCE, "ticker_history", target=symbol) as ctx:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period="1mo")
            ctx.status_code = 200

        if history is not None and not history.empty and "Close" in history:
            valid_closes = history["Close"].dropna()
            if len(valid_closes) >= 2:
                closes = [round(float(v), 2) for v in valid_closes.values]
                current = closes[-1]
                prev = closes[-2]
                change_abs = round(current - prev, 2)
                change_pct = round((change_abs / prev) * 100.0, 2) if prev > 0 else 0.0

                return MacroIndicator(
                    id=indicator_id,
                    name=name,
                    symbol=symbol,
                    region=region,
                    current_value=current,
                    change_pct=change_pct,
                    change_abs=change_abs,
                    unit=unit,
                    sparkline_30d=closes,
                    last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                )
    except Exception as exc:
        logger.warning("Fallo al extraer cotización histórica para '%s': %s. Utilizando valores base de contingencia.", symbol, exc)

    # Valores base de contingencia en caso de indisponibilidad temporal de la API externa
    baseline_values = {
        "^IBEX": (11850.0, 0.35, 41.5, "pts"),
        "^STOXX50E": (4950.0, 0.20, 9.8, "pts"),
        "^GSPC": (5800.0, 0.40, 23.2, "pts"),
        "^NDX": (20200.0, 0.55, 110.0, "pts"),
        "^TNX": (4.25, -0.02, -0.01, "%"),
    }
    cur, pct, diff, u = baseline_values.get(symbol, (100.0, 0.0, 0.0, unit))
    return MacroIndicator(
        id=indicator_id,
        name=name,
        symbol=symbol,
        region=region,
        current_value=cur,
        change_pct=pct,
        change_abs=diff,
        unit=u,
        sparkline_30d=[cur] * 15,
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def _fetch_ecb_series(url: str, default_val: float) -> Tuple[float, float, List[float]]:
    """Función auxiliar para obtener series de rendimiento recientes desde la API REST SDMX del Banco Central Europeo."""
    target_name = "bund_10y" if "SV_C_YM.SR_10Y" in url else ("spain_10y" if "IRS" in url else "ecb_series")
    try:
        with track_external_latency(ExternalProviderEnum.ECB, "yield_series", target=target_name) as ctx:
            res = requests.get(url, timeout=4)
            ctx.status_code = res.status_code

        if res.status_code == 200:
            data = res.json()
            datasets = data.get("dataSets", [])
            if datasets and "series" in datasets[0]:
                series_values = list(datasets[0]["series"].values())
                if series_values and "observations" in series_values[0]:
                    obs = series_values[0]["observations"]
                    vals = [round(float(v[0]), 2) for v in obs.values() if v and v[0] is not None]
                    if len(vals) >= 2:
                        cur = vals[-1]
                        prev = vals[-2]
                        diff = round(cur - prev, 2)
                        return cur, diff, vals
    except Exception as exc:
        logger.warning("Fallo al consultar serie del BCE en '%s': %s. Utilizando valor base de contingencia.", url, exc)
    return default_val, 0.0, [default_val] * 10


def fetch_sovereign_bonds_and_risk_premium() -> Tuple[MacroIndicator, MacroIndicator, MacroIndicator]:
    """
    Obtiene el Bono Español a 10A, el Bund Alemán a 10A y deriva matemáticamente la Prima de Riesgo de España:
    Prima de Riesgo (pb) = (Bono_España_10A - Bund_Alemania_10A) * 100
    """
    # 1. Bund Alemán 10A (Rendimiento soberano de referencia AAA en la Eurozona - BCE)
    bund_url = "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?lastNObservations=25&format=jsondata"
    bund_val, bund_diff, bund_spark = _fetch_ecb_series(bund_url, default_val=2.25)

    bund_ind = MacroIndicator(
        id="bund_de_10y",
        name="Bono Alemán 10A (Bund)",
        symbol="BUND10Y",
        region="Eurozona",
        current_value=bund_val,
        change_pct=bund_diff,
        change_abs=bund_diff,
        unit="%",
        sparkline_30d=bund_spark,
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    # 2. Bono Español 10A (Obligaciones del Estado a 10 años)
    spain_url = "https://data-api.ecb.europa.eu/service/data/IRS/M.ES.L.L40.CI.0000.EUR.N.Z?lastNObservations=25&format=jsondata"
    spain_val, spain_diff, spain_spark = _fetch_ecb_series(spain_url, default_val=3.00)

    spain_ind = MacroIndicator(
        id="bono_es_10y",
        name="Bono Español 10A",
        symbol="SPAIN10Y",
        region="España",
        current_value=spain_val,
        change_pct=spain_diff,
        change_abs=spain_diff,
        unit="%",
        sparkline_30d=spain_spark,
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    # 3. Prima de Riesgo de España en puntos básicos (pb)
    risk_premium_bps = round((spain_val - bund_val) * 100.0, 1)
    prev_premium = round(((spain_val - spain_diff) - (bund_val - bund_diff)) * 100.0, 1)
    premium_diff = round(risk_premium_bps - prev_premium, 1)

    # Generar sparkline alineado para la prima de riesgo
    min_len = min(len(spain_spark), len(bund_spark))
    premium_spark = [
        round((spain_spark[i] - bund_spark[i]) * 100.0, 1) for i in range(min_len)
    ]

    premium_ind = MacroIndicator(
        id="prima_riesgo_es",
        name="Prima de Riesgo España",
        symbol="SPREAD_ES_DE",
        region="España",
        current_value=risk_premium_bps,
        change_pct=premium_diff,
        change_abs=premium_diff,
        unit="pb",
        sparkline_30d=premium_spark if premium_spark else [risk_premium_bps] * 10,
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    return spain_ind, bund_ind, premium_ind


def get_macro_overview() -> List[MacroIndicator]:
    """Consolida los 8 activos e indicadores macroeconómicos priorizando España y Europa."""
    indicators: List[MacroIndicator] = []

    # 1. Renta Variable prioritaria: España y Eurozona
    indicators.append(
        _extract_ticker_data("^IBEX", "ibex35", "IBEX 35", "España", "pts")
    )
    indicators.append(
        _extract_ticker_data("^STOXX50E", "stoxx50", "EuroStoxx 50", "Eurozona", "pts")
    )

    # 2. Deuda Soberana prioritaria y Prima de Riesgo: España y Eurozona
    spain_bond, bund_bond, risk_premium = fetch_sovereign_bonds_and_risk_premium()
    indicators.extend([spain_bond, bund_bond, risk_premium])

    # 3. Renta Variable y Renta Fija Global de referencia (EE.UU.)
    indicators.append(
        _extract_ticker_data("^GSPC", "sp500", "S&P 500", "EE.UU.", "pts")
    )
    indicators.append(
        _extract_ticker_data("^NDX", "nasdaq100", "Nasdaq 100", "EE.UU.", "pts")
    )
    indicators.append(
        _extract_ticker_data("^TNX", "bono_us_10y", "Bono EE.UU. 10A", "EE.UU.", "%")
    )

    return indicators


def get_macro_overview_response(is_cached: bool = False) -> MacroOverviewResponse:
    """Consolida todos los indicadores macroeconómicos en una respuesta tipada MacroOverviewResponse."""
    indicators = get_macro_overview()
    return MacroOverviewResponse(
        indicators=indicators,
        fetched_at=datetime.now(),
        is_cached=is_cached,
        source_notes="Datos extraídos de Yahoo Finance y BCE",
    )

