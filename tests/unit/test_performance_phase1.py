"""
Pruebas automatizadas para la Fase 1 de la Especificación 014:
Capa de Red (requests.Session) y Base de Datos SQLite (PRAGMAs, Bulk Atómico, Between e Índices).
"""

import datetime
import pytest
from sqlalchemy import create_engine, event, text, Table, Index
from sqlalchemy.orm import sessionmaker
from sqlite3 import Connection as SQLite3Connection
from requests.adapters import HTTPAdapter

from backend.domain.models.base import Base
from backend.domain.models import categories, budgets, transactions, joint
from backend.domain.schemas import budgets as pres_schemas, transactions as trans_schemas
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.componentes.sqlite_db import set_sqlite_pragma
from frontend import api_client


def test_api_client_session_configured():
    """RF-1: Verifica que api_client utilice una sesión requests persistente con pool."""
    session = api_client.get_session()
    assert session is not None
    assert "http://" in session.adapters
    assert "https://" in session.adapters
    adapter = session.adapters["http://"]
    assert isinstance(adapter, HTTPAdapter)
    assert adapter._pool_connections == 20
    assert adapter._pool_maxsize == 30


def test_sqlite_pragmas_applied():
    """RF-2: Verifica que los 4 pragmas de alto rendimiento se apliquen en conexiones SQLite."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    event.listen(test_engine, "connect", set_sqlite_pragma)

    with test_engine.connect() as conn:
        fk = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
        assert fk == 1

        # En bases de datos en memoria SQLite reporta 'memory', pero para ficheros WAL reporta 'wal'
        # Verificamos cache_size, temp_store y synchronous
        synch = conn.exec_driver_sql("PRAGMA synchronous").scalar()
        # synchronous: 1 representa NORMAL
        assert synch in (1, 2)

        cache = conn.exec_driver_sql("PRAGMA cache_size").scalar()
        assert cache == -64000

        temp_st = conn.exec_driver_sql("PRAGMA temp_store").scalar()
        # 2 representa MEMORY
        assert temp_st == 2


def test_save_budgets_bulk_atomic_execution():
    """RF-3: Verifica que save_budgets_bulk inserte y actualice en bloque atómicamente."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSession()

    try:
        repo = SQLiteRepository(db)

        # Crear categoría y subcategorías de prueba
        cat = categories.Category(name="Necesidades", type="GASTO")
        db.add(cat)
        db.commit()

        sub1 = categories.Subcategory(name="Alquiler", category_id=cat.id)
        sub2 = categories.Subcategory(name="Supermercado", category_id=cat.id)
        db.add_all([sub1, sub2])
        db.commit()

        # 1. Guardar lote inicial
        batch_1 = [
            {"month": "2026-03", "subcategory_id": sub1.id, "amount": 800.0},
            {"month": "2026-03", "subcategory_id": sub2.id, "amount": 350.0},
        ]
        saved_1 = repo.save_budgets_bulk(batch_1)
        assert len(saved_1) == 2
        assert saved_1[0].amount == 800.0
        assert saved_1[1].amount == 350.0

        # 2. Actualizar una subcategoría existente e insertar una nueva en el mismo lote
        sub3 = categories.Subcategory(name="Luz", category_id=cat.id)
        db.add(sub3)
        db.commit()

        batch_2 = [
            {"month": "2026-03", "subcategory_id": sub1.id, "amount": 850.0},  # update
            {"month": "2026-03", "subcategory_id": sub3.id, "amount": 75.0},   # insert
        ]
        saved_2 = repo.save_budgets_bulk(batch_2)
        assert len(saved_2) == 2

        # Comprobar estado final en base de datos
        all_budgets = repo.get_budgets("2026-03")
        amounts_by_sub = {b.subcategory_id: b.amount for b in all_budgets}
        assert amounts_by_sub[sub1.id] == 850.0
        assert amounts_by_sub[sub2.id] == 350.0
        assert amounts_by_sub[sub3.id] == 75.0
    finally:
        db.close()


