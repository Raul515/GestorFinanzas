"""Infraestructura HTTP compartida, normalización de frontera y hooks de caché para el frontend."""

import logging
import os
import sys
from typing import Any, Dict, Iterable, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from backend.utils.logging_config import setup_logging

frontend_log_file = os.getenv("FRONTEND_LOG_FILE", "logs/frontend.log")
setup_logging(frontend_log_file)
logger = logging.getLogger(__name__)

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

_session = requests.Session()
_adapter = HTTPAdapter(
    pool_connections=20,
    pool_maxsize=30,
    max_retries=Retry(total=2, backoff_factor=0.2, status_forcelist=[502, 503, 504]),
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def get_session() -> requests.Session:
    """Retorna la sesión HTTP persistente compartida."""
    return _session


def clear_cache_hook(fn_name: str) -> None:
    """Invoca un limpiador de caché registrado en frontend.api_client respetando mocks en tests."""
    facade = sys.modules.get("frontend.api_client") or sys.modules.get("api_client")
    fn = getattr(facade, fn_name, None) if facade else None
    if callable(fn):
        try:
            fn()
        except Exception as exc:
            logger.debug("Error ejecutando hook de caché %s: %s", fn_name, exc)


def normalize_bidirectional(
    record: Dict[str, Any],
    pairs: Iterable[Tuple[str, str]],
) -> Dict[str, Any]:
    """Adapta claves en una única frontera para compatibilidad inglés/español sin duplicar lógica."""
    for en_key, es_key in pairs:
        if en_key in record and es_key not in record:
            record[es_key] = record[en_key]
        if es_key in record and en_key not in record:
            record[en_key] = record[es_key]
    return record


def request(
    method: str,
    path: str,
    *,
    default: Any = None,
    expected_statuses: Tuple[int, ...] = (200,),
    timeout: int = 10,
    params: Optional[Dict[str, Any]] = None,
    json: Any = None,
    files: Any = None,
    data: Any = None,
    headers: Optional[Dict[str, str]] = None,
    raw_response: bool = False,
    http_client: Any = None,
    log_context: Optional[str] = None,
) -> Any:
    """Ejecuta una petición HTTP centralizada con logging estructurado y parsing JSON seguro."""
    url = f"{API_URL}{path}"
    ctx = log_context or f"{method.upper()} {path}"
    method_lower = method.lower()
    if http_client is not None:
        client = http_client
    else:
        facade = sys.modules.get("frontend.api_client") or sys.modules.get("api_client")
        facade_requests = getattr(facade, "requests", None) if facade else None
        req_method = getattr(facade_requests, method_lower, None) if facade_requests else None
        # Respeta @patch("frontend.api_client.requests.<method>") heredado en tests unitarios
        client = facade_requests if hasattr(req_method, "assert_called") else _session
    kwargs: Dict[str, Any] = {"timeout": timeout}
    if params is not None:
        kwargs["params"] = params
    if json is not None:
        kwargs["json"] = json
    if files is not None:
        kwargs["files"] = files
    if data is not None:
        kwargs["data"] = data
    if headers is not None:
        kwargs["headers"] = headers

    try:
        http_fn = getattr(client, method_lower)
        response = http_fn(url, **kwargs)
        if raw_response:
            if response.status_code in expected_statuses:
                return response
            logger.warning("Respuesta no exitosa en %s (%s): %s", ctx, response.status_code, response.text)
            return response

        if response.status_code in expected_statuses:
            return response.json()

        logger.warning("Respuesta no exitosa en %s (%s): %s", ctx, response.status_code, response.text)
    except requests.exceptions.RequestException as exc:
        logger.error("Error de red en %s (%s): %s", ctx, url, exc)
    except Exception as exc:
        logger.error("Error inesperado en %s: %s", ctx, exc)
    return default


def safe_error_detail(response: requests.Response, fallback: str = "") -> str:
    """Extrae de forma segura el campo detail de una respuesta HTTP de error."""
    try:
        data = response.json()
        if isinstance(data, dict) and "detail" in data:
            return str(data["detail"])
    except Exception as exc:
        logger.debug("No se pudo parsear JSON de error HTTP %s: %s", getattr(response, "status_code", "?"), exc)
    return fallback or getattr(response, "text", "")
