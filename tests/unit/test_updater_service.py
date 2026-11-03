"""
Pruebas unitarias para el servicio de actualizaciones Over-The-Air (updater_service.py).
Cubre detección de versión, consultas con caché y mock a GitHub API (200, 403, 404, red),
protección anti-Tar-Slip, normalización de subcarpeta de GitHub, pre-validación sintáctica,
blindaje de archivos protegidos, pruning de obsoletos, dependencias, rollback y ciclo completo.
"""

import io
import json
import os
import tarfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.domain.schemas.backup import BackupMetadata
from backend.domain.schemas.updater import UpdateApplyResponse
from backend.services.updater_service import (
    _is_safe_tar_member,
    apply_update,
    calculate_file_sha256,
    check_dependency_changes,
    check_remote_updates,
    clear_check_cache,
    create_code_snapshot,
    extract_tarball_with_staging_normalization,
    get_current_version,
    get_data_dir,
    get_project_root,
    get_staging_dir,
    get_version_file,
    is_git_repository,
    is_path_protected,
    purge_bytecode,
    rollback_code,
    run_defensive_database_migrations,
    save_current_version,
    transfer_staging_to_production,
    validate_staging_syntax,
)


@pytest.fixture
def mock_project_env(tmp_path: Path):
    """Crea una estructura de proyecto temporal aislada para pruebas."""
    root_dir = tmp_path / "app_root"
    root_dir.mkdir(parents=True)

    # Crear carpetas requeridas
    (root_dir / "src" / "backend" / "api").mkdir(parents=True)
    (root_dir / "src" / "backend" / "data").mkdir(parents=True)
    (root_dir / "src" / "frontend").mkdir(parents=True)
    (root_dir / "requirements").mkdir(parents=True)
    (root_dir / "backups").mkdir(parents=True)
    (root_dir / "tmp" / "update_staging").mkdir(parents=True)

    # Archivos iniciales
    (root_dir / "src" / "backend" / "api" / "main.py").write_text("# main backend", encoding="utf-8")
    (root_dir / "src" / "frontend" / "app.py").write_text("# app frontend", encoding="utf-8")
    (root_dir / "requirements" / "backend.txt").write_text("fastapi==0.115.0\n", encoding="utf-8")
    (root_dir / "requirements" / "frontend.txt").write_text("streamlit==1.40.0\n", encoding="utf-8")
    (root_dir / "src" / "backend" / "data" / "finanzas.db").write_text("sqlite-mock-data", encoding="utf-8")
    (root_dir / ".env").write_text("SECRET_KEY=12345\n", encoding="utf-8")

    clear_check_cache()

    with patch.dict(os.environ, {"PROJECT_ROOT": str(root_dir), "BACKUP_DIR": str(root_dir / "backups")}):
        yield root_dir

    clear_check_cache()


def test_get_project_root_and_data_dir(mock_project_env: Path):
    """Verifica la resolución dinámica de PROJECT_ROOT y directorios clave."""
    assert get_project_root() == mock_project_env
    assert get_data_dir() == mock_project_env / "src" / "backend" / "data"
    assert get_staging_dir() == mock_project_env / "tmp" / "update_staging"
    assert get_version_file() == mock_project_env / "src" / "backend" / "data" / "version.json"


def test_is_git_repository(mock_project_env: Path):
    """Verifica la detección de presencia de carpeta .git."""
    assert not is_git_repository(mock_project_env)
    (mock_project_env / ".git").mkdir()
    assert is_git_repository(mock_project_env)


def test_calculate_file_sha256(mock_project_env: Path):
    """Verifica el cálculo de hash criptográfico de ficheros."""
    env_file = mock_project_env / ".env"
    sha = calculate_file_sha256(env_file)
    assert sha is not None
    assert len(sha) == 64

    missing_sha = calculate_file_sha256(mock_project_env / "archivo_inexistente.txt")
    assert missing_sha is None


