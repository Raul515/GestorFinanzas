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


def render_market_radar_view() -> None:
    """Renderiza la pestaña de Radar Macroeconómico y Noticias IA."""
    col_r_title, col_r_btn = st.columns([3, 1])
    with col_r_title:
        st.header("🌐 Radar Macroeconómico y Noticias")
        st.caption("Monitor ejecutivo de mercados con foco prioritario en España y la Eurozona, y canal de noticias financieras depurado con IA.")
    with col_r_btn:
        if st.button("🔄 Actualizar Radar", width="stretch", key="btn_refresh_radar"):
            with st.spinner("Actualizando indicadores y analizando noticias financieras..."):
                refresh_res = api_client.refresh_market_radar()
                if refresh_res:
                    st.success("¡Radar actualizado con éxito!")
                    st.rerun()
                else:
                    st.error("Error al actualizar el radar de mercado. Verifica la conexión con el backend.")

    # Función auxiliar para renderizar sparklines de 30 días con Altair
    def _render_sparkline_chart(values_list, height=55):
        if not values_list or len(values_list) < 2:
            return None
        df_sp = pd.DataFrame({"dia": list(range(len(values_list))), "valor": values_list})
        is_pos = values_list[-1] >= values_list[0]
        line_color = "#2e7d32" if is_pos else "#d32f2f"
        min_v = min(values_list) * 0.998
        max_v = max(values_list) * 1.002
        return (
            alt.Chart(df_sp)
            .mark_line(color=line_color, strokeWidth=2)
            .encode(
                x=alt.X("dia:Q", axis=None),
                y=alt.Y("valor:Q", scale=alt.Scale(domain=[min_v, max_v]), axis=None),
                tooltip=[alt.Tooltip("valor:Q", format=",.2f", title="Valor")],
            )
            .properties(height=height)
            .configure_view(strokeWidth=0)
        )

    st.markdown("---")

    # 1. BLOQUE MACROECONÓMICO (Índices, Deuda Soberana y Prima de Riesgo)
    st.subheader("📊 Monitor Macroeconómico y Tipos de Interés")
    macro_data = api_client.get_macro_indicators()

    if not macro_data or not macro_data.get("indicators"):
        st.info("No se pudieron cargar los indicadores macroeconómicos. Pulsa '🔄 Actualizar Radar' para sincronizar con los proveedores.")
    else:
        cached_tag = "📦 Desde caché local (24h)" if macro_data.get("is_cached") else "⚡ Datos en vivo"
        fetch_time = _format_datetime_es(macro_data.get("fetched_at", ""))
        st.caption(f"{cached_tag} | Captura: {fetch_time} | {macro_data.get('source_notes', '')}")

        indicators_by_id = {ind["id"]: ind for ind in macro_data.get("indicators", [])}

        # Sub-bloque A: España y Eurozona (Prioridad Máxima)
        st.markdown("##### 🇪🇸 España y Eurozona")
        col_es_ids = ["ibex35", "bono_es_10y", "prima_riesgo_es", "bund_10y", "stoxx50"]
        cols_es = st.columns(len(col_es_ids))

        for idx_col, ind_id in enumerate(col_es_ids):
            with cols_es[idx_col]:
                ind = indicators_by_id.get(ind_id)
                if ind:
                    val = ind["current_value"]
                    unit = ind.get("unit", "")
                    val_str = f"{val:,.2f} {unit}" if unit != "pb" else f"{int(val)} pb"
                    chg_pct = ind.get("change_pct", 0.0)
                    chg_abs = ind.get("change_abs", 0.0)
                    delta_str = f"{chg_pct:+.2f}% ({chg_abs:+.2f})"

                    st.metric(label=ind["name"], value=val_str, delta=delta_str)
                    chart = _render_sparkline_chart(ind.get("sparkline_30d", []))
                    if chart:
                        st.altair_chart(chart, width="stretch")

        st.markdown("<br>", unsafe_allow_html=True)

        # Sub-bloque B: Referencias Globales (EE.UU.)
        st.markdown("##### 🌍 Referencias Globales (EE.UU.)")
        col_global_ids = ["sp500", "nasdaq100", "bono_us_10y"]
        cols_global = st.columns(3)

        for idx_col, ind_id in enumerate(col_global_ids):
            with cols_global[idx_col]:
                ind = indicators_by_id.get(ind_id)
                if ind:
                    val = ind["current_value"]
                    unit = ind.get("unit", "")
                    val_str = f"{val:,.2f} {unit}"
                    chg_pct = ind.get("change_pct", 0.0)
                    chg_abs = ind.get("change_abs", 0.0)
                    delta_str = f"{chg_pct:+.2f}% ({chg_abs:+.2f})"

                    st.metric(label=ind["name"], value=val_str, delta=delta_str)
                    chart = _render_sparkline_chart(ind.get("sparkline_30d", []))
                    if chart:
                        st.altair_chart(chart, width="stretch")

    st.markdown("---")

    # 2. BLOQUE DE NOTICIAS DEPURADAS POR IA
    st.subheader("📰 Canal de Noticias y Pulso Económico (Perspectiva España)")
    news_data = api_client.get_market_news(limit=15)

    if not news_data or not news_data.get("news"):
        st.info("No hay noticias almacenadas actualmente. Pulsa '🔄 Actualizar Radar' para descargar y analizar los titulares.")
    else:
        ai_available = news_data.get("ai_analysis_available", False)
        if ai_available:
            st.caption("✨ Síntesis y análisis de impacto generados con inteligencia artificial (Google Gemini Pro).")
        else:
            st.warning("⚠️ Análisis de IA no disponible temporalmente. Mostrando titulares públicos.")

        all_news = news_data.get("news", [])

        # Filtros interactivos y ordenación de Noticias
        col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
        with col_f1:
            impact_options = ["Todos", "Alto", "Medio", "Bajo"]
            impact_selected = st.selectbox("🎯 Filtrar por Impacto:", impact_options, index=0)
        with col_f2:
            existing_topics = sorted(list({n.get("topic") for n in all_news if n.get("topic")}))
            topic_options = ["Todas"] + existing_topics
            topic_selected = st.selectbox("📂 Filtrar por Temática:", topic_options, index=0)
        with col_f3:
            sort_options = [
                "Fecha (más reciente primero)",
                "Impacto (de mayor a menor)",
                "Temática (A - Z)",
            ]
            sort_selected = st.selectbox("🔃 Ordenar por:", sort_options, index=0)

        # Aplicar filtros
        filtered = all_news
        if impact_selected != "Todos":
            filtered = [n for n in filtered if n.get("impact") == impact_selected]
        if topic_selected != "Todas":
            filtered = [n for n in filtered if n.get("topic") == topic_selected]

        # Aplicar ordenación (por defecto de mayor a menor)
        impact_weights = {"alto": 3, "medio": 2, "bajo": 1}
        if "Impacto" in sort_selected:
            filtered = sorted(
                filtered,
                key=lambda n: impact_weights.get(str(n.get("impact", "")).lower(), 0),
                reverse=True,
            )
        elif "Fecha" in sort_selected:
            filtered = sorted(
                filtered,
                key=lambda n: n.get("published_at") or "",
                reverse=True,
            )
        elif "Temática" in sort_selected:
            filtered = sorted(
                filtered,
                key=lambda n: (n.get("topic") or "").lower(),
            )

        st.caption(f"Mostrando {len(filtered)} de {len(all_news)} noticias")

        if not filtered:
            st.info("No hay noticias que coincidan con los filtros seleccionados.")
        else:
            for n in filtered:
                impact = n.get("impact", "Medio")
                topic = n.get("topic", "")
                title = n.get("title", "")
                summary = n.get("summary", "")
                source = n.get("source", "Fuente pública")
                link = n.get("link", "#")
                pub = n.get("published_at")
                pub_txt = f" • {_format_datetime_es(pub)}" if pub else ""

                # Tarjeta visual de la noticia
                with st.container():
                    st.markdown(
                        f"""
                        <div class="news-card">
                            <div style="margin-bottom: 0.5rem;">
                                <span class="badge-impact badge-impact-{impact.lower()}">{impact}</span>
                                <span class="badge-topic">{topic}</span>
                            </div>
                            <h4 style="margin: 0.3rem 0; font-size: 1.05rem;">{title}</h4>
                            <p style="margin: 0.4rem 0 0.8rem 0; font-size: 0.95rem; opacity: 0.9; line-height: 1.4;">
                                {summary}
                            </p>
                            <div style="font-size: 0.82rem; opacity: 0.7;">
                                <span>📰 {source}{pub_txt}</span>
                                <span style="float: right;">
                                    <a href="{link}" target="_blank" style="text-decoration: none; font-weight: 500;">Leer noticia completa ↗</a>
                                </span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )


# ==========================================
# PESTAÑA 15: SCREENER Y OPORTUNIDADES
# ==========================================
