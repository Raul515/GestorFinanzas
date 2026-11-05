"""Módulo de resolución y configuración automática del entorno local (.env).

Garantiza la experiencia Clone & Run (Zero-Config): si el usuario clona el repositorio
y arranca sin haber creado manualmente el archivo .env, el sistema copia de forma segura
la plantilla '.env.example' a '.env' con valores por defecto locales y seguros.
"""

import logging
import os
from pathlib import Path
import shutil
from dotenv import load_dotenv

logger = logging.getLogger("backend.utils.env_setup")


def ensure_env_file() -> Path:
    """Verifica si existe el archivo .env; si no existe pero existe .env.example,

    crea automáticamente una copia local para facilitar la puesta en marcha Zero-Config.
    Carga las variables de entorno resultantes en el entorno de ejecución.
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
        load_dotenv(dotenv_path=env_file)
    else:
        load_dotenv()

    return env_file

