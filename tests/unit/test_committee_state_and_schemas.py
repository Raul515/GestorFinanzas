"""
Pruebas unitarias para BaseAgent, InvestmentCommitteeState, Schemas y LocalDocLoader (Spec 005 - Fase 1).
"""

from datetime import datetime, timezone
import operator
import os
import pytest
from pydantic import ValidationError

from backend.agents.base_agent import BaseAgent
from backend.domain.states.investment_committee_state import InvestmentCommitteeState
from backend.domain.schemas.committee import (
    AgentLogItem,
    InvestmentCommitteeRequest,
    InvestmentCommitteeResponse,
)
from backend.external_components.data_ingestion.local_doc_loader import LocalDocLoader


# ==============================================================================
# 1. Pruebas de BaseAgent
# ==============================================================================

def test_base_agent_cannot_be_instantiated_directly():
    """Verifica que BaseAgent sea abstracta y no permita instanciación directa sin build_graph."""
    with pytest.raises(TypeError):
        BaseAgent(name="TestAgent", description="Test agent")  # type: ignore[abstract]


class DummyMockAgent(BaseAgent):
    """Subclase concreta de prueba para BaseAgent."""

    def build_graph(self):
        class MockCompiledGraph:
            def invoke(self, state):
                return {**state, "visited_by": "DummyMockAgent"}

        return MockCompiledGraph()


def test_base_agent_subclass_compilation_and_execution():
    """Verifica que una subclase concreta compile y ejecute su grafo correctamente."""
    agent = DummyMockAgent(name="DummyAgent", description="Agent for testing", model_name="gemini-mock")
    assert agent.name == "DummyAgent"
    assert agent.description == "Agent for testing"
    assert agent.model_name == "gemini-mock"
    assert "DummyMockAgent" in repr(agent)

    # Compilación manual o perezosa en run()
    compiled = agent.compile()
    assert compiled is not None
    # Reutiliza el grafo compilado en llamadas subsiguientes
    assert agent.compile() is compiled

    result = agent.run({"input": "test_val"})
    assert result["input"] == "test_val"
    assert result["visited_by"] == "DummyMockAgent"


# ==============================================================================
# 2. Pruebas de InvestmentCommitteeState
# ==============================================================================

def test_investment_committee_state_structure():
    """Verifica la asignación de claves y comportamiento de TypedDict en InvestmentCommitteeState."""
    state: InvestmentCommitteeState = {
        "ticker": "ITX.MC",
        "month": "2026-10",
        "veto_active": False,
        "safety_status": {"coverage_months": 4.5, "investing_allowed": True},
        "bull_thesis": "Excelente ROCE y caja neta.",
        "bear_risks": ["Aumento de costes logísticos", "Desaceleración en China"],
        "agent_logs": [{"agent": "SafetyGuard", "message": "Fondo completo"}],
    }

    assert state["ticker"] == "ITX.MC"
    assert state["month"] == "2026-10"
    assert state["veto_active"] is False
    assert len(state["bear_risks"]) == 2
    assert len(state["agent_logs"]) == 1

    # Verificación del comportamiento del reducer operator.add para agent_logs
    new_logs = [{"agent": "FundamentalAnalyst", "message": "Piotroski 8/9"}]
    combined_logs = operator.add(state["agent_logs"], new_logs)
    assert len(combined_logs) == 2
    assert combined_logs[0]["agent"] == "SafetyGuard"
    assert combined_logs[1]["agent"] == "FundamentalAnalyst"


# ==============================================================================
# 3. Pruebas de Esquemas Pydantic v2 (Committee)
# ==============================================================================

