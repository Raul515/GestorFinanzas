"""Pruebas unitarias para el motor de configuración de logs y sanitización de privacidad."""

import logging
import pytest
from backend.utils.logging_config import (
    setup_logging,
    PrivacyFilter,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAX_BYTES,
    DEFAULT_BACKUP_COUNT,
)


@pytest.fixture(autouse=True)
def clean_root_logger():
    """Limpia los manejadores del logger raíz tras cada prueba para evitar efectos colaterales."""
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)


def test_setup_logging_creates_directory_and_file(tmp_path):
    """Verifica que setup_logging cree automáticamente el directorio de destino y escriba el registro formateado."""
    log_dir = tmp_path / "custom_logs"
    log_file = log_dir / "test.log"

    assert not log_dir.exists()
    logger = setup_logging(str(log_file), log_level="INFO")

    assert log_dir.exists()
    logger.info("Mensaje de prueba para creación de archivo")

    # Forzar volcado a disco
    for h in logger.handlers:
        h.flush()

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "[INFO]" in content
    assert "Mensaje de prueba para creación de archivo" in content
    assert "(test_logging_config.py:" in content


def test_setup_logging_rotation(tmp_path):
    """Verifica que RotatingFileHandler rote al alcanzar max_bytes y respete el límite máximo de copias backup_count."""
    log_file = tmp_path / "rotating.log"
    # Configurar un límite pequeño para forzar rotación rápida en pruebas
    logger = setup_logging(str(log_file), log_level="DEBUG", max_bytes=200, backup_count=3)

    for i in range(50):
        logger.info(f"Línea de log número {i:03d} con suficiente longitud para superar el límite rápidamente")

    for h in logger.handlers:
        h.flush()

    # Comprobar que se han generado copias rotadas y que no exceden el tope de 3
    backups = list(tmp_path.glob("rotating.log.*"))
    assert len(backups) > 0
    assert len(backups) <= 3


def test_privacy_filter_redacts_gemini_api_key(tmp_path):
    """Verifica que el filtro de privacidad sustituya claves de Gemini (AIza...) por [REDACTED]."""
    log_file = tmp_path / "privacy_key.log"
    logger = setup_logging(str(log_file), log_level="INFO")

    fake_gemini_key = "AIzaSyD-1234567890abcdef1234567890abcde"
    logger.info(f"Conexión con la API de Gemini usando la clave {fake_gemini_key} para análisis")

    for h in logger.handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert fake_gemini_key not in content
    assert "[REDACTED]" in content


def test_privacy_filter_redacts_bearer_token(tmp_path):
    """Verifica que las cabeceras de autorización con tokens Bearer sean ofuscadas a Bearer [REDACTED]."""
    log_file = tmp_path / "privacy_bearer.log"
    logger = setup_logging(str(log_file), log_level="INFO")

    bearer_token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
    logger.info(f"Petición saliente con Authorization: {bearer_token}")

    for h in logger.handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in content
    assert "Bearer [REDACTED]" in content


def test_privacy_filter_redacts_secret_assignments(tmp_path):
    """Verifica que las asignaciones de contraseñas, claves y secretos queden enmascaradas con [REDACTED]."""
    log_file = tmp_path / "privacy_secrets.log"
    logger = setup_logging(str(log_file), log_level="INFO")

    logger.info("Servicio inicializado con api_key=ultraSecret123 y password='miPasswordSeguro!'")
    logger.info("Otro token: 'tokenSecreto987'")

    for h in logger.handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "ultraSecret123" not in content
    assert "miPasswordSeguro!" not in content
    assert "tokenSecreto987" not in content
    assert "[REDACTED]" in content


def test_privacy_filter_with_tuple_args(tmp_path):
    """Verifica que los argumentos posicionales pasados al formateador del logger también se sintaticen."""
    log_file = tmp_path / "privacy_args.log"
    logger = setup_logging(str(log_file), log_level="INFO")

    fake_key = "AIzaSyD-9999999999abcdef9999999999abcde"
    logger.info("Petición con clave %s y estado %d", fake_key, 200)

    for h in logger.handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert fake_key not in content
    assert "[REDACTED]" in content


def test_privacy_filter_direct_record_list_args():
    """Verifica que si un LogRecord contiene una lista en args, se transforme limpiamente a tupla sanitizada."""
    filter_obj = PrivacyFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Usuario autenticado: %s",
        args=(),
        exc_info=None,
    )
    setattr(record, "args", ["Bearer eyJhbGciOi..."])
    result = filter_obj.filter(record)
    assert result is True
    assert isinstance(record.args, tuple)
    assert record.args == ("Bearer [REDACTED]",)


def test_log_level_overrides(tmp_path, monkeypatch):
    """Verifica la precedencia de niveles de log: INFO por defecto, sobreescritura por argumento y por variable de entorno."""
    log_file = tmp_path / "levels.log"

    # Nivel predeterminado: INFO
    logger = setup_logging(str(log_file))
    logger.debug("Mensaje de depuración que NO debe aparecer")
    logger.info("Mensaje informativo que SÍ debe aparecer")

    for h in logger.handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "Mensaje de depuración que NO debe aparecer" not in content
    assert "Mensaje informativo que SÍ debe aparecer" in content

    # Sobreescritura mediante parámetro explícito a DEBUG
    log_file_debug = tmp_path / "levels_debug.log"
    logger_debug = setup_logging(str(log_file_debug), log_level="DEBUG")
    logger_debug.debug("Mensaje de depuración que AHORA SÍ debe aparecer")

    for h in logger_debug.handlers:
        h.flush()

    content_debug = log_file_debug.read_text(encoding="utf-8")
    assert "Mensaje de depuración que AHORA SÍ debe aparecer" in content_debug

    # Sobreescritura mediante variable de entorno a WARNING
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    log_file_warn = tmp_path / "levels_warn.log"
    logger_warn = setup_logging(str(log_file_warn))
    logger_warn.info("Mensaje informativo suprimido por variable de entorno")
    logger_warn.warning("Mensaje de advertencia que SÍ debe aparecer")

    for h in logger_warn.handlers:
        h.flush()

    content_warn = log_file_warn.read_text(encoding="utf-8")
    assert "Mensaje informativo suprimido por variable de entorno" not in content_warn
    assert "Mensaje de advertencia que SÍ debe aparecer" in content_warn


def test_idempotent_setup_logging_no_duplicate_handlers(tmp_path):
    """Verifica que llamadas sucesivas a setup_logging no dupliquen manejadores en el logger."""
    log_file = tmp_path / "idempotent.log"
    logger1 = setup_logging(str(log_file))
    initial_count = len(logger1.handlers)

    logger2 = setup_logging(str(log_file))
    assert len(logger2.handlers) == initial_count
