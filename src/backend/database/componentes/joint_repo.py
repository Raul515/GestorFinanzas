"""
Repositorio del Espacio Conjunto / Hogar (SQLite, Spec 010 / Spec 015 / Spec 017).
"""

import calendar
import datetime
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.domain.constants import DEFAULT_JOINT_SUBCATEGORIES, is_default_joint_subcategory
from backend.domain.models import joint as joint_model, transactions as trans_model
from backend.domain.schemas import joint as joint_schema

logger = logging.getLogger(__name__)


class JointAccountMixin:
    """Mixin de persistencia SQLite para la cuenta conjunta, huchas, gastos comunes y aportaciones."""

    db: Session

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
            custom_total_monthly_budget=data.get("custom_total_monthly_budget", 0.0),
        )
        self.db.add(account)
        self.db.flush()

        cat_needs = joint_model.JointCategory(
            joint_account_id=1,
            name="Necesidades Básicas del Hogar",
            type="JOINT_NEEDS",
        )
        self.db.add(cat_needs)
        self.db.flush()

        for sub_name in DEFAULT_JOINT_SUBCATEGORIES:
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
        """Obtiene las categorías de necesidades del hogar."""
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
        """Crea una nueva subcategoría de necesidades comunes verificando etapa y unicidad."""
        data = subcategory.model_dump()
        raw_name = data.get("name", "")
        cleaned_name = raw_name.strip() if raw_name else ""
        if not cleaned_name:
            raise ValueError("El nombre de la subcategoría del hogar no puede estar vacío.")

        account = self.get_joint_account()
        if account and account.cohabitation_stage in ("PRE_COHABITATION", "DATING_COHABITATION"):
            raise ValueError("No se pueden registrar subcategorías de necesidades comunes en etapa de Pre-Convivencia.")

        existing = (
            self.db.query(joint_model.JointSubcategory)
            .filter(func.lower(joint_model.JointSubcategory.name) == cleaned_name.lower())
            .first()
        )
        if existing:
            raise ValueError(f"Ya existe una subcategoría con el nombre '{cleaned_name}' en los gastos del hogar.")

        db_item = joint_model.JointSubcategory(
            joint_category_id=data["joint_category_id"],
            name=cleaned_name,
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
        if "name" in data and data["name"] is not None:
            new_name = data["name"].strip()
            if not new_name:
                raise ValueError("El nombre no puede estar vacío.")
            if new_name.lower() != item.name.lower():
                if is_default_joint_subcategory(item.name):
                    raise ValueError(f"No se puede modificar el nombre de la subcategoría base del hogar '{item.name}'.")
                existing = (
                    self.db.query(joint_model.JointSubcategory)
                    .filter(
                        func.lower(joint_model.JointSubcategory.name) == new_name.lower(),
                        joint_model.JointSubcategory.id != subcategory_id,
                    )
                    .first()
                )
                if existing:
                    raise ValueError(f"Ya existe una subcategoría con el nombre '{new_name}' en los gastos del hogar.")
                data["name"] = new_name

        for key, value in data.items():
            setattr(item, key, value)
        self.db.commit()
        self.db.refresh(item)
        return item

    def check_joint_subcategory_usage(self, subcategory_id: int) -> Dict[str, Any]:
        """Comprueba el número de transacciones comunes que dependen de una subcategoría conjunta."""
        tx_count = (
            self.db.query(joint_model.JointTransaction)
            .filter(joint_model.JointTransaction.joint_subcategory_id == subcategory_id)
            .count()
        )
        subcat = self.get_joint_subcategory(subcategory_id)
        is_base = is_default_joint_subcategory(subcat.name) if subcat else False
        return {
            "subcategory_id": subcategory_id,
            "transactions_count": tx_count,
            "is_base": is_base,
            "can_delete": (tx_count == 0 and not is_base),
        }

    def delete_joint_subcategory(self, subcategory_id: int) -> bool:
        """Elimina una subcategoría de necesidades comunes si no tiene transacciones asociadas."""
        item = self.get_joint_subcategory(subcategory_id)
        if not item:
            return False
        if is_default_joint_subcategory(item.name):
            raise ValueError(f"No se puede eliminar la subcategoría base del hogar '{item.name}'.")
        usage = self.check_joint_subcategory_usage(subcategory_id)
        if not usage["can_delete"]:
            raise ValueError(
                f"No se puede eliminar la subcategoría conjunta '{item.name}': "
                f"tiene {usage['transactions_count']} transacciones del hogar vinculadas."
            )
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
                target_fund.current_balance = round(float(target_fund.current_balance) + float(fund.current_balance), 2)

        self.db.query(joint_model.JointTransaction).filter(
            joint_model.JointTransaction.joint_sinking_fund_id == fund_id
        ).update({"joint_sinking_fund_id": None})

        self.db.delete(fund)
        self.db.commit()
        return True

    def transfer_sinking_fund_balance(
        self, transfer_data: joint_schema.JointSinkingFundTransferCreate
    ) -> joint_model.JointSinkingFundTransfer:
        """Ejecuta un rebalanceo atómico de saldo entre dos huchas de amortización y registra la traza."""
        if transfer_data.source_fund_id == transfer_data.target_fund_id:
            raise ValueError("La hucha de origen y destino deben ser distintas.")

        source = self.get_joint_sinking_fund(transfer_data.source_fund_id)
        target = self.get_joint_sinking_fund(transfer_data.target_fund_id)

        if not source:
            raise ValueError(f"Hucha de origen con ID {transfer_data.source_fund_id} no encontrada.")
        if not target:
            raise ValueError(f"Hucha de destino con ID {transfer_data.target_fund_id} no encontrada.")
        if target.status != "ACTIVE":
            raise ValueError(f"La hucha de destino '{target.name}' debe encontrarse en estado ACTIVE.")

        amt = round(float(transfer_data.amount), 2)
        if amt <= 0:
            raise ValueError("El importe a transferir debe ser mayor que 0.")

        curr_src = round(float(source.current_balance), 2)
        if curr_src < amt:
            raise ValueError(
                f"Saldo insuficiente en la hucha origen '{source.name}' ({curr_src:.2f} € disponibles vs {amt:.2f} € solicitados)."
            )

        source.current_balance = round(curr_src - amt, 2)
        target.current_balance = round(float(target.current_balance) + amt, 2)

        p_val = transfer_data.created_by_profile
        if hasattr(p_val, "value"):
            p_val = p_val.value
        p_val = str(p_val or "MEMBER_A")

        t_date = transfer_data.date
        if isinstance(t_date, str):
            t_date = datetime.date.fromisoformat(t_date)
        elif not t_date:
            t_date = datetime.date.today()

        transfer = joint_model.JointSinkingFundTransfer(
            uuid=transfer_data.uuid or str(uuid.uuid4()),
            joint_account_id=1,
            source_fund_id=source.id,
            target_fund_id=target.id,
            amount=amt,
            date=t_date,
            notes=transfer_data.notes,
            created_by_profile=p_val,
        )

        self.db.add(transfer)
        self.db.commit()
        self.db.refresh(transfer)
        self.db.refresh(source)
        self.db.refresh(target)
        return transfer

    def get_joint_sinking_fund_transfers(
        self, limit: int = 100
    ) -> List[joint_model.JointSinkingFundTransfer]:
        """Obtiene el historial cronológico de traspasos entre huchas."""
        return (
            self.db.query(joint_model.JointSinkingFundTransfer)
            .filter(joint_model.JointSinkingFundTransfer.joint_account_id == 1)
            .order_by(
                joint_model.JointSinkingFundTransfer.date.desc(),
                joint_model.JointSinkingFundTransfer.id.desc(),
            )
            .limit(limit)
            .all()
        )

    def get_joint_transactions(
        self, year: Optional[int] = None, month: Optional[str] = None
    ) -> List[joint_model.JointTransaction]:
        """Obtiene el historial de gastos comunes o movimientos de huchas."""
        query = self.db.query(joint_model.JointTransaction).filter(joint_model.JointTransaction.joint_account_id == 1)
        if year:
            query = query.filter(
                joint_model.JointTransaction.date >= datetime.date(year, 1, 1),
                joint_model.JointTransaction.date <= datetime.date(year, 12, 31),
            )
        if month:
            try:
                parts = month.split("-")
                m_year, m_num = int(parts[0]), int(parts[1])
                query = query.filter(
                    joint_model.JointTransaction.date >= datetime.date(m_year, m_num, 1),
                    joint_model.JointTransaction.date <= datetime.date(m_year, m_num, calendar.monthrange(m_year, m_num)[1]),
                )
            except Exception as exc:
                logger.warning("Formato de mes inválido en get_joint_transactions: %s", exc)

        return query.order_by(joint_model.JointTransaction.date.desc()).all()

    def search_joint_transactions(
        self,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        query_text: Optional[str] = None,
        joint_subcategory_id: Optional[int] = None,
        paid_by: Optional[str] = None,
        settlement_status: Optional[str] = None,
        is_sinking_fund: Optional[bool] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
    ) -> List[joint_model.JointTransaction]:
        """Búsqueda global y filtrado multicriterio de transacciones del hogar."""
        q = self.db.query(joint_model.JointTransaction).filter(joint_model.JointTransaction.joint_account_id == 1)
        if start_date:
            q = q.filter(joint_model.JointTransaction.date >= start_date)
        if end_date:
            q = q.filter(joint_model.JointTransaction.date <= end_date)
        if query_text and query_text.strip():
            term = f"%{query_text.strip()}%"
            q = q.filter(joint_model.JointTransaction.description.ilike(term))
        if joint_subcategory_id is not None:
            q = q.filter(joint_model.JointTransaction.joint_subcategory_id == joint_subcategory_id)
        if paid_by and paid_by != "ALL":
            q = q.filter(joint_model.JointTransaction.paid_by == paid_by)
        if settlement_status and settlement_status != "ALL":
            q = q.filter(joint_model.JointTransaction.settlement_status == settlement_status)
        if is_sinking_fund is True:
            q = q.filter(joint_model.JointTransaction.joint_sinking_fund_id.is_not(None))
        elif is_sinking_fund is False:
            q = q.filter(joint_model.JointTransaction.joint_sinking_fund_id.is_(None))
        if min_amount is not None:
            q = q.filter(joint_model.JointTransaction.amount >= min_amount)
        if max_amount is not None:
            q = q.filter(joint_model.JointTransaction.amount <= max_amount)

        return q.order_by(joint_model.JointTransaction.date.desc(), joint_model.JointTransaction.id.desc()).all()

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

        paid_by_val = data.get("paid_by")
        if hasattr(paid_by_val, "value"):
            paid_by_val = paid_by_val.value
        elif not paid_by_val:
            paid_by_val = "COMMON"

        settlement_mechanism_val = data.get("settlement_mechanism")
        if hasattr(settlement_mechanism_val, "value"):
            settlement_mechanism_val = settlement_mechanism_val.value

        settlement_status_val = data.get("settlement_status")
        if hasattr(settlement_status_val, "value"):
            settlement_status_val = settlement_status_val.value
        elif not settlement_status_val:
            settlement_status_val = "PENDING" if paid_by_val in ("MEMBER_A", "MEMBER_B") else "SETTLED"

        settled_at_val = data.get("settled_at")

        db_tx = joint_model.JointTransaction(
            uuid=data.get("uuid") or str(uuid.uuid4()),
            joint_account_id=1,
            date=data["date"],
            amount=data["amount"],
            description=data["description"],
            joint_subcategory_id=data.get("joint_subcategory_id"),
            joint_sinking_fund_id=data.get("joint_sinking_fund_id"),
            created_by_profile=str(profile_val),
            paid_by=str(paid_by_val),
            settlement_mechanism=str(settlement_mechanism_val) if settlement_mechanism_val else None,
            settlement_status=str(settlement_status_val),
            settled_at=settled_at_val,
        )

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

    def settle_joint_transaction(self, tx_id: int) -> Optional[joint_model.JointTransaction]:
        """Marca una transacción conjunta pendiente como liquidada/reembolsada."""
        tx = self.get_joint_transaction(tx_id)
        if not tx:
            return None
        tx.settlement_status = "SETTLED"
        tx.settled_at = datetime.datetime.now(datetime.timezone.utc)
        self.db.commit()
        self.db.refresh(tx)
        return tx

    def settle_all_joint_transactions(self) -> List[joint_model.JointTransaction]:
        """Marca todas las transacciones conjuntas pendientes como liquidadas/reembolsadas."""
        unsettled = (
            self.db.query(joint_model.JointTransaction)
            .filter(
                joint_model.JointTransaction.joint_account_id == 1,
                joint_model.JointTransaction.settlement_status == "PENDING",
            )
            .all()
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        for tx in unsettled:
            tx.settlement_status = "SETTLED"
            tx.settled_at = now
        self.db.commit()
        for tx in unsettled:
            self.db.refresh(tx)
        return unsettled

    def get_unsettled_joint_transactions(self) -> List[joint_model.JointTransaction]:
        """Obtiene todas las transacciones con liquidación pendiente."""
        return (
            self.db.query(joint_model.JointTransaction)
            .filter(
                joint_model.JointTransaction.joint_account_id == 1,
                joint_model.JointTransaction.settlement_status == "PENDING",
            )
            .order_by(joint_model.JointTransaction.date.desc())
            .all()
        )

    def delete_joint_transaction(self, tx_id: int) -> Optional[str]:
        """Elimina una transacción y retorna su UUID para emitir el tombstone de sincronización."""
        tx = self.get_joint_transaction(tx_id)
        if not tx:
            return None

        tx_uuid = tx.uuid
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
        query = self.db.query(joint_model.JointMonthlyContribution).filter(
            joint_model.JointMonthlyContribution.joint_account_id == 1
        )
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
        self.db.query(joint_model.JointAppliedSyncEvent).delete()
        account = self.get_joint_account()
        if account:
            self.db.delete(account)
        else:
            self.db.query(joint_model.JointTransaction).delete()
            self.db.query(joint_model.JointMonthlyContribution).delete()
            self.db.query(joint_model.JointSinkingFund).delete()
            self.db.query(joint_model.JointSubcategory).delete()
            self.db.query(joint_model.JointCategory).delete()

        self.db.commit()
        return True
