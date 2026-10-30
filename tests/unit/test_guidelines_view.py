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

    def _mock_cols_handler(spec):
        n = spec if isinstance(spec, int) else len(spec)
        res = []
        for _ in range(n):
            c = MagicMock()
            c.__enter__.return_value = c
            res.append(c)
        return res

    mock_cols.side_effect = _mock_cols_handler

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


@patch("streamlit.expander")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.caption")
@patch("streamlit.radio")
@patch("streamlit.button")
@patch("streamlit.selectbox")
def test_clean_html_table_and_suppressed_caption_on_surplus(
    mock_selectbox,
    mock_button,
    mock_radio,
    mock_caption,
    mock_cols,
    mock_markdown,
    mock_expander,
):
    """
    Verifica los Puntos 1 y 2:
    1º: La tabla sinóptica está libre de sangrías CommonMark indebidas (cierre limpio de tabla).
    2º: La recomendación operativa NO se muestra en tarjetas de excedente (NEEDS_SURPLUS).
    """
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    def _mock_cols_surplus(spec):
        n = spec if isinstance(spec, int) else len(spec)
        res = []
        for _ in range(n):
            c = MagicMock()
            c.__enter__.return_value = c
            res.append(c)
        return res

    mock_cols.side_effect = _mock_cols_surplus
    mock_radio.return_value = "Traspaso Total (100%)"

    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=2000.0,
        budget_income=2000.0,
        real_needs=700.0,  # 35% vs 50% -> 300 € excedente
        real_wants=600.0,
        real_savings=700.0,
        safety_status={"is_completed": True, "coverage_months": 3.0, "target_months": 3.0},
    )

    cats = [
        {"id": 1, "nombre": "Ahorro e Inversión", "tipo": "ahorro"},
        {"id": 2, "nombre": "Deseos", "tipo": "gasto"},
    ]
    subcats = [
        {"id": 10, "nombre": "Fondo de emergencia", "categoria_id": 1},
        {"id": 11, "nombre": "Inversión Indexada", "categoria_id": 1},
        {"id": 20, "nombre": "Ocio y Salidas", "categoria_id": 2},
    ]

    render_monthly_guidelines_expander(
        report,
        expanded=True,
        subcategories=subcats,
        categories=cats,
    )

    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    # Punto 1: Tabla HTML cerrada correctamente
    assert "<tbody>" in combined_html
    assert "</tbody></table></div>" in combined_html
    # No deben existir bloques <pre><code> generados por sangrías de 4 espacios
    assert "<pre><code>" not in combined_html

    # Punto 2: No debe haber caption de "Recomendación Operativa" en NEEDS_SURPLUS
    caption_calls = [call[0][0] for call in mock_caption.call_args_list if call[0]]
    combined_captions = " ".join(caption_calls)
    assert "Recomendación Operativa:" not in combined_captions


@patch("streamlit.expander")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.caption")
def test_operational_caption_retained_on_high_unassigned(
    mock_caption, mock_cols, mock_markdown, mock_expander
):
    """Verifica que la recomendación operativa SÍ se mantenga para Dinero Sin Asignar (HIGH_UNASSIGNED)."""
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx
    def _mock_cols(spec):
        n = spec if isinstance(spec, int) else len(spec)
        res = []
        for _ in range(n):
            c = MagicMock()
            c.__enter__.return_value = c
            res.append(c)
        return res

    mock_cols.side_effect = _mock_cols

    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=3000.0,
        budget_income=3000.0,
        real_needs=1000.0,
        real_wants=600.0,
        real_savings=600.0,  # 800 € sin asignar (26.7% > 5%)
        safety_status={"is_completed": True, "coverage_months": 3.0, "target_months": 3.0},
    )

    render_monthly_guidelines_expander(report, expanded=True)

    rendered_calls = [call[0][0] for call in mock_caption.call_args_list if call[0]] + [
        call[0][0] for call in mock_markdown.call_args_list if call[0]
    ]
    combined_rendered = " ".join(rendered_calls)
    assert "Recomendación Operativa:" in combined_rendered


