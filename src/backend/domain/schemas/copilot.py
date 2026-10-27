import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CopilotMessageBase(BaseModel):
    """Esquema base para un mensaje del Copiloto Patrimonial."""
    role: Literal["user", "assistant", "system", "tool"] = Field(
        ..., description="Rol del emisor del mensaje (user, assistant, system o tool)"
    )
    content: str = Field(..., min_length=1, description="Contenido textual del mensaje")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Llamadas a herramientas ejecutadas asociadas al mensaje"
    )


class CopilotMessageCreate(BaseModel):
    """Esquema para la creación o inserción de un mensaje en una sesión."""
    role: Literal["user", "assistant", "system", "tool"] = Field(
        default="user", description="Rol del mensaje enviado"
    )
    content: str = Field(..., min_length=1, description="Texto del mensaje")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Herramientas registradas si aplica"
    )


class CopilotMessageResponse(BaseModel):
    """Esquema de respuesta para un mensaje individual dentro de una sesión."""
    id: int = Field(..., description="Identificador único del mensaje")
    session_id: int = Field(..., description="ID de la sesión de conversación")
    role: str = Field(..., description="Rol del emisor")
    content: str = Field(..., description="Texto del mensaje")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Llamadas a herramientas ejecutadas"
    )
    created_at: datetime = Field(..., description="Marca temporal de creación")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tool_calls", mode="before")
    @classmethod
    def parse_tool_calls_json(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class CopilotSessionCreate(BaseModel):
    """Esquema para la creación explícita de una nueva sesión de chat."""
    title: Optional[str] = Field(
        default=None, max_length=150, description="Título opcional para identificar la conversación"
    )


class CopilotSessionResponse(BaseModel):
    """Esquema de respuesta resumida de una sesión de conversación."""
    id: int = Field(..., description="Identificador único de la sesión")
    title: str = Field(..., description="Título de la conversación")
    created_at: datetime = Field(..., description="Fecha y hora de creación")
    updated_at: datetime = Field(..., description="Fecha y hora de última actividad")
    message_count: int = Field(default=0, description="Número total de mensajes almacenados en la sesión")

    model_config = ConfigDict(from_attributes=True)


class CopilotSessionDetailResponse(CopilotSessionResponse):
    """Esquema de respuesta detallada de una sesión con todos sus mensajes ordenados cronológicamente."""
    messages: List[CopilotMessageResponse] = Field(
        default_factory=list, description="Historial de mensajes de la sesión ordenados por fecha"
    )


class CopilotChatRequest(BaseModel):
    """Esquema de solicitud para enviar un mensaje y obtener respuesta del Copiloto."""
    session_id: Optional[int] = Field(
        default=None, description="ID de sesión existente (si es None, se crea una automáticamente)"
    )
    message: str = Field(..., min_length=1, description="Pregunta o consulta del usuario")


class CopilotChatResponse(BaseModel):
    """Esquema de respuesta del asistente conteniendo el mensaje y herramientas consultadas."""
    session_id: int = Field(..., description="ID de la sesión de conversación")
    session_title: str = Field(..., description="Título de la sesión de conversación")
    message: CopilotMessageResponse = Field(..., description="Mensaje de respuesta generado por el Copiloto")
    tools_used: List[str] = Field(
        default_factory=list, description="Lista de nombres de herramientas invocadas para elaborar la respuesta"
    )
