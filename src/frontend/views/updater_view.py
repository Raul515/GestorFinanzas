"""
Vista interactiva del Actualizador Over-The-Air (In-App OTA Updater).
Presenta estado de la versión actual, commit SHA, comprobación en GitHub API,
panel de novedades, confirmación previa, barra de progreso y reversión de código en 1 clic.
"""

from datetime import datetime
import logging
import time
from typing import Any, Dict, Optional
import streamlit as st

try:
    import api_client
except ImportError:
    from frontend import api_client  # type: ignore

logger = logging.getLogger(__name__)


def format_iso_timestamp(iso_str: Optional[str]) -> str:
    """Convierte un timestamp ISO-8601 a un formato legible para el usuario."""
    if not iso_str:
        return "Versión inicial (sin registro)"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return iso_str[:19].replace("T", " ")


def render_updater_view() -> None:
    """Renderiza la pestaña de Actualizaciones del Sistema en Streamlit."""
    st.title("🚀 Actualizaciones del Sistema")
    st.markdown(
        "Mantén tu aplicación actualizada a la última versión en un solo clic directamente desde GitHub, "
        "con directorio de pruebas en staging, doble red de seguridad previa y reversión garantizada."
    )

    # 1. Obtener información de versión del backend
    version_data = api_client.get_app_version()
    if not version_data:
        st.error("No se pudo conectar con el servicio backend para verificar la versión del sistema.")
        return

    current_commit = str(version_data.get("current_commit", "initial"))
    branch = str(version_data.get("branch", "main"))
    last_updated_at = version_data.get("last_updated_at")
    commit_msg = version_data.get("commit_message")
    rollback_avail = bool(version_data.get("rollback_available", False))
    is_git = bool(version_data.get("is_git_repo", False))

    # ==============================================================================
    # BANNER DE ROLLBACK EN 1 CLIC (SI EXISTE INSTANTÁNEA PREVIA)
    # ==============================================================================
    if rollback_avail:
        st.markdown(
            """
            <div style="background-color: #fff3cd; border-left: 5px solid #ffc107; padding: 12px 18px; border-radius: 6px; margin-bottom: 20px;">
                <span style="font-size: 1.1rem; font-weight: 600; color: #856404;">
                    ↩️ ¿La última actualización presenta algún problema o inestabilidad?
                </span>
                <p style="margin: 4px 0 0 0; color: #664d03; font-size: 0.95rem;">
                    Existe una instantánea de código previo disponible en <code>backups/code_snapshot_prev.tar.gz</code>.
                    Puedes deshacer la actualización en 1 clic y volver al estado previo sin perder ninguna transacción
                    ni modificar la base de datos.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_rb1, col_rb2 = st.columns([3, 1])
        with col_rb1:
            st.caption("La instantánea previa preserva la versión estable anterior del código y dependencias.")
        with col_rb2:
            if st.button("↩️ Deshacer Actualización", key="btn_rollback_code_banner", type="primary", width="stretch"):
                with st.spinner("Restaurando versión previa de código..."):
                    res_rb = api_client.rollback_system_update()
                    if res_rb and res_rb.get("success"):
                        st.success(res_rb.get("message", "Código restaurado con éxito."))
                        time.sleep(1)
                        st.rerun()
                    else:
                        err_detail = res_rb.get("message") if res_rb else "Fallo desconocido"
                        st.error(f"Error al deshacer actualización: {err_detail}")

    # ==============================================================================
    # TARJETA 1: ESTADO ACTUAL DEL SISTEMA
    # ==============================================================================
    st.subheader("1. Estado Actual de la Aplicación")

    commit_badge = current_commit[:7] if current_commit != "initial" else "v1.0 (Inicial)"
    col_v1, col_v2, col_v3, col_v4 = st.columns(4)
    with col_v1:
        st.metric("Versión / Commit Activo", commit_badge)
    with col_v2:
        st.metric("Rama de Trabajo", branch)
    with col_v3:
        st.metric("Última Actualización", format_iso_timestamp(last_updated_at))
    with col_v4:
        st.metric("Reversión Disponible", "✅ Sí" if rollback_avail else "❌ No")

    if commit_msg:
        st.caption(f"📝 **Último cambio aplicado:** {commit_msg}")

    # Alerta informativa preventiva si se detecta un clon Git local
    if is_git:
        st.info(
            "ℹ️ **Entorno de desarrollo Git detectado:** El proyecto contiene una carpeta `.git/`. "
            "Ten en cuenta que si actualizas directamente desde la interfaz web, el código descargado de GitHub "
            "sobrescribirá los archivos en el disco local."
        )

    st.markdown("---")

    # ==============================================================================
    # TARJETA 2: COMPROBACIÓN DE ACTUALIZACIONES REMOTAS
    # ==============================================================================
    st.subheader("2. Comprobación de Nuevas Versiones")

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        check_clicked = st.button("🔍 Buscar Actualizaciones", key="btn_check_updates", width="stretch")

    if check_clicked:
        with st.spinner("Consultando GitHub API..."):
            check_result = api_client.check_for_updates(force=True, branch=branch)
            st.session_state["updater_check_result"] = check_result

    check_res = st.session_state.get("updater_check_result")

    if check_res:
        err = check_res.get("error")
        if err:
            st.warning(f"⚠️ {err}")
        else:
            update_available = check_res.get("update_available", False)
            remote_sha = str(check_res.get("remote_commit", ""))
            remote_msg = check_res.get("remote_commit_message", "")
            remote_date = format_iso_timestamp(check_res.get("remote_commit_date"))
            cached_flag = check_res.get("cached", False)

            if not update_available:
                st.success(f"✅ **¡Tu sistema está al día!** Tienes instalada la versión más reciente en GitHub (`{remote_sha[:7]}`).")
                if cached_flag:
                    st.caption("ℹ️ Resultado obtenido de la memoria caché (búfer de 15 minutos).")
            else:
                st.info(
                    f"✨ **Hay una nueva versión disponible en GitHub:** Commit `[{remote_sha[:7]}]` "
                    f"publicado el {remote_date} en la rama `{branch}`."
                )

                # Tarjeta de novedades del commit
                with st.expander("📋 Ver detalles de la nueva versión", expanded=True):
                    st.markdown(f"**Título del Commit:** {remote_msg or 'Actualización de mantenimiento'}")
                    st.markdown(f"**Hash Completo:** `{remote_sha}`")
                    st.markdown(f"**Fecha en GitHub:** {remote_date}")

                # ==============================================================================
                # TARJETA 3: APLICAR ACTUALIZACIÓN EN 1 CLIC
                # ==============================================================================
                st.markdown("---")
                st.subheader("3. Aplicar Actualización")
                st.markdown(
                    "El proceso se ejecutará de forma atómica y segura:\n"
                    "1. Se descargará el código en una carpeta temporal (*staging*).\n"
                    "2. Se validará la sintaxis completa antes de tocar producción.\n"
                    "3. Se creará una copia de seguridad preventiva de tu base de datos y código previo.\n"
                    "4. Se transferirán los nuevos archivos y se limpiarán los obsoletos."
                )

                confirm_update = st.checkbox(
                    "He leído las indicaciones y deseo actualizar el sistema ahora.",
                    key="chk_confirm_update",
                )

                if st.button(
                    "🚀 Actualizar a la Última Versión",
                    key="btn_apply_update",
                    type="primary",
                    disabled=not confirm_update,
                ):
                    progress_bar = st.progress(10)
                    status_text = st.empty()

                    status_text.text("Descargando paquete desde GitHub...")
                    progress_bar.progress(30)
                    time.sleep(0.5)

                    status_text.text("Validando sintaxis y creando copia de seguridad preventiva...")
                    progress_bar.progress(60)

                    apply_res = api_client.apply_system_update(branch=branch, remote_commit=remote_sha)

                    if apply_res and apply_res.get("success"):
                        progress_bar.progress(100)
                        status_text.empty()
                        st.success(apply_res.get("message", "¡Actualización completada con éxito!"))

                        if apply_res.get("requires_rebuild"):
                            st.warning(
                                "⚠️ **Cambios en dependencias detectados:** Se han modificado librerías en `requirements/`. "
                                "Si ejecutas la aplicación con Docker Compose, se recomienda reiniciar los contenedores "
                                "(`docker compose restart`) para activar los nuevos paquetes."
                            )

                        st.info("💡 Por favor, pulsa el botón a continuación para recargar la aplicación y cargar los nuevos cambios.")
                        if st.button("🔄 Recargar Aplicación Ahora", key="btn_reload_after_update", type="primary"):
                            st.session_state.pop("updater_check_result", None)
                            st.rerun()
                    else:
                        progress_bar.empty()
                        status_text.empty()
                        err_msg = apply_res.get("message") if apply_res else "Error desconocido del servidor"
                        st.error(f"❌ No se pudo completar la actualización: {err_msg}")
