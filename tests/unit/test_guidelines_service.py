"""
Pruebas unitarias para el servicio de pautas deterministas de gestión y compensación presupuestaria (Spec 008).
Valida todos los escenarios mensuales, jerarquías de absorción con cifras reales y diagnósticos anuales.
"""

import pytest
from backend.domain.schemas.guidelines import (
    AnnualScenarioType,
    GuidelineSeverity,
    MonthlyScenarioType,
)
from backend.services.guidelines_service import (
    evaluate_annual_guidelines,
    evaluate_monthly_guidelines,
)


# ==========================================
# PRUEBAS MENSUALES
# ==========================================


def test_needs_surplus_incomplete_emergency_fund():
    """Valida el cálculo del excedente en Necesidades cuando el Fondo de Emergencia está en construcción."""
    # Presupuesto: Ingreso 1350€, Meta Necesidades 675€ (50%). Real Necesidades: 100€ -> Excedente 575€
    safety_status = {
        "current_balance": 200.0,
        "target_amount": 1200.0,
        "coverage_months": 1.0,
        "target_months": 3.0,
        "is_completed": False,
        "gap": 1000.0,
    }

    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=1350.0,
        budget_income=1350.0,
        real_needs=100.0,
        real_wants=405.0,
        real_savings=270.0,
        safety_status=safety_status,
    )

    assert report.month_key == "2026-10"
    assert report.real_income == 1350.0
    assert report.real_needs == 100.0

    # Buscar pauta de excedente
    surplus_guidelines = [
        g for g in report.guidelines if g.scenario_type == MonthlyScenarioType.NEEDS_SURPLUS
    ]
    assert len(surplus_guidelines) == 1
    g = surplus_guidelines[0]

    assert g.delta_amount == 575.0
    assert g.severity == GuidelineSeverity.INFO
    assert len(g.strategies) == 3

    # Estrategia 1: FIRE (Fondo en construcción)
    strat_fire = g.strategies[0]
    assert "FIRE" in strat_fire.name
    assert strat_fire.allocation_amount == 575.0
    assert "Fondo en Construcción" in strat_fire.breakdown_items[0]
    assert "1,000.00 €" in strat_fire.breakdown_items[0]

    # Estrategia 3: 80/20
    strat_hybrid = g.strategies[2]
    assert "80/20" in strat_hybrid.name
    assert "460.00 €" in strat_hybrid.breakdown_items[0]
    assert "115.00 €" in strat_hybrid.breakdown_items[1]

    # Regla Fondo de Emergencia
    assert "NO se retira" in g.emergency_fund_rule
    assert len(report.synoptic_table) >= 1


def test_needs_surplus_completed_emergency_fund():
    """Valida el cálculo del excedente en Necesidades cuando el Fondo de Emergencia ya está completo."""
    safety_status = {
        "current_balance": 3000.0,
        "target_amount": 2000.0,
        "coverage_months": 4.5,
        "target_months": 3.0,
        "is_completed": True,
        "gap": 0.0,
    }

    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=1350.0,
        budget_income=1350.0,
        real_needs=100.0,
        real_wants=405.0,
        real_savings=270.0,
        safety_status=safety_status,
    )

    g = [g for g in report.guidelines if g.scenario_type == MonthlyScenarioType.NEEDS_SURPLUS][0]
    strat_fire = g.strategies[0]
    assert "Fondo Blindado" in strat_fire.breakdown_items[0]
    assert "fondos indexados" in strat_fire.breakdown_items[0]


def test_needs_deficit_absorbed_from_wants():
    """Valida que un exceso en Necesidades se absorba primero de Deseos sin tocar Fondo de Emergencia."""
    # Ingreso: 1350€, Meta Necesidades: 675€. Real: 800€ -> Exceso: 125€
    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=1350.0,
        budget_income=1350.0,
        real_needs=800.0,
        real_wants=405.0,
        real_savings=145.0,
        safety_status={"coverage_months": 3.0, "is_completed": True},
    )

    deficit_guidelines = [
        g for g in report.guidelines if g.scenario_type == MonthlyScenarioType.NEEDS_DEFICIT
    ]
    assert len(deficit_guidelines) == 1
    g = deficit_guidelines[0]

    assert g.delta_amount == 125.0
    assert g.severity == GuidelineSeverity.ALERT
    assert "NO" in g.emergency_fund_rule

    # Jerarquía de compensación
    assert len(g.compensation_hierarchy) == 3
    step1 = g.compensation_hierarchy[0]
    assert step1.source_block == "Deseos (30%)"
    assert step1.amount == 125.0
    assert step1.can_touch_emergency_fund is False

    step2 = g.compensation_hierarchy[1]
    assert step2.amount == 0.0  # Cubierto al 100% con Deseos

    step3 = g.compensation_hierarchy[2]
    assert step3.can_touch_emergency_fund is True
    assert "catástrofe" in step3.action_text.lower() or "urgencia" in step3.action_text.lower()


