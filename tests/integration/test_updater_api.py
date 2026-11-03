"""
Pruebas de integración para los endpoints REST del actualizador OTA (/api/updater) (Spec 012 - Fase 2).
Valida contratos HTTP, códigos de estado (200, 400, 404, 500, 502), inyección del servicio desacoplado,
consultas con caché/force, aplicación con validación sintáctica y reversión de código (rollback).
"""

from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.domain.schemas.updater import (
    CodeRollbackResponse,
    UpdateApplyResponse,
    UpdateCheckResponse,
    VersionInfo,
)


def test_api_get_version(client: TestClient):
    """GET /api/updater/version devuelve 200 con el esquema tipado VersionInfo."""
    mock_version = VersionInfo(
        current_commit="abc1234",
        branch="main",
        last_updated_at="2026-11-03T10:00:00Z",
        commit_message="feat: commit inicial",
        rollback_available=True,
        is_git_repo=False,
    )
    with patch("backend.services.updater_service.get_current_version", return_value=mock_version):
        response = client.get("/api/updater/version")
        assert response.status_code == 200
        data = response.json()
        assert data["current_commit"] == "abc1234"
        assert data["branch"] == "main"
        assert data["rollback_available"] is True
        assert data["is_git_repo"] is False


def test_api_check_updates_success(client: TestClient):
    """GET /api/updater/check devuelve 200 con el estado de actualización remota."""
    mock_check = UpdateCheckResponse(
        update_available=True,
        current_commit="abc1234",
        remote_commit="def5678",
        remote_commit_message="feat(core): nueva funcionalidad",
        remote_commit_date="2026-11-03T12:00:00Z",
        branch="main",
        checked_at="2026-11-03T12:01:00Z",
        cached=False,
        rate_limit_remaining=55,
        error=None,
    )
    with patch("backend.services.updater_service.check_remote_updates", return_value=mock_check) as mock_service:
        response = client.get("/api/updater/check?force=true&branch=main")
        assert response.status_code == 200
        data = response.json()
        assert data["update_available"] is True
        assert data["remote_commit"] == "def5678"
        assert data["remote_commit_message"] == "feat(core): nueva funcionalidad"
        assert data["rate_limit_remaining"] == 55
        mock_service.assert_called_once_with(force=True, branch="main")


def test_api_check_updates_with_rate_limit_error(client: TestClient):
    """GET /api/updater/check devuelve 200 con detalle en el campo error si GitHub limita peticiones."""
    mock_check = UpdateCheckResponse(
        update_available=False,
        current_commit="abc1234",
        remote_commit="",
        remote_commit_message="",
        remote_commit_date=None,
        branch="main",
        checked_at="2026-11-03T12:01:00Z",
        cached=False,
        rate_limit_remaining=0,
        error="Límite de peticiones a GitHub alcanzado (HTTP 403).",
    )
    with patch("backend.services.updater_service.check_remote_updates", return_value=mock_check):
        response = client.get("/api/updater/check")
        assert response.status_code == 200
        data = response.json()
        assert data["update_available"] is False
        assert data["rate_limit_remaining"] == 0
        err_msg = str(data["error"])
        assert "Límite de peticiones" in err_msg


def test_api_apply_update_success(client: TestClient):
    """POST /api/updater/apply aplica la actualización y devuelve 200 con UpdateApplyResponse."""
    mock_apply = UpdateApplyResponse(
        success=True,
        previous_commit="abc1234",
        updated_to_commit="def5678",
        files_updated_count=12,
        obsolete_files_pruned_count=2,
        pre_update_backup_path="/backups/pre_update_safety_20261103.db",
        new_dependencies_detected=True,
        requires_rebuild=True,
        message="Actualización completada con éxito.",
    )
    with patch("backend.services.updater_service.apply_update", return_value=mock_apply) as mock_service:
        payload = {"branch": "develop", "remote_commit": "def5678"}
        response = client.post("/api/updater/apply", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["updated_to_commit"] == "def5678"
        assert data["files_updated_count"] == 12
        assert data["obsolete_files_pruned_count"] == 2
        assert data["requires_rebuild"] is True
        mock_service.assert_called_once_with(branch="develop", remote_commit="def5678")


def test_api_apply_update_validation_error_400(client: TestClient):
    """POST /api/updater/apply devuelve 400 Bad Request si la validación previa o anti-tar-slip falla."""
    with patch(
        "backend.services.updater_service.apply_update",
        side_effect=ValueError("Fallo de sintaxis en el código remoto"),
    ):
        response = client.post("/api/updater/apply", json={})
        assert response.status_code == 400
        data = response.json()
        err_detail = str(data["detail"])
        assert "Fallo de sintaxis" in err_detail


def test_api_apply_update_download_error_502(client: TestClient):
    """POST /api/updater/apply devuelve 502 Bad Gateway si la descarga desde GitHub falla."""
    with patch(
        "backend.services.updater_service.apply_update",
        side_effect=RuntimeError("Error descargando tarball de GitHub (HTTP 500)"),
    ):
        response = client.post("/api/updater/apply")
        assert response.status_code == 502
        data = response.json()
        err_detail = str(data["detail"])
        assert "Error descargando tarball" in err_detail


def test_api_rollback_success(client: TestClient):
    """POST /api/updater/rollback restaura el código previo y devuelve 200 con CodeRollbackResponse."""
    mock_rollback = CodeRollbackResponse(
        success=True,
        restored_commit="abc1234",
        message="Código revertido con éxito a la versión previa.",
    )
    with patch("backend.services.updater_service.rollback_code", return_value=mock_rollback):
        response = client.post("/api/updater/rollback")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["restored_commit"] == "abc1234"
        assert "Código revertido" in data["message"]


def test_api_rollback_not_found_404(client: TestClient):
    """POST /api/updater/rollback devuelve 404 Not Found si no existe instantánea previa."""
    with patch(
        "backend.services.updater_service.rollback_code",
        side_effect=FileNotFoundError("No existe snapshot previo"),
    ):
        response = client.post("/api/updater/rollback")
        assert response.status_code == 404
        data = response.json()
        err_detail = str(data["detail"])
        assert "No existe snapshot previo" in err_detail


def test_api_apply_update_concurrency_conflict_409(client: TestClient):
    """POST /api/updater/apply devuelve 409 Conflict si otra operación está en curso."""
    with patch(
        "backend.services.updater_service.apply_update",
        side_effect=RuntimeError("Ya hay una operación de actualización o reversión en curso..."),
    ):
        response = client.post("/api/updater/apply")
        assert response.status_code == 409
        data = response.json()
        assert "en curso" in data["detail"]


def test_api_rollback_concurrency_conflict_409(client: TestClient):
    """POST /api/updater/rollback devuelve 409 Conflict si otra operación está en curso."""
    with patch(
        "backend.services.updater_service.rollback_code",
        side_effect=RuntimeError("Ya hay una operación de actualización o reversión en curso..."),
    ):
        response = client.post("/api/updater/rollback")
        assert response.status_code == 409
        data = response.json()
        assert "en curso" in data["detail"]


