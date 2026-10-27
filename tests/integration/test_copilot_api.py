"""
Pruebas de integración para los endpoints REST del Copiloto Patrimonial (Spec 004 - Fase 4).
Verifica el ciclo de vida de sesiones de conversación, gestión de historial y endpoints de chat.
"""

from unittest.mock import patch
from fastapi.testclient import TestClient


def test_list_sessions_initially_empty(client: TestClient):
    """Verifica que el listado de sesiones devuelva una lista vacía inicialmente."""
    response = client.get("/copilot/sessions")
    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_session(client: TestClient):
    """Verifica la creación explícita de una sesión de conversación con título personalizado."""
    res = client.post("/copilot/sessions", json={"title": "Estrategia Semanal"})
    assert res.status_code == 201
    created = res.json()
    assert created["id"] > 0
    assert created["title"] == "Estrategia Semanal"
    assert created["message_count"] == 0

    # Listar sesiones
    list_res = client.get("/copilot/sessions")
    assert list_res.status_code == 200
    sessions = list_res.json()
    assert len(sessions) == 1
    assert sessions[0]["title"] == "Estrategia Semanal"


def test_create_session_default_title(client: TestClient):
    """Verifica que crear una sesión sin título asigne el valor por defecto."""
    res = client.post("/copilot/sessions", json={})
    assert res.status_code == 201
    created = res.json()
    assert created["title"] == "Nueva conversación"


def test_get_session_detail_and_messages(client: TestClient):
    """Verifica la recuperación de una sesión detallada con sus mensajes."""
    res = client.post("/copilot/sessions", json={"title": "Sesión Detallada"})
    session_id = res.json()["id"]

    detail_res = client.get(f"/copilot/sessions/{session_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == session_id
    assert detail["title"] == "Sesión Detallada"
    assert detail["messages"] == []
    assert detail["message_count"] == 0


def test_get_nonexistent_session_returns_404(client: TestClient):
    """Verifica que consultar una sesión inexistente devuelva un código HTTP 404."""
    res = client.get("/copilot/sessions/9999")
    assert res.status_code == 404
    assert "no encontrada" in res.json()["detail"].lower()


def test_delete_session_success_and_cascade(client: TestClient):
    """Verifica la eliminación de una sesión y la respuesta de confirmación."""
    res = client.post("/copilot/sessions", json={"title": "Sesión a borrar"})
    session_id = res.json()["id"]

    del_res = client.delete(f"/copilot/sessions/{session_id}")
    assert del_res.status_code == 200
    assert del_res.json() == {"deleted": True, "session_id": session_id}

    # Verificar que ya no existe
    get_res = client.get(f"/copilot/sessions/{session_id}")
    assert get_res.status_code == 404


def test_delete_nonexistent_session_returns_404(client: TestClient):
    """Verifica que eliminar una sesión inexistente devuelva un código HTTP 404."""
    del_res = client.delete("/copilot/sessions/9999")
    assert del_res.status_code == 404
    assert "no encontrada" in del_res.json()["detail"].lower()


@patch("backend.api.routers.copilot.run_copilot_turn")
def test_copilot_chat_creates_new_session_when_none(mock_turn, client: TestClient):
    """Verifica que enviar un mensaje sin session_id cree una sesión automática y persista el intercambio."""
    mock_turn.return_value = {
        "reply_text": "Tu fondo de emergencia cubre 4.5 meses. Puedes invertir responsablemente.",
        "tools_used": ["get_financial_profile"],
        "tool_calls_details": [
            {"tool": "get_financial_profile", "args": {}, "result_summary": ["fondo_emergencia"]}
        ],
        "model_used": "gemini-2.5-pro",
        "error": False,
    }

    payload = {
        "session_id": None,
        "message": "¿Puedo empezar a invertir en bolsa este mes?",
    }
    chat_res = client.post("/copilot/chat", json=payload)
    assert chat_res.status_code == 200
    data = chat_res.json()

    assert data["session_id"] > 0
    assert data["tools_used"] == ["get_financial_profile"]
    assert "Tu fondo de emergencia cubre 4.5 meses" in data["message"]["content"]
    assert data["message"]["role"] == "assistant"
    assert data["message"]["tool_calls"] is not None
    assert len(data["message"]["tool_calls"]) == 1

    # Verificar que los dos mensajes (usuario y asistente) están persistidos en la sesión
    session_id = data["session_id"]
    detail_res = client.get(f"/copilot/sessions/{session_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["message_count"] == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][0]["content"] == "¿Puedo empezar a invertir en bolsa este mes?"
    assert detail["messages"][1]["role"] == "assistant"


@patch("backend.api.routers.copilot.run_copilot_turn")
def test_copilot_chat_with_existing_session_and_history(mock_turn, client: TestClient):
    """Verifica que continuar un chat en una sesión existente mantenga la continuidad."""
    # 1. Crear sesión
    create_res = client.post("/copilot/sessions", json={"title": "Charla Activa"})
    session_id = create_res.json()["id"]

    mock_turn.return_value = {
        "reply_text": "Respuesta al primer mensaje",
        "tools_used": [],
        "tool_calls_details": [],
        "model_used": "gemini-2.5-pro",
        "error": False,
    }

    # Primer mensaje
    client.post(
        "/copilot/chat",
        json={"session_id": session_id, "message": "Primer mensaje"},
    )

    # Segundo mensaje
    mock_turn.return_value = {
        "reply_text": "Respuesta al segundo mensaje",
        "tools_used": ["get_watchlist_items"],
        "tool_calls_details": [{"tool": "get_watchlist_items", "args": {}}],
        "model_used": "gemini-2.5-pro",
        "error": False,
    }

    chat_res = client.post(
        "/copilot/chat",
        json={"session_id": session_id, "message": "Segundo mensaje"},
    )
    assert chat_res.status_code == 200
    assert chat_res.json()["tools_used"] == ["get_watchlist_items"]

    # Verificar que mock_turn recibió el historial previo
    mock_turn.assert_called()
    _, kwargs = mock_turn.call_args
    history = kwargs["conversation_history"]
    # El historial previo para el 2º mensaje contiene el 1er user y el 1er assistant
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Primer mensaje"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Respuesta al primer mensaje"


def test_copilot_chat_nonexistent_session_returns_404(client: TestClient):
    """Verifica que enviar un chat a una sesión inexistente devuelva un código HTTP 404."""
    chat_res = client.post(
        "/copilot/chat",
        json={"session_id": 9999, "message": "Hola copiloto"},
    )
    assert chat_res.status_code == 404
    assert "no encontrada" in chat_res.json()["detail"].lower()


def test_copilot_chat_validation_error_on_empty_message(client: TestClient):
    """Verifica que un mensaje vacío sea rechazado con HTTP 422."""
    res = client.post("/copilot/chat", json={"message": ""})
    assert res.status_code == 422
