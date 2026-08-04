from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date
from sqlalchemy.orm import relationship
from .base import Base

class Transaccion(Base):
    __tablename__ = "transacciones"

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, index=True)
    subcategoria_id = Column(Integer, ForeignKey("subcategorias.id"))
    cantidad = Column(Float)
    concepto = Column(String)

    subcategoria = relationship("Subcategoria", back_populates="transacciones")
