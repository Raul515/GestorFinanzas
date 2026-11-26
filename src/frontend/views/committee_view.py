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


def render_committee_view(year_selected: Optional[int] = None) -> None:
    """Renderiza la pestaña del Comité Asesor Multiagente."""
    if year_selected is None:
        year_selected = date.today().year
    st.header("🏛️ Comité Asesor de Inversión Multiagente")
    st.caption(
        "Órgano colegiado de deliberación patrimonial orquestado con LangGraph. Coordina cinco agentes cognitivos especializados "
        "con veto constitucional vinculante (Principio 9) y auditoría obligatoria de doble tesis (Principio 12)."
    )

    # 1. SALVAGUARDA DE SEGURIDAD PATRIMONIAL (Principio 9 de la Constitución)
    safety_committee = api_client.get_safety_status()
    if safety_committee:
        cov_m = float(safety_committee.get("coverage_months", 0.0))
        inv_ok = bool(safety_committee.get("can_invest") if "can_invest" in safety_committee else safety_committee.get("investing_allowed", False))
        target_3m = float(safety_committee.get("target_amount") or safety_committee.get("target_3m", 0.0))
        curr_bal = float(safety_committee.get("current_balance", 0.0))
        unassigned_bal = float(safety_committee.get("unassigned_balance", 0.0))

        if not inv_ok or cov_m < 3.0:
            st.markdown(
                f"""
                <div class="committee-veto-banner">
                    <h4 style="margin: 0; color: #b71c1c;">⛔ Veto Constitucional Activo (Principio 9 de la Constitución)</h4>
                    <p style="margin-top: 0.5rem; margin-bottom: 0.2rem;">
                        Tu Fondo de Emergencia cubre actualmente <strong>{cov_m:.1f} meses</strong> ({curr_bal:,.2f} €) de tus gastos esenciales.
                        El mínimo constitucional obligatorio es de <strong>3.0 meses</strong> ({target_3m:,.2f} €).
                    </p>
                    <p style="margin: 0; font-size: 0.88rem; color: #c62828;">
                        <em>El Comité Asesor bloqueará de forma inmediata cualquier asignación a renta variable o activos con riesgo y emitirá un plan de acción para completar tu colchón de liquidez.</em>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            unassigned_desc = f"Dispones de <strong>{unassigned_bal:,.2f} €</strong> en saldo 'Sin Asignar' para inversión estratégica." if unassigned_bal > 0 else "Tienes capacidad autorizada para evaluar asignaciones de inversión estratégica."
            st.markdown(
                f"""
                <div class="committee-approved-banner">
                    <h4 style="margin: 0; color: #1b5e20;">🛡️ Salvaguarda Patrimonial Superada (Cobertura: {cov_m:.1f} meses)</h4>
                    <p style="margin-top: 0.5rem; margin-bottom: 0.2rem;">
                        Tu Fondo de Emergencia ({curr_bal:,.2f} €) supera el umbral constitucional de 3 meses.
                        {unassigned_desc}
                    </p>
                    <p style="margin: 0; font-size: 0.88rem; color: #2e7d32;">
                        <em>El Comité deliberará la conveniencia y tramos de entrada bajo la estricta formulación de la doble tesis (mínimo 2 riesgos bajistas obligatorios).</em>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # 2. FORMULARIO DE CONVOCATORIA DEL COMITÉ
    st.subheader("📋 Convocatoria de Deliberación")

    # Recuperar lista de seguimiento para facilitar la selección de empresas
    watch_items_com = api_client.get_watchlist()
    watch_tickers = [w["ticker"] for w in watch_items_com] if watch_items_com else []

    col_c1, col_c2 = st.columns([6, 6])
    with col_c1:
        tipo_analisis = st.radio(
            "Modalidad de deliberación:",
            options=["Activo específico (Empresa / ETF)", "Consulta patrimonial general (Sin ticker)"],
            horizontal=True,
            key="committee_tipo_analisis",
        )

        selected_ticker = None
        if tipo_analisis == "Activo específico (Empresa / ETF)":
            ticker_options = ["(Ingresar manualmente)"] + watch_tickers
            chosen_option = st.selectbox(
                "Seleccionar ticker:",
                options=ticker_options,
                help="Puedes seleccionar una empresa de tu Watchlist o escribir cualquier ticker de mercado.",
                key="committee_ticker_select",
            )
            if chosen_option == "(Ingresar manualmente)":
                manual_ticker = st.text_input(
                    "Símbolo bursátil (ej. ITX.MC, SAN.MC, AAPL, IWDA.AS):",
                    value="ITX.MC",
                    key="committee_manual_ticker",
                )
                selected_ticker = manual_ticker.strip().upper() if manual_ticker else None
            else:
                selected_ticker = chosen_option

    with col_c2:
        mes_auditar = st.selectbox(
            "Mes contable de referencia:",
            options=["BASE"] + [f"{year_selected}-{m:02d}" for m in range(1, 13)],
            index=0,
            help="Mes para evaluar la liquidez real disponible y los gastos esenciales.",
            key="committee_month_select",
        )

        user_notes = st.text_area(
            "Notas o directrices del usuario (opcional):",
            placeholder="Ejemplo: Perfil moderado, horizonte temporal a 5 años, dudas sobre el impacto de tipos del BCE...",
            max_chars=500,
            height=78,
            key="committee_user_notes",
        )

    st.write("")
    btn_deliberar = st.button(
        "🚀 Convocar Deliberación del Comité Asesor",
        type="primary",
        width="stretch",
        key="btn_run_committee",
    )

    if btn_deliberar:
        with st.spinner("🏛️ El Comité Asesor de Inversión está deliberando en LangGraph (Salvaguarda ➔ Macro ➔ Fundamental ➔ Debate de Riesgos ➔ Síntesis)..."):
            res_committee = api_client.run_investment_committee(
                ticker=selected_ticker,
                month=mes_auditar,
                initial_notes=user_notes,
            )
            if res_committee:
                st.session_state["committee_result"] = res_committee
                st.success("¡Deliberación del Comité completada con éxito!")
            else:
                st.error("No se pudo completar la deliberación. Asegúrate de que el backend FastAPI esté ejecutándose.")

    # 3. RENDERIZADO DEL INFORME Y VEREDICTO FINAL
    committee_data = st.session_state.get("committee_result")
    if committee_data:
        st.markdown("---")
        st.subheader("📑 Dictamen Oficial del Comité Asesor")

        veto_flag = committee_data.get("veto_active", False)
        veredicto_txt = committee_data.get("final_verdict", "Sin veredicto emitido.")
        action_plan_txt = committee_data.get("action_plan", "")
        ticker_reportado = committee_data.get("ticker")
        mes_reportado = committee_data.get("month", "BASE")

        # 3.1 TARJETA DEL VEREDICTO FINAL
        if veto_flag:
            st.error(veredicto_txt)
        else:
            st.markdown(
                f"""
                <div class="committee-verdict-card">
                    <h3 style="margin-top: 0; color: #1565c0;">⚖️ Veredicto Vinculante del Comité — {ticker_reportado or 'Patrimonio General'} (Mes {mes_reportado})</h3>
                    <div style="font-size: 1.05rem; line-height: 1.6; white-space: pre-wrap;">{veredicto_txt}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 3.2 PLAN DE ACCIÓN ESTRATÉGICO
        if action_plan_txt:
            st.markdown(
                f"""
                <div class="committee-action-card">
                    <h4 style="margin-top: 0; color: #0d47a1;">📋 Plan de Acción y Despliegue de Liquidez</h4>
                    <div style="white-space: pre-wrap; font-size: 0.95rem; line-height: 1.6;">{action_plan_txt}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 3.3 AUDITORÍA DE DOBLE TESIS (PRINCIPIO 12 DE LA CONSTITUCIÓN)
        if not veto_flag and ticker_reportado:
            st.subheader("⚖️ Auditoría de Doble Tesis (Principio 12)")
            col_bull, col_bear = st.columns(2)

            bull_thesis_txt = committee_data.get("bull_thesis") or "Fundamentales sólidos y ventaja competitiva contrastada."
            bear_risks_list = committee_data.get("bear_risks") or []

            with col_bull:
                st.markdown(
                    f"""
                    <div class="committee-bull-card">
                        <h4 style="margin-top: 0; color: #1b5e20;">🐂 Tesis Favorable & Moat (Bull Case)</h4>
                        <div style="white-space: pre-wrap; font-size: 0.92rem; line-height: 1.5;">{bull_thesis_txt}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col_bear:
                risks_html = "".join([f"<li style='margin-bottom: 0.45rem;'><strong>{r}</strong></li>" for r in bear_risks_list])
                st.markdown(
                    f"""
                    <div class="committee-bear-card">
                        <h4 style="margin-top: 0; color: #b71c1c;">🐻 Auditoría Red Team (Bear Risks Obligatorios)</h4>
                        <p style="font-size: 0.85rem; color: #c62828; margin-bottom: 0.6rem;">
                            <em>"¿Qué puede salir mal y cuánto beneficio destruiría?"</em>
                        </p>
                        <ul style="font-size: 0.92rem; line-height: 1.45; padding-left: 1.2rem; margin: 0;">
                            {risks_html}
                        </ul>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # 3.4 CRONOLOGÍA Y TRAZABILIDAD DE LOS AGENTES EN LANGGRAPH
        agent_logs = committee_data.get("agent_logs") or []
        if agent_logs:
            st.markdown("---")
            st.subheader(f"🔄 Deliberación Paso a Paso de los Agentes ({len(agent_logs)} Intervenciones)")

            for idx, log in enumerate(agent_logs, start=1):
                agent_name = log.get("agent", "Agente")
                log_time = log.get("timestamp", "")
                log_msg = log.get("message", "")
                data_keys = log.get("data_keys", [])

                # Asignar badge según rol
                if "Safety" in agent_name:
                    badge_class = "badge-agent-safety"
                    agent_title = f"🛡️ Paso {idx}: Salvaguarda Patrimonial ({agent_name})"
                elif "Macro" in agent_name:
                    badge_class = "badge-agent-macro"
                    agent_title = f"🌐 Paso {idx}: Contexto Macroeconómico ({agent_name})"
                elif "Fundamental" in agent_name:
                    badge_class = "badge-agent-fundamental"
                    agent_title = f"🔬 Paso {idx}: Diagnóstico Contable ({agent_name})"
                elif "Risk" in agent_name:
                    badge_class = "badge-agent-risk"
                    agent_title = f"🐻 Paso {idx}: Red Team & Doble Tesis ({agent_name})"
                else:
                    badge_class = "badge-agent-advisor"
                    agent_title = f"⚖️ Paso {idx}: Síntesis y Veredicto Final ({agent_name})"

                with st.expander(agent_title, expanded=(idx == len(agent_logs) or "Veto" in log_msg)):
                    col_l1, col_l2 = st.columns([9, 3])
                    with col_l1:
                        st.markdown(f"**Conclusión del agente**: {log_msg}")
                    with col_l2:
                        st.caption(f"⏱️ {_format_datetime_es(log_time)}")

                    if data_keys:
                        st.write("🔑 *Claves inyectadas al estado compartido:*")
                        st.code(", ".join(data_keys), language="text")

        # 3.5 DIAGNÓSTICOS CUANTITATIVOS AUXILIARES
        macro_sum = committee_data.get("macro_summary")
        fund_sum = committee_data.get("fundamental_summary")
        if macro_sum or fund_sum:
            st.markdown("---")
            st.subheader("📊 Datos Cuantitativos de Soporte")
            tab_diag_m, tab_diag_f = st.tabs(["🌐 Indicadores Macro", "📈 Auditoría Contable"])

            with tab_diag_m:
                if macro_sum and "indicators" in macro_sum:
                    df_macro = pd.DataFrame(macro_sum["indicators"])
                    st.dataframe(df_macro, width="stretch")
                else:
                    st.info("Sin datos macroeconómicos requeridos en esta consulta.")

            with tab_diag_f:
                if fund_sum:
                    st.json(fund_sum)
                else:
                    st.info("Sin datos contables de empresa individual requeridos en esta consulta.")

    # 4. DESCARGO LEGAL AL PIE (Principio 10 de la Constitución)
    st.markdown("---")
    st.caption(
        "⚖️ **Descargo de Responsabilidad Legal (Disclaimer)**: Las deliberaciones y dictámenes del Comité Asesor de Inversión Multiagente "
        "tienen propósito exclusivamente pedagógico e informativo. No constituyen recomendación de inversión personalizada ni asesoramiento financiero "
        "regulado (MiFID II). La asignación de activos de riesgo debe realizarse bajo el estricto criterio y responsabilidad del usuario."
    )



