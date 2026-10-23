import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Float, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from .base import Base

if TYPE_CHECKING:
    from .categories import Subcategory


class Transaction(Base):
    """Modelo ORM para transacciones financieras reales (gastos, aportaciones o ingresos)."""
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    date: Mapped[datetime.date] = mapped_column(Date, index=True)
    subcategory_id: Mapped[int] = mapped_column(ForeignKey("subcategories.id"))
    amount: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String)

    subcategory: Mapped["Subcategory"] = relationship("Subcategory", back_populates="transactions")

    def __init__(self, *args, **kwargs):
        # Soporte de argumentos con nombres en español para retrocompatibilidad
        if "fecha" in kwargs and "date" not in kwargs:
            kwargs["date"] = kwargs.pop("fecha")
        if "cantidad" in kwargs and "amount" not in kwargs:
            kwargs["amount"] = kwargs.pop("cantidad")
        if "concepto" in kwargs and "description" not in kwargs:
            kwargs["description"] = kwargs.pop("concepto")
        if "subcategoria_id" in kwargs and "subcategory_id" not in kwargs:
            kwargs["subcategory_id"] = kwargs.pop("subcategoria_id")
        super().__init__(*args, **kwargs)


    @hybrid_property
    def fecha(self):
        return self.date

    @fecha.setter
    def fecha(self, value: datetime.date):
        self.date = value

    @hybrid_property
    def cantidad(self):
        return self.amount

    @cantidad.setter
    def cantidad(self, value: float):
        self.amount = value

    @hybrid_property
    def concepto(self):
        return self.description

    @concepto.setter
    def concepto(self, value: str):
        self.description = value

    @hybrid_property
    def subcategoria_id(self):
        return self.subcategory_id

    @subcategoria_id.setter
    def subcategoria_id(self, value: int):
        self.subcategory_id = value

