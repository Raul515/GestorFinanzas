from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import Optional


class TransactionBase(BaseModel):
    """Esquema base para transacciones financieras."""
    date: date
    subcategory_id: int
    amount: float
    description: Optional[str] = None
    applied_strategy_id: Optional[int] = None


class TransactionCreate(TransactionBase):
    """Esquema para creación de una nueva transacción contable."""
    pass


class Transaction(TransactionBase):
    """Esquema de respuesta para transacción persistida."""
    model_config = ConfigDict(from_attributes=True)

    id: int