def test_get_transactions_between_date_filter():
    """RF-4: Verifica que get_transactions filtre fechas con between sin omitir días límite."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSession()

    try:
        repo = SQLiteRepository(db)

        cat = categories.Category(name="TestCat", type="GASTO")
        db.add(cat)
        db.commit()
        sub = categories.Subcategory(name="TestSub", category_id=cat.id)
        db.add(sub)
        db.commit()

        # Insertar transacciones: día 1, día 15, último día (28 feb), y otro mes (1 marzo)
        tx_feb_1 = transactions.Transaction(date=datetime.date(2026, 2, 1), subcategory_id=sub.id, amount=10.0, description="Día 1")
        tx_feb_15 = transactions.Transaction(date=datetime.date(2026, 2, 15), subcategory_id=sub.id, amount=20.0, description="Día 15")
        tx_feb_28 = transactions.Transaction(date=datetime.date(2026, 2, 28), subcategory_id=sub.id, amount=30.0, description="Día 28")
        tx_mar_1 = transactions.Transaction(date=datetime.date(2026, 3, 1), subcategory_id=sub.id, amount=40.0, description="Día 1 Mar")
        db.add_all([tx_feb_1, tx_feb_15, tx_feb_28, tx_mar_1])
        db.commit()

        feb_txs = repo.get_transactions("2026-02")
        assert len(feb_txs) == 3
        descriptions = [t.description for t in feb_txs]
        assert "Día 1" in descriptions
        assert "Día 15" in descriptions
        assert "Día 28" in descriptions
        assert "Día 1 Mar" not in descriptions

        mar_txs = repo.get_transactions("2026-03")
        assert len(mar_txs) == 1
        assert mar_txs[0].description == "Día 1 Mar"
    finally:
        db.close()


def test_get_joint_transactions_date_filter():
    """RF-4: Verifica que get_joint_transactions filtre por año y por mes usando rangos indexables."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSession()

    try:
        repo = SQLiteRepository(db)

        # Crear cuenta conjunta
        acc = joint.JointAccount(household_name="Hogar Test", member_a_name="A", member_b_name="B")
        db.add(acc)
        db.commit()

        # Gastos en 2026-01, 2026-02 y 2025-12
        tx1 = joint.JointTransaction(joint_account_id=1, date=datetime.date(2026, 1, 15), amount=50.0, description="Enero 2026", created_by_profile="MEMBER_A")
        tx2 = joint.JointTransaction(joint_account_id=1, date=datetime.date(2026, 2, 20), amount=70.0, description="Febrero 2026", created_by_profile="MEMBER_A")
        tx3 = joint.JointTransaction(joint_account_id=1, date=datetime.date(2025, 12, 31), amount=90.0, description="Diciembre 2025", created_by_profile="MEMBER_A")
        db.add_all([tx1, tx2, tx3])
        db.commit()

        # Filtrar solo 2026
        txs_2026 = repo.get_joint_transactions(year=2026)
        assert len(txs_2026) == 2
        assert all(t.date.year == 2026 for t in txs_2026)

        # Filtrar mes específico 2026-02
        txs_feb_2026 = repo.get_joint_transactions(year=2026, month="2026-02")
        assert len(txs_feb_2026) == 1
        assert txs_feb_2026[0].description == "Febrero 2026"
    finally:
        db.close()


def test_orm_indexes_declared():
    """RF-5: Verifica que los índices declarados estén presentes en las tablas SQLAlchemy."""
    budget_table = budgets.MonthlyBudget.__table__
    assert isinstance(budget_table, Table)
    budget_indexes: dict[str, Index] = {str(idx.name): idx for idx in budget_table.indexes if idx.name}
    assert "idx_budget_month_subcat" in budget_indexes
    assert budget_indexes["idx_budget_month_subcat"].unique is True

    # Transaction subcategory_id index
    tx_table = transactions.Transaction.__table__
    assert isinstance(tx_table, Table)
    tx_subcat_col = tx_table.columns["subcategory_id"]
    assert tx_subcat_col.index is True

    # JointTransaction settlement_status index
    j_tx_table = joint.JointTransaction.__table__
    assert isinstance(j_tx_table, Table)
    j_tx_settle_col = j_tx_table.columns["settlement_status"]
    assert j_tx_settle_col.index is True

