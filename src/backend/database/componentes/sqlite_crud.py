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
    joint as joint_model,
)
from backend.domain.schemas import (
    categories as cat_schema,
    budgets as pres_schema,
    transactions as trans_schema,
    watchlist as watchlist_schema,
    copilot as copilot_schema,
    joint as joint_schema,
)
from typing import Optional, Any, List, Dict
import json
import datetime
import uuid
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

            # Si la transacción personal corresponde a una aportación conjunta, eliminar la aportación en cascada y sincronizar
            j_contrib = None
            if getattr(db_item, "joint_contribution_uuid", None):
                j_contrib = (
                    self.db.query(joint_model.JointMonthlyContribution)
                    .filter(joint_model.JointMonthlyContribution.uuid == db_item.joint_contribution_uuid)
                    .first()
                )
            elif "cuenta conjunta" in getattr(db_item, "description", "").lower():
                j_contrib = (
                    self.db.query(joint_model.JointMonthlyContribution)
                    .filter(joint_model.JointMonthlyContribution.personal_transaction_id == db_item.id)
                    .first()
                )

            if j_contrib:
                logger.info(
                    "Eliminación en cascada de aportación conjunta %s por eliminación de transacción personal %s",
                    j_contrib.id,
                    transaction_id,
                )
                del_info = self.delete_joint_contribution(j_contrib.id)
                try:
                    from backend.services.joint_sync_service import JointSyncService
                    sync_svc = JointSyncService()
                    if del_info and del_info.get("uuid"):
                        sync_svc.emit_event(
                            entity_type=joint_schema.SyncEntityType.CONTRIBUTION,
                            action=joint_schema.SyncAction.DELETE,
                            payload={
                                "uuid": del_info["uuid"],
                                "month": del_info["month"],
                                "contributor_profile": del_info["contributor_profile"],
                            },
                            origin_device_id=sync_svc.local_device_id,
                        )
                        for f_data in (del_info.get("reverted_funds") or {}).values():
                            sync_svc.emit_event(
                                entity_type=joint_schema.SyncEntityType.SINKING_FUND,
                                action=joint_schema.SyncAction.UPSERT,
                                payload=f_data,
                                origin_device_id=sync_svc.local_device_id,
                            )
                except Exception as sync_exc:
                    logger.warning("No se pudo emitir tombstone desde delete_transaction: %s", sync_exc)
                return True

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

    # ==========================================
    # 8. Espacio Conjunto / Hogar (Spec 010)
    # ==========================================

    def get_joint_account(self) -> Optional[joint_model.JointAccount]:
        """Obtiene la cuenta conjunta configurada o None si el usuario aún no la ha creado."""
        return self.db.query(joint_model.JointAccount).filter(joint_model.JointAccount.id == 1).first()

    def create_joint_account(
        self, setup_data: joint_schema.JointAccountSetupRequest
    ) -> joint_model.JointAccount:
        """Crea la cuenta conjunta e inicializa el catálogo base de necesidades comunes."""
        existing = self.get_joint_account()
        if existing:
            raise ValueError("Ya existe una cuenta conjunta configurada en este dispositivo.")

        data = setup_data.model_dump()
        account = joint_model.JointAccount(
            id=1,
            household_name=data["household_name"],
            cohabitation_stage=data["cohabitation_stage"].value if hasattr(data["cohabitation_stage"], "value") else str(data["cohabitation_stage"]),
            contribution_strategy=data["contribution_strategy"].value if hasattr(data["contribution_strategy"], "value") else str(data["contribution_strategy"]),
            split_mode=data["split_mode"].value if hasattr(data["split_mode"], "value") else str(data["split_mode"]),
            member_a_reference_income=data.get("member_a_reference_income", 0.0),
            member_b_reference_income=data.get("member_b_reference_income", 0.0),
            member_a_contribution_pct=data.get("member_a_contribution_pct", 50.0),
            member_b_contribution_pct=data.get("member_b_contribution_pct", 50.0),
            local_profile=data["local_profile"].value if hasattr(data["local_profile"], "value") else str(data["local_profile"]),
            remote_profile=data["remote_profile"].value if hasattr(data["remote_profile"], "value") else str(data["remote_profile"]),
            member_a_name=data.get("member_a_name", "Miembro A"),
            member_b_name=data.get("member_b_name", "Miembro B"),
        )
        self.db.add(account)
        self.db.flush()

        # Sembrar catálogo estandarizado de conceptos comunes (sin ocio)
        cat_needs = joint_model.JointCategory(
            joint_account_id=1,
            name="Necesidades Básicas del Hogar",
            type="JOINT_NEEDS",
        )
        self.db.add(cat_needs)
        self.db.flush()

        default_subcats = [
            "Vivienda (Alquiler / Hipoteca)",
            "Suministros (Luz, Agua, Gas, Internet)",
            "Alimentación y Supermercado",
            "Comunidad y Seguros del Hogar",
        ]
        for sub_name in default_subcats:
            self.db.add(
                joint_model.JointSubcategory(
                    joint_category_id=cat_needs.id,
                    name=sub_name,
                    monthly_budget=0.0,
                )
            )

        self.db.commit()
        self.db.refresh(account)
        return account

    def update_joint_account(
        self, update_data: joint_schema.JointAccountUpdate
    ) -> Optional[joint_model.JointAccount]:
        """Actualiza la configuración de la cuenta conjunta."""
        account = self.get_joint_account()
        if not account:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            if value is not None:
                val_to_set = value.value if hasattr(value, "value") else value
                setattr(account, field, val_to_set)

        self.db.commit()
        self.db.refresh(account)
        return account

    def get_joint_categories(self) -> List[joint_model.JointCategory]:
        """Obtiene las categorías del hogar junto a sus subcategorías."""
        return self.db.query(joint_model.JointCategory).filter(joint_model.JointCategory.joint_account_id == 1).all()

    def get_joint_category(self, category_id: int) -> Optional[joint_model.JointCategory]:
        """Obtiene una categoría de necesidades del hogar por su ID."""
        return (
            self.db.query(joint_model.JointCategory)
            .filter(joint_model.JointCategory.id == category_id, joint_model.JointCategory.joint_account_id == 1)
            .first()
        )

    def create_joint_category(self, category: joint_schema.JointCategoryCreate) -> joint_model.JointCategory:
        """Crea una categoría de necesidades del hogar."""
        data = category.model_dump()
        db_item = joint_model.JointCategory(
            joint_account_id=1,
            name=data["name"],
            type="JOINT_NEEDS",
        )
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def get_joint_subcategories(self, category_id: Optional[int] = None) -> List[joint_model.JointSubcategory]:
        """Obtiene las subcategorías de necesidades comunes."""
        query = self.db.query(joint_model.JointSubcategory)
        if category_id:
            query = query.filter(joint_model.JointSubcategory.joint_category_id == category_id)
        return query.all()

    def get_joint_subcategory(self, subcategory_id: int) -> Optional[joint_model.JointSubcategory]:
        """Obtiene una subcategoría de necesidades comunes por ID."""
        return self.db.query(joint_model.JointSubcategory).filter(joint_model.JointSubcategory.id == subcategory_id).first()

    def create_joint_subcategory(self, subcategory: joint_schema.JointSubcategoryCreate) -> joint_model.JointSubcategory:
        """Crea una nueva subcategoría de necesidades comunes."""
        data = subcategory.model_dump()
        db_item = joint_model.JointSubcategory(
            joint_category_id=data["joint_category_id"],
            name=data["name"],
            monthly_budget=data.get("monthly_budget", 0.0),
        )
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def update_joint_subcategory(
        self, subcategory_id: int, update_data: joint_schema.JointSubcategoryUpdate
    ) -> Optional[joint_model.JointSubcategory]:
        """Actualiza el nombre o presupuesto mensual de una subcategoría común."""
        item = self.get_joint_subcategory(subcategory_id)
        if not item:
            return None
        data = update_data.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(item, key, value)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_joint_subcategory(self, subcategory_id: int) -> bool:
        """Elimina una subcategoría de necesidades comunes."""
        item = self.get_joint_subcategory(subcategory_id)
        if not item:
            return False
        self.db.delete(item)
        self.db.commit()
        return True

    def get_joint_sinking_funds(self, status: Optional[str] = None) -> List[joint_model.JointSinkingFund]:
        """Obtiene las huchas de amortización, filtrando opcionalmente por estado."""
        query = self.db.query(joint_model.JointSinkingFund).filter(joint_model.JointSinkingFund.joint_account_id == 1)
        if status:
            query = query.filter(joint_model.JointSinkingFund.status == status)
        return query.order_by(joint_model.JointSinkingFund.priority.asc()).all()

    def get_joint_sinking_fund(self, fund_id: int) -> Optional[joint_model.JointSinkingFund]:
        """Obtiene una hucha de amortización por su ID."""
        return (
            self.db.query(joint_model.JointSinkingFund)
            .filter(
                joint_model.JointSinkingFund.id == fund_id,
                joint_model.JointSinkingFund.joint_account_id == 1,
            )
            .first()
        )

    def create_joint_sinking_fund(self, fund: joint_schema.JointSinkingFundCreate) -> joint_model.JointSinkingFund:
        """Crea una nueva meta de amortización / hucha del hogar."""
        data = fund.model_dump()
        status_val = data.get("status", "ACTIVE")
        if hasattr(status_val, "value"):
            status_val = status_val.value

        db_item = joint_model.JointSinkingFund(
            joint_account_id=1,
            name=data["name"],
            target_amount=data["target_amount"],
            current_balance=data.get("current_balance", 0.0),
            monthly_target_amount=data.get("monthly_target_amount", 0.0),
            allocation_percentage=data.get("allocation_percentage", 0.0),
            status=str(status_val),
            priority=data.get("priority", 1),
        )
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def update_joint_sinking_fund(
        self, fund_id: int, fund_update: joint_schema.JointSinkingFundUpdate
    ) -> Optional[joint_model.JointSinkingFund]:
        """Actualiza una meta de amortización."""
        fund = self.get_joint_sinking_fund(fund_id)
        if not fund:
            return None

        update_dict = fund_update.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            if value is not None:
                val_to_set = value.value if hasattr(value, "value") else value
                setattr(fund, field, val_to_set)

        self.db.commit()
        self.db.refresh(fund)
        return fund

    def delete_joint_sinking_fund(self, fund_id: int, reallocate_to_fund_id: Optional[int] = None) -> bool:
        """Elimina una hucha de amortización; si tiene saldo remanente, lo reasigna a otra hucha activa."""
        fund = self.get_joint_sinking_fund(fund_id)
        if not fund:
            return False

        if fund.current_balance > 0 and reallocate_to_fund_id:
            target_fund = self.get_joint_sinking_fund(reallocate_to_fund_id)
            if target_fund:
                target_fund.current_balance += fund.current_balance

        # Desvincular explícitamente cualquier transacción para que joint_sinking_fund_id quede en None
        self.db.query(joint_model.JointTransaction).filter(
            joint_model.JointTransaction.joint_sinking_fund_id == fund_id
        ).update({"joint_sinking_fund_id": None})

        self.db.delete(fund)
        self.db.commit()
        return True

    def get_joint_transactions(
        self, year: Optional[int] = None, month: Optional[str] = None
    ) -> List[joint_model.JointTransaction]:
        """Obtiene el historial de gastos comunes o movimientos de huchas."""
        query = self.db.query(joint_model.JointTransaction).filter(joint_model.JointTransaction.joint_account_id == 1)
        if year:
            query = query.filter(extract("year", joint_model.JointTransaction.date) == year)
        if month:
            # month en formato YYYY-MM
            try:
                parts = month.split("-")
                m_year, m_num = int(parts[0]), int(parts[1])
                query = query.filter(
                    extract("year", joint_model.JointTransaction.date) == m_year,
                    extract("month", joint_model.JointTransaction.date) == m_num,
                )
            except Exception as exc:
                logger.warning("Formato de mes inválido en get_joint_transactions: %s", exc)

        return query.order_by(joint_model.JointTransaction.date.desc()).all()

    def get_joint_transaction(self, tx_id: int) -> Optional[joint_model.JointTransaction]:
        """Obtiene una transacción conjunta por su ID primario."""
        return (
            self.db.query(joint_model.JointTransaction)
            .filter(
                joint_model.JointTransaction.id == tx_id,
                joint_model.JointTransaction.joint_account_id == 1,
            )
            .first()
        )

    def create_joint_transaction(self, tx: joint_schema.JointTransactionCreate) -> joint_model.JointTransaction:
        """Registra una transacción en el espacio conjunto."""
        data = tx.model_dump()
        profile_val = data["created_by_profile"]
        if hasattr(profile_val, "value"):
            profile_val = profile_val.value

        db_tx = joint_model.JointTransaction(
            uuid=data.get("uuid") or str(uuid.uuid4()),
            joint_account_id=1,
            date=data["date"],
            amount=data["amount"],
            description=data["description"],
            joint_subcategory_id=data.get("joint_subcategory_id"),
            joint_sinking_fund_id=data.get("joint_sinking_fund_id"),
            created_by_profile=str(profile_val),
        )

        # Si el gasto proviene de una hucha de amortización, descontar únicamente el saldo disponible acumulado
        deducted = 0.0
        if db_tx.joint_sinking_fund_id:
            fund = self.get_joint_sinking_fund(db_tx.joint_sinking_fund_id)
            if fund and fund.current_balance > 0:
                deducted = min(float(fund.current_balance), float(db_tx.amount))
                fund.current_balance = round(float(fund.current_balance) - deducted, 2)

        db_tx.sinking_fund_deduction = deducted
        self.db.add(db_tx)
        self.db.commit()
        self.db.refresh(db_tx)
        return db_tx

    def delete_joint_transaction(self, tx_id: int) -> Optional[str]:
        """Elimina una transacción y retorna su UUID para emitir el tombstone de sincronización."""
        tx = self.get_joint_transaction(tx_id)
        if not tx:
            return None

        tx_uuid = tx.uuid

        # Si procedía de una hucha de amortización, restaurar únicamente lo que efectivamente se descontó
        if tx.joint_sinking_fund_id:
            fund = self.get_joint_sinking_fund(tx.joint_sinking_fund_id)
            if fund:
                deduction_to_restore = getattr(tx, "sinking_fund_deduction", 0.0) or 0.0
                fund.current_balance = round(float(fund.current_balance) + float(deduction_to_restore), 2)

        self.db.delete(tx)
        self.db.commit()
        return tx_uuid

    def get_joint_contributions(
        self, year: Optional[int] = None, month: Optional[str] = None
    ) -> List[joint_model.JointMonthlyContribution]:
        """Obtiene las aportaciones mensuales registradas."""
        query = self.db.query(joint_model.JointMonthlyContribution).filter(joint_model.JointMonthlyContribution.joint_account_id == 1)
        if year:
            query = query.filter(joint_model.JointMonthlyContribution.month.like(f"{year}-%"))
        if month:
            query = query.filter(joint_model.JointMonthlyContribution.month == month)
        return query.order_by(joint_model.JointMonthlyContribution.contribution_date.desc()).all()

    def get_joint_contribution(self, contrib_id: int) -> Optional[joint_model.JointMonthlyContribution]:
        """Obtiene una aportación mensual por su ID primario."""
        return (
            self.db.query(joint_model.JointMonthlyContribution)
            .filter(
                joint_model.JointMonthlyContribution.id == contrib_id,
                joint_model.JointMonthlyContribution.joint_account_id == 1,
            )
            .first()
        )

    def create_joint_contribution(
        self, contrib: joint_schema.JointMonthlyContributionCreate
    ) -> joint_model.JointMonthlyContribution:
        """Registra una aportación mensual a la tesorería común."""
        data = contrib.model_dump()
        profile_val = data["contributor_profile"]
        if hasattr(profile_val, "value"):
            profile_val = profile_val.value

        c_uuid = data.get("uuid") or str(uuid.uuid4())
        db_contrib = joint_model.JointMonthlyContribution(
            uuid=c_uuid,
            joint_account_id=1,
            month=data["month"],
            contributor_profile=str(profile_val),
            amount=data["amount"],
            contribution_date=data["contribution_date"],
            personal_transaction_id=data.get("personal_transaction_id"),
            sinking_fund_allocations=data.get("sinking_fund_allocations"),
        )
        self.db.add(db_contrib)
        self.db.commit()
        self.db.refresh(db_contrib)
        return db_contrib

    def delete_joint_contribution(self, contrib_id: int) -> Optional[Dict[str, Any]]:
        """Elimina una aportación conjunta, revierte el saldo de huchas asignadas y borra la transacción personal asociada."""
        contrib = self.get_joint_contribution(contrib_id)
        if not contrib:
            return None

        c_uuid = contrib.uuid
        c_month = contrib.month
        c_profile = contrib.contributor_profile
        p_tx_id = contrib.personal_transaction_id
        alloc_str = contrib.sinking_fund_allocations

        reverted_funds = {}
        if alloc_str:
            try:
                allocs = json.loads(alloc_str)
                for fid_str, amount in allocs.items():
                    f_id = int(fid_str)
                    fund = self.get_joint_sinking_fund(f_id)
                    if fund:
                        fund.current_balance = round(max(0.0, float(fund.current_balance) - float(amount)), 2)
                        reverted_funds[fund.name] = {
                            "name": fund.name,
                            "target_amount": float(fund.target_amount),
                            "current_balance": float(fund.current_balance),
                            "monthly_target_amount": float(fund.monthly_target_amount),
                            "allocation_percentage": float(fund.allocation_percentage),
                            "status": fund.status,
                            "priority": fund.priority,
                        }
            except Exception as exc:
                logger.error("Error al revertir asignaciones de huchas en aportación %s: %s", contrib_id, exc)

        # Eliminar transacción personal vinculada si existe
        if p_tx_id:
            p_tx = self.db.query(trans_model.Transaction).filter(trans_model.Transaction.id == p_tx_id).first()
            if p_tx:
                self.db.delete(p_tx)

        self.db.delete(contrib)
        self.db.commit()

        return {
            "uuid": c_uuid,
            "month": c_month,
            "contributor_profile": c_profile,
            "reverted_funds": reverted_funds,
        }

    def reset_joint_account(self) -> bool:
        """Purga todas las entidades del espacio conjunto, devolviendo la base de datos al Estado Cero."""
        # 1. Purgar eventos aplicados de sincronización
        self.db.query(joint_model.JointAppliedSyncEvent).delete()

        # 2. Obtener y eliminar la cuenta conjunta (cascade elimina subentidades)
        account = self.get_joint_account()
        if account:
            self.db.delete(account)
        else:
            # Purgar por seguridad si existieran registros huérfanos
            self.db.query(joint_model.JointTransaction).delete()
            self.db.query(joint_model.JointMonthlyContribution).delete()
            self.db.query(joint_model.JointSinkingFund).delete()
            self.db.query(joint_model.JointSubcategory).delete()
            self.db.query(joint_model.JointCategory).delete()

        self.db.commit()
        return True



