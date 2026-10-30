import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .transactions import Transaction


class AppliedGuidelineStrategy(Base):
    """Modelo ORM para registrar estrategias de pautas deterministas aplicadas a un mes determinado."""
    __tablename__ = "applied_guideline_strategies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    month: Mapped[str] = mapped_column(String, index=True)  # Formato YYYY-MM
    scenario_type: Mapped[str] = mapped_column(String, index=True)  # NEEDS_SURPLUS, EXTRAORDINARY_INCOME
    strategy_type: Mapped[str] = mapped_column(String)  # FIRE, SINKING_FUND, HYBRID_80_20, etc.
    is_partial: Mapped[bool] = mapped_column(Boolean, default=False)
    allocated_amount: Mapped[float] = mapped_column(Float, default=0.0)
    cushion_amount: Mapped[float] = mapped_column(Float, default=0.0)
    split_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="applied_strategy", cascade="all, delete-orphan"
    )
