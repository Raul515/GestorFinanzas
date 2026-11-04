"""
Pruebas Unitarias para el Refinamiento Ergonómico de la Cuenta Conjunta (Spec 013 - Fase 2).
Valida la navegación mensual ágil (RF-6), la disposición simétrica de movimientos (RF-7),
la elevación del semáforo de esfuerzo familiar a la cabecera (RF-8) y la separación visual
de la pestaña de configuración a la derecha mediante CSS.
"""

import ast
import os
import pytest


def test_joint_view_syntax_and_compilation():
    """Valida que joint_view.py compila sin errores sintácticos."""
    jv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/views/joint_view.py"))
    assert os.path.exists(jv_path), "joint_view.py debe existir"
    with open(jv_path, "r", encoding="utf-8") as f:
        code = f.read()
    parsed = ast.parse(code)
    assert parsed is not None


def test_joint_view_agile_month_navigation_rf6():
    """Valida el Requerimiento Funcional RF-6:
    - Navegación mensual ágil con botones de paso rápido 'btn_joint_prev_month' y 'btn_joint_next_month'.
    - Sincronización mediante 'joint_active_month' en st.session_state.
    """
    jv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/views/joint_view.py"))
    with open(jv_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert 'btn_joint_prev_month' in code
    assert 'btn_joint_next_month' in code
    assert 'joint_active_month' in code
    assert 'st.session_state["joint_active_month"]' in code


def test_joint_view_symmetric_action_blocks_rf7():
    """Valida el Requerimiento Funcional RF-7:
    - Disposición en 2 columnas simétricas para registrar gastos comunes vs asentar aportaciones.
    - Presencia de ambos bloques contiguos.
    """
    jv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/views/joint_view.py"))
    with open(jv_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert 'col_act_gasto, col_act_aport = st.columns(2)' in code
    assert '🛒 Registrar Gasto Común' in code
    assert '💰 Asentar Aportación' in code


def test_joint_view_elevated_effort_traffic_light_rf8():
    """Valida el Requerimiento Funcional RF-8:
    - El diagnóstico de la Tasa de Esfuerzo Familiar se sitúa en la cabecera superior,
      inmediatamente antes de las tarjetas de métricas agregadas anuales.
    """
    jv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/views/joint_view.py"))
    with open(jv_path, "r", encoding="utf-8") as f:
        code = f.read()

    traffic_light_pos = code.find('RF-8: Diagnóstico Inmediato de Salud Financiera y Tasa de Esfuerzo en Cabecera Superior')
    metrics_pos = code.find('# Tarjetas de Métricas Principales (3 Columnas)\n    col1, col2, col3 = st.columns(3)')

    assert traffic_light_pos != -1, "El marcador de RF-8 debe existir"
    assert metrics_pos != -1, "El bloque de 3 columnas de métricas debe existir"
    assert traffic_light_pos < metrics_pos, "El semáforo debe renderizarse antes de las tarjetas de métricas"


def test_joint_view_settings_tab_right_aligned_css():
    """Valida la separación visual hacia la derecha de la pestaña de Configuración
    mediante la regla CSS flexbox margin-left: auto vinculada al marcador #joint-tabs-marker.
    """
    jv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/views/joint_view.py"))
    with open(jv_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert '#joint-tabs-marker' in code
    assert 'margin-left: auto !important;' in code
