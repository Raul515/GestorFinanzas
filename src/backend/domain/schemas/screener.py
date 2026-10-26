from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class ScreenerPresetEnum(str, Enum):
    """Estrategias de cribado cuantitativo predefinidas."""
    ALL = "all"
    QUALITY = "quality"
    HIGH_DIVIDEND = "high_dividend"
    VALUE = "value"
    GROWTH = "growth"
    LOW_COST_ETF = "low_cost_etf"


class UniverseInfo(BaseModel):
    """Metadatos descriptivos de un universo de activos disponible."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    asset_type: Literal["stock", "etf", "mixed"] = "stock"
    ticker_count: int


class StockScreenerItem(BaseModel):
    """Métricas cuantitativas y fundamentales de una acción de renta variable."""
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str
    sector: Optional[str] = None
    country: Optional[str] = None
    currency: str = "EUR"
    price: float
    change_pct: float
    market_cap: Optional[float] = None
    beta: Optional[float] = None

    # Múltiplos de valoración
    pe_trailing: Optional[float] = None
    pe_forward: Optional[float] = None
    pb_ratio: Optional[float] = None
    ev_to_ebitda: Optional[float] = None

    # Métricas de rentabilidad y márgenes (en porcentaje, ej. 12.5 para 12.5%)
    dividend_yield: Optional[float] = None
    roe: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None

    # Métricas de solvencia
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None

    asset_type: Literal["stock"] = "stock"


class ETFScreenerItem(BaseModel):
    """Métricas cuantitativas y operativas de un ETF indexado cotizado."""
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str
    category: Optional[str] = None
    currency: str = "EUR"
    price: float
    change_pct: float

    expense_ratio: Optional[float] = None  # Ratio de Gastos Totales (TER en %)
    dividend_yield: Optional[float] = None  # Rentabilidad por dividendo en %
    total_assets: Optional[float] = None    # Patrimonio gestionado (AUM)
    avg_volume: Optional[float] = None
    beta: Optional[float] = None

    asset_type: Literal["etf"] = "etf"


ScreenerItem = Union[StockScreenerItem, ETFScreenerItem]


class ScreenerFilterParams(BaseModel):
    """Parámetros y umbrales para el filtrado en memoria de activos."""
    preset: Optional[ScreenerPresetEnum] = ScreenerPresetEnum.ALL
    max_pe: Optional[float] = None
    min_dividend_yield: Optional[float] = None
    min_roe: Optional[float] = None
    max_debt_to_equity: Optional[float] = None
    max_expense_ratio: Optional[float] = None
    search_query: Optional[str] = None


class ScreenerResponse(BaseModel):
    """Respuesta consolidada del screener con metadatos de caché y conteo de activos."""
    model_config = ConfigDict(from_attributes=True)

    universe: str
    asset_type: str
    updated_at: datetime
    from_cache: bool = False
    total_count: int
    filtered_count: int
    items: List[ScreenerItem] = Field(default_factory=list)
    notes: Optional[str] = None
