import datetime
from typing import List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class CopilotSession(Base):
    """Modelo ORM para sesiones de conversación con el Copiloto Patrimonial en SQLite."""
    __tablename__ = "copilot_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False, default="Nueva conversación")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[List["CopilotMessage"]] = relationship(
        "CopilotMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CopilotMessage.created_at",
    )

    @property
    def message_count(self) -> int:
        return len(self.messages) if self.messages is not None else 0


class CopilotMessage(Base):
    """Modelo ORM para mensajes individuales intercambiados dentro de una sesión de conversación."""
    __tablename__ = "copilot_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("copilot_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    session: Mapped["CopilotSession"] = relationship("CopilotSession", back_populates="messages")
