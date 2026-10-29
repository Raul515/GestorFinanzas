"""
Pruebas unitarias para el módulo de presentación visual de pautas deterministas (Spec 008).
Verifica que las funciones de renderizado de Streamlit generen las tablas sinópticas,
tarjetas con cifras reales y jerarquías de compensación sin fallos de ejecución.
"""

from unittest.mock import MagicMock, patch
import pytest

from backend.domain.schemas.guidelines import (
    AnnualGuidelineReport,
    GuidelineSeverity,
    MonthlyGuidelineReport,
)
from backend.services.guidelines_service import (
    evaluate_annual_guidelines,
    evaluate_monthly_guidelines,
)
from frontend.services.guidelines_view import (
    _get_severity_colors,
    evaluate_annual_guidelines as view_eval_annual,
    evaluate_monthly_guidelines as view_eval_monthly,
    render_annual_guidelines_expander,
    render_monthly_guidelines_expander,
)


def test_reexports():
    """Verifica que las funciones del servicio se reexportan adecuadamente en el frontend."""
    assert view_eval_monthly is evaluate_monthly_guidelines
    assert view_eval_annual is evaluate_annual_guidelines


def test_get_severity_colors():
    """Verifica la asignación coherente de colores e iconos según la severidad."""
    border, bg, icon = _get_severity_colors(GuidelineSeverity.ALERT)
    assert border == "#c62828"
    assert "198, 40, 40" in bg
    assert icon == "🚨"

    border, bg, icon = _get_severity_colors(GuidelineSeverity.WARNING)
    assert border == "#ef6c00"
    assert "239, 108, 0" in bg
    assert icon == "⚠️"

    border, bg, icon = _get_severity_colors(GuidelineSeverity.INFO)
    assert border == "#1565c0"
    assert "21, 101, 192" in bg
    assert icon == "💡"


@patch("streamlit.expander")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.caption")
def test_render_monthly_guidelines_surplus(mock_caption, mock_cols, mock_markdown, mock_expander):
    """Verifica el renderizado de un informe mensual con excedente y estrategias de asignación."""
    # Configurar mock de st.expander como context manager
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    # Mock de st.columns para las 3 estrategias
    col1, col2, col3 = MagicMock(), MagicMock(), MagicMock()
    col1.__enter__.return_value = MagicMock()
    col2.__enter__.return_value = MagicMock()
    col3.__enter__.return_value = MagicMock()
    mock_cols.return_value = [col1, col2, col3]

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

    render_monthly_guidelines_expander(report, expanded=False)

    # Validar que expander fue llamado con el título adecuado
    mock_expander.assert_called_once()
    assert "Pautas de Actuación y Compensación Presupuestaria" in mock_expander.call_args[0][0]

    # Validar que markdown fue llamado con las tablas y tarjetas
    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    assert "Tabla Sinóptica de Compensación Rápida" in combined_html
    assert "¿De dónde se saca el dinero?" in combined_html
    assert "575.00 €" in combined_html
    assert "Fondo de Emergencia" in combined_html


@patch("streamlit.expander")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.caption")
def test_render_monthly_guidelines_deficit_hierarchy(mock_caption, mock_cols, mock_markdown, mock_expander):
    """Verifica el renderizado de un informe mensual con déficit y jerarquía de absorción."""
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=2000.0,
        budget_income=2000.0,
        real_needs=1300.0,  # 300€ déficit
        real_wants=600.0,
        real_savings=100.0,
        safety_status=None,
    )

    render_monthly_guidelines_expander(report, expanded=True)

    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    assert "Jerarquía de Compensación Presupuestaria:" in combined_html
    assert "Línea 1" in combined_html
    assert "Línea 2" in combined_html
    assert "300.00 €" in combined_html


@patch("streamlit.expander")
@patch("streamlit.markdown")
def test_render_annual_guidelines(mock_markdown, mock_expander):
    """Verifica el renderizado del informe de diagnóstico estructural anual."""
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    ann_metrics = {
        "ingresos_anual_real": 24000.0,
        "aho_anual_real": 2400.0,   # Tasa 10% (< 20%)
        "nec_anual_real": 14000.0,  # 58.3% (> 50%)
        "des_anual_real": 7600.0,   # 31.7% (> 30%)
        "pct_aho_real": 10.0,
        "pct_nec_real": 58.33,
        "pct_des_real": 31.67,
    }

    report = evaluate_annual_guidelines(ann_metrics)
    render_annual_guidelines_expander(report, expanded=False)

    mock_expander.assert_called_once()
    assert "Diagnóstico Estructural y Pautas Anuales" in mock_expander.call_args[0][0]

    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    assert "Tasa de Ahorro Anual Deficitaria" in combined_html
    assert "Rigidez Estructural" in combined_html
    assert "10.00%" in combined_html
