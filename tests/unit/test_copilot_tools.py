import os
import json
import pytest
from sqlalchemy.orm import Session
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.schemas.watchlist import WatchlistCreate
from backend.services.copilot_tools import (
    COPILOT_TOOL_DEFINITIONS,
    execute_copilot_tool,
    get_cached_deepdive,
    get_cached_macro_overview,
    get_financial_profile,
    get_watchlist_items,
    search_local_knowledge,
)


def test_get_financial_profile_emergency_fund_undercovered(
    db_session: Session, seed_data: dict[str, int]
):
    """Verifica que si el fondo no cubre 3 meses, se bloqueen inversiones con riesgo y se emita la advertencia constitucional."""
    repo = SQLiteRepository(db_session)

    # Configurar presupuesto BASE de Necesidades Básicas en 1,000 €/mes
    # y saldo actual del fondo en 1,500 € (cubre 1.5 meses < 3 meses mínimos)
    from backend.domain.models.budgets import MonthlyBudget
    b1 = MonthlyBudget(
        month="BASE",
        subcategory_id=seed_data["sub_alquiler_id"],
        amount=1000.0,
    )
    db_session.add(b1)
    db_session.commit()

    repo.update_emergency_fund(target_months=3, current_balance=1500.0)

    profile = get_financial_profile(repo=repo, db=db_session, month="BASE")

    assert profile["risk_investment_allowed"] is False
    assert profile["constitutional_warning"] is not None
    assert "ADVERTENCIA CONSTITUCIONAL" in profile["constitutional_warning"]
    assert profile["emergency_fund"]["coverage_months"] == 1.5
    assert profile["emergency_fund"]["gap_to_target"] == 1500.0
    assert profile["emergency_fund"]["is_completed"] is False


def test_get_financial_profile_emergency_fund_covered(
    db_session: Session, seed_data: dict[str, int]
):
    """Verifica que con el fondo cubierto a >= 3 meses se autoricen inversiones con riesgo."""
    repo = SQLiteRepository(db_session)

    from backend.domain.models.budgets import MonthlyBudget
    b1 = MonthlyBudget(
        month="BASE",
        subcategory_id=seed_data["sub_alquiler_id"],
        amount=1000.0,
    )
    b_sal = MonthlyBudget(
        month="BASE",
        subcategory_id=seed_data["sub_salario_id"],
        amount=2500.0,
    )
    db_session.add_all([b1, b_sal])
    db_session.commit()

    # Fondo cubierto con 4,000 € frente a meta de 3,750 € (1,250 €/mes x 3 = 3,750 €)
    repo.update_emergency_fund(target_months=3, current_balance=4000.0)

    profile = get_financial_profile(repo=repo, db=db_session, month="BASE")

    assert profile["risk_investment_allowed"] is True
    assert profile["constitutional_warning"] is None
    assert profile["emergency_fund"]["coverage_months"] == 3.2
    assert profile["emergency_fund"]["is_completed"] is True
    assert profile["needs_50pct"]["target_cap"] == 1250.0  # 50% de 2,500 €


def test_get_watchlist_items_empty_and_populated(db_session: Session):
    """Verifica la recuperación de la Watchlist vacía y con elementos."""
    repo = SQLiteRepository(db_session)

    # Vacía
    res_empty = get_watchlist_items(repo=repo)
    assert res_empty["count"] == 0
    assert len(res_empty["items"]) == 0
    assert "vacía" in res_empty["message"]

    # Con elementos
    repo.add_to_watchlist(
        WatchlistCreate(
            ticker="ITX.MC",
            name="Inditex",
            sector="Consumer Cyclical",
            price_at_addition=45.50,
            notes="Calidad a buen precio",
        )
    )

    res_populated = get_watchlist_items(repo=repo)
    assert res_populated["count"] == 1
    assert res_populated["items"][0]["ticker"] == "ITX.MC"
    assert res_populated["items"][0]["price_at_addition"] == 45.50


