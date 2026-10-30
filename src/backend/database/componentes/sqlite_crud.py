from sqlalchemy.orm import Session
from sqlalchemy import extract
from backend.database.interfaz.db_interface import IRepository
from backend.domain.models import (
    categories as cat_model,
    budgets as pres_model,
    transactions as trans_model,
    emergency_fund as fund_model,
    market_cache as cache_model,
    watchlist as watchlist_model,
    copilot as copilot_model,
)
from backend.domain.schemas import (
    categories as cat_schema,
    budgets as pres_schema,
    transactions as trans_schema,
    watchlist as watchlist_schema,
    copilot as copilot_schema,
)
from typing import Optional, Any, List, Dict
import json
import datetime
import logging

logger = logging.getLogger(__name__)


class SQLiteRepository(IRepository):
    """Implementación SQLite del repositorio central desacoplado de base de datos."""

    def __init__(self, db: Session):
        self.db = db

    # 1. Categorías y Subcategorías
    def get_categories(self) -> List[cat_model.Category]:
        """Obtiene todas las categorías contables con sus relaciones cargadas."""
        return self.db.query(cat_model.Category).all()

    def create_category(self, category: cat_schema.CategoryCreate) -> cat_model.Category:
        """Persiste una nueva categoría contable."""
        data = category.model_dump()
        db_item = cat_model.Category(name=data.get("name"), type=data.get("type"))
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def get_subcategories(self, category_id: Optional[int] = None) -> List[cat_model.Subcategory]:
        """Obtiene subcategorías, filtrando opcionalmente por identificador de categoría."""
        query = self.db.query(cat_model.Subcategory)
        if category_id:
            query = query.filter(cat_model.Subcategory.category_id == category_id)
        return query.all()

    def create_subcategory(self, subcategory: cat_schema.SubcategoryCreate) -> cat_model.Subcategory:
        """Persiste una nueva subcategoría contable."""
        data = subcategory.model_dump()
        db_item = cat_model.Subcategory(name=data.get("name"), category_id=data.get("category_id"))
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    # 2. Transacciones
    def get_transactions(self, month: Optional[str] = None) -> List[trans_model.Transaction]:
        """Obtiene las transacciones registradas, filtrando opcionalmente por mes (YYYY-MM)."""
        query = self.db.query(trans_model.Transaction)
        if month and month != "BASE" and "-" in month:
            try:
                year, m = map(int, month.split('-'))
                query = query.filter(
                    extract('year', trans_model.Transaction.date) == year,
                    extract('month', trans_model.Transaction.date) == m
                )
            except ValueError as exc:
                logger.warning("Formato de mes no interpretable en get_transactions ('%s'): %s", month, exc)
        return query.all()

    def create_transaction(self, transaction: trans_schema.TransactionCreate) -> trans_model.Transaction:
        """
        Persiste una nueva transacción contable.
        Si la transacción corresponde a la subcategoría 'Fondo de emergencia',
        sincroniza en tiempo real el saldo acumulado en la entidad EmergencyFund.
        """
        data = transaction.model_dump()
        db_item = trans_model.Transaction(
            date=data.get("date"),
            subcategory_id=data.get("subcategory_id"),
            amount=data.get("amount"),
            description=data.get("description", ""),
            applied_strategy_id=data.get("applied_strategy_id"),
        )
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)

        # Sincronizar el saldo del fondo de emergencia si la transacción pertenece a dicha subcategoría
        subcat = self.db.query(cat_model.Subcategory).filter(cat_model.Subcategory.id == db_item.subcategory_id).first()
        if subcat and "fondo de emergencia" in subcat.name.lower():
            self.adjust_emergency_fund_balance(db_item.amount)

        return db_item

    def delete_transaction(self, transaction_id: int) -> bool:
        """
        Elimina físicamente una transacción contable por su identificador.
        Si la transacción pertenecía a la subcategoría 'Fondo de emergencia',
        revierte el saldo en la entidad EmergencyFund deduciendo su importe.
        Retorna True si la transacción existía y fue eliminada, o False en caso contrario.
        """
        try:
            db_item = (
                self.db.query(trans_model.Transaction)
                .filter(trans_model.Transaction.id == transaction_id)
                .first()
            )
            if not db_item:
                logger.info("Intento de eliminar transacción inexistente con ID %s", transaction_id)
                return False

            # Si la transacción está vinculada a una estrategia de pautas, revertir la estrategia completa en cascada
            strat_id = getattr(db_item, "applied_strategy_id", None)
            if strat_id:
                from backend.domain.models import guidelines as guideline_models
                applied_entry = (
                    self.db.query(guideline_models.AppliedGuidelineStrategy)
                    .filter(guideline_models.AppliedGuidelineStrategy.id == strat_id)
                    .first()
                )
                siblings = (
                    self.db.query(trans_model.Transaction)
                    .filter(trans_model.Transaction.applied_strategy_id == strat_id)
                    .all()
                )
                for sib in siblings:
                    sub = (
                        self.db.query(cat_model.Subcategory)
                        .filter(cat_model.Subcategory.id == sib.subcategory_id)
                        .first()
                    )
                    if sub and "fondo de emergencia" in sub.name.lower():
                        self.adjust_emergency_fund_balance(-sib.amount)
                    self.db.delete(sib)

                if applied_entry:
                    self.db.delete(applied_entry)
                self.db.commit()
                logger.info(
                    "Estrategia %s y %d transacciones vinculadas eliminadas en cascada por eliminación de transacción %s",
                    strat_id,
                    len(siblings),
                    transaction_id,
                )
                return True

            subcat = (
                self.db.query(cat_model.Subcategory)
                .filter(cat_model.Subcategory.id == db_item.subcategory_id)
                .first()
            )
            if subcat and "fondo de emergencia" in subcat.name.lower():
                logger.info(
                    "Revirtiendo saldo de fondo de emergencia: deduciendo %.2f por eliminación de transacción %s",
                    db_item.amount,
                    db_item.id,
                )
                self.adjust_emergency_fund_balance(-db_item.amount)

            self.db.delete(db_item)
            self.db.commit()
            logger.info("Transacción con ID %s eliminada exitosamente", transaction_id)
            return True
        except Exception as exc:
            self.db.rollback()
            logger.error("Error al eliminar la transacción con ID %s: %s", transaction_id, exc)
            raise

    # 3. Presupuestos Mensuales
    def get_budgets(self, month: str) -> List[pres_model.MonthlyBudget]:
        """
        Obtiene los presupuestos del mes indicado.
        Si no existen registros presupuestarios para dicho mes y no es 'BASE',
        recurre automáticamente a la plantilla predeterminada 'BASE'.
        """
        specific = self.db.query(pres_model.MonthlyBudget).filter(pres_model.MonthlyBudget.month == month).all()
        if month == "BASE" or specific:
            return specific

        # Contingencia: recurrir a la plantilla presupuestaria BASE
        base_list = self.db.query(pres_model.MonthlyBudget).filter(pres_model.MonthlyBudget.month == "BASE").all()
        result = []

        for b in base_list:
            result.append(pres_model.MonthlyBudget(id=0, month=month, subcategory_id=b.subcategory_id, amount=b.amount))
        return result

    def create_budget(self, budget: pres_schema.MonthlyBudgetCreate) -> pres_model.MonthlyBudget:
        """Crea o actualiza una asignación presupuestaria individual."""
        data = budget.model_dump()
        month_val = str(data.get("month", ""))
        sub_id = int(data.get("subcategory_id", 0))
        amt_val = float(data.get("amount", 0.0) or 0.0)

        db_item = self.db.query(pres_model.MonthlyBudget).filter(
            pres_model.MonthlyBudget.month == month_val,
            pres_model.MonthlyBudget.subcategory_id == sub_id
        ).first()

        if db_item:
            db_item.amount = amt_val
        else:
            db_item = pres_model.MonthlyBudget(
                month=month_val,
                subcategory_id=sub_id,
                amount=amt_val
            )
            self.db.add(db_item)

        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def save_budgets_bulk(self, budgets: List[Any]) -> List[pres_model.MonthlyBudget]:
        """Guarda o actualiza un conjunto masivo de presupuestos mensuales."""
        result = []
        for p in budgets:
            if isinstance(p, dict):
                m_val = str(p.get("month") or p.get("mes", ""))
                s_val = int(p.get("subcategory_id") or p.get("subcategoria_id", 0))
                raw_amt = p.get("amount") if p.get("amount") is not None else p.get("cantidad", 0.0)
                a_val = float(raw_amt or 0.0)
            else:
                m_val = str(p.month)
                s_val = int(p.subcategory_id)
                a_val = float(p.amount)

            db_item = self.db.query(pres_model.MonthlyBudget).filter(
                pres_model.MonthlyBudget.month == m_val,
                pres_model.MonthlyBudget.subcategory_id == s_val
            ).first()

            if db_item:
                db_item.amount = a_val
            else:
                db_item = pres_model.MonthlyBudget(month=m_val, subcategory_id=s_val, amount=a_val)
                self.db.add(db_item)

            self.db.commit()
            self.db.refresh(db_item)
            result.append(db_item)
        return result

    # 4. Fondo de Emergencia
    def get_or_create_emergency_fund(self) -> fund_model.EmergencyFund:
        """Obtiene la entidad única del fondo de emergencia o la inicializa con valores constitucionales por defecto (3 meses)."""
        fund = self.db.query(fund_model.EmergencyFund).first()
        if not fund:
            fund = fund_model.EmergencyFund(
                current_balance=0.0,
                target_months=3,
                target_amount=0.0,
                is_completed=False,
            )
            self.db.add(fund)
            self.db.commit()
            self.db.refresh(fund)
        return fund

    def update_emergency_fund(
        self,
        target_months: Optional[int] = None,
        current_balance: Optional[float] = None,
    ) -> fund_model.EmergencyFund:
        """
        Actualiza los parámetros configurables del fondo de emergencia.
        Garantiza por regla constitucional que target_months sea de al menos 3 meses.
        """
        fund = self.get_or_create_emergency_fund()
        if target_months is not None:
            if target_months < 3:
                raise ValueError("El número de meses de cobertura no puede ser inferior a 3 (regla constitucional).")
            fund.target_months = target_months
        if current_balance is not None:
            fund.current_balance = max(0.0, current_balance)
        self.db.commit()
        self.db.refresh(fund)
        return fund

    def adjust_emergency_fund_balance(self, delta: float) -> fund_model.EmergencyFund:
        """Ajusta el saldo acumulado del fondo de emergencia garantizando que no sea negativo."""
        fund = self.get_or_create_emergency_fund()
        fund.current_balance = max(0.0, fund.current_balance + delta)
        self.db.commit()
        self.db.refresh(fund)
        return fund

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
        except Exception:
            return None

    def set_market_cache(
        self, key: str, data: Any, ttl_hours: int = 24
    ) -> cache_model.MarketCache:
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
        return self.db.query(watchlist_model.WatchlistItem).order_by(
            watchlist_model.WatchlistItem.created_at.desc()
        ).all()

    def add_to_watchlist(self, item: watchlist_schema.WatchlistCreate) -> watchlist_model.WatchlistItem:
        """Añade o actualiza un activo en la lista de seguimiento con ticker normalizado a mayúsculas."""
        normalized_ticker = item.ticker.strip().upper()
        existing = self.db.query(watchlist_model.WatchlistItem).filter(
            watchlist_model.WatchlistItem.ticker == normalized_ticker
        ).first()

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
        deleted_count = self.db.query(watchlist_model.WatchlistItem).filter(
            watchlist_model.WatchlistItem.ticker == normalized_ticker
        ).delete()
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

        tool_calls_json = (
            json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None
        )
        message = copilot_model.CopilotMessage(
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls_json,
        )
        self.db.add(message)

        # Actualizar timestamp de la sesión
        now = datetime.datetime.now()
        session.updated_at = now

        # Si la sesión tiene el título por defecto y es el primer mensaje de usuario, auto-generar título
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