@patch("streamlit.expander")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.caption")
@patch("streamlit.selectbox")
@patch("streamlit.button")
def test_render_wants_deficit_and_needs_deficit_interactive_controls(
    mock_button,
    mock_selectbox,
    mock_caption,
    mock_cols,
    mock_markdown,
    mock_expander,
):
    """Verifica que para WANTS_DEFICIT y NEEDS_DEFICIT se rendericen los controles de ajuste y amortiguación."""
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    def _mock_cols(spec):
        n = spec if isinstance(spec, int) else len(spec)
        res = []
        for _ in range(n):
            c = MagicMock()
            c.__enter__.return_value = c
            res.append(c)
        return res

    mock_cols.side_effect = _mock_cols

    cats = [
        {"id": 1, "nombre": "Necesidades Básicas", "tipo": "gasto"},
        {"id": 2, "nombre": "Deseos", "tipo": "gasto"},
        {"id": 3, "nombre": "Ahorro e Inversión", "tipo": "ahorro"},
    ]
    subcats = [
        {"id": 10, "nombre": "Alquiler", "categoria_id": 1},
        {"id": 20, "nombre": "Ocio", "categoria_id": 2},
        {"id": 30, "nombre": "Fondo de emergencia", "categoria_id": 3},
    ]

    # Report con WANTS_DEFICIT (35% en deseos)
    report_wants = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=2000.0,
        budget_income=2000.0,
        real_needs=1000.0,
        real_wants=700.0,  # 35% vs 30% -> 100 € exceso
        real_savings=300.0,
        safety_status={"is_completed": True, "coverage_months": 3.0, "target_months": 3.0},
    )

    render_monthly_guidelines_expander(
        report_wants,
        expanded=True,
        subcategories=subcats,
        categories=cats,
    )

    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    assert "Programar Ajuste Compensatorio al Próximo Mes" in combined_html
    assert "2026-11" in combined_html
    assert "100.00 €" in combined_html

    # Report con NEEDS_DEFICIT (55% en necesidades)
    mock_markdown.reset_mock()
    report_needs = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=2000.0,
        budget_income=2000.0,
        real_needs=1100.0,  # 55% vs 50% -> 100 € exceso
        real_wants=500.0,
        real_savings=400.0,
        safety_status={"is_completed": True, "coverage_months": 3.0, "target_months": 3.0},
    )

    render_monthly_guidelines_expander(
        report_needs,
        expanded=True,
        subcategories=subcats,
        categories=cats,
    )

    markdown_calls_needs = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html_needs = " ".join(markdown_calls_needs)

    assert "Amortiguar con Deseos del Mes" in combined_html_needs
    assert "Protección del Fondo de Emergencia" in combined_html_needs


@patch("streamlit.expander")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.caption")
@patch("streamlit.button")
def test_render_income_shortfall_freeze_controls(
    mock_button,
    mock_caption,
    mock_cols,
    mock_markdown,
    mock_expander,
):
    """Verifica que para INCOME_SHORTFALL se renderice el protocolo de congelación de deseos."""
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    def _mock_cols(spec):
        n = spec if isinstance(spec, int) else len(spec)
        res = []
        for _ in range(n):
            c = MagicMock()
            c.__enter__.return_value = c
            res.append(c)
        return res

    mock_cols.side_effect = _mock_cols

    cats = [
        {"id": 2, "nombre": "Deseos", "tipo": "gasto"},
    ]
    subcats = [
        {"id": 20, "nombre": "Ocio", "categoria_id": 2},
    ]

    report = evaluate_monthly_guidelines(
        month_key="2026-10",
        month_name="Octubre",
        real_income=1500.0,
        budget_income=2000.0,  # -25% caída ingresos
        real_needs=900.0,
        real_wants=300.0,
        real_savings=300.0,
        safety_status={"is_completed": True, "coverage_months": 3.0, "target_months": 3.0},
    )

    render_monthly_guidelines_expander(
        report,
        expanded=True,
        subcategories=subcats,
        categories=cats,
    )

    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    assert "Congelar Deseos del Mes" in combined_html


