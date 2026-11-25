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


def render_deepdive_view() -> None:
    """Renderiza la pestaña de Deep Dive Quality Value."""
    st.header("🔬 Análisis Fundamental en Profundidad (Deep Dive)")
    st.caption("Diagnóstico contable cuantitativo a 4 años, algoritmo Piotroski F-Score (0-9) y tesis agéntica Quality Value con IA.")

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
                f"brecha: **{gap:,.2f} €**). La asignación de ahorro hacia instrumentos con riesgo está bloqueada en tus presupuestos. "
                f"Este módulo tiene fines formativos y de diagnóstico contable previo.",
                icon="⚠️",
            )
        else:
            st.info(
                f"🛡️ **Salvaguarda Patrimonial Cumplida**: Tu fondo de emergencia cubre **{cov_months:.1f} meses** de gastos esenciales. "
                f"Asignación de capital a inversión permitida.",
                icon="✅",
            )

    st.markdown("---")

    # 2. SELECTOR DE TICKER Y GESTIÓN DE WATCHLIST
    watchlist_items = api_client.get_watchlist()
    watchlist_tickers = [w["ticker"] for w in watchlist_items] if watchlist_items else []

    col_search, col_watch_sel, col_btn_analizar, col_btn_ref = st.columns([4, 4, 2, 2])

    with col_search:
        ticker_val = st.text_input(
            "Símbolo Bursátil (Ticker)",
            value=st.session_state.get("deepdive_selected_ticker", "ITX.MC"),
            help="Introduce el ticker bursátil con su sufijo de mercado (ej. ITX.MC, SAN.MC, AAPL, MSFT)",
            key="deepdive_input_ticker_field",
        )
        ticker_input = (ticker_val or "").strip().upper()

    with col_watch_sel:
        watch_options = ["-- Seleccionar de Watchlist --"] + [f"{w['ticker']} - {w['name']}" for w in watchlist_items]
        selected_watch = st.selectbox(
            "O carga un valor de tu Watchlist",
            options=watch_options,
            key="deepdive_watchlist_quick_selector",
        )
        if selected_watch != "-- Seleccionar de Watchlist --":
            chosen_ticker = selected_watch.split(" - ")[0].strip().upper()
            if chosen_ticker != ticker_input:
                ticker_input = chosen_ticker
                st.session_state["deepdive_selected_ticker"] = chosen_ticker

    with col_btn_analizar:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        analizar_clicked = st.button("🔍 Analizar", width="stretch", key="btn_deepdive_analyze")

    with col_btn_ref:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        refresh_clicked = st.button("🔄 Refrescar", width="stretch", key="btn_deepdive_refresh")

    # Ejecución o recuperación del análisis
    active_ticker = ticker_input or "ITX.MC"

    if refresh_clicked:
        with st.spinner(f"Invalidando caché y reanalizando {active_ticker}..."):
            data = api_client.refresh_deepdive_analysis(active_ticker)
            if data:
                st.session_state[f"deepdive_data_{active_ticker}"] = data
                st.success(f"¡Análisis de {active_ticker} actualizado con éxito!")
            else:
                st.error(f"No se pudieron refrescar los datos para '{active_ticker}'. Comprueba el ticker y mercado.")
    elif analizar_clicked:
        with st.spinner(f"Cargando diagnóstico financiero para {active_ticker}..."):
            data = api_client.get_deepdive_analysis(active_ticker)
            if data:
                st.session_state[f"deepdive_data_{active_ticker}"] = data
            else:
                st.error(f"No se pudieron encontrar estados financieros para '{active_ticker}'.")

    data = st.session_state.get(f"deepdive_data_{active_ticker}")

    if data:
        # Estado de caché
        if data.get("from_cache"):
            st.caption(f"⚡ Datos servidos desde la caché local de 24h. Última actualización: {_format_datetime_es(data.get('updated_at', ''))}")
        else:
            st.caption(f"✨ Datos actualizados en directo. Fecha de extracción: {_format_datetime_es(data.get('updated_at', ''))}")

        # Cabecera de la empresa
        name = data.get("name") or active_ticker
        sector = data.get("sector") or "General"
        industry = data.get("industry") or ""
        country = data.get("country") or ""
        currency = data.get("currency") or "EUR"
        curr_price = float(data.get("current_price", 0.0))
        day_chg = data.get("day_change_pct")

        chg_str = f"{day_chg:+.2f}%" if day_chg is not None else ""

        col_h1, col_h2 = st.columns([9, 3])
        with col_h1:
            st.subheader(f"{name} ({active_ticker})")
            st.write(f"🏢 **Sector**: {sector} | 🏭 **Industria**: {industry} | 📍 **País**: {country} | 💱 **Divisa**: {currency}")
            if data.get("description"):
                with st.expander("📖 Descripción del Negocio", expanded=False):
                    st.write(data["description"])

        with col_h2:
            st.metric("Cotización Actual", f"{curr_price:,.2f} {currency}", delta=chg_str)

        st.markdown("---")

        # 3. FILA DE MÉTRICAS CLAVE Y MÚLTIPLOS (KPIs)
        m_cap = data.get("market_cap")
        if m_cap:
            if m_cap >= 1e9:
                m_cap_str = f"{m_cap / 1e9:,.2f} B {currency}"
            else:
                m_cap_str = f"{m_cap / 1e6:,.2f} M {currency}"
        else:
            m_cap_str = "N/D"

        pe_t = data.get("pe_trailing")
        pe_f = data.get("pe_forward")
        ev_ebitda = data.get("ev_to_ebitda")
        pb = data.get("price_to_book")
        div_y = data.get("dividend_yield")
        fcf_m = data.get("fcf_metrics") or {}
        fcf_y = fcf_m.get("fcf_yield")
        roe = fcf_m.get("roe")
        roic = fcf_m.get("roic")

        kpi_cols = st.columns(6)
        kpi_cols[0].metric("Cap. Bursátil", m_cap_str)
        kpi_cols[1].metric("PER Trailing", f"{pe_t:.1f}x" if pe_t is not None else "N/D")
        kpi_cols[2].metric("EV/EBITDA", f"{ev_ebitda:.1f}x" if ev_ebitda is not None else "N/D")
        kpi_cols[3].metric("Price / Book", f"{pb:.1f}x" if pb is not None else "N/D")
        kpi_cols[4].metric("FCF Yield", f"{fcf_y:.1f}%" if fcf_y is not None else "N/D")
        kpi_cols[5].metric("ROE / ROIC", f"{roe:.1f}% / {roic:.1f}%" if roe is not None and roic is not None else "N/D")

        st.markdown("---")

        # 4. DIAGNÓSTICO PIOTROSKI F-SCORE (0 A 9 PUNTOS)
        piotroski = data.get("piotroski") or {}
        total_p = piotroski.get("total_score", 0)
        max_p = piotroski.get("max_score", 9)
        rating_p = piotroski.get("rating", "Aceptable")

        col_piot_score, col_piot_desc = st.columns([4, 8])
        with col_piot_score:
            if rating_p == "Excelente":
                st.success(f"### Piotroski F-Score: {total_p} / {max_p}\n**Salud Contable Excelente** 🟢")
            elif rating_p == "Aceptable":
                st.warning(f"### Piotroski F-Score: {total_p} / {max_p}\n**Salud Contable Aceptable** 🟡")
            else:
                st.error(f"### Piotroski F-Score: {total_p} / {max_p}\n**Riesgo Contable / Debilidad** 🔴")

            if data.get("is_financial_institution"):
                st.caption("ℹ️ *Entidad Financiera (Banco/Seguros): Puntuación adaptada a 7 criterios al no aplicar Margen Bruto ni Ratio Corriente.*")

        with col_piot_desc:
            with st.expander("📋 Ver Desglose de los Criterios Contables Evaluados", expanded=True):
                criteria_list = piotroski.get("criteria", [])
                if criteria_list:
                    p_data = []
                    for c in criteria_list:
                        icon = "✅ Cumple (1 pto)" if c.get("points") == 1 else "❌ No cumple (0 ptos)"
                        p_data.append({
                            "Regla": c.get("code"),
                            "Categoría": c.get("category", "").capitalize(),
                            "Evaluación": icon,
                            "Descripción": c.get("description"),
                        })
                    st.dataframe(pd.DataFrame(p_data), width="stretch", hide_index=True)

        st.markdown("---")

        # 5. GRÁFICOS HISTÓRICOS Y EVOLUCIÓN CONTABLE
        statements = data.get("statements", [])
        if statements:
            st.subheader("📊 Historial Financiero Consolidado")

            df_hist = pd.DataFrame(statements)
            df_hist_sorted = df_hist.sort_values("year", ascending=True).copy()

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("**Evolución de Ingresos y Beneficio Neto (€)**")
                chart_data_rev = df_hist_sorted[["year", "revenue", "net_income"]].copy()
                chart_data_rev["year"] = chart_data_rev["year"].astype(str)
                chart_rev = alt.Chart(chart_data_rev).transform_fold(
                    ["revenue", "net_income"], as_=["Métrica", "Importe"]
                ).mark_bar().encode(
                    x=alt.X("year:O", title="Año"),
                    y=alt.Y("Importe:Q", title="Importe (€)"),
                    color=alt.Color("Métrica:N", scale=alt.Scale(domain=["revenue", "net_income"], range=["#1565c0", "#2e7d32"])),
                    xOffset="Métrica:N",
                    tooltip=["year:O", "Métrica:N", alt.Tooltip("Importe:Q", format=",.0f")]
                ).properties(height=280)
                st.altair_chart(chart_rev, width="stretch")

            with col_g2:
                st.markdown("**Generación de Flujos de Caja: CFO vs CapEx vs FCF (€)**")
                chart_data_cf = df_hist_sorted[["year", "operating_cash_flow", "capital_expenditure", "free_cash_flow"]].copy()
                chart_data_cf["year"] = chart_data_cf["year"].astype(str)
                chart_cf = alt.Chart(chart_data_cf).transform_fold(
                    ["operating_cash_flow", "capital_expenditure", "free_cash_flow"], as_=["Flujo", "Importe"]
                ).mark_line(point=True).encode(
                    x=alt.X("year:O", title="Año"),
                    y=alt.Y("Importe:Q", title="Importe (€)"),
                    color=alt.Color("Flujo:N", scale=alt.Scale(domain=["operating_cash_flow", "capital_expenditure", "free_cash_flow"], range=["#00838f", "#ef6c00", "#2e7d32"])),
                    tooltip=["year:O", "Flujo:N", alt.Tooltip("Importe:Q", format=",.0f")]
                ).properties(height=280)
                st.altair_chart(chart_cf, width="stretch")

            # Tabla resumen de estados contables
            with st.expander("📑 Ver Tabla Completa de Estados Financieros Históricos"):
                disp_cols = [
                    "year", "revenue", "gross_profit", "operating_income", "net_income",
                    "operating_cash_flow", "capital_expenditure", "free_cash_flow",
                    "total_assets", "total_debt", "cash_and_equivalents"
                ]
                existing_cols = [c for c in disp_cols if c in df_hist.columns]
                df_table = df_hist[existing_cols].copy()
                table_rename_map = {
                    "year": "Año",
                    "revenue": "Ingresos",
                    "gross_profit": "Beneficio Bruto",
                    "operating_income": "EBIT / Beneficio Op.",
                    "net_income": "Beneficio Neto",
                    "operating_cash_flow": "CFO (Caja Operativa)",
                    "capital_expenditure": "CapEx",
                    "free_cash_flow": "FCF (Caja Libre)",
                    "total_assets": "Activo Total",
                    "total_debt": "Deuda Total",
                    "cash_and_equivalents": "Efectivo",
                }
                df_table.columns = [table_rename_map.get(str(c), str(c)) for c in df_table.columns]
                st.dataframe(df_table, width="stretch", hide_index=True)

        st.markdown("---")

        # 6. INFORME AGÉNTICO QUALITY VALUE (IA CON GEMINI)
        st.subheader("🤖 Tesis Agéntica de Inversión (Quality Value)")
        report = data.get("quality_value_report")

        if report:
            quadrant = report.get("quadrant", "Quality Value")
            if quadrant == "Quality Value":
                st.markdown(
                    f"<div class='quadrant-quality-value'><h3>💎 Cuadrante: {quadrant}</h3>"
                    f"<p>Excelente negocio con retornos sostenibles sobre el capital, foso defensivo y cotizando a múltiplo razonable.</p></div>",
                    unsafe_allow_html=True,
                )
            elif quadrant == "Calidad Cara":
                st.markdown(
                    f"<div class='quadrant-calidad-cara'><h3>⭐ Cuadrante: {quadrant}</h3>"
                    f"<p>Gran negocio con sólidas ventajas competitivas pero cotizando a múltiplos muy exigentes que reducen el margen de seguridad.</p></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div class='quadrant-trampa-valor'><h3>⚠️ Cuadrante: {quadrant}</h3>"
                    f"<p>Negocio aparentemente barato por múltiplos simples pero con deterioro estructural de foso o quema de caja.</p></div>",
                    unsafe_allow_html=True,
                )

            st.markdown(f"**Tesis Ejecutiva**: {report.get('summary_thesis')}")

            # 6 Ingredientes
            st.markdown("#### 🔍 Evaluación de los 6 Ingredientes Clave")
            ingredients = report.get("six_ingredients") or {}
            ing_cols1, ing_cols2 = st.columns(2)
            with ing_cols1:
                st.info(f"**📈 Crecimiento a Largo Plazo**: {ingredients.get('long_term_growth', 'N/D')}")
                st.info(f"**🌬️ Vientos de Cola**: {ingredients.get('tailwinds', 'N/D')}")
                st.info(f"**👑 Liderazgo de Mercado**: {ingredients.get('market_leadership', 'N/D')}")
            with ing_cols2:
                st.info(f"**🏰 Foso Defensivo (Moat)**: {ingredients.get('moat', 'N/D')}")
                st.info(f"**💰 Rentabilidad sobre Capital (ROIC/ROE)**: {ingredients.get('high_returns_on_capital', 'N/D')}")
                st.info(f"**⏳ Dificultades Temporales / Descuento**: {ingredients.get('temporary_headwinds', 'N/D')}")

            # Doble Tesis y Matriz de Riesgos
            st.markdown("#### 🛡️ Matriz de Riesgos: \"¿Qué puede salir mal y cuánto beneficio destruiría?\"")
            b_model = report.get("business_model_and_risks") or {}
            if b_model:
                st.write(f"**Dinámica de Negocio**: {b_model.get('business_model', b_model.get('cash_cycle', 'Generación recurrente de caja.'))}")

            bearish = report.get("bearish_risks") or []
            for r in bearish:
                st.error(f"🔻 **Riesgo Bajista**: {r}")

            # Valoración y Zona de Entrada por TIR
            st.markdown("#### 🎯 Valoración a 5 Años y Zona de Entrada Ideal (TIR 15% - 20%)")
            target_zone = report.get("target_irr_entry_zone", "N/D")

            # 1. Tarjeta destacada de Zona de Compra con Margen de Seguridad
            st.markdown(
                f"<div class='valuation-entry-zone-card'>"
                f"<div style='display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;'>"
                f"  <div>"
                f"    <span style='font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; color: #2e7d32;'>🎯 Zona de Compra con Margen de Seguridad</span>"
                f"    <div style='font-size: 1.45rem; font-weight: 800; margin-top: 0.2rem;'>{target_zone}</div>"
                f"  </div>"
                f"  <div style='text-align: right;'>"
                f"    <span style='font-size: 0.82rem; color: gray;'>Cotización Actual</span>"
                f"    <div style='font-size: 1.25rem; font-weight: 700;'>{curr_price:,.2f} {currency}</div>"
                f"  </div>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # 2. Análisis y Comparación de Escenarios Proyectados a 5 Años
            val_proj = report.get("valuation_projections") or {}

            def _clean_val(val):
                if val is None:
                    return None
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, str):
                    clean = val.replace("€", "").replace("$", "").replace("%", "").replace("x", "").replace("X", "").strip()
                    try:
                        return float(clean)
                    except ValueError:
                        return None
                return None

            base_raw = val_proj.get("scenario_base") or val_proj.get("base") or {}
            stress_raw = val_proj.get("scenario_stress") or val_proj.get("stress") or {}

            base_target = _clean_val(base_raw.get("target_price", base_raw.get("precio_objetivo")))
            base_pe = _clean_val(base_raw.get("exit_multiple", base_raw.get("multiplo_salida")))
            base_irr = _clean_val(base_raw.get("expected_irr", base_raw.get("tir_esperada", base_raw.get("irr"))))

            stress_target = _clean_val(stress_raw.get("target_price", stress_raw.get("precio_objetivo")))
            stress_pe = _clean_val(stress_raw.get("exit_multiple", stress_raw.get("multiplo_salida")))
            stress_irr = _clean_val(stress_raw.get("expected_irr", stress_raw.get("tir_esperada", stress_raw.get("irr"))))

            delta_base_str = None
            delta_stress_str = None

            if base_target is not None or stress_target is not None:
                col_sc_base, col_sc_stress = st.columns(2)

                with col_sc_base:
                    st.markdown(
                        "<div class='valuation-scenario-card valuation-scenario-card-base'>"
                        "<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;'>"
                        "  <strong style='font-size: 1.05rem;'>📈 Escenario Base (Central)</strong>"
                        "  <span class='valuation-badge-base'>Probabilidad Central</span>"
                        "</div>"
                        "<p style='font-size: 0.84rem; color: gray; margin-bottom: 0.75rem;'>"
                        "Crecimiento secular de ingresos, mantenimiento de márgenes operativos y conversión de caja sólida a 5 años."
                        "</p>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    m1, m2, m3 = st.columns(3)
                    delta_base = ((base_target - curr_price) / curr_price * 100.0) if (base_target and curr_price) else None
                    delta_base_str = f"{delta_base:+.1f}%" if delta_base is not None else None
                    m1.metric("Precio Obj. 5A", f"{base_target:,.2f} {currency}" if base_target else "N/D", delta=delta_base_str)
                    m2.metric("TIR Esperada", f"{base_irr:.1f}% / año" if base_irr is not None else "N/D", help="Tasa Interna de Retorno anualizada esperada a 5 años")
                    m3.metric("Múltiplo PER", f"{base_pe:.1f}x" if base_pe is not None else "N/D", help="Múltiplo de salida proyectado al año 5")

                with col_sc_stress:
                    st.markdown(
                        "<div class='valuation-scenario-card valuation-scenario-card-stress'>"
                        "<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;'>"
                        "  <strong style='font-size: 1.05rem;'>🛡️ Escenario de Estrés (Conservador)</strong>"
                        "  <span class='valuation-badge-stress'>Margen de Seguridad</span>"
                        "</div>"
                        "<p style='font-size: 0.84rem; color: gray; margin-bottom: 0.75rem;'>"
                        "Compresión de múltiplos por tipos altos, desaceleración macro o presiones competitivas transitorias."
                        "</p>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    s1, s2, s3 = st.columns(3)
                    delta_stress = ((stress_target - curr_price) / curr_price * 100.0) if (stress_target and curr_price) else None
                    delta_stress_str = f"{delta_stress:+.1f}%" if delta_stress is not None else None
                    s1.metric("Precio Obj. 5A", f"{stress_target:,.2f} {currency}" if stress_target else "N/D", delta=delta_stress_str)
                    s2.metric("TIR Esperada", f"{stress_irr:.1f}% / año" if stress_irr is not None else "N/D", help="Tasa Interna de Retorno anualizada en escenario de estrés")
                    s3.metric("Múltiplo PER", f"{stress_pe:.1f}x" if stress_pe is not None else "N/D", help="Múltiplo de salida comprimido al año 5")

                # Tabla Comparativa Sintética
                summary_data = [
                    {
                        "Métrica Financiera a 5 Años": "Precio Objetivo por Acción",
                        "Escenario de Estrés 🛡️": f"{stress_target:,.2f} {currency} ({delta_stress_str})" if stress_target else "N/D",
                        "Cotización Actual 📍": f"{curr_price:,.2f} {currency}",
                        "Escenario Base 📈": f"{base_target:,.2f} {currency} ({delta_base_str})" if base_target else "N/D",
                        "Zona de Entrada Óptima 🎯": target_zone,
                    },
                    {
                        "Métrica Financiera a 5 Años": "Múltiplo de Salida (PER)",
                        "Escenario de Estrés 🛡️": f"{stress_pe:.1f}x" if stress_pe else "N/D",
                        "Cotización Actual 📍": f"{pe_t:.1f}x" if pe_t is not None else "N/D",
                        "Escenario Base 📈": f"{base_pe:.1f}x" if base_pe else "N/D",
                        "Zona de Entrada Óptima 🎯": "Margen de Seguridad",
                    },
                    {
                        "Métrica Financiera a 5 Años": "Rentabilidad Anual Compuesta (TIR)",
                        "Escenario de Estrés 🛡️": f"{stress_irr:.1f}% / año" if stress_irr is not None else "N/D",
                        "Cotización Actual 📍": "—",
                        "Escenario Base 📈": f"{base_irr:.1f}% / año" if base_irr is not None else "N/D",
                        "Zona de Entrada Óptima 🎯": "15.0% - 20.0% / año",
                    },
                ]
                st.dataframe(pd.DataFrame(summary_data), width="stretch", hide_index=True)

            if val_proj:
                with st.expander("🔎 Ver JSON técnico estructurado"):
                    st.json(val_proj)
        else:
            st.info(
                "ℹ️ **Síntesis Agéntica con IA no disponible**: Los datos cuantitativos, ratios contables y Piotroski Score "
                "están calculados con precisión matemática local en Python. La generación de la tesis cualitativa requiere configurar "
                "la clave `GEMINI_API_KEY` en tu archivo `.env`.",
                icon="ℹ️",
            )

        st.markdown("---")

        # 7. GESTIÓN DE LA WATCHLIST PARA EL VALOR ACTUAL
        st.subheader("⭐ Lista de Seguimiento (Watchlist)")
        is_in_watch = active_ticker in watchlist_tickers

        col_w_info, col_w_act = st.columns([8, 4])
        with col_w_info:
            if is_in_watch:
                matched_w = [w for w in watchlist_items if w["ticker"] == active_ticker][0]
                st.write(f"📌 **Guardado en Watchlist**: Añadido a **{matched_w.get('price_at_addition', 0):,.2f} {currency}**.")
                if matched_w.get("notes"):
                    st.caption(f"📝 Notas: {matched_w['notes']}")
            else:
                st.write(f"Este activo no está en tu lista de seguimiento.")

        with col_w_act:
            if is_in_watch:
                if st.button("🗑️ Eliminar de Watchlist", key="btn_del_from_watchlist"):
                    if api_client.remove_from_watchlist(active_ticker):
                        st.success(f"¡{active_ticker} eliminado de la Watchlist!")
                        st.rerun()
                    else:
                        st.error("Error al eliminar el activo.")
            else:
                notes_input = st.text_input("Notas u objetivo de compra", key="notes_for_watchlist")
                if st.button("⭐ Añadir a Watchlist", key="btn_add_to_watchlist"):
                    add_payload = {
                        "ticker": active_ticker,
                        "name": name,
                        "sector": sector,
                        "currency": currency,
                        "price_at_addition": curr_price,
                        "notes": notes_input or None,
                    }
                    res_add = api_client.add_to_watchlist(add_payload)
                    if res_add:
                        st.success(f"¡{active_ticker} guardado en tu Watchlist!")
                        st.rerun()
                    else:
                        st.error("Error al guardar en Watchlist.")

        # 8. DESCARGO LEGAL AL PIE (Principio 10 de la Constitución)
        st.markdown("---")
        st.caption(
            "⚖️ **Descargo Legal (Disclaimer)**: Esta herramienta de diagnóstico y la síntesis generada por IA "
            "tienen carácter exclusivamente formativo e informativo. No constituyen recomendación de compra o venta "
            "ni asesoramiento financiero regulado. Los rendimientos pasados no garantizan rentabilidades futuras."
        )
    else:
        st.info(
            "💡 Introduce un ticker (ej. `ITX.MC`, `SAN.MC`, `AAPL`) o selecciona una empresa de tu Watchlist "
            "y pulsa **[🔍 Analizar]** para cargar su diagnóstico fundamental en profundidad bajo demanda.",
            icon="ℹ️"
        )


# ==========================================
# PESTAÑA 17: COPILOTO PATRIMONIAL (SPEC 004)
# ==========================================
