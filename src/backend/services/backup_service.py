import datetime
from datetime import timezone
import hashlib
import logging
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_db import DB_PATH, engine, init_db
from backend.domain.models.backup import BackupScheduleConfig
from backend.domain.schemas.backup import (
    BackupListResponse,
    BackupMetadata,
    BackupScheduleResponse,
    BackupScheduleUpdate,
    BackupValidationResult,
    DatabaseHealthResponse,
    RestoreResponse,
)

logger = logging.getLogger(__name__)

ESSENTIAL_TABLES = [
    "transactions",
    "categories",
    "subcategories",
    "monthly_budgets",
    "emergency_funds",
    "joint_accounts",
    "joint_transactions",
    "watchlist",
]


def get_backup_dir() -> Path:
    """Retorna la ruta del directorio de copias de seguridad garantizando su existencia."""
    custom_dir = os.environ.get("BACKUP_DIR")
    if custom_dir:
        backup_path = Path(custom_dir).resolve()
    else:
        # Por defecto backups/ en la raíz del proyecto
        project_root = Path(__file__).resolve().parents[3]
        backup_path = project_root / "backups"

    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path


def get_db_path() -> Path:
    """Retorna la ruta absoluta normalizada de la base de datos activa."""
    return Path(DB_PATH).resolve()


def calculate_sha256(file_path: Path) -> str:
    """Calcula el hash criptográfico SHA-256 de un fichero en bloques de 64 KB."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def format_bytes(size_bytes: int) -> str:
    """Convierte un tamaño en bytes a un formato legible para humanos."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def count_database_tables(conn: sqlite3.Connection) -> Dict[str, int]:
    """Obtiene el recuento de filas para las tablas maestras de la aplicación."""
    counts: Dict[str, int] = {}
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}

    for table in ESSENTIAL_TABLES:
        if table in existing_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cursor.fetchone()[0]
            except sqlite3.Error as exc:
                logger.warning("Error contando filas de la tabla %s: %s", table, exc)
                counts[table] = 0
        else:
            counts[table] = 0
    return counts


def get_database_health(
    db_path: Optional[Path] = None, backup_dir: Optional[Path] = None
) -> DatabaseHealthResponse:
    """Inspecciona la base de datos activa y devuelve su diagnóstico de salud, integridad y respaldos."""
    path = db_path or get_db_path()
    b_dir = backup_dir or get_backup_dir()

    if not path.exists():
        logger.warning("Base de datos no encontrada en la ruta: %s", path)
        return DatabaseHealthResponse(
            status="DEGRADED",
            database_path=str(path),
            file_size_bytes=0,
            file_size_formatted="0 B",
            sha256="",
            last_modified=None,
            integrity_check_passed=False,
            table_counts={},
            days_since_last_backup=None,
            last_backup_at=None,
            backup_warning_needed=True,
        )

    file_size = path.stat().st_size
    file_size_fmt = format_bytes(file_size)
    sha256_hash = calculate_sha256(path)
    last_modified_dt = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    last_modified = last_modified_dt.isoformat()

    integrity_passed = False
    table_counts: Dict[str, int] = {}

    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            row = cursor.fetchone()
            integrity_passed = (row is not None and row[0] == "ok")
            table_counts = count_database_tables(conn)
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Fallo al verificar integridad SQLite de %s: %s", path, exc)
        integrity_passed = False

    status = "HEALTHY" if integrity_passed else "CORRUPTED"

    # Cálculo de días sin respaldo
    days_since_last_backup: Optional[int] = None
    last_backup_at: Optional[str] = None
    backup_warning_needed: bool = False

    backup_files = [f for f in b_dir.glob("*.db") if f.is_file()]
    if not backup_files:
        days_since_last_backup = None
        last_backup_at = None
        backup_warning_needed = True
    else:
        most_recent = max(backup_files, key=lambda f: f.stat().st_mtime)
        most_recent_dt = datetime.datetime.fromtimestamp(
            most_recent.stat().st_mtime, tz=timezone.utc
        )
        now = datetime.datetime.now(timezone.utc)
        diff_days = max(0, (now - most_recent_dt).days)
        days_since_last_backup = diff_days
        last_backup_at = most_recent_dt.isoformat()
        backup_warning_needed = (diff_days >= 14)

    return DatabaseHealthResponse(
        status=status,
        database_path=str(path),
        file_size_bytes=file_size,
        file_size_formatted=file_size_fmt,
        sha256=sha256_hash,
        last_modified=last_modified,
        integrity_check_passed=integrity_passed,
        table_counts=table_counts,
        days_since_last_backup=days_since_last_backup,
        last_backup_at=last_backup_at,
        backup_warning_needed=backup_warning_needed,
    )


