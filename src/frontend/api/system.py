"""Cliente HTTP para Copias de Seguridad (Backup/Restore) y Actualizador OTA del sistema."""

from typing import Any, Dict, Optional

import requests
import streamlit as st

from frontend.api import http


def get_database_health(http_client: Any = None) -> Optional[Dict[str, Any]]:
    """Consulta el diagnóstico de salud, integridad y advertencia de respaldos."""
    return http.request(
        "GET",
        "/backup/health",
        default=None,
        http_client=http_client,
        log_context="get_database_health",
    )


def create_backup(custom_name: Optional[str] = None, http_client: Any = None) -> Optional[Dict[str, Any]]:
    """Genera una copia de seguridad caliente en el servidor."""
    params = {"custom_name": custom_name} if custom_name else {}
    return http.request(
        "POST",
        "/backup/create",
        params=params,
        expected_statuses=(200, 201),
        timeout=30,
        default=None,
        http_client=http_client,
        log_context="create_backup",
    )


def download_backup_bytes(http_client: Any = None) -> Optional[tuple[bytes, str]]:
    """Descarga los bytes binarios de la base de datos consistente y retorna (bytes, filename)."""
    response = http.request(
        "GET",
        "/backup/download",
        timeout=45,
        raw_response=True,
        default=None,
        http_client=http_client,
        log_context="download_backup_bytes",
    )
    if response is not None and response.status_code == 200:
        filename = "finanzas_backup.db"
        cd = response.headers.get("content-disposition", "")
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip('"')
        return response.content, filename
    return None


def list_backups(http_client: Any = None) -> Dict[str, Any]:
    """Obtiene el catálogo de copias de seguridad locales disponibles."""
    return http.request(
        "GET",
        "/backup/list",
        default={"backups": [], "total_count": 0, "latest_safety_snapshot": None},
        http_client=http_client,
        log_context="list_backups",
    )


def validate_backup_upload(file_bytes: bytes, filename: str, http_client: Any = None) -> Optional[Dict[str, Any]]:
    """Inspecciona y valida un archivo de copia subido sin aplicarlo a la base activa."""
    url = f"{http.API_URL}/backup/validate"
    files = {"file": (filename, file_bytes, "application/x-sqlite3")}
    client = http_client or http._session
    try:
        response = client.post(url, files=files, timeout=30)
        if response.status_code == 200:
            return response.json()
        http.logger.warning("Fallo en validate_backup_upload (%s): %s", response.status_code, response.text)
        return {"is_valid": False, "error_message": http.safe_error_detail(response)}
    except requests.exceptions.RequestException as exc:
        http.logger.error("Error de red en validate_backup_upload en %s: %s", url, exc)
        return {"is_valid": False, "error_message": f"Error de conexión: {str(exc)}"}
    except Exception as exc:
        http.logger.error("Error inesperado en validate_backup_upload(): %s", exc)
        return {"is_valid": False, "error_message": f"Error inesperado: {str(exc)}"}


def restore_backup_upload(file_bytes: bytes, filename: str, http_client: Any = None) -> Optional[Dict[str, Any]]:
    """Sube y aplica un archivo .db de restauración validando previamente su integridad."""
    url = f"{http.API_URL}/backup/restore/upload"
    files = {"file": (filename, file_bytes, "application/x-sqlite3")}
    client = http_client or http._session
    try:
        response = client.post(url, files=files, timeout=45)
        if response.status_code == 200:
            return response.json()
        http.logger.warning("Fallo en restore_backup_upload (%s): %s", response.status_code, response.text)
        return {"success": False, "message": http.safe_error_detail(response)}
    except requests.exceptions.RequestException as exc:
        http.logger.error("Error de red en restore_backup_upload en %s: %s", url, exc)
        return {"success": False, "message": f"Error de conexión: {str(exc)}"}
    except Exception as exc:
        http.logger.error("Error inesperado en restore_backup_upload(): %s", exc)
        return {"success": False, "message": f"Error inesperado: {str(exc)}"}


def _backup_post_message(path: str, timeout: int, ctx: str, http_client: Any = None) -> Dict[str, Any]:
    url = f"{http.API_URL}{path}"
    client = http_client or http._session
    try:
        response = client.post(url, timeout=timeout)
        if response.status_code == 200:
            return response.json()
        http.logger.warning("Fallo en %s (%s): %s", ctx, response.status_code, response.text)
        return {"success": False, "message": http.safe_error_detail(response)}
    except requests.exceptions.RequestException as exc:
        http.logger.error("Error de red en %s en %s: %s", ctx, url, exc)
        return {"success": False, "message": f"Error de conexión: {str(exc)}"}
    except Exception as exc:
        http.logger.error("Error inesperado en %s: %s", ctx, exc)
        return {"success": False, "message": f"Error inesperado: {str(exc)}"}


