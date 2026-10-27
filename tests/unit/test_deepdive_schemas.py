from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from backend.domain.schemas.deepdive import (
    DeepDiveResponse,
    FinancialStatementYear,
    PiotroskiCriterion,
    PiotroskiScore,
    QualityValueReport,
)


def test_financial_statement_year_full():
    """Verifica la instanciación de un ejercicio contable completo para empresa industrial/consumo."""
    year_data = FinancialStatementYear(
        year=2023,
        revenue=35947000000.0,
        gross_profit=20792000000.0,
        operating_income=6806000000.0,
        net_income=5381000000.0,
        diluted_eps=1.73,
        total_assets=30312000000.0,
        current_assets=15872000000.0,
        current_liabilities=10920000000.0,
        long_term_debt=12000000.0,
        total_debt=18000000.0,
        cash_and_equivalents=11400000000.0,
        operating_cash_flow=7800000000.0,
        capital_expenditure=1800000000.0,
        free_cash_flow=6000000000.0,
        shares_outstanding=3116000000.0,
    )

    assert year_data.year == 2023
    assert year_data.revenue == 35947000000.0
    assert year_data.free_cash_flow == 6000000000.0
    assert year_data.gross_profit == 20792000000.0


def test_financial_statement_year_financial_institution():
    """Verifica que una entidad bancaria pueda prescindir de Margen Bruto y Activos/Pasivos Corrientes."""
    year_data = FinancialStatementYear(
        year=2023,
        revenue=57423000000.0,
        gross_profit=None,
        operating_income=12000000000.0,
        net_income=11076000000.0,
        diluted_eps=0.68,
        total_assets=1797000000000.0,
        current_assets=None,
        current_liabilities=None,
        long_term_debt=None,
        total_debt=None,
        cash_and_equivalents=None,
        operating_cash_flow=15000000000.0,
        capital_expenditure=2000000000.0,
        free_cash_flow=13000000000.0,
    )

    assert year_data.gross_profit is None
    assert year_data.current_assets is None
    assert year_data.current_liabilities is None
    assert year_data.net_income == 11076000000.0


def test_piotroski_criterion_valid_and_invalid():
    """Verifica validación de criterios discretos del Piotroski F-Score."""
    crit = PiotroskiCriterion(
        code="ROA",
        category="profitability",
        description="Retorno sobre activos positivo en el último ejercicio",
        points=1,
        current_value=0.177,
        previous_value=0.155,
    )
    assert crit.points == 1
    assert crit.code == "ROA"
    assert crit.category == "profitability"

    # Puntos fuera de 0 o 1 deben fallar
    with pytest.raises(ValidationError):
        PiotroskiCriterion.model_validate(
            {
                "code": "ROA",
                "category": "profitability",
                "description": "Test",
                "points": 2,
            }
        )

    # Categoría inválida debe fallar
    with pytest.raises(ValidationError):
        PiotroskiCriterion.model_validate(
            {
                "code": "ROA",
                "category": "invalida",
                "description": "Test",
                "points": 1,
            }
        )


def test_piotroski_score_ratings():
    """Verifica la agregación de puntuación y el semáforo cualitativo."""
    score = PiotroskiScore(
        total_score=8,
        max_score=9,
        rating="Excelente",
        criteria=[
            PiotroskiCriterion(
                code="ROA",
                category="profitability",
                description="ROA positivo",
                points=1,
            )
        ],
    )
    assert score.total_score == 8
    assert score.rating == "Excelente"

    # Puntuación mayor a 9 rechazada
    with pytest.raises(ValidationError):
        PiotroskiScore.model_validate(
            {
                "total_score": 10,
                "rating": "Excelente",
            }
        )

    # Rating no reconocido rechazado
    with pytest.raises(ValidationError):
        PiotroskiScore.model_validate(
            {
                "total_score": 5,
                "rating": "Regular",
            }
        )


def test_quality_value_report_structure():
    """Verifica el esquema del informe sintético agéntico Quality Value."""
    report = QualityValueReport(
        quadrant="Quality Value",
        summary_thesis="Líder global con foso defensivo en escala y logística ágil, cotizando a múltiplo razonable.",
        six_ingredients={
            "long_term_growth": "Crecimiento de ingresos al 8% anual con expansión omnicanal.",
            "tailwinds": "Consolidación de cuota de mercado frente a competidores fragmentados.",
            "market_leadership": "Número 1 indiscutible en retail textil por margen y rotación.",
            "moat": "Ventaja en costes de distribución y rotación de inventario en < 3 semanas.",
            "high_returns_on_capital": "ROIC sostenido superior al 25%.",
            "temporary_headwinds": "Preocupación coyuntural por costes laborales y fletes marítimos.",
        },
        business_model_and_risks={
            "cash_cycle": "Ciclo de conversión de caja negativo; cobra al contado a clientes y paga a 60 días a proveedores.",
        },
        bearish_risks=[
            "Disrupción arancelaria en cadenas de suministro del sudeste asiático.",
            "Presión salarial sostenida en Europa occidental recortando el margen operativo.",
        ],
        valuation_projections={
            "scenario_base": {"fcf_5y": 8500000000.0, "exit_multiple": 22.0, "target_price": 58.0, "irr": 0.165},
            "scenario_stress": {"fcf_5y": 6200000000.0, "exit_multiple": 16.0, "target_price": 38.0, "irr": 0.045},
        },
        target_irr_entry_zone="38.00 € - 42.00 € (TIR exigida: 15% - 20%)",
    )

    assert report.quadrant == "Quality Value"
    assert len(report.bearish_risks) == 2
    assert "38.00 €" in report.target_irr_entry_zone

    # Cuadrante no reconocido debe fallar
    with pytest.raises(ValidationError):
        QualityValueReport.model_validate(
            {
                "quadrant": "Empresa Mala",
                "summary_thesis": "Tesis",
                "target_irr_entry_zone": "20 €",
            }
        )


def test_deepdive_response_complete():
    """Verifica el esquema unificado de respuesta de diagnóstico Deep Dive."""
    response = DeepDiveResponse(
        ticker="ITX.MC",
        name="Industria de Diseño Textil, S.A.",
        sector="Consumer Cyclical",
        industry="Apparel Retail",
        country="Spain",
        currency="EUR",
        description="Inditex es uno de los mayores distribuidores de moda del mundo.",
        current_price=45.50,
        day_change_pct=1.12,
        market_cap=141800000000.0,
        pe_trailing=23.5,
        pe_forward=20.1,
        ev_to_ebitda=12.2,
        price_to_book=6.8,
        dividend_yield=3.4,
        beta=0.88,
        statements=[
            FinancialStatementYear(
                year=2023,
                revenue=35947000000.0,
                net_income=5381000000.0,
                total_assets=30312000000.0,
                operating_cash_flow=7800000000.0,
                capital_expenditure=1800000000.0,
                free_cash_flow=6000000000.0,
            )
        ],
        piotroski=PiotroskiScore(
            total_score=8,
            max_score=9,
            rating="Excelente",
        ),
        fcf_metrics={
            "fcf_yield": 4.23,
            "fcf_conversion_ratio": 1.11,
            "roe": 28.5,
            "roic": 25.2,
            "has_moat": True,
        },
        quality_value_report=None,
        is_financial_institution=False,
        from_cache=False,
        updated_at=datetime.now(timezone.utc),
    )

    assert response.ticker == "ITX.MC"
    assert response.current_price == 45.50
    assert response.piotroski.rating == "Excelente"
    assert response.fcf_metrics["has_moat"] is True
    assert response.quality_value_report is None
    assert response.from_cache is False
