from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class GuidelineSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"


class MonthlyScenarioType(str, Enum):
    NEEDS_SURPLUS = "NEEDS_SURPLUS"
    NEEDS_DEFICIT = "NEEDS_DEFICIT"
    WANTS_DEFICIT = "WANTS_DEFICIT"
    INCOME_SHORTFALL = "INCOME_SHORTFALL"
    EXTRAORDINARY_INCOME = "EXTRAORDINARY_INCOME"
    HIGH_UNASSIGNED = "HIGH_UNASSIGNED"
    OPTIMAL = "OPTIMAL"


class AnnualScenarioType(str, Enum):
    ANNUAL_SAVINGS_DEFICIT = "ANNUAL_SAVINGS_DEFICIT"
    LIFESTYLE_CREEP = "LIFESTYLE_CREEP"
    FIXED_COST_RIGIDITY = "FIXED_COST_RIGIDITY"
    IDLE_CASH = "IDLE_CASH"
    ANNUAL_BALANCED = "ANNUAL_BALANCED"


class GuidelineActionStrategy(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(description="Nombre descriptivo de la estrategia")
    badge: str = Field(description="Etiqueta rápida (ej. Opción Principal, Propósito, Híbrido)")
    allocation_amount: float = Field(default=0.0, ge=0.0, description="Monto en euros asignado en esta estrategia")
    description: str = Field(description="Explicación detallada de la estrategia")
    breakdown_items: List[str] = Field(default_factory=list, description="Pasos o fases desglosadas")


class CompensationStep(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    priority: int = Field(description="Orden de prelación (1, 2, 3...)")
    source_block: str = Field(description="Bloque de donde se absorbe el dinero")
    amount: float = Field(ge=0.0, description="Importe a absorber en euros")
    action_text: str = Field(description="Pauta operativa a ejecutar")
    can_touch_emergency_fund: bool = Field(default=False, description="Indica si se autoriza recurrir al Fondo de Emergencia")


class SynopticTableRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenario_name: str = Field(description="Nombre del desvío o situación detectada")
    funding_source: str = Field(description="De dónde se saca o a dónde va el dinero")
    touch_emergency_fund: str = Field(description="Regla tajante sobre el Fondo de Emergencia")
    budget_action: str = Field(description="Acción concreta recomendada")


class MonthlyGuidelineItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenario_type: MonthlyScenarioType
    severity: GuidelineSeverity
    title: str
    summary_headline: str
    delta_amount: float
    delta_percentage: float
    strategies: List[GuidelineActionStrategy] = Field(default_factory=list)
    compensation_hierarchy: List[CompensationStep] = Field(default_factory=list)
    synoptic_row: Optional[SynopticTableRow] = None
    emergency_fund_rule: str
    key_recommendation: str


class MonthlyGuidelineReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month_key: str
    month_name: str
    overall_status: str
    status_severity: GuidelineSeverity
    guidelines: List[MonthlyGuidelineItem] = Field(default_factory=list)
    synoptic_table: List[SynopticTableRow] = Field(default_factory=list)
    real_income: float
    real_needs: float
    real_wants: float
    real_savings: float
    unassigned_amount: float
    savings_rate: float
    emergency_fund_coverage_months: float
    emergency_fund_target_months: float
    is_emergency_fund_completed: bool


class AnnualGuidelineItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenario_type: AnnualScenarioType
    severity: GuidelineSeverity
    title: str
    description: str
    metric_value_text: str
    action_plan: str


class AnnualGuidelineReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overall_health: str
    status_severity: GuidelineSeverity
    average_savings_rate: float
    guidelines: List[AnnualGuidelineItem] = Field(default_factory=list)
    summary_text: str
