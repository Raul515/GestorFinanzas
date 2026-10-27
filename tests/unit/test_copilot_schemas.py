from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from backend.domain.schemas.copilot import (
    CopilotChatRequest,
    CopilotChatResponse,
    CopilotMessageCreate,
    CopilotMessageResponse,
    CopilotSessionCreate,
    CopilotSessionDetailResponse,
    CopilotSessionResponse,
)


def test_copilot_message_create_valid():
    """Verifica la validación correcta de creación de mensajes."""
    msg = CopilotMessageCreate(
        role="user",
        content="¿Puedo invertir en fondos indexados este mes?",
    )
    assert msg.role == "user"
    assert msg.content == "¿Puedo invertir en fondos indexados este mes?"
    assert msg.tool_calls is None

    # Mensaje de asistente con tool calls
    msg_tool = CopilotMessageCreate(
        role="assistant",
        content="Consultando saldo sin asignar.",
        tool_calls=[{"name": "get_financial_profile", "args": {}}],
    )
    assert msg_tool.role == "assistant"
    assert len(msg_tool.tool_calls or []) == 1


def test_copilot_message_create_invalid():
    """Verifica que mensajes vacíos o con roles no reconocidos fallen."""
    # Mensaje vacío debe fallar
    with pytest.raises(ValidationError):
        CopilotMessageCreate.model_validate(
            {
                "role": "user",
                "content": "",
            }
        )

    # Rol inválido debe fallar
    with pytest.raises(ValidationError):
        CopilotMessageCreate.model_validate(
            {
                "role": "invalido",
                "content": "Mensaje válido",
            }
        )


def test_copilot_message_response_schema():
    """Verifica el esquema de respuesta de un mensaje individual."""
    resp = CopilotMessageResponse(
        id=1,
        session_id=10,
        role="assistant",
        content="Respuesta del copiloto",
        tool_calls=[{"name": "get_watchlist_items", "args": {}}],
        created_at=datetime.now(timezone.utc),
    )
    assert resp.id == 1
    assert resp.session_id == 10
    assert resp.role == "assistant"
    assert resp.tool_calls is not None
    assert resp.tool_calls[0]["name"] == "get_watchlist_items"


def test_copilot_session_create_validation():
    """Verifica la validación del esquema de creación de sesiones."""
    # Sesión sin título es válida
    s_empty = CopilotSessionCreate()
    assert s_empty.title is None

    # Sesión con título normal
    s_title = CopilotSessionCreate(title="Estrategia Q4")
    assert s_title.title == "Estrategia Q4"

    # Título que supere los 150 caracteres debe ser rechazado
    with pytest.raises(ValidationError):
        CopilotSessionCreate.model_validate(
            {
                "title": "A" * 151,
            }
        )


def test_copilot_session_response_and_detail():
    """Verifica esquemas de respuesta resumida y detallada de sesiones."""
    now = datetime.now(timezone.utc)
    summary = CopilotSessionResponse(
        id=1,
        title="Sesión Resumida",
        created_at=now,
        updated_at=now,
        message_count=5,
    )
    assert summary.id == 1
    assert summary.message_count == 5

    detail = CopilotSessionDetailResponse(
        id=1,
        title="Sesión Detallada",
        created_at=now,
        updated_at=now,
        message_count=1,
        messages=[
            CopilotMessageResponse(
                id=101,
                session_id=1,
                role="user",
                content="Hola",
                tool_calls=None,
                created_at=now,
            )
        ],
    )
    assert len(detail.messages) == 1
    assert detail.messages[0].content == "Hola"


def test_copilot_chat_request_and_response():
    """Verifica esquemas de petición y respuesta interactiva de chat."""
    # Petición válida con session_id None (creación sobre la marcha)
    req_new = CopilotChatRequest(message="¿Cuánto tengo en el fondo de emergencia?")
    assert req_new.session_id is None
    assert "fondo de emergencia" in req_new.message

    # Petición válida con session_id existente
    req_exist = CopilotChatRequest(session_id=42, message="Continuar análisis")
    assert req_exist.session_id == 42

    # Petición con mensaje vacío rechazada
    with pytest.raises(ValidationError):
        CopilotChatRequest.model_validate({"message": ""})

    # Respuesta completa
    now = datetime.now(timezone.utc)
    chat_resp = CopilotChatResponse(
        session_id=42,
        session_title="Consulta de Emergencia",
        message=CopilotMessageResponse(
            id=202,
            session_id=42,
            role="assistant",
            content="Tu fondo cubre 3.2 meses.",
            tool_calls=[{"name": "get_financial_profile", "args": {}}],
            created_at=now,
        ),
        tools_used=["get_financial_profile"],
    )
    assert chat_resp.session_id == 42
    assert chat_resp.session_title == "Consulta de Emergencia"
    assert chat_resp.tools_used == ["get_financial_profile"]
    assert chat_resp.message.role == "assistant"
