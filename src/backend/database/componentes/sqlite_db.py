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
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
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

            cursor_acc = conn.exec_driver_sql("PRAGMA table_info(joint_accounts)")
            acc_cols = [row[1] for row in cursor_acc.fetchall()]
            if acc_cols and "custom_total_monthly_budget" not in acc_cols:
                conn.exec_driver_sql("ALTER TABLE joint_accounts ADD COLUMN custom_total_monthly_budget REAL DEFAULT 0.0")
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

            # Índices de alto rendimiento
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_transactions_subcategory_id ON transactions(subcategory_id)")
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_month_subcat ON monthly_budgets(month, subcategory_id)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_joint_transactions_account ON joint_transactions(joint_account_id)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_joint_transactions_settlement ON joint_transactions(settlement_status)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_joint_transactions_subcat ON joint_transactions(joint_subcategory_id)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_joint_transactions_fund ON joint_transactions(joint_sinking_fund_id)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_joint_contributions_personal_tx ON joint_monthly_contributions(personal_transaction_id)")
            conn.commit()

            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS joint_sinking_fund_transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid VARCHAR(36) UNIQUE NOT NULL,
                    joint_account_id INTEGER DEFAULT 1 REFERENCES joint_accounts(id),
                    source_fund_id INTEGER NOT NULL REFERENCES joint_sinking_funds(id) ON DELETE CASCADE,
                    target_fund_id INTEGER NOT NULL REFERENCES joint_sinking_funds(id) ON DELETE CASCADE,
                    amount FLOAT NOT NULL,
                    date DATE NOT NULL,
                    notes VARCHAR(255),
                    created_by_profile VARCHAR(20) DEFAULT 'MEMBER_A',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT ck_joint_transfer_amount_positive CHECK (amount > 0),
                    CONSTRAINT ck_joint_transfer_diff_funds CHECK (source_fund_id != target_fund_id)
                )
            """)
            conn.commit()

            # Asegurar subcategoría de reintegros por cierre de huchas conjuntas bajo 'Ingresos Netos'
            cur_cat = conn.exec_driver_sql("SELECT id FROM categories WHERE type = 'ingreso' OR name = 'Ingresos Netos' LIMIT 1")
            row_cat = cur_cat.fetchone()
            if row_cat:
                income_cat_id = row_cat[0]
                # Si existe con el nombre antiguo 'Reintegro Hucha Conjunta', actualizar nombre
                conn.exec_driver_sql(
                    "UPDATE subcategories SET name = 'Reintegros por Cierres de Huchas Conjuntas' "
                    "WHERE name IN ('Reintegro Hucha Conjunta', 'Reintegros por cierre de huchas conjuntas') "
                    "AND category_id = ?",
                    (income_cat_id,)
                )
                # Verificar si ya existe 'Reintegros por Cierres de Huchas Conjuntas'
                cur_sub = conn.exec_driver_sql(
                    "SELECT id FROM subcategories WHERE name = 'Reintegros por Cierres de Huchas Conjuntas' AND category_id = ?",
                    (income_cat_id,)
                )
                if not cur_sub.fetchone():
                    conn.exec_driver_sql(
                        "INSERT INTO subcategories (name, category_id) VALUES ('Reintegros por Cierres de Huchas Conjuntas', ?)",
                        (income_cat_id,)
                    )
                conn.commit()
    except Exception as exc:
        logger.warning("Error comprobando/migrando columnas en SQLite: %s", exc)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
