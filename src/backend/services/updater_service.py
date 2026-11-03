"""
Servicio desacoplado de Actualizaciones Over-The-Air (In-App OTA Updater).
Implementa comprobación inteligente en GitHub API, descarga en staging, validación
sintáctica con compileall, protección anti-Tar-Slip, doble respaldo preventivo,
manifiesto de archivos instalados (pruning), diff de dependencias y rollback en 1 clic.
"""

import compileall
import hashlib
import json
import logging
import os
import shutil
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
import sqlalchemy as sa

from backend.database.componentes.sqlite_db import DB_PATH, Base, engine, init_db
from backend.domain.schemas.updater import (
    CodeRollbackResponse,
    UpdateApplyResponse,
    UpdateCheckResponse,
    VersionInfo,
)
from backend.services.backup_service import create_backup, get_backup_dir

logger = logging.getLogger(__name__)

# Archivos y prefijos protegidos: NUNCA deben sobrescribirse ni eliminarse
PROTECTED_PATHS: Set[str] = {
    "src/backend/data/finanzas.db",
    "src/backend/data/finanzas.db-wal",
    "src/backend/data/finanzas.db-shm",
    "src/backend/data/device_id.txt",
    "src/backend/data/version.json",
    "src/backend/data/installed_manifest.json",
    ".env",
    ".env.local",
}

PROTECTED_PREFIXES: Tuple[str, ...] = (
    "src/backend/data/finanzas.db",
    "backups",
    "sync",
    ".git",
    "venv",
    ".venv",
    "tmp",
    "logs",
)

# Caché en memoria para comprobaciones en GitHub API
_cache: Dict[str, Any] = {
    "response": None,
    "timestamp": 0.0,
}

CACHE_TTL_SECONDS: float = 900.0  # 15 minutos
DEBOUNCE_SECONDS: float = 60.0    # 60 segundos


