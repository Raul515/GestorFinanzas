from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CohabitationStage(str, Enum):
    """Etapa de convivencia de la pareja."""
    PRE_COHABITATION = "PRE_COHABITATION"
    COHABITATION = "COHABITATION"


class ContributionStrategy(str, Enum):
    """Estrategia de cálculo de aportaciones mensuales."""
    NOMINAL_TEMPLATE = "NOMINAL_TEMPLATE"
    INCOME_PERCENTAGE = "INCOME_PERCENTAGE"


class SplitMode(str, Enum):
    """Modalidad de reparto de la cuota conjunta entre los miembros."""
    EQUAL_50_50 = "EQUAL_50_50"
    INCOME_PROPORTIONAL = "INCOME_PROPORTIONAL"
    CUSTOM_FIXED = "CUSTOM_FIXED"


class ProfileIdentifier(str, Enum):
    """Identificador inequívoco de miembro de la pareja en cada máquina."""
    MEMBER_A = "MEMBER_A"
    MEMBER_B = "MEMBER_B"


class SinkingFundStatus(str, Enum):
    """Estado operativo de una meta de ahorro / hucha de amortización."""
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"


class SyncAction(str, Enum):
    """Acción del delta de sincronización."""
    UPSERT = "UPSERT"
    DELETE = "DELETE"


class SyncEntityType(str, Enum):
    """Tipo de entidad sincronizable entre dispositivos."""
    TRANSACTION = "TRANSACTION"
    CONTRIBUTION = "CONTRIBUTION"
    SINKING_FUND = "SINKING_FUND"
    ACCOUNT = "ACCOUNT"


class HealthStatus(str, Enum):
    """Diagnóstico semafórico determinista de salud financiera del hogar."""
    SUSTAINABLE = "SUSTAINABLE"  # Tasa de esfuerzo < 50%
    TENSION = "TENSION"          # Tasa de esfuerzo 50% - 60%
    ALERT = "ALERT"              # Tasa de esfuerzo > 60%


# ==========================================
# ESQUEMAS DE ESTADO Y ONBOARDING INICIAL
# ==========================================

class JointStatusResponse(BaseModel):
    """Respuesta con el estado de inicialización del espacio conjunto."""
    is_configured: bool
    household_name: Optional[str] = None
    cohabitation_stage: Optional[CohabitationStage] = None
    local_profile: Optional[ProfileIdentifier] = None


class JointAccountSetupRequest(BaseModel):
    """Petición para el Asistente de Configuración Inicial (Onboarding)."""
    household_name: str = Field(min_length=1, max_length=100)
    cohabitation_stage: CohabitationStage = CohabitationStage.PRE_COHABITATION
    contribution_strategy: ContributionStrategy = ContributionStrategy.NOMINAL_TEMPLATE
    split_mode: SplitMode = SplitMode.EQUAL_50_50
    member_a_reference_income: float = Field(ge=0.0, default=0.0)
    member_b_reference_income: float = Field(ge=0.0, default=0.0)
    member_a_contribution_pct: float = Field(ge=0.0, le=100.0, default=50.0)
    member_b_contribution_pct: float = Field(ge=0.0, le=100.0, default=50.0)
    member_a_name: str = Field(default="Miembro A", max_length=100)
    member_b_name: str = Field(default="Miembro B", max_length=100)
    local_profile: ProfileIdentifier = ProfileIdentifier.MEMBER_A
    remote_profile: ProfileIdentifier = ProfileIdentifier.MEMBER_B

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "account_name" in d and "household_name" not in d:
            d["household_name"] = d.pop("account_name")
        if "member_a_estimated_income" in d and "member_a_reference_income" not in d:
            d["member_a_reference_income"] = d.pop("member_a_estimated_income")
        if "member_b_estimated_income" in d and "member_b_reference_income" not in d:
            d["member_b_reference_income"] = d.pop("member_b_estimated_income")
        stage = d.get("cohabitation_stage")
        if stage in ("DATING_COHABITATION", "PRE"):
            d["cohabitation_stage"] = "PRE_COHABITATION"
        elif stage in ("MARRIAGE_LONG_TERM", "COHABITATION", "FULL"):
            d["cohabitation_stage"] = "COHABITATION"
        split = d.get("split_mode")
        if split in ("EQUAL", "50_50", "EQUAL_50_50"):
            d["split_mode"] = "EQUAL_50_50"
        elif split in ("PROPORTIONAL", "INCOME_PROPORTIONAL"):
            d["split_mode"] = "INCOME_PROPORTIONAL"
        return d

    @model_validator(mode="after")
    def validate_profiles_different(self) -> "JointAccountSetupRequest":
        if self.local_profile == self.remote_profile:
            raise ValueError("local_profile y remote_profile deben ser distintos (MEMBER_A vs MEMBER_B).")
        return self


