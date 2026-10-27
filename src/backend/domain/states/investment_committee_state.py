"""
Definición del Estado Compartido para el Grafo del Comité de Inversión (Spec 005).
Compatible con el StateGraph de LangGraph mediante TypedDict y reducers acumulativos.
"""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class InvestmentCommitteeState(TypedDict, total=False):
    """
    Estado compartido que fluye entre los nodos del Comité Asesor de Inversión en LangGraph.
    Contiene la información de entrada, los diagnósticos intermedios, el registro de deliberación
    y el veredicto final.
    """

    # 1. Datos de Entrada y Contexto
    ticker: Optional[str]
    month: Optional[str]
    initial_notes: Optional[str]

    # 2. Salvaguarda Patrimonial (Principio 9 de la Constitución)
    safety_status: Dict[str, Any]
    veto_active: bool

    # 3. Datos Cuantitativos de Mercado y Contabilidad
    macro_data: Optional[Dict[str, Any]]
    fundamental_data: Optional[Dict[str, Any]]

    # 4. Doble Tesis (Bull Case vs Bear Risks)
    bull_thesis: Optional[str]
    bear_risks: List[str]

    # 5. Veredicto y Síntesis Final
    final_verdict: Optional[str]
    action_plan: Optional[str]

    # 6. Historial de Deliberación Acumulativo (Reducer con operator.add)
    # Permite a cada agente añadir su intervención cronológica sin sobreescribir las anteriores
    agent_logs: Annotated[List[Dict[str, Any]], operator.add]

    # 7. Gestión de Errores y Resiliencia
    error: bool
    error_message: Optional[str]
