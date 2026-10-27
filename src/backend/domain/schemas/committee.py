"""
Esquemas Pydantic v2 para el Comité Asesor de Inversión Multiagente (Spec 005).
Define los DTOs de solicitud y respuesta estructurada para la API REST y LangGraph.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class InvestmentCommitteeRequest(BaseModel):
    """Esquema de solicitud para convocar la deliberación del Comité Asesor."""

    ticker: Optional[str] = Field(
        default=None,
        max_length=15,
        description="Símbolo bursátil opcional a evaluar (ej. 'ITX.MC', 'AAPL', 'SAN.MC')",
    )
    month: Optional[str] = Field(
        default=None,
        description="Mes contable a auditar en formato 'YYYY-MM' o 'BASE'. Por defecto, mes en curso.",
    )
    initial_notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Observaciones, dudas o contexto financiero adicional proporcionado por el usuario",
    )


class AgentLogItem(BaseModel):
    """Elemento individual del registro cronológico de deliberación de un agente."""

    agent: str = Field(..., description="Identificador del agente o nodo que intervino")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Marca temporal de la intervención",
    )
    message: str = Field(..., description="Resumen de la intervención o conclusión del agente")
    data_keys: List[str] = Field(
        default_factory=list,
        description="Claves de datos que este agente inyectó en el estado compartido",
    )

    model_config = ConfigDict(from_attributes=True)


class InvestmentCommitteeResponse(BaseModel):
    """Esquema de respuesta estructurada con el dictamen unificado del Comité Asesor."""

    ticker: Optional[str] = Field(default=None, description="Símbolo bursátil analizado si aplica")
    month: str = Field(..., description="Mes contable de referencia evaluado")
    veto_active: bool = Field(
        ...,
        description="Indica si el veto constitucional está activo por cobertura del fondo de emergencia < 3 meses",
    )
    safety_summary: Dict[str, Any] = Field(
        ...,
        description="Resumen de la salvaguarda patrimonial (meses cubiertos, saldo actual y objetivo)",
    )
    macro_summary: Optional[Dict[str, Any]] = Field(
        default=None, description="Resumen de indicadores macroeconómicos clave y primas de riesgo"
    )
    fundamental_summary: Optional[Dict[str, Any]] = Field(
        default=None, description="Diagnóstico cuantitativo contable (Piotroski Score, FCF y solvencia)"
    )
    bull_thesis: Optional[str] = Field(
        default=None, description="Tesis alcista / fortalezas competitivas identificadas"
    )
    bear_risks: List[str] = Field(
        default_factory=list,
        description="Lista obligatoria de al menos 2 riesgos bajistas severos ('¿Qué puede salir mal?')",
    )
    final_verdict: str = Field(
        ..., description="Dictamen y veredicto patrimonial unificado del Comité Asesor"
    )
    action_plan: Optional[str] = Field(
        default=None, description="Plan de acción paso a paso para el usuario"
    )
    agent_logs: List[Dict[str, Any]] = Field(
        default_factory=list, description="Cronología de deliberación de cada agente en el grafo"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Marca temporal de emisión del informe",
    )

    model_config = ConfigDict(from_attributes=True)
