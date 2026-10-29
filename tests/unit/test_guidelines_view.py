"""
Pruebas unitarias para el módulo de presentación visual de pautas deterministas (Spec 008).
Verifica que las funciones de renderizado de Streamlit generen las tablas sinópticas,
tarjetas con cifras reales y jerarquías de compensación sin fallos de ejecución,
tanto con diccionarios JSON de la API como con objetos de reporte.
"""

from unittest.mock import MagicMock, patch
import pytest

from backend.services.guidelines_service import (
    evaluate_annual_guidelines,
    evaluate_monthly_guidelines,
)
from frontend.services.guidelines_view import (
    GuidelineSeverity,
    _DataNode,
    _get_severity_colors,
    render_annual_guidelines_expander,
    render_monthly_guidelines_expander,
)


def test_data_node_adapter():
    """Verifica que _DataNode permita acceso tanto por atributo como por clave anidada."""
    data = {
        "status_severity": "warning",
        "guidelines": [
            {"title": "Pauta 1", "strategies": [{"name": "FIRE", "badge": "fire"}]}
        ],
    }
    node = _DataNode(data)
    assert node.status_severity == "warning"
    assert len(node.guidelines) == 1
    assert node.guidelines[0].title == "Pauta 1"
    assert node.guidelines[0].strategies[0].name == "FIRE"
    assert node.guidelines[0].strategies[0].badge == "fire"
    assert node["status_severity"] == "warning"


def test_get_severity_colors():
    """Verifica la asignación coherente de colores e iconos según la severidad."""
    border, bg, icon = _get_severity_colors(GuidelineSeverity.ALERT)
    assert border == "#c62828"
    assert "198, 40, 40" in bg
    assert icon == "🚨"

    border, bg, icon = _get_severity_colors("alert")
    assert border == "#c62828"
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
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

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

    mock_expander.assert_called_once()
    assert "Pautas de Actuación y Compensación Presupuestaria" in mock_expander.call_args[0][0]

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
def test_render_monthly_guidelines_from_dict(mock_caption, mock_cols, mock_markdown, mock_expander):
    """Verifica que render_monthly_guidelines_expander acepte diccionarios JSON directos de la API."""
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    dict_report = {
        "month_key": "2026-10",
        "month_name": "Octubre",
        "overall_status": "Excedente en Necesidades",
        "status_severity": "info",
        "real_income": 3000.0,
        "real_needs": 1000.0,
        "real_wants": 900.0,
        "real_savings": 1100.0,
        "savings_rate": 36.7,
        "synoptic_table": [
            {
                "scenario_name": "Excedente",
                "funding_source": "Sobrante de Necesidades",
                "touch_emergency_fund": "NO (Aporte)",
                "budget_action": "Invertir excedente",
            }
        ],
        "guidelines": [],
    }

    render_monthly_guidelines_expander(dict_report, expanded=False)
    mock_expander.assert_called_once()
    assert "Pautas de Actuación y Compensación Presupuestaria" in mock_expander.call_args[0][0]


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
        real_needs=1300.0,
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
        "aho_anual_real": 2400.0,
        "nec_anual_real": 14000.0,
        "des_anual_real": 7600.0,
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


def test_render_none_handles_gracefully():
    """Verifica que si el reporte es None no lance excepción."""
    render_monthly_guidelines_expander(None)
    render_annual_guidelines_expander(None)
