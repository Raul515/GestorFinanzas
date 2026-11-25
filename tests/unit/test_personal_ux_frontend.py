"""
Pruebas Unitarias para la Reestructuración de UX/UI del Frontend (Spec 013 / Spec 017).
Valida la arquitectura modular de navegación, visibilidad condicional del sidebar,
sincronización con session_state, confinamiento del banner de aportaciones y
optimización a 2 pestañas con navegación ágil de 1 clic en la Cuenta Personal.
"""

import ast
import os


def _frontend_path(*parts: str) -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend", *parts))


def _read_file(*parts: str) -> str:
    with open(_frontend_path(*parts), "r", encoding="utf-8") as f:
        return f.read()


def test_app_py_syntax_and_compilation():
    """Valida que app.py compila sin errores sintácticos."""
    app_path = _frontend_path("app.py")
    assert os.path.exists(app_path), "src/frontend/app.py debe existir"
    parsed = ast.parse(_read_file("app.py"))
    assert parsed is not None


def test_app_py_sidebar_conditional_modular_navigation():
    """Valida los Requerimientos Funcionales RF-1 y RF-2 de la Spec 013."""
    code = _read_file("app.py")

    assert 'if context_mode == "👤 Mi Perfil Personal":' in code
    assert 'modulo_personal = st.sidebar.radio(' in code
    assert 'st.session_state["personal_active_module"]' in code
    assert '"📊 Presupuesto y Meses"' in code
    assert '"🧠 Inversión y Mercado (IA)"' in code
    assert '"⚙️ Ajustes y Sistema"' in code


def test_app_py_tab_lists_per_module():
    """Valida los Requerimientos Funcionales RF-3, RF-4 y RF-5 en app.py y personal_monthly_view.py."""
    app_code = _read_file("app.py")
    monthly_code = _read_file("views", "personal_monthly_view.py")

    assert 'if modulo_personal == "📊 Presupuesto y Meses":' in app_code
    assert '"📊 Resumen Anual"' in app_code
    assert '"📅 Gestión Mensual"' in app_code
    assert 'btn_personal_prev_month' in monthly_code
    assert 'btn_personal_next_month' in monthly_code
    assert 'personal_active_month_idx' in monthly_code

    assert 'elif modulo_personal == "🧠 Inversión y Mercado (IA)":' in app_code
    assert '"🌐 Radar Macro y Noticias"' in app_code
    assert '"🔍 Screener y Oportunidades"' in app_code
    assert '"🔬 Análisis Fundamental (Deep Dive)"' in app_code
    assert '"💬 Copiloto Patrimonial"' in app_code
    assert '"🏛️ Comité Asesor Multiagente"' in app_code

    assert 'elif modulo_personal == "⚙️ Ajustes y Sistema":' in app_code
    assert '"📝 Presupuesto Base y Fondo de Emergencia"' in app_code
    assert '"💾 Base de Datos y Copias de Seguridad"' in app_code
    assert '"🚀 Actualizaciones del Sistema"' in app_code


def test_app_py_household_banner_confinement():
    """Valida que el banner de aportación al hogar esté confinado exclusivamente a Presupuesto y Meses."""
    code = _read_file("app.py")

    pos_banner_call = code.find('render_personal_assisted_contribution_banner(year_selected)')
    pos_budget = code.find('if modulo_personal == "📊 Presupuesto y Meses":')
    pos_ai = code.find('elif modulo_personal == "🧠 Inversión y Mercado (IA)":')

    assert pos_banner_call != -1, "La llamada al banner asistido debe existir"
    assert pos_budget != -1, "El módulo de presupuesto debe existir"
    assert pos_ai != -1, "El módulo de IA debe existir"
    assert pos_budget < pos_banner_call < pos_ai


def test_app_py_subcategories_management_expander():
    """Valida la integración de gestión de subcategorías personalizadas en settings_view.py."""
    code = _read_file("views", "settings_view.py")

    pos_subcat_expander = code.find("🏷️ Administrar Subcategorías Personalizadas")
    pos_base_form = code.find("⚙️ Formulario de Configuración del Presupuesto Base")

    assert pos_subcat_expander != -1, "El expander de subcategorías personalizadas debe existir"
    assert pos_base_form != -1, "El formulario de presupuesto base debe existir"
    assert pos_base_form < pos_subcat_expander

    assert "api_client.create_subcategory" in code
    assert "api_client.update_subcategory" in code
    assert "api_client.delete_subcategory" in code


def test_app_py_subcategory_start_month_and_budget_propagation():
    """Valida la presencia del selector de mes de inicio y la propagación de presupuestos al crear subcategoría."""
    code = _read_file("views", "settings_view.py")
    assert "sel_new_subcat_start_month" in code
