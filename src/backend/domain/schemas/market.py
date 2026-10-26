from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ImpactLevel(str, Enum):
    """Nivel de impacto financiero para un residente en España."""
    HIGH = "Alto"
    MEDIUM = "Medio"
    LOW = "Bajo"


class NewsTopic(str, Enum):
    """Temática contextual para catalogar las noticias económicas."""
    MONETARY_POLICY = "Política Monetaria BCE / Tipos e Hipotecas"
    MACROECONOMY = "Macroeconomía España y Eurozona"
    CORPORATE_EARNINGS = "Resultados Empresariales"
    GEOPOLITICS_GLOBAL = "Geopolítica y Mercados Globales"


class MacroIndicator(BaseModel):
    """Métrica o activo macroeconómico con cotización actual, variación y serie a 30 días."""
    id: str
    name: str
    symbol: str
    region: str
    current_value: float
    change_pct: float
    change_abs: float
    unit: str  # "pts", "%", "pb" (puntos básicos)
    sparkline_30d: List[float] = Field(default_factory=list)
    last_updated: Optional[str] = None


class MacroOverviewResponse(BaseModel):
    """Resumen consolidado de indicadores macroeconómicos."""
    model_config = ConfigDict(from_attributes=True)

    indicators: List[MacroIndicator]
    fetched_at: datetime
    is_cached: bool = False
    source_notes: str = "Datos extraídos de Yahoo Finance y BCE"


class NewsItem(BaseModel):
    """Noticia financiera capturada de fuente pública."""
    id: str
    title: str
    link: str
    source: str
    published_at: Optional[str] = None


class AnalyzedNewsItem(NewsItem):
    """Noticia financiera evaluada y sintetizada con inteligencia artificial."""
    impact: str = ImpactLevel.MEDIUM.value
    topic: str = NewsTopic.MACROECONOMY.value
    summary: str


class MarketNewsResponse(BaseModel):
    """Respuesta agregada de noticias financieras con análisis de IA y degradación elegante."""
    model_config = ConfigDict(from_attributes=True)

    news: List[AnalyzedNewsItem] = Field(default_factory=list)
    fetched_at: datetime
    is_cached: bool = False
    ai_analysis_available: bool = True
    notes: Optional[str] = None


class MarketRefreshResponse(BaseModel):
    """Respuesta consolidada tras forzar el refresco de indicadores y noticias."""
    model_config = ConfigDict(from_attributes=True)

    message: str = "Radar de mercado y noticias actualizado con éxito"
    macro_indicators: MacroOverviewResponse
    news: MarketNewsResponse


