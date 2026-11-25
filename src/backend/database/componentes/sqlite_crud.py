from sqlalchemy.orm import Session

from backend.database.componentes.joint_repo import JointAccountMixin
from backend.database.componentes.market_repo import MarketCopilotMixin
from backend.database.componentes.personal_repo import PersonalFinanceMixin
from backend.database.interfaz.db_interface import IRepository


class SQLiteRepository(PersonalFinanceMixin, MarketCopilotMixin, JointAccountMixin, IRepository):
    """Implementación SQLite compuesta del repositorio central desacoplado de base de datos."""

    def __init__(self, db: Session):
        self.db = db
