from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class WatchlistCreate(BaseModel):
    """Esquema para la adición o actualización de un activo en la lista de seguimiento."""
    ticker: str = Field(..., min_length=1, max_length=20, description="Símbolo bursátil del activo, ej. ITX.MC o AAPL")
    name: str = Field(..., min_length=1, max_length=100, description="Nombre de la empresa o activo")
    sector: Optional[str] = Field(default=None, max_length=100, description="Sector macroeconómico o industria")
    currency: str = Field(default="EUR", max_length=10, description="Divisa de cotización")
    price_at_addition: float = Field(..., ge=0.0, description="Precio de cotización en el momento de adición")
    notes: Optional[str] = Field(default=None, max_length=1000, description="Notas personales de inversión o precios objetivo")


class WatchlistResponse(WatchlistCreate):
    """Esquema de respuesta para un activo en la lista de seguimiento con marca de tiempo de creación."""
    created_at: datetime = Field(..., description="Fecha y hora de incorporación a la lista")

    model_config = ConfigDict(from_attributes=True)
