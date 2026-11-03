import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class BackupScheduleConfig(Base):
    """Modelo ORM para la configuración persistente de copias de seguridad automáticas."""
    __tablename__ = "backup_schedule_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    frequency_days: Mapped[int] = mapped_column(Integer, default=14)
    keep_max_copies: Mapped[int] = mapped_column(Integer, default=5)
    last_automated_backup_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_backup_sha256: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )
