"""
Pruebas unitarias para las herramientas deterministas y nodos de procesamiento del Comité Asesor (Spec 005 - Fase 2).
Valida salvaguarda constitucional, veto en cascada, auditoría cuantitativa, debate obligatorio (mínimo 2 riesgos)
y síntesis de asignación patrimonial.
"""

from unittest.mock import MagicMock, patch
import pytest

from backend.components.nodes.safety_validator_node import safety_validator_node
from backend.components.nodes.macro_evaluation_node import macro_evaluation_node
from backend.components.nodes.fundamental_analysis_node import fundamental_analysis_node
from backend.components.nodes.risk_debate_node import risk_debate_node
from backend.components.nodes.synthesis_node import synthesis_node
from backend.components.tools.committee_tools import (
    fetch_safety_status,
    fetch_macro_overview,
    fetch_fundamental_deepdive,
    search_local_notes,
)
from backend.domain.states.investment_committee_state import InvestmentCommitteeState


# ==============================================================================
# 1. Pruebas de Tools Deterministas (committee_tools.py)
# ==============================================================================

def test_fetch_safety_status_with_mock_services():
    """Verifica que fetch_safety_status consulte correctamente categorías, presupuestos y fondo de emergencia."""
    mock_repo = MagicMock()
    mock_repo.get_categories.return_value = []
    mock_repo.get_subcategories.return_value = []
    mock_repo.get_budgets.return_value = []
    mock_repo.get_transactions.return_value = []

    mock_fund = MagicMock()
    mock_fund.target_months = 3
    mock_fund.current_balance = 4500.0
    mock_fund.target_amount = 3000.0
    mock_fund.is_completed = True
    mock_repo.get_or_create_emergency_fund.return_value = mock_fund

    with patch("backend.components.tools.committee_tools.calculate_category_totals") as mock_totals, \
         patch("backend.components.tools.committee_tools.sync_fund_state", return_value=mock_fund), \
         patch("backend.components.tools.committee_tools.evaluate_safety_status") as mock_eval:

        mock_totals.return_value = {
            "Ingresos Netos": {"real": 3000.0, "presupuesto": 3000.0},
            "Necesidades Básicas": {"real": 1000.0, "presupuesto": 1000.0},
            "Deseos": {"real": 500.0, "presupuesto": 500.0},
            "Ahorro e Inversión": {"real": 500.0, "presupuesto": 500.0},
        }

        mock_status_response = MagicMock()
        mock_status_response.coverage_months = 4.5
        mock_status_response.can_invest = True
        mock_status_response.target_amount = 3000.0
        mock_status_response.current_balance = 4500.0
        mock_status_response.gap = 0.0
        mock_eval.return_value = mock_status_response

        status = fetch_safety_status(repo=mock_repo, month="2026-10")

        assert status["current_balance"] == 4500.0
        assert status["coverage_months"] == 4.5
        assert status["investing_allowed"] is True
        assert status["unassigned_balance"] == 1000.0
        assert status["error"] is False


def test_fetch_macro_overview():
    """Verifica que fetch_macro_overview devuelva indicadores macroeconómicos clave del mercado."""
    overview = fetch_macro_overview()
    assert isinstance(overview, dict)
    assert "indicators" in overview
    assert "total_indicators" in overview
    assert overview["total_indicators"] >= 0


def test_search_local_notes_delegates_to_doc_loader(tmp_path):
    """Verifica que search_local_notes busque documentos locales mediante LocalDocLoader."""
    doc_file = tmp_path / "ITX.md"
    doc_file.write_text("Inditex tiene ventajas competitivas y caja neta récord.", encoding="utf-8")

    notes = search_local_notes("ITX", notes_dir=str(tmp_path))
    assert len(notes) == 1
    assert "Inditex tiene ventajas competitivas" in notes[0]["snippet"]


