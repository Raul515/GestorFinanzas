"""
Servicio desacoplado para el Screener Fundamental de Acciones y ETFs (Spec 002 - Fase 2).
Gestiona universos modulares, extracción cuantitativa resiliente con Yahoo Finance y motor de filtrado puro.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence, Union
import yfinance as yf

from backend.domain.schemas.screener import (
    ETFScreenerItem,
    ScreenerFilterParams,
    ScreenerItem,
    ScreenerPresetEnum,
    StockScreenerItem,
    UniverseInfo,
)

logger = logging.getLogger(__name__)

# --- UNIVERSOS PREDEFINIDOS ---

IBEX_35_TICKERS: List[str] = [
    "ANA.MC", "ANE.MC", "ACX.MC", "ACS.MC", "AENA.MC", "AMS.MC", "BBVA.MC", "BKT.MC",
    "CABK.MC", "CLNX.MC", "COL.MC", "ELE.MC", "ENG.MC", "FDR.MC", "FER.MC", "GRF.MC",
    "IAG.MC", "IBE.MC", "IDR.MC", "ITX.MC", "LOG.MC", "MAP.MC", "MEL.MC", "MRL.MC",
    "NTGY.MC", "RED.MC", "REP.MC", "ROVI.MC", "SAB.MC", "SAN.MC", "SCYR.MC", "SLR.MC",
    "TEF.MC", "UNI.MC", "VIS.MC",
]

EUROSTOXX_50_TICKERS: List[str] = [
    "ABI.BR", "AD.AS", "AIR.PA", "ALV.DE", "ASML.AS", "BAS.DE", "BAYN.DE", "BBVA.MC",
    "BMW.DE", "BN.PA", "BNP.PA", "CRH.L", "CS.PA", "DG.PA", "DHL.DE", "DTE.DE",
    "EL.PA", "ENEL.MI", "ENI.MI", "FLTR.L", "HER.PA", "IBE.MC", "IFX.DE", "INGA.AS",
    "ISP.MI", "ITX.MC", "KER.PA", "KNEBV.HE", "MC.PA", "MBG.DE", "MUV2.DE", "NDA-FI.HE",
    "NOKIA.HE", "OR.PA", "ORAN.PA", "PRX.AS", "RI.PA", "RMS.PA", "SAF.PA", "SAN.MC",
    "SAN.PA", "SAP.DE", "SIE.DE", "STLAM.MI", "SU.PA", "TTE.PA", "UCG.MI", "VIV.PA",
    "VOW3.DE", "ENGI.PA",
]

SP500_TOP50_TICKERS: List[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "TSLA", "AVGO", "LLY",
    "JPM", "V", "UNH", "WMT", "XOM", "MA", "JNJ", "PG", "HD", "COST",
    "MRK", "ABBV", "CVX", "KO", "BAC", "PEP", "CRM", "NFLX", "TMO", "AMD",
    "WFC", "LIN", "ADBE", "ACN", "MCD", "DIS", "CSCO", "ABT", "QCOM", "GE",
    "CAT", "INTU", "VZ", "TXN", "IBM", "AMAT", "PM", "NOW", "PFE", "BKNG",
]

UCITS_ETFS_TICKERS: List[str] = [
    "VWCE.DE", "CSPX.AS", "IWDA.AS", "EUNL.DE", "MEUD.PA", "VAGF.DE", "VHYL.AS",
    "EQAC.DE", "QDVE.DE", "SX5EEX.DE", "IS3N.DE", "EMIM.AS", "SJPA.DE", "EXXT.DE", "VFEA.DE",
]

UNIVERSES_METADATA: Dict[str, UniverseInfo] = {
    "ibex35": UniverseInfo(
        id="ibex35",
        name="IBEX 35",
        description="Los 35 valores más representativos y líquidos del mercado continuo español",
        asset_type="stock",
        ticker_count=len(IBEX_35_TICKERS),
    ),
    "eurostoxx50": UniverseInfo(
        id="eurostoxx50",
        name="EuroStoxx 50",
        description="Las 50 mayores empresas cotizadas líderes de la Eurozona",
        asset_type="stock",
        ticker_count=len(EUROSTOXX_50_TICKERS),
    ),
    "sp500_top50": UniverseInfo(
        id="sp500_top50",
        name="S&P 500 Top 50",
        description="Las 50 principales empresas por capitalización bursátil de Estados Unidos",
        asset_type="stock",
        ticker_count=len(SP500_TOP50_TICKERS),
    ),
    "etfs_referencia": UniverseInfo(
        id="etfs_referencia",
        name="ETFs de Referencia (UCITS)",
        description="Cesta de fondos indexados cotizados UCITS líderes negociables en Europa",
        asset_type="etf",
        ticker_count=len(UCITS_ETFS_TICKERS),
    ),
    "custom": UniverseInfo(
        id="custom",
        name="Tickers Personalizados",
        description="Cesta a medida de acciones o ETFs configurada bajo demanda por el usuario",
        asset_type="mixed",
        ticker_count=0,
    ),
}


# --- FUNCIONES DE EXTRACCIÓN Y NORMALIZACIÓN ---

def _clean_percentage(val: Any, treat_as_ratio: bool = True) -> Optional[float]:
    """Convierte ratios decimales (ej. 0.045) en porcentajes limpios (4.50%)."""
    if val is None:
        return None
    try:
        fval = float(val)
        if treat_as_ratio and abs(fval) <= 1.0:
            return round(fval * 100.0, 2)
        return round(fval, 2)
    except (ValueError, TypeError):
        return None


def fetch_stock_item(ticker: str, info_dict: Optional[Dict[str, Any]] = None) -> Optional[StockScreenerItem]:
    """Extrae y normaliza los ratios contables y cotización de una acción."""
    try:
        info = info_dict if info_dict is not None else yf.Ticker(ticker).info
        if not info or not isinstance(info, dict):
            logger.warning("No se recibieron datos para el ticker %s", ticker)
            return None

        price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
            or 0.0
        )
        if price <= 0.0:
            logger.warning("Precio no disponible o inválido para %s (precio: %s)", ticker, price)
            return None

        # Variación porcentual
        change_pct = info.get("regularMarketChangePercent")
        if change_pct is None:
            prev_close = info.get("previousClose")
            if prev_close and prev_close > 0:
                change_pct = ((price - prev_close) / prev_close) * 100.0
            else:
                change_pct = 0.0
        elif abs(change_pct) < 0.2 and abs(change_pct) > 0.0:
            # En ocasiones yfinance devuelve regularMarketChangePercent como 0.015 en vez de 1.5%
            change_pct = change_pct * 100.0

        # Ratios de valoración
        pe_trailing = info.get("trailingPE")
        pe_forward = info.get("forwardPE")
        pb_ratio = info.get("priceToBook")
        ev_to_ebitda = info.get("enterpriseToEbitda")

        # Ratios de rentabilidad y márgenes en %
        dividend_yield = _clean_percentage(info.get("dividendYield"), treat_as_ratio=True)
        roe = _clean_percentage(info.get("returnOnEquity"), treat_as_ratio=True)
        op_margin = _clean_percentage(info.get("operatingMargins"), treat_as_ratio=True)
        net_margin = _clean_percentage(info.get("profitMargins"), treat_as_ratio=True)

        # Solvencia
        # En yfinance debtToEquity suele venir expresado en porcentaje (ej. 120.5 para 120.5%)
        debt_to_equity = info.get("debtToEquity")
        if debt_to_equity is not None:
            debt_to_equity = round(float(debt_to_equity), 2)
        current_ratio = info.get("currentRatio")
        if current_ratio is not None:
            current_ratio = round(float(current_ratio), 2)

        return StockScreenerItem(
            ticker=ticker.upper(),
            name=info.get("shortName") or info.get("longName") or ticker.upper(),
            sector=info.get("sector"),
            country=info.get("country"),
            currency=info.get("currency") or "EUR",
            price=round(float(price), 2),
            change_pct=round(float(change_pct), 2),
            market_cap=info.get("marketCap"),
            beta=round(float(info["beta"]), 2) if info.get("beta") is not None else None,
            pe_trailing=round(float(pe_trailing), 2) if pe_trailing is not None else None,
            pe_forward=round(float(pe_forward), 2) if pe_forward is not None else None,
            pb_ratio=round(float(pb_ratio), 2) if pb_ratio is not None else None,
            ev_to_ebitda=round(float(ev_to_ebitda), 2) if ev_to_ebitda is not None else None,
            dividend_yield=dividend_yield,
            roe=roe,
            operating_margin=op_margin,
            net_margin=net_margin,
            debt_to_equity=debt_to_equity,
            current_ratio=current_ratio,
            asset_type="stock",
        )
    except Exception as exc:
        logger.error("Error al procesar acción %s: %s", ticker, exc)
        return None


def fetch_etf_item(ticker: str, info_dict: Optional[Dict[str, Any]] = None) -> Optional[ETFScreenerItem]:
    """Extrae y normaliza las métricas operativas de un ETF cotizado."""
    try:
        info = info_dict if info_dict is not None else yf.Ticker(ticker).info
        if not info or not isinstance(info, dict):
            logger.warning("No se recibieron datos para el ETF %s", ticker)
            return None

        price = (
            info.get("navPrice")
            or info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
            or 0.0
        )
        if price <= 0.0:
            logger.warning("Precio no disponible para ETF %s", ticker)
            return None

        change_pct = info.get("regularMarketChangePercent")
        if change_pct is None:
            prev_close = info.get("previousClose")
            if prev_close and prev_close > 0:
                change_pct = ((price - prev_close) / prev_close) * 100.0
            else:
                change_pct = 0.0
        elif abs(change_pct) < 0.2 and abs(change_pct) > 0.0:
            change_pct = change_pct * 100.0

        # TER (Total Expense Ratio)
        exp_ratio = info.get("annualReportExpenseRatio") or info.get("netExpenseRatio")
        expense_ratio = _clean_percentage(exp_ratio, treat_as_ratio=True)

        div_yield = info.get("yield") or info.get("dividendYield")
        dividend_yield = _clean_percentage(div_yield, treat_as_ratio=True)

        total_assets = info.get("totalAssets")
        avg_volume = info.get("averageVolume") or info.get("averageDailyVolume10Day")

        return ETFScreenerItem(
            ticker=ticker.upper(),
            name=info.get("shortName") or info.get("longName") or ticker.upper(),
            category=info.get("category"),
            currency=info.get("currency") or "EUR",
            price=round(float(price), 2),
            change_pct=round(float(change_pct), 2),
            expense_ratio=expense_ratio,
            dividend_yield=dividend_yield,
            total_assets=float(total_assets) if total_assets is not None else None,
            avg_volume=float(avg_volume) if avg_volume is not None else None,
            beta=round(float(info["beta"]), 2) if info.get("beta") is not None else None,
            asset_type="etf",
        )
    except Exception as exc:
        logger.error("Error al procesar ETF %s: %s", ticker, exc)
        return None


def fetch_universe_data(universe_id: str) -> List[ScreenerItem]:
    """Descarga los tickers correspondientes a un universo modular predefinido."""
    tickers: List[str] = []
    is_etf_universe = False

    if universe_id == "ibex35":
        tickers = IBEX_35_TICKERS
    elif universe_id == "eurostoxx50":
        tickers = EUROSTOXX_50_TICKERS
    elif universe_id == "sp500_top50":
        tickers = SP500_TOP50_TICKERS
    elif universe_id == "etfs_referencia":
        tickers = UCITS_ETFS_TICKERS
        is_etf_universe = True
    else:
        logger.warning("Universo no reconocido: %s", universe_id)
        return []

    items: List[ScreenerItem] = []
    for t in tickers:
        item = fetch_etf_item(t) if is_etf_universe else fetch_stock_item(t)
        if item is not None:
            items.append(item)
    return items


def fetch_custom_tickers(tickers: List[str]) -> List[ScreenerItem]:
    """Descarga y autodetecta una lista personalizada de tickers (máximo 50)."""
    items: List[ScreenerItem] = []
    cleaned_tickers = [t.strip().upper() for t in tickers if t.strip()][:50]

    for ticker in cleaned_tickers:
        try:
            info = yf.Ticker(ticker).info
            quote_type = (info.get("quoteType") or "").upper() if isinstance(info, dict) else ""
            if quote_type in ("ETF", "MUTUALFUND"):
                item = fetch_etf_item(ticker, info_dict=info)
            else:
                item = fetch_stock_item(ticker, info_dict=info)

            if item is not None:
                items.append(item)
        except Exception as exc:
            logger.warning("Fallo al inspeccionar ticker personalizado %s: %s", ticker, exc)
    return items


# --- MOTOR DE FILTRADO PURO ---

def apply_screener_filters(
    items: Sequence[ScreenerItem],
    params: Optional[ScreenerFilterParams] = None,
) -> List[ScreenerItem]:
    """Aplica filtros numéricos, presets y búsqueda en memoria a una colección de activos."""
    if not params:
        return list(items)

    filtered: List[ScreenerItem] = []
    query = params.search_query.strip().lower() if params.search_query else None

    for item in items:
        # 1. Búsqueda por texto (ticker o nombre o sector)
        if query:
            match_ticker = query in item.ticker.lower()
            match_name = query in item.name.lower()
            match_sector = False
            if isinstance(item, StockScreenerItem) and item.sector:
                match_sector = query in item.sector.lower()

            if not (match_ticker or match_name or match_sector):
                continue

        # 2. Filtro por Preset
        preset = params.preset or ScreenerPresetEnum.ALL
        if preset != ScreenerPresetEnum.ALL:
            if preset == ScreenerPresetEnum.QUALITY:
                if not isinstance(item, StockScreenerItem):
                    continue
                if item.roe is None or item.roe < 15.0:
                    continue
                if item.net_margin is None or item.net_margin < 10.0:
                    continue
                if item.debt_to_equity is not None and item.debt_to_equity > 120.0:
                    continue

            elif preset == ScreenerPresetEnum.HIGH_DIVIDEND:
                if isinstance(item, StockScreenerItem):
                    if item.dividend_yield is None or item.dividend_yield < 3.5:
                        continue
                    # PER adelantado <= 18 (o trailing si no hay forward)
                    pe_check = item.pe_forward if item.pe_forward is not None else item.pe_trailing
                    if pe_check is not None and pe_check > 18.0:
                        continue
                    if item.debt_to_equity is not None and item.debt_to_equity > 150.0:
                        continue
                elif isinstance(item, ETFScreenerItem):
                    if item.dividend_yield is None or item.dividend_yield < 3.5:
                        continue

            elif preset == ScreenerPresetEnum.VALUE:
                if not isinstance(item, StockScreenerItem):
                    continue
                if item.pe_trailing is None or item.pe_trailing <= 0 or item.pe_trailing > 15.0:
                    continue
                if item.pb_ratio is None or item.pb_ratio > 2.0:
                    continue
                if item.dividend_yield is None or item.dividend_yield < 2.0:
                    continue

            elif preset == ScreenerPresetEnum.GROWTH:
                if not isinstance(item, StockScreenerItem):
                    continue
                if item.operating_margin is None or item.operating_margin < 15.0:
                    continue
                if item.roe is None or item.roe < 12.0:
                    continue
                if item.beta is not None and item.beta < 0.9:
                    continue

            elif preset == ScreenerPresetEnum.LOW_COST_ETF:
                if not isinstance(item, ETFScreenerItem):
                    continue
                if item.expense_ratio is None or item.expense_ratio > 0.25:
                    continue
                if item.total_assets is not None and item.total_assets < 500_000_000:
                    continue

        # 3. Filtros numéricos manuales
        if isinstance(item, StockScreenerItem):
            if params.max_pe is not None:
                if item.pe_trailing is None or item.pe_trailing > params.max_pe:
                    continue
            if params.min_roe is not None:
                if item.roe is None or item.roe < params.min_roe:
                    continue
            if params.max_debt_to_equity is not None:
                if item.debt_to_equity is not None and item.debt_to_equity > params.max_debt_to_equity:
                    continue

        if isinstance(item, ETFScreenerItem):
            if params.max_expense_ratio is not None:
                if item.expense_ratio is None or item.expense_ratio > params.max_expense_ratio:
                    continue

        # Filtro de dividendo común para acciones y ETFs
        if params.min_dividend_yield is not None:
            if item.dividend_yield is None or item.dividend_yield < params.min_dividend_yield:
                continue

        filtered.append(item)

    return filtered
