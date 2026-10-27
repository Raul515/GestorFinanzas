import json
import pytest
from sqlalchemy.orm import Session
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.models.copilot import CopilotMessage, CopilotSession


def test_create_and_get_copilot_session(db_session: Session):
    """Verifica la creación y recuperación de una sesión de conversación."""
    repo = SQLiteRepository(db_session)

    session = repo.create_copilot_session(title="Planificación Fiscal 2026")
    assert session.id is not None
    assert session.title == "Planificación Fiscal 2026"
    assert session.created_at is not None
    assert session.updated_at is not None

    fetched = repo.get_copilot_session(session.id)
    assert fetched is not None
    assert fetched.id == session.id
    assert fetched.title == "Planificación Fiscal 2026"


def test_create_copilot_session_default_title(db_session: Session):
    """Verifica que una sesión sin título explícito use el valor por defecto."""
    repo = SQLiteRepository(db_session)

    session = repo.create_copilot_session()
    assert session.title == "Nueva conversación"


def test_add_copilot_messages_and_auto_title(db_session: Session):
    """Verifica la inserción de mensajes y la auto-generación de título en el primer mensaje de usuario."""
    repo = SQLiteRepository(db_session)

    session = repo.create_copilot_session()
    assert session.title == "Nueva conversación"

    msg_user = repo.add_copilot_message(
        session_id=session.id,
        role="user",
        content="¿Cómo debería distribuir mi salario este mes entre ahorro e inversión?",
    )
    assert msg_user.id is not None
    assert msg_user.role == "user"
    assert msg_user.content.startswith("¿Cómo debería distribuir")

    # El título debe haberse auto-generado a partir del primer mensaje
    db_session.refresh(session)
    assert session.title != "Nueva conversación"
    assert "¿Cómo debería distribuir" in session.title

    # Añadir respuesta del asistente con tool_calls
    tool_calls_data = [{"name": "get_financial_profile", "args": {}}]
    msg_asst = repo.add_copilot_message(
        session_id=session.id,
        role="assistant",
        content="He consultado tu perfil patrimonial. Tu fondo de emergencia está completo.",
        tool_calls=tool_calls_data,
    )
    assert msg_asst.role == "assistant"
    assert msg_asst.tool_calls is not None
    decoded_tools = json.loads(msg_asst.tool_calls)
    assert decoded_tools[0]["name"] == "get_financial_profile"

    # Recuperar mensajes en orden cronológico
    messages = repo.get_copilot_messages(session.id)
    assert len(messages) == 2
    assert messages[0].id == msg_user.id
    assert messages[1].id == msg_asst.id


def test_copilot_session_cascade_delete(db_session: Session):
    """Verifica que la eliminación de una sesión elimine en cascada todos sus mensajes asociados."""
    repo = SQLiteRepository(db_session)

    session = repo.create_copilot_session(title="Sesión para eliminar")
    repo.add_copilot_message(session_id=session.id, role="user", content="Hola")
    repo.add_copilot_message(session_id=session.id, role="assistant", content="Hola, ¿en qué puedo ayudarte?")

    assert len(repo.get_copilot_messages(session.id)) == 2

    success = repo.delete_copilot_session(session.id)
    assert success is True

    # La sesión ya no debe existir
    assert repo.get_copilot_session(session.id) is None

    # Los mensajes deben haber sido eliminados en cascada
    messages_in_db = db_session.query(CopilotMessage).filter(CopilotMessage.session_id == session.id).all()
    assert len(messages_in_db) == 0


def test_copilot_delete_non_existent_session(db_session: Session):
    """Verifica que intentar eliminar una sesión inexistente devuelva False."""
    repo = SQLiteRepository(db_session)
    assert repo.delete_copilot_session(99999) is False


def test_add_message_to_non_existent_session_raises(db_session: Session):
    """Verifica que registrar un mensaje en una sesión inexistente lance ValueError."""
    repo = SQLiteRepository(db_session)
    with pytest.raises(ValueError, match="no encontrada"):
        repo.add_copilot_message(session_id=99999, role="user", content="Mensaje huérfano")


def test_get_copilot_sessions_ordering(db_session: Session):
    """Verifica que las sesiones se ordenen por fecha de actualización descendente."""
    repo = SQLiteRepository(db_session)

    s1 = repo.create_copilot_session(title="Sesión 1")
    s2 = repo.create_copilot_session(title="Sesión 2")

    # Al añadir un mensaje a s1, su updated_at se vuelve más reciente que s2
    repo.add_copilot_message(session_id=s1.id, role="user", content="Mensaje nuevo en sesión 1")

    sessions = repo.get_copilot_sessions()
    assert len(sessions) >= 2
    assert sessions[0].id == s1.id
