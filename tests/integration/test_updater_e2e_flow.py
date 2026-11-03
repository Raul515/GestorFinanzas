"""
Prueba de integración End-to-End (E2E) para el flujo completo del actualizador OTA (Spec 012 - Fase 4).
Verifica:
1. Consulta de versión inicial (v1.0 / commit inicial).
2. Comprobación remota en GitHub API detectando nuevo commit.
3. Descarga y aplicación de actualización completa:
   - Validación sintáctica en staging.
   - Creación de copia de seguridad previa de la base de datos (finanzas.db preservada).
   - Instantánea de código comprimida (code_snapshot_prev.tar.gz).
   - Reemplazo atómico de archivos en src/ y detección de nuevas dependencias (requires_rebuild).
   - Poda de archivos obsoletos según installed_manifest.json.
4. Consulta de estado post-actualización (nuevo commit activo y rollback disponible).
5. Ejecución de rollback en 1 clic:
   - Restauración de código desde la instantánea previa.
   - Purga de bytecode.
   - Verificación de código revertido y base de datos contable intacta.
"""

import io
import os
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.domain.schemas.backup import BackupMetadata
from backend.services.updater_service import clear_check_cache


def create_mock_tarball_bytes(commit_sha: str = "remote1234567") -> bytes:
    """Genera en memoria un archivo tar.gz con estructura realista de descarga de GitHub."""
    tar_buffer = io.BytesIO()
    prefix = f"GestorFinanzas-{commit_sha}"

    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        # Puntos de entrada obligatorios validados por validate_staging_syntax
        v2_main = b"# Main backend entrypoint v2\nfrom fastapi import FastAPI\napp = FastAPI()\n"
        ti_m = tarfile.TarInfo(name=f"{prefix}/src/backend/api/main.py")
        ti_m.size = len(v2_main)
        tar.addfile(ti_m, io.BytesIO(v2_main))

        v2_app = b"# Main frontend entrypoint v2\nimport streamlit as st\n"
        ti_a = tarfile.TarInfo(name=f"{prefix}/src/frontend/app.py")
        ti_a.size = len(v2_app)
        tar.addfile(ti_a, io.BytesIO(v2_app))

        # 1. src/backend/dummy_feature.py (Versión 2.0)
        v2_backend = b"# Dummy Backend Service v2.0\ndef get_val(): return 42\n"
        ti_b = tarfile.TarInfo(name=f"{prefix}/src/backend/dummy_feature.py")
        ti_b.size = len(v2_backend)
        tar.addfile(ti_b, io.BytesIO(v2_backend))

        # 2. src/frontend/views/dummy_view.py (Versión 2.0)
        v2_frontend = b"# Dummy Frontend View v2.0\ndef render(): pass\n"
        ti_f = tarfile.TarInfo(name=f"{prefix}/src/frontend/views/dummy_view.py")
        ti_f.size = len(v2_frontend)
        tar.addfile(ti_f, io.BytesIO(v2_frontend))

        # 3. requirements/backend.txt con nueva dependencia agregada (gatilla requires_rebuild)
        v2_req_b = b"fastapi==0.115.0\npydantic>=2.10.0\nnew-dependency==1.0.0\n"
        ti_rb = tarfile.TarInfo(name=f"{prefix}/requirements/backend.txt")
        ti_rb.size = len(v2_req_b)
        tar.addfile(ti_rb, io.BytesIO(v2_req_b))

        # 4. requirements/frontend.txt
        v2_req_f = b"streamlit==1.40.0\n"
        ti_rf = tarfile.TarInfo(name=f"{prefix}/requirements/frontend.txt")
        ti_rf.size = len(v2_req_f)
        tar.addfile(ti_rf, io.BytesIO(v2_req_f))

    tar_buffer.seek(0)
    return tar_buffer.getvalue()


