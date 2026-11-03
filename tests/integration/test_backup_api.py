"""
Pruebas de integración para los endpoints REST de Backup & Restore (/backup) (Spec 011 - Fase 2).
Valida contratos HTTP, códigos de estado (200, 201, 400, 403, 404, 422), headers binarios y rollback.
"""

import io
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from backend.domain.schemas.backup import BackupScheduleUpdate
from backend.services import backup_service


@pytest.fixture
def isolated_backup_env(tmp_path: Path, monkeypatch):
    """Configura un entorno temporal aislado para la base de datos y la carpeta de backups."""
    db_file = tmp_path / "finanzas.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Inicializar una base SQLite válida con tablas y datos
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT, group_type TEXT)")
    conn.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, amount REAL, description TEXT, category_id INTEGER)")
    conn.execute("INSERT INTO categories VALUES (1, 'Supermercado', 'NEED')")
    conn.execute("INSERT INTO transactions VALUES (1, 35.0, 'Compra semanal', 1)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(backup_service, "get_db_path", lambda: db_file)
    monkeypatch.setattr(backup_service, "get_backup_dir", lambda: backup_dir)

    return {
        "db_file": db_file,
        "backup_dir": backup_dir,
    }


def test_api_get_database_health(client: TestClient, isolated_backup_env):
    """GET /backup/health devuelve 200 con el esquema de salud y advertencia de respaldo."""
    response = client.get("/backup/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["integrity_check_passed"] is True
    assert "sha256" in data
    assert data["table_counts"]["transactions"] == 1
    assert data["backup_warning_needed"] is True


def test_api_create_backup_manual(client: TestClient, isolated_backup_env):
    """POST /backup/create genera una instantánea local manual y devuelve 201."""
    response = client.post("/backup/create")
    assert response.status_code == 201
    data = response.json()
    assert data["backup_type"] == "MANUAL"
    assert data["filename"].startswith("manual_backup_")
    assert (isolated_backup_env["backup_dir"] / data["filename"]).exists()

    # Creación con nombre personalizado
    resp_custom = client.post("/backup/create?custom_name=respaldo_especial.db")
    assert resp_custom.status_code == 201
    assert resp_custom.json()["filename"] == "respaldo_especial.db"


def test_api_download_backup(client: TestClient, isolated_backup_env):
    """GET /backup/download retorna un stream binario con media-type de SQLite."""
    response = client.get("/backup/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-sqlite3"
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert len(response.content) > 0


def test_api_list_backups(client: TestClient, isolated_backup_env):
    """GET /backup/list devuelve el catálogo de copias ordenado."""
    client.post("/backup/create")
    client.post("/backup/create")

    response = client.get("/backup/list")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2
    assert len(data["backups"]) == 2


def test_api_restore_upload_valid_and_invalid(client: TestClient, isolated_backup_env):
    """POST /backup/restore/upload valida extensiones, integridad y ejecuta la restauración."""
    # 1. Extensión inválida
    bad_ext_file = io.BytesIO(b"dummy")
    resp_bad_ext = client.post(
        "/backup/restore/upload",
        files={"file": ("invalido.txt", bad_ext_file, "text/plain")},
    )
    assert resp_bad_ext.status_code == 400
    assert "extensión .db" in resp_bad_ext.json()["detail"]

    # 2. Archivo corrupto
    corrupt_file = io.BytesIO(b"no es un sqlite real")
    resp_corrupt = client.post(
        "/backup/restore/upload",
        files={"file": ("corrupto.db", corrupt_file, "application/x-sqlite3")},
    )
    assert resp_corrupt.status_code == 400
    assert "inválido o corrupto" in resp_corrupt.json()["detail"]

    # 3. Archivo válido
    # Creamos un backup previo para simular subida
    create_resp = client.post("/backup/create?custom_name=para_subir.db")
    valid_bytes = (isolated_backup_env["backup_dir"] / "para_subir.db").read_bytes()

    resp_valid = client.post(
        "/backup/restore/upload",
        files={"file": ("restaurado.db", io.BytesIO(valid_bytes), "application/x-sqlite3")},
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["success"] is True
    assert resp_valid.json()["can_rollback"] is True


def test_api_validate_backup_upload(client: TestClient, isolated_backup_env):
    """POST /backup/validate: Comprueba integridad sin aplicar cambios."""
    # 1. Extensión incorrecta
    resp_ext = client.post(
        "/backup/validate",
        files={"file": ("invalido.txt", io.BytesIO(b"texto plano"), "text/plain")},
    )
    assert resp_ext.status_code == 400

    # 2. Archivo corrupto
    resp_corrupt = client.post(
        "/backup/validate",
        files={"file": ("corrupto.db", io.BytesIO(b"no sqlite header"), "application/x-sqlite3")},
    )
    assert resp_corrupt.status_code == 200
    assert resp_corrupt.json()["is_valid"] is False
    assert "Error" in resp_corrupt.json()["error_message"] or "database" in resp_corrupt.json()["error_message"]

    # 3. Archivo válido
    client.post("/backup/create?custom_name=valido_inspeccion.db")
    valid_bytes = (isolated_backup_env["backup_dir"] / "valido_inspeccion.db").read_bytes()
    resp_valid = client.post(
        "/backup/validate",
        files={"file": ("valido.db", io.BytesIO(valid_bytes), "application/x-sqlite3")},
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["is_valid"] is True
    assert resp_valid.json()["integrity_status"] == "ok"
    assert "transactions" in resp_valid.json()["table_counts"]


def test_api_restore_local_and_rollback(client: TestClient, isolated_backup_env):
    """POST /backup/restore/local y POST /backup/restore/rollback."""
    b_dir = isolated_backup_env["backup_dir"]
    db_file = isolated_backup_env["db_file"]

    # 1. Local inexistente -> 404
    resp_404 = client.post("/backup/restore/local/inexistente.db")
    assert resp_404.status_code == 404

    # 2. Creamos copia del Estado 1 (1 transacción)
    client.post("/backup/create?custom_name=estado_1.db")

    # Modificamos la base: insertamos 2 transacciones más
    conn = sqlite3.connect(str(db_file))
    conn.execute("INSERT INTO transactions VALUES (2, 50.0, 'Cena', 1)")
    conn.execute("INSERT INTO transactions VALUES (3, 20.0, 'Taxi', 1)")
    conn.commit()
    conn.close()

    # 3. Restauramos estado_1.db (vuelve a 1 transacción y crea snapshot de seguridad con 3 transacciones)
    resp_restore = client.post("/backup/restore/local/estado_1.db")
    assert resp_restore.status_code == 200
    assert resp_restore.json()["success"] is True
    assert resp_restore.json()["can_rollback"] is True

    # Comprobamos que actualmente hay 1 fila
    health_resp = client.get("/backup/health")
    assert health_resp.json()["table_counts"]["transactions"] == 1

    # 4. Rollback en 1 clic
    resp_rollback = client.post("/backup/restore/rollback")
    assert resp_rollback.status_code == 200
    assert resp_rollback.json()["success"] is True

    # Comprobamos que recuperó las 3 transacciones
    health_after_rollback = client.get("/backup/health")
    assert health_after_rollback.json()["table_counts"]["transactions"] == 3

    # Comprobamos que latest_safety_snapshot ya no aparece pendiente en el catálogo
    list_after_rollback = client.get("/backup/list")
    assert list_after_rollback.json()["latest_safety_snapshot"] is None


def test_api_delete_local_backup(client: TestClient, isolated_backup_env):
    """DELETE /backup/local/{filename} elimina la copia o devuelve 404."""
    # 404 si no existe
    resp_404 = client.delete("/backup/local/fantasma.db")
    assert resp_404.status_code == 404

    # Crear y borrar
    client.post("/backup/create?custom_name=borrame.db")
    resp_del = client.delete("/backup/local/borrame.db")
    assert resp_del.status_code == 200
    assert resp_del.json()["deleted"] is True


def test_api_schedule_config(client: TestClient):
    """GET y PUT /backup/schedule gestionan la periodicidad de copias."""
    # 1. GET inicial
    get_resp = client.get("/backup/schedule")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["enabled"] is True
    assert data["frequency_days"] == 14
    assert data["keep_max_copies"] == 5

    # 2. PUT válido
    put_resp = client.put(
        "/backup/schedule",
        json={"enabled": True, "frequency_days": 7, "keep_max_copies": 10},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["frequency_days"] == 7
    assert put_resp.json()["keep_max_copies"] == 10

    # 3. PUT inválido (frecuencia 0 días -> validación Pydantic ge=1)
    bad_resp = client.put(
        "/backup/schedule",
        json={"enabled": True, "frequency_days": 0, "keep_max_copies": 5},
    )
    assert bad_resp.status_code == 422
