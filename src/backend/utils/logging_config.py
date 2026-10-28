"""Módulo centralizado de configuración de registros (logging) y sanitización de seguridad.

Proporciona una configuración unificada para archivos de log rotativos persistentes
con ofuscación automática de tokens, credenciales y claves privadas (Observabilidad con Fuga Cero).
"""

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from typing import Optional

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_BACKUP_COUNT = 3
DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"


class PrivacyFilter(logging.Filter):
    """Filtro de seguridad que intercepta y enmascara tokens sensibles, claves API y credenciales."""

    # Expresión regular para claves de API de Google AI / Gemini (ej. AIzaSyD-...)
    GEMINI_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z\-_]{35}")

    # Expresión regular para cabeceras de autorización Bearer
    BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_\.]+")

    # Expresión regular para asignaciones de contraseñas, secretos, tokens o claves API
    SECRET_ASSIGNMENT_PATTERN = re.compile(
        r"(?i)(['\"]?\b(?:api[_-]?key|password|secret|token|auth[_-]?token)['\"]?)(\s*[:=]\s*)(?:'[^']*'|\"[^\"]*\"|[^\s'\"&,]+)"
    )

    def sanitize(self, text: str) -> str:
        """Sanitiza una cadena de texto sustituyendo patrones confidenciales por [REDACTED].

        Args:
            text: Cadena de texto de entrada a inspeccionar.

        Returns:
            Cadena de texto con los secretos ofuscados.
        """
        if not text:
            return text

        # Ofuscación de claves de Gemini
        text = self.GEMINI_KEY_PATTERN.sub("[REDACTED]", text)

        # Ofuscación de tokens de tipo Bearer
        text = self.BEARER_TOKEN_PATTERN.sub("Bearer [REDACTED]", text)

        # Ofuscación de pares clave-valor de secretos y contraseñas
        text = self.SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", text)

        return text

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitiza el mensaje del registro de log y sus argumentos de forma directa.

        Args:
            record: Objeto de registro LogRecord emitido por el sistema de logging.

        Returns:
            Booleano True permitiendo la propagación continua del registro filtrado.
        """
        if isinstance(record.msg, str):
            record.msg = self.sanitize(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (self.sanitize(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, (tuple, list)):
                record.args = tuple(
                    (self.sanitize(v) if isinstance(v, str) else v)
                    for v in record.args
                )

        return True


def setup_logging(
    log_file: str,
    log_level: Optional[str] = None,
    max_bytes: Optional[int] = None,
    backup_count: Optional[int] = None,
    target_logger: Optional[logging.Logger] = None,
) -> logging.Logger:
    """Configura la persistencia de logs rotativos en fichero con sanitización de seguridad.

    Args:
        log_file: Ruta relativa o absoluta hacia el archivo de log de destino.
        log_level: Nivel de registro opcional (ej. 'DEBUG', 'INFO').
        max_bytes: Tamaño máximo del archivo en bytes antes de rotar.
        backup_count: Número máximo de copias de respaldo históricas a conservar.
        target_logger: Instancia opcional de Logger a configurar. Por defecto configura el logger raíz.

    Returns:
        La instancia configurada del Logger.
    """
    # 1. Resolución de parámetros de configuración
    level_str = log_level or os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    numeric_level = getattr(logging, level_str.upper(), logging.INFO)

    if max_bytes is None:
        try:
            max_bytes = int(os.getenv("LOG_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
        except ValueError:
            max_bytes = DEFAULT_MAX_BYTES

    if backup_count is None:
        try:
            backup_count = int(os.getenv("LOG_BACKUP_COUNT", str(DEFAULT_BACKUP_COUNT)))
        except ValueError:
            backup_count = DEFAULT_BACKUP_COUNT

    # 2. Asegurar la existencia del directorio de destino
    abs_log_path = os.path.abspath(log_file)
    log_dir = os.path.dirname(abs_log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # 3. Resolución del logger objetivo
    target = target_logger if target_logger is not None else logging.getLogger()
    target.setLevel(numeric_level)

    # 4. Comprobación de manejador existente para garantizar idempotencia
    existing_handler = None
    for handler in target.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and getattr(handler, "baseFilename", None) == abs_log_path
        ):
            existing_handler = handler
            break

    if existing_handler:
        existing_handler.setLevel(numeric_level)
        return target

    # 5. Creación y asignación de RotatingFileHandler
    formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
    file_handler = RotatingFileHandler(
        abs_log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(PrivacyFilter())

    target.addHandler(file_handler)

    # 6. Asegurar que los manejadores existentes (ej. consola) apliquen el filtro de privacidad
    for h in target.handlers:
        if not any(isinstance(f, PrivacyFilter) for f in h.filters):
            h.addFilter(PrivacyFilter())

    return target
