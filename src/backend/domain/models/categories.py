from typing import TYPE_CHECKING
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from .base import Base

if TYPE_CHECKING:
    from .budgets import MonthlyBudget
    from .transactions import Transaction


class Category(Base):
    """Modelo ORM para categorías contables principales (ingresos, necesidades, deseos, ahorro)."""
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    type: Mapped[str] = mapped_column(String)

    subcategories: Mapped[list["Subcategory"]] = relationship("Subcategory", back_populates="category")

    def __init__(self, *args, **kwargs):
        # Soporte de argumentos con nombres en español para retrocompatibilidad
        if "nombre" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs.pop("nombre")
        if "tipo" in kwargs and "type" not in kwargs:
            kwargs["type"] = kwargs.pop("tipo")
        super().__init__(*args, **kwargs)

    @hybrid_property
    def nombre(self):
        """Propiedad híbrida para acceder al nombre en español."""
        return self.name

    @nombre.setter
    def nombre(self, value: str):
        self.name = value

    @hybrid_property
    def tipo(self):
        """Propiedad híbrida para acceder al tipo en español."""
        return self.type

    @tipo.setter
    def tipo(self, value: str):
        self.type = value


class Subcategory(Base):
    """Modelo ORM para subcategorías contables asociadas a una categoría principal."""
    __tablename__ = "subcategories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    category: Mapped["Category"] = relationship("Category", back_populates="subcategories")
    budgets: Mapped[list["MonthlyBudget"]] = relationship("MonthlyBudget", back_populates="subcategory")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="subcategory")

    def __init__(self, *args, **kwargs):
        if "nombre" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs.pop("nombre")
        if "categoria_id" in kwargs and "category_id" not in kwargs:

            kwargs["category_id"] = kwargs.pop("categoria_id")
        super().__init__(*args, **kwargs)

    @hybrid_property
    def nombre(self):
        return self.name

    @nombre.setter
    def nombre(self, value: str):
        self.name = value

    @hybrid_property
    def categoria_id(self):
        return self.category_id

    @categoria_id.setter
    def categoria_id(self, value: int):
        self.category_id = value

