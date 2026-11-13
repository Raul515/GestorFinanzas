"""
Vista interactiva del Companion Móvil Quick-Capture en Streamlit.
Permite conectar teléfonos móviles (Android e iOS) a la micro-app PWA mediante código QR,
consultar el estado del motor de sincronización offline y auditar los gastos capturados desde el móvil.
"""

from __future__ import annotations
import base64
from datetime import datetime
import logging
import socket
from typing import Any, Dict, List, Optional
import streamlit as st

try:
    import api_client
except ImportError:
    from frontend import api_client  # type: ignore

from frontend.qrcodegen import QrCode

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """Detecta la IP local de la máquina en la red Wi-Fi o interfaz activa."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "localhost"


def format_display_date(date_val: Any) -> str:
    """Convierte cualquier formato de fecha a DD/MM/AAAA según la Regla 12."""
    if not date_val:
        return "N/A"
    date_str = str(date_val).strip()
    try:
        if "T" in date_str or " " in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        parts = date_str.split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return date_str


def generate_qr_svg_base64(url: str) -> str:
    """Genera el código QR en SVG base64 para incrustar directamente en la interfaz."""
    try:
        qr = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
        svg_code = qr.to_svg_str(border=2, fg_color="#0f172a", bg_color="#ffffff")
        b64 = base64.b64encode(svg_code.encode("utf-8")).decode("utf-8")
        return f"data:image/svg+xml;base64,{b64}"
    except Exception as exc:
        logger.warning("Fallo generando código QR para %s: %s", url, exc)
        return ""


def render_mobile_view() -> None:
    """Renderiza la pestaña del Companion Móvil en Streamlit."""
    st.title("📱 Companion Móvil Quick-Capture")
    st.markdown(
        "Anota tus gastos personales en **menos de 5 segundos** desde tu teléfono (Android e iOS) cuando estés en la calle. "
        "La micro-app funciona **100% offline** y sincroniza automáticamente las transacciones con tu ordenador al conectarte a la Wi-Fi de casa."
    )

    local_ip = get_local_ip()
    mobile_url = f"http://{local_ip}:8000/mobile/"
    localhost_url = "http://localhost:8000/mobile/"

    # ==============================================================================
    # SECCIÓN 1: ACCESO RÁPIDO CON CÓDIGO QR Y ENLACES
    # ==============================================================================
    st.subheader("🔗 Conexión Rápida desde el Teléfono")

    col_qr, col_info = st.columns([1, 2])

    with col_qr:
        qr_uri = generate_qr_svg_base64(mobile_url)
        if qr_uri:
            st.markdown(
                f"""
                <div style="background-color: #ffffff; padding: 16px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 8px;">
                    <img src="{qr_uri}" style="width: 190px; height: 190px; display: block; margin: 0 auto; border-radius: 6px;" alt="Código QR Micro-app" />
                    <div style="font-size: 0.85rem; color: #475569; margin-top: 8px; font-weight: 600;">
                        📷 Escanea con la cámara de tu móvil
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.info("Abre la URL en tu navegador móvil.")

        st.caption(f"📍 IP local detectada: **`{local_ip}`**")

    with col_info:
        st.markdown(
            f"""
            <div style="background: #f8fafc; border-left: 5px solid #3b82f6; padding: 14px 18px; border-radius: 8px; margin-bottom: 12px;">
                <div style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 700;">
                    URL de la Micro-app PWA en tu red local:
                </div>
                <div style="font-size: 1.15rem; font-weight: 700; color: #1e293b; margin-top: 4px; word-break: break-all;">
                    <code>{mobile_url}</code>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            st.link_button("🌐 Abrir PWA en el PC", localhost_url, use_container_width=True)
        with col_btn2:
            st.link_button("📖 Ver Guía Completa", "https://github.com/", use_container_width=True, help="Consulta docs/guia_companion_movil.md en el repositorio.")

        guide_tabs = st.tabs(["🍏 iPhone (Safari)", "🤖 Android (Chrome PWA)", "📦 Android APK", "🔄 Syncthing (Opcional)"])

        with guide_tabs[0]:
            st.markdown(
                """
                1. Asegúrate de que el iPhone esté conectado a la **misma red Wi-Fi** que tu ordenador.
                2. Escanea el código QR con la cámara del iPhone o escribe la URL en **Safari**.
                3. Toca el botón **Compartir** (icono cuadrado con flecha hacia arriba en la barra inferior).
                4. Selecciona **«Añadir a la pantalla de inicio»** (icono `➕`).
                5. ¡Listo! Se abrirá como una aplicación nativa a pantalla completa y funcionará sin conexión.
                """
            )

        with guide_tabs[1]:
            st.markdown(
                """
                1. Conecta tu teléfono a la **misma Wi-Fi** que el ordenador.
                2. Escanea el código QR o abre la URL en **Google Chrome**.
                3. Pulsa el botón de opciones (**tres puntos `⋮`** en la esquina superior derecha).
                4. Pulsa en **«Instalar aplicación»** o **«Añadir a pantalla principal»**.
                5. Tendrás el icono en tu escritorio listo para registrar gastos en 1 tap.
                """
            )

        with guide_tabs[2]:
            st.markdown(
                """
                1. Cada vez que actualices el repositorio en GitHub, **GitHub Actions** compila un archivo APK nativo (`app-debug.apk`) automáticamente.
                2. Entra en tu repositorio en GitHub > pestaña **Actions** > workflow **Build Mobile APK (Capacitor)**.
                3. En la última ejecución completada, descarga el artefacto **`gestor-finanzas-mobile-apk`**.
                4. Descomprime el ZIP e instala el APK en tu dispositivo Android.
                """
            )

        with guide_tabs[3]:
            st.markdown(
                """
                - Si utilizas **Syncthing** para sincronización silenciosa entre tu teléfono y tu PC sin necesidad de Wi-Fi directa:
                  - En la app móvil, pulsa el botón **«Exportar Lote JSON»** para guardar tus gastos en un archivo `.json`.
                  - Deposítalo en la carpeta sincronizada `sync/mobile/inbox/`.
                  - El backend de tu ordenador lo procesará automáticamente al arrancar o puedes pulsar el botón de abajo.
                """
            )

    st.markdown("---")

    # ==============================================
    # SECCIÓN 2: ESTADO DEL MOTOR DE SINCRONIZACIÓN Y ACCIONES
    # ==============================================
    st.subheader("⚙️ Estado del Motor de Sincronización")

    status_data = api_client.get_mobile_status()

    if status_data:
        inbox_count = status_data.get("pending_inbox_files", 0)
        today_count = status_data.get("today_transactions_count", 0)
        online = status_data.get("server_online", True)
        server_time = status_data.get("server_time_utc")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Servicio Móvil", "✅ Activo" if online else "❌ Inactivo")
        m2.metric("Transacciones Hoy", f"{today_count}")
        m3.metric("Bandeja Inbox", f"{inbox_count} ficheros")
        m4.metric("Sincronización Wi-Fi", "⚡ Directa")

        if server_time:
            st.caption(f"🕒 Servidor sincronizado a las: **{format_display_date(server_time)}**")

        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        col_act1, col_act2 = st.columns([1, 2])
        with col_act1:
            if st.button("🔄 Procesar Ficheros de la Carpeta Inbox", key="btn_process_mobile_folder", use_container_width=True):
                with st.spinner("Procesando ficheros JSON pendientes en sync/mobile/inbox/..."):
                    res = api_client.process_mobile_folder()
                    if res and res.get("success"):
                        txs = res.get("processed_count", 0)
                        st.success(f"✅ Sincronización completada: {txs} transacciones importadas desde el buzón.")
                        try:
                            api_client.clear_all_frontend_cache()
                        except Exception:
                            pass
                        st.rerun()
                    else:
                        st.error("No se pudieron procesar los ficheros o la carpeta está vacía.")
        with col_act2:
            st.caption("Usa este botón si has depositado manualmente archivos `.json` en `sync/mobile/inbox/` o mediante Syncthing y deseas importarlos al instante.")
    else:
        st.warning("⚠️ No se pudo obtener el estado del servicio móvil. Verifica que el backend esté en ejecución.")

    st.markdown("---")

    # ==============================================================================
    # SECCIÓN 3: HISTORIAL DE GASTOS CAPTURADOS DESDE EL MÓVIL
    # ==============================================================================
    st.subheader("📋 Últimos Gastos Capturados desde el Teléfono")

    todas_txs = api_client.get_transacciones() or []
    # Filtrar aquellas transacciones con mobile_event_id presente
    mobile_txs = [
        t for t in todas_txs
        if (t.get("mobile_event_id") is not None and str(t.get("mobile_event_id")).strip() != "")
    ]

    if mobile_txs:
        # Ordenar de más reciente a más antigua
        mobile_txs.sort(key=lambda x: str(x.get("date") or x.get("fecha") or ""), reverse=True)

        total_gastado_movil = sum(float(t.get("amount") or t.get("cantidad") or 0.0) for t in mobile_txs)
        st.info(f"📱 Se han sincronizado **{len(mobile_txs)}** gastos personales desde la micro-app móvil, sumando un total de **{total_gastado_movil:.2f} €**.")

        # Obtener mapeo de nombres de subcategorías
        subcats_list = api_client.get_subcategorias() or []
        subcat_names = {s.get("id"): s.get("nombre") or s.get("name") for s in subcats_list if s.get("id")}

        table_rows = []
        for t in mobile_txs[:30]:  # Mostrar las 30 más recientes
            raw_date = t.get("date") or t.get("fecha")
            sub_id = t.get("subcategory_id") or t.get("subcategoria_id")
            sub_name = subcat_names.get(sub_id, f"Subcategoría #{sub_id}")
            amount_val = float(t.get("amount") or t.get("cantidad") or 0.0)
            concept_val = t.get("description") or t.get("concepto") or "-"
            event_id = str(t.get("mobile_event_id"))

            table_rows.append({
                "Fecha": format_display_date(raw_date),
                "Concepto": concept_val,
                "Subcategoría": sub_name,
                "Importe": f"{amount_val:.2f} €",
                "ID Móvil": event_id[:16] + "..." if len(event_id) > 16 else event_id,
            })

        st.dataframe(table_rows, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Aún no se han registrado transacciones desde el móvil. Captura tu primer gasto desde la micro-app para verlo reflejado aquí.")

    # ==============================================================================
    # SECCIÓN 4: HOJA DE RUTA Y MEJORAS FUTURAS DOCUMENTADAS
    # ==============================================================================
    with st.expander("🚀 Hoja de Ruta y Mejoras Futuras de la Micro-app", expanded=False):
        st.markdown(
            """
            Para preservar la velocidad extrema (< 5 segundos por captura), la versión actual está acotada estrictamente a **Gastos Personales**.
            Las siguientes capacidades están planificadas para versiones posteriores:
            - **Gastos de Cuenta Conjunta (`👥 Hogar`)**: Selector rápido para imputar un gasto al hogar eligiendo el pagador (Tú o tu Pareja) con cálculo automático de compensaciones.
            - **Huchas y Metas de Ahorro**: Asignación directa de aportaciones a huchas específicas desde el móvil.
            - **Resumen Financiero Rápido**: Tarjeta en la micro-app con el disponible restante del mes en 1 tap sin sobrecargar con gráficos pesados.
            """
        )
