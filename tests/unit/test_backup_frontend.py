"""
Pruebas unitarias para los métodos cliente de Backup & Restore en api_client.py
y funciones auxiliares de formato de backup_view.py (Spec 011 - Fase 3).
"""

from unittest.mock import MagicMock, patch
import requests
import pytest

from frontend import api_client
from frontend.views.backup_view import format_iso_date


def test_format_iso_date():
    assert format_iso_date(None) == "Nunca"
    assert format_iso_date("") == "Nunca"
    assert format_iso_date("2026-11-03T09:30:00Z") == "03/11/2026 09:30:00"
    assert format_iso_date("2026-11-03T09:30:00+00:00") == "03/11/2026 09:30:00"


@patch("frontend.api_client.requests.get")
def test_client_get_database_health(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "HEALTHY",
        "database_path": "/app/src/backend/data/finanzas.db",
        "file_size_formatted": "1.25 MB",
        "sha256": "abc123456789",
        "integrity_check_passed": True,
        "table_counts": {"transactions": 10},
        "days_since_last_backup": 2,
        "backup_warning_needed": False,
    }
    mock_get.return_value = mock_resp

    health = api_client.get_database_health()
    assert health is not None
    assert health["status"] == "HEALTHY"
    assert health["integrity_check_passed"] is True

    # Error de red
    mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
    assert api_client.get_database_health() is None


@patch("frontend.api_client.requests.post")
def test_client_create_backup(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "filename": "manual_backup_20261103.db",
        "backup_type": "MANUAL",
        "file_size_bytes": 1024,
    }
    mock_post.return_value = mock_resp

    res = api_client.create_backup(custom_name="test.db")
    assert res is not None
    assert res["filename"] == "manual_backup_20261103.db"

    # Fallo HTTP 500
    mock_resp.status_code = 500
    assert api_client.create_backup() is None


@patch("frontend.api_client.requests.get")
def test_client_download_backup_bytes(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"SQLITE_BINARY_DUMMY"
    mock_resp.headers = {"content-disposition": 'attachment; filename="descarga.db"'}
    mock_get.return_value = mock_resp

    res = api_client.download_backup_bytes()
    assert res is not None
    content, filename = res
    assert content == b"SQLITE_BINARY_DUMMY"
    assert filename == "descarga.db"


@patch("frontend.api_client.requests.get")
def test_client_list_backups(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "backups": [{"filename": "b1.db"}],
        "total_count": 1,
        "latest_safety_snapshot": "safety_prerestore_1.db",
    }
    mock_get.return_value = mock_resp

    listing = api_client.list_backups()
    assert listing["total_count"] == 1
    assert listing["latest_safety_snapshot"] == "safety_prerestore_1.db"


@patch("frontend.api_client.requests.post")
def test_client_restore_and_rollback(mock_post):
    # Restore upload exitoso
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "message": "Restaurado OK", "can_rollback": True}
    mock_post.return_value = mock_resp

    res_upload = api_client.restore_backup_upload(b"content", "subida.db")
    assert res_upload is not None
    assert res_upload["success"] is True

    # Restore local exitoso
    res_local = api_client.restore_backup_local("local_1.db")
    assert res_local is not None
    assert res_local["success"] is True

    # Rollback exitoso
    res_rb = api_client.rollback_restore()
    assert res_rb is not None
    assert res_rb["success"] is True

    # Rollback con error 404
    mock_resp.status_code = 404
    mock_resp.json.return_value = {"detail": "No hay snapshot"}
    res_rb_fail = api_client.rollback_restore()
    assert res_rb_fail is not None
    assert res_rb_fail["success"] is False
    assert "No hay snapshot" in res_rb_fail["message"]


@patch("frontend.api_client.requests.delete")
def test_client_delete_backup_local(mock_delete):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_delete.return_value = mock_resp

    assert api_client.delete_backup_local("archivo.db") is True

    mock_resp.status_code = 404
    assert api_client.delete_backup_local("fantasma.db") is False


@patch("frontend.api_client.requests.get")
@patch("frontend.api_client.requests.put")
def test_client_schedule_config(mock_put, mock_get):
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {"enabled": True, "frequency_days": 14, "keep_max_copies": 5}
    mock_get.return_value = mock_get_resp

    schedule = api_client.get_backup_schedule()
    assert schedule is not None
    assert schedule["enabled"] is True
    assert schedule["frequency_days"] == 14

    mock_put_resp = MagicMock()
    mock_put_resp.status_code = 200
    mock_put_resp.json.return_value = {"enabled": True, "frequency_days": 7, "keep_max_copies": 10}
    mock_put.return_value = mock_put_resp

    updated = api_client.update_backup_schedule(enabled=True, frequency_days=7, keep_max_copies=10)
    assert updated is not None
    assert updated["frequency_days"] == 7


@patch("frontend.api_client.requests.post")
def test_client_validate_backup_upload(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "is_valid": True,
        "integrity_status": "ok",
        "table_counts": {"transactions": 5},
        "sha256": "abcdef123456",
        "error_message": None,
    }
    mock_post.return_value = mock_resp

    val = api_client.validate_backup_upload(b"SQLITE_DATA", "val.db")
    assert val is not None
    assert val["is_valid"] is True
    assert val["table_counts"]["transactions"] == 5

    # Error de conexión
    mock_post.side_effect = requests.exceptions.ConnectionError("Net error")
    val_err = api_client.validate_backup_upload(b"SQLITE_DATA", "val.db")
    assert val_err is not None
    assert val_err["is_valid"] is False
    assert "Error de conexión" in val_err["error_message"]