# ==========================================
# ESQUEMAS DE CUENTA CONJUNTA (JOINT ACCOUNT)
# ==========================================

class JointAccountBase(BaseModel):
    """Esquema base para la cuenta conjunta del hogar."""
    household_name: str = Field(min_length=1, max_length=100)
    cohabitation_stage: CohabitationStage
    contribution_strategy: ContributionStrategy
    split_mode: SplitMode
    member_a_reference_income: float = Field(ge=0.0, default=0.0)
    member_b_reference_income: float = Field(ge=0.0, default=0.0)
    member_a_contribution_pct: float = Field(ge=0.0, le=100.0, default=50.0)
    member_b_contribution_pct: float = Field(ge=0.0, le=100.0, default=50.0)
    member_a_name: str = Field(default="Miembro A", max_length=100)
    member_b_name: str = Field(default="Miembro B", max_length=100)
    local_profile: ProfileIdentifier = ProfileIdentifier.MEMBER_A
    remote_profile: ProfileIdentifier = ProfileIdentifier.MEMBER_B


class JointAccountUpdate(BaseModel):
    """Esquema para actualización de configuración del hogar."""
    household_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    cohabitation_stage: Optional[CohabitationStage] = None
    contribution_strategy: Optional[ContributionStrategy] = None
    split_mode: Optional[SplitMode] = None
    member_a_reference_income: Optional[float] = Field(default=None, ge=0.0)
    member_b_reference_income: Optional[float] = Field(default=None, ge=0.0)
    member_a_contribution_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    member_b_contribution_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    member_a_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    member_b_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    local_profile: Optional[ProfileIdentifier] = None
    remote_profile: Optional[ProfileIdentifier] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "account_name" in d and "household_name" not in d:
            d["household_name"] = d.pop("account_name")
        if "member_a_estimated_income" in d and "member_a_reference_income" not in d:
            d["member_a_reference_income"] = d.pop("member_a_estimated_income")
        if "member_b_estimated_income" in d and "member_b_reference_income" not in d:
            d["member_b_reference_income"] = d.pop("member_b_estimated_income")
        stage = d.get("cohabitation_stage")
        if stage in ("DATING_COHABITATION", "PRE"):
            d["cohabitation_stage"] = "PRE_COHABITATION"
        elif stage in ("MARRIAGE_LONG_TERM", "COHABITATION", "FULL"):
            d["cohabitation_stage"] = "COHABITATION"
        split = d.get("split_mode")
        if split in ("EQUAL", "50_50", "EQUAL_50_50"):
            d["split_mode"] = "EQUAL_50_50"
        elif split in ("PROPORTIONAL", "INCOME_PROPORTIONAL"):
            d["split_mode"] = "INCOME_PROPORTIONAL"
        return d


class JointAccountResponse(JointAccountBase):
    """Esquema de respuesta para la cuenta conjunta."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ==========================================
# ESQUEMAS DE CATEGORÍAS Y SUBCATEGORÍAS
# ==========================================

class JointSubcategoryBase(BaseModel):
    """Esquema base de subcategorías de necesidades comunes."""
    name: str = Field(min_length=1, max_length=100)
    monthly_budget: float = Field(ge=0.0, default=0.0)


class JointSubcategoryCreate(JointSubcategoryBase):
    """Esquema para creación de una subcategoría de necesidades."""
    joint_category_id: int


class JointSubcategoryUpdate(BaseModel):
    """Esquema para actualización de una subcategoría."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    monthly_budget: Optional[float] = Field(default=None, ge=0.0)


class JointSubcategoryResponse(JointSubcategoryBase):
    """Esquema de respuesta para subcategoría persistida."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    joint_category_id: int


class JointCategoryBase(BaseModel):
    """Esquema base para categorías del hogar."""
    name: str = Field(min_length=1, max_length=100)
    type: str = "JOINT_NEEDS"


class JointCategoryCreate(JointCategoryBase):
    """Esquema para creación de una categoría."""
    joint_account_id: int


class JointCategoryResponse(JointCategoryBase):
    """Esquema de respuesta para categoría persistida con sus subcategorías."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    joint_account_id: int
    subcategories: list[JointSubcategoryResponse] = []


# ==========================================
# ESQUEMAS DE HUCHAS DE AMORTIZACIÓN (SINKING FUNDS)
# ==========================================

class JointSinkingFundBase(BaseModel):
    """Esquema base para huchas de amortización del hogar."""
    name: str = Field(min_length=1, max_length=100)
    target_amount: float = Field(gt=0.0)
    current_balance: float = Field(ge=0.0, default=0.0)
    monthly_target_amount: float = Field(ge=0.0, default=0.0)
    allocation_percentage: float = Field(ge=0.0, le=100.0, default=0.0)
    status: SinkingFundStatus = SinkingFundStatus.ACTIVE
    priority: int = Field(ge=1, default=1)