def create_backup(
    backup_type: str = "MANUAL",
    custom_name: Optional[str] = None,
    db_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    keep_max_copies: int = 5,
) -> BackupMetadata:
    """Genera una copia de seguridad atómica en caliente con sqlite3.backup y checkpoint WAL."""
    src_path = db_path or get_db_path()
    b_dir = backup_dir or get_backup_dir()

    if not src_path.exists():
        raise FileNotFoundError(f"No existe la base de datos fuente en {src_path}")

    now = datetime.datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")

    prefix_map = {
        "MANUAL": "manual_backup_",
        "AUTOMATIC": "auto_backup_",
        "SAFETY_PRERESTORE": "safety_prerestore_",
        "SAFETY_PREUPDATE": "safety_preupdate_",
    }
    prefix = prefix_map.get(backup_type, "manual_backup_")

    if custom_name:
        clean_name = Path(custom_name).name
        if not clean_name.endswith(".db"):
            clean_name = f"{clean_name}.db"
        filename = clean_name
    else:
        filename = f"{prefix}{ts}.db"
        if (b_dir / filename).exists():
            ts_micro = now.strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{prefix}{ts_micro}.db"

    target_path = b_dir / filename

    logger.info("Iniciando copia de seguridad (%s) hacia %s...", backup_type, target_path)

    # Copia consistente mediante la API oficial sqlite3.backup()
    src_conn = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True, timeout=30.0)
    target_conn = sqlite3.connect(str(target_path))
    try:
        src_conn.backup(target_conn)
    finally:
        target_conn.close()
        src_conn.close()

    # Rotación de copias si no es un snapshot pre-restauración
    if backup_type != "SAFETY_PRERESTORE":
        rotate_backups(b_dir=b_dir, keep_max_copies=keep_max_copies)

    file_size = target_path.stat().st_size
    file_size_fmt = format_bytes(file_size)
    sha256_hash = calculate_sha256(target_path)

    logger.info(
        "Copia de seguridad finalizada con éxito: %s (%s, SHA-256: %s)",
        filename,
        file_size_fmt,
        sha256_hash[:8],
    )

    return BackupMetadata(
        filename=filename,
        created_at=now.isoformat(),
        file_size_bytes=file_size,
        file_size_formatted=file_size_fmt,
        sha256=sha256_hash,
        backup_type=backup_type,  # type: ignore
    )


def rotate_backups(b_dir: Path, keep_max_copies: int) -> None:
    """Elimina las copias manuales y automáticas más antiguas que superen el límite configurado."""
    # 1. Rotación de copias estándar de usuario (excluyendo snapshots internos de seguridad y archivo)
    standard_backups = [
        f for f in b_dir.glob("*.db")
        if f.is_file() and not f.name.startswith("safety_prerestore_") and not f.name.startswith("archived_prerestore_")
    ]
    standard_backups.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    if len(standard_backups) > keep_max_copies:
        to_delete = standard_backups[keep_max_copies:]
        for old_file in to_delete:
            try:
                old_file.unlink()
                logger.info("Rotación: Eliminada copia de seguridad antigua %s", old_file.name)
            except OSError as exc:
                logger.warning("Error eliminando copia antigua %s: %s", old_file.name, exc)

    # 2. Rotación independiente para copias archivadas de rollback (máximo 2 copias)
    archived_backups = [
        f for f in b_dir.glob("archived_prerestore_*.db")
        if f.is_file()
    ]
    archived_backups.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    if len(archived_backups) > 2:
        for old_archive in archived_backups[2:]:
            try:
                old_archive.unlink()
                logger.info("Rotación: Eliminado snapshot archivado antiguo %s", old_archive.name)
            except OSError as exc:
                logger.warning("Error eliminando snapshot archivado %s: %s", old_archive.name, exc)


def validate_backup_file(file_path: Path) -> BackupValidationResult:
    """Valida exhaustivamente la integridad y esquema de un archivo de copia de seguridad."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return BackupValidationResult(
            is_valid=False,
            integrity_status="file_not_found_or_empty",
            table_counts={},
            sha256="",
            error_message="El archivo no existe o se encuentra vacío.",
        )

    sha256_hash = calculate_sha256(file_path)

    try:
        conn = sqlite3.connect(f"file:{file_path.as_posix()}?mode=ro", uri=True, timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            row = cursor.fetchone()
            if not row or row[0] != "ok":
                status = row[0] if row else "unknown_error"
                return BackupValidationResult(
                    is_valid=False,
                    integrity_status=status,
                    table_counts={},
                    sha256=sha256_hash,
                    error_message=f"La verificación de integridad SQLite falló: {status}",
                )

            # Comprobar que contiene todas las tablas maestras indispensables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cursor.fetchall()}
            required_tables = {"transactions", "categories"}
            missing_tables = required_tables - tables
            if missing_tables:
                return BackupValidationResult(
                    is_valid=False,
                    integrity_status="missing_schema",
                    table_counts={},
                    sha256=sha256_hash,
                    error_message=f"El archivo SQLite no contiene las tablas financieras obligatorias: {', '.join(sorted(missing_tables))}.",
                )

            counts = count_database_tables(conn)
            return BackupValidationResult(
                is_valid=True,
                integrity_status="ok",
                table_counts=counts,
                sha256=sha256_hash,
                error_message=None,
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Excepción validando archivo de copia %s: %s", file_path, exc)
        return BackupValidationResult(
            is_valid=False,
            integrity_status="exception",
            table_counts={},
            sha256=sha256_hash,
            error_message=f"Error al inspeccionar la base de datos: {str(exc)}",
        )


def list_backups(backup_dir: Optional[Path] = None) -> BackupListResponse:
    """Lista todos los archivos de respaldo disponibles en el directorio backups/."""
    b_dir = backup_dir or get_backup_dir()
    db_files = [f for f in b_dir.glob("*.db") if f.is_file()]
    db_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    backups: List[BackupMetadata] = []
    latest_safety_snapshot: Optional[str] = None

    for f in db_files:
        if f.name.startswith("safety_prerestore_"):
            b_type = "SAFETY_PRERESTORE"
            if latest_safety_snapshot is None:
                latest_safety_snapshot = f.name
        elif f.name.startswith("safety_preupdate_"):
            b_type = "SAFETY_PREUPDATE"
        elif f.name.startswith("auto_backup_"):
            b_type = "AUTOMATIC"
        else:
            b_type = "MANUAL"

        dt = datetime.datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        size = f.stat().st_size

        backups.append(
            BackupMetadata(
                filename=f.name,
                created_at=dt.isoformat(),
                file_size_bytes=size,
                file_size_formatted=format_bytes(size),
                sha256=calculate_sha256(f),
                backup_type=b_type,  # type: ignore
            )
        )

    return BackupListResponse(
        backups=backups,
        total_count=len(backups),
        latest_safety_snapshot=latest_safety_snapshot,
    )


def purge_wal_files(db_path: Path) -> None:
    """Elimina de forma segura los archivos temporales de Write-Ahead Logging (-wal y -shm)."""
    wal_file = db_path.with_name(f"{db_path.name}-wal")
    shm_file = db_path.with_name(f"{db_path.name}-shm")

    if wal_file.exists():
        try:
            wal_file.unlink()
            logger.info("Purga WAL: eliminado archivo residual %s", wal_file.name)
        except OSError as exc:
            logger.warning("No se pudo purgar %s: %s", wal_file.name, exc)

    if shm_file.exists():
        try:
            shm_file.unlink()
            logger.info("Purga WAL: eliminado archivo residual %s", shm_file.name)
        except OSError as exc:
            logger.warning("No se pudo purgar %s: %s", shm_file.name, exc)


def restore_backup(
    backup_file_path: Path,
    db_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
) -> RestoreResponse:
    """Restaura de forma segura un respaldo previo sobre la base de datos activa."""
    target_db = db_path or get_db_path()
    b_dir = backup_dir or get_backup_dir()

    # 1. Validación previa de integridad
    validation = validate_backup_file(backup_file_path)
    if not validation.is_valid:
        raise ValueError(
            f"El archivo de respaldo no es válido para restaurar: {validation.error_message}"
        )

    # 2. Creación obligatoria de instantánea de seguridad previa
    safety_snapshot_name: Optional[str] = None
    if target_db.exists():
        logger.info("Generando instantánea de seguridad pre-restauración...")
        safety_meta = create_backup(
            backup_type="SAFETY_PRERESTORE",
            db_path=target_db,
            backup_dir=b_dir,
        )
        safety_snapshot_name = safety_meta.filename

    # 3. Liberar conexiones SQLAlchemy activas
    logger.info("Liberando conexiones del motor SQLAlchemy (engine.dispose)...")
    engine.dispose()

    # 4. Purgar archivos -wal y -shm
    purge_wal_files(target_db)

    # 5. Sustitución atómica del fichero .db
    logger.info("Sobrescribiendo base de datos activa con %s...", backup_file_path.name)
    shutil.copy2(backup_file_path, target_db)

    # 6. Auto-migración retroactiva mediante init_db()
    try:
        init_db()
    except Exception as exc:
        logger.warning("Error durante init_db() post-restauración: %s", exc)

    # 7. Conteo de tablas tras restauración
    restored_counts: Dict[str, int] = {}
    try:
        conn = sqlite3.connect(f"file:{target_db.as_posix()}?mode=ro", uri=True)
        try:
            restored_counts = count_database_tables(conn)
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Error al contar tablas post-restauración: %s", exc)

    logger.info("Restauración completada con éxito desde %s", backup_file_path.name)

    return RestoreResponse(
        success=True,
        message=f"Base de datos restaurada con éxito desde '{backup_file_path.name}'.",
        safety_snapshot_filename=safety_snapshot_name,
        can_rollback=bool(safety_snapshot_name),
        restored_table_counts=restored_counts,
    )


def rollback_last_restore(
    db_path: Optional[Path] = None, backup_dir: Optional[Path] = None
) -> RestoreResponse:
    """Revierte la última restauración aplicando en 1 clic el snapshot previo de seguridad."""
    target_db = db_path or get_db_path()
    b_dir = backup_dir or get_backup_dir()

    safety_files = [f for f in b_dir.glob("safety_prerestore_*.db") if f.is_file()]
    if not safety_files:
        raise FileNotFoundError(
            "No se encontró ninguna instantánea previa de seguridad disponible para deshacer la restauración."
        )

    # El más reciente
    safety_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    latest_snapshot = safety_files[0]

    logger.info("Ejecutando Rollback a instantánea de seguridad: %s", latest_snapshot.name)

    validation = validate_backup_file(latest_snapshot)
    if not validation.is_valid:
        raise ValueError(
            f"La instantánea de seguridad está corrupta: {validation.error_message}"
        )

    engine.dispose()
    purge_wal_files(target_db)
    shutil.copy2(latest_snapshot, target_db)

    # Archivar el snapshot aplicado para que no quede pendiente en el banner de la UI
    now_ts = datetime.datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archived_name = latest_snapshot.name.replace("safety_prerestore_", f"archived_prerestore_{now_ts}_")
    try:
        latest_snapshot.rename(b_dir / archived_name)
        logger.info("Instantánea de seguridad archivada tras rollback como: %s", archived_name)
    except OSError as exc:
        logger.warning("No se pudo renombrar la instantánea de seguridad tras rollback: %s", exc)

    try:
        init_db()
    except Exception as exc:
        logger.warning("Error durante init_db() post-rollback: %s", exc)

    restored_counts: Dict[str, int] = {}
    try:
        conn = sqlite3.connect(f"file:{target_db.as_posix()}?mode=ro", uri=True)
        try:
            restored_counts = count_database_tables(conn)
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Error contando tablas post-rollback: %s", exc)

    return RestoreResponse(
        success=True,
        message=f"Restauración deshecha con éxito. Se ha recuperado el estado previo desde '{latest_snapshot.name}'.",
        safety_snapshot_filename=None,
        can_rollback=False,
        restored_table_counts=restored_counts,
    )


def delete_local_backup(filename: str, backup_dir: Optional[Path] = None) -> bool:
    """Elimina de forma segura una copia de seguridad local verificando Path Traversal."""
    b_dir = backup_dir or get_backup_dir()
    target_file = (b_dir / filename).resolve()

    # Protección contra Path Traversal
    if target_file.parent != b_dir.resolve():
        raise PermissionError("Acceso no autorizado fuera del directorio de backups.")

    if not target_file.exists():
        raise FileNotFoundError(f"La copia de seguridad '{filename}' no existe.")

    target_file.unlink()
    logger.info("Copia de seguridad eliminada: %s", filename)
    return True


def get_or_create_schedule_config(db_session: Session) -> BackupScheduleConfig:
    """Obtiene o inicializa la configuración singleton de programación de respaldos."""
    config = db_session.query(BackupScheduleConfig).filter_by(id=1).first()
    if not config:
        config = BackupScheduleConfig(
            id=1,
            enabled=True,
            frequency_days=14,
            keep_max_copies=5,
            last_automated_backup_at=None,
            last_backup_sha256=None,
        )
        db_session.add(config)
        db_session.commit()
        db_session.refresh(config)
    return config


def update_schedule_config(
    db_session: Session, update: BackupScheduleUpdate
) -> BackupScheduleResponse:
    """Actualiza la periodicidad y límites de retención de copias programadas."""
    config = get_or_create_schedule_config(db_session)
    config.enabled = update.enabled
    config.frequency_days = update.frequency_days
    config.keep_max_copies = update.keep_max_copies
    db_session.commit()
    db_session.refresh(config)

    next_estimated: Optional[str] = None
    last_auto_str: Optional[str] = None

    if config.last_automated_backup_at:
        last_dt = config.last_automated_backup_at.replace(tzinfo=timezone.utc)
        last_auto_str = last_dt.isoformat()
        if config.enabled:
            next_dt = last_dt + datetime.timedelta(days=config.frequency_days)
            next_estimated = next_dt.isoformat()
    elif config.enabled:
        next_estimated = datetime.datetime.now(timezone.utc).isoformat()

    return BackupScheduleResponse(
        enabled=config.enabled,
        frequency_days=config.frequency_days,
        keep_max_copies=config.keep_max_copies,
        last_automated_backup_at=last_auto_str,
        next_backup_estimated_at=next_estimated,
        last_backup_sha256=config.last_backup_sha256,
    )


def get_database_content_fingerprint(db_path: Path) -> str:
    """Calcula una huella criptográfica determinista del contenido de usuario, ignorando tablas de configuración."""
    if not db_path.exists():
        return ""
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'backup_%' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            tables = [r[0] for r in cursor.fetchall()]
            hasher = hashlib.sha256()
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                hasher.update(f"{table}:{count};".encode("utf-8"))
                if count > 0:
                    cursor.execute(f"SELECT * FROM {table} ORDER BY rowid")
                    for row in cursor.fetchall():
                        hasher.update(str(row).encode("utf-8"))
            return hasher.hexdigest()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Fallo al calcular huella de contenido de %s: %s", db_path, exc)
        return calculate_sha256(db_path)


def check_and_run_scheduled_backup(
    db_session: Session,
    db_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
) -> Optional[BackupMetadata]:
    """Evalúa si corresponde generar un respaldo programado y lo ejecuta evitando duplicados por huella de contenido."""
    config = get_or_create_schedule_config(db_session)
    if not config.enabled:
        return None

    now = datetime.datetime.now(timezone.utc)
    target_db = db_path or get_db_path()
    b_dir = backup_dir or get_backup_dir()

    if not target_db.exists():
        logger.warning("No se puede ejecutar copia programada: no existe base de datos en %s", target_db)
        return None

    # Comprobar vencimiento por fecha
    is_due = False
    if config.last_automated_backup_at is None:
        is_due = True
    else:
        last_dt = config.last_automated_backup_at.replace(tzinfo=timezone.utc)
        if (now - last_dt) >= datetime.timedelta(days=config.frequency_days):
            is_due = True

    if not is_due:
        return None

    # Comprobación de duplicados determinista por huella digital de contenido de usuario
    current_fingerprint = get_database_content_fingerprint(target_db)
    if config.last_backup_sha256 == current_fingerprint:
        logger.info(
            "Copia programada omitida: el contenido contable no ha experimentado cambios (Huella: %s)",
            current_fingerprint[:8],
        )
        config.last_automated_backup_at = now
        db_session.commit()
        return None

    logger.info("Ejecutando copia programada periódica (frecuencia: %d días)...", config.frequency_days)
    metadata = create_backup(
        backup_type="AUTOMATIC",
        db_path=target_db,
        backup_dir=b_dir,
        keep_max_copies=config.keep_max_copies,
    )

    config.last_automated_backup_at = now
    config.last_backup_sha256 = current_fingerprint
    db_session.commit()

    return metadata
