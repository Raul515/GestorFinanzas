from pydantic import BaseModel

class PresupuestoMensualBase(BaseModel):
    mes: str
    subcategoria_id: int
    cantidad: float

class PresupuestoMensualCreate(PresupuestoMensualBase):
    pass

class PresupuestoMensual(PresupuestoMensualBase):
    id: int

    class Config:
        from_attributes = True