def test_needs_deficit_exceeding_wants():
    """Valida la absorción en 2ª línea (Ahorro del mes) cuando Deseos no alcanza para cubrir el exceso."""
    # Ingreso: 1000€, Meta Nec: 500€. Real Nec: 850€ (exceso 350€). Real Deseos: 200€
    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=1000.0,
        budget_income=1000.0,
        real_needs=850.0,
        real_wants=200.0,
        real_savings=0.0,
    )

    g = [g for g in report.guidelines if g.scenario_type == MonthlyScenarioType.NEEDS_DEFICIT][0]
    assert g.delta_amount == 350.0

    step1 = g.compensation_hierarchy[0]
    assert step1.amount == 200.0  # Consume todo Deseos disponible

    step2 = g.compensation_hierarchy[1]
    assert step2.amount == 150.0  # El remanente de 150€ va al ahorro


def test_wants_deficit_autocorrection():
    """Valida que el sobregasto en Deseos deduzca del Ahorro y prohíba tajantemente el Fondo de Emergencia."""
    # Ingreso: 1350€, Meta Deseos: 405€ (30%). Real: 450€ -> Exceso: 45€
    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=1350.0,
        budget_income=1350.0,
        real_needs=675.0,
        real_wants=450.0,
        real_savings=225.0,
    )

    wants_guidelines = [
        g for g in report.guidelines if g.scenario_type == MonthlyScenarioType.WANTS_DEFICIT
    ]
    assert len(wants_guidelines) == 1
    g = wants_guidelines[0]

    assert g.delta_amount == 45.0
    assert g.severity == GuidelineSeverity.WARNING
    assert "JAMÁS" in g.emergency_fund_rule

    # Compensación
    assert g.compensation_hierarchy[0].amount == 45.0
    assert g.compensation_hierarchy[0].can_touch_emergency_fund is False

    # Estrategias de corrección
    strat_a = g.strategies[0]
    assert "Ajuste Compensatorio" in strat_a.name
    assert "45.00 €" in strat_a.breakdown_items[0]


def test_income_shortfall():
    """Valida la activación del protocolo de contención ante caída de ingresos > 5%."""
    # Presupuestado: 2000€, Real: 1500€ -> Caída de 500€ (-25%)
    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=1500.0,
        budget_income=2000.0,
        real_needs=750.0,
        real_wants=450.0,
        real_savings=300.0,
    )

    shortfall_guidelines = [
        g for g in report.guidelines if g.scenario_type == MonthlyScenarioType.INCOME_SHORTFALL
    ]
    assert len(shortfall_guidelines) == 1
    g = shortfall_guidelines[0]
    assert g.delta_amount == 500.0
    assert g.severity == GuidelineSeverity.ALERT
    assert "CONDICIONAL" in g.emergency_fund_rule


def test_extraordinary_income():
    """Valida la recomendación de distribución de bonus o paga extra (> 5% de ingreso extra)."""
    # Presupuestado: 1500€, Real: 2500€ -> Extra de 1000€ (+66.7%)
    safety_status = {"gap": 400.0, "is_completed": False}
    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=2500.0,
        budget_income=1500.0,
        real_needs=750.0,
        real_wants=500.0,
        real_savings=1250.0,
        safety_status=safety_status,
    )

    extra_guidelines = [
        g for g in report.guidelines if g.scenario_type == MonthlyScenarioType.EXTRAORDINARY_INCOME
    ]
    assert len(extra_guidelines) == 1
    g = extra_guidelines[0]
    assert g.delta_amount == 1000.0

    # Verifica reparto de bonus
    strat_ef = g.strategies[0]
    assert "400.00 €" in strat_ef.breakdown_items[0]  # Cubre el gap del fondo
    assert "600.00 €" in strat_ef.breakdown_items[1]  # Remanente a bolsa


def test_high_unassigned_liquidity():
    """Valida la alerta de liquidez invisible cuando el dinero sin asignar supera el 5%."""
    # Ingreso: 2000€, Gastos: Nec 500€ + Des 300€ + Aho 200€ = 1000€ -> Sin Asignar: 1000€ (50%)
    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=2000.0,
        budget_income=2000.0,
        real_needs=500.0,
        real_wants=300.0,
        real_savings=200.0,
    )

    unassigned_guidelines = [
        g for g in report.guidelines if g.scenario_type == MonthlyScenarioType.HIGH_UNASSIGNED
    ]
    assert len(unassigned_guidelines) == 1
    g = unassigned_guidelines[0]
    assert g.delta_amount == 1000.0
    assert g.severity == GuidelineSeverity.WARNING