class JointSinkingFundCreate(JointSinkingFundBase):
    """Esquema para creación de una nueva hucha de amortización."""
    joint_account_id: Optional[int] = None


class JointSinkingFundUpdate(BaseModel):
    """Esquema para edición de una hucha de amortización."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    target_amount: Optional[float] = Field(default=None, gt=0.0)
    current_balance: Optional[float] = Field(default=None, ge=0.0)
    monthly_target_amount: Optional[float] = Field(default=None, ge=0.0)
    allocation_percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    status: Optional[SinkingFundStatus] = None
    priority: Optional[int] = Field(default=None, ge=1)


class JointSinkingFundResponse(JointSinkingFundBase):
    """Esquema de respuesta para hucha de amortización persistida."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    joint_account_id: int
    created_at: datetime


# ==========================================
# ESQUEMAS DE TRANSACCIONES DEL HOGAR
# ==========================================

class JointTransactionBase(BaseModel):
    """Esquema base para gastos del hogar."""
    date: date
    amount: float = Field(gt=0.0)
    description: str = Field(min_length=1, max_length=255)
    joint_subcategory_id: Optional[int] = None
    joint_sinking_fund_id: Optional[int] = None
    created_by_profile: ProfileIdentifier


class JointTransactionCreate(JointTransactionBase):
    """Esquema para registrar un gasto común."""
    uuid: Optional[str] = None
    joint_account_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_destination_assigned(self) -> "JointTransactionCreate":
        if self.joint_subcategory_id is None and self.joint_sinking_fund_id is None:
            raise ValueError(
                "La transacción debe asignarse a una subcategoría de necesidades o a una hucha de amortización."
            )
        if self.uuid is None:
            self.uuid = str(uuid.uuid4())
        return self


class JointTransactionResponse(JointTransactionBase):
    """Esquema de respuesta para transacción del hogar."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    joint_account_id: int
    created_at: datetime
    updated_at: datetime


# ==========================================
# ESQUEMAS DE APORTACIONES MENSUALES
# ==========================================

class JointMonthlyContributionBase(BaseModel):
    """Esquema base para aportaciones a la cuenta común."""
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")  # Formato YYYY-MM
    contributor_profile: ProfileIdentifier
    amount: float = Field(gt=0.0)
    contribution_date: date
    uuid: Optional[str] = None


class JointMonthlyContributionCreate(JointMonthlyContributionBase):
    """Esquema para creación de aportación."""
    joint_account_id: Optional[int] = None
    personal_transaction_id: Optional[int] = None
    sinking_fund_allocations: Optional[str] = None


class JointMonthlyContributionResponse(JointMonthlyContributionBase):
    """Esquema de respuesta para aportación persistida."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    joint_account_id: int
    personal_transaction_id: Optional[int] = None
    sinking_fund_allocations: Optional[str] = None
    created_at: datetime


# ==========================================
# ESQUEMAS DE SINCRONIZACIÓN ASÍNCRONA P2P (EVENT SOURCING)
# ==========================================

class SyncEventPayload(BaseModel):
    """Esquema de evento delta para buzones sync/outbox y sync/inbox."""
    event_id: str
    entity_type: SyncEntityType
    action: SyncAction
    origin_device_id: str = Field(min_length=1)
    timestamp_utc: str
    payload: dict[str, Any]

    @field_validator("event_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v, version=4)
        except ValueError:
            raise ValueError(f"event_id debe ser un UUIDv4 válido. Recibido: {v}")
        return v

    @field_validator("timestamp_utc")
    @classmethod
    def validate_iso8601_utc(cls, v: str) -> str:
        try:
            # Validar formato ISO-8601
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("timestamp_utc debe incluir zona horaria UTC o 'Z'.")
        except Exception as e:
            raise ValueError(f"timestamp_utc inválido: {e}")
        return v


# ==========================================
# ESQUEMAS DE SALUD Y RESUMEN ANUAL CONSOLIDADO DEL HOGAR
# ==========================================

class JointHealthDiagnosticResponse(BaseModel):
    """Diagnóstico de salud financiera del hogar según semáforo determinista."""
    joint_needs_budget: float
    combined_reference_income: float
    effort_rate_pct: float
    status: HealthStatus
    message: str


class JointAnnualSummaryResponse(BaseModel):
    """Resumen Anual consolidado de la unidad familiar (sin desglose Member A vs Member B)."""
    year: int
    total_needs_spent: float
    total_sinking_funds_saved: float
    effort_rate_pct: float
    health_status: HealthStatus
    monthly_metrics: list[dict[str, Any]] = []
