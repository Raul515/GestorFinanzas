import datetime
from sqlalchemy import Float, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class EmergencyFund(Base):
    __tablename__ = "emergency_funds"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    current_balance: Mapped[float] = mapped_column(Float, default=0.0)
    target_months: Mapped[int] = mapped_column(Integer, default=3)
    target_amount: Mapped[float] = mapped_column(Float, default=0.0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )
