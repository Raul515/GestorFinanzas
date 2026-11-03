import datetime
from datetime import timezone
import sqlite3
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.domain.models.base import Base
from backend.domain.models.backup import BackupScheduleConfig
from backend.domain.models.transactions import Transaction
from backend.domain.schemas.backup import BackupScheduleUpdate
from backend.services.backup_service import (
    calculate_sha256,
    check_and_run_scheduled_backup,
    create_backup,
    delete_local_backup,
    format_bytes,
    get_database_health,
    get_or_create_schedule_config,
    list_backups,
    restore_backup,
    rollback_last_restore,
    rotate_backups,
    update_schedule_config,
    validate_backup_file,
)


@pytest.fixture
def temp_env(tmp_path: Path):
    """Crea un entorno aislado temporal con base de datos SQLite y carpeta de backups."""
    db_path = tmp_path / "finanzas.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Inicializar una base de datos SQLite válida con tablas maestras
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            group_type TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            amount REAL NOT NULL,
            description TEXT,
            category_id INTEGER
        )
        """
    )
    cursor.execute("INSERT INTO categories (id, name, group_type) VALUES (1, 'Alimentación', 'NEED')")
    cursor.execute("INSERT INTO transactions (id, amount, description, category_id) VALUES (1, 45.50, 'Mercadona', 1)")
    conn.commit()
    conn.close()

    # Base de datos en memoria para el session de SQLAlchemy (config)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield {
        "db_path": db_path,
        "backup_dir": backup_dir,
        "session": session,
    }

    session.close()


def test_format_bytes():
    assert format_bytes(500) == "500 B"
    assert format_bytes(2048) == "2.00 KB"
    assert format_bytes(1024 * 1024 * 2) == "2.00 MB"
    assert format_bytes(1024 * 1024 * 1024 * 3) == "3.00 GB"


def test_calculate_sha256(temp_env):
    db_path = temp_env["db_path"]
    sha = calculate_sha256(db_path)
    assert isinstance(sha, str)
    assert len(sha) == 64


def test_get_database_health_missing_db(tmp_path: Path):
    missing_path = tmp_path / "non_existent.db"
    health = get_database_health(db_path=missing_path, backup_dir=tmp_path)
    assert health.status == "DEGRADED"
    assert health.integrity_check_passed is False
    assert health.backup_warning_needed is True


def test_get_database_health_healthy(temp_env):
    db_path = temp_env["db_path"]
    b_dir = temp_env["backup_dir"]

    # Al inicio no hay copias, debe marcar warning
    health = get_database_health(db_path=db_path, backup_dir=b_dir)
    assert health.status == "HEALTHY"
    assert health.integrity_check_passed is True
    assert health.table_counts.get("transactions") == 1
    assert health.days_since_last_backup is None
    assert health.backup_warning_needed is True

    # Creamos un backup hoy
    create_backup(backup_type="MANUAL", db_path=db_path, backup_dir=b_dir)
    health2 = get_database_health(db_path=db_path, backup_dir=b_dir)
    assert health2.days_since_last_backup == 0
    assert health2.backup_warning_needed is False


def test_create_backup_hot_atomic(temp_env):
    db_path = temp_env["db_path"]
    b_dir = temp_env["backup_dir"]

    meta = create_backup(backup_type="MANUAL", db_path=db_path, backup_dir=b_dir)
    assert meta.backup_type == "MANUAL"
    assert (b_dir / meta.filename).exists()
    assert meta.file_size_bytes > 0
    assert len(meta.sha256) == 64


def test_backup_rotation(temp_env):
    db_path = temp_env["db_path"]
    b_dir = temp_env["backup_dir"]

    # Crear 6 backups con keep_max_copies=3
    for i in range(6):
        create_backup(
            backup_type="MANUAL",
            custom_name=f"manual_test_{i}.db",
            db_path=db_path,
            backup_dir=b_dir,
            keep_max_copies=3,
        )

    listing = list_backups(backup_dir=b_dir)
    # Deben quedar exactamente 3 copias manuales
    assert listing.total_count == 3

    # Crear 4 snapshots archivados simulados para probar la rotación independiente de archivos (máx 2)
    for j in range(4):
        (b_dir / f"archived_prerestore_{j}.db").write_text("dummy")

    rotate_backups(b_dir=b_dir, keep_max_copies=3)
    remaining_archives = list(b_dir.glob("archived_prerestore_*.db"))
    assert len(remaining_archives) == 2
    # Las copias de usuario deben seguir siendo 3
    remaining_manuals = [f for f in b_dir.glob("*.db") if f.name.startswith("manual_test_")]
    assert len(remaining_manuals) == 3


def test_validate_backup_file(temp_env, tmp_path: Path):
    db_path = temp_env["db_path"]
    b_dir = temp_env["backup_dir"]

    # 1. Archivo válido
    meta = create_backup(backup_type="MANUAL", db_path=db_path, backup_dir=b_dir)
    valid_res = validate_backup_file(b_dir / meta.filename)
    assert valid_res.is_valid is True
    assert valid_res.integrity_status == "ok"
    assert valid_res.table_counts["transactions"] == 1

    # 2. Archivo corrupto (texto plano fingiendo ser SQLite)
    fake_file = tmp_path / "fake.db"
    fake_file.write_text("Esto no es una base de datos SQLite real")
    invalid_res = validate_backup_file(fake_file)
    assert invalid_res.is_valid is False

    # 3. Archivo inexistente
    missing_res = validate_backup_file(tmp_path / "ghost.db")
    assert missing_res.is_valid is False

    # 4. Archivo SQLite de otra aplicación con esquema incompleto (solo 1 tabla 'categories')
    foreign_db = tmp_path / "foreign_incomplete.db"
    f_conn = sqlite3.connect(foreign_db)
    f_conn.execute("CREATE TABLE categories (id INT, name TEXT)")
    f_conn.commit()
    f_conn.close()
    foreign_res = validate_backup_file(foreign_db)
    assert foreign_res.is_valid is False
    assert foreign_res.integrity_status == "missing_schema"
    assert "tablas financieras obligatorias" in foreign_res.error_message


def test_restore_backup_with_safety_snapshot_and_wal_purge(temp_env):
    db_path = temp_env["db_path"]
    b_dir = temp_env["backup_dir"]

    # Creamos copia inicial que tiene 1 transacción
    initial_backup = create_backup(backup_type="MANUAL", db_path=db_path, backup_dir=b_dir)

    # Modificamos la base activa: insertamos una segunda transacción
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO transactions (id, amount, description, category_id) VALUES (2, 100.0, 'Gasolina', 1)")
    conn.commit()
    conn.close()

    # Creamos archivos WAL residuales simulados
    wal_file = db_path.with_name(f"{db_path.name}-wal")
    shm_file = db_path.with_name(f"{db_path.name}-shm")
    wal_file.write_text("wal dummy data")
    shm_file.write_text("shm dummy data")
    assert wal_file.exists()
    assert shm_file.exists()

    # Restauramos la copia inicial (que solo tenía 1 transacción)
    restore_res = restore_backup(
        backup_file_path=b_dir / initial_backup.filename,
        db_path=db_path,
        backup_dir=b_dir,
    )

    assert restore_res.success is True
    assert restore_res.can_rollback is True
    assert restore_res.safety_snapshot_filename is not None
    assert (b_dir / restore_res.safety_snapshot_filename).exists()

    # Verificar que los archivos WAL fueron purgados
    assert not wal_file.exists()
    assert not shm_file.exists()

    # Verificar que la base activa volvió a tener exactamente 1 transacción
    conn2 = sqlite3.connect(str(db_path))
    count = conn2.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn2.close()
    assert count == 1


def test_rollback_last_restore(temp_env):
    db_path = temp_env["db_path"]
    b_dir = temp_env["backup_dir"]

    # Estado A: 1 transacción
    meta_a = create_backup(backup_type="MANUAL", db_path=db_path, backup_dir=b_dir)

    # Modificamos a Estado B: 2 transacciones
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO transactions (id, amount, description, category_id) VALUES (2, 99.0, 'Libro', 1)")
    conn.commit()
    conn.close()

    # Restauramos Estado A (se genera automáticamente safety_prerestore con Estado B)
    restore_backup(backup_file_path=b_dir / meta_a.filename, db_path=db_path, backup_dir=b_dir)

    # Comprobamos que actualmente hay 1 transacción
    conn2 = sqlite3.connect(str(db_path))
    assert conn2.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
    conn2.close()

    # Ejecutamos rollback
    rollback_res = rollback_last_restore(db_path=db_path, backup_dir=b_dir)
    assert rollback_res.success is True

    # Comprobamos que recuperó el Estado B (2 transacciones)
    conn3 = sqlite3.connect(str(db_path))
    assert conn3.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2
    conn3.close()

    # Comprobamos que la instantánea fue archivada y no queda pendiente en el banner
    list_res = list_backups(backup_dir=b_dir)
    assert list_res.latest_safety_snapshot is None


def test_delete_local_backup_and_path_traversal(temp_env):
    db_path = temp_env["db_path"]
    b_dir = temp_env["backup_dir"]

    meta = create_backup(backup_type="MANUAL", db_path=db_path, backup_dir=b_dir)
    assert (b_dir / meta.filename).exists()

    # Borrado normal
    assert delete_local_backup(meta.filename, backup_dir=b_dir) is True
    assert not (b_dir / meta.filename).exists()

    # Intento de Path Traversal
    with pytest.raises(PermissionError):
        delete_local_backup("../finanzas.db", backup_dir=b_dir)


def test_schedule_config_crud_and_check(temp_env):
    session = temp_env["session"]
    db_path = temp_env["db_path"]
    b_dir = temp_env["backup_dir"]

    # 1. Obtener o crear configuración por defecto
    cfg = get_or_create_schedule_config(session)
    assert cfg.enabled is True
    assert cfg.frequency_days == 14
    assert cfg.keep_max_copies == 5

    # 2. Actualizar configuración
    update = BackupScheduleUpdate(enabled=True, frequency_days=7, keep_max_copies=10)
    resp = update_schedule_config(session, update)
    assert resp.frequency_days == 7
    assert resp.keep_max_copies == 10

    # 3. Primera ejecución programada (debe crear backup)
    meta1 = check_and_run_scheduled_backup(session, db_path=db_path, backup_dir=b_dir)
    assert meta1 is not None
    assert meta1.backup_type == "AUTOMATIC"

    # 4. Segunda ejecución inmediata con la base intacta (debe omitir por SHA-256 idéntico)
    meta2 = check_and_run_scheduled_backup(session, db_path=db_path, backup_dir=b_dir)
    assert meta2 is None

    # 5. Modificamos la base y forzamos fecha vencida
    cfg_refreshed = get_or_create_schedule_config(session)
    cfg_refreshed.last_automated_backup_at = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=10)
    session.commit()

    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO transactions (id, amount, description, category_id) VALUES (5, 12.0, 'Café', 1)")
    conn.commit()
    conn.close()

    # Ahora debe generar un nuevo backup automático
    meta3 = check_and_run_scheduled_backup(session, db_path=db_path, backup_dir=b_dir)
    assert meta3 is not None
    assert meta3.backup_type == "AUTOMATIC"
