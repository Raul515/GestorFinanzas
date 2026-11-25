"""
Pruebas Unitarias para el Refinamiento Ergonómico de la Cuenta Conjunta (Spec 013 - Fase 2 / Spec 017).
Valida la navegación mensual ágil (RF-6), la disposición simétrica de movimientos (RF-7),
la elevación del semáforo de esfuerzo familiar a la cabecera (RF-8) y la separación visual
de la pestaña de configuración a la derecha mediante CSS.
"""

import ast
import os


def _joint_views_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/views"))


def _read_all_joint_code() -> str:
    views_dir = _joint_views_dir()
    chunks = []
    facade = os.path.join(views_dir, "joint_view.py")
    with open(facade, "r", encoding="utf-8") as f:
        chunks.append(f.read())
    joint_pkg = os.path.join(views_dir, "joint")
    for fname in sorted(os.listdir(joint_pkg)):
        if fname.endswith(".py"):
            with open(os.path.join(joint_pkg, fname), "r", encoding="utf-8") as f:
                chunks.append(f.read())
    return "\n".join(chunks)


def test_joint_view_syntax_and_compilation():
    """Valida que joint_view.py y sus submódulos compilan sin errores sintácticos."""
    views_dir = _joint_views_dir()
    jv_path = os.path.join(views_dir, "joint_view.py")
    assert os.path.exists(jv_path), "joint_view.py debe existir"
    with open(jv_path, "r", encoding="utf-8") as f:
        assert ast.parse(f.read()) is not None

    joint_pkg = os.path.join(views_dir, "joint")
    for fname in os.listdir(joint_pkg):
        if fname.endswith(".py"):
            with open(os.path.join(joint_pkg, fname), "r", encoding="utf-8") as f:
                assert ast.parse(f.read()) is not None


def test_joint_view_agile_month_navigation_rf6():
    """Valida el Requerimiento Funcional RF-6."""
    code = _read_all_joint_code()
    assert 'btn_joint_prev_month' in code
    assert 'btn_joint_next_month' in code
    assert 'joint_active_month' in code
    assert 'st.session_state["joint_active_month"]' in code


def test_joint_view_symmetric_action_blocks_rf7():
    """Valida el Requerimiento Funcional RF-7."""
    code = _read_all_joint_code()
    assert 'col_act_gasto, col_act_aport = st.columns(2)' in code
    assert '🛒 Registrar Gasto Común' in code
    assert '💰 Asentar Aportación' in code


def test_joint_view_elevated_effort_traffic_light_rf8():
    """Valida el Requerimiento Funcional RF-8."""
    code = _read_all_joint_code()
    traffic_light_pos = code.find('RF-8: Diagnóstico Inmediato de Salud Financiera y Tasa de Esfuerzo en Cabecera Superior')
    metrics_pos = code.find('# Tarjetas de Métricas Principales (3 Columnas)\n    col1, col2, col3 = st.columns(3)')

    assert traffic_light_pos != -1, "El marcador de RF-8 debe existir"
    assert metrics_pos != -1, "El bloque de 3 columnas de métricas debe existir"
    assert traffic_light_pos < metrics_pos, "El semáforo debe renderizarse antes de las tarjetas de métricas"


def test_joint_view_settings_tab_right_aligned_css():
    """Valida la separación visual hacia la derecha de la pestaña de Configuración."""
    code = _read_all_joint_code()
    assert '#joint-tabs-marker' in code
    assert 'margin-left: auto !important;' in code


def test_joint_view_subcategories_management_expander():
    """Valida la integración de gestión de subcategorías del hogar en config_view.py."""
    code = _read_all_joint_code()
    pos_subcats = code.find("🏷️ Administrar Subcategorías del Hogar")
    pos_params = code.find("⚙️ Parámetros de la Cuenta Conjunta")
    assert pos_subcats != -1
    assert pos_params != -1
    assert pos_subcats < pos_params

    assert "api_client.create_joint_subcategory" in code
    assert "api_client.update_joint_subcategory" in code
    assert "api_client.delete_joint_subcategory" in code


def test_joint_view_sinking_funds_ux_improvements():
    """Valida las mejoras de UX en Huchas de Amortización (Fase 5)."""
    code = _read_all_joint_code()
    assert 'st.form("create_sinking_fund_form", clear_on_submit=True)' in code
    assert 'st.form("transfer_sinking_fund_form", clear_on_submit=True)' in code
    assert 'dest_id == src_id' in code or 'src_id == dest_id' in code
    assert '✅ Completada' in code
    assert '#10b981' in code


def test_joint_view_assisted_contribution_banner_auto_hiding():
    """Valida que el banner de aportación asistida se auto-oculte cuando la cuota local requerida es 0.00 €."""
    code = _read_all_joint_code()
    assert 'is_local_complete = (target_local <= 0.0) or (contrib_local >= target_local)' in code
    assert 'is_remote_complete = (target_remote <= 0.0) or (contrib_remote >= target_remote)' in code
