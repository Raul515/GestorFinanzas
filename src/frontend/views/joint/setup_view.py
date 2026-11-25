import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional
import sys

import altair as alt
import pandas as pd
import streamlit as st

from backend.domain.constants import is_default_joint_subcategory

try:
    import api_client as _default_api_client
except ImportError:
    from frontend import api_client as _default_api_client  # type: ignore

try:
    from utils.formatting import format_date_es as _shared_format_date_es  # type: ignore
except ImportError:
    from frontend.utils.formatting import format_date_es as _shared_format_date_es  # type: ignore

logger = logging.getLogger(__name__)

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _format_date_es(d_val: Any) -> str:
    return _shared_format_date_es(d_val, fallback="—")


class _ApiProxy:
    def __getattr__(self, name: str) -> Any:
        jv = sys.modules.get("frontend.views.joint_view") or sys.modules.get("views.joint_view")
        client = getattr(jv, "api_client", _default_api_client) if jv else _default_api_client
        return getattr(client, name)


api_client = _ApiProxy()


def _render_zero_state_wizard() -> None:
    """Asistente de bienvenida y configuración inicial de la cuenta conjunta."""
    st.header("✨ Configurar Espacio Compartido del Hogar")
    st.markdown(
        """
        Bienvenido a la gestión financiera conjunta. Este espacio permite coordinar los gastos del hogar
        y las huchas compartidas manteniendo la **total privacidad** de tus ingresos individuales,
        patrimonio propio y gastos personales (ocio, caprichos o formación).
        """
    )

    # Detección de invitación previa enviada por la pareja vía Syncthing (Opción A)
    inv_resp = api_client.get_joint_invitation()
    has_invitation = inv_resp.get("has_invitation", False)

    if has_invitation:
        inv = inv_resp.get("invitation", {})
        h_name = inv.get("household_name", "Hogar Compartido")
        creator = inv.get("member_a_name", "tu pareja")
        split_lbl = "Al 50%" if "50" in str(inv.get("split_mode", "50")) else "Proporcional a Ingresos"
        strat_val = inv.get("contribution_strategy", "NOMINAL_TEMPLATE")
        custom_budget_val = float(inv.get("custom_total_monthly_budget", 0.0) or 0.0)
        strat_lbl = (
            f"Presupuesto Fijo Global ({custom_budget_val:,.2f} €/mes)"
            if strat_val == "GLOBAL_FIXED"
            else "Calculado por Conceptos (Necesidades + Huchas)"
        )
        cohab_lbl = "Convivencia Inicial" if "DATING" in str(inv.get("cohabitation_stage", "")) or "PRE" in str(inv.get("cohabitation_stage", "")) else "Matrimonio / Proyecto a Largo Plazo"

        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #064e3b, #0f172a); border: 2px solid #10b981; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                <h3 style="color: #6ee7b7; margin: 0 0 8px 0;">🎉 ¡Invitación de Hogar Detectada!</h3>
                <p style="color: #f1f5f9; margin: 0 0 10px 0; font-size: 1rem;">
                    Tu pareja (<b>{creator}</b>) ya ha configurado el hogar <b>'{h_name}'</b> en su ordenador y lo ha compartido contigo a través de Syncthing.
                </p>
                <p style="color: #cbd5e1; margin: 0 0 14px 0; font-size: 0.9rem;">
                    • <b>Modo de Reparto pactado</b>: {split_lbl}<br>
                    • <b>Estrategia de Presupuesto</b>: {strat_lbl}<br>
                    • <b>Etapa de Convivencia</b>: {cohab_lbl}
                </p>
                <p style="color: #94a3b8; font-size: 0.85rem; margin: 0;">
                    Al unirte, este dispositivo adoptará automáticamente la configuración común sin riesgo de discrepancias ni duplicados.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("✨ Unirse a este Hogar en 1-Clic", type="primary", width="stretch", key="btn_accept_inv"):
            with st.spinner("Conectando con la cuenta conjunta de tu pareja..."):
                res_acc = api_client.accept_joint_invitation()
                if res_acc:
                    api_client.clear_joint_cache()
                    api_client.clear_annual_cache()
                    st.cache_data.clear()
                    st.success("🎉 ¡Te has unido a la cuenta conjunta exitosamente!")
                    st.rerun()
                else:
                    st.error("❌ Ocurrió un error al aceptar la invitación.")

        st.markdown("<hr style='margin: 25px 0 15px 0; border: 0; border-top: 1px dashed #475569;'>", unsafe_allow_html=True)
        st.markdown("<p style='color: #94a3b8; font-size: 0.9rem;'>O si lo prefieres, puedes ignorar la invitación y configurar una cuenta distinta manualmente:</p>", unsafe_allow_html=True)

    with st.expander("📝 Configurar Cuenta Conjunta Manualmente", expanded=(not has_invitation)):
        with st.form("joint_onboarding_form"):
            st.subheader("1. Identificación del Hogar")
            account_name = st.text_input(
                "Nombre del Hogar o Cuenta Común",
                value="Hogar Compartido",
                help="Ejemplo: Hogar Martínez-López, Casa Nuestra, etc.",
            )

            col_a, col_b = st.columns(2)
            with col_a:
                member_a_name = st.text_input(
                    "Tu Nombre (Miembro A - Dispositivo Local)",
                    value="Raúl",
                    help="Identificador que figurará en tus aportaciones conjuntas.",
                )
                member_a_income = st.number_input(
                    "Tu Salario Neto Mensual Estimado (€)",
                    min_value=0.0,
                    value=2000.0,
                    step=50.0,
                    help="Utilizado de forma confidencial para el cálculo del semáforo y reparto proporcional.",
                )

            with col_b:
                member_b_name = st.text_input(
                    "Nombre de tu Pareja (Miembro B - Cotitular)",
                    value="Pareja",
                    help="Nombre de la otra persona del hogar.",
                )
                member_b_income = st.number_input(
                    "Salario Neto Mensual Estimado de tu Pareja (€)",
                    min_value=0.0,
                    value=2000.0,
                    step=50.0,
                    help="Utilizado para la Tasa de Esfuerzo Familiar combinada.",
                )

            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader("2. Reglas de Convivencia y Reparto")
            col_c, col_d = st.columns(2)
            with col_c:
                split_mode_choice = st.selectbox(
                    "Modo de Reparto de Gastos",
                    options=["Al 50% cada uno (EQUAL_50_50)", "Proporcional a Ingresos Netos (INCOME_PROPORTIONAL)"],
                    index=0,
                    help="Define cómo se calcula la aportación mensual de cada persona a la cuenta común.",
                )
                split_mode = "EQUAL_50_50" if "50%" in split_mode_choice else "INCOME_PROPORTIONAL"

            with col_d:
                cohab_choice = st.selectbox(
                    "Etapa de Convivencia",
                    options=[
                        "Convivencia Plena / Compartiendo Hogar (COHABITATION)",
                        "Pre-Convivencia / Viviendo Separados (PRE_COHABITATION)",
                    ],
                    index=0,
                    help="En convivencia plena se gestionan facturas del hogar (alquiler, suministros, súper) + huchas. En pre-convivencia se ahorra para metas futuras sin costes de vivienda.",
                )
                cohabitation_stage = "COHABITATION" if "Convivencia Plena" in cohab_choice or "Compartiendo" in cohab_choice else "PRE_COHABITATION"

            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader("3. Estrategia de Presupuesto y Aportaciones")
            col_e, col_f = st.columns(2)
            with col_e:
                strat_options = [
                    "Presupuesto Fijo Global (Manual)",
                    "Calculado por Conceptos (Necesidades + Huchas)",
                ]
                strat_choice = st.selectbox(
                    "Cálculo del Presupuesto del Hogar",
                    options=strat_options,
                    index=0,
                    help="Determina si el presupuesto mensual total del hogar se fija como una cuota global fija o se calcula sumando las necesidades y metas del hogar.",
                )
                contribution_strategy = "GLOBAL_FIXED" if "Global" in strat_choice else "NOMINAL_TEMPLATE"

            with col_f:
                custom_budget_input = st.number_input(
                    "Presupuesto Fijo Mensual Total (€)",
                    min_value=0.0,
                    value=300.0,
                    step=50.0,
                    help="Aplica si eliges Presupuesto Fijo Global. Este importe se repartirá mensualmente según el Modo de Reparto seleccionado.",
                )

            st.info(
                "ℹ️ Al crear la cuenta conjunta, se inicializarán automáticamente las subcategorías de necesidades comunes "
                "(Alquiler/Hipoteca, Supermercado, Luz, Agua, Seguros del Hogar, etc.) y se habilitará la sincronización Syncthing."
            )

            submitted = st.form_submit_button("🚀 Iniciar y Activar Cuenta Conjunta", width="stretch")
            if submitted:
                if not account_name.strip() or not member_a_name.strip() or not member_b_name.strip():
                    st.error("Por favor completa los nombres requeridos.")
                    return

                payload = {
                    "household_name": account_name.strip(),
                    "member_a_name": member_a_name.strip(),
                    "member_b_name": member_b_name.strip(),
                    "split_mode": split_mode,
                    "cohabitation_stage": cohabitation_stage,
                    "contribution_strategy": contribution_strategy,
                    "custom_total_monthly_budget": float(custom_budget_input) if contribution_strategy == "GLOBAL_FIXED" else 0.0,
                    "member_a_reference_income": float(member_a_income),
                    "member_b_reference_income": float(member_b_income),
                    "local_profile": "MEMBER_A",
                    "remote_profile": "MEMBER_B",
                }

                with st.spinner("Configurando el espacio del hogar..."):
                    res = api_client.setup_joint_account(payload)
                    if res:
                        api_client.clear_joint_cache()
                        api_client.clear_annual_cache()
                        st.cache_data.clear()
                        st.success("🎉 ¡Cuenta conjunta configurada exitosamente!")
                        st.rerun()
                    else:
                        st.error("❌ Ocurrió un error al crear la cuenta conjunta. Revisa los registros.")



# =====================================================================
# 2. PANTALLA PRINCIPAL (CONFIGURED JOINT ACCOUNT)