def test_fetch_fundamental_deepdive_uses_cache_and_service():
    """Verifica que fetch_fundamental_deepdive use caché SQLite si existe o invoque el servicio."""
    mock_repo = MagicMock()
    mock_repo.get_market_cache.return_value = {"ticker": "ITX.MC", "company_name": "Inditex Cached"}

    cached_res = fetch_fundamental_deepdive("ITX.MC", repo=mock_repo)
    assert cached_res is not None
    assert cached_res["company_name"] == "Inditex Cached"

    mock_repo.get_market_cache.return_value = None
    with patch("backend.components.tools.committee_tools.get_equity_deepdive_data") as mock_get_deepdive:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"ticker": "ITX.MC", "company_name": "Inditex Fresh"}
        mock_get_deepdive.return_value = mock_response

        fresh_res = fetch_fundamental_deepdive("ITX.MC", repo=mock_repo)
        assert fresh_res is not None
        assert fresh_res["company_name"] == "Inditex Fresh"
        mock_repo.set_market_cache.assert_called_once()


# ==============================================================================
# 2. Pruebas de SafetyValidatorNode
# ==============================================================================

def test_safety_validator_node_activates_veto_when_under_3_months():
    """Principio 9: Si el fondo cubre menos de 3 meses, activa veto constitucional innegociable."""
    state: InvestmentCommitteeState = {
        "safety_status": {
            "coverage_months": 2.2,
            "investing_allowed": False,
            "current_balance": 2200.0,
            "target_3m": 3000.0,
            "unassigned_balance": 500.0,
        },
        "agent_logs": [],
    }

    result = safety_validator_node(state)

    assert result["veto_active"] is True
    assert len(result["agent_logs"]) == 1
    assert result["agent_logs"][0]["agent"] == "SafetyValidatorNode"
    assert "Veto Constitucional Activado" in result["agent_logs"][0]["message"]
    assert "2.2 meses" in result["agent_logs"][0]["message"]


def test_safety_validator_node_clears_safeguard_when_3_or_more_months():
    """Principio 9: Si el fondo cubre 3 o más meses, autoriza deliberación de inversiones."""
    state: InvestmentCommitteeState = {
        "safety_status": {
            "coverage_months": 4.5,
            "investing_allowed": True,
            "current_balance": 4500.0,
            "target_3m": 3000.0,
            "unassigned_balance": 1200.0,
        },
        "agent_logs": [],
    }

    result = safety_validator_node(state)

    assert result["veto_active"] is False
    assert len(result["agent_logs"]) == 1
    assert "Salvaguarda Superada" in result["agent_logs"][0]["message"]


def test_safety_validator_node_isolated_fallback_activates_veto():
    """Si se ejecuta sin datos previos ni base de datos, aplica fallback defensivo y activa veto."""
    state: InvestmentCommitteeState = {"agent_logs": []}

    result = safety_validator_node(state)

    assert result["veto_active"] is True
    assert result["safety_status"]["coverage_months"] == 0.0


# ==============================================================================
# 3. Pruebas de MacroEvaluationNode
# ==============================================================================

def test_macro_evaluation_node_short_circuits_on_veto():
    """Si el veto está activo, omite la consulta de mercado para ahorrar recursos."""
    state: InvestmentCommitteeState = {
        "veto_active": True,
        "agent_logs": [],
    }

    result = macro_evaluation_node(state)

    assert "macro_data" not in result
    assert len(result["agent_logs"]) == 1
    assert "omitida por veto constitucional activo" in result["agent_logs"][0]["message"]


def test_macro_evaluation_node_executes_when_safeguard_cleared():
    """Si el veto no está activo, recupera y emite los datos macroeconómicos."""
    state: InvestmentCommitteeState = {
        "veto_active": False,
        "agent_logs": [],
    }

    with patch("backend.components.nodes.macro_evaluation_node.fetch_macro_overview") as mock_macro:
        mock_macro.return_value = {
            "timestamp": "2026-10-27T10:00:00Z",
            "indicators": [{"symbol": "^TNX", "name": "US 10Y", "value": 4.2}],
            "total_indicators": 1,
        }

        result = macro_evaluation_node(state)

        assert "macro_data" in result
        assert result["macro_data"]["total_indicators"] == 1
        assert len(result["agent_logs"]) == 1
        assert "Entorno macroeconómico evaluado" in result["agent_logs"][0]["message"]


