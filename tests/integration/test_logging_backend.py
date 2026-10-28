"""Pruebas de integración para la persistencia de logs en backend FastAPI y middleware de observabilidad."""

import logging
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.utils.logging_config import setup_logging


def test_backend_startup_and_request_logging(tmp_path):
    """Verifica que las peticiones HTTP registren método, ruta, estado y latencia en el archivo de log."""
    log_file = tmp_path / "backend_integration.log"
    setup_logging(str(log_file), log_level="INFO")

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200

    # Forzar volcado a disco de todos los manejadores activos
    for h in logging.getLogger().handlers:
        h.flush()

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "HTTP GET / completed with status 200 in" in content
    assert "ms" in content
    assert "[INFO]" in content
    assert "(main.py:" in content


def test_backend_404_request_logging(tmp_path):
    """Verifica que las peticiones con error 404 registren el código de estado y la latencia correctamente."""
    log_file = tmp_path / "backend_404.log"
    setup_logging(str(log_file), log_level="INFO")

    client = TestClient(app)
    response = client.get("/non-existent-endpoint-test-xyz")
    assert response.status_code == 404

    for h in logging.getLogger().handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "HTTP GET /non-existent-endpoint-test-xyz completed with status 404 in" in content
    assert "ms" in content


def test_backend_privacy_sanitization_in_requests(tmp_path):
    """Verifica que cualquier secreto o clave API pasada en la URL quede enmascarada con [REDACTED]."""
    log_file = tmp_path / "backend_privacy.log"
    setup_logging(str(log_file), log_level="INFO")

    client = TestClient(app)
    fake_key = "AIzaSyD-1234567890abcdef1234567890abcde"
    response = client.get(f"/?api_key={fake_key}&password=miClaveUltraSecreta")
    assert response.status_code == 200

    for h in logging.getLogger().handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert fake_key not in content
    assert "miClaveUltraSecreta" not in content
    assert "[REDACTED]" in content
    assert "HTTP GET /?api_key=[REDACTED]&password=[REDACTED] completed with status 200 in" in content


def test_backend_multiple_requests_sequential(tmp_path):
    """Verifica que múltiples peticiones sucesivas se registren de forma ordenada sin interferencias."""
    log_file = tmp_path / "backend_sequential.log"
    setup_logging(str(log_file), log_level="INFO")

    client = TestClient(app)
    client.get("/")
    client.get("/non-existent-1")
    client.get("/non-existent-2")

    for h in logging.getLogger().handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "HTTP GET / completed with status 200 in" in content
    assert "HTTP GET /non-existent-1 completed with status 404 in" in content
    assert "HTTP GET /non-existent-2 completed with status 404 in" in content


def test_backend_unhandled_exception_logging(tmp_path):
    """Verifica que si ocurre una excepción no capturada, el middleware registre el error con latencia."""
    log_file = tmp_path / "backend_error.log"
    setup_logging(str(log_file), log_level="INFO")

    @app.get("/test-raise-error")
    def error_endpoint():
        raise RuntimeError("Fallo forzado de prueba")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test-raise-error")
    assert response.status_code == 500

    for h in logging.getLogger().handlers:
        h.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "HTTP GET /test-raise-error failed with exception: Fallo forzado de prueba" in content
    assert "ms" in content
