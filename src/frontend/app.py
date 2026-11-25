"""Punto de entrada y enrutador principal de la interfaz Streamlit (Spec 017 - Fase 5)."""

from datetime import date
import logging
import os
import sys

import streamlit as st

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.abspath(os.path.dirname(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if FRONTEND_DIR not in sys.path:
    sys.path.insert(0, FRONTEND_DIR)

try:
    from backend.utils.env_setup import ensure_env_file

    ensure_env_file()
except Exception as env_exc:
    logging.getLogger(__name__).debug("ensure_env_file omitido: %s", env_exc)

try:
    from frontend import api_client
    from frontend.views.backup_view import render_backup_view
    from frontend.views.committee_view import render_committee_view
    from frontend.views.copilot_view import render_copilot_view
    from frontend.views.deepdive_view import render_deepdive_view
    from frontend.views.joint_view import render_joint_view, render_personal_assisted_contribution_banner
    from frontend.views.market_radar_view import render_market_radar_view
    from frontend.views.mobile_view import render_mobile_view
    from frontend.views.personal_annual_view import render_personal_annual_view
    from frontend.views.personal_monthly_view import render_personal_monthly_view
    from frontend.views.screener_view import render_screener_view
    from frontend.views.settings_view import render_base_budget_settings_view
    from frontend.views.updater_view import render_updater_view
except ImportError:
    import api_client  # type: ignore
    from views.backup_view import render_backup_view  # type: ignore
    from views.committee_view import render_committee_view  # type: ignore
    from views.copilot_view import render_copilot_view  # type: ignore
    from views.deepdive_view import render_deepdive_view  # type: ignore
    from views.joint_view import render_joint_view, render_personal_assisted_contribution_banner  # type: ignore
    from views.market_radar_view import render_market_radar_view  # type: ignore
    from views.mobile_view import render_mobile_view  # type: ignore
    from views.personal_annual_view import render_personal_annual_view  # type: ignore
    from views.personal_monthly_view import render_personal_monthly_view  # type: ignore
    from views.screener_view import render_screener_view  # type: ignore
    from views.settings_view import render_base_budget_settings_view  # type: ignore
    from views.updater_view import render_updater_view  # type: ignore

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Gestor Finanzas", layout="wide")

css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
if os.path.exists(css_path):
    with open(css_path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.sidebar.header("Espacio de Trabajo")
context_mode = st.sidebar.radio(
    "Modo de Gestión",
    options=["👤 Mi Perfil Personal", "👥 Economía del Hogar (Cuenta Conjunta)"],
    index=0,
)

personal_module_options = [
    "📊 Presupuesto y Meses",
    "🧠 Inversión y Mercado (IA)",
    "⚙️ Ajustes y Sistema",
]

if (
    "personal_active_module" not in st.session_state
    or st.session_state["personal_active_module"] not in personal_module_options
):
    st.session_state["personal_active_module"] = personal_module_options[0]

modulo_personal = None
if context_mode == "👤 Mi Perfil Personal":
    st.sidebar.markdown("---")
    st.sidebar.header("Módulos")
    current_module_index = personal_module_options.index(st.session_state["personal_active_module"])
    modulo_personal = st.sidebar.radio(
        "Módulo Personal",
        options=personal_module_options,
        index=current_module_index,
        key="personal_module_radio_selector",
    )
    st.session_state["personal_active_module"] = modulo_personal

st.sidebar.markdown("---")
st.sidebar.header("Configuración Temporal")
year_today = date.today().year
year_selected = st.sidebar.number_input("Año", min_value=2000, max_value=2100, value=year_today, step=1)

if context_mode == "👥 Economía del Hogar (Cuenta Conjunta)":
    st.title("Economía del Hogar (Cuenta Conjunta)")
    render_joint_view(selected_year=year_selected)
    st.stop()

st.title("Gestor de Finanzas Personales")

categorias = api_client.get_categorias()
todas_subcats = api_client.get_subcategorias()
subcat_options = {s["id"]: s["nombre"] for s in todas_subcats} if todas_subcats else {}

necesidades_name = "Necesidades Básicas"
deseos_name = "Deseos y Estilo de vida"
ahorro_name = "Ahorro e Inversión"
ingresos_name = "Ingresos Netos"

colores_cabecera = {
    "Ingresos Netos": "#2e7d32",
    "Necesidades Básicas": "#1565c0",
    "Deseos y Estilo de vida": "#ef6c00",
    "Ahorro e Inversión": "#00838f",
}

if modulo_personal == "📊 Presupuesto y Meses":
    try:
        joint_status = api_client.get_joint_status()
        if joint_status.get("is_configured"):
            api_client.trigger_process_inbox()
            render_personal_assisted_contribution_banner(year_selected)
    except Exception as exc:
        logger.warning("Error al comprobar el estado de la cuenta conjunta: %s", exc)

    tab_anual, tab_mensual = st.tabs(["📊 Resumen Anual", "📅 Gestión Mensual"])
    with tab_anual:
        render_personal_annual_view(
            year_selected=year_selected,
            categorias=categorias,
            todas_subcats=todas_subcats,
            colores_cabecera=colores_cabecera,
            ingresos_name=ingresos_name,
            necesidades_name=necesidades_name,
            deseos_name=deseos_name,
            ahorro_name=ahorro_name,
        )
    with tab_mensual:
        render_personal_monthly_view(
            year_selected=year_selected,
            categorias=categorias,
            todas_subcats=todas_subcats,
            subcat_options=subcat_options,
            colores_cabecera=colores_cabecera,
            ingresos_name=ingresos_name,
            necesidades_name=necesidades_name,
            deseos_name=deseos_name,
            ahorro_name=ahorro_name,
        )

elif modulo_personal == "🧠 Inversión y Mercado (IA)":
    tabs_list = [
        "🌐 Radar Macro y Noticias",
        "🔍 Screener y Oportunidades",
        "🔬 Análisis Fundamental (Deep Dive)",
        "💬 Copiloto Patrimonial",
        "🏛️ Comité Asesor Multiagente",
    ]
    tab_radar, tab_screener, tab_deepdive, tab_copilot, tab_committee = st.tabs(tabs_list)
    with tab_radar:
        render_market_radar_view()
    with tab_screener:
        render_screener_view()
    with tab_deepdive:
        render_deepdive_view()
    with tab_copilot:
        render_copilot_view()
    with tab_committee:
        render_committee_view()

elif modulo_personal == "⚙️ Ajustes y Sistema":
    tabs_list = [
        "📝 Presupuesto Base y Fondo de Emergencia",
        "💾 Base de Datos y Copias de Seguridad",
        "🚀 Actualizaciones del Sistema",
        "📱 Companion Móvil Quick-Capture",
    ]
    tab_base, tab_backup, tab_updater, tab_mobile = st.tabs(tabs_list)
    with tab_base:
        render_base_budget_settings_view(
            categorias=categorias,
            todas_subcats=todas_subcats,
            colores_cabecera=colores_cabecera,
        )
    with tab_backup:
        render_backup_view()
    with tab_updater:
        render_updater_view()
    with tab_mobile:
        render_mobile_view()
