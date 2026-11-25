"""
Cliente LLM centralizado para Google Gemini (Spec 017 - Fase 3).
Unifica carga de .env, sanitización de GEMINI_API_KEY, resolución jerárquica de modelos
y medición de latencia externa en todos los servicios y nodos LangGraph.
"""

import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai

from backend.domain.schemas.latency_metrics import ExternalProviderEnum
from backend.services.latency_profiler import track_external_latency

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"


def sanitize_secret_value(value: Optional[str]) -> Optional[str]:
    """Limpia espacios y comillas envolventes de una clave o nombre de modelo."""
    if not value or not value.strip():
        return None
    cleaned = value.strip().strip("'\"")
    return cleaned or None


def get_gemini_api_key(api_key: Optional[str] = None) -> Optional[str]:
    """Resuelve y sanea la clave GEMINI_API_KEY desde parámetro o entorno."""
    return sanitize_secret_value(api_key) or sanitize_secret_value(os.getenv("GEMINI_API_KEY"))


def get_gemini_client(api_key: Optional[str] = None) -> Optional[genai.Client]:
    """Inicializa genai.Client si existe una clave de API válida."""
    clean_key = get_gemini_api_key(api_key)
    if not clean_key:
        return None
    try:
        return genai.Client(api_key=clean_key)
    except Exception as exc:
        logger.warning("Fallo al inicializar genai.Client: %s", exc)
        return None


def resolve_gemini_model(
    *env_vars: str,
    default: str = DEFAULT_GEMINI_MODEL,
    model_override: Optional[str] = None,
) -> str:
    """Resuelve el modelo Gemini priorizando override explícito, variables de entorno y fallback."""
    override = sanitize_secret_value(model_override)
    if override:
        return override

    for var_name in env_vars:
        env_val = sanitize_secret_value(os.getenv(var_name))
        if env_val:
            return env_val

    return default


def generate_gemini_content(
    client: genai.Client,
    *,
    model: str,
    contents: Any,
    config: Any,
    operation: str,
) -> Any:
    """Ejecuta generate_content midiendo la latencia externa bajo ExternalProviderEnum.GEMINI."""
    with track_external_latency(ExternalProviderEnum.GEMINI, operation, target=model) as ctx:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        ctx.status_code = 200
        return response
