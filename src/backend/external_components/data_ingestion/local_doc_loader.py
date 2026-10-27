"""
Adaptador de Ingesta y Lectura de Documentos Locales (Spec 005 - external_components).
Permite buscar y cargar archivos de texto y Markdown almacenados localmente
en el directorio de conocimiento (tipo notas exportadas o resúmenes de inversión).
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_KNOWLEDGE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "knowledge"
)


class LocalDocLoader:
    """
    Cargador e indexador ligero de documentos locales para el sistema multiagente.
    Opera 100% en local sin servicios externos.
    """

    def __init__(self, knowledge_dir: Optional[str] = None) -> None:
        self.knowledge_dir = knowledge_dir or os.path.abspath(DEFAULT_KNOWLEDGE_DIR)
        os.makedirs(self.knowledge_dir, exist_ok=True)

    def list_documents(self) -> List[str]:
        """Retorna los nombres de archivo soportados presentes en la carpeta de conocimiento."""
        if not os.path.exists(self.knowledge_dir):
            return []

        supported_exts = {".md", ".txt", ".json"}
        return [
            f for f in os.listdir(self.knowledge_dir)
            if os.path.isfile(os.path.join(self.knowledge_dir, f))
            and os.path.splitext(f)[1].lower() in supported_exts
        ]

    def load_document(self, filename: str) -> Optional[str]:
        """Lee y retorna el contenido completo de un documento específico."""
        clean_name = os.path.basename(filename)
        filepath = os.path.join(self.knowledge_dir, clean_name)
        if not os.path.exists(filepath):
            logger.warning("Documento local '%s' no encontrado en %s", clean_name, self.knowledge_dir)
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as exc:
            logger.error("Error al leer documento local '%s': %s", clean_name, exc)
            return None

    def search_documents(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Búsqueda por palabras clave en los documentos locales.
        Retorna fragmentos relevantes con nombre de archivo y coincidencias.
        """
        clean_query = query.strip().lower()
        if not clean_query:
            return []

        results: List[Dict[str, Any]] = []
        docs = self.list_documents()

        for doc_name in docs:
            content = self.load_document(doc_name)
            if not content:
                continue

            content_lower = content.lower()
            if clean_query in content_lower or clean_query in doc_name.lower():
                idx = content_lower.find(clean_query)
                if idx != -1:
                    start = max(0, idx - 120)
                    end = min(len(content), idx + 250)
                    snippet = "..." + content[start:end].replace("\n", " ").strip() + "..."
                else:
                    snippet = content[:300].replace("\n", " ").strip() + "..."

                results.append(
                    {
                        "document": doc_name,
                        "snippet": snippet,
                    }
                )

                if len(results) >= max_results:
                    break

        return results
