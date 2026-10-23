from typing import TYPE_CHECKING
from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from .base import Base

if TYPE_CHECKING:
    from .categories import Subcategory


class MonthlyBudget(Base):
    """Modelo ORM para asignaciones presupuestarias mensuales (formato YYYY-MM o BASE)."""
    __tablename__ = "monthly_budgets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    month: Mapped[str] = mapped_column(String, index=True)  # Formato YYYY-MM o BASE
    subcategory_id: Mapped[int] = mapped_column(ForeignKey("subcategories.id"))
    amount: Mapped[float] = mapped_column(Float, default=0.0)

    subcategory: Mapped["Subcategory"] = relationship("Subcategory", back_populates="budgets")

    def __init__(self, *args, **kwargs):
        # Soporte de argumentos con nombres en español para retrocompatibilidad
        if "mes" in kwargs and "month" not in kwargs:
            kwargs["month"] = kwargs.pop("mes")
        if "cantidad" in kwargs and "amount" not in kwargs:
            kwargs["amount"] = kwargs.pop("cantidad")
        if "subcategoria_id" in kwargs and "subcategory_id" not in kwargs:
            kwargs["subcategory_id"] = kwargs.pop("subcategoria_id")
        super().__init__(*args, **kwargs)


    @hybrid_property
    def mes(self):
        return self.month

    @mes.setter
    def mes(self, value: str):
        self.month = value

    @hybrid_property
    def cantidad(self):
        return self.amount

    @cantidad.setter
    def cantidad(self, value: float):
        self.amount = value

    @hybrid_property
    def subcategoria_id(self):
        return self.subcategory_id

    @subcategoria_id.setter
    def subcategoria_id(self, value: int):
        self.subcategory_id = value