# ==============================================================================
# 4. Pruebas de FundamentalAnalysisNode
# ==============================================================================

def test_fundamental_analysis_node_short_circuits_on_veto():
    """Si el veto está activo, omite la auditoría de estados contables."""
    state: InvestmentCommitteeState = {
        "veto_active": True,
        "ticker": "ITX.MC",
        "agent_logs": [],
    }

    result = fundamental_analysis_node(state)

    assert "bull_thesis" not in result
    assert len(result["agent_logs"]) == 1
    assert "omitida por veto constitucional activo" in result["agent_logs"][0]["message"]


def test_fundamental_analysis_node_without_ticker():
    """Si no se proporciona un ticker concreto, genera un mensaje contextual pedagógico."""
    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": None,
        "agent_logs": [],
    }

    result = fundamental_analysis_node(state)

    assert "bull_thesis" in result
    assert "no se especificó un ticker" in result["bull_thesis"]


def test_fundamental_analysis_node_generates_bull_thesis_with_gemini_client():
    """Verifica que formule la tesis favorable apoyándose en Gemini si el cliente está provisto."""
    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": "ITX.MC",
        "fundamental_data": {
            "company_name": "Inditex S.A.",
            "piotroski_score": {"score": 8},
            "fcf_analysis": {"fcf_yield_percentage": 5.4},
        },
        "agent_logs": [],
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Tesis Bull Case: FCF creciente y balance sin deuda bancaria."
    mock_client.models.generate_content.return_value = mock_response

    result = fundamental_analysis_node(state, client=mock_client)

    assert "bull_thesis" in result
    assert "Tesis Bull Case" in result["bull_thesis"]
    assert len(result["agent_logs"]) == 1
    assert "Tesis favorable formulada" in result["agent_logs"][0]["message"]


def test_fundamental_analysis_node_offline_fallback():
    """Verifica que formule una tesis determinista si no hay clave API de Gemini."""
    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": "ITX.MC",
        "fundamental_data": {
            "company_name": "Inditex S.A.",
            "piotroski_score": {"score": 9},
            "fcf_analysis": {"fcf_yield_percentage": 5.8},
        },
        "agent_logs": [],
    }

    with patch.dict("os.environ", {}, clear=True):
        result = fundamental_analysis_node(state, client=None)

        assert "bull_thesis" in result
        assert "9/9" in result["bull_thesis"]
        assert "Inditex S.A." in result["bull_thesis"]


# ==============================================================================
# 5. Pruebas de RiskDebateNode (Red Team - Doble Tesis Obligatoria)
# ==============================================================================

def test_risk_debate_node_short_circuits_on_veto():
    """Si el veto está activo, omite el debate de riesgos para renta variable."""
    state: InvestmentCommitteeState = {
        "veto_active": True,
        "ticker": "ITX.MC",
        "agent_logs": [],
    }

    result = risk_debate_node(state)

    assert "bear_risks" not in result
    assert len(result["agent_logs"]) == 1
    assert "omitida por veto constitucional activo" in result["agent_logs"][0]["message"]


def test_risk_debate_node_mandatory_two_bear_risks_with_gemini():
    """Principio 12: Obligatoriedad de al menos 2 riesgos bajistas severos formulados por Gemini."""
    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": "ITX.MC",
        "bull_thesis": "Excelente empresa con Moat.",
        "fundamental_data": {},
        "macro_data": {},
        "agent_logs": [],
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = (
        "- Riesgo 1: Presión salarial en tiendas físicas y aumento del coste logístico global.\n"
        "- Riesgo 2: Volatilidad de divisas en mercados emergentes y desaceleración del consumo discrecional.\n"
    )
    mock_client.models.generate_content.return_value = mock_response

    result = risk_debate_node(state, client=mock_client)

    assert "bear_risks" in result
    assert len(result["bear_risks"]) >= 2
    assert "Presión salarial" in result["bear_risks"][0]
    assert "Volatilidad de divisas" in result["bear_risks"][1]


