from abc import ABC, abstractmethod
from typing import List, Optional, Any
from backend.domain.schemas import categorias as cat_schema, presupuestos as pres_schema, transacciones as trans_schema

class ICategoriaRepository(ABC):
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

class IPresupuestoRepository(ABC):
    @abstractmethod
    def get_presupuestos(self, mes: str) -> List[Any]:
        pass

    @abstractmethod
    def create_presupuesto(self, presupuesto: pres_schema.PresupuestoMensualCreate) -> Any:
        pass

    @abstractmethod
    def save_presupuestos_bulk(self, presupuestos: List[pres_schema.PresupuestoMensualCreate]) -> List[Any]:
        pass

class ITransaccionRepository(ABC):
    @abstractmethod
    def get_transacciones(self, mes: Optional[str] = None) -> List[Any]:
        pass

    @abstractmethod
    def create_transaccion(self, transaccion: trans_schema.TransaccionCreate) -> Any:
        pass

class IEmergencyFundRepository(ABC):
    @abstractmethod
    def get_or_create_emergency_fund(self) -> Any:
        pass

    @abstractmethod
    def update_emergency_fund(self, target_months: Optional[int] = None, current_balance: Optional[float] = None) -> Any:
        pass

    @abstractmethod
    def adjust_emergency_fund_balance(self, delta: float) -> Any:
        pass

class IRepository(ICategoriaRepository, IPresupuestoRepository, ITransaccionRepository, IEmergencyFundRepository, ABC):
    """Interfaz monolítica unificada para compatibilidad global."""
    pass

