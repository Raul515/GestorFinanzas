import logging
import os
from sqlalchemy import create_engine
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
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    from backend.domain.models import categories, budgets, transactions, emergency_fund, market_cache, watchlist, copilot, guidelines
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            cursor = conn.exec_driver_sql("PRAGMA table_info(transactions)")
            cols = [row[1] for row in cursor.fetchall()]
            if cols and "applied_strategy_id" not in cols:
                conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN applied_strategy_id INTEGER REFERENCES applied_guideline_strategies(id) ON DELETE CASCADE")
                conn.commit()

            cursor_strat = conn.exec_driver_sql("PRAGMA table_info(applied_guideline_strategies)")
            strat_cols = [row[1] for row in cursor_strat.fetchall()]
            if strat_cols and "split_config" not in strat_cols:
                conn.exec_driver_sql("ALTER TABLE applied_guideline_strategies ADD COLUMN split_config TEXT")
                conn.commit()
    except Exception as exc:
        logger.warning("Error comprobando/migrando columnas en SQLite: %s", exc)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
