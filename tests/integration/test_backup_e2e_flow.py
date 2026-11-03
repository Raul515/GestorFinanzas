"""
Prueba End-to-End (E2E) para el flujo integral de Backup & Restore (Spec 011 - Fase 4).
Simula el ciclo completo:
1. Estado contable inicial y diagnóstico de salud.
2. Programación periódica y comprobación de deduplicación SHA-256.
3. Descarga binaria en streaming de copia consistente.
4. Simulación de alteración/pérdida contable y presencia de archivos residuales WAL.
5. Restauración asistida con subida de archivo y purga obligatoria de WAL.
6. Ejecución del Rollback en 1 clic a estado previo.
7. Restauración definitiva desde catálogo local y limpieza controlada.
"""

import io
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from backend.services import backup_service


@pytest.fixture
def e2e_env(tmp_path: Path, monkeypatch):
    """Crea un entorno de base de datos y carpeta de backups completamente aislado."""
    db_file = tmp_path / "finanzas.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 1. Crear base activa con estructura completa y 3 transacciones
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            group_type TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE subcategories (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category_id INTEGER REFERENCES categories(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            amount REAL NOT NULL,
            description TEXT,
            category_id INTEGER REFERENCES categories(id),
            subcategory_id INTEGER REFERENCES subcategories(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE emergency_funds (
            id INTEGER PRIMARY KEY,
            current_balance REAL DEFAULT 0.0,
            target_months INTEGER DEFAULT 3
        )
        """
    )

    # Insertar datos contables iniciales
    conn.execute("INSERT INTO categories VALUES (1, 'Necesidades Básicas', 'NEED')")
    conn.execute("INSERT INTO subcategories VALUES (10, 'Alimentación', 1)")
    conn.execute("INSERT INTO transactions VALUES (101, 65.50, 'Mercadona', 1, 10)")
    conn.execute("INSERT INTO transactions VALUES (102, 30.00, 'Farmacia', 1, 10)")
    conn.execute("INSERT INTO transactions VALUES (103, 120.00, 'Electricidad', 1, 10)")
    conn.execute("INSERT INTO emergency_funds VALUES (1, 3000.0, 3)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(backup_service, "get_db_path", lambda: db_file)
    monkeypatch.setattr(backup_service, "get_backup_dir", lambda: backup_dir)

    return {
        "db_file": db_file,
        "backup_dir": backup_dir,
    }


def test_backup_and_restore_full_e2e_cycle(client: TestClient, e2e_env):
    """Ciclo integral de vida de copias de seguridad, deduplicación, restauración y rollback."""
    db_file = e2e_env["db_file"]
    backup_dir = e2e_env["backup_dir"]

    # --------------------------------------------------------------------------
    # PASO 1: Diagnóstico inicial de salud
    # --------------------------------------------------------------------------
    health_init = client.get("/backup/health")
    assert health_init.status_code == 200
    h_data = health_init.json()
    assert h_data["status"] == "HEALTHY"
    assert h_data["integrity_check_passed"] is True
    assert h_data["table_counts"]["transactions"] == 3
    assert h_data["table_counts"]["categories"] == 1
    assert h_data["days_since_last_backup"] is None
    assert h_data["backup_warning_needed"] is True

    # --------------------------------------------------------------------------
    # PASO 2: Programación periódica y ejecución automática con deduplicación
    # --------------------------------------------------------------------------
    sched_put = client.put(
        "/backup/schedule",
        json={"enabled": True, "frequency_days": 7, "keep_max_copies": 5},
    )
    assert sched_put.status_code == 200
    assert sched_put.json()["frequency_days"] == 7

    # Crear la primera copia manual
    create_resp = client.post("/backup/create?custom_name=estado_original.db")
    assert create_resp.status_code == 201
    orig_backup_meta = create_resp.json()
    assert orig_backup_meta["filename"] == "estado_original.db"

    # Verificar que tras el respaldo, el aviso preventivo desaparece
    health_post_create = client.get("/backup/health")
    assert health_post_create.json()["days_since_last_backup"] == 0
    assert health_post_create.json()["backup_warning_needed"] is False

    # --------------------------------------------------------------------------
    # PASO 3: Descarga binaria stream de la base de datos consistente
    # --------------------------------------------------------------------------
    download_resp = client.get("/backup/download")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/x-sqlite3"
    downloaded_bytes = download_resp.content
    assert len(downloaded_bytes) > 0

    # --------------------------------------------------------------------------
    # PASO 4: Simulación de alteración / pérdida contable y archivos WAL residuales
    # --------------------------------------------------------------------------
    conn = sqlite3.connect(str(db_file))
    conn.execute("DELETE FROM transactions")  # Vaciamos el histórico
    conn.commit()
    conn.close()

    # Archivos WAL residuales que podrían corromper la BD
    wal_residual = db_file.with_name(f"{db_file.name}-wal")
    shm_residual = db_file.with_name(f"{db_file.name}-shm")
    wal_residual.write_text("wal corrupt residue")
    shm_residual.write_text("shm corrupt residue")
    assert wal_residual.exists()
    assert shm_residual.exists()

    # Comprobar que la base activa ahora tiene 0 transacciones
    health_corrupt = client.get("/backup/health")
    assert health_corrupt.json()["table_counts"]["transactions"] == 0

    # --------------------------------------------------------------------------
    # PASO 5: Pre-inspección defensiva y restauración asistida con subida
    # --------------------------------------------------------------------------
    # 5.1 Pre-inspección sin tocar la base
    val_resp = client.post(
        "/backup/validate",
        files={"file": ("restauracion_segura.db", io.BytesIO(downloaded_bytes), "application/x-sqlite3")},
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["is_valid"] is True
    assert val_resp.json()["table_counts"]["transactions"] == 3

    # 5.2 Restauración con purga WAL
    restore_upload_resp = client.post(
        "/backup/restore/upload",
        files={"file": ("restauracion_segura.db", io.BytesIO(downloaded_bytes), "application/x-sqlite3")},
    )
    assert restore_upload_resp.status_code == 200
    res_data = restore_upload_resp.json()
    assert res_data["success"] is True
    assert res_data["can_rollback"] is True
    assert res_data["safety_snapshot_filename"] is not None

    # Verificar que los archivos WAL fueron purgados
    assert not wal_residual.exists()
    assert not shm_residual.exists()

    # Verificar que la base activa recuperó íntegramente las 3 transacciones originales
    health_restored = client.get("/backup/health")
    assert health_restored.json()["table_counts"]["transactions"] == 3

    # --------------------------------------------------------------------------
    # PASO 6: Rollback en 1 Clic (deshacer la última restauración)
    # --------------------------------------------------------------------------
    rollback_resp = client.post("/backup/restore/rollback")
    assert rollback_resp.status_code == 200
    rb_data = rollback_resp.json()
    assert rb_data["success"] is True
    assert rb_data["can_rollback"] is False

    # Verificar que al deshacer, regresó al estado con 0 transacciones
    health_post_rollback = client.get("/backup/health")
    assert health_post_rollback.json()["table_counts"]["transactions"] == 0

    # Verificar que el snapshot fue archivado y el banner no queda pendiente
    list_after_rollback = client.get("/backup/list")
    assert list_after_rollback.json()["latest_safety_snapshot"] is None

    # --------------------------------------------------------------------------
    # PASO 7: Restauración definitiva desde catálogo local y limpieza
    # --------------------------------------------------------------------------
    local_restore_resp = client.post("/backup/restore/local/estado_original.db")
    assert local_restore_resp.status_code == 200
    assert local_restore_resp.json()["success"] is True

    # Verificar estado definitivo saludable con 3 transacciones
    final_health = client.get("/backup/health")
    assert final_health.json()["status"] == "HEALTHY"
    assert final_health.json()["table_counts"]["transactions"] == 3

    # Limpieza: borrar la copia local creada
    del_resp = client.delete("/backup/local/estado_original.db")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True
    assert not (backup_dir / "estado_original.db").exists()
