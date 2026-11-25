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


def render_screener_view() -> None:
    """Renderiza la pestaña de Screener de Inversión."""
    col_sc_head, col_sc_btn = st.columns([8, 3])
    with col_sc_head:
        st.header("🔍 Screener Fundamental y Oportunidades de Inversión")
        st.caption("Cribado cuantitativo de renta variable y ETFs indexados con ratios contables, presets estratégicos y caché local de 24h.")
    with col_sc_btn:
        st.write("")

    # 1. SALVAGUARDA DE SEGURIDAD (Principio 9 de la Constitución)
    safety_status = api_client.get_safety_status(mes="BASE")
    if safety_status:
        is_safe = safety_status.get("is_safe", True)
        cov_months = float(safety_status.get("coverage_months", 0.0))
        target_months = float(safety_status.get("target_months", 3.0))
        gap = float(safety_status.get("gap", 0.0))

        if not is_safe or cov_months < 3.0:
            st.warning(
                f"⚠️ **Aviso de Salvaguarda Patrimonial (Principio 9 - Constitución)**: Tu fondo de emergencia actual cubre "
                f"**{cov_months:.1f} meses** de gastos esenciales (mínimo constitucional: **{target_months:.1f} meses**; "
                f"brecha por cubrir: **{gap:,.2f} €**). La asignación de ahorro hacia instrumentos con riesgo está bloqueada "
                f"en tus presupuestos. Este screener tiene fines formativos y de seguimiento de mercado.",
                icon="⚠️",
            )
        else:
            st.info(
                f"🛡️ **Salvaguarda Patrimonial Cumplida**: Tu fondo de emergencia cubre **{cov_months:.1f} meses** de gastos esenciales. "
                f"Asignación de capital a inversión permitida.",
                icon="✅",
            )

    st.markdown("---")

    # 2. SELECTOR DE UNIVERSO Y CONTROLES DE CACHÉ
    universe_options = {
        "ibex35": "🇪🇸 IBEX 35 (35 Acciones España)",
        "eurostoxx50": "🇪🇺 EuroStoxx 50 (50 Líderes Eurozona)",
        "sp500_top50": "🇺🇸 S&P 500 Top 50 (50 Mega-caps EE.UU.)",
        "etfs_referencia": "📈 ETFs de Referencia UCITS (15 Fondos Indexados)",
        "custom": "⚙️ Tickers Personalizados (Cesta a Medida)",
    }

    col_u_sel, col_u_ref = st.columns([8, 3])
    with col_u_sel:
        selected_universe = st.selectbox(
            "Selecciona el Universo de Activos a Inspeccionar",
            options=list(universe_options.keys()),
            format_func=lambda x: universe_options[x],
            key="screener_universe_selector",
        )
    with col_u_ref:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if selected_universe != "custom":
            if st.button("🔄 Actualizar Universo", width="stretch", key="btn_refresh_screener_univ"):
                with st.spinner("Descargando datos actualizados desde Yahoo Finance..."):
                    ref_res = api_client.refresh_screener_universe(selected_universe)
                    if ref_res:
                        st.success("¡Universo actualizado con éxito!")
                        st.rerun()
                    else:
                        st.error("Error al actualizar los datos del universo.")

    custom_tickers_list = []
    if selected_universe == "custom":
        custom_input = st.text_input(
            "Introduce tickers separados por coma (ej. ITX.MC, SAN.MC, AAPL, VWCE.DE)",
            value="ITX.MC, SAN.MC, AAPL, VWCE.DE",
            key="screener_custom_tickers_input",
        )
        custom_tickers_list = [t.strip().upper() for t in custom_input.split(",") if t.strip()]

    # 3. PRESETS RÁPIDOS Y ESTRATEGIAS
    if selected_universe == "etfs_referencia":
        preset_map = {
            "all": "Todos los ETFs",
            "low_cost_etf": "🛡️ ETFs de Bajo Coste (TER ≤ 0.25%, AUM ≥ 500M)",
            "high_dividend": "💰 Alto Dividendo (Yield ≥ 3.5%)",
        }
    else:
        preset_map = {
            "all": "Todos los valores",
            "quality": "💎 Calidad y Solvencia (ROE ≥ 15%, Margen ≥ 10%, Deuda ≤ 120%)",
            "high_dividend": "💰 Alto Dividendo (Yield ≥ 3.5%, PER Fwd ≤ 18)",
            "value": "🏷️ Valoración Atractiva (PER ≤ 15, P/B ≤ 2.0)",
            "growth": "🚀 Crecimiento (Margen Op ≥ 15%, ROE ≥ 12%, Beta ≥ 0.9)",
        }

    selected_preset = st.radio(
        "Estrategia Cuantitativa Rápida (Preset)",
        options=list(preset_map.keys()),
        format_func=lambda x: preset_map[x],
        horizontal=True,
        key="screener_preset_radio",
    )

    # 4. FILTROS AVANZADOS MANUALES
    with st.expander("⚙️ Filtros Manuales Avanzados", expanded=False):
        col_f_search, col_f_empty = st.columns([6, 6])
        with col_f_search:
            search_text = st.text_input("Buscar por Ticker, Compañía o Sector", key="screener_search_query_input")

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            filter_max_pe = st.number_input("PER Máximo", min_value=1.0, max_value=200.0, value=None, step=1.0, key="sc_max_pe")
        with col_f2:
            filter_min_div = st.number_input("Dividendo Mínimo (%)", min_value=0.0, max_value=25.0, value=None, step=0.5, key="sc_min_div")
        with col_f3:
            filter_min_roe = st.number_input("ROE Mínimo (%)", min_value=0.0, max_value=100.0, value=None, step=1.0, key="sc_min_roe")
        with col_f4:
            if selected_universe == "etfs_referencia":
                filter_max_ter = st.number_input("TER Máximo (%)", min_value=0.01, max_value=2.0, value=None, step=0.05, key="sc_max_ter")
                filter_max_debt = None
            else:
                filter_max_debt = st.number_input("Deuda/Patrimonio Máx. (%)", min_value=0.0, max_value=500.0, value=None, step=10.0, key="sc_max_debt")
                filter_max_ter = None

    # 5. OBTENCIÓN Y RENDERIZADO DE DATOS
    screener_data = None
    if selected_universe == "custom":
        if custom_tickers_list:
            filter_params_dict = {
                "preset": selected_preset,
                "search_query": search_text if search_text else None,
                "max_pe": filter_max_pe,
                "min_dividend_yield": filter_min_div,
                "min_roe": filter_min_roe,
                "max_debt_to_equity": filter_max_debt,
                "max_expense_ratio": filter_max_ter,
            }
            screener_data = api_client.get_screener_custom(custom_tickers_list, filter_params=filter_params_dict)
    else:
        screener_data = api_client.get_screener_universe(
            universe_id=selected_universe,
            preset=selected_preset if selected_preset != "all" else None,
            max_pe=filter_max_pe,
            min_dividend_yield=filter_min_div,
            min_roe=filter_min_roe,
            max_debt_to_equity=filter_max_debt,
            max_expense_ratio=filter_max_ter,
            search_query=search_text if search_text else None,
        )

    if not screener_data or "items" not in screener_data:
        st.info("Cargando activos del universo... Si es la primera vez que se consulta, puede demorarse unos segundos.")
    else:
        cached_tag = "📦 Desde caché local (24h)" if screener_data.get("from_cache") else "⚡ Datos en vivo"
        fetch_time = _format_datetime_es(screener_data.get("updated_at", ""))
        tot_c = screener_data.get("total_count", 0)
        filt_c = screener_data.get("filtered_count", 0)

        st.caption(f"{cached_tag} | Captura: {fetch_time} | Mostrando **{filt_c}** de **{tot_c}** activos disponibles")

        items_list = screener_data.get("items", [])
        if not items_list:
            st.warning("Ningún activo cumple con los criterios de filtrado seleccionados.")
        else:
            df_screener = pd.DataFrame(items_list)
            is_etf_view = selected_universe == "etfs_referencia"

            if is_etf_view:
                col_order = [
                    "ticker", "name", "category", "currency", "price", "change_pct",
                    "expense_ratio", "dividend_yield", "total_assets", "avg_volume", "beta"
                ]
                existing_cols = [c for c in col_order if c in df_screener.columns]
                df_view = df_screener[existing_cols].copy()
                etf_rename_map = {
                    "ticker": "Ticker",
                    "name": "Nombre ETF",
                    "category": "Categoría",
                    "currency": "Divisa",
                    "price": "Precio",
                    "change_pct": "Var. Diaria",
                    "expense_ratio": "TER (Costes)",
                    "dividend_yield": "Div. Yield",
                    "total_assets": "Patrimonio (AUM)",
                    "avg_volume": "Volumen Medio",
                    "beta": "Beta",
                }
                df_view.columns = [etf_rename_map.get(str(c), str(c)) for c in df_view.columns]

                col_config = {
                    "Precio": st.column_config.NumberColumn(format="%.2f"),
                    "Var. Diaria": st.column_config.NumberColumn(format="%.2f %%"),
                    "TER (Costes)": st.column_config.NumberColumn(format="%.2f %%"),
                    "Div. Yield": st.column_config.NumberColumn(format="%.2f %%"),
                    "Patrimonio (AUM)": st.column_config.NumberColumn(format="%,.0f €"),
                    "Volumen Medio": st.column_config.NumberColumn(format="%,.0f"),
                    "Beta": st.column_config.NumberColumn(format="%.2f"),
                }
            else:
                col_order = [
                    "ticker", "name", "sector", "currency", "price", "change_pct",
                    "pe_trailing", "pe_forward", "pb_ratio", "ev_to_ebitda",
                    "dividend_yield", "roe", "operating_margin", "net_margin",
                    "debt_to_equity", "beta"
                ]
                existing_cols = [c for c in col_order if c in df_screener.columns]
                df_view = df_screener[existing_cols].copy()
                stock_rename_map = {
                    "ticker": "Ticker",
                    "name": "Compañía",
                    "sector": "Sector",
                    "currency": "Divisa",
                    "price": "Precio",
                    "change_pct": "Var. Diaria",
                    "pe_trailing": "PER (Hist.)",
                    "pe_forward": "PER (Adel.)",
                    "pb_ratio": "P/B",
                    "ev_to_ebitda": "EV/EBITDA",
                    "dividend_yield": "Div. Yield",
                    "roe": "ROE",
                    "operating_margin": "Margen Op.",
                    "net_margin": "Margen Neto",
                    "debt_to_equity": "Deuda/Patr.",
                    "beta": "Beta",
                }
                df_view.columns = [stock_rename_map.get(str(c), str(c)) for c in df_view.columns]

                col_config = {
                    "Precio": st.column_config.NumberColumn(format="%.2f"),
                    "Var. Diaria": st.column_config.NumberColumn(format="%.2f %%"),
                    "PER (Hist.)": st.column_config.NumberColumn(format="%.2f x"),
                    "PER (Adel.)": st.column_config.NumberColumn(format="%.2f x"),
                    "P/B": st.column_config.NumberColumn(format="%.2f x"),
                    "EV/EBITDA": st.column_config.NumberColumn(format="%.2f x"),
                    "Div. Yield": st.column_config.NumberColumn(format="%.2f %%"),
                    "ROE": st.column_config.NumberColumn(format="%.2f %%"),
                    "Margen Op.": st.column_config.NumberColumn(format="%.2f %%"),
                    "Margen Neto": st.column_config.NumberColumn(format="%.2f %%"),
                    "Deuda/Patr.": st.column_config.NumberColumn(format="%.2f %%"),
                    "Beta": st.column_config.NumberColumn(format="%.2f"),
                }

            st.dataframe(
                df_view,
                width="stretch",
                hide_index=True,
                column_config=col_config,
            )

            # Botón de Descarga en CSV
            csv_data = df_view.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="📥 Exportar Resultados a CSV",
                data=csv_data,
                file_name=f"screener_{selected_universe}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                key="btn_download_screener_csv",
            )


# ==========================================
# PESTAÑA 16: ANÁLISIS FUNDAMENTAL (DEEP DIVE)
# ==========================================
