import datetime
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    pass


class JointAccount(Base):
    """Modelo ORM para la cuenta conjunta del hogar (restricción singleton: exactamente 1 hogar por BD local)."""
    __tablename__ = "joint_accounts"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_joint_account_singleton"),
        CheckConstraint("member_a_reference_income >= 0", name="ck_joint_income_a_non_negative"),
        CheckConstraint("member_b_reference_income >= 0", name="ck_joint_income_b_non_negative"),
        CheckConstraint("member_a_contribution_pct >= 0 AND member_a_contribution_pct <= 100", name="ck_joint_pct_a_valid"),
        CheckConstraint("member_b_contribution_pct >= 0 AND member_b_contribution_pct <= 100", name="ck_joint_pct_b_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    household_name: Mapped[str] = mapped_column(String(100), nullable=False)
    cohabitation_stage: Mapped[str] = mapped_column(String(50), nullable=False, default="PRE_COHABITATION")
    contribution_strategy: Mapped[str] = mapped_column(String(50), nullable=False, default="NOMINAL_TEMPLATE")
    split_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="EQUAL_50_50")
    member_a_reference_income: Mapped[float] = mapped_column(Float, default=0.0)
    member_b_reference_income: Mapped[float] = mapped_column(Float, default=0.0)
    member_a_contribution_pct: Mapped[float] = mapped_column(Float, default=50.0)
    member_b_contribution_pct: Mapped[float] = mapped_column(Float, default=50.0)
    local_profile: Mapped[str] = mapped_column(String(20), default="MEMBER_A")
    remote_profile: Mapped[str] = mapped_column(String(20), default="MEMBER_B")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    categories: Mapped[list["JointCategory"]] = relationship(
        "JointCategory", back_populates="account", cascade="all, delete-orphan"
    )
    sinking_funds: Mapped[list["JointSinkingFund"]] = relationship(
        "JointSinkingFund", back_populates="account", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["JointTransaction"]] = relationship(
        "JointTransaction", back_populates="account", cascade="all, delete-orphan"
    )
    contributions: Mapped[list["JointMonthlyContribution"]] = relationship(
        "JointMonthlyContribution", back_populates="account", cascade="all, delete-orphan"
    )


class JointCategory(Base):
    """Modelo ORM para categorías de gastos comunes del hogar (libre de ocio)."""
    __tablename__ = "joint_categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    joint_account_id: Mapped[int] = mapped_column(
        ForeignKey("joint_accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="JOINT_NEEDS")

    account: Mapped["JointAccount"] = relationship("JointAccount", back_populates="categories")
    subcategories: Mapped[list["JointSubcategory"]] = relationship(
        "JointSubcategory", back_populates="category", cascade="all, delete-orphan"
    )


class JointSubcategory(Base):
    """Modelo ORM para subconceptos específicos de necesidades del hogar (alquiler, luz, supermercado...)."""
    __tablename__ = "joint_subcategories"
    __table_args__ = (
        CheckConstraint("monthly_budget >= 0", name="ck_joint_subcategory_budget_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    joint_category_id: Mapped[int] = mapped_column(
        ForeignKey("joint_categories.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_budget: Mapped[float] = mapped_column(Float, default=0.0)

    category: Mapped["JointCategory"] = relationship("JointCategory", back_populates="subcategories")
    transactions: Mapped[list["JointTransaction"]] = relationship(
        "JointTransaction", back_populates="subcategory"
    )


class JointSinkingFund(Base):
    """Modelo ORM para huchas de amortización y metas de ahorro del hogar."""
    __tablename__ = "joint_sinking_funds"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="ck_joint_sinking_target_positive"),
        CheckConstraint("current_balance >= 0", name="ck_joint_sinking_balance_non_negative"),
        CheckConstraint("monthly_target_amount >= 0", name="ck_joint_sinking_monthly_target_non_negative"),
        CheckConstraint("allocation_percentage >= 0 AND allocation_percentage <= 100", name="ck_joint_sinking_alloc_pct_valid"),
        CheckConstraint("priority >= 1", name="ck_joint_sinking_priority_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    joint_account_id: Mapped[int] = mapped_column(
        ForeignKey("joint_accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_amount: Mapped[float] = mapped_column(Float, nullable=False)
    current_balance: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_target_amount: Mapped[float] = mapped_column(Float, default=0.0)
    allocation_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    priority: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    account: Mapped["JointAccount"] = relationship("JointAccount", back_populates="sinking_funds")
    transactions: Mapped[list["JointTransaction"]] = relationship(
        "JointTransaction", back_populates="sinking_fund"
    )


class JointTransaction(Base):
    """Modelo ORM para transacciones del hogar con UUIDv4 para sincronización P2P idempotente."""
    __tablename__ = "joint_transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_joint_transaction_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    joint_account_id: Mapped[int] = mapped_column(
        ForeignKey("joint_accounts.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    joint_subcategory_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("joint_subcategories.id", ondelete="SET NULL"), nullable=True
    )
    joint_sinking_fund_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("joint_sinking_funds.id", ondelete="SET NULL"), nullable=True
    )
    created_by_profile: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    account: Mapped["JointAccount"] = relationship("JointAccount", back_populates="transactions")
    subcategory: Mapped[Optional["JointSubcategory"]] = relationship(
        "JointSubcategory", back_populates="transactions"
    )
    sinking_fund: Mapped[Optional["JointSinkingFund"]] = relationship(
        "JointSinkingFund", back_populates="transactions"
    )


class JointMonthlyContribution(Base):
    """Modelo ORM para el registro de aportaciones mensuales pactadas o extraordinarias de cada miembro."""
    __tablename__ = "joint_monthly_contributions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_joint_contribution_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    joint_account_id: Mapped[int] = mapped_column(
        ForeignKey("joint_accounts.id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[str] = mapped_column(String(7), index=True, nullable=False)  # 'YYYY-MM'
    contributor_profile: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    contribution_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    account: Mapped["JointAccount"] = relationship("JointAccount", back_populates="contributions")


class JointAppliedSyncEvent(Base):
    """Modelo ORM para registrar eventos de sincronización aplicados y garantizar idempotencia absoluta."""
    __tablename__ = "joint_applied_sync_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    applied_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

