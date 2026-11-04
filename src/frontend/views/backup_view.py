"""
Vista interactiva de Gestión y Copias de Seguridad de Base de Datos (Backup & Restore).
Estructurada en 5 tarjetas visuales: Diagnóstico de Salud, Descarga Directa, Programación Periódica,
Restauración Asistida con Rollback en 1 Clic, y Catálogo de Instantáneas Locales.
"""

from datetime import datetime
import logging
from typing import Any, Dict, Optional
import streamlit as st

try:
    import api_client
except ImportError:
    from frontend import api_client  # type: ignore

logger = logging.getLogger(__name__)


def format_iso_date(iso_str: Optional[str]) -> str:
    """Convierte un timestamp ISO-8601 a un formato amigable para el usuario."""
    if not iso_str:
        return "Nunca"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return iso_str[:19].replace("T", " ")


def render_backup_view() -> None:
    """Renderiza la pestaña de Copias de Seguridad y Base de Datos en Streamlit."""
    st.title("💾 Base de Datos y Copias de Seguridad")
    st.markdown(
        "Gestiona la seguridad patrimonial de tus datos financieros: genera respaldos descargables, "
        "programa copias automáticas periódicas y restaura estados previos con red de seguridad en 1 clic."
    )

    # 1. Obtener diagnóstico de salud y listado de copias
    health = api_client.get_database_health()
    backups_data = api_client.list_backups()
    backups = backups_data.get("backups", [])
    latest_safety_snapshot = backups_data.get("latest_safety_snapshot")

    # ==============================================================================
    # BANNER DE ROLLBACK EN 1 CLIC (SI EXISTE INSTANTÁNEA PREVIA)
    # ==============================================================================
    if latest_safety_snapshot:
        st.markdown(
            f"""
            <div style="background-color: #fff3cd; border-left: 5px solid #ffc107; padding: 12px 18px; border-radius: 6px; margin-bottom: 20px;">
                <span style="font-size: 1.1rem; font-weight: 600; color: #856404;">
                    ↩️ ¿La última restauración no era la esperada?
                </span>
                <p style="margin: 4px 0 0 0; color: #664d03; font-size: 0.95rem;">
                    Existe una instantánea previa de seguridad disponible (<code>{latest_safety_snapshot}</code>).
                    Puedes revertir y recuperar el estado anterior con un solo clic.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_rb1, col_rb2 = st.columns([3, 1])
        with col_rb1:
            st.caption(f"Instantánea previa detectada: {latest_safety_snapshot}")
        with col_rb2:
            if st.button("↩️ Deshacer Restauración", key="btn_rollback_banner", type="primary", width="stretch"):
                with st.spinner("Revirtiendo base de datos al estado previo..."):
                    res = api_client.rollback_restore()
                    if res and res.get("success"):
                        st.success(res.get("message", "Restauración deshecha con éxito."))
                        st.rerun()
                    else:
                        st.error(f"Error al deshacer: {res.get('message') if res else 'Fallo desconocido'}")

    # ==============================================================================
    # TARJETA 1: DIAGNÓSTICO DE SALUD DE LA BASE DE DATOS
    # ==============================================================================
    st.subheader("1. Diagnóstico de Salud de la Base de Datos")

    if not health:
        st.error("No se pudo conectar con el servicio de base de datos para obtener el diagnóstico.")
    else:
        status_col = "🟢" if health.get("status") == "HEALTHY" else "🔴"
        status_label = "Base de Datos Saludable" if health.get("status") == "HEALTHY" else "Requiere Atención"

        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        with col_h1:
            st.metric("Estado General", f"{status_col} {status_label}")
        with col_h2:
            st.metric("Tamaño en Disco", health.get("file_size_formatted", "0 B"))
        with col_h3:
            sha_short = health.get("sha256", "")[:10] + "..." if health.get("sha256") else "N/A"
            st.metric("Hash SHA-256", sha_short)
        with col_h4:
            days = health.get("days_since_last_backup")
            days_str = f"Hace {days} días" if days is not None else "Sin copias"
            st.metric("Último Respaldo", days_str)

        # Aviso preventivo de días sin respaldo
        if health.get("backup_warning_needed"):
            st.warning(
                "⚠️ **Aviso Preventivo de Seguridad**: No se ha detectado ningún respaldo reciente en los últimos 14 días "
                "(o aún no has generado ninguna copia). Te recomendamos crear o descargar una instantánea de tus finanzas."
            )

        # Desplegable de tablas
        with st.expander("🔍 Ver desglose de registros por tabla contable"):
            table_counts = health.get("table_counts", {})
            if table_counts:
                cols_tc = st.columns(4)
                for i, (tbl, cnt) in enumerate(table_counts.items()):
                    cols_tc[i % 4].metric(f"Tabla `{tbl}`", f"{cnt:,} filas")
            else:
                st.info("No hay tablas registradas.")

    st.markdown("---")

    # ==============================================================================
    # TARJETA 2: DESCARGAR Y CREAR COPIAS DE SEGURIDAD
    # ==============================================================================
    st.subheader("2. Crear y Descargar Copias de Seguridad")

    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.markdown("#### 📥 Descarga Directa al Ordenador")
        st.write("Genera una copia en caliente consistente y descárgala directamente a tu equipo mediante el navegador:")
        
        # Gestión de descarga con session_state para evitar llamadas repetidas en cada re-renderizado
        if "backup_download_bytes" not in st.session_state:
            st.session_state["backup_download_bytes"] = None
            st.session_state["backup_download_filename"] = None

        if st.session_state["backup_download_bytes"] is None:
            if st.button("📥 Generar Copia Descargable (.db)", key="btn_prep_download", width="stretch", type="primary"):
                with st.spinner("Generando copia atómica en caliente con sqlite3.backup..."):
                    dl_result = api_client.download_backup_bytes()
                    if dl_result:
                        st.session_state["backup_download_bytes"] = dl_result[0]
                        st.session_state["backup_download_filename"] = dl_result[1]
                        st.rerun()
                    else:
                        st.error("No se pudo generar la copia para descarga.")
        else:
            file_bytes = st.session_state["backup_download_bytes"]
            dl_filename = st.session_state["backup_download_filename"]
            st.success(f"Copia lista: `{dl_filename}` ({len(file_bytes) / (1024 * 1024):.2f} MB)")
            st.download_button(
                label=f"💾 Guardar {dl_filename} en mi equipo",
                data=file_bytes,
                file_name=dl_filename,
                mime="application/x-sqlite3",
                key="btn_download_backup",
                width="stretch",
                type="primary",
            )
            if st.button("🔄 Generar Otra Descarga Nueva", key="btn_reset_download", width="stretch"):
                st.session_state["backup_download_bytes"] = None
                st.session_state["backup_download_filename"] = None
                st.rerun()

    with col_c2:
        st.markdown("#### 📸 Instantánea Local en el Servidor")
        st.write("Crea una copia de seguridad en la carpeta `backups/` del servidor sin necesidad de descargarla:")
        custom_name = st.text_input(
            "Nombre personalizado (opcional):",
            placeholder="ej. antes_de_cerrar_ano.db",
            key="input_custom_backup_name",
        )
        if st.button("📸 Crear Instantánea Ahora", key="btn_create_local_snapshot", width="stretch"):
            with st.spinner("Generando instantánea en caliente con sqlite3.backup..."):
                created = api_client.create_backup(custom_name=custom_name.strip() if custom_name else None)
                if created:
                    st.success(f"Instantánea creada con éxito: `{created.get('filename')}`")
                    st.rerun()
                else:
                    st.error("Error al generar la instantánea en el servidor.")

    st.markdown("---")

    # ==============================================================================
    # TARJETA 3: PROGRAMACIÓN DE COPIAS PERIÓDICAS
    # ==============================================================================
    st.subheader("3. Programación Periódica Automática")
    schedule = api_client.get_backup_schedule() or {}

    col_s1, col_s2 = st.columns([1, 1])

    with col_s1:
        current_enabled = schedule.get("enabled", True)
        enabled_toggle = st.toggle(
            "Activar copias de seguridad automáticas en segundo plano",
            value=current_enabled,
            key="toggle_backup_enabled",
        )

        freq_options = {
            "Semanal (cada 7 días)": 7,
            "Quincenal (cada 14 días)": 14,
            "Mensual (cada 30 días)": 30,
            "Personalizada": -1,
        }
        current_days = schedule.get("frequency_days", 14)

        # Detectar selección inicial
        initial_label = "Quincenal (cada 14 días)"
        for label, d in freq_options.items():
            if d == current_days:
                initial_label = label
                break
        if initial_label not in freq_options:
            initial_label = "Personalizada"

        freq_label = st.selectbox(
            "Frecuencia de las copias automáticas:",
            options=list(freq_options.keys()),
            index=list(freq_options.keys()).index(initial_label),
            key="select_backup_freq",
        )

        if freq_label == "Personalizada":
            selected_days = st.number_input(
                "Días entre cada copia (1 a 365):",
                min_value=1,
                max_value=365,
                value=max(1, current_days),
                key="num_custom_days",
            )
        else:
            selected_days = freq_options[freq_label]

        keep_copies = st.slider(
            "Límite máximo de instantáneas locales a conservar (rotación automática):",
            min_value=3,
            max_value=20,
            value=schedule.get("keep_max_copies", 5),
            key="slider_keep_copies",
        )

        if st.button("💾 Guardar Configuración de Programación", key="btn_save_schedule", width="stretch"):
            updated = api_client.update_backup_schedule(
                enabled=enabled_toggle,
                frequency_days=selected_days,
                keep_max_copies=int(keep_copies),
            )
            if updated:
                st.success("Configuración de copias periódicas guardada con éxito.")
                st.rerun()
            else:
                st.error("No se pudo actualizar la configuración de programación.")

    with col_s2:
        st.markdown("#### ℹ️ Estado de la Tarea Programada")
        st.write(
            "El servidor evalúa en segundo plano cada hora si corresponde generar un nuevo respaldo. "
            "Si la base de datos no ha experimentado cambios, **se omite la copia automáticamente por deduplicación SHA-256**."
        )
        st.info(
            f"📅 **Última copia automática**: {format_iso_date(schedule.get('last_automated_backup_at'))}\n\n"
            f"⏳ **Próxima copia estimada**: {format_iso_date(schedule.get('next_backup_estimated_at'))}\n\n"
            f"🔄 **Estado del programador**: {'🟢 Activo' if schedule.get('enabled') else '⏸️ Pausado'}"
        )

    st.markdown("---")

    # ==============================================================================
    # TARJETA 4: RESTAURAR DESDE ARCHIVO Y DESHACER
    # ==============================================================================
    st.subheader("4. Restaurar Base de Datos desde Archivo")
    st.markdown(
        "Sube un archivo de copia de seguridad `.db` para restaurar tu historial financiero. "
        "Antes de sobrescribir nada, el sistema validará la integridad del archivo y **creará automáticamente "
        "una instantánea de seguridad previa** para que puedas revertir los cambios si lo necesitas."
    )

    uploaded_file = st.file_uploader(
        "Selecciona un archivo de copia de seguridad (.db):",
        type=["db"],
        key="uploader_backup_db",
    )

    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        col_up1, col_up2 = st.columns([2, 1])
        with col_up1:
            st.write(f"📁 **Archivo seleccionado**: `{uploaded_file.name}` ({len(file_bytes) / 1024:.2f} KB)")

        # Inspección previa con session_state
        val_key = f"val_cache_{uploaded_file.name}_{len(file_bytes)}"
        with col_up2:
            if st.button("🔍 Inspeccionar y Validar Copia", key="btn_inspect_upload", width="stretch"):
                with st.spinner("Inspeccionando integridad SQLite y tablas contables..."):
                    val_res = api_client.validate_backup_upload(file_bytes, uploaded_file.name)
                    st.session_state[val_key] = val_res

        val_result = st.session_state.get(val_key)
        if val_result:
            if val_result.get("is_valid"):
                st.success(
                    f"🟢 **Copia Válida e Íntegra**: PRAGMA integrity_check=`{val_result.get('integrity_status')}` "
                    f"• SHA-256: `{val_result.get('sha256', '')[:10]}...`"
                )
                tc = val_result.get("table_counts", {})
                if tc:
                    with st.expander("📊 Ver desglose de registros contenidos en este respaldo", expanded=True):
                        cols_val = st.columns(4)
                        for idx, (t_name, t_cnt) in enumerate(tc.items()):
                            cols_val[idx % 4].metric(f"`{t_name}`", f"{t_cnt:,} filas")
            else:
                st.error(f"🔴 **Archivo Inválido o Dañado**: {val_result.get('error_message', 'No pasó la validación.')}")

        st.markdown("---")
        confirm_box = st.checkbox(
            "Entiendo que la base de datos activa será reemplazada (se creará automáticamente un snapshot de seguridad previo)",
            key="chk_confirm_restore",
        )

        can_restore = confirm_box and (val_result is None or val_result.get("is_valid", False))
        if st.button("🔄 Confirmar y Restaurar Base de Datos", type="primary", disabled=not can_restore):
            with st.spinner("Validando integridad, purgando WAL y restaurando base de datos..."):
                res_upload = api_client.restore_backup_upload(file_bytes, uploaded_file.name)
                if res_upload and res_upload.get("success"):
                    st.success(res_upload.get("message", "Base de datos restaurada."))
                    st.rerun()
                else:
                    err_msg = res_upload.get("message") if res_upload else "Fallo al restaurar"
                    st.error(f"Error en la restauración: {err_msg}")

    st.markdown("---")

    # ==============================================================================
    # TARJETA 5: HISTORIAL DE INSTANTÁNEAS LOCALES
    # ==============================================================================
    st.subheader("5. Catálogo de Instantáneas Locales en el Servidor")

    if not backups:
        st.info("No hay ninguna instantánea guardada en la carpeta `backups/`.")
    else:
        st.caption(f"Total de copias almacenadas: {len(backups)}")
        for b in backups:
            with st.container():
                col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns([3, 2, 2, 1.5, 1.5])
                with col_b1:
                    type_badge = {
                        "MANUAL": "📸 Manual",
                        "AUTOMATIC": "🤖 Automática",
                        "SAFETY_PRERESTORE": "🛡️ Pre-Restauración",
                    }.get(b.get("backup_type"), "Copia")
                    st.markdown(f"**`{b.get('filename')}`**")
                    st.caption(f"{type_badge} • Hash: `{b.get('sha256', '')[:8]}`")
                with col_b2:
                    st.write(f"📅 {format_iso_date(b.get('created_at'))}")
                with col_b3:
                    st.write(f"📦 {b.get('file_size_formatted', '')}")
                with col_b4:
                    with st.popover("🔄 Restaurar", width="stretch"):
                        st.markdown(f"**¿Restaurar instantánea `{b.get('filename')}`?**")
                        st.caption("Se sobrescribirá la base activa tras generar automáticamente una copia de seguridad previa.")
                        if st.button("Confirmar Restauración", key=f"btn_pop_res_{b.get('filename')}", type="primary", width="stretch"):
                            with st.spinner(f"Restaurando {b.get('filename')}..."):
                                res = api_client.restore_backup_local(b.get("filename"))
                                if res and res.get("success"):
                                    st.success("Restaurado con éxito.")
                                    st.rerun()
                                else:
                                    st.error(res.get("message") if res else "Fallo al restaurar")
                with col_b5:
                    with st.popover("🗑️ Borrar", width="stretch"):
                        st.markdown(f"**¿Eliminar copia `{b.get('filename')}`?**")
                        st.caption("Esta acción eliminará definitivamente el archivo de la carpeta de respaldos.")
                        if st.button("Confirmar Eliminación", key=f"btn_pop_del_{b.get('filename')}", type="primary", width="stretch"):
                            if api_client.delete_backup_local(b.get("filename")):
                                st.success(f"Copia `{b.get('filename')}` eliminada.")
                                st.rerun()
                            else:
                                st.error("No se pudo eliminar la copia.")
                st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #eee;'>", unsafe_allow_html=True)
