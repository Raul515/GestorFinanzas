from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.services.llm_copilot_advisor import (
    DEFAULT_COPILOT_MODEL,
    get_configured_copilot_model,
    run_copilot_turn,
)


def test_get_configured_copilot_model_precedence(monkeypatch):
    """Verifica la jerarquía de resolución de modelos para el Copiloto."""
    monkeypatch.delenv("GEMINI_COPILOT_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_DEEPDIVE_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert get_configured_copilot_model() == DEFAULT_COPILOT_MODEL

    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-flash")
    assert get_configured_copilot_model() == "gemini-1.5-flash"

    monkeypatch.setenv("GEMINI_DEEPDIVE_MODEL", "gemini-2.5-pro")
    assert get_configured_copilot_model() == "gemini-2.5-pro"

    monkeypatch.setenv("GEMINI_COPILOT_MODEL", "gemini-3.1-flash")
    assert get_configured_copilot_model() == "gemini-3.1-flash"


def test_run_copilot_turn_no_api_key(db_session: Session, monkeypatch):
    """Verifica que sin clave de API se devuelva un mensaje informativo y educado sin fallos."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    repo = SQLiteRepository(db_session)

    result = run_copilot_turn(
        user_message="¿Cómo está mi fondo de emergencia?",
        conversation_history=[],
        repo=repo,
        api_key="",
    )

    assert result["error"] is False
    assert result["model_used"] == "none"
    assert "Modo Sin Conexión" in result["reply_text"]
    assert result["tools_used"] == []


def test_run_copilot_turn_direct_text_without_tools(db_session: Session):
    """Verifica una respuesta conversacional conceptual donde el modelo no invoca herramientas."""
    repo = SQLiteRepository(db_session)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.function_calls = None
    mock_response.text = "Un fondo indexado es un vehículo de inversión colectiva que replica un índice de mercado."
    mock_client.models.generate_content.return_value = mock_response

    with patch("backend.services.llm_copilot_advisor.genai.Client", return_value=mock_client):
        result = run_copilot_turn(
            user_message="¿Qué es un fondo indexado?",
            conversation_history=[],
            repo=repo,
            api_key="mock_key",
        )

        assert result["error"] is False
        assert "fondo indexado es un vehículo" in result["reply_text"]
        assert result["tools_used"] == []
        assert len(result["tool_calls_details"]) == 0
        assert mock_client.models.generate_content.call_count == 1


def test_run_copilot_turn_with_function_calling_loop(db_session: Session):
    """Verifica el bucle de Function Calling cuando el modelo solicita ejecutar una herramienta."""
    repo = SQLiteRepository(db_session)

    # 1ª respuesta: el modelo solicita ejecutar get_watchlist_items
    mock_call = MagicMock()
    mock_call.name = "get_watchlist_items"
    mock_call.args = {}

    mock_resp1 = MagicMock()
    mock_resp1.function_calls = [mock_call]
    mock_resp1.candidates = [MagicMock()]
    mock_resp1.candidates[0].content = MagicMock()

    # 2ª respuesta: el modelo sintetiza la respuesta con los datos recibidos
    mock_resp2 = MagicMock()
    mock_resp2.function_calls = None
    mock_resp2.text = "He consultado tu lista de seguimiento y actualmente no tienes empresas guardadas."

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [mock_resp1, mock_resp2]

    with patch("backend.services.llm_copilot_advisor.genai.Client", return_value=mock_client):
        result = run_copilot_turn(
            user_message="¿Qué acciones tengo en mi watchlist?",
            conversation_history=[],
            repo=repo,
            api_key="mock_key",
        )

        assert result["error"] is False
        assert result["tools_used"] == ["get_watchlist_items"]
        assert len(result["tool_calls_details"]) == 1
        assert result["tool_calls_details"][0]["tool"] == "get_watchlist_items"
        assert "no tienes empresas guardadas" in result["reply_text"]
        assert mock_client.models.generate_content.call_count == 2


def test_run_copilot_turn_api_exception_fallback(db_session: Session):
    """Verifica la degradación elegante ante fallo de red o cuota de API."""
    repo = SQLiteRepository(db_session)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("ResourceExhausted: 429 Quota Exceeded")

    with patch("backend.services.llm_copilot_advisor.genai.Client", return_value=mock_client):
        result = run_copilot_turn(
            user_message="Analiza mi situación",
            conversation_history=[],
            repo=repo,
            api_key="mock_key",
        )

        assert result["error"] is True
        assert "Aviso del Copiloto Patrimonial" in result["reply_text"]
        assert "ResourceExhausted" in result["reply_text"]


def test_run_copilot_turn_passes_conversation_history(db_session: Session):
    """Verifica que el historial de mensajes de la sesión se estructure adecuadamente en contents."""
    repo = SQLiteRepository(db_session)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.function_calls = None
    mock_response.text = "Continuando con nuestra charla previa..."
    mock_client.models.generate_content.return_value = mock_response

    history = [
        {"role": "user", "content": "Hola, tengo 500 € ahorrados."},
        {"role": "assistant", "content": "¡Hola! Es un buen inicio. ¿Tienes fondo de emergencia?"},
    ]

    with patch("backend.services.llm_copilot_advisor.genai.Client", return_value=mock_client):
        result = run_copilot_turn(
            user_message="Sí, tengo 1000 € en el fondo.",
            conversation_history=history,
            repo=repo,
            api_key="mock_key",
        )

        assert result["error"] is False
        # Verificar contents pasados al cliente
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        contents_arg = call_kwargs["contents"]
        assert len(contents_arg) == 3  # 2 de historia + 1 nuevo
        assert contents_arg[0].role == "user"
        assert contents_arg[1].role == "model"
        assert contents_arg[2].role == "user"
