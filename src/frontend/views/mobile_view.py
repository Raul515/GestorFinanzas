"""
Vista interactiva del Companion Móvil Quick-Capture en Streamlit.
Permite conectar teléfonos móviles (Android e iOS) a la micro-app PWA mediante código PIN de vinculación de 6 dígitos,
consultar el estado del motor de sincronización offline y auditar los gastos capturados desde el móvil.
"""

from __future__ import annotations
import base64
from datetime import datetime
import logging
import os
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
    """Detecta la IP local de la máquina en la red Wi-Fi o interfaz activa, respetando HOST_IP si existe."""
    env_ip = os.environ.get("HOST_IP", "").strip()
    if env_ip:
        return env_ip
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


def generate_qr_png_bytes(url: str, ecc: QrCode.Ecc = QrCode.Ecc.MEDIUM) -> bytes:
    """Genera una imagen PNG nítida de alto contraste para lectura instantánea desde monitores."""
    try:
        qr = QrCode.encode_text(url, ecc)
        return qr.to_png_bytes(border=4, scale=10, fg_color="#000000", bg_color="#ffffff")
    except Exception as exc:
        logger.warning("Fallo generando código QR PNG para %s: %s", url, exc)
        return b""


def generate_qr_svg_base64(url: str) -> str:
    """Genera el código QR en SVG base64 como fallback (borde ISO 4)."""
    try:
        qr = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
        svg_code = qr.to_svg_str(border=4, fg_color="#000000", bg_color="#ffffff")
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

    status_data = api_client.get_mobile_status()
    pairing_token = api_client.get_mobile_pairing_token()

    detected_ip = get_local_ip()
    custom_ip = st.session_state.get("custom_mobile_host_ip")
    local_ip = custom_ip.strip() if custom_ip and custom_ip.strip() else detected_ip
    is_docker_detected = local_ip.startswith("172.")

    server_base_url = f"http://{local_ip}:8000"
    token_query = f"?token={pairing_token}" if pairing_token else ""
    mobile_url = f"{server_base_url}/mobile/{token_query}"
    localhost_url = f"http://localhost:8000/mobile/{token_query}"

    # ==============================================================================
    # SECCIÓN 1: ACCESO RÁPIDO CON CÓDIGO PIN DE 6 DÍGITOS Y ENLACES
    # ==============================================================================
    st.subheader("🔗 Conexión Rápida desde el Teléfono")

    with st.expander("⚙️ Configuración de IP / Docker Wi-Fi", expanded=is_docker_detected):
        if is_docker_detected and not custom_ip:
            st.warning(
                f"⚠️ **Entorno Docker detectado**: La IP detectada (`{detected_ip}`) pertenece a la red interna del contenedor. "
                "Para que tu teléfono móvil pueda conectar desde la misma Wi-Fi, introduce abajo la IP de tu PC en la red local (ej. `192.168.1.35`)."
            )
        else:
            st.info("Si tu teléfono y tu PC están en la misma red Wi-Fi pero la IP no se detecta automáticamente (o ejecutas en Docker), puedes ajustarla aquí.")

        col_ip_in, col_ip_btn, col_ip_reset = st.columns([3, 1, 1])
        with col_ip_in:
            user_ip_input = st.text_input(
                "IP de tu PC en la red Wi-Fi:",
                value=local_ip if not (is_docker_detected and not custom_ip) else "",
                placeholder="Ejemplo: 192.168.1.35",
                help="IP asignada por el router a tu PC en la red Wi-Fi.",
                key="input_custom_mobile_host_ip",
            )
        with col_ip_btn:
            st.write("")
            st.write("")
            if st.button("Aplicar IP", use_container_width=True):
                cleaned_ip = user_ip_input.strip()
                if cleaned_ip:
                    st.session_state["custom_mobile_host_ip"] = cleaned_ip
                else:
                    st.session_state.pop("custom_mobile_host_ip", None)
                st.rerun()
        with col_ip_reset:
            st.write("")
            st.write("")
            if st.button("Detectar Auto", use_container_width=True, help="Restablece la detección automática de IP."):
                st.session_state.pop("custom_mobile_host_ip", None)
                st.rerun()

    # Gestión del PIN de emparejamiento (6 dígitos)
    pin_data = st.session_state.get("mobile_pairing_pin_data")
    if not pin_data:
        pin_data = api_client.generate_mobile_pin(ttl_seconds=600)
        if pin_data:
            st.session_state["mobile_pairing_pin_data"] = pin_data

    active_pin = pin_data.get("pin", "------") if pin_data else "------"
    formatted_pin = f"{active_pin[:3]} {active_pin[3:]}" if len(active_pin) == 6 else active_pin
    clean_mobile_url = f"{server_base_url}/mobile/"
    auto_pair_url = f"{clean_mobile_url}?pin={active_pin}" if active_pin != "------" else clean_mobile_url
    localhost_pin_url = f"http://localhost:8000/mobile/?pin={active_pin}" if active_pin != "------" else localhost_url

    col_pin, col_info = st.columns([1, 2])

    with col_pin:
        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 2px solid #3b82f6; border-radius: 16px; padding: 22px 16px; text-align: center; box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.25); margin-bottom: 12px;">
                <div style="color: #94a3b8; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em;">
                    🔑 CÓDIGO DE VINCULACIÓN
                </div>
                <div style="font-family: 'Courier New', Courier, monospace; font-size: 2.6rem; font-weight: 800; letter-spacing: 0.2em; color: #38bdf8; text-shadow: 0 0 15px rgba(56, 189, 248, 0.4); margin: 14px 0;">
                    {formatted_pin}
                </div>
                <div style="color: #10b981; font-size: 0.8rem; font-weight: 600;">
                    ⏱️ Validez: 10 minutos (un solo uso)
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🔄 Generar Nuevo PIN", use_container_width=True, help="Genera un nuevo código de vinculación de 6 dígitos con validez de 10 minutos."):
            new_pin_data = api_client.generate_mobile_pin(ttl_seconds=600)
            if new_pin_data:
                st.session_state["mobile_pairing_pin_data"] = new_pin_data
            st.rerun()

        st.caption(f"📍 Servidor en red Wi-Fi: **`{local_ip}`**")
        st.caption("🛡️ Rate-limiting: Bloqueo tras 5 intentos fallidos.")

    with col_info:
        st.markdown(
            f"""
            <div style="background: #f8fafc; border-left: 5px solid #3b82f6; padding: 14px 18px; border-radius: 8px; margin-bottom: 12px;">
                <div style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 700;">
                    Dirección web de la aplicación móvil:
                </div>
                <div style="font-size: 1.15rem; font-weight: 700; color: #1e293b; margin-top: 4px; word-break: break-all;">
                    <code>{clean_mobile_url}</code>
                </div>
                <div style="font-size: 0.82rem; color: #475569; margin-top: 6px;">
                    Abre la dirección en el navegador de tu móvil e introduce el <b>PIN de 6 dígitos</b> para emparejar tu teléfono al instante.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.code(clean_mobile_url, language=None)

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            st.link_button("🌐 Probar en este PC", localhost_pin_url, use_container_width=True)
        with col_btn2:
            st.link_button("📖 Ver Guía Completa", "https://github.com/", use_container_width=True, help="Consulta docs/guia_companion_movil.md en el repositorio.")

        guide_tabs = st.tabs(["🤖 Android (Chrome PWA)", "🍏 iPhone (Safari)", "📦 Android APK (Sin Barras)", "🔄 Syncthing (Opcional)"])

        with guide_tabs[0]:
            st.markdown(
                f"""
                1. Conecta tu teléfono a la **misma Wi-Fi** que este PC.
                2. Abre en **Google Chrome**: `http://{local_ip}:8000/mobile`
                3. Introduce el **PIN de 6 dígitos** (`{active_pin}`) y pulsa **Vincular**.
                4. Pulsa el menú de opciones (**tres puntos `⋮`**) y selecciona **«Instalar aplicación»** o **«Añadir a la pantalla principal»**.
                5. ¡Listo! Tendrás el acceso directo listo para capturar gastos en 1 tap con operativa 100% offline.

                > ℹ️ **Nota sobre la barra superior de Chrome en Android**:
                > En redes Wi-Fi locales bajo HTTP, Android muestra una barra de navegación delgada debido a las políticas WebAPK de Google. La app funciona de forma idéntica y sin límites. Si prefieres **pantalla completa pura de borde a borde (sin barra)**, puedes instalar la **📦 Android APK**.
                >
                > 💡 **Si Chrome indica «Esta aplicación no se puede instalar»**:
                > 1. En Chrome en el móvil abre: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
                > 2. Actívalo en **Enabled** y escribe: `http://{local_ip}:8000`
                > 3. Pulsa **Relaunch**.
                """
            )

        with guide_tabs[1]:
            st.markdown(
                f"""
                1. Conecta el iPhone a la **misma red Wi-Fi** que el ordenador.
                2. Abre en **Safari**: `http://{local_ip}:8000/mobile`
                3. Introduce el **PIN de 6 dígitos** (`{active_pin}`) y pulsa **Vincular**.
                4. Toca el botón **Compartir** (icono de cuadrado con flecha hacia arriba) y selecciona **«Añadir a la pantalla de inicio»** (`➕`).
                5. ¡Listo! En iOS, Safari abre la aplicación al **100% a pantalla completa nativa sin ninguna barra de navegación ni menús**.
                """
            )

        with guide_tabs[2]:
            st.markdown(
                f"""
                1. Diseñado para quienes desean eliminar totalmente la barra superior de Chrome en Android.
                2. En la sección inferior **«📦 Distribución y Actualizaciones»**, descarga el archivo `.apk` publicado.
                3. Instálalo en tu Android permitiendo la instalación desde fuentes desconocidas.
                4. Al abrir la app por primera vez, pulsa el engranaje de configuración `[⚙️]`, introduce la IP `{local_ip}` y el PIN de 6 dígitos (`{active_pin}`).
                5. ¡Disfruta de una experiencia 100% nativa de pantalla completa sin barras!
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
    # SECCIÓN 3: DISTRIBUCIÓN Y ACTUALIZACIONES OTA DE LA APK
    # ==============================================================================
    st.markdown("---")
    st.subheader("📦 Distribución y Actualizaciones de la App Android (OTA)")

    v_data = api_client.get_mobile_version()
    if v_data:
        v_code = v_data.get("version_code", 1)
        v_name = v_data.get("version_name", "1.0.0")
        available = v_data.get("apk_available", False)
        apk_size = v_data.get("apk_size_bytes")
        notes = v_data.get("release_notes") or "Sin notas de versión"
        size_mb = f"{apk_size / (1024 * 1024):.2f} MB" if apk_size else "-"

        col_v1, col_v2, col_v3 = st.columns([1, 1, 2])
        col_v1.metric("Versión Publicada", f"v{v_name} (b{v_code})")
        col_v2.metric("Estado APK", "🟢 Disponible" if available else "⚪ No subido")
        col_v3.metric("Tamaño Binario", size_mb)

        st.caption(f"📝 Notas de la versión: {notes}")

        if available:
            download_url = f"{api_client.API_URL}/api/mobile/download-apk"
            st.markdown(
                f"""
                <a href="{download_url}" target="_blank" style="text-decoration:none;">
                    <div style="display:inline-flex; align-items:center; gap:8px; padding:10px 18px; border-radius:12px; background:#10b981; color:#020617; font-weight:800; font-size:13px; margin-top:6px;">
                        📥 Descargar APK para Android ({v_data.get('apk_filename') or 'app-release.apk'})
                    </div>
                </a>
                """,
                unsafe_allow_html=True,
            )

        with st.expander("📤 Publicar Nueva Versión de la APK (OTA Update)", expanded=False):
            st.markdown(
                "Sube un archivo `.apk` compilado para que tus teléfonos móviles se auto-actualicen al abrir la app o al pulsar **[Actualizar]**."
            )
            up_file = st.file_uploader("Selecciona el archivo APK", type=["apk"], key="uploader_apk_release")
            c_code, c_name = st.columns(2)
            new_code = c_code.number_input("Código de versión (entero)", min_value=1, value=v_code + 1, step=1)
            new_name = c_name.text_input("Nombre de versión (ej. 1.1.0)", value=f"1.{v_code}.0")
            new_notes = st.text_area("Notas de la versión (changelog)", placeholder="Ej. Nuevas mejoras en la captura rápida...")

            if st.button("🚀 Publicar Release OTA", key="btn_publish_apk", disabled=up_file is None):
                if up_file:
                    with st.spinner("Guardando APK y publicando metadata..."):
                        content = up_file.read()
                        res = api_client.upload_mobile_apk(
                            file_bytes=content,
                            filename=up_file.name,
                            version_code=int(new_code),
                            version_name=new_name.strip(),
                            release_notes=new_notes.strip(),
                        )
                        if res:
                            st.success(f"✅ Versión v{new_name} (código {new_code}) publicada con éxito. Los dispositivos conectados recibirán el aviso de actualización.")
                            st.rerun()
                        else:
                            st.error("Error al publicar la release en el servidor.")

    # ==============================================================================
    # SECCIÓN 4: HISTORIAL DE GASTOS CAPTURADOS DESDE EL MÓVIL
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