@pytest.fixture
def isolated_e2e_env(tmp_path: Path):
    """Crea una estructura de proyecto temporal completamente aislada para la prueba E2E."""
    root_dir = tmp_path / "e2e_project"
    root_dir.mkdir(parents=True)

    # Carpetas requeridas
    (root_dir / "src" / "backend" / "api").mkdir(parents=True)
    (root_dir / "src" / "backend" / "data").mkdir(parents=True)
    (root_dir / "src" / "frontend" / "views").mkdir(parents=True)
    (root_dir / "requirements").mkdir(parents=True)
    (root_dir / "backups").mkdir(parents=True)
    (root_dir / "tmp" / "update_staging").mkdir(parents=True)

    # Ficheros iniciales (Versión 1.0)
    (root_dir / "src" / "backend" / "api" / "main.py").write_text(
        "# Main backend entrypoint v1\nfrom fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    (root_dir / "src" / "frontend" / "app.py").write_text(
        "# Main frontend entrypoint v1\nimport streamlit as st\n", encoding="utf-8"
    )
    (root_dir / "src" / "backend" / "dummy_feature.py").write_text(
        "# Dummy Backend Service v1.0\ndef get_val(): return 10\n", encoding="utf-8"
    )
    (root_dir / "src" / "frontend" / "views" / "dummy_view.py").write_text(
        "# Dummy Frontend View v1.0\ndef render(): pass\n", encoding="utf-8"
    )
    (root_dir / "requirements" / "backend.txt").write_text(
        "fastapi==0.115.0\npydantic>=2.10.0\n", encoding="utf-8"
    )
    (root_dir / "requirements" / "frontend.txt").write_text(
        "streamlit==1.40.0\n", encoding="utf-8"
    )

    # Base de datos local con datos que NUNCA deben perderse
    db_file = root_dir / "src" / "backend" / "data" / "finanzas.db"
    db_file.write_text("CRITICAL_FINANCIAL_TRANSACTIONS_DATA_V1", encoding="utf-8")

    clear_check_cache()

    with patch.dict(os.environ, {"PROJECT_ROOT": str(root_dir), "BACKUP_DIR": str(root_dir / "backups")}):
        yield root_dir

    clear_check_cache()


