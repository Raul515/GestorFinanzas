"""
Pruebas unitarias para los métodos cliente de actualizaciones OTA en api_client.py
y la lógica de presentación de updater_view.py (Spec 012 - Fase 3).
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from frontend import api_client
from frontend.views.updater_view import format_iso_timestamp, render_updater_view


def test_format_iso_timestamp():
    """Valida la conversión de timestamps ISO a formato legible y manejo de nulos."""
    assert format_iso_timestamp(None) == "Versión inicial (sin registro)"
    assert format_iso_timestamp("") == "Versión inicial (sin registro)"
    assert format_iso_timestamp("2026-11-03T10:30:00Z") == "03/11/2026 10:30:00"
    assert format_iso_timestamp("2026-11-03T10:30:00+00:00") == "03/11/2026 10:30:00"
    # Cadena no estándar
    assert format_iso_timestamp("2026-11-03 Invalid String") == "2026-11-03 Invalid "


@patch("frontend.api_client.requests.get")
def test_client_get_app_version(mock_get):
    """GET /api/updater/version devuelve la versión instalada o None ante fallo de red."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "current_commit": "abc1234",
        "branch": "main",
        "last_updated_at": "2026-11-03T10:00:00Z",
        "rollback_available": True,
        "is_git_repo": False,
    }
    mock_get.return_value = mock_resp

    res = api_client.get_app_version()
    assert res is not None
    assert res["current_commit"] == "abc1234"
    assert res["branch"] == "main"
    assert res["rollback_available"] is True

    # Error de red
    mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
    assert api_client.get_app_version() is None


@patch("frontend.api_client.requests.get")
def test_client_check_for_updates(mock_get):
    """GET /api/updater/check consulta GitHub API con parámetros force y branch."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "update_available": True,
        "current_commit": "abc1234",
        "remote_commit": "def5678",
        "remote_commit_message": "feat: mejoras",
        "cached": False,
        "rate_limit_remaining": 50,
        "error": None,
    }
    mock_get.return_value = mock_resp

    res = api_client.check_for_updates(force=True, branch="develop")
    assert res is not None
    assert res["update_available"] is True
    assert res["remote_commit"] == "def5678"

    mock_get.assert_called_once()
    assert mock_get.call_args[1]["params"] == {"force": True, "branch": "develop"}

    # Error de red
    mock_get.side_effect = requests.exceptions.Timeout("Timeout")
    assert api_client.check_for_updates() is None


@patch("frontend.api_client.requests.post")
def test_client_apply_system_update(mock_post):
    """POST /api/updater/apply envía solicitud de actualización y maneja errores."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "previous_commit": "abc1234",
        "updated_to_commit": "def5678",
        "files_updated_count": 5,
        "requires_rebuild": False,
        "message": "Actualización exitosa",
    }
    mock_post.return_value = mock_resp

    res = api_client.apply_system_update(branch="main", remote_commit="def5678")
    assert res is not None
    assert res["success"] is True
    assert res["updated_to_commit"] == "def5678"

    # Error 400 del servidor
    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 400
    mock_err_resp.json.return_value = {"detail": "Error de sintaxis"}
    mock_post.return_value = mock_err_resp
    res_err = api_client.apply_system_update()
    assert res_err is not None
    assert res_err.get("detail") == "Error de sintaxis"

    # Excepción de red
    mock_post.side_effect = requests.exceptions.ConnectionError("Server unreachable")
    res_conn = api_client.apply_system_update()
    assert res_conn is not None
    assert res_conn["success"] is False
    assert "Error de conexión" in str(res_conn.get("message"))


@patch("frontend.api_client.requests.post")
def test_client_rollback_system_update(mock_post):
    """POST /api/updater/rollback envía petición de reversión y devuelve respuesta."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "restored_commit": "abc1234",
        "message": "Código revertido",
    }
    mock_post.return_value = mock_resp

    res = api_client.rollback_system_update()
    assert res is not None
    assert res["success"] is True
    assert res["restored_commit"] == "abc1234"

    # Excepción de red
    mock_post.side_effect = requests.exceptions.ConnectionError("Offline")
    res_offline = api_client.rollback_system_update()
    assert res_offline is not None
    assert res_offline["success"] is False


@patch("frontend.views.updater_view.st")
@patch("frontend.views.updater_view.api_client.get_app_version")
def test_render_updater_view_error_state(mock_get_ver, mock_st):
    """Verifica que la vista muestre un mensaje de error si el backend no responde."""
    mock_get_ver.return_value = None
    render_updater_view()
    mock_st.error.assert_called_once()
    assert "No se pudo conectar con el servicio backend" in str(mock_st.error.call_args[0][0])


@patch("frontend.views.updater_view.st")
@patch("frontend.views.updater_view.api_client.get_app_version")
def test_render_updater_view_active_state(mock_get_ver, mock_st):
    """Verifica el renderizado regular de métricas de versión y controles."""
    mock_get_ver.return_value = {
        "current_commit": "abc1234567",
        "branch": "main",
        "last_updated_at": "2026-11-03T10:00:00Z",
        "commit_message": "feat: release v1",
        "rollback_available": False,
        "is_git_repo": True,
    }
    mock_st.session_state = {}
    mock_st.columns.side_effect = lambda spec: [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]
    mock_st.button.return_value = False

    render_updater_view()

    # Comprobar llamada de métricas
    assert mock_st.metric.call_count >= 4
    # Comprobar aviso informativo de clon Git
    mock_st.info.assert_called()
    assert "Entorno de desarrollo Git detectado" in str(mock_st.info.call_args[0][0])