def restore_backup_local(filename: str, http_client: Any = None) -> Optional[Dict[str, Any]]:
    """Restaura una instantánea del catálogo local en backups/."""
    return _backup_post_message(f"/backup/restore/local/{filename}", 30, "restore_backup_local", http_client)


def rollback_restore(http_client: Any = None) -> Optional[Dict[str, Any]]:
    """Deshace en 1 clic la última restauración aplicando el snapshot previo de seguridad."""
    return _backup_post_message("/backup/restore/rollback", 30, "rollback_restore", http_client)


def delete_backup_local(filename: str, http_client: Any = None) -> bool:
    """Elimina permanentemente una copia de seguridad local del servidor."""
    res = http.request(
        "DELETE",
        f"/backup/local/{filename}",
        default=None,
        http_client=http_client,
        log_context=f"delete_backup_local({filename})",
    )
    return res is not None


def get_backup_schedule(http_client: Any = None) -> Optional[Dict[str, Any]]:
    """Consulta la configuración de programación de copias automáticas."""
    return http.request("GET", "/backup/schedule", default=None, http_client=http_client, log_context="get_backup_schedule")


def update_backup_schedule(
    enabled: bool,
    frequency_days: int,
    keep_max_copies: int,
    http_client: Any = None,
) -> Optional[Dict[str, Any]]:
    """Actualiza la programación de copias periódicas automáticas."""
    return http.request(
        "PUT",
        "/backup/schedule",
        json={
            "enabled": enabled,
            "frequency_days": frequency_days,
            "keep_max_copies": keep_max_copies,
        },
        default=None,
        http_client=http_client,
        log_context="update_backup_schedule",
    )


@st.cache_data(ttl=300, show_spinner=False)
def get_app_version() -> Optional[Dict[str, Any]]:
    """Obtiene la versión del sistema instalada localmente, rama y disponibilidad de rollback."""
    return http.request("GET", "/api/updater/version", default=None, log_context="get_app_version")


def check_for_updates(force: bool = False, branch: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Comprueba en GitHub API si existen nuevas versiones disponibles con soporte de caché."""
    params: Dict[str, Any] = {"force": force}
    if branch:
        params["branch"] = branch
    return http.request("GET", "/api/updater/check", params=params, timeout=15, default=None, log_context="check_for_updates")


def _updater_post(path: str, payload: Optional[Dict[str, Any]], timeout: int, ctx: str) -> Dict[str, Any]:
    url = f"{http.API_URL}{path}"
    try:
        response = http._session.post(url, json=payload, timeout=timeout) if payload is not None else http._session.post(url, timeout=timeout)
        if response.status_code == 200:
            return response.json()
        http.logger.warning("Fallo en %s (%s): %s", ctx, response.status_code, response.text)
        try:
            return response.json()
        except Exception as parse_exc:
            http.logger.debug("Respuesta no JSON en %s (%s): %s", ctx, response.status_code, parse_exc)
            return {"success": False, "message": f"Error del servidor ({response.status_code}): {response.text}"}
    except requests.exceptions.RequestException as exc:
        http.logger.error("Error de red en %s en %s: %s", ctx, url, exc)
        return {"success": False, "message": f"Error de conexión con el servidor backend: {exc}"}
    except Exception as exc:
        http.logger.error("Error inesperado en %s: %s", ctx, exc)
        return {"success": False, "message": f"Error inesperado: {exc}"}


def apply_system_update(branch: Optional[str] = None, remote_commit: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Ejecuta la actualización del sistema en staging, backups y reemplazo atómico."""
    payload: Dict[str, Any] = {}
    if branch:
        payload["branch"] = branch
    if remote_commit:
        payload["remote_commit"] = remote_commit
    return _updater_post("/api/updater/apply", payload, 60, "apply_system_update")


def rollback_system_update() -> Optional[Dict[str, Any]]:
    """Restaura la versión previa de código y dependencias desde la instantánea comprimida."""
    return _updater_post("/api/updater/rollback", None, 30, "rollback_system_update")