def test_get_current_version_initial_and_save(mock_project_env: Path):
    """Verifica que el estado inicial devuelva 'initial' y que el guardado sea atómico."""
    v_info = get_current_version(mock_project_env)
    assert v_info.current_commit == "initial"
    assert v_info.branch == "main"
    assert v_info.last_updated_at is None
    assert not v_info.rollback_available

    save_current_version("abc1234567", "develop", "feat: nueva funcionalidad", mock_project_env)

    v_updated = get_current_version(mock_project_env)
    assert v_updated.current_commit == "abc1234567"
    assert v_updated.branch == "develop"
    assert v_updated.commit_message == "feat: nueva funcionalidad"
    assert v_updated.last_updated_at is not None


def test_is_path_protected():
    """Verifica que la lista negra y los prefijos protegidos se respeten estrictamente."""
    assert is_path_protected("src/backend/data/finanzas.db")
    assert is_path_protected("src/backend/data/finanzas.db-wal")
    assert is_path_protected("src/backend/data/device_id.txt")
    assert is_path_protected("src/backend/data/version.json")
    assert is_path_protected(".env")
    assert is_path_protected(".env.local")
    assert is_path_protected("backups/manual_backup_1.db")
    assert is_path_protected("sync/inbox/delta.json")
    assert is_path_protected(".git/config")
    assert is_path_protected("venv/bin/python")

    # Archivos normales de código no deben estar protegidos
    assert not is_path_protected("src/backend/api/main.py")
    assert not is_path_protected("src/frontend/views/updater_view.py")
    assert not is_path_protected("requirements/backend.txt")


