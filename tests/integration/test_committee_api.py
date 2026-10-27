"""
Pruebas de integración para los endpoints REST del Comité Asesor de Inversión Multiagente (Spec 005 - Fase 4).
Verifica el endpoint POST /committee/analyze, la aplicación del veto constitucional (Principio 9),
la doble tesis obligatoria (Principio 12), la validación de esquemas y la resiliencia operativa.
"""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def test_post_committee_analyze_veto_constitutional(client: TestClient):
    """
    Principio 9: Si el Fondo de Emergencia no cubre 3 meses (caso base de BD vacía con 0.0 meses),
    el endpoint activa inmediatamente el veto constitucional, cortocircuitando y omitiendo el análisis
    de mercado, macroeconomía y renta variable.
    """
    payload = {
        "ticker": "SAN.MC",
        "month": "2026-10",
        "initial_notes": "Deseo invertir en banca española.",
    }

    response = client.post("/committee/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    # 1. Comprobación del Veto
    assert data["veto_active"] is True
    assert data["ticker"] == "SAN.MC"
    assert data["month"] == "2026-10"
    assert "VETO CONSTITUCIONAL" in data["final_verdict"]

    # 2. Cortocircuito patrimonial: no se consultaron activos ni macro
    assert data["macro_summary"] is None
    assert data["fundamental_summary"] is None
    assert data["bull_thesis"] is None
    assert data["bear_risks"] == []

    # 3. Plan de acción de blindaje de liquidez
    assert "Plan de Acción Inmediato de Blindaje Patrimonial" in (data["action_plan"] or "")

    # 4. Trazabilidad de agentes: exactamente 2 nodos (SafetyValidatorNode y SynthesisNode)
    logs = data["agent_logs"]
    assert len(logs) == 2
    assert logs[0]["agent"] == "SafetyValidatorNode"
    assert logs[1]["agent"] == "SynthesisNode"


def test_post_committee_analyze_full_flow_when_safeguard_cleared(client: TestClient):
    """
    Principio 12: Cuando la salvaguarda está superada (fondo >= 3 meses), el endpoint ejecuta
    la deliberación completa: Macro, Fundamental, Debate de Riesgos (mínimo 2 riesgos bajistas) y Síntesis.
    """
    mock_safety_data = {
        "month": "2026-10",
        "coverage_months": 4.5,
        "investing_allowed": True,
        "monthly_needs": 1000.0,
        "target_3m": 3000.0,
        "current_balance": 4500.0,
        "gap_to_target": 0.0,
        "unassigned_balance": 1200.0,
        "effective_income": 3000.0,
        "error": False,
    }

    mock_macro_data = {
        "indicators": [
            {"symbol": "^IBEX", "name": "IBEX 35", "value": 11800.0, "change_pct": 0.5},
            {"symbol": "10Y_ES", "name": "Bono España 10A", "value": 3.05, "change_pct": 0.0},
        ],
        "total_indicators": 2,
        "error": False,
    }

    mock_gemini_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = (
        "### VEREDICTO FINAL\nAprobada asignación prudente con margen de seguridad.\n\n"
        "### PLAN DE ACCIÓN\nDesplegar capital en tres tramos escalonados."
    )
    mock_gemini_client.models.generate_content.return_value = mock_resp

    with patch("backend.components.nodes.safety_validator_node.fetch_safety_status", return_value=mock_safety_data), \
         patch("backend.components.nodes.macro_evaluation_node.fetch_macro_overview", return_value=mock_macro_data), \
         patch("backend.components.nodes.fundamental_analysis_node.fetch_fundamental_deepdive") as mock_dd:

        mock_dd.return_value = {
            "company_name": "Inditex S.A.",
            "ticker": "ITX.MC",
            "piotroski_score": {"score": 8, "verdict": "Excelente Salud Financiera"},
            "fcf_analysis": {"fcf_yield_percentage": 5.4, "moat_status": "Wide Moat"},
        }

        payload = {
            "ticker": "itx.mc",
            "month": "2026-10",
            "initial_notes": "Perfil moderado, horizonte a 5 años.",
        }

        response = client.post("/committee/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()

        # 1. Verificación de salvaguarda superada
        assert data["veto_active"] is False
        assert data["ticker"] == "ITX.MC"
        assert data["month"] == "2026-10"

        # 2. Diagnósticos de mercado y contabilidad
        assert data["macro_summary"] is not None
        assert data["fundamental_summary"] is not None
        assert data["bull_thesis"] is not None

        # 3. Principio 12: Mínimo 2 riesgos bajistas obligatorios formulados
        bear_risks = data["bear_risks"]
        assert len(bear_risks) >= 2

        # 4. Dictamen final y plan de acción presentes
        assert data["final_verdict"] is not None
        assert data["action_plan"] is not None

        # 5. Trazabilidad completa de deliberación (5 agentes)
        logs = data["agent_logs"]
        assert len(logs) == 5
        agent_names = [item["agent"] for item in logs]
        assert agent_names == [
            "SafetyValidatorNode",
            "MacroEvaluationNode",
            "FundamentalAnalysisNode",
            "RiskDebateNode",
            "SynthesisNode",
        ]


def test_post_committee_analyze_general_without_ticker(client: TestClient):
    """
    Verifica que la consulta patrimonial general sin ticker (asignación general del saldo Sin Asignar)
    se ejecute sin errores cuando la salvaguarda está superada.
    """
    mock_safety_data = {
        "month": "2026-10",
        "coverage_months": 5.0,
        "investing_allowed": True,
        "monthly_needs": 1000.0,
        "target_3m": 3000.0,
        "current_balance": 5000.0,
        "gap_to_target": 0.0,
        "unassigned_balance": 1500.0,
        "effective_income": 3500.0,
        "error": False,
    }

    mock_macro_data = {
        "indicators": [{"symbol": "^IBEX", "name": "IBEX 35", "value": 11800.0}],
        "total_indicators": 1,
        "error": False,
    }

    with patch("backend.components.nodes.safety_validator_node.fetch_safety_status", return_value=mock_safety_data), \
         patch("backend.components.nodes.macro_evaluation_node.fetch_macro_overview", return_value=mock_macro_data):

        payload = {
            "month": "2026-10",
            "initial_notes": "¿Cómo distribuyo mi liquidez disponible este mes?",
        }

        response = client.post("/committee/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["veto_active"] is False
        assert data["ticker"] is None
        assert data["month"] == "2026-10"
        assert data["macro_summary"] is not None
        # Sin ticker específico, fundamental_summary es None
        assert data["fundamental_summary"] is None
        assert len(data["bear_risks"]) >= 2
        assert len(data["agent_logs"]) == 5


def test_post_committee_analyze_validation_errors(client: TestClient):
    """Verifica que el schema Pydantic v2 rechace peticiones con ticker o notas excesivamente largas."""
    # Ticker con más de 15 caracteres
    res1 = client.post("/committee/analyze", json={"ticker": "ESTO_ES_UN_TICKER_DEMASIADO_LARGO"})
    assert res1.status_code == 422

    # Notas con más de 500 caracteres
    res2 = client.post("/committee/analyze", json={"initial_notes": "A" * 501})
    assert res2.status_code == 422


def test_post_committee_analyze_handles_orchestrator_exception_gracefully(client: TestClient):
    """
    Verifica que el endpoint capture cualquier fallo crítico no previsto y devuelva
    un código HTTP 500 descriptivo sin provocar caídas silenciosas ni corrupción del servidor.
    """
    with patch("backend.api.routers.committee.MainInvestmentOrchestrator") as mock_orch_cls:
        mock_instance = MagicMock()
        mock_instance.run.side_effect = RuntimeError("Fallo catastrófico simulado en el motor de grafos")
        mock_orch_cls.return_value = mock_instance

        response = client.post("/committee/analyze", json={"ticker": "TEST.MC"})
        assert response.status_code == 500
        error_detail = response.json()["detail"]
        assert "Fallo catastrófico simulado" in error_detail