def test_investment_committee_request_valid_and_defaults():
    """Verifica la validación correcta de solicitudes al Comité Asesor."""
    # Solicitud vacía es válida (toma valores por defecto)
    req_empty = InvestmentCommitteeRequest()
    assert req_empty.ticker is None
    assert req_empty.month is None
    assert req_empty.initial_notes is None

    # Solicitud completa
    req_full = InvestmentCommitteeRequest(
        ticker="itx.mc",
        month="2026-10",
        initial_notes="Evaluar asignación de 500€ de excedente.",
    )
    assert req_full.ticker == "itx.mc"
    assert req_full.month == "2026-10"
    assert req_full.initial_notes == "Evaluar asignación de 500€ de excedente."


def test_investment_committee_request_length_validation():
    """Verifica que solicitudes con textos excesivamente largos sean rechazadas."""
    with pytest.raises(ValidationError):
        InvestmentCommitteeRequest(ticker="A" * 20)

    with pytest.raises(ValidationError):
        InvestmentCommitteeRequest(initial_notes="X" * 501)


def test_agent_log_item_schema():
    """Verifica el esquema individual de log de agente."""
    log_item = AgentLogItem(
        agent="MacroAnalyst",
        message="Tipos del BCE en pausa, Bund en 2.30%",
        data_keys=["macro_data"],
    )
    assert log_item.agent == "MacroAnalyst"
    assert "Tipos del BCE" in log_item.message
    assert log_item.data_keys == ["macro_data"]
    assert log_item.timestamp is not None


def test_investment_committee_response_schema():
    """Verifica la creación y serialización del reporte final del Comité Asesor."""
    now = datetime.now(timezone.utc)
    resp = InvestmentCommitteeResponse(
        ticker="ITX.MC",
        month="2026-10",
        veto_active=False,
        safety_summary={"coverage_months": 4.2, "investing_allowed": True},
        bull_thesis="Fuerte ventaja competitiva en logística de proximidad.",
        bear_risks=["Competencia de ultra fast fashion", "Inflación salarial"],
        final_verdict="Aprobada compra gradual con hasta el 30% del saldo sin asignar.",
        agent_logs=[{"agent": "SynthesisNode", "message": "Dictamen aprobado"}],
        created_at=now,
    )

    assert resp.ticker == "ITX.MC"
    assert resp.veto_active is False
    assert len(resp.bear_risks) == 2
    assert resp.created_at == now
    assert resp.safety_summary["coverage_months"] == 4.2


# ==============================================================================
# 4. Pruebas de LocalDocLoader (data_ingestion)
# ==============================================================================

def test_local_doc_loader_empty_and_operations(tmp_path):
    """Verifica la carga, listado y búsqueda en documentos locales."""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()

    loader = LocalDocLoader(knowledge_dir=str(knowledge_dir))
    assert loader.list_documents() == []
    assert loader.search_documents("inditex") == []
    assert loader.load_document("no_existe.md") is None

    # Crear documentos de prueba
    doc1 = knowledge_dir / "tesis_inditex.md"
    doc1.write_text(
        "# Tesis Inditex 2026\nInditex mantiene un retorno sobre capital empleado superior al 25% con nula deuda.",
        encoding="utf-8",
    )

    doc2 = knowledge_dir / "notas_macro.txt"
    doc2.write_text("El BCE prevé recortes de tipos a lo largo de 2026.", encoding="utf-8")

    # Documento con extensión no soportada debe ignorarse
    doc_bin = knowledge_dir / "imagen.png"
    doc_bin.write_bytes(b"\x89PNG")

    docs = loader.list_documents()
    assert len(docs) == 2
    assert "tesis_inditex.md" in docs
    assert "notas_macro.txt" in docs

    # Leer documento
    content = loader.load_document("tesis_inditex.md")
    assert content is not None
    assert "retorno sobre capital empleado" in content

    # Búsqueda por palabra clave
    search_res = loader.search_documents("inditex")
    assert len(search_res) == 1
    assert search_res[0]["document"] == "tesis_inditex.md"
    assert "Inditex" in search_res[0]["snippet"]

    # Búsqueda sin coincidencias
    assert loader.search_documents("criptomoneda") == []

    # Búsqueda vacía
    assert loader.search_documents("") == []
