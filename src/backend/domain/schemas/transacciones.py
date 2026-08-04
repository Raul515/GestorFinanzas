from pydantic import BaseModel
from datetime import date
from typing import Optional

class TransaccionBase(BaseModel):
    fecha: date
    subcategoria_id: int
    cantidad: float
    concepto: Optional[str] = None

class TransaccionCreate(TransaccionBase):
    pass

class Transaccion(TransaccionBase):
    id: int

    class Config:
        from_attributes = True
