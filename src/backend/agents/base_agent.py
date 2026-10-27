"""
Clase Base Abstracta para los Agentes Inteligentes del Sistema (Spec 005).
Exige que cada agente implemente y compile su propio subgrafo o flujo de trabajo en LangGraph.
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Clase abstracta para todos los agentes cognitivos del sistema.
    Cada agente tiene un rol específico, descripción y compila su flujo de trabajo en LangGraph.
    """

    def __init__(
        self,
        name: str,
        description: str,
        model_name: Optional[str] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.model_name = model_name
        self._compiled_graph: Optional[Any] = None

    @abstractmethod
    def build_graph(self) -> Any:
        """
        Construye, conecta y compila el flujo de trabajo (StateGraph) del agente en LangGraph.
        Retorna el grafo compilado listo para ejecución.
        """
        pass

    def compile(self) -> Any:
        """
        Compila el grafo del agente si no estaba compilado previamente y lo almacena en caché interna.
        """
        if self._compiled_graph is None:
            logger.info("Compilando grafo para el agente '%s'", self.name)
            self._compiled_graph = self.build_graph()
        return self._compiled_graph

    def run(self, state: Any) -> Any:
        """
        Ejecuta el grafo compilado del agente pasando el estado correspondiente.
        """
        graph = self.compile()
        logger.debug("Ejecutando agente '%s' con estado inicial: %s", self.name, list(state.keys()))
        result = graph.invoke(state)
        return result

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}', model='{self.model_name}')>"