@patch("streamlit.expander")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.radio")
@patch("streamlit.button")
def test_render_intelligent_sweep_with_active_cushion(
    mock_button,
    mock_radio,
    mock_cols,
    mock_markdown,
    mock_expander,
):
    """Verifica que el barrido presente la opción inteligente de heredar estrategia si hay colchón activo."""
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx
    mock_radio.return_value = "INHERIT_STRATEGY"

    def _mock_cols(spec):
        n = spec if isinstance(spec, int) else len(spec)
        res = []
        for _ in range(n):
            c = MagicMock()
            c.__enter__.return_value = c
            res.append(c)
        return res

    mock_cols.side_effect = _mock_cols

    cats = [
        {"id": 1, "nombre": "Necesidades Básicas", "tipo": "gasto"},
        {"id": 2, "nombre": "Deseos", "tipo": "gasto"},
        {"id": 3, "nombre": "Ahorro e Inversión", "tipo": "ahorro"},
    ]
    subcats = [
        {"id": 10, "nombre": "Alquiler", "categoria_id": 1},
        {"id": 20, "nombre": "Viajes", "categoria_id": 2},
        {"id": 30, "nombre": "Fondo de emergencia", "categoria_id": 3},
    ]

    applied_strat = {
        "month": "2026-01",  # Mes pasado para activar ventana de barrido
        "scenario_type": "NEEDS_SURPLUS",
        "strategy_type": "HYBRID_80_20",
        "is_partial": True,
        "allocated_amount": 200.0,
        "cushion_amount": 200.0,
        "split_config": {
            "savings": [{"subcategory_id": 30, "amount": 160.0}],
            "wants": [{"subcategory_id": 20, "amount": 40.0}],
        },
    }

    report = evaluate_monthly_guidelines(
        month_key="2026-01",
        month_name="Enero",
        real_income=2000.0,
        budget_income=2000.0,
        real_needs=600.0,
        real_wants=400.0,
        real_savings=400.0,
        safety_status={"is_completed": True, "coverage_months": 3.0, "target_months": 3.0},
        applied_strategy=applied_strat,
    )

    render_monthly_guidelines_expander(
        report,
        expanded=True,
        subcategories=subcats,
        categories=cats,
    )

    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    assert "Barrido de Fin de Mes (Liquidación de Colchón y Remanente)" in combined_html
    assert mock_radio.called
    radio_kwargs = mock_radio.call_args[1]
    assert "INHERIT_STRATEGY" in mock_radio.call_args[1].get("options", mock_radio.call_args[0][1] if len(mock_radio.call_args[0]) > 1 else [])


@patch("streamlit.expander")
@patch("streamlit.markdown")
def test_render_empty_month_notice(mock_markdown, mock_expander):
    """Verifica que un mes vacío muestre aviso neutro y no tablas ni cálculos erróneos."""
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    empty_report = evaluate_monthly_guidelines(
        month_key="2026-04",
        month_name="Abril",
        real_income=0.0,
        budget_income=0.0,
        real_needs=0.0,
        real_wants=0.0,
        real_savings=0.0,
    )

    render_monthly_guidelines_expander(empty_report, expanded=True)

    mock_expander.assert_called_once()
    assert "Mes sin Información Financiera" in mock_expander.call_args[0][0]

    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    assert "No se han registrado ingresos ni gastos en este mes" in combined_html
    assert "Tabla Sinóptica" not in combined_html
    assert "Diagnóstico del Mes: Cumplimiento" not in combined_html


