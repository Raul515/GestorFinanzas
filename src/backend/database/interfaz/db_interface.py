from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict
import datetime
from backend.domain.schemas import categories as cat_schema, budgets as budget_schema, transactions as trans_schema


class ICategoryRepository(ABC):
    """Interfaz del repositorio de categorías y subcategorías."""

    @abstractmethod
    def get_categories(self) -> List[Any]:
        """Obtiene el listado completo de categorías contables."""
        pass

    @abstractmethod
    def create_category(self, category: cat_schema.CategoryCreate) -> Any:
        """Crea una nueva categoría contable."""
        pass

    @abstractmethod
    def get_subcategories(self, category_id: Optional[int] = None) -> List[Any]:
        """Obtiene subcategorías, filtrando opcionalmente por categoría."""
        pass

    @abstractmethod
    def create_subcategory(self, subcategory: cat_schema.SubcategoryCreate) -> Any:
        """Crea una nueva subcategoría contable."""
        pass

    # Métodos alias para compatibilidad
    def get_categorias(self) -> List[Any]:
        return self.get_categories()

    def create_categoria(self, categoria: Any) -> Any:
        return self.create_category(categoria)

    def get_subcategorias(self, categoria_id: Optional[int] = None) -> List[Any]:
        return self.get_subcategories(categoria_id)

    def create_subcategoria(self, subcategoria: Any) -> Any:
        return self.create_subcategory(subcategoria)


ICategoriaRepository = ICategoryRepository


class IBudgetRepository(ABC):
    """Interfaz del repositorio de presupuestos mensuales."""

    @abstractmethod
    def get_budgets(self, month: str) -> List[Any]:
        """Obtiene las asignaciones presupuestarias para un mes o plantilla BASE."""
        pass

    @abstractmethod
    def create_budget(self, budget: budget_schema.MonthlyBudgetCreate) -> Any:
        """Crea o actualiza una asignación presupuestaria individual."""
        pass

    @abstractmethod
    def save_budgets_bulk(self, budgets: List[budget_schema.MonthlyBudgetCreate]) -> List[Any]:
        """Guarda un conjunto de presupuestos en bloque."""
        pass

    # Métodos alias para compatibilidad
    def get_presupuestos(self, mes: str) -> List[Any]:
        return self.get_budgets(mes)

    def create_presupuesto(self, presupuesto: Any) -> Any:
        return self.create_budget(presupuesto)

    def save_presupuestos_bulk(self, presupuestos: List[Any]) -> List[Any]:
        return self.save_budgets_bulk(presupuestos)


IPresupuestoRepository = IBudgetRepository


class ITransactionRepository(ABC):
    """Interfaz del repositorio de transacciones contables."""

    @abstractmethod
    def get_transactions(self, month: Optional[str] = None) -> List[Any]:
        """Obtiene transacciones registradas, filtrando opcionalmente por mes."""
        pass

    @abstractmethod
    def create_transaction(self, transaction: trans_schema.TransactionCreate) -> Any:
        """Registra una nueva transacción y ejecuta sincronizaciones colaterales."""
        pass

    @abstractmethod
    def delete_transaction(self, transaction_id: int) -> bool:
        """Elimina una transacción existente y revierte efectos colaterales (ej. fondo de emergencia)."""
        pass

    # Métodos alias para compatibilidad
    def get_transacciones(self, mes: Optional[str] = None) -> List[Any]:
        return self.get_transactions(mes)

    def create_transaccion(self, transaccion: Any) -> Any:
        return self.create_transaction(transaccion)

    def delete_transaccion(self, transaccion_id: int) -> bool:
        return self.delete_transaction(transaccion_id)


ITransaccionRepository = ITransactionRepository


class IEmergencyFundRepository(ABC):
    """Interfaz del repositorio del fondo de emergencia."""

    @abstractmethod
    def get_or_create_emergency_fund(self) -> Any:
        """Obtiene o inicializa el fondo de emergencia con valores seguros."""
        pass

    @abstractmethod
    def update_emergency_fund(self, target_months: Optional[int] = None, current_balance: Optional[float] = None) -> Any:
        """Actualiza parámetros de cobertura o saldo del fondo."""
        pass

    @abstractmethod
    def adjust_emergency_fund_balance(self, delta: float) -> Any:
        """Incrementa o decrementa el saldo acumulado del fondo de emergencia."""
        pass


class IMarketCacheRepository(ABC):
    """Interfaz del repositorio de caché de datos de mercado."""

    @abstractmethod
    def get_market_cache(self, key: str) -> Optional[dict]:
        """Recupera datos cacheados válidos según su TTL."""
        pass

    @abstractmethod
    def set_market_cache(self, key: str, data: dict, ttl_hours: int = 24) -> Any:
        """Almacena datos en la caché de mercado con expiración configurable."""
        pass

    @abstractmethod
    def invalidate_market_cache(self, key: Optional[str] = None) -> None:
        """Invalida claves específicas o toda la caché de mercado."""
        pass


class IWatchlistRepository(ABC):
    """Interfaz del repositorio de lista de seguimiento (watchlist)."""

    @abstractmethod
    def get_watchlist(self) -> List[Any]:
        """Obtiene el listado completo de activos en la lista de seguimiento."""
        pass

    @abstractmethod
    def add_to_watchlist(self, item: Any) -> Any:
        """Añade o actualiza un activo en la lista de seguimiento."""
        pass

    @abstractmethod
    def remove_from_watchlist(self, ticker: str) -> bool:
        """Elimina un activo de la lista de seguimiento por su ticker."""
        pass


