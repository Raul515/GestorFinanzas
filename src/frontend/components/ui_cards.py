"""Tarjetas, cabeceras y navegadores reutilizables de la interfaz Streamlit."""

from datetime import date
import html
from typing import Any, Dict, Optional

import streamlit as st

_MONTH_NAMES_ES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def render_section_header(
    title: str,
    subtitle: Optional[str] = None,
    accent_color: str = "#10B981",
) -> None:
    """Renderiza una cabecera de sección limpia con barra de acento lateral."""
    safe_title = html.escape(title)
    sub_html = (
        f'<div style="color:#94A3B8;font-size:0.9rem;margin-top:0.2rem;">{html.escape(subtitle)}</div>'
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div style="border-left:4px solid {accent_color};padding-left:0.75rem;margin:0.5rem 0 1rem 0;">
            <div style="font-size:1.15rem;font-weight:700;color:#F8FAFC;">{safe_title}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_safety_guard_banner(safety_data: Optional[Dict[str, Any]]) -> None:
    """Renderiza el banner de estado del Fondo de Emergencia (Salvaguarda Patrimonial)."""
    if not safety_data:
        st.info("🛡️ Estado del Fondo de Emergencia no disponible en este momento.")
        return

    can_invest = bool(safety_data.get("can_invest", False))
    coverage = float(safety_data.get("coverage_months", 0.0) or 0.0)
    target_months = int(safety_data.get("target_months", 3) or 3)
    current_balance = float(safety_data.get("current_balance", 0.0) or 0.0)
    target_amount = float(safety_data.get("target_amount", 0.0) or 0.0)

    if can_invest:
        st.success(
            f"🛡️ **Salvaguarda Patrimonial Superada** — Fondo de Emergencia: "
            f"**{current_balance:,.2f} € / {target_amount:,.2f} €** "
            f"({coverage:.1f} / {target_months} meses cubiertos)."
        )
    else:
        gap = max(0.0, target_amount - current_balance)
        st.warning(
            f"🛡️ **Veto Patrimonial Activo** — Fondo de Emergencia al "
            f"**{current_balance:,.2f} € / {target_amount:,.2f} €** "
            f"({coverage:.1f} / {target_months} meses). Faltan **{gap:,.2f} €** para desbloquear renta variable."
        )


def render_month_navigator(mes_key: Optional[str] = None, *, key_prefix: str = "nav") -> str:
    """Renderiza un selector compacto Año/Mes y devuelve la clave YYYY-MM seleccionada."""
    today = date.today()
    if mes_key and "-" in mes_key:
        try:
            y_str, m_str = mes_key.split("-", 1)
            init_year, init_month = int(y_str), int(m_str)
        except ValueError:
            init_year, init_month = today.year, today.month
    else:
        init_year, init_month = today.year, today.month

    years = list(range(today.year - 5, today.year + 3))
    if init_year not in years:
        years.append(init_year)
        years.sort()

    col_y, col_m = st.columns(2)
    with col_y:
        sel_year = st.selectbox("Año", options=years, index=years.index(init_year), key=f"{key_prefix}_year")
    with col_m:
        sel_month_name = st.selectbox(
            "Mes",
            options=list(_MONTH_NAMES_ES),
            index=max(0, min(11, init_month - 1)),
            key=f"{key_prefix}_month",
        )
    sel_month_idx = _MONTH_NAMES_ES.index(sel_month_name) + 1
    return f"{sel_year}-{sel_month_idx:02d}"


@st.dialog("📷 Comprobante / Ticket Adjunto")
def open_receipt_dialog(
    receipt_filename: str,
    concept: str,
    amount_label: str,
    date_label: str,
) -> None:
    """Muestra un diálogo modal con la foto del ticket descargada bajo demanda del backend."""
    try:
        from frontend import api_client
    except ImportError:
        import api_client  # type: ignore

    st.markdown(f"**{concept}** · `{amount_label}` · 📅 {date_label}")
    with st.spinner("Cargando imagen del ticket..."):
        img_bytes = api_client.get_mobile_receipt_bytes(receipt_filename)
    if img_bytes:
        st.image(img_bytes, caption=f"Ticket ({receipt_filename})", width="stretch")
    else:
        st.warning("⚠️ No se pudo cargar la foto del comprobante desde el servidor local.")
