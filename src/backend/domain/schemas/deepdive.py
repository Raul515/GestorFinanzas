from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class FinancialStatementYear(BaseModel):
    """Ejercicio contable anual histórico para el análisis fundamental (hasta 4 años)."""
    year: int = Field(..., description="Año fiscal contable")
    revenue: float = Field(..., description="Ingresos totales anuales")
    gross_profit: Optional[float] = Field(default=None, description="Beneficio bruto (None para entidades financieras)")
    operating_income: Optional[float] = Field(default=None, description="Beneficio operativo / EBIT")
    net_income: float = Field(..., description="Beneficio neto atribuible a los accionistas ordinarios")
    diluted_eps: Optional[float] = Field(default=None, description="Beneficio por acción diluido (BPA)")
    total_assets: float = Field(..., description="Activo total del balance")
    current_assets: Optional[float] = Field(default=None, description="Activo corriente (None para banca/seguros)")
    current_liabilities: Optional[float] = Field(default=None, description="Pasivo corriente (None para banca/seguros)")
    long_term_debt: Optional[float] = Field(default=None, description="Deuda financiera a largo plazo")
    total_debt: Optional[float] = Field(default=None, description="Deuda financiera total")
    cash_and_equivalents: Optional[float] = Field(default=None, description="Efectivo y equivalentes de efectivo")
    operating_cash_flow: float = Field(..., description="Flujo de caja operativo (CFO)")
    capital_expenditure: float = Field(..., description="Gastos de capital en inmovilizado (CapEx)")
    free_cash_flow: float = Field(..., description="Flujo de caja libre (CFO - CapEx)")
    shares_outstanding: Optional[float] = Field(default=None, description="Número total de acciones ordinarias en circulación")

    model_config = ConfigDict(from_attributes=True)


class PiotroskiCriterion(BaseModel):
    """Evaluación de un criterio contable discreto del Piotroski F-Score."""
    code: str = Field(..., description="Código identificador de la regla contable, ej. ROA, CFO, DELTA_ROA")
    category: Literal["profitability", "leverage_liquidity", "operating_efficiency"] = Field(
        ..., description="Categoría del criterio contable de Piotroski"
    )
    description: str = Field(..., description="Descripción explicativa de la prueba contable")
    points: int = Field(..., ge=0, le=1, description="Puntuación binaria: 1 si se cumple el criterio, 0 si no se cumple")
    current_value: Optional[float] = Field(default=None, description="Valor de la métrica en el ejercicio fiscal más reciente")
    previous_value: Optional[float] = Field(default=None, description="Valor de la métrica en el ejercicio fiscal precedente")


class PiotroskiScore(BaseModel):
    """Puntuación consolidada del Piotroski F-Score (0 a 9 puntos) y clasificación de salud financiera."""
    total_score: int = Field(..., ge=0, le=9, description="Puntuación total acumulada")
    max_score: int = Field(default=9, ge=1, le=9, description="Puntuación máxima evaluable (adaptada a 7 para el sector bancario)")
    rating: Literal["Excelente", "Aceptable", "Riesgo Contable"] = Field(
        ..., description="Semáforo cualitativo de solvencia y salud contable"
    )
    criteria: List[PiotroskiCriterion] = Field(
        default_factory=list, description="Desglose discreto de las evaluaciones de los criterios"
    )


class QualityValueReport(BaseModel):
    """Síntesis agéntica institucional de la tesis de inversión bajo metodología Quality Value."""
    quadrant: Literal["Quality Value", "Calidad Cara", "Trampa de Valor"] = Field(
        ..., description="Clasificación estratégica en cuadrante Quality Value"
    )
    summary_thesis: str = Field(..., description="Tesis ejecutiva sintética de inversión")
    six_ingredients: Dict[str, str] = Field(
        default_factory=dict,
        description="Evaluación de los 6 ingredientes clave (crecimiento a largo plazo, vientos de cola, liderazgo, foso defensivo, ROIC/ROE y dificultades temporales)",
    )
    business_model_and_risks: Dict[str, Any] = Field(
        default_factory=dict,
        description="Modelo de negocio, generación de ingresos y dinámica del capital circulante",
    )
    bearish_risks: List[str] = Field(
        default_factory=list,
        description="Lista obligatoria de al menos 2 riesgos bajistas ('¿Qué puede salir mal y cuánto beneficio destruiría?')",
    )
    valuation_projections: Dict[str, Any] = Field(
        default_factory=dict,
        description="Proyecciones a 5 años (Escenario Base vs Estrés, múltiplos de salida y precios objetivos)",
    )
    target_irr_entry_zone: str = Field(
        ..., description="Zona de entrada ideal exigiendo una TIR anualizada del 15% al 20% con margen de seguridad"
    )


class DeepDiveResponse(BaseModel):
    """Carga de datos completa del diagnóstico contable en profundidad (Deep Dive) para un ticker."""
    ticker: str = Field(..., description="Símbolo bursátil del activo")
    name: str = Field(..., description="Nombre o razón social de la empresa")
    sector: Optional[str] = Field(default=None, description="Sector macroeconómico")
    industry: Optional[str] = Field(default=None, description="Industria específica")
    country: Optional[str] = Field(default=None, description="País de constitución o sede principal")
    currency: str = Field(default="EUR", description="Divisa de reporte financiero")
    description: Optional[str] = Field(default=None, description="Descripción del modelo de negocio de la compañía")
    current_price: float = Field(..., description="Última cotización de mercado registrada")
    day_change_pct: Optional[float] = Field(default=None, description="Variación porcentual de la cotización en la sesión")
    market_cap: Optional[float] = Field(default=None, description="Capitalización bursátil total")
    pe_trailing: Optional[float] = Field(default=None, description="Ratio Precio/Beneficio histórico (PER trailing)")
    pe_forward: Optional[float] = Field(default=None, description="Ratio Precio/Beneficio estimado a 12 meses (PER forward)")
    ev_to_ebitda: Optional[float] = Field(default=None, description="Ratio Valor de Empresa sobre EBITDA (EV/EBITDA)")
    price_to_book: Optional[float] = Field(default=None, description="Ratio Precio sobre Valor en Libros (P/B)")
    dividend_yield: Optional[float] = Field(default=None, description="Rentabilidad por dividendo anualizada en porcentaje")
    beta: Optional[float] = Field(default=None, description="Coeficiente de volatilidad Beta respecto al mercado")
    statements: List[FinancialStatementYear] = Field(
        default_factory=list, description="Serie histórica de estados financieros anuales (últimos 3-4 años)"
    )
    piotroski: PiotroskiScore = Field(..., description="Diagnóstico algorítmico del Piotroski F-Score")
    fcf_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métricas de Flujo de Caja Libre: FCF Yield, tasa de conversión a caja, ROE, ROIC y foso defensivo",
    )
    quality_value_report: Optional[QualityValueReport] = Field(
        default=None, description="Tesis agéntica sintetizada Quality Value (None si no hay clave API o cuota agotada)"
    )
    is_financial_institution: bool = Field(
        default=False, description="Indicador booleano de si el activo es un banco o aseguradora"
    )
    from_cache: bool = Field(default=False, description="Indica si la respuesta procede de la caché SQLite de 24 horas")
    updated_at: datetime = Field(..., description="Fecha y hora de extracción o actualización del análisis")

    model_config = ConfigDict(from_attributes=True)
