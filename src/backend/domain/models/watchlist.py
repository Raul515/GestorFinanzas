import datetime
from typing import Optional
from sqlalchemy import String, Float, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class WatchlistItem(Base):
    """Modelo ORM para los activos guardados en la lista de seguimiento (Watchlist) en SQLite."""
    __tablename__ = "watchlist"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    price_at_addition: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
