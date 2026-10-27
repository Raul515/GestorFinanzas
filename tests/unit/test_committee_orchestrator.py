"""
Pruebas unitarias para los Agentes Cognitivos y el Orquestador Principal LangGraph (Spec 005 - Fase 3).
Verifica subgrafos compilados de BaseAgent, StateGraph maestro, cortocircuito condicional por veto
(Principio 9) y deliberación completa con doble tesis obligatoria (Principio 12).
"""

from unittest.mock import MagicMock, patch
import pytest

from backend.agents.safety_guard_agent import SafetyGuardAgent
from backend.agents.macro_agent import MacroAgent
from backend.agents.fundamental_agent import FundamentalAgent
from backend.agents.risk_thesis_agent import RiskThesisAgent
from backend.agents.portfolio_advisor_agent import PortfolioAdvisorAgent
from backend.components.orchestrator.main_investment_orchestrator import (
    MainInvestmentOrchestrator,
    should_continue_after_safety,
)
from backend.domain.states.investment_committee_state import InvestmentCommitteeState


# ==============================================================================
# 1. Pruebas de Agentes Individuales (Especializaciones de BaseAgent)
# ==============================================================================

def test_safety_guard_agent_graph_execution():
    """Verifica que SafetyGuardAgent compile su subgrafo y evalúe la salvaguarda."""
    agent = SafetyGuardAgent()
    assert agent.name == "SafetyGuardAgent"

    state: InvestmentCommitteeState = {
        "safety_status": {
            "coverage_months": 2.0,
            "investing_allowed": False,
            "current_balance": 2000.0,
            "target_3m": 3000.0,
            "unassigned_balance": 300.0,
        },
        "agent_logs": [],
    }

    result = agent.run(state)
    assert result["veto_active"] is True
    assert len(result["agent_logs"]) == 1
    assert result["agent_logs"][0]["agent"] == "SafetyValidatorNode"


def test_macro_agent_graph_execution():
    """Verifica que MacroAgent compile su subgrafo y evalúe el entorno macroeconómico."""
    agent = MacroAgent()
    assert agent.name == "MacroAgent"

    state: InvestmentCommitteeState = {
        "veto_active": False,
        "agent_logs": [],
    }

    with patch("backend.components.nodes.macro_evaluation_node.fetch_macro_overview") as mock_macro:
        mock_macro.return_value = {
            "timestamp": "2026-10-27T10:00:00Z",
            "indicators": [{"symbol": "^IBEX", "name": "IBEX 35", "value": 11800.0}],
            "total_indicators": 1,
        }

        result = agent.run(state)
        assert "macro_data" in result
        assert result["macro_data"]["total_indicators"] == 1