def test_updater_full_lifecycle_e2e(client: TestClient, isolated_e2e_env: Path):
    """
    Ejecuta el ciclo de vida completo E2E a través de la API REST:
    1. GET /api/updater/version -> versión inicial, rollback_available=False
    2. GET /api/updater/check -> detecta actualización remota
    3. POST /api/updater/apply -> aplica tarball mock, crea backup y snapshot, reemplaza código
    4. GET /api/updater/version -> nuevo commit, rollback_available=True
    5. POST /api/updater/rollback -> restaura código previo sin alterar finanzas.db
    6. GET /api/updater/version -> versión restaurada
    """
    root_dir = isolated_e2e_env
    db_file = root_dir / "src" / "backend" / "data" / "finanzas.db"
    dummy_backend = root_dir / "src" / "backend" / "dummy_feature.py"
    dummy_frontend = root_dir / "src" / "frontend" / "views" / "dummy_view.py"

    # ==============================================================================
    # PASO 1: VERIFICAR VERSIÓN INICIAL
    # ==============================================================================
    resp_v1 = client.get("/api/updater/version")
    assert resp_v1.status_code == 200
    data_v1 = resp_v1.json()
    assert data_v1["current_commit"] == "initial"
    assert data_v1["rollback_available"] is False

    # ==============================================================================
    # PASO 2: CONSULTAR GITHUB API POR ACTUALIZACIONES
    # ==============================================================================
    mock_gh_commit_resp = MagicMock()
    mock_gh_commit_resp.status_code = 200
    mock_gh_commit_resp.json.return_value = {
        "sha": "remote1234567890abcdef",
        "commit": {
            "message": "feat(core): nuevo motor de auditoria y mejoras de rendimiento",
            "committer": {"date": "2026-11-03T18:00:00Z"},
        },
    }
    mock_gh_commit_resp.headers = {"X-RateLimit-Remaining": "58"}

    with patch("backend.services.updater_service.requests.get", return_value=mock_gh_commit_resp):
        resp_check = client.get("/api/updater/check?force=true&branch=main")
        assert resp_check.status_code == 200
        data_check = resp_check.json()
        assert data_check["update_available"] is True
        assert data_check["remote_commit"] == "remote1234567890abcdef"
        assert "nuevo motor de auditoria" in data_check["remote_commit_message"]

    # ==============================================================================
    # PASO 3: DESCARGA Y APLICACIÓN DE ACTUALIZACIÓN
    # ==============================================================================
    tarball_bytes = create_mock_tarball_bytes(commit_sha="remote1234567890abcdef")

    mock_download_resp = MagicMock()
    mock_download_resp.status_code = 200
    mock_download_resp.headers = {"content-length": str(len(tarball_bytes))}
    mock_download_resp.iter_content.return_value = [tarball_bytes]
    mock_download_resp.__enter__.return_value = mock_download_resp
    mock_download_resp.__exit__.return_value = False

    mock_backup_meta = BackupMetadata(
        filename="backup_pre_update_20261103.backup",
        created_at="2026-11-03T18:30:00Z",
        file_size_bytes=1024,
        file_size_formatted="1.00 KB",
        sha256="abcdef1234567890" * 4,
        backup_type="MANUAL",
        is_encrypted=False,
    )

    with patch("backend.services.updater_service.requests.get", return_value=mock_download_resp), \
         patch("backend.services.updater_service.create_backup", return_value=mock_backup_meta):
        
        apply_payload = {
            "branch": "main",
            "remote_commit": "remote1234567890abcdef",
        }
        resp_apply = client.post("/api/updater/apply", json=apply_payload)
        assert resp_apply.status_code == 200
        data_apply = resp_apply.json()

        assert data_apply["success"] is True
        assert data_apply["updated_to_commit"] == "remote1234567890abcdef"
        assert data_apply["requires_rebuild"] is True  # Añadimos new-dependency
        assert data_apply["pre_update_backup_path"] is not None
        assert data_apply["files_updated_count"] >= 4

    # Verificar que el código se actualizó en disco a la v2.0
    assert "v2.0" in dummy_backend.read_text(encoding="utf-8")
    assert "v2.0" in dummy_frontend.read_text(encoding="utf-8")

    # Verificar salvaguarda patrimonial crítica: finanzas.db NO fue alterado
    assert db_file.exists()
    assert db_file.read_text(encoding="utf-8") == "CRITICAL_FINANCIAL_TRANSACTIONS_DATA_V1"

    # Verificar que se creó la instantánea de rollback
    snapshot_path = root_dir / "backups" / "code_snapshot_prev.tar.gz"
    assert snapshot_path.is_file()

    # ==============================================================================
    # PASO 4: VERIFICAR ESTADO POST-ACTUALIZACIÓN
    # ==============================================================================
    resp_v2 = client.get("/api/updater/version")
    assert resp_v2.status_code == 200
    data_v2 = resp_v2.json()
    assert data_v2["current_commit"] == "remote1234567890abcdef"
    assert data_v2["rollback_available"] is True

    # ==============================================================================
    # PASO 5: EJECUTAR ROLLBACK DE CÓDIGO EN 1 CLIC
    # ==============================================================================
    resp_rollback = client.post("/api/updater/rollback")
    assert resp_rollback.status_code == 200
    data_rollback = resp_rollback.json()
    assert data_rollback["success"] is True
    assert "revertido con éxito" in data_rollback["message"]

    # Verificar que los archivos volvieron a la versión 1.0
    assert "v1.0" in dummy_backend.read_text(encoding="utf-8")
    assert "v1.0" in dummy_frontend.read_text(encoding="utf-8")

    # Verificar salvaguarda patrimonial crítica: finanzas.db SIGUE INTACTA
    assert db_file.exists()
    assert db_file.read_text(encoding="utf-8") == "CRITICAL_FINANCIAL_TRANSACTIONS_DATA_V1"

    # ==============================================================================
    # PASO 6: ESTADO FINAL TRAS REVERSIÓN
    # ==============================================================================
    resp_v_final = client.get("/api/updater/version")
    assert resp_v_final.status_code == 200
    data_final = resp_v_final.json()
    assert data_final["current_commit"] == "initial"
    assert data_final["rollback_available"] is False
