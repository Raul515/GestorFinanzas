from pydantic import BaseModel, ConfigDict


class MonthlyBudgetBase(BaseModel):
    """Esquema base para asignaciones presupuestarias."""
    month: str
    subcategory_id: int
    amount: float


class MonthlyBudgetCreate(MonthlyBudgetBase):
    """Esquema para creación o actualización de presupuesto mensual."""
    pass


class MonthlyBudget(MonthlyBudgetBase):
    """Esquema de respuesta para presupuesto mensual persistido."""
    model_config = ConfigDict(from_attributes=True)

    id: int

