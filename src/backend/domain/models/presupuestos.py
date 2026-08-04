from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class PresupuestoMensual(Base):
    __tablename__ = "presupuestos_mensuales"

    id = Column(Integer, primary_key=True, index=True)
    mes = Column(String, index=True) # Formato YYYY-MM
    subcategoria_id = Column(Integer, ForeignKey("subcategorias.id"))
    cantidad = Column(Float, default=0.0)

    subcategoria = relationship("Subcategoria", back_populates="presupuestos")