def test_check_remote_updates_success_and_cache(mock_project_env: Path):
    """Verifica consulta exitosa a GitHub, detección de cambios y uso de caché en memoria."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"X-RateLimit-Remaining": "58"}
    mock_response.json.return_value = {
        "sha": "9876543210abcdef",
        "commit": {
            "message": "feat(core): optimización de rendimiento\nDetalles adicionales",
            "committer": {"date": "2026-11-03T10:00:00Z"},
        },
    }

    with patch("requests.get", return_value=mock_response) as mock_get:
        # 1. Consulta inicial (sin caché)
        res1 = check_remote_updates(project_root=mock_project_env, branch="main")
        assert res1.update_available is True
        assert res1.remote_commit == "9876543210abcdef"
        assert res1.remote_commit_message == "feat(core): optimización de rendimiento"
        assert res1.rate_limit_remaining == 58
        assert res1.cached is False
        assert mock_get.call_count == 1

        # Verificar cabeceras enviadas
        call_headers = mock_get.call_args[1]["headers"]
        assert call_headers["User-Agent"] == "GestorFinanzas-OTA-Updater/1.0"

        # 2. Segunda consulta inmediata: debe servirse de la caché
        res2 = check_remote_updates(project_root=mock_project_env, branch="main")
        assert res2.cached is True
        assert res2.remote_commit == "9876543210abcdef"
        assert mock_get.call_count == 1  # No se volvió a llamar a requests.get


def test_check_remote_updates_rate_limit_403(mock_project_env: Path):
    """Verifica manejo amigable y descriptivo de error 403 Rate Limit de GitHub."""
    future_reset = int(time.time()) + 1200  # 20 minutos en el futuro
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.headers = {
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(future_reset),
    }

    with patch("requests.get", return_value=mock_response):
        res = check_remote_updates(project_root=mock_project_env, branch="main")
        assert res.update_available is False
        assert res.rate_limit_remaining == 0
        assert res.error is not None
        err_msg = res.error
        assert "Límite de peticiones a GitHub alcanzado" in err_msg
        assert "minutos" in err_msg


def test_check_remote_updates_404_and_network_error(mock_project_env: Path):
    """Verifica respuestas ante rama/repo no encontrado (404) y excepciones de red."""
    mock_404 = MagicMock()
    mock_404.status_code = 404
    with patch("requests.get", return_value=mock_404):
        res_404 = check_remote_updates(project_root=mock_project_env, branch="rama-inexistente")
        assert res_404.update_available is False
        assert res_404.error is not None
        err_404 = res_404.error
        assert "no encontrada en GitHub" in err_404

    with patch("requests.get", side_effect=requests.RequestException("DNS lookup failed")):
        res_err = check_remote_updates(project_root=mock_project_env, branch="main")
        assert res_err.update_available is False
        assert res_err.error is not None
        err_conn = res_err.error
        assert "Error de conexión" in err_conn


def test_anti_tar_slip_detection(tmp_path: Path):
    """Verifica que la función _is_safe_tar_member rechace rutas maliciosas (Tar-Slip)."""
    target = tmp_path / "target"
    target.mkdir()

    # Caso 1: Ruta normal segura
    safe_info = tarfile.TarInfo(name="src/app.py")
    assert _is_safe_tar_member(safe_info, target)

    # Caso 2: Ruta absoluta
    abs_info = tarfile.TarInfo(name="/etc/passwd" if os.name != "nt" else "C:/Windows/System32/calc.exe")
    assert not _is_safe_tar_member(abs_info, target)

    # Caso 3: Secuencia con salto de directorio ../
    slip_info = tarfile.TarInfo(name="src/../../evil.py")
    assert not _is_safe_tar_member(slip_info, target)


def test_extract_tarball_with_staging_normalization(tmp_path: Path):
    """
    Verifica que el extractor normalice la subcarpeta raíz que GitHub inyecta
    automáticamente ({repo}-{branch}/) y deposite los ficheros en la raíz de staging.
    """
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    tar_path = staging_dir / "test_repo.tar.gz"

    # Crear tarball simulando el formato de GitHub: Carpeta raíz GestorFinanzas-main/
    with tarfile.open(tar_path, "w:gz") as tar:
        f1_data = b"# Backend code"
        ti1 = tarfile.TarInfo(name="GestorFinanzas-main/src/backend/api/main.py")
        ti1.size = len(f1_data)
        tar.addfile(ti1, io.BytesIO(f1_data))

        f2_data = b"# Frontend code"
        ti2 = tarfile.TarInfo(name="GestorFinanzas-main/src/frontend/app.py")
        ti2.size = len(f2_data)
        tar.addfile(ti2, io.BytesIO(f2_data))

    extract_tarball_with_staging_normalization(tar_path, staging_dir)

    # Los archivos deben estar accesibles directamente bajo staging_dir sin la subcarpeta GestorFinanzas-main
    assert (staging_dir / "src" / "backend" / "api" / "main.py").is_file()
    assert (staging_dir / "src" / "frontend" / "app.py").is_file()
    assert not (staging_dir / "GestorFinanzas-main").exists()
    assert not tar_path.exists()


def test_validate_staging_syntax(tmp_path: Path):
    """Verifica que validate_staging_syntax apruebe código válido y rechace sintaxis inválida."""
    staging_dir = tmp_path / "staging_syntax"
    staging_dir.mkdir()
    backend_dir = staging_dir / "src" / "backend" / "api"
    frontend_dir = staging_dir / "src" / "frontend"
    backend_dir.mkdir(parents=True)
    frontend_dir.mkdir(parents=True)

    # Código válido
    (backend_dir / "main.py").write_text("x = 1\n", encoding="utf-8")
    (frontend_dir / "app.py").write_text("y = 2\n", encoding="utf-8")
    assert validate_staging_syntax(staging_dir) is True

    # Introducir error de sintaxis en un módulo
    (backend_dir / "broken.py").write_text("def broken_syntax(:\n", encoding="utf-8")
    assert validate_staging_syntax(staging_dir) is False


def test_check_dependency_changes(mock_project_env: Path, tmp_path: Path):
    """Verifica la detección de cambios de dependencias en requirements/."""
    staging = tmp_path / "staging_deps"
    (staging / "requirements").mkdir(parents=True)

    # Idénticos -> False
    (staging / "requirements" / "backend.txt").write_text("fastapi==0.115.0\n", encoding="utf-8")
    (staging / "requirements" / "frontend.txt").write_text("streamlit==1.40.0\n", encoding="utf-8")
    assert check_dependency_changes(mock_project_env, staging) is False

    # Cambio en backend -> True
    (staging / "requirements" / "backend.txt").write_text("fastapi==0.116.0\n", encoding="utf-8")
    assert check_dependency_changes(mock_project_env, staging) is True


def test_transfer_staging_to_production_and_pruning(mock_project_env: Path, tmp_path: Path):
    """
    Verifica que la transferencia respete archivos protegidos (ej. finanzas.db, .env)
    y elimine archivos obsoletos según el installed_manifest.json.
    """
    staging = tmp_path / "staging_transfer"
    (staging / "src" / "backend" / "api").mkdir(parents=True)
    (staging / "src" / "backend" / "data").mkdir(parents=True)

    # Nuevos archivos
    (staging / "src" / "backend" / "api" / "new_service.py").write_text("# new service", encoding="utf-8")
    # Intento de sobrescribir finanzas.db en staging
    (staging / "src" / "backend" / "data" / "finanzas.db").write_text("MALICIOUS-OVERWRITE", encoding="utf-8")

    # Crear archivo obsoleto en producción que estaba en el manifiesto anterior
    obsolete_file = mock_project_env / "src" / "backend" / "api" / "deprecated.py"
    obsolete_file.write_text("# obsolete", encoding="utf-8")

    manifest_file = mock_project_env / "src" / "backend" / "data" / "installed_manifest.json"
    manifest_file.write_text(json.dumps(["src/backend/api/deprecated.py"]), encoding="utf-8")

    # Ejecutar transferencia
    updated_cnt, pruned_cnt = transfer_staging_to_production(staging, mock_project_env)

    # Verificaciones
    assert updated_cnt >= 1
    assert pruned_cnt == 1
    assert not obsolete_file.exists()  # Fue podado

    # El nuevo servicio se copió
    assert (mock_project_env / "src" / "backend" / "api" / "new_service.py").is_file()

    # finanzas.db permaneció intacto (no fue sobrescrito)
    db_content = (mock_project_env / "src" / "backend" / "data" / "finanzas.db").read_text(encoding="utf-8")
    assert db_content == "sqlite-mock-data"


def test_purge_bytecode(tmp_path: Path):
    """Verifica que purge_bytecode elimine __pycache__ y .pyc de manera defensiva."""
    src = tmp_path / "src"
    pycache = src / "backend" / "__pycache__"
    pycache.mkdir(parents=True)
    pyc_file = pycache / "main.cpython-311.pyc"
    pyc_file.write_bytes(b"\x00\x00\x00\x00")

    loose_pyc = src / "backend" / "helper.pyc"
    loose_pyc.write_bytes(b"\x00\x00\x00\x00")

    purge_bytecode(src)

    assert not pyc_file.exists()
    assert not loose_pyc.exists()
    assert not pycache.exists()


def test_code_snapshot_and_rollback(mock_project_env: Path):
    """Verifica el ciclo de creación de instantánea y rollback de código."""
    backups_dir = mock_project_env / "backups"
    save_current_version("v1_commit_hash", "main", "Versión 1 inicial", mock_project_env)

    # Modificar un archivo para snapshot
    main_file = mock_project_env / "src" / "backend" / "api" / "main.py"
    main_file.write_text("# Version 1 original", encoding="utf-8")

    # Crear instantánea
    snapshot_path = create_code_snapshot(mock_project_env, backups_dir)
    assert snapshot_path.is_file()

    # Simular actualización a Versión 2
    main_file.write_text("# Version 2 modificada con errores", encoding="utf-8")
    save_current_version("v2_bad_commit", "main", "Versión 2 errónea", mock_project_env)
    assert get_current_version(mock_project_env).current_commit == "v2_bad_commit"

    # Ejecutar rollback
    rollback_res = rollback_code(mock_project_env)
    assert rollback_res.success is True
    assert rollback_res.restored_commit == "v1_commit_hash"

    # Comprobar que el archivo volvió a la versión 1
    restored_content = main_file.read_text(encoding="utf-8")
    assert restored_content == "# Version 1 original"


def test_run_defensive_database_migrations():
    """Verifica la ejecución del hook introspectivo de migración de esquema SQLite."""
    migrated = run_defensive_database_migrations()
    assert isinstance(migrated, list)


def test_apply_update_full_lifecycle(mock_project_env: Path, tmp_path: Path):
    """
    Verifica el flujo completo de apply_update:
    - Descompresión en staging
    - Validación sintáctica
    - Copia de seguridad preventiva
    - Reemplazo y actualización de versión
    - Limpieza de staging
    """
    # 1. Crear un tarball simulado listo para aplicar
    custom_tar = tmp_path / "update_pkg.tar.gz"
    with tarfile.open(custom_tar, "w:gz") as tar:
        backend_code = b"# Updated main backend v2\nval = 42\n"
        ti1 = tarfile.TarInfo(name="GestorFinanzas-main/src/backend/api/main.py")
        ti1.size = len(backend_code)
        tar.addfile(ti1, io.BytesIO(backend_code))

        frontend_code = b"# Updated frontend v2\nimport streamlit as st\n"
        ti2 = tarfile.TarInfo(name="GestorFinanzas-main/src/frontend/app.py")
        ti2.size = len(frontend_code)
        tar.addfile(ti2, io.BytesIO(frontend_code))

        new_reqs = b"fastapi==0.116.0\n"
        ti3 = tarfile.TarInfo(name="GestorFinanzas-main/requirements/backend.txt")
        ti3.size = len(new_reqs)
        tar.addfile(ti3, io.BytesIO(new_reqs))

    # Mock de create_backup para prueba unitaria
    mock_meta = BackupMetadata(
        filename="pre_update_safety_test.db",
        created_at="2026-11-03T10:00:00Z",
        file_size_bytes=1024,
        file_size_formatted="1.00 KB",
        sha256="mockhash",
        backup_type="MANUAL",
    )

    with patch("backend.services.updater_service.create_backup", return_value=mock_meta):
        res: UpdateApplyResponse = apply_update(
            project_root=mock_project_env,
            branch="main",
            remote_commit="new_commit_sha_12345",
            custom_tarball_path=custom_tar,
        )

        assert res.success is True
        assert res.updated_to_commit == "new_commit_sha_12345"
        assert res.new_dependencies_detected is True
        assert res.requires_rebuild is True
        assert res.files_updated_count >= 2
        assert "Actualización completada con éxito" in res.message

        # Comprobar que el archivo main.py se actualizó en producción
        updated_main = (mock_project_env / "src" / "backend" / "api" / "main.py").read_text(encoding="utf-8")
        assert "Updated main backend v2" in updated_main

        # Comprobar version.json
        cur_ver = get_current_version(mock_project_env)
        assert cur_ver.current_commit == "new_commit_sha_12345"

        # Staging debe haberse limpiado (eliminado o vacío)
        staging = mock_project_env / "tmp" / "update_staging"
        assert not staging.exists() or len(list(staging.iterdir())) == 0


def test_apply_update_aborts_on_syntax_error(mock_project_env: Path, tmp_path: Path):
    """Verifica que si el paquete tiene errores de sintaxis, la actualización aborte sin tocar producción."""
    broken_tar = tmp_path / "broken_update.tar.gz"
    with tarfile.open(broken_tar, "w:gz") as tar:
        broken_code = b"def broken(:\n"
        ti1 = tarfile.TarInfo(name="GestorFinanzas-main/src/backend/api/main.py")
        ti1.size = len(broken_code)
        tar.addfile(ti1, io.BytesIO(broken_code))

        frontend_code = b"# Valid frontend\n"
        ti2 = tarfile.TarInfo(name="GestorFinanzas-main/src/frontend/app.py")
        ti2.size = len(frontend_code)
        tar.addfile(ti2, io.BytesIO(frontend_code))

    original_main = (mock_project_env / "src" / "backend" / "api" / "main.py").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="La validación sintáctica o estructural.*ha fallado"):
        apply_update(
            project_root=mock_project_env,
            branch="main",
            remote_commit="should_fail_sha",
            custom_tarball_path=broken_tar,
        )

    # Producción debe permanecer intacta
    current_main = (mock_project_env / "src" / "backend" / "api" / "main.py").read_text(encoding="utf-8")
    assert current_main == original_main
