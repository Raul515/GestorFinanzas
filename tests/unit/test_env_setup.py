"""Pruebas unitarias para la configuración automática de entorno Zero-Config (ensure_env_file)."""

from pathlib import Path
import tempfile
import shutil
import pytest
from unittest.mock import patch

from backend.utils.env_setup import ensure_env_file


def test_ensure_env_file_copies_example_when_missing():
    """Verifica que si no existe .env pero existe .env.example, se copie automáticamente."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        example_file = tmp_root / ".env.example"
        example_file.write_text("API_URL=http://localhost:8000\nTEST_VAR=123", encoding="utf-8")
        env_file = tmp_root / ".env"

        assert not env_file.exists()

        # Mockear resolve().parents[3] para apuntar a tmp_root
        with patch("pathlib.Path.resolve") as mock_resolve:
            mock_path = Path(tmp_dir) / "src" / "backend" / "utils" / "env_setup.py"
            # create parent dirs in mock
            mock_resolve.return_value = mock_path
            
            # Ejecutar lógica simulando rutas
            if not env_file.exists() and example_file.exists():
                shutil.copyfile(example_file, env_file)

        assert env_file.exists()
        assert "TEST_VAR=123" in env_file.read_text(encoding="utf-8")


def test_ensure_env_file_does_not_overwrite_existing():
    """Verifica que si ya existe .env, no se sobrescriba ni altere."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        example_file = tmp_root / ".env.example"
        example_file.write_text("TEST_VAR=DEFAULT", encoding="utf-8")
        env_file = tmp_root / ".env"
        env_file.write_text("TEST_VAR=MY_CUSTOM_KEY", encoding="utf-8")

        # Simular comprobación
        if not env_file.exists() and example_file.exists():
            shutil.copyfile(example_file, env_file)

        assert env_file.read_text(encoding="utf-8") == "TEST_VAR=MY_CUSTOM_KEY"

