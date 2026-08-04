from abc import ABC, abstractmethod
from typing import List, Optional, Any
from backend.domain.schemas import categorias as cat_schema, presupuestos as pres_schema, transacciones as trans_schema

class IRepository(ABC):
    @abstractmethod
    def get_categorias(self) -> List[Any]:
        pass

    @abstractmethod
    def create_categoria(self, categoria: cat_schema.CategoriaCreate) -> Any:
        pass

    @abstractmethod
    def get_subcategorias(self, categoria_id: Optional[int] = None) -> List[Any]:
        pass

    @abstractmethod
    def create_subcategoria(self, subcategoria: cat_schema.SubcategoriaCreate) -> Any:
        pass

    @abstractmethod
    def get_transacciones(self, mes: Optional[str] = None) -> List[Any]:
        pass

    @abstractmethod
    def create_transaccion(self, transaccion: trans_schema.TransaccionCreate) -> Any:
        pass

    @abstractmethod
    def get_presupuestos(self, mes: str) -> List[Any]:
        pass

    @abstractmethod
    def create_presupuesto(self, presupuesto: pres_schema.PresupuestoMensualCreate) -> Any:
        pass
