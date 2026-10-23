import pytest
from backend.services.financial_calculator import (
    calculate_category_totals,
    calculate_503020_percentages,
    calculate_annual_metrics,
    get_monthly_needs_budget,
)


def test_calculate_category_totals_503020_derivation():
    """Verifies that 50/30/20 budget ceilings are mathematically derived from budgeted income."""
    categorias = [
        {"id": 1, "nombre": "Ingresos Netos", "tipo": "ingreso"},
        {"id": 2, "nombre": "Necesidades Básicas", "tipo": "gasto"},
        {"id": 3, "nombre": "Deseos", "tipo": "gasto"},
        {"id": 4, "nombre": "Ahorro e Inversión", "tipo": "ahorro"},
    ]
    subcategorias = [
        {"id": 10, "categoria_id": 1, "nombre": "Nómina"},
        {"id": 20, "categoria_id": 2, "nombre": "Alquiler"},
        {"id": 30, "categoria_id": 3, "nombre": "Restaurantes"},
        {"id": 40, "categoria_id": 4, "nombre": "Fondo de emergencia"},
    ]
    # Income budget of 2000.0
    presupuestos = [
        {"subcategoria_id": 10, "cantidad": 2000.0},
        {"subcategoria_id": 20, "cantidad": 800.0},
        {"subcategoria_id": 30, "cantidad": 300.0},
        {"subcategoria_id": 40, "cantidad": 200.0},
    ]
    transacciones = []

    totals = calculate_category_totals(
        categorias=categorias,
        todas_subcats=subcategorias,
        presupuestos_m=presupuestos,
        transacciones_m=transacciones,
        ingresos_name="Ingresos Netos",
        necesidades_name="Necesidades Básicas",
        deseos_name="Deseos",
        ahorro_name="Ahorro e Inversión",
    )

    # Ingresos budget = 2000.0
    assert totals["Ingresos Netos"]["presupuesto"] == 2000.0
    # Needs = 50% of 2000 = 1000.0
    assert totals["Necesidades Básicas"]["presupuesto"] == 1000.0
    # Wants = 30% of 2000 = 600.0
    assert totals["Deseos"]["presupuesto"] == 600.0
    # Savings = 20% of 2000 = 400.0
    assert totals["Ahorro e Inversión"]["presupuesto"] == 400.0


def test_calculate_503020_percentages_standard():
    """Verifies percentage calculations and unassigned funds tracking."""
    # Income: 2000, Needs: 1000 (50%), Wants: 500 (25%), Savings: 300 (15%), Unassigned: 200 (10%)
    pct_nec, pct_des, pct_aho, pct_sin, sin_asignar = calculate_503020_percentages(
        real_ing=2000.0,
        real_nec=1000.0,
        real_des=500.0,
        real_aho=300.0,
    )
    assert pct_nec == pytest.approx(50.0)
    assert pct_des == pytest.approx(25.0)
    assert pct_aho == pytest.approx(15.0)
    assert pct_sin == pytest.approx(10.0)
    assert sin_asignar == pytest.approx(200.0)


def test_calculate_503020_percentages_zero_income():
    """Verifies edge case: zero income should yield 0.0 percentages without ZeroDivisionError."""
    pct_nec, pct_des, pct_aho, pct_sin, sin_asignar = calculate_503020_percentages(
        real_ing=0.0,
        real_nec=500.0,
        real_des=200.0,
        real_aho=100.0,
    )
    assert pct_nec == 0.0
    assert pct_des == 0.0
    assert pct_aho == 0.0
    assert pct_sin == 0.0
    assert sin_asignar == 0.0


def test_calculate_503020_percentages_overspending():
    """Verifies that unassigned amount cannot be negative (clamped at 0.0)."""
    # Total expenses (2500) exceed income (2000)
    _, _, _, pct_sin, sin_asignar = calculate_503020_percentages(
        real_ing=2000.0,
        real_nec=1500.0,
        real_des=700.0,
        real_aho=300.0,
    )
    assert sin_asignar == 0.0
    assert pct_sin == 0.0


def test_calculate_annual_metrics():
    """Verifies annual accumulated metrics and target deviations."""
    # Synthetic 12 months data
    anual_data = {}
    for m in range(1, 13):
        anual_data[m] = {
            "Ingresos Netos": {"real": 2000.0},
            "Necesidades Básicas": {"real": 1000.0},
            "Deseos": {"real": 600.0},
            "Ahorro e Inversión": {"real": 400.0},
        }

    metrics = calculate_annual_metrics(
        anual_data=anual_data,
        ingresos_name="Ingresos Netos",
        necesidades_name="Necesidades Básicas",
        deseos_name="Deseos",
        ahorro_name="Ahorro e Inversión",
    )

    assert metrics["ingresos_anual_real"] == 24000.0
    assert metrics["nec_anual_real"] == 12000.0
    assert metrics["des_anual_real"] == 7200.0
    assert metrics["aho_anual_real"] == 4800.0
    assert metrics["pct_nec_real"] == pytest.approx(50.0)
    assert metrics["pct_des_real"] == pytest.approx(30.0)
    assert metrics["pct_aho_real"] == pytest.approx(20.0)
    # Deviations from 50/30/20 target should be 0.0
    assert metrics["desv_nec"] == pytest.approx(0.0)
    assert metrics["desv_des"] == pytest.approx(0.0)
    assert metrics["desv_aho"] == pytest.approx(0.0)


def test_get_monthly_needs_budget():
    """Verifies extraction of total budgeted amount for basic needs category."""
    subcats = [
        {"id": 1, "categoria_id": 10, "nombre": "Alquiler"},
        {"id": 2, "categoria_id": 10, "nombre": "Supermercado"},
        {"id": 3, "categoria_id": 20, "nombre": "Cine"},
    ]
    presupuestos = [
        {"subcategoria_id": 1, "cantidad": 800.0},
        {"subcategoria_id": 2, "cantidad": 350.0},
        {"subcategoria_id": 3, "cantidad": 100.0},
    ]

    total_needs = get_monthly_needs_budget(
        presupuestos=presupuestos,
        subcategorias=subcats,
        categoria_necesidades_id=10,
    )
    # 800 + 350 = 1150.0 (cine belongs to cat 20, excluded)
    assert total_needs == 1150.0
