"""
Paquete de vistas frontend para la aplicación Gestor de Finanzas.
"""

from .joint_view import render_joint_view
from .backup_view import render_backup_view
from .updater_view import render_updater_view
from .mobile_view import render_mobile_view

__all__ = ["render_joint_view", "render_backup_view", "render_updater_view", "render_mobile_view"]
