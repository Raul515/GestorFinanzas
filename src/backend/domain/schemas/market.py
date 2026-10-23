from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


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