def test_fundamental_agent_graph_execution():
    """Verifica que FundamentalAgent compile su subgrafo y formule la tesis favorable."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Tesis Bull Case: Negocio con ROCE superior al 25% y balance neto de caja."
    mock_client.models.generate_content.return_value = mock_response

    agent = FundamentalAgent(client=mock_client)
    assert agent.name == "FundamentalAgent"

    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": "ITX.MC",
        "fundamental_data": {
            "company_name": "Inditex S.A.",
            "piotroski_score": {"score": 8},
            "fcf_analysis": {"fcf_yield_percentage": 5.5},
        },
        "agent_logs": [],
    }

    result = agent.run(state)
    assert "bull_thesis" in result
    assert "Tesis Bull Case" in result["bull_thesis"]


def test_risk_thesis_agent_graph_execution():
    """Principio 12: Verifica que RiskThesisAgent devuelva obligatoriamente al menos 2 riesgos bajistas."""
    agent = RiskThesisAgent(client=None)
    assert agent.name == "RiskThesisAgent"

    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": "ITX.MC",
        "bull_thesis": "Excelente empresa con Moat.",
        "agent_logs": [],
    }

    with patch.dict("os.environ", {}, clear=True):
        result = agent.run(state)
        assert "bear_risks" in result
        assert len(result["bear_risks"]) >= 2


def test_portfolio_advisor_agent_graph_execution():
    """Verifica que PortfolioAdvisorAgent emita el veredicto vinculante de asignación."""
    agent = PortfolioAdvisorAgent(client=None)
    assert agent.name == "PortfolioAdvisorAgent"

    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": "ITX.MC",
        "safety_status": {
            "coverage_months": 4.5,
            "unassigned_balance": 1500.0,
        },
        "bear_risks": ["Riesgo 1", "Riesgo 2"],
        "agent_logs": [],
    }

    with patch.dict("os.environ", {}, clear=True):
        result = agent.run(state)
        assert "final_verdict" in result
        assert "action_plan" in result
        assert "Tramo Inicial" in result["action_plan"]


# ==============================================================================
# 2. Pruebas de la Función de Enrutamiento Condicional
# ==============================================================================

def test_should_continue_after_safety_routing():
    """Verifica el enrutamiento condicional según el Principio 9 de la Constitución."""
    assert should_continue_after_safety({"veto_active": True}) == "portfolio_advisor"
    assert should_continue_after_safety({"veto_active": False}) == "macro_evaluation"
    assert should_continue_after_safety({}) == "macro_evaluation"


# ==============================================================================
# 3. Pruebas de MainInvestmentOrchestrator (StateGraph Maestro)
# ==============================================================================

def test_orchestrator_veto_constitutional_short_circuit():
    """
    Principio 9: Si el fondo cubre menos de 3 meses, el orquestador cortocircuita directamente
    desde safety_guard a portfolio_advisor, omitiendo macro, fundamental y riesgo.
    """
    orchestrator = MainInvestmentOrchestrator()

    initial_state: InvestmentCommitteeState = {
        "ticker": "SAN.MC",
        "month": "2026-10",
        "safety_status": {
            "coverage_months": 1.9,
            "investing_allowed": False,
            "current_balance": 1900.0,
            "target_3m": 3000.0,
            "unassigned_balance": 400.0,
            "gap_to_target": 1100.0,
        },
        "agent_logs": [],
    }

    final_state = orchestrator.run(initial_state)

    # 1. Comprobación del veto
    assert final_state.get("veto_active") is True
    assert "⛔ VETO CONSTITUCIONAL ACTIVO" in (final_state.get("final_verdict") or "")
    assert "1.9 meses" in (final_state.get("final_verdict") or "")

    # 2. Comprobación del cortocircuito (los agentes de inversión no fueron visitados)
    assert final_state.get("macro_data") is None
    assert final_state.get("bull_thesis") is None
    assert final_state.get("bear_risks") is None

    # 3. Comprobación de logs: exactamente 2 entradas (SafetyValidatorNode y SynthesisNode)
    logs = final_state.get("agent_logs") or []
    assert len(logs) == 2
    assert logs[0]["agent"] == "SafetyValidatorNode"
    assert logs[1]["agent"] == "SynthesisNode"


def test_orchestrator_full_deliberation_flow_when_safeguard_cleared():
    """
    Si el fondo cubre >= 3 meses, el orquestador ejecuta el flujo completo de deliberación
    (Safety -> Macro -> Fundamental -> RiskDebate -> PortfolioAdvisor).
    """
    mock_client = MagicMock()
    mock_gemini_resp = MagicMock()
    mock_gemini_resp.text = (
        "### VEREDICTO FINAL\nAprobada asignación prudente con margen de seguridad.\n\n"
        "### PLAN DE ACCIÓN\nDesplegar capital en tres tramos escalonados."
    )
    mock_client.models.generate_content.return_value = mock_gemini_resp

    orchestrator = MainInvestmentOrchestrator(client=mock_client)

    initial_state: InvestmentCommitteeState = {
        "ticker": "ITX.MC",
        "month": "2026-10",
        "safety_status": {
            "coverage_months": 4.2,
            "investing_allowed": True,
            "current_balance": 4200.0,
            "target_3m": 3000.0,
            "unassigned_balance": 1800.0,
        },
        "fundamental_data": {
            "company_name": "Inditex S.A.",
            "piotroski_score": {"score": 8},
            "fcf_analysis": {"fcf_yield_percentage": 5.2},
        },
        "agent_logs": [],
    }

    with patch("backend.components.nodes.macro_evaluation_node.fetch_macro_overview") as mock_macro:
        mock_macro.return_value = {
            "timestamp": "2026-10-27T10:00:00Z",
            "indicators": [{"symbol": "^IBEX", "name": "IBEX 35", "value": 11800.0}],
            "total_indicators": 1,
        }

        final_state = orchestrator.run(initial_state)

        # 1. Comprobación de salvaguarda superada
        assert final_state.get("veto_active") is False

        # 2. Comprobación de que todos los nodos generaron sus estados
        assert final_state.get("macro_data") is not None
        assert final_state.get("bull_thesis") is not None
        bear_risks = final_state.get("bear_risks") or []
        assert len(bear_risks) >= 2
        assert final_state.get("final_verdict") is not None
        assert final_state.get("action_plan") is not None

        # 3. Comprobación del registro cronológico completo de deliberación (5 agentes)
        logs = final_state.get("agent_logs") or []
        assert len(logs) == 5
        assert logs[0]["agent"] == "SafetyValidatorNode"
        assert logs[1]["agent"] == "MacroEvaluationNode"
        assert logs[2]["agent"] == "FundamentalAnalysisNode"
        assert logs[3]["agent"] == "RiskDebateNode"
        assert logs[4]["agent"] == "SynthesisNode"


def test_orchestrator_handles_exception_gracefully():
    """Verifica que el orquestador capture excepciones críticas y devuelva estado degradado."""
    orchestrator = MainInvestmentOrchestrator()

    # Inyectar error forzado al ejecutar el grafo
    with patch.object(orchestrator, "compile", side_effect=RuntimeError("Fallo simulado en motor LangGraph")):
        result = orchestrator.run({"ticker": "TEST", "agent_logs": []})

        assert result.get("error") is True
        assert "Fallo simulado en motor LangGraph" in (result.get("error_message") or "")
        agent_logs = result.get("agent_logs") or []
        assert len(agent_logs) == 1
        assert agent_logs[0]["agent"] == "MainInvestmentOrchestrator"