@patch("streamlit.expander")
@patch("streamlit.markdown")
def test_render_empty_year_notice(mock_markdown, mock_expander):
    """Verifica que un año vacío muestre aviso neutro y no tablas ni cálculos erróneos."""
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    empty_annual = evaluate_annual_guidelines({
        "ingresos_anual_real": 0.0,
        "nec_anual_real": 0.0,
        "des_anual_real": 0.0,
        "aho_anual_real": 0.0,
        "pct_nec_real": 0.0,
        "pct_des_real": 0.0,
        "pct_aho_real": 0.0,
        "ahorro_acumulado_total": 0.0,
    })

    render_annual_guidelines_expander(empty_annual, expanded=True)

    mock_expander.assert_called_once()
    assert "Año sin Información Financiera" in mock_expander.call_args[0][0]

    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    assert "No se han registrado transacciones ni presupuesto en este ejercicio" in combined_html


@patch("streamlit.expander")
@patch("streamlit.markdown")
@patch("streamlit.columns")
@patch("streamlit.selectbox")
@patch("streamlit.button")
def test_render_suppressed_recommendations_when_sweep_active(
    mock_button,
    mock_selectbox,
    mock_cols,
    mock_markdown,
    mock_expander,
):
    """
    Verifica que al activarse el barrido de fin de mes:
    1º: Se suprimen las tarjetas de excedente no aplicado (FIRE, Sinking Fund, 80/20).
    2º: Se suprimen las tarjetas de Dinero Sin Asignar Elevado (HIGH_UNASSIGNED) y Cumplimiento Óptimo (OPTIMAL).
    3º: Se renderiza exclusivamente el barrido de fin de mes.
    """
    mock_exp_ctx = MagicMock()
    mock_expander.return_value.__enter__.return_value = mock_exp_ctx

    def _mock_cols_sweep(spec):
        n = spec if isinstance(spec, int) else len(spec)
        res = []
        for _ in range(n):
            c = MagicMock()
            c.__enter__.return_value = c
            res.append(c)
        return res

    mock_cols.side_effect = _mock_cols_sweep

    cats = [
        {"id": 1, "nombre": "Necesidades Básicas", "tipo": "gasto"},
        {"id": 2, "nombre": "Deseos", "tipo": "gasto"},
        {"id": 3, "nombre": "Ahorro e Inversión", "tipo": "ahorro"},
    ]
    subcats = [
        {"id": 10, "nombre": "Alquiler", "categoria_id": 1},
        {"id": 20, "nombre": "Ocio", "categoria_id": 2},
        {"id": 30, "nombre": "Fondo de emergencia", "categoria_id": 3},
    ]

    # Mes pasado (2026-01) con excedente en necesidades no aplicado y dinero sin asignar
    report = evaluate_monthly_guidelines(
        month_key="2026-01",
        month_name="Enero",
        real_income=2000.0,
        budget_income=2000.0,
        real_needs=700.0,   # Meta: 1000.0 -> Excedente 300.0
        real_wants=400.0,
        real_savings=400.0,
        safety_status={"is_completed": True, "coverage_months": 3.0, "target_months": 3.0},
    )

    render_monthly_guidelines_expander(
        report,
        expanded=True,
        subcategories=subcats,
        categories=cats,
    )

    markdown_calls = [call[0][0] for call in mock_markdown.call_args_list if call[0]]
    combined_html = " ".join(markdown_calls)

    # El barrido DEBE aparecer porque es fin de mes y hay remanente > 5€
    assert "🧹 Barrido de Fin de Mes (Cierre Contable)" in combined_html
    # Las tarjetas operativas deben quedar SUPRIMIDAS
    assert "El Acelerador FIRE" not in combined_html
    assert "El Enfoque Híbrido" not in combined_html
    assert "Dinero Sin Asignar Elevado" not in combined_html
    assert "Pautas Operativas y Asignación con Cifras Reales" not in combined_html




