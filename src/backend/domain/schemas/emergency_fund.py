from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmergencyFundBase(BaseModel):
    current_balance: float = Field(default=0.0, ge=0.0, description="Saldo actual en el fondo (€)")
    target_months: int = Field(default=3, ge=3, description="Meses de cobertura objetivo (mínimo 3 por Constitución)")

    @field_validator("target_months")
    @classmethod
    def validate_target_months(cls, v: int) -> int:
        if v < 3:
            raise ValueError("El número de meses de cobertura no puede ser inferior a 3 (regla constitucional).")
        return v


class EmergencyFundConfigUpdate(BaseModel):
    target_months: Optional[int] = Field(default=None, ge=3, description="Nuevo objetivo de meses")
    current_balance: Optional[float] = Field(default=None, ge=0.0, description="Ajuste manual de saldo acumulado")

    @field_validator("target_months")
    @classmethod
    def validate_target_months(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 3:
            raise ValueError("El número de meses de cobertura no puede ser inferior a 3 (regla constitucional).")
        return v


class EmergencyFundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    current_balance: float
    target_months: int
    target_amount: float
    is_completed: bool
    updated_at: datetime


class SafetyStatusResponse(BaseModel):
    """Diagnóstico detallado devuelto por el servicio Safety Guard."""
    model_config = ConfigDict(from_attributes=True)

    current_balance: float
    target_amount: float
    coverage_months: float
    target_months: int
    monthly_needs_reference: float
    is_completed: bool
    can_invest: bool
    gap: float
    message: str
    investing_allowed: Optional[bool] = None
    target_3m: Optional[float] = None