def test_risk_debate_node_constitutional_fallback_guarantees_two_risks():
    """Principio 12: Si Gemini falla o no devuelve suficientes riesgos, garantiza al menos 2 riesgos severos."""
    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": "ITX.MC",
        "bull_thesis": "Empresa sólida.",
        "agent_logs": [],
    }

    with patch.dict("os.environ", {}, clear=True):
        result = risk_debate_node(state, client=None)

        assert "bear_risks" in result
        assert len(result["bear_risks"]) >= 2
        for r in result["bear_risks"]:
            assert len(r) > 10


# ==============================================================================
# 6. Pruebas de SynthesisNode (Supervisor y Planificador)
# ==============================================================================

def test_synthesis_node_constitutional_veto():
    """Principio 9: Emite veredicto vinculante de veto cuando el fondo cubre menos de 3 meses."""
    state: InvestmentCommitteeState = {
        "veto_active": True,
        "safety_status": {
            "coverage_months": 2.1,
            "current_balance": 2100.0,
            "target_3m": 3000.0,
            "unassigned_balance": 600.0,
            "gap_to_target": 900.0,
        },
        "agent_logs": [],
    }

    result = synthesis_node(state)

    assert "⛔ VETO CONSTITUCIONAL ACTIVO" in result["final_verdict"]
    assert "2.1 meses" in result["final_verdict"]
    assert "Principio 9" in result["final_verdict"]
    assert "600,00 €" in result["action_plan"] or "600.00 €" in result["action_plan"]
    assert "900,00 €" in result["action_plan"] or "900.00 €" in result["action_plan"]


def test_synthesis_node_with_gemini_client():
    """Verifica la emisión de veredicto y plan de acción estructurado con cliente Gemini provisto."""
    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": "ITX.MC",
        "safety_status": {
            "coverage_months": 5.0,
            "unassigned_balance": 3000.0,
        },
        "bull_thesis": "Fuerte generación de FCF.",
        "bear_risks": ["Riesgo 1: Competencia", "Riesgo 2: Tipos altos"],
        "macro_data": {},
        "agent_logs": [],
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = (
        "### VEREDICTO FINAL\nAprobado para asignación escalonada con margen de seguridad del 15%.\n\n"
        "### PLAN DE ACCIÓN\n1. Invertir 900€ en tramo inicial.\n2. Reservar 2100€ para liquidez y acumulación."
    )
    mock_client.models.generate_content.return_value = mock_response

    result = synthesis_node(state, client=mock_client)

    assert "Aprobado para asignación escalonada" in result["final_verdict"]
    assert "Invertir 900€ en tramo inicial" in result["action_plan"]
    assert len(result["agent_logs"]) == 1
    assert "Veredicto final emitido" in result["agent_logs"][0]["message"]


def test_synthesis_node_deterministic_fallback():
    """Verifica que el planificador formule veredicto y tramos del 30%-30%-40% si no hay Gemini."""
    state: InvestmentCommitteeState = {
        "veto_active": False,
        "ticker": "ITX.MC",
        "safety_status": {
            "coverage_months": 4.0,
            "unassigned_balance": 1000.0,
        },
        "bull_thesis": "Tesis positiva.",
        "bear_risks": ["Riesgo de margen", "Riesgo macro"],
        "agent_logs": [],
    }

    with patch.dict("os.environ", {}, clear=True):
        result = synthesis_node(state, client=None)

        assert "⚖️ VEREDICTO FINAL: APROBADO CON ASIGNACIÓN GRADUAL CONDICIONADA" in result["final_verdict"]
        assert "Tramo Inicial (30%)" in result["action_plan"]
        assert "Tramo de Acumulación (30%)" in result["action_plan"]
        assert "Colchón Estratégico (40% restante)" in result["action_plan"]
        assert "300,00 €" in result["action_plan"] or "300.00 €" in result["action_plan"]
