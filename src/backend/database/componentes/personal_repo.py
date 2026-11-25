"""
Repositorio de Dominio Personal (SQLite):
Categorías, subcategorías, transacciones, presupuestos mensuales y fondo de emergencia.
"""

import calendar
import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.domain.constants import is_default_personal_subcategory, is_emergency_fund_subcategory
from backend.domain.models import (
    budgets as pres_model,
    categories as cat_model,
    emergency_fund as fund_model,
    guidelines as guideline_models,
    joint as joint_model,
    transactions as trans_model,
)
from backend.domain.schemas import (
    categories as cat_schema,
    transactions as trans_schema,
)
from backend.services.safety_guard import get_effective_monthly_budgets

logger = logging.getLogger(__name__)


class PersonalFinanceMixin:
    """Mixin de persistencia SQLite para el perfil financiero personal."""

    db: Session

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
        """Persiste una nueva subcategoría contable verificando unicidad por nombre."""
        data = subcategory.model_dump()
        raw_name = data.get("name", "")
        cleaned_name = raw_name.strip() if raw_name else ""
        if not cleaned_name:
            raise ValueError("El nombre de la subcategoría no puede estar vacío.")

        cat_id = data.get("category_id")
        existing = (
            self.db.query(cat_model.Subcategory)
            .filter(
                cat_model.Subcategory.category_id == cat_id,
                func.lower(cat_model.Subcategory.name) == cleaned_name.lower(),
            )
            .first()
        )
        if existing:
            raise ValueError(f"Ya existe una subcategoría con el nombre '{cleaned_name}' en esta categoría.")

        db_item = cat_model.Subcategory(name=cleaned_name, category_id=cat_id)
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def update_subcategory(self, subcategory_id: int, name: str) -> Optional[cat_model.Subcategory]:
        """Actualiza el nombre de una subcategoría contable personal."""
        db_item = self.db.query(cat_model.Subcategory).filter(cat_model.Subcategory.id == subcategory_id).first()
        if not db_item:
            return None
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("El nombre de la subcategoría no puede estar vacío.")
        if is_default_personal_subcategory(db_item.name):
            raise ValueError(f"No se puede modificar el nombre de la subcategoría base del sistema '{db_item.name}'.")
        db_item.name = cleaned_name
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def check_subcategory_usage(self, subcategory_id: int) -> Dict[str, Any]:
        """Comprueba el número de transacciones y presupuestos que dependen de una subcategoría."""
        tx_count = self.db.query(trans_model.Transaction).filter(
            trans_model.Transaction.subcategory_id == subcategory_id
        ).count()
        budgets_count = self.db.query(pres_model.MonthlyBudget).filter(
            pres_model.MonthlyBudget.subcategory_id == subcategory_id
        ).count()
        subcat = self.db.query(cat_model.Subcategory).filter(cat_model.Subcategory.id == subcategory_id).first()
        is_base = is_default_personal_subcategory(subcat.name) if subcat else False
        return {
            "subcategory_id": subcategory_id,
            "transactions_count": tx_count,
            "budgets_count": budgets_count,
            "is_base": is_base,
            "can_delete": (tx_count == 0 and not is_base),
        }

    def delete_subcategory(self, subcategory_id: int) -> bool:
        """Elimina una subcategoría si no tiene transacciones asociadas, limpiando presupuestos huérfanos."""
        db_item = self.db.query(cat_model.Subcategory).filter(cat_model.Subcategory.id == subcategory_id).first()
        if not db_item:
            return False
        if is_default_personal_subcategory(db_item.name):
            raise ValueError(f"No se puede eliminar la subcategoría base del sistema '{db_item.name}'.")
        usage = self.check_subcategory_usage(subcategory_id)
        if not usage["can_delete"]:
            raise ValueError(
                f"No se puede eliminar la subcategoría '{db_item.name}': "
                f"tiene {usage['transactions_count']} transacciones vinculadas."
            )
        self.db.query(pres_model.MonthlyBudget).filter(
            pres_model.MonthlyBudget.subcategory_id == subcategory_id
        ).delete()
        self.db.delete(db_item)
        self.db.commit()
        return True

    # 2. Transacciones
    def get_transactions(self, month: Optional[str] = None) -> List[trans_model.Transaction]:
        """Obtiene las transacciones registradas, filtrando opcionalmente por mes (YYYY-MM)."""
        query = self.db.query(trans_model.Transaction)
        if month and month != "BASE" and "-" in month:
            try:
                year, m = map(int, month.split("-"))
                query = query.filter(
                    trans_model.Transaction.date >= datetime.date(year, m, 1),
                    trans_model.Transaction.date <= datetime.date(year, m, calendar.monthrange(year, m)[1]),
                )
            except ValueError as exc:
                logger.warning("Formato de mes no interpretable en get_transactions ('%s'): %s", month, exc)
        return query.all()

    def create_transaction(self, transaction: trans_schema.TransactionCreate) -> trans_model.Transaction:
        """Persiste una nueva transacción contable y sincroniza el fondo de emergencia si corresponde."""
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

        subcat = self.db.query(cat_model.Subcategory).filter(cat_model.Subcategory.id == db_item.subcategory_id).first()
        if subcat and is_emergency_fund_subcategory(subcat):
            self.adjust_emergency_fund_balance(db_item.amount)

        return db_item

    def delete_transaction_with_context(self, transaction_id: int) -> Tuple[bool, Dict[str, Any]]:
        """
        Elimina físicamente una transacción (y sus cascadas en BD: aportación conjunta o estrategia)
        sin acoplarse a disco/sync, retornando metadatos para que la capa de aplicación emita eventos.
        """
        context: Dict[str, Any] = {
            "joint_del_info": None,
            "receipt_filenames": [],
            "mobile_event_ids": [],
        }
        try:
            db_item = (
                self.db.query(trans_model.Transaction)
                .filter(trans_model.Transaction.id == transaction_id)
                .first()
            )
            if not db_item:
                logger.info("Intento de eliminar transacción inexistente con ID %s", transaction_id)
                return False, context

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
                context["joint_del_info"] = self.delete_joint_contribution(j_contrib.id)  # type: ignore[attr-defined]
                return True, context

            receipt_fn = getattr(db_item, "receipt_filename", None)
            if receipt_fn:
                context["receipt_filenames"].append(receipt_fn)

            strat_id = getattr(db_item, "applied_strategy_id", None)
            if strat_id:
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
                    sib_receipt = getattr(sib, "receipt_filename", None)
                    if sib_receipt and sib_receipt not in context["receipt_filenames"]:
                        context["receipt_filenames"].append(sib_receipt)
                    sib_mob_evt = getattr(sib, "mobile_event_id", None)
                    if sib_mob_evt:
                        context["mobile_event_ids"].append(sib_mob_evt)
                    sub = (
                        self.db.query(cat_model.Subcategory)
                        .filter(cat_model.Subcategory.id == sib.subcategory_id)
                        .first()
                    )
                    if sub and is_emergency_fund_subcategory(sub):
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
                return True, context

            mob_evt = getattr(db_item, "mobile_event_id", None)
            if mob_evt:
                context["mobile_event_ids"].append(mob_evt)

            subcat = (
                self.db.query(cat_model.Subcategory)
                .filter(cat_model.Subcategory.id == db_item.subcategory_id)
                .first()
            )
            if subcat and is_emergency_fund_subcategory(subcat):
                logger.info(
                    "Revirtiendo saldo de fondo de emergencia: deduciendo %.2f por eliminación de transacción %s",
                    db_item.amount,
                    db_item.id,
                )
                self.adjust_emergency_fund_balance(-db_item.amount)

            self.db.delete(db_item)
            self.db.commit()
            logger.info("Transacción con ID %s eliminada exitosamente", transaction_id)
            return True, context
        except Exception as exc:
            self.db.rollback()
            logger.error("Error al eliminar la transacción con ID %s: %s", transaction_id, exc)
            raise

    def delete_transaction(self, transaction_id: int) -> bool:
        """Elimina físicamente una transacción contable por su identificador."""
        deleted, _ = self.delete_transaction_with_context(transaction_id)
        return deleted

    # 3. Presupuestos Mensuales
    def get_budgets(self, month: str) -> List[pres_model.MonthlyBudget]:
        """Obtiene los presupuestos efectivos fusionando por subcategoría sobre la plantilla 'BASE'."""
        return get_effective_monthly_budgets(self.db, month)

    def create_budget(self, budget: Any) -> pres_model.MonthlyBudget:
        """Crea o actualiza una asignación presupuestaria individual."""
        data = budget.model_dump()
        month_val = str(data.get("month", ""))
        sub_id = int(data.get("subcategory_id", 0))
        amt_val = float(data.get("amount", 0.0) or 0.0)

        db_item = (
            self.db.query(pres_model.MonthlyBudget)
            .filter(
                pres_model.MonthlyBudget.month == month_val,
                pres_model.MonthlyBudget.subcategory_id == sub_id,
            )
            .first()
        )
        if db_item:
            db_item.amount = amt_val
        else:
            db_item = pres_model.MonthlyBudget(month=month_val, subcategory_id=sub_id, amount=amt_val)
            self.db.add(db_item)

        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def save_budgets_bulk(self, budgets: List[Any]) -> List[pres_model.MonthlyBudget]:
        """Guarda o actualiza un conjunto masivo de presupuestos mensuales en una única transacción atómica."""
        if not budgets:
            return []

        months_set = set()
        parsed_items = []
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
            months_set.add(m_val)
            parsed_items.append((m_val, s_val, a_val))

        existing_items = (
            self.db.query(pres_model.MonthlyBudget)
            .filter(pres_model.MonthlyBudget.month.in_(months_set))
            .all()
        )
        existing_map = {(b.month, b.subcategory_id): b for b in existing_items}

        result = []
        for m_val, s_val, a_val in parsed_items:
            db_item = existing_map.get((m_val, s_val))
            if db_item:
                db_item.amount = a_val
            else:
                db_item = pres_model.MonthlyBudget(month=m_val, subcategory_id=s_val, amount=a_val)
                self.db.add(db_item)
                existing_map[(m_val, s_val)] = db_item
            result.append(db_item)

        self.db.commit()
        for item in result:
            self.db.refresh(item)
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
        """Actualiza los parámetros configurables del fondo de emergencia (mínimo 3 meses)."""
        fund = self.get_or_create_emergency_fund()
        if target_months is not None:
            if target_months < 3:
                raise ValueError("El número de meses de cobertura no puede ser inferior a 3 (regla constitucional).")
            fund.target_months = target_months
        if current_balance is not None:
            fund.current_balance = round(max(0.0, float(current_balance)), 2)
        self.db.commit()
        self.db.refresh(fund)
        return fund

    def adjust_emergency_fund_balance(self, delta: float) -> fund_model.EmergencyFund:
        """Ajusta el saldo acumulado del fondo de emergencia garantizando no-negatividad y redondeo a 2 decimales."""
        fund = self.get_or_create_emergency_fund()
        fund.current_balance = round(max(0.0, float(fund.current_balance or 0.0) + float(delta)), 2)
        self.db.commit()
        self.db.refresh(fund)
        return fund