def test_get_cached_deepdive_missing_and_found(db_session: Session):
    """Verifica la lectura del diagnóstico contable en caché de 24h."""
    repo = SQLiteRepository(db_session)

    # Caso no en caché
    res_missing = get_cached_deepdive(repo=repo, ticker="AAPL")
    assert res_missing["found_in_cache"] is False
    assert "No existe un análisis fundamental" in res_missing["message"]

    # Guardar en caché
    mock_deepdive = {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "current_price": 220.0,
        "currency": "USD",
        "sector": "Technology",
        "piotroski": {
            "total_score": 8,
            "max_score": 9,
            "rating": "Excelente",
        },
        "fcf_metrics": {
            "fcf_yield": 4.1,
            "fcf_conversion_ratio": 1.05,
            "roe": 140.0,
            "roic": 45.0,
            "has_moat": True,
        },
        "quality_value_report": {
            "quadrant": "Quality Value",
            "summary_thesis": "Foso defensivo masivo en ecosistema iOS.",
            "six_ingredients": {"moat": "Altos costes de cambio"},
            "bearish_risks": ["Riesgo antimonopolio", "Saturación de hardware"],
            "target_irr_entry_zone": "190 - 200 $",
        },
        "updated_at": "2026-10-27T10:00:00",
    }
    repo.set_market_cache(key="deepdive_AAPL", data=mock_deepdive, ttl_hours=24)

    # Caso en caché
    res_found = get_cached_deepdive(repo=repo, ticker="aapl")
    assert res_found["found_in_cache"] is True
    assert res_found["ticker"] == "AAPL"
    assert res_found["piotroski_f_score"]["score"] == 8
    assert res_found["quality_value_thesis"]["quadrant"] == "Quality Value"
    assert len(res_found["quality_value_thesis"]["bearish_risks"]) == 2


def test_get_cached_macro_overview_missing_and_found(db_session: Session):
    """Verifica la consulta de indicadores macroeconómicos cacheados."""
    repo = SQLiteRepository(db_session)

    # No en caché
    res_missing = get_cached_macro_overview(repo=repo)
    assert res_missing["found_in_cache"] is False

    # Guardar en caché
    mock_macro = {
        "updated_at": "2026-10-27T10:00:00",
        "indicators": [
            {"symbol": "^IBEX", "name": "IBEX 35", "price": 11800.0, "change_pct": 0.45},
            {"symbol": "ES10Y", "name": "Bono España 10A", "price": 2.95, "change_pct": -0.02},
            {"symbol": "RISK_PREMIUM_ES_DE", "name": "Prima de Riesgo", "price": 72.0, "change_pct": 0.0},
        ],
    }
    repo.set_market_cache(key="macro_overview_indicators", data=mock_macro, ttl_hours=24)

    res_found = get_cached_macro_overview(repo=repo)
    assert res_found["found_in_cache"] is True
    assert len(res_found["indicators"]) == 3
    assert res_found["indicators"][2]["name"] == "Prima de Riesgo"


def test_search_local_knowledge(tmp_path):
    """Verifica la búsqueda de fragmentos en archivos de conocimiento locales."""
    k_dir = tmp_path / "knowledge"
    k_dir.mkdir()

    # Archivo de prueba
    note_file = k_dir / "tesis_inditex.md"
    note_file.write_text(
        "# Tesis Inditex\n"
        "Inditex tiene un ciclo de caja negativo y rotación veloz.\n"
        "Su ventaja en costes de escala le confiere un foso defensivo duradero.\n",
        encoding="utf-8",
    )

    # Búsqueda con resultado
    res_match = search_local_knowledge(query="ciclo de caja", knowledge_dir=str(k_dir))
    assert res_match["count"] == 1
    assert "tesis_inditex.md" in res_match["matches"][0]["file"]
    assert "ciclo de caja" in res_match["matches"][0]["excerpt"].lower()

    # Búsqueda sin resultado
    res_none = search_local_knowledge(query="criptomonedas bitcoin", knowledge_dir=str(k_dir))
    assert res_none["count"] == 0
    assert len(res_none["matches"]) == 0


def test_execute_copilot_tool_router(db_session: Session):
    """Verifica que el despachador execute_copilot_tool enrute correctamente las herramientas."""
    repo = SQLiteRepository(db_session)

    # Herramienta get_watchlist_items
    resp_watch = execute_copilot_tool("get_watchlist_items", {}, repo=repo)
    assert "items" in resp_watch

    # Herramienta get_cached_deepdive
    resp_dd = execute_copilot_tool("get_cached_deepdive", {"ticker": "MSFT"}, repo=repo)
    assert resp_dd["found_in_cache"] is False

    # Herramienta no existente
    resp_unknown = execute_copilot_tool("tool_inexistente", {}, repo=repo)
    assert resp_unknown["error"] is True
    assert "no reconocida" in resp_unknown["message"]


def test_copilot_tool_definitions_integrity():
    """Verifica que las definiciones de esquemas de herramientas cumplan el estándar de Function Calling."""
    assert len(COPILOT_TOOL_DEFINITIONS) == 5
    names = [t["name"] for t in COPILOT_TOOL_DEFINITIONS]
    assert "get_financial_profile" in names
    assert "get_watchlist_items" in names
    assert "get_cached_deepdive" in names
    assert "get_cached_macro_overview" in names
    assert "search_local_knowledge" in names

    for tool in COPILOT_TOOL_DEFINITIONS:
        assert "description" in tool
        assert "parameters" in tool
        params = tool["parameters"]
        assert isinstance(params, dict)
        assert params.get("type") == "object"