def test_optimal_month():
    """Valida que un mes exactamente equilibrado devuelva estado OPTIMAL sin alertas."""
    # 50% Nec (1000€), 30% Des (600€), 20% Aho (400€)
    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=2000.0,
        budget_income=2000.0,
        real_needs=1000.0,
        real_wants=600.0,
        real_savings=400.0,
    )

    assert report.status_severity == GuidelineSeverity.INFO
    assert "Óptimo" in report.overall_status
    assert report.guidelines[0].scenario_type == MonthlyScenarioType.OPTIMAL


# ==========================================
# PRUEBAS ANUALES
# ==========================================


def test_annual_guidelines_savings_deficit():
    """Valida el diagnóstico de tasa de ahorro anual deficitaria (< 20%)."""
    metrics = {
        "ingresos_anual_real": 24000.0,
        "nec_anual_real": 12000.0,
        "des_anual_real": 9000.0,
        "aho_anual_real": 3000.0,  # 12.5% de tasa de ahorro
        "pct_nec_real": 50.0,
        "pct_des_real": 37.5,
        "pct_aho_real": 12.5,
        "ahorro_acumulado_total": 3000.0,
    }

    report = evaluate_annual_guidelines(metrics)
    assert report.average_savings_rate == 12.5

    def_items = [
        g for g in report.guidelines if g.scenario_type == AnnualScenarioType.ANNUAL_SAVINGS_DEFICIT
    ]
    assert len(def_items) == 1
    assert "Sinking Fund" in def_items[0].action_plan


def test_annual_guidelines_lifestyle_creep():
    """Valida la detección de inflación de estilo de vida en Deseos (> 30%)."""
    metrics = {
        "ingresos_anual_real": 20000.0,
        "nec_anual_real": 9000.0,
        "des_anual_real": 7000.0,  # 35%
        "aho_anual_real": 4000.0,
        "pct_nec_real": 45.0,
        "pct_des_real": 35.0,
        "pct_aho_real": 20.0,
        "ahorro_acumulado_total": 4000.0,
    }

    report = evaluate_annual_guidelines(metrics)
    creep_items = [
        g for g in report.guidelines if g.scenario_type == AnnualScenarioType.LIFESTYLE_CREEP
    ]
    assert len(creep_items) == 1
    assert "Desindexación del ocio" in creep_items[0].action_plan


def test_annual_guidelines_fixed_cost_rigidity():
    """Valida la alerta por rigidez estructural de Necesidades (> 50%)."""
    metrics = {
        "ingresos_anual_real": 20000.0,
        "nec_anual_real": 12000.0,  # 60%
        "des_anual_real": 5000.0,
        "aho_anual_real": 3000.0,
        "pct_nec_real": 60.0,
        "pct_des_real": 25.0,
        "pct_aho_real": 15.0,
        "ahorro_acumulado_total": 3000.0,
    }

    report = evaluate_annual_guidelines(metrics)
    rigidity_items = [
        g for g in report.guidelines if g.scenario_type == AnnualScenarioType.FIXED_COST_RIGIDITY
    ]
    assert len(rigidity_items) == 1
    assert rigidity_items[0].severity == GuidelineSeverity.ALERT
    assert "Revisión de estructura de vida" in rigidity_items[0].action_plan


def test_annual_guidelines_idle_cash():
    """Valida la recomendación de DCA ante exceso de liquidez ociosa en cuenta (> 12 meses de necesidades)."""
    metrics = {
        "ingresos_anual_real": 24000.0,
        "nec_anual_real": 12000.0,  # 1000€/mes
        "des_anual_real": 6000.0,
        "aho_anual_real": 6000.0,
        "pct_nec_real": 50.0,
        "pct_des_real": 25.0,
        "pct_aho_real": 25.0,
        "ahorro_acumulado_total": 35000.0,  # 35 meses de necesidades
    }

    report = evaluate_annual_guidelines(metrics)
    idle_items = [
        g for g in report.guidelines if g.scenario_type == AnnualScenarioType.IDLE_CASH
    ]
    assert len(idle_items) == 1
    assert "DCA" in idle_items[0].action_plan


def test_annual_guidelines_balanced():
    """Valida que un año perfectamente equilibrado devuelva estado equilibrado."""
    metrics = {
        "ingresos_anual_real": 24000.0,
        "nec_anual_real": 12000.0,
        "des_anual_real": 7200.0,
        "aho_anual_real": 4800.0,
        "pct_nec_real": 50.0,
        "pct_des_real": 30.0,
        "pct_aho_real": 20.0,
        "ahorro_acumulado_total": 4800.0,
    }

    report = evaluate_annual_guidelines(metrics)
    assert report.status_severity == GuidelineSeverity.INFO
    assert "Excelente Salud Financiera Anual" in report.overall_health
    assert report.guidelines[0].scenario_type == AnnualScenarioType.ANNUAL_BALANCED