def get_project_root() -> Path:
    """Resuelve la ruta raíz del proyecto garantizando cero configuración manual."""
    env_root = os.environ.get("PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    # Desde src/backend/services/ hacia la raíz del repositorio
    return Path(__file__).resolve().parents[3]


def get_data_dir(project_root: Optional[Path] = None) -> Path:
    """Retorna la carpeta de datos persistente (src/backend/data)."""
    root = project_root or get_project_root()
    data_dir = root / "src" / "backend" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_staging_dir(project_root: Optional[Path] = None) -> Path:
    """Retorna el directorio temporal de staging para descargas y validación."""
    root = project_root or get_project_root()
    staging_dir = root / "tmp" / "update_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    return staging_dir


def get_version_file(project_root: Optional[Path] = None) -> Path:
    """Retorna la ruta del archivo version.json."""
    return get_data_dir(project_root) / "version.json"


def get_manifest_file(project_root: Optional[Path] = None) -> Path:
    """Retorna la ruta del manifiesto de ficheros instalados."""
    return get_data_dir(project_root) / "installed_manifest.json"


def is_git_repository(project_root: Optional[Path] = None) -> bool:
    """Verifica si el entorno actual es un clon local de Git (.git/)."""
    root = project_root or get_project_root()
    return (root / ".git").is_dir()


def clear_check_cache() -> None:
    """Limpia la caché en memoria de comprobaciones (utilizado en tests)."""
    global _cache
    _cache["response"] = None
    _cache["timestamp"] = 0.0


def calculate_file_sha256(filepath: Path) -> Optional[str]:
    """Calcula el hash SHA-256 de un fichero si existe en disco."""
    if not filepath.exists() or not filepath.is_file():
        return None
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_current_version(project_root: Optional[Path] = None) -> VersionInfo:
    """Lee y devuelve la versión actualmente instalada en el sistema."""
    root = project_root or get_project_root()
    v_file = get_version_file(root)
    b_dir = get_backup_dir()

    rollback_available = (b_dir / "code_snapshot_prev.tar.gz").is_file()
    is_git = is_git_repository(root)
    default_branch = os.environ.get("UPDATE_BRANCH", "main")

    if not v_file.exists():
        return VersionInfo(
            current_commit="initial",
            branch=default_branch,
            last_updated_at=None,
            commit_message=None,
            rollback_available=rollback_available,
            is_git_repo=is_git,
        )

    try:
        data = json.loads(v_file.read_text(encoding="utf-8"))
        return VersionInfo(
            current_commit=data.get("current_commit", "initial"),
            branch=data.get("branch", default_branch),
            last_updated_at=data.get("last_updated_at"),
            commit_message=data.get("commit_message"),
            rollback_available=rollback_available,
            is_git_repo=is_git,
        )
    except Exception as exc:
        logger.warning("No se pudo leer version.json: %s", exc)
        return VersionInfo(
            current_commit="initial",
            branch=default_branch,
            last_updated_at=None,
            commit_message=None,
            rollback_available=rollback_available,
            is_git_repo=is_git,
        )


def save_current_version(
    commit_hash: str,
    branch: str,
    commit_message: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> None:
    """Guarda atómicamente el estado de la versión en src/backend/data/version.json."""
    v_file = get_version_file(project_root)
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "current_commit": commit_hash,
        "branch": branch,
        "last_updated_at": now_iso,
        "commit_message": commit_message,
    }
    tmp_file = v_file.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_file.replace(v_file)
    logger.info("Versión guardada con éxito en %s: commit %s", v_file, commit_hash[:7])


def check_remote_updates(
    force: bool = False,
    project_root: Optional[Path] = None,
    repo_owner: Optional[str] = None,
    repo_name: Optional[str] = None,
    branch: Optional[str] = None,
    github_token: Optional[str] = None,
) -> UpdateCheckResponse:
    """
    Comprueba si existen actualizaciones en GitHub respetando la cuota de la API
    mediante búfer de 15 minutos en RAM y debounce de 60 segundos.
    """
    global _cache
    root = project_root or get_project_root()
    current_ver = get_current_version(root)

    owner = repo_owner or os.environ.get("GITHUB_REPO_OWNER", "Raul515")
    repo = repo_name or os.environ.get("GITHUB_REPO_NAME", "GestorFinanzas")
    target_branch = branch or current_ver.branch or os.environ.get("UPDATE_BRANCH", "main")
    token = github_token or os.environ.get("GITHUB_TOKEN")

    now = time.time()
    last_check = _cache["timestamp"]
    cached_resp: Optional[UpdateCheckResponse] = _cache["response"]

    # Comprobación de caché
    if cached_resp is not None:
        elapsed = now - last_check
        if not force and elapsed < CACHE_TTL_SECONDS:
            return cached_resp.model_copy(update={"cached": True})
        if force and elapsed < DEBOUNCE_SECONDS:
            return cached_resp.model_copy(update={"cached": True})

    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{target_branch}"
    headers = {
        "User-Agent": "GestorFinanzas-OTA-Updater/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    logger.info("Consultando GitHub API para actualizaciones: %s", url)
    checked_iso = datetime.now(timezone.utc).isoformat()

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        rate_rem_header = resp.headers.get("X-RateLimit-Remaining")
        rate_rem = int(rate_rem_header) if rate_rem_header and rate_rem_header.isdigit() else None

        if resp.status_code == 200:
            data = resp.json()
            remote_sha = data.get("sha", "")
            commit_data = data.get("commit", {})
            remote_msg = commit_data.get("message", "").split("\n")[0]
            committer_date = commit_data.get("committer", {}).get("date")

            update_avail = False
            if current_ver.current_commit == "initial":
                update_avail = True
            elif (
                remote_sha != current_ver.current_commit
                and remote_sha[:7] != current_ver.current_commit[:7]
            ):
                update_avail = True

            result = UpdateCheckResponse(
                update_available=update_avail,
                current_commit=current_ver.current_commit,
                remote_commit=remote_sha,
                remote_commit_message=remote_msg,
                remote_commit_date=committer_date,
                branch=target_branch,
                checked_at=checked_iso,
                cached=False,
                rate_limit_remaining=rate_rem,
                error=None,
            )
            _cache["response"] = result
            _cache["timestamp"] = now
            return result

        if resp.status_code == 403:
            reset_ts_str = resp.headers.get("X-RateLimit-Reset")
            min_wait = 15
            if reset_ts_str and reset_ts_str.isdigit():
                diff_sec = max(0, int(reset_ts_str) - int(now))
                min_wait = max(1, diff_sec // 60)
            err_msg = (
                f"Límite de peticiones a GitHub alcanzado (HTTP 403). Podrás consultar de nuevo "
                f"en aproximadamente {min_wait} minutos o configurar GITHUB_TOKEN en tu archivo .env."
            )
            logger.warning("GitHub API Rate limit alcanzado: %s", err_msg)
            return UpdateCheckResponse(
                update_available=False,
                current_commit=current_ver.current_commit,
                remote_commit="",
                remote_commit_message="",
                remote_commit_date=None,
                branch=target_branch,
                checked_at=checked_iso,
                cached=False,
                rate_limit_remaining=0,
                error=err_msg,
            )

        if resp.status_code == 404:
            err_msg = f"Repositorio o rama '{target_branch}' no encontrada en GitHub (HTTP 404)."
            logger.warning(err_msg)
            return UpdateCheckResponse(
                update_available=False,
                current_commit=current_ver.current_commit,
                remote_commit="",
                remote_commit_message="",
                remote_commit_date=None,
                branch=target_branch,
                checked_at=checked_iso,
                cached=False,
                rate_limit_remaining=rate_rem,
                error=err_msg,
            )

        err_msg = f"Respuesta inesperada de GitHub (HTTP {resp.status_code})."
        logger.warning(err_msg)
        return UpdateCheckResponse(
            update_available=False,
            current_commit=current_ver.current_commit,
            remote_commit="",
            remote_commit_message="",
            remote_commit_date=None,
            branch=target_branch,
            checked_at=checked_iso,
            cached=False,
            rate_limit_remaining=rate_rem,
            error=err_msg,
        )

    except requests.RequestException as exc:
        err_msg = f"Error de conexión al consultar GitHub: {exc}"
        logger.warning(err_msg)
        return UpdateCheckResponse(
            update_available=False,
            current_commit=current_ver.current_commit,
            remote_commit="",
            remote_commit_message="",
            remote_commit_date=None,
            branch=target_branch,
            checked_at=checked_iso,
            cached=False,
            rate_limit_remaining=None,
            error=err_msg,
        )


def _is_safe_tar_member(member: tarfile.TarInfo, target_dir: Path) -> bool:
    """Valida rigurosamente que una entrada de un tarball no escape del destino (Anti-Tar-Slip)."""
    if os.path.isabs(member.name):
        return False
    parts = Path(member.name).parts
    if ".." in parts:
        return False
    try:
        resolved_dest = (target_dir / member.name).resolve()
        resolved_dest.relative_to(target_dir.resolve())
        return True
    except (ValueError, RuntimeError):
        return False


def extract_tarball_with_staging_normalization(tar_path: Path, staging_dir: Path) -> Path:
    """
    Descomprime un tarball aplicando validación anti-Tar-Slip y normaliza la
    subcarpeta generada automáticamente por GitHub ({repo}-{branch}/) hacia staging_dir.
    """
    raw_dir = staging_dir / "_raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir, ignore_errors=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tar_path, "r:*") as tar:
        for member in tar.getmembers():
            if not _is_safe_tar_member(member, raw_dir):
                raise ValueError(
                    f"Ruta maliciosa o sospechosa detectada en el tarball (Anti-Tar-Slip): {member.name}"
                )
            tar.extract(member, path=raw_dir)

    # Identificar si GitHub encapsuló los archivos en un directorio raíz único
    entries = [e for e in raw_dir.iterdir() if not e.name.startswith(".")]
    content_root = raw_dir
    if len(entries) == 1 and entries[0].is_dir():
        content_root = entries[0]

    # Mover el contenido al directorio staging_dir
    for item in content_root.iterdir():
        dest = staging_dir / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest, ignore_errors=True)
            else:
                dest.unlink(missing_ok=True)
        shutil.move(str(item), str(dest))

    # Limpiar directorio auxiliar _raw y archivo tar
    shutil.rmtree(raw_dir, ignore_errors=True)
    if tar_path.exists() and tar_path.parent == staging_dir:
        tar_path.unlink(missing_ok=True)

    logger.info("Tarball extraído y normalizado en staging: %s", staging_dir)
    return staging_dir


def download_tarball_to_staging(
    branch: str,
    staging_dir: Path,
    repo_owner: Optional[str] = None,
    repo_name: Optional[str] = None,
    github_token: Optional[str] = None,
) -> Path:
    """Descarga el tarball oficial desde GitHub y lo deposita en el staging."""
    owner = repo_owner or os.environ.get("GITHUB_REPO_OWNER", "Raul515")
    repo = repo_name or os.environ.get("GITHUB_REPO_NAME", "GestorFinanzas")
    token = github_token or os.environ.get("GITHUB_TOKEN")

    tar_path = staging_dir / "download.tar.gz"
    url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.tar.gz"
    headers = {
        "User-Agent": "GestorFinanzas-OTA-Updater/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    logger.info("Descargando paquete de actualización desde: %s", url)
    with requests.get(url, headers=headers, stream=True, timeout=30) as r:
        if r.status_code != 200:
            raise RuntimeError(
                f"Error descargando el tarball de GitHub (HTTP {r.status_code}). Verifica rama o permisos."
            )
        with open(tar_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

    return tar_path


def validate_staging_syntax(staging_dir: Path) -> bool:
    """
    Valida la integridad y la sintaxis de Python en el staging antes de transferir a producción.
    Verifica la existencia de los puntos de entrada principales y ejecuta compileall.
    """
    backend_main = staging_dir / "src" / "backend" / "api" / "main.py"
    frontend_app = staging_dir / "src" / "frontend" / "app.py"

    if not backend_main.is_file():
        logger.error("Archivo principal de backend no encontrado en staging: %s", backend_main)
        return False

    if not frontend_app.is_file():
        logger.error("Archivo principal de frontend no encontrado en staging: %s", frontend_app)
        return False

    # Validar compilación de sintaxis de Python en todo src/ del staging
    src_staging = staging_dir / "src"
    syntax_ok = compileall.compile_dir(str(src_staging), force=True, quiet=1)
    if not syntax_ok:
        logger.error("Fallo de sintaxis de Python detectado en el paquete en staging.")
        return False

    logger.info("Validación sintáctica en staging completada con éxito.")
    return True


def check_dependency_changes(root_dir: Path, staging_dir: Path) -> bool:
    """Compara hashes SHA-256 de requerimientos para detectar nuevas dependencias."""
    req_files = ["backend.txt", "frontend.txt"]
    for req_name in req_files:
        current_req = root_dir / "requirements" / req_name
        staging_req = staging_dir / "requirements" / req_name

        curr_hash = calculate_file_sha256(current_req)
        stag_hash = calculate_file_sha256(staging_req)

        if stag_hash is not None and stag_hash != curr_hash:
            logger.info("Cambio detectado en requirements/%s (Nuevo SHA: %s)", req_name, stag_hash[:8])
            return True
    return False


def _snapshot_tar_filter(tarinfo: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
    """Filtra archivos temporales, base de datos activa y bytecode en la instantánea de código."""
    norm = tarinfo.name.replace("\\", "/")
    if "__pycache__" in norm or norm.endswith(".pyc"):
        return None
    if "finanzas.db" in norm:
        return None
    return tarinfo


def create_code_snapshot(root_dir: Path, backups_dir: Path) -> Path:
    """Crea una instantánea comprimida de código y requerimientos (code_snapshot_prev.tar.gz)."""
    snapshot_path = backups_dir / "code_snapshot_prev.tar.gz"
    tmp_snapshot = backups_dir / "code_snapshot_prev.tmp.tar.gz"

    with tarfile.open(tmp_snapshot, "w:gz") as tar:
        src_path = root_dir / "src"
        if src_path.exists():
            tar.add(str(src_path), arcname="src", filter=_snapshot_tar_filter)

        req_path = root_dir / "requirements"
        if req_path.exists():
            tar.add(str(req_path), arcname="requirements", filter=_snapshot_tar_filter)

        v_file = get_version_file(root_dir)
        if v_file.exists():
            tar.add(str(v_file), arcname="src/backend/data/version.json")

    tmp_snapshot.replace(snapshot_path)
    logger.info("Instantánea de código previo creada: %s", snapshot_path)
    return snapshot_path


def purge_bytecode(src_dir: Path) -> None:
    """Purga de forma defensiva las carpetas __pycache__ y archivos .pyc en src/."""
    if not src_dir.exists():
        return
    for item in src_dir.rglob("__pycache__"):
        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
        except (PermissionError, OSError) as exc:
            logger.warning("No se pudo purgar __pycache__ en %s: %s", item, exc)

    for pyc in src_dir.rglob("*.pyc"):
        try:
            pyc.unlink(missing_ok=True)
        except (PermissionError, OSError) as exc:
            logger.warning("No se pudo eliminar archivo bytecode %s: %s", pyc, exc)


def is_path_protected(rel_path_str: str) -> bool:
    """Determina si una ruta relativa pertenece a la lista protegida incondicional."""
    norm = rel_path_str.replace("\\", "/").strip("/")
    if norm in PROTECTED_PATHS:
        return True
    for prefix in PROTECTED_PREFIXES:
        if norm == prefix or norm.startswith(f"{prefix}/"):
            return True
    return False


def transfer_staging_to_production(staging_dir: Path, root_dir: Path) -> Tuple[int, int]:
    """
    Transfiere archivos validados desde staging a producción respetando el blindaje
    y realiza pruning de archivos obsoletos según installed_manifest.json.
    """
    files_updated = 0
    obsolete_pruned = 0
    new_manifest_files: List[str] = []

    # 1. Copiar archivos desde staging respetando la protección
    for file_path in staging_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(staging_dir).as_posix()
            if is_path_protected(rel_path):
                logger.debug("Archivo protegido omitido de sobrescritura: %s", rel_path)
                continue

            target_path = root_dir / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(file_path), str(target_path))
            files_updated += 1
            new_manifest_files.append(rel_path)

    # 2. Pruning de archivos obsoletos usando el manifiesto previo
    manifest_path = get_manifest_file(root_dir)
    if manifest_path.exists():
        try:
            old_manifest: List[str] = json.loads(manifest_path.read_text(encoding="utf-8"))
            new_manifest_set = set(new_manifest_files)
            for old_rel in old_manifest:
                if old_rel not in new_manifest_set and not is_path_protected(old_rel):
                    obsolete_file = root_dir / old_rel
                    if obsolete_file.is_file():
                        try:
                            obsolete_file.unlink(missing_ok=True)
                            obsolete_pruned += 1
                            logger.info("Archivo obsoleto eliminado (pruning): %s", old_rel)
                        except OSError as exc:
                            logger.warning("No se pudo podar archivo obsoleto %s: %s", old_rel, exc)
        except Exception as exc:
            logger.warning("Error leyendo installed_manifest.json previo: %s", exc)

    # 3. Guardar el nuevo manifiesto instalado
    tmp_manifest = manifest_path.with_suffix(".tmp")
    tmp_manifest.write_text(json.dumps(sorted(new_manifest_files), indent=2), encoding="utf-8")
    tmp_manifest.replace(manifest_path)

    return files_updated, obsolete_pruned


def run_defensive_database_migrations(db_engine=None) -> List[str]:
    """
    Ejecuta init_db() y aplica de forma defensiva sentencias ALTER TABLE ... ADD COLUMN
    si los modelos de SQLAlchemy incorporan columnas ausentes en la base SQLite activa.
    """
    init_db()
    applied_columns: List[str] = []
    eng = db_engine or engine

    try:
        with eng.connect() as conn:
            cursor = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            for table_name, table in Base.metadata.tables.items():
                if table_name in existing_tables:
                    col_cursor = conn.exec_driver_sql(f"PRAGMA table_info('{table_name}')")
                    existing_cols = {row[1] for row in col_cursor.fetchall()}
                    for col in table.columns:
                        if col.name not in existing_cols:
                            col_type = col.type.compile(dialect=eng.dialect)
                            default_clause = ""
                            if (
                                col.default is not None
                                and hasattr(col.default, "arg")
                                and not callable(col.default.arg)
                            ):
                                default_clause = f" DEFAULT {col.default.arg}"
                            elif col.nullable:
                                default_clause = " DEFAULT NULL"
                            sql = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}{default_clause}"
                            logger.info("Aplicando migración de esquema SQLite: %s", sql)
                            conn.exec_driver_sql(sql)
                            conn.commit()
                            applied_columns.append(f"{table_name}.{col.name}")
    except Exception as exc:
        logger.warning("Excepción en hook introspectivo de migración: %s", exc)

    return applied_columns


def rollback_code(project_root: Optional[Path] = None) -> CodeRollbackResponse:
    """
    Restaura el código y los requerimientos desde backups/code_snapshot_prev.tar.gz
    dejando la base de datos contable intacta.
    """
    root = project_root or get_project_root()
    b_dir = get_backup_dir()
    snapshot_path = b_dir / "code_snapshot_prev.tar.gz"

    if not snapshot_path.is_file():
        raise FileNotFoundError(
            "No existe ninguna instantánea de código previo en el directorio backups/ para revertir."
        )

    logger.info("Iniciando reversión de código desde %s...", snapshot_path)

    # Extraer snapshot sobre root con validación anti-Tar-Slip
    with tarfile.open(snapshot_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not _is_safe_tar_member(member, root):
                raise ValueError(f"Ruta maliciosa en instantánea de código: {member.name}")
            tar.extract(member, path=root)

    # Purgar bytecode
    purge_bytecode(root / "src")

    # Obtener versión restaurada
    current_ver = get_current_version(root)
    msg = f"Código revertido con éxito a la versión previa ({current_ver.current_commit[:7]})."
    logger.info(msg)

    return CodeRollbackResponse(
        success=True,
        restored_commit=current_ver.current_commit,
        message=msg,
    )


def apply_update(
    project_root: Optional[Path] = None,
    branch: Optional[str] = None,
    remote_commit: Optional[str] = None,
    custom_tarball_path: Optional[Path] = None,
    repo_owner: Optional[str] = None,
    repo_name: Optional[str] = None,
    github_token: Optional[str] = None,
) -> UpdateApplyResponse:
    """
    Orquestador completo del ciclo de actualización:
    1. Respaldo de base de datos preventivo (sqlite3.backup).
    2. Snapshot previo de código (code_snapshot_prev.tar.gz).
    3. Descarga y extracción en staging con normalización de subcarpeta de GitHub.
    4. Validación sintáctica con compileall.
    5. Detección de dependencias (requirements/).
    6. Transferencia y pruning de archivos obsoletos.
    7. Purga de bytecode.
    8. Hook introspectivo de migraciones SQLite.
    9. Actualización atómica de version.json.
    10. Limpieza de staging.
    """
    root = project_root or get_project_root()
    b_dir = get_backup_dir()
    staging_dir = get_staging_dir(root)
    current_ver = get_current_version(root)
    target_branch = branch or current_ver.branch or "main"

    # Determinar commit objetivo y mensaje
    target_commit = remote_commit or "unknown"
    commit_msg = None

    if not remote_commit or target_commit == "unknown":
        check_res = check_remote_updates(
            force=True,
            project_root=root,
            repo_owner=repo_owner,
            repo_name=repo_name,
            branch=target_branch,
            github_token=github_token,
        )
        if check_res.remote_commit:
            target_commit = check_res.remote_commit
            commit_msg = check_res.remote_commit_message

    logger.info("Iniciando ciclo de actualización hacia commit %s...", target_commit[:7])

    try:
        # Paso 1: Descargar o usar tarball suministrado
        if custom_tarball_path and custom_tarball_path.is_file():
            tar_path = custom_tarball_path
        else:
            tar_path = download_tarball_to_staging(
                branch=target_branch,
                staging_dir=staging_dir,
                repo_owner=repo_owner,
                repo_name=repo_name,
                github_token=github_token,
            )

        # Paso 2: Descomprimir y normalizar subcarpeta en staging
        extract_tarball_with_staging_normalization(tar_path, staging_dir)

        # Paso 3: Validación sintáctica obligatoria
        if not validate_staging_syntax(staging_dir):
            raise ValueError(
                "La validación sintáctica o estructural del paquete descargado ha fallado. "
                "La actualización se ha cancelado de forma segura sin alterar producción."
            )

        # Paso 4: Detección de cambios en requerimientos
        new_deps = check_dependency_changes(root, staging_dir)

        # Paso 5: Generar respaldo preventivo de base de datos
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_backup_meta = create_backup(
            backup_type="MANUAL",
            custom_name=f"pre_update_safety_{ts}.db",
            backup_dir=b_dir,
        )
        pre_backup_path_str = str(b_dir / pre_backup_meta.filename)

        # Paso 6: Crear instantánea de código previo
        create_code_snapshot(root, b_dir)

        # Paso 7: Transferencia a producción y pruning
        updated_count, pruned_count = transfer_staging_to_production(staging_dir, root)

        # Paso 8: Purgar bytecode
        purge_bytecode(root / "src")

        # Paso 9: Hook de migraciones defensivas
        run_defensive_database_migrations()

        # Paso 10: Persistir nuevo commit en version.json
        save_current_version(
            commit_hash=target_commit,
            branch=target_branch,
            commit_message=commit_msg,
            project_root=root,
        )

        # Limpiar caché de comprobación
        clear_check_cache()

        msg = (
            f"Actualización completada con éxito al commit {target_commit[:7]}. "
            f"Se actualizaron {updated_count} archivos y se podaron {pruned_count} obsoletos."
        )
        if new_deps:
            msg += " ⚠️ Se detectaron nuevas dependencias: se recomienda reiniciar los contenedores o el entorno."

        return UpdateApplyResponse(
            success=True,
            previous_commit=current_ver.current_commit,
            updated_to_commit=target_commit,
            files_updated_count=updated_count,
            obsolete_files_pruned_count=pruned_count,
            pre_update_backup_path=pre_backup_path_str,
            new_dependencies_detected=new_deps,
            requires_rebuild=new_deps,
            message=msg,
        )

    except Exception as exc:
        logger.error("Error durante el ciclo de actualización: %s", exc, exc_info=True)
        raise

    finally:
        # Limpieza obligatoria del directorio de staging
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

