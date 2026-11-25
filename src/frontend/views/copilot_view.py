import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import altair as alt
import pandas as pd
import streamlit as st

from backend.domain.constants import is_default_personal_subcategory

try:
    from frontend import api_client
    from frontend.services.financial_calculator import (
        calculate_503020_percentages,
        calculate_annual_metrics,
        calculate_category_totals,
    )
    from frontend.services.guidelines_view import (
        render_annual_guidelines_expander,
        render_monthly_guidelines_expander,
    )
    from frontend.utils.formatting import format_datetime_es as _shared_format_datetime_es
except ImportError:
    import api_client  # type: ignore
    from services.financial_calculator import (  # type: ignore
        calculate_503020_percentages,
        calculate_annual_metrics,
        calculate_category_totals,
    )
    from services.guidelines_view import (  # type: ignore
        render_annual_guidelines_expander,
        render_monthly_guidelines_expander,
    )
    from utils.formatting import format_datetime_es as _shared_format_datetime_es  # type: ignore

logger = logging.getLogger(__name__)

MESES_NOMBRES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _format_datetime_es(raw: Any) -> str:
    return _shared_format_datetime_es(raw, fallback="")


def render_copilot_view() -> None:
    """Renderiza la pestaña de Copiloto Patrimonial IA."""
    st.header("💬 Copiloto Patrimonial")
    st.caption(
        "Asistente conversacional de inteligencia financiera con Function Calling bajo demanda y doble tesis obligatoria."
    )

    safety_info = api_client.get_safety_status()
    if safety_info:
        cov_months = float(safety_info.get("coverage_months", 0.0))
        inv_allowed = bool(safety_info.get("can_invest") if "can_invest" in safety_info else safety_info.get("investing_allowed", False))
        if not inv_allowed or cov_months < 3.0:
            st.warning(
                f"🛡️ **Salvaguarda de Seguridad Activa (Principio 9)**: Tu Fondo de Emergencia cubre "
                f"**{cov_months:.1f} meses** de necesidades básicas (mínimo constitucional: **3.0 meses**). "
                f"El Copiloto vetará cualquier recomendación de renta variable o instrumentos con riesgo hasta que el fondo esté completo."
            )
        else:
            st.info(
                f"✅ **Salvaguarda Superada**: Tu Fondo de Emergencia cubre **{cov_months:.1f} meses** "
                f"(objetivo constitucional cumplido). Puedes planificar asignaciones de inversión responsable con tu saldo 'Sin Asignar'."
            )

    st.markdown("---")

    # 2. GESTIÓN DE SESIONES DE CONVERSACIÓN
    if "copilot_session_id" not in st.session_state:
        st.session_state["copilot_session_id"] = None

    copilot_sessions = api_client.get_copilot_sessions()
    sess_col1, sess_col2, sess_col3 = st.columns([6, 3, 3])

    with sess_col1:
        if copilot_sessions:
            session_map = {
                s["id"]: f"{s.get('title', 'Conversación')} ({s.get('message_count', 0)} msgs)"
                for s in copilot_sessions
            }
            if (
                st.session_state["copilot_session_id"] not in session_map
                and len(copilot_sessions) > 0
            ):
                st.session_state["copilot_session_id"] = copilot_sessions[0]["id"]

            active_sess_id = st.session_state["copilot_session_id"]
            active_idx = (
                list(session_map.keys()).index(active_sess_id)
                if active_sess_id in session_map
                else 0
            )

            chosen_sess_id = st.selectbox(
                "Conversación activa:",
                options=list(session_map.keys()),
                index=active_idx,
                format_func=lambda sid: session_map.get(sid, str(sid)),
                key="copilot_session_selector",
            )
            st.session_state["copilot_session_id"] = chosen_sess_id
        else:
            st.write("*(No hay conversaciones guardadas)*")

    with sess_col2:
        st.write("")
        st.write("")
        if st.button("➕ Nueva conversación", key="btn_new_copilot_sess", width="stretch"):
            new_sess = api_client.create_copilot_session()
            if new_sess and "id" in new_sess:
                st.session_state["copilot_session_id"] = new_sess["id"]
                st.rerun()

    with sess_col3:
        st.write("")
        st.write("")
        if st.session_state["copilot_session_id"]:
            if st.button("🗑️ Eliminar conversación", key="btn_del_copilot_sess", width="stretch"):
                api_client.delete_copilot_session(st.session_state["copilot_session_id"])
                st.session_state["copilot_session_id"] = None
                st.rerun()

    st.markdown("---")

    # 3. RENDERIZADO DE MENSAJES HISTÓRICOS
    current_session_id = st.session_state.get("copilot_session_id")
    messages = []
    if current_session_id:
        detail_data = api_client.get_copilot_session_detail(current_session_id)
        if detail_data and "messages" in detail_data:
            messages = detail_data["messages"]

    if not messages:
        st.markdown(
            """
            <div class="copilot-welcome-card">
                <h4>👋 ¡Bienvenido a tu Copiloto Patrimonial!</h4>
                <p>Estoy aquí para ayudarte a tomar decisiones financieras prudentes, planificar tu presupuesto 50/30/20 y auditar oportunidades de inversión con máxima objetividad.</p>
                <p><strong>Ejemplos de preguntas que puedes hacerme:</strong></p>
                <ul>
                    <li><em>"¿Cómo está mi presupuesto este mes y cuánto tengo en 'Sin Asignar'?"</em></li>
                    <li><em>"¿Puedo empezar a invertir en fondos o bolsa este mes?"</em></li>
                    <li><em>"¿Qué valores tengo guardados en mi Watchlist?"</em></li>
                    <li><em>"¿Cuál es el análisis fundamental y la tesis Quality Value de ITX.MC?"</em></li>
                    <li><em>"¿Qué riesgos bajistas tiene Apple antes de plantearme comprar?"</em></li>
                    <li><em>"¿Cómo están los tipos de interés del BCE y la prima de riesgo de España?"</em></li>
                </ul>
                <p><small>🔒 <em>Tus datos contables privados residen exclusivamente en tu base de datos SQLite local y sólo son consultados cuando tu pregunta lo requiere.</em></small></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for msg in messages:
            msg_role = msg.get("role", "assistant")
            msg_content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")

            with st.chat_message(msg_role):
                st.markdown(msg_content)
                if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
                    with st.expander(f"🔧 Herramientas consultadas ({len(tool_calls)})", expanded=False):
                        for tc in tool_calls:
                            tool_name = tc.get("tool", "herramienta")
                            tool_args = tc.get("args", {})
                            st.markdown(f"- **`{tool_name}`**: `{tool_args}`")

    # 4. ENTRADA INTERACTIVA DE CHAT (st.chat_input)
    if chat_input := st.chat_input("Escribe tu consulta financiera al Copiloto..."):
        # Mostrar el mensaje del usuario de inmediato en la UI
        with st.chat_message("user"):
            st.markdown(chat_input)

        with st.spinner("El Copiloto está analizando datos y razonando..."):
            chat_response = api_client.send_copilot_chat(
                message=chat_input,
                session_id=current_session_id,
            )

        if chat_response:
            st.session_state["copilot_session_id"] = chat_response["session_id"]
            st.rerun()
        else:
            st.error("No se pudo obtener respuesta del Copiloto. Comprueba que el backend FastAPI esté ejecutándose.")

    # 5. DESCARGO LEGAL AL PIE (Principio 10 de la Constitución)
    st.markdown("---")
    st.caption(
        "⚖️ **Descargo de Responsabilidad Legal (Disclaimer)**: El Copiloto Patrimonial es una herramienta de asistencia formativa y de soporte analítico. "
        "No constituye asesoramiento financiero regulado (MiFID II / CNMV), recomendación vinculante de inversión ni oferta de productos financieros. "
        "Toda decisión de inversión conlleva riesgo de pérdida de capital y debe basarse en tu propio análisis prudente."
    )


# ========================================================
# PESTAÑA 18: COMITÉ ASESOR MULTIAGENTE (SPEC 005 - LANGGRAPH)
# ========================================================
