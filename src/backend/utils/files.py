"""Utilidades transversales de escritura atómica y hashing de archivos (Spec 017 - Fase 3)."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def atomic_write_json(target_path: Path, data: Any, indent: int = 2) -> None:
    """Escribe un JSON de forma atómica mediante archivo temporal y os.replace()."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f"{target_path.name}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        os.replace(tmp_path, target_path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def calculate_file_sha256(file_path: Path) -> str:
    """Calcula el digest SHA-256 hexadecimal de un archivo leyendo en bloques de 64 KB."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
