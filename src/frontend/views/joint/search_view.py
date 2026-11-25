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


def _render_tab_buscador_gastos(account: Dict[str, Any], selected_year: int) -> None:
    """
    Buscador global y filtro multicriterio sobre el histórico de gastos comunes.
    Permite filtrar por concepto, rango de fechas, subcategoría, imputación (corriente vs hucha),
    pagador, estado de liquidación y rango de importes, mostrando KPIs agregados y exportación a CSV.
    """
    st.subheader("🔍 Buscador Global y Auditoría de Gastos Comunes")
    st.caption("Localiza y filtra transacciones del hogar en cualquier rango de fechas o categoría.")

    # 1. Obtener catálogos para los filtros
    subcategories_all = api_client.get_joint_subcategories()
    subcat_map = {s["name"]: s["id"] for s in subcategories_all}
    subcat_names = ["Todas las subcategorías"] + sorted(list(subcat_map.keys()))

    funds_all = api_client.get_joint_sinking_funds()
    funds_dict = {f["id"]: f["name"] for f in funds_all}
    subcat_dict = {s["id"]: s["name"] for s in subcategories_all}

    member_a = account.get("member_a_name", "Miembro A")
    member_b = account.get("member_b_name", "Miembro B")

    # 2. Formulario de Filtros
    with st.expander("🛠️ Parámetros de Búsqueda y Filtros", expanded=True):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            query_val = st.text_input(
                "Concepto / Descripción",
                placeholder="Ej. Mercadona, Seguro, Farmacia, IKEA...",
                key="joint_search_query",
            )
        with col2:
            start_date_val = st.date_input(
                "Fecha Desde",
                value=date(selected_year, 1, 1),
                format="DD/MM/YYYY",
                key="joint_search_start_date",
            )
        with col3:
            end_date_val = st.date_input(
                "Fecha Hasta",
                value=date(selected_year, 12, 31),
                format="DD/MM/YYYY",
                key="joint_search_end_date",
            )

        col4, col5, col6, col7 = st.columns(4)
        with col4:
            selected_subcat_name = st.selectbox(
                "Subcategoría",
                options=subcat_names,
                index=0,
                key="joint_search_subcat",
            )
        with col5:
            imputation_opts = ["Todas", "Solo Gastos Corrientes", "Solo Imputados a Hucha"]
            selected_imputation = st.selectbox(
                "Tipo de Imputación",
                options=imputation_opts,
                index=0,
                key="joint_search_imputation",
            )
        with col6:
            payer_opts = ["Todos", "💳 Fondo Común", f"👤 {member_a}", f"👤 {member_b}"]
            selected_payer = st.selectbox(
                "Pagado Por",
                options=payer_opts,
                index=0,
                key="joint_search_payer",
            )
        with col7:
            settle_opts = ["Todos", "🟢 Directos / Liquidados", "🟡 Pendientes de Reembolso"]
            selected_settle = st.selectbox(
                "Estado de Reembolso",
                options=settle_opts,
                index=0,
                key="joint_search_settlement",
            )

        col8, col9, col10 = st.columns([1, 1, 2])
        with col8:
            min_amt_val = st.number_input(
                "Importe Mínimo (€)",
                min_value=0.0,
                value=0.0,
                step=10.0,
                key="joint_search_min_amt",
            )
        with col9:
            max_amt_val = st.number_input(
                "Importe Máximo (€, 0 = sin límite)",
                min_value=0.0,
                value=0.0,
                step=10.0,
                key="joint_search_max_amt",
            )
        with col10:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            search_clicked = st.button("🔎 Buscar Transacciones", key="btn_apply_joint_search", width="stretch")

    # Control de ejecución del buscador
    if "joint_search_active" not in st.session_state:
        st.session_state["joint_search_active"] = False

    if search_clicked:
        st.session_state["joint_search_active"] = True

    # Si aún no se ha usado el buscador, no ejecutar consulta ni mostrar mensaje de 'no encontrado'
    if not st.session_state["joint_search_active"]:
        return

    # 3. Mapeo de parámetros para la consulta
    subcat_id = subcat_map.get(selected_subcat_name) if selected_subcat_name != "Todas las subcategorías" else None

    is_sinking_fund: Optional[bool] = None
    if selected_imputation == "Solo Gastos Corrientes":
        is_sinking_fund = False
    elif selected_imputation == "Solo Imputados a Hucha":
        is_sinking_fund = True

    paid_by_param: Optional[str] = None
    if selected_payer == "💳 Fondo Común":
        paid_by_param = "COMMON"
    elif selected_payer == f"👤 {member_a}":
        paid_by_param = "MEMBER_A"
    elif selected_payer == f"👤 {member_b}":
        paid_by_param = "MEMBER_B"

    settle_param: Optional[str] = None
    if selected_settle == "🟢 Directos / Liquidados":
        settle_param = "SETTLED"
    elif selected_settle == "🟡 Pendientes de Reembolso":
        settle_param = "PENDING"

    min_amt = float(min_amt_val) if min_amt_val > 0 else None
    max_amt = float(max_amt_val) if max_amt_val > 0 else None

    # 4. Ejecución de la búsqueda
    start_str = start_date_val.isoformat() if start_date_val else None
    end_str = end_date_val.isoformat() if end_date_val else None

    results = api_client.search_joint_transactions(
        start_date=start_str,
        end_date=end_str,
        query=query_val.strip() if query_val else None,
        joint_subcategory_id=subcat_id,
        paid_by=paid_by_param,
        settlement_status=settle_param,
        is_sinking_fund=is_sinking_fund,
        min_amount=min_amt,
        max_amount=max_amt,
    )

    st.markdown("---")

    # 5. Visualización de Resultados
    if not results:
        st.info("ℹ️ No se han encontrado gastos que coincidan con los filtros seleccionados.")
        return

    # Métricas agregadas
    total_spent = sum(float(tx.get("amount", 0.0)) for tx in results)
    count_tx = len(results)
    avg_ticket = total_spent / count_tx if count_tx > 0 else 0.0
    common_spent = sum(float(tx.get("amount", 0.0)) for tx in results if tx.get("paid_by") == "COMMON")
    member_a_spent = sum(float(tx.get("amount", 0.0)) for tx in results if tx.get("paid_by") == "MEMBER_A")
    member_b_spent = sum(float(tx.get("amount", 0.0)) for tx in results if tx.get("paid_by") == "MEMBER_B")

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Gastado Encontrado", f"{total_spent:,.2f} €")
    kpi2.metric("Nº de Transacciones", f"{count_tx}")
    kpi3.metric("Ticket Medio", f"{avg_ticket:,.2f} €")
    kpi4.metric(
        "Desglose por Pagador",
        f"Común: {common_spent:,.0f}€ | {member_a}: {member_a_spent:,.0f}€ | {member_b}: {member_b_spent:,.0f}€",
    )

    # Construir tabla
    table_rows = []
    for tx in results:
        subcat_lbl = subcat_dict.get(tx.get("joint_subcategory_id"), "—")
        fund_lbl = funds_dict.get(tx.get("joint_sinking_fund_id"), "Gasto Corriente")
        if tx.get("joint_sinking_fund_id"):
            fund_lbl = f"🎯 Hucha: {fund_lbl}"

        paid_by_val = tx.get("paid_by") or "COMMON"
        if paid_by_val == "MEMBER_A":
            paid_lbl = f"👤 {member_a}"
        elif paid_by_val == "MEMBER_B":
            paid_lbl = f"👤 {member_b}"
        else:
            paid_lbl = "💳 Cuenta Común"

        status_val = tx.get("settlement_status")
        if paid_by_val == "COMMON":
            status_lbl = "🟢 Directo"
        elif status_val == "PENDING":
            mech_val = tx.get("settlement_mechanism")
            mech_short = "Bizum" if mech_val == "DIRECT_MEMBER_SETTLEMENT" else "Cta. Común"
            status_lbl = f"🟡 Pendiente ({mech_short})"
        else:
            status_lbl = "🟢 Reembolsado"

        table_rows.append({
            "Fecha": _format_date_es(tx.get("date")),
            "Concepto / Descripción": tx.get("description"),
            "Subcategoría": subcat_lbl,
            "Imputación": fund_lbl,
            "Pagado Por": paid_lbl,
            "Estado Reembolso": status_lbl,
            "Importe (€)": f"{float(tx.get('amount', 0.0)):,.2f} €",
            "Importe_Num": float(tx.get("amount", 0.0)),
        })

    df_results = pd.DataFrame(table_rows)
    display_cols = ["Fecha", "Concepto / Descripción", "Subcategoría", "Imputación", "Pagado Por", "Estado Reembolso", "Importe (€)"]
    st.dataframe(df_results[display_cols], width="stretch", hide_index=True)

    # Descarga a CSV
    csv_export_cols = ["Fecha", "Concepto / Descripción", "Subcategoría", "Imputación", "Pagado Por", "Estado Reembolso", "Importe_Num"]
    df_export = df_results[csv_export_cols].rename(columns={"Importe_Num": "Importe"})
    csv_bytes = df_export.to_csv(index=False).encode("utf-8-sig")

    start_export_str = start_date_val.strftime("%Y%m%d") if start_date_val else "inicio"
    end_export_str = end_date_val.strftime("%Y%m%d") if end_date_val else "fin"
    st.download_button(
        label="📥 Descargar Resultados en CSV (.csv)",
        data=csv_bytes,
        file_name=f"gastos_comunes_{start_export_str}_{end_export_str}.csv",
        mime="text/csv",
        width="stretch",
        key="btn_download_search_csv",
    )


# =====================================================================
# TAB 5: CONFIGURACIÓN Y SINCRONIZACIÓN

