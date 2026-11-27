"""Módulo de resolución y configuración automática del entorno local (.env).

Garantiza la experiencia Clone & Run (Zero-Config): si el usuario clona el repositorio
y arranca sin haber creado manualmente el archivo .env, el sistema copia de forma segura
la plantilla '.env.example' a '.env' con valores por defecto locales y seguros.
Incluye parser nativo en Python por si el contenedor (p. ej. frontend) no instala python-dotenv.
"""

import logging
import os
from pathlib import Path
import shutil
from typing import Dict, Set

try:
    from dotenv import dotenv_values as _dotenv_values
except ImportError:  # pragma: no cover - ruta activa en contenedor frontend sin python-dotenv
    _dotenv_values = None  # type: ignore[assignment]

logger = logging.getLogger("backend.utils.env_setup")

_LOADED_FROM_ENV_KEYS: Set[str] = set()


def _parse_env_lines(env_file: Path) -> Dict[str, str]:
    """Lee pares KEY=VALUE desde .env usando python-dotenv si está disponible o fallback stdlib."""
    if _dotenv_values is not None:
        raw_map = _dotenv_values(env_file)
        return {k: v for k, v in raw_map.items() if k and v is not None}

    parsed: Dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
            val = val[1:-1]
        if key:
            parsed[key] = val
    return parsed



def _parse_env_lines(env_file: Path) -> Dict[str, str]:
    """Lee pares KEY=VALUE desde .env usando python-dotenv si está disponible o fallback stdlib."""
    if _dotenv_values is not None:
        raw_map = _dotenv_values(env_file)
        return {k: v for k, v in raw_map.items() if k and v is not None}

    parsed: Dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
            val = val[1:-1]
        if key:
            parsed[key] = val
    return parsed


def ensure_env_file() -> Path:
    """Verifica si existe el archivo .env; si no existe pero existe .env.example,

    crea automáticamente una copia local para facilitar la puesta en marcha Zero-Config.
    Carga las variables de entorno resultantes en el entorno de ejecución, rellenando
    también variables declaradas vacías por Docker Compose (ej. MOBILE_PUBLIC_URL='').
    """
    # Localizar raíz del repositorio (3 niveles arriba desde src/backend/utils/)
    root = Path(__file__).resolve().parents[3]
    env_file = root / ".env"
    env_example = root / ".env.example"

    if not env_file.exists() and env_example.exists():
        try:
            shutil.copyfile(env_example, env_file)
            logger.info("Archivo .env no encontrado. Creado automáticamente a partir de .env.example")
        except Exception as exc:
            logger.warning("No se pudo copiar automáticamente .env.example a .env: %s", exc)

    if env_file.exists():
        try:
            values = _parse_env_lines(env_file)
            for key, val in values.items():
                current = os.environ.get(key)
                if current is None or current == "" or key in _LOADED_FROM_ENV_KEYS:
                    os.environ[key] = val
                    _LOADED_FROM_ENV_KEYS.add(key)
        except Exception as exc:
            logger.warning("No se pudo cargar variables desde %s: %s", env_file, exc)

    return env_file
