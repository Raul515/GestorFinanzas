from typing import TYPE_CHECKING
from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .categorias import Subcategoria

class PresupuestoMensual(Base):
    __tablename__ = "presupuestos_mensuales"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    mes: Mapped[str] = mapped_column(String, index=True) # Formato YYYY-MM
    subcategoria_id: Mapped[int] = mapped_column(ForeignKey("subcategorias.id"))
    cantidad: Mapped[float] = mapped_column(Float, default=0.0)

    subcategoria: Mapped["Subcategoria"] = relationship("Subcategoria", back_populates="presupuestos")


