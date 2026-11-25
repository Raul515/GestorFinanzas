"""
Repositorio de Mercado, Watchlist y Copiloto Patrimonial (SQLite).
"""

import datetime
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.domain.models import (
    copilot as copilot_model,
    market_cache as cache_model,
    watchlist as watchlist_model,
)
from backend.domain.schemas import watchlist as watchlist_schema

logger = logging.getLogger(__name__)


class MarketCopilotMixin:
    """Mixin de persistencia SQLite para caché de mercado, watchlist y sesiones del Copiloto."""

    db: Session

    # 5. Caché de Mercado
    def get_market_cache(self, key: str) -> Optional[dict]:
        """Recupera datos de mercado cacheados si no han expirado."""
        entry = (
            self.db.query(cache_model.MarketCache)
            .filter(cache_model.MarketCache.key == key)
            .first()
        )
        if not entry:
            return None
        now = datetime.datetime.now()
        if entry.expires_at and entry.expires_at < now:
            return None
        try:
            return json.loads(entry.data_json)
        except Exception as exc:
            logger.warning("Error deserializando MarketCache '%s': %s", key, exc)
            return None

    def set_market_cache(self, key: str, data: Any, ttl_hours: int = 24) -> cache_model.MarketCache:
        """Persiste datos de mercado en SQLite con TTL configurable (por defecto 24 horas)."""
        now = datetime.datetime.now()
        expires_at = now + datetime.timedelta(hours=ttl_hours)
        data_json = json.dumps(data, ensure_ascii=False, default=str)

        entry = (
            self.db.query(cache_model.MarketCache)
            .filter(cache_model.MarketCache.key == key)
            .first()
        )
        if entry:
            entry.data_json = data_json
            entry.updated_at = now
            entry.expires_at = expires_at
        else:
            entry = cache_model.MarketCache(
                key=key,
                data_json=data_json,
                updated_at=now,
                expires_at=expires_at,
            )
            self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def invalidate_market_cache(self, key: Optional[str] = None) -> None:
        """Invalida una clave específica o vacía la totalidad de la caché de mercado."""
        if key:
            self.db.query(cache_model.MarketCache).filter(
                cache_model.MarketCache.key == key
            ).delete()
        else:
            self.db.query(cache_model.MarketCache).delete()
        self.db.commit()

    # 6. Lista de Seguimiento (Watchlist)
    def get_watchlist(self) -> List[watchlist_model.WatchlistItem]:
        """Recupera todos los activos guardados en la lista de seguimiento ordenados por fecha de adición descendente."""
        return (
            self.db.query(watchlist_model.WatchlistItem)
            .order_by(watchlist_model.WatchlistItem.created_at.desc())
            .all()
        )

    def add_to_watchlist(self, item: watchlist_schema.WatchlistCreate) -> watchlist_model.WatchlistItem:
        """Añade o actualiza un activo en la lista de seguimiento con ticker normalizado a mayúsculas."""
        normalized_ticker = item.ticker.strip().upper()
        existing = (
            self.db.query(watchlist_model.WatchlistItem)
            .filter(watchlist_model.WatchlistItem.ticker == normalized_ticker)
            .first()
        )
        if existing:
            existing.name = item.name
            existing.sector = item.sector
            existing.currency = item.currency
            existing.price_at_addition = item.price_at_addition
            existing.notes = item.notes
            db_item = existing
        else:
            db_item = watchlist_model.WatchlistItem(
                ticker=normalized_ticker,
                name=item.name,
                sector=item.sector,
                currency=item.currency,
                price_at_addition=item.price_at_addition,
                notes=item.notes,
            )
            self.db.add(db_item)

        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def remove_from_watchlist(self, ticker: str) -> bool:
        """Elimina un activo de la lista de seguimiento por su símbolo bursátil."""
        normalized_ticker = ticker.strip().upper()
        deleted_count = (
            self.db.query(watchlist_model.WatchlistItem)
            .filter(watchlist_model.WatchlistItem.ticker == normalized_ticker)
            .delete()
        )
        self.db.commit()
        return deleted_count > 0

    # 7. Copiloto Patrimonial (Sesiones y Mensajes)
    def create_copilot_session(self, title: Optional[str] = None) -> copilot_model.CopilotSession:
        """Crea una nueva sesión de conversación para el Copiloto."""
        clean_title = title.strip()[:150] if title and title.strip() else "Nueva conversación"
        session = copilot_model.CopilotSession(title=clean_title)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_copilot_sessions(self) -> List[copilot_model.CopilotSession]:
        """Obtiene todas las sesiones ordenadas por última actividad descendente."""
        return (
            self.db.query(copilot_model.CopilotSession)
            .order_by(copilot_model.CopilotSession.updated_at.desc())
            .all()
        )

    def get_copilot_session(self, session_id: int) -> Optional[copilot_model.CopilotSession]:
        """Recupera una sesión específica por su ID."""
        return (
            self.db.query(copilot_model.CopilotSession)
            .filter(copilot_model.CopilotSession.id == session_id)
            .first()
        )

    def delete_copilot_session(self, session_id: int) -> bool:
        """Elimina una sesión de conversación y todos sus mensajes en cascada."""
        session = self.get_copilot_session(session_id)
        if not session:
            return False
        self.db.delete(session)
        self.db.commit()
        return True

    def add_copilot_message(
        self,
        session_id: int,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> copilot_model.CopilotMessage:
        """Registra un nuevo mensaje en la sesión indicada y actualiza su fecha de última actividad."""
        session = self.get_copilot_session(session_id)
        if not session:
            raise ValueError(f"Sesión del copiloto con ID {session_id} no encontrada.")

        tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None
        message = copilot_model.CopilotMessage(
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls_json,
        )
        self.db.add(message)
        session.updated_at = datetime.datetime.now()

        if session.title == "Nueva conversación" and role == "user":
            snippet = content.strip().replace("\n", " ")
            session.title = (snippet[:45] + "...") if len(snippet) > 45 else snippet

        self.db.commit()
        self.db.refresh(message)
        return message

    def get_copilot_messages(self, session_id: int) -> List[copilot_model.CopilotMessage]:
        """Obtiene la lista de mensajes de una sesión ordenados cronológicamente."""
        return (
            self.db.query(copilot_model.CopilotMessage)
            .filter(copilot_model.CopilotMessage.session_id == session_id)
            .order_by(copilot_model.CopilotMessage.created_at.asc())
            .all()
        )
