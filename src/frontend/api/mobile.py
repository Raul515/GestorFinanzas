"""Cliente HTTP para Sincronización Móvil Quick-Capture y OTA APK."""

from typing import Any, Dict, Optional
from urllib.parse import quote

import requests

from frontend.api import http

_cached_pairing_token: Optional[str] = None


def get_mobile_pairing_token() -> Optional[str]:
    """Consulta el token de emparejamiento maestro desde el endpoint local admin."""
    global _cached_pairing_token
    data = http.request(
        "GET",
        "/api/mobile/admin/pairing-token",
        timeout=5,
        default=None,
        log_context="get_mobile_pairing_token",
    )
    if isinstance(data, dict):
        token = data.get("pairing_token")
        if token:
            _cached_pairing_token = token
        return token
    return None


def get_cached_pairing_token(force_refresh: bool = False) -> Optional[str]:
    """Retorna el token de emparejamiento móvil en memoria para evitar peticiones redundantes."""
    global _cached_pairing_token
    if _cached_pairing_token and not force_refresh:
        return _cached_pairing_token
    return get_mobile_pairing_token()


def generate_mobile_pin(ttl_seconds: int = 600) -> Optional[Dict[str, Any]]:
    """Solicita la generación de un PIN temporal de 6 dígitos para emparejamiento asistido."""
    return http.request(
        "POST",
        f"/api/mobile/admin/generate-pin?ttl_seconds={ttl_seconds}",
        timeout=5,
        default=None,
        log_context="generate_mobile_pin",
    )


def get_mobile_status() -> Optional[Dict[str, Any]]:
    """Consulta el estado de salud y métricas del servicio de sincronización móvil."""
    global _cached_pairing_token
    data = http.request("GET", "/api/mobile/status", timeout=5, default=None, log_context="get_mobile_status")
    if isinstance(data, dict) and data.get("pairing_token"):
        _cached_pairing_token = data["pairing_token"]
    return data


def process_mobile_folder() -> Optional[Dict[str, Any]]:
    """Dispara el procesamiento manual de ficheros delta en sync/mobile/inbox/."""
    return http.request("POST", "/api/mobile/process-folder", timeout=10, default=None, log_context="process_mobile_folder")


def _mobile_auth_request(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    timeout: int = 5,
    params: Optional[Dict[str, Any]] = None,
    json: Any = None,
    files: Any = None,
    data: Any = None,
    ctx: str = "",
) -> Optional[Dict[str, Any]]:
    global _cached_pairing_token
    effective_token = token or get_cached_pairing_token()
    headers = {"X-Mobile-Pairing-Token": effective_token} if effective_token else {}
    url = f"{http.API_URL}{path}"
    kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout}
    if params is not None:
        kwargs["params"] = params
    if json is not None:
        kwargs["json"] = json
    if files is not None:
        kwargs["files"] = files
    if data is not None:
        kwargs["data"] = data

    try:
        response = getattr(http._session, method.lower())(url, **kwargs)
        if response.status_code == 200:
            return response.json()
        if response.status_code in (401, 403):
            _cached_pairing_token = None
        http.logger.warning("Fallo en %s (%s): %s", ctx or path, response.status_code, response.text)
    except requests.exceptions.RequestException as exc:
        http.logger.error("Error de red en %s en %s: %s", ctx or path, url, exc)
    except Exception as exc:
        http.logger.error("Error inesperado en %s: %s", ctx or path, exc)
    return None


def get_mobile_catalog(token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Consulta el catálogo de subcategorías y conceptos frecuentes para clientes móviles."""
    return _mobile_auth_request("GET", "/api/mobile/catalog", token=token, ctx="get_mobile_catalog")


def get_mobile_monthly_summary(month: Optional[str] = None, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Consulta el resumen de ejecución presupuestaria del mes (50/30/20) para el móvil."""
    params = {"month": month} if month else {}
    return _mobile_auth_request("GET", "/api/mobile/summary", token=token, params=params, ctx="get_mobile_monthly_summary")


def update_mobile_budget(
    month: str,
    subcategory_id: int,
    amount: float,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Ajusta la asignación presupuestaria de una subcategoría para un mes desde el móvil."""
    return _mobile_auth_request(
        "POST",
        "/api/mobile/budget",
        token=token,
        json={"month": month, "subcategory_id": subcategory_id, "amount": amount},
        ctx="update_mobile_budget",
    )


def get_mobile_version() -> Optional[Dict[str, Any]]:
    """Consulta la versión y estado de disponibilidad del APK de Android (OTA Updates)."""
    return http.request("GET", "/api/mobile/version", timeout=5, default=None, log_context="get_mobile_version")


def upload_mobile_apk(
    file_bytes: bytes,
    filename: str,
    version_code: int,
    version_name: str,
    release_notes: str = "",
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Publica una nueva release de APK de Android para distribución OTA."""
    return _mobile_auth_request(
        "POST",
        "/api/mobile/upload-apk",
        token=token,
        timeout=60,
        files={"apk_file": (filename, file_bytes, "application/vnd.android.package-archive")},
        data={
            "version_code": str(version_code),
            "version_name": version_name,
            "release_notes": release_notes,
        },
        ctx="upload_mobile_apk",
    )


def get_mobile_receipt_bytes(
    receipt_filename: str,
    pairing_token: Optional[str] = None,
) -> Optional[bytes]:
    """Descarga los bytes de un comprobante de ticket desde el backend local."""
    global _cached_pairing_token
    if not receipt_filename or not receipt_filename.strip():
        return None

    safe_filename = quote(receipt_filename.strip(), safe="")
    path = f"/api/mobile/receipts/{safe_filename}"
    effective_token = pairing_token or get_cached_pairing_token()
    headers = {"X-Mobile-Pairing-Token": effective_token} if effective_token else None

    response = http.request(
        "GET",
        path,
        headers=headers,
        timeout=5,
        raw_response=True,
        default=None,
        log_context=f"get_mobile_receipt_bytes({receipt_filename})",
    )
    if response is not None and getattr(response, "status_code", None) in (401, 403) and not pairing_token:
        _cached_pairing_token = None
        refreshed = get_cached_pairing_token(force_refresh=True)
        if refreshed:
            response = http.request(
                "GET",
                path,
                headers={"X-Mobile-Pairing-Token": refreshed},
                timeout=5,
                raw_response=True,
                default=None,
                log_context=f"get_mobile_receipt_bytes_retry({receipt_filename})",
            )

    if response is not None and getattr(response, "status_code", None) == 200:
        return response.content
    return None
