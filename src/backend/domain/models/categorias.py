from typing import TYPE_CHECKING
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .presupuestos import PresupuestoMensual
    from .transacciones import Transaccion

class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String, unique=True, index=True)
    tipo: Mapped[str] = mapped_column(String)

    subcategorias: Mapped[list["Subcategoria"]] = relationship("Subcategoria", back_populates="categoria")

class Subcategoria(Base):
    __tablename__ = "subcategorias"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String, index=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))

    categoria: Mapped["Categoria"] = relationship("Categoria", back_populates="subcategorias")
    presupuestos: Mapped[list["PresupuestoMensual"]] = relationship("PresupuestoMensual", back_populates="subcategoria")
    transacciones: Mapped[list["Transaccion"]] = relationship("Transaccion", back_populates="subcategoria")


