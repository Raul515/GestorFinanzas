"""
Router REST para el Copiloto Patrimonial (Spec 004 - Fase 4).
Expone endpoints para la gestión de sesiones de conversación y el bucle interactivo de chat
con el asistente patrimonial y su sistema de Function Calling.
"""

import logging
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import get_db
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.interfaz.db_interface import IRepository
from backend.domain.schemas.copilot import (
    CopilotChatRequest,
    CopilotChatResponse,
    CopilotMessageResponse,
    CopilotSessionCreate,
    CopilotSessionDetailResponse,
    CopilotSessionResponse,
)
from backend.services.llm_copilot_advisor import run_copilot_turn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot", "advisor"])


def get_repo(db: Session = Depends(get_db)) -> IRepository:
    """Inyección de dependencias para el repositorio de base de datos."""
    return SQLiteRepository(db)


@router.get("/sessions", response_model=List[CopilotSessionResponse])
def list_copilot_sessions(
    repo: IRepository = Depends(get_repo),
) -> List[CopilotSessionResponse]:
    """
    Obtiene todas las sesiones de conversación registradas con el Copiloto,
    ordenadas cronológicamente por fecha de última actividad descendente.
    """
    sessions = repo.get_copilot_sessions()
    return [CopilotSessionResponse.model_validate(s) for s in sessions]


@router.post(
    "/sessions",
    response_model=CopilotSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_copilot_session(
    session_in: CopilotSessionCreate,
    repo: IRepository = Depends(get_repo),
) -> CopilotSessionResponse:
    """
    Crea explícitamente una nueva sesión de conversación vacía para el Copiloto.
    """
    session = repo.create_copilot_session(title=session_in.title)
    return CopilotSessionResponse.model_validate(session)


@router.get("/sessions/{session_id}", response_model=CopilotSessionDetailResponse)
def get_copilot_session_detail(
    session_id: int,
    repo: IRepository = Depends(get_repo),
) -> CopilotSessionDetailResponse:
    """
    Recupera los detalles de una sesión concreta junto con la totalidad de su
    historial de mensajes y llamadas a herramientas asociadas.
    """
    session = repo.get_copilot_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesión con ID {session_id} no encontrada.",
        )
    return CopilotSessionDetailResponse.model_validate(session)


@router.delete("/sessions/{session_id}")
def delete_copilot_session(
    session_id: int,
    repo: IRepository = Depends(get_repo),
) -> Dict[str, Any]:
    """
    Elimina una sesión de conversación y todos sus mensajes asociados en cascada.
    """
    deleted = repo.delete_copilot_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesión con ID {session_id} no encontrada.",
        )
    return {"deleted": True, "session_id": session_id}


@router.post("/chat", response_model=CopilotChatResponse)
def copilot_chat(
    chat_in: CopilotChatRequest,
    db: Session = Depends(get_db),
    repo: IRepository = Depends(get_repo),
) -> CopilotChatResponse:
    """
    Envía un mensaje al Copiloto Patrimonial.
    - Si no se especifica `session_id`, se inicializa una nueva sesión de forma automática.
    - Persiste el mensaje del usuario.
    - Recupera el historial previo de la sesión.
    - Ejecuta el bucle agéntico con Function Calling bajo demanda (Principio 10) y salvaguarda de riesgo (Principio 9).
    - Persiste la respuesta del asistente y las herramientas utilizadas.
    - Retorna el mensaje resultante y el metadato de herramientas invocadas.
    """
    # 1. Resolver sesión activa
    if chat_in.session_id is None:
        session = repo.create_copilot_session(title=None)
    else:
        session = repo.get_copilot_session(chat_in.session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesión con ID {chat_in.session_id} no encontrada.",
            )

    # 2. Registrar mensaje del usuario en la base de datos
    repo.add_copilot_message(
        session_id=session.id,
        role="user",
        content=chat_in.message,
    )

    # 3. Extraer historial previo para contexto de conversación (excluyendo el recién insertado)
    all_messages = repo.get_copilot_messages(session.id)
    history_for_llm: List[Dict[str, str]] = []
    for m in all_messages[:-1]:
        history_for_llm.append({"role": m.role, "content": m.content})

    # 4. Orquestar el turno conversacional con Function Calling
    turn_result = run_copilot_turn(
        user_message=chat_in.message,
        conversation_history=history_for_llm,
        repo=repo,
        db=db,
    )

    # 5. Persistir la respuesta del asistente
    assistant_msg = repo.add_copilot_message(
        session_id=session.id,
        role="assistant",
        content=turn_result["reply_text"],
        tool_calls=turn_result.get("tool_calls_details"),
    )

    # 6. Refrescar la sesión para obtener el título actualizado (si fue auto-generado)
    refreshed_session = repo.get_copilot_session(session.id)
    session_title = refreshed_session.title if refreshed_session else session.title

    logger.info(
        "Turno de chat completado exitosamente para sesión ID %d. Herramientas: %s",
        session.id,
        turn_result.get("tools_used", []),
    )

    return CopilotChatResponse(
        session_id=session.id,
        session_title=session_title,
        message=CopilotMessageResponse.model_validate(assistant_msg),
        tools_used=turn_result.get("tools_used", []),
    )
