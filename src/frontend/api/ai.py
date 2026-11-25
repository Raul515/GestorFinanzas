"""Cliente HTTP para Copiloto Patrimonial y Comité Asesor Multiagente."""

from typing import Any, Dict, List, Optional

from frontend.api import http


def get_copilot_sessions() -> List[Dict[str, Any]]:
    """Obtiene el listado de sesiones históricas del Copiloto Patrimonial."""
    return http.request("GET", "/copilot/sessions", default=[], log_context="get_copilot_sessions")


def create_copilot_session(title: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Crea una nueva sesión de conversación para el Copiloto."""
    payload = {"title": title} if title else {}
    return http.request(
        "POST",
        "/copilot/sessions",
        json=payload,
        expected_statuses=(200, 201),
        default=None,
        log_context="create_copilot_session",
    )


def get_copilot_session_detail(session_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene el detalle de una sesión con todos sus mensajes e historial."""
    return http.request(
        "GET",
        f"/copilot/sessions/{session_id}",
        default=None,
        log_context=f"get_copilot_session_detail({session_id})",
    )


def delete_copilot_session(session_id: int) -> bool:
    """Elimina una sesión de conversación y todos sus mensajes."""
    res = http.request(
        "DELETE",
        f"/copilot/sessions/{session_id}",
        default=None,
        log_context=f"delete_copilot_session({session_id})",
    )
    return res is not None


def send_copilot_chat(message: str, session_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Envía un mensaje al Copiloto Patrimonial ejecutando el turno con Function Calling."""
    return http.request(
        "POST",
        "/copilot/chat",
        json={"message": message, "session_id": session_id},
        timeout=60,
        default=None,
        log_context="send_copilot_chat",
    )


def run_investment_committee(
    ticker: Optional[str] = None,
    month: Optional[str] = None,
    initial_notes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Convoca la deliberación del Comité Asesor de Inversión Multiagente (LangGraph)."""
    payload = {
        "ticker": ticker.strip().upper() if ticker and isinstance(ticker, str) and ticker.strip() else None,
        "month": month.strip() if month and isinstance(month, str) and month.strip() else None,
        "initial_notes": initial_notes.strip() if initial_notes and isinstance(initial_notes, str) and initial_notes.strip() else None,
    }
    return http.request(
        "POST",
        "/committee/analyze",
        json=payload,
        timeout=90,
        default=None,
        log_context="run_investment_committee",
    )