class ICopilotRepository(ABC):
    """Interfaz del repositorio de sesiones y mensajes del Copiloto Patrimonial."""

    @abstractmethod
    def create_copilot_session(self, title: Optional[str] = None) -> Any:
        """Crea una nueva sesión de conversación para el Copiloto."""
        pass

    @abstractmethod
    def get_copilot_sessions(self) -> List[Any]:
        """Obtiene el listado histórico de sesiones de conversación ordenadas por actividad reciente."""
        pass

    @abstractmethod
    def get_copilot_session(self, session_id: int) -> Optional[Any]:
        """Recupera una sesión específica junto con sus mensajes asociados."""
        pass

    @abstractmethod
    def delete_copilot_session(self, session_id: int) -> bool:
        """Elimina una sesión de conversación y todos sus mensajes en cascada."""
        pass

    @abstractmethod
    def add_copilot_message(
        self,
        session_id: int,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        """Registra un nuevo mensaje en la sesión indicada y actualiza su marca temporal."""
        pass

    @abstractmethod
    def get_copilot_messages(self, session_id: int) -> List[Any]:
        """Obtiene la lista cronológica de mensajes de una sesión."""
        pass


class IJointRepository(ABC):
    """Interfaz del repositorio para el espacio conjunto del hogar (Spec 010)."""

    @abstractmethod
    def get_joint_account(self) -> Optional[Any]:
        """Obtiene la cuenta conjunta configurada o None si no existe."""
        pass

    @abstractmethod
    def create_joint_account(self, setup_data: Any) -> Any:
        """Inicializa la cuenta conjunta y el catálogo base de necesidades comunes."""
        pass

    @abstractmethod
    def update_joint_account(self, update_data: Any) -> Optional[Any]:
        """Actualiza la configuración de la cuenta conjunta."""
        pass

    @abstractmethod
    def get_joint_categories(self) -> List[Any]:
        """Obtiene las categorías de necesidades del hogar."""
        pass

    @abstractmethod
    def get_joint_subcategories(self, category_id: Optional[int] = None) -> List[Any]:
        """Obtiene las subcategorías de necesidades del hogar."""
        pass

    @abstractmethod
    def get_joint_subcategory(self, subcategory_id: int) -> Optional[Any]:
        """Obtiene una subcategoría de necesidades por ID."""
        pass


    @abstractmethod
    def get_joint_sinking_funds(self, status: Optional[str] = None) -> List[Any]:
        """Obtiene el listado de huchas de amortización del hogar."""
        pass

    @abstractmethod
    def get_joint_sinking_fund(self, fund_id: int) -> Optional[Any]:
        """Obtiene una hucha de amortización específica."""
        pass

    @abstractmethod
    def create_joint_sinking_fund(self, fund: Any) -> Any:
        """Crea una nueva hucha de amortización."""
        pass

    @abstractmethod
    def update_joint_sinking_fund(self, fund_id: int, fund_update: Any) -> Optional[Any]:
        """Actualiza una hucha de amortización."""
        pass

    @abstractmethod
    def delete_joint_sinking_fund(self, fund_id: int, reallocate_to_fund_id: Optional[int] = None) -> bool:
        """Elimina una hucha de amortización reasignando su saldo si corresponde."""
        pass

    @abstractmethod
    def get_joint_transactions(self, year: Optional[int] = None, month: Optional[str] = None) -> List[Any]:
        """Obtiene las transacciones conjuntas registradas."""
        pass

    @abstractmethod
    def search_joint_transactions(
        self,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        query_text: Optional[str] = None,
        joint_subcategory_id: Optional[int] = None,
        paid_by: Optional[str] = None,
        settlement_status: Optional[str] = None,
        is_sinking_fund: Optional[bool] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
    ) -> List[Any]:
        """Búsqueda global y filtrado multicriterio de transacciones del hogar."""
        pass

    @abstractmethod
    def get_joint_transaction(self, tx_id: int) -> Optional[Any]:
        """Obtiene una transacción conjunta por su ID."""
        pass

    @abstractmethod
    def create_joint_transaction(self, tx: Any) -> Any:
        """Registra una transacción conjunta."""
        pass

    @abstractmethod
    def delete_joint_transaction(self, tx_id: int) -> Optional[str]:
        """Elimina una transacción conjunta retornando su UUID para el tombstone."""
        pass

    @abstractmethod
    def get_joint_contributions(self, year: Optional[int] = None, month: Optional[str] = None) -> List[Any]:
        """Obtiene las aportaciones mensuales efectuadas."""
        pass

    @abstractmethod
    def create_joint_contribution(self, contrib: Any) -> Any:
        """Registra una aportación mensual a la cuenta común."""
        pass

    @abstractmethod
    def reset_joint_account(self) -> bool:
        """Purga todas las entidades del espacio conjunto, devolviendo la base de datos al Estado Cero."""
        pass


class IRepository(
    ICategoryRepository,
    IBudgetRepository,
    ITransactionRepository,
    IEmergencyFundRepository,
    IMarketCacheRepository,
    IWatchlistRepository,
    ICopilotRepository,
    IJointRepository,
    ABC,
):
    """Interfaz unificada del repositorio del sistema."""
    pass



