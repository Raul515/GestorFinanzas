import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Float, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .categorias import Subcategoria

class Transaccion(Base):
    __tablename__ = "transacciones"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    fecha: Mapped[datetime.date] = mapped_column(Date, index=True)
    subcategoria_id: Mapped[int] = mapped_column(ForeignKey("subcategorias.id"))
    cantidad: Mapped[float] = mapped_column(Float)
    concepto: Mapped[str] = mapped_column(String)

    subcategoria: Mapped["Subcategoria"] = relationship("Subcategoria", back_populates="transacciones")


