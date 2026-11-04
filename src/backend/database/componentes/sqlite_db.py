import logging
import os
from sqlite3 import Connection as SQLite3Connection
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from backend.domain.models.base import Base

logger = logging.getLogger(__name__)

# Ensure data directory exists
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "finanzas.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Activa el soporte de claves foráneas y restricciones referenciales en SQLite."""
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    from backend.domain.models import categories, budgets, transactions, emergency_fund, market_cache, watchlist, copilot, guidelines, joint, backup
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            cursor = conn.exec_driver_sql("PRAGMA table_info(transactions)")
            cols = [row[1] for row in cursor.fetchall()]
            if cols and "applied_strategy_id" not in cols:
                conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN applied_strategy_id INTEGER REFERENCES applied_guideline_strategies(id) ON DELETE CASCADE")
                conn.commit()
            if cols and "joint_contribution_uuid" not in cols:
                conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN joint_contribution_uuid TEXT")
                conn.commit()

            cursor_strat = conn.exec_driver_sql("PRAGMA table_info(applied_guideline_strategies)")
            strat_cols = [row[1] for row in cursor_strat.fetchall()]
            if strat_cols and "split_config" not in strat_cols:
                conn.exec_driver_sql("ALTER TABLE applied_guideline_strategies ADD COLUMN split_config TEXT")
                conn.commit()

            cursor_j_tx = conn.exec_driver_sql("PRAGMA table_info(joint_transactions)")
            j_tx_cols = [row[1] for row in cursor_j_tx.fetchall()]
            if j_tx_cols and "sinking_fund_deduction" not in j_tx_cols:
                conn.exec_driver_sql("ALTER TABLE joint_transactions ADD COLUMN sinking_fund_deduction REAL DEFAULT 0.0")
                conn.commit()
            if j_tx_cols and "paid_by" not in j_tx_cols:
                conn.exec_driver_sql("ALTER TABLE joint_transactions ADD COLUMN paid_by TEXT DEFAULT 'COMMON'")
                conn.commit()
            if j_tx_cols and "settlement_mechanism" not in j_tx_cols:
                conn.exec_driver_sql("ALTER TABLE joint_transactions ADD COLUMN settlement_mechanism TEXT DEFAULT 'COMMON_REIMBURSEMENT'")
                conn.commit()
            if j_tx_cols and "settlement_status" not in j_tx_cols:
                conn.exec_driver_sql("ALTER TABLE joint_transactions ADD COLUMN settlement_status TEXT DEFAULT 'SETTLED'")
                conn.commit()
            if j_tx_cols and "settled_at" not in j_tx_cols:
                conn.exec_driver_sql("ALTER TABLE joint_transactions ADD COLUMN settled_at TIMESTAMP")
                conn.commit()

            cursor_j_cb = conn.exec_driver_sql("PRAGMA table_info(joint_monthly_contributions)")
            j_cb_cols = [row[1] for row in cursor_j_cb.fetchall()]
            if j_cb_cols and "uuid" not in j_cb_cols:
                conn.exec_driver_sql("ALTER TABLE joint_monthly_contributions ADD COLUMN uuid TEXT")
                conn.commit()
            if j_cb_cols and "personal_transaction_id" not in j_cb_cols:
                conn.exec_driver_sql("ALTER TABLE joint_monthly_contributions ADD COLUMN personal_transaction_id INTEGER")
                conn.commit()
            if j_cb_cols and "sinking_fund_allocations" not in j_cb_cols:
                conn.exec_driver_sql("ALTER TABLE joint_monthly_contributions ADD COLUMN sinking_fund_allocations TEXT")
                conn.commit()
    except Exception as exc:
        logger.warning("Error comprobando/migrando columnas en SQLite: %s", exc)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
