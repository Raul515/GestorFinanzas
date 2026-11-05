"""
Pruebas Unitarias para la Reestructuración de UX/UI del Frontend (Spec 013).
Valida la arquitectura modular de navegación, visibilidad condicional del sidebar,
sincronización con session_state, confinamiento del banner de aportaciones y
optimización a 2 pestañas con navegación ágil de 1 clic en la Cuenta Personal.
"""

import ast
import os
import pytest


def test_app_py_syntax_and_compilation():
    """Valida que app.py compila sin errores sintácticos."""
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/app.py"))
    assert os.path.exists(app_path), "src/frontend/app.py debe existir"
    with open(app_path, "r", encoding="utf-8") as f:
        code = f.read()
    parsed = ast.parse(code)
    assert parsed is not None


def test_app_py_sidebar_conditional_modular_navigation():
    """Valida los Requerimientos Funcionales RF-1 y RF-2 de la Spec 013:
    - Selector 'Módulo Personal' condicionado a context_mode == '👤 Mi Perfil Personal'.
    - Sincronización explícita con st.session_state['personal_active_module'].
    - Opciones exactas: '📊 Presupuesto y Meses', '🧠 Inversión y Mercado (IA)', '⚙️ Ajustes y Sistema'.
    """
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/app.py"))
    with open(app_path, "r", encoding="utf-8") as f:
        code = f.read()

    # RF-1 y RF-2: Bloque condicional en el sidebar con sincronización de estado
    assert 'if context_mode == "👤 Mi Perfil Personal":' in code
    assert 'modulo_personal = st.sidebar.radio(' in code
    assert 'st.session_state["personal_active_module"]' in code
    assert '"📊 Presupuesto y Meses"' in code
    assert '"🧠 Inversión y Mercado (IA)"' in code
    assert '"⚙️ Ajustes y Sistema"' in code


def test_app_py_tab_lists_per_module():
    """Valida los Requerimientos Funcionales RF-3, RF-4 y RF-5:
    - Presupuesto y Meses: 2 pestañas limpias (Resumen Anual + Gestión Mensual) con navegación de 1 clic.
    - Inversión y Mercado (IA): 5 pestañas exactas.
    - Ajustes y Sistema: 3 pestañas exactas.
    """
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/app.py"))
    with open(app_path, "r", encoding="utf-8") as f:
        code = f.read()

    # RF-3: Presupuesto y Meses (2 pestañas optimizadas para rendimiento)
    assert 'if modulo_personal == "📊 Presupuesto y Meses":' in code
    assert 'tabs_list = ["📊 Resumen Anual", "📅 Gestión Mensual"]' in code
    assert 'btn_personal_prev_month' in code
    assert 'btn_personal_next_month' in code
    assert 'personal_active_month_idx' in code

    # RF-4: Inversión y Mercado IA (5 pestañas)
    assert 'elif modulo_personal == "🧠 Inversión y Mercado (IA)":' in code
    assert '"🌐 Radar Macro y Noticias"' in code
    assert '"🔍 Screener y Oportunidades"' in code
    assert '"🔬 Análisis Fundamental (Deep Dive)"' in code
    assert '"💬 Copiloto Patrimonial"' in code
    assert '"🏛️ Comité Asesor Multiagente"' in code

    # RF-5: Ajustes y Sistema (3 pestañas)
    assert 'elif modulo_personal == "⚙️ Ajustes y Sistema":' in code
    assert '"📝 Presupuesto Base y Fondo de Emergencia"' in code
    assert '"💾 Base de Datos y Copias de Seguridad"' in code
    assert '"🚀 Actualizaciones del Sistema"' in code


def test_app_py_household_banner_confinement():
    """Valida que el banner de aportación al hogar esté confinado exclusivamente
    a 'Presupuesto y Meses' y no se ejecute a nivel global antes de los módulos.
    """
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/app.py"))
    with open(app_path, "r", encoding="utf-8") as f:
        code = f.read()

    pos_banner_call = code.find('_render_personal_assisted_contribution_banner(year_selected)')
    pos_budget = code.find('if modulo_personal == "📊 Presupuesto y Meses":')
    pos_ai = code.find('elif modulo_personal == "🧠 Inversión y Mercado (IA)":')

    assert pos_banner_call != -1, "La llamada al banner asistido debe existir"
    assert pos_budget != -1, "El módulo de presupuesto debe existir"
    assert pos_ai != -1, "El módulo de IA debe existir"
    assert pos_budget < pos_banner_call < pos_ai, "La llamada al banner debe estar dentro del módulo de presupuesto y antes del módulo de IA"


def test_app_py_subcategories_management_expander():
    """Valida la integración de gestión de subcategorías personalizadas en app.py (Spec 015 - Fase 3):
    - Presencia del expander '🏷️ Administrar Subcategorías Personalizadas'.
    - Situado inmediatamente antes del '⚙️ Formulario de Configuración del Presupuesto Base'.
    - Conexión con los métodos de api_client (create_subcategory, update_subcategory, delete_subcategory).
    """
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/app.py"))
    with open(app_path, "r", encoding="utf-8") as f:
        code = f.read()

    pos_subcat_expander = code.find("🏷️ Administrar Subcategorías Personalizadas")
    pos_base_form = code.find("⚙️ Formulario de Configuración del Presupuesto Base")

    assert pos_subcat_expander != -1, "El expander de subcategorías personalizadas debe existir en app.py"
    assert pos_base_form != -1, "El formulario de presupuesto base debe existir en app.py"
    assert pos_base_form < pos_subcat_expander, "El formulario de presupuesto base debe situarse arriba y el expander de subcategorías debajo"

    assert "api_client.create_subcategory" in code
    assert "api_client.update_subcategory" in code
    assert "api_client.delete_subcategory" in code


def test_app_py_subcategory_start_month_and_budget_propagation():
    """Valida la presencia del selector de mes de inicio y la propagación de presupuestos al crear subcategoría."""
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/app.py"))
    with open(app_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "sel_new_subcat_start_month" in code, "Debe existir el selector de mes de inicio en el formulario de alta"
    assert "A partir de" in code, "Debe mostrarse la etiqueta 'A partir de' con el año natural"
    assert "bulk_presupuestos = [" in code, "Debe preparar el lote masivo de presupuestos para los meses"
    assert "api_client.save_presupuestos_bulk" in code, "Debe guardar los presupuestos de forma atómica en bulk"
