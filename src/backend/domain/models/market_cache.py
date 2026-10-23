import datetime
from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class MarketCache(Base):
    __tablename__ = "market_cache"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    data_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, index=True)
