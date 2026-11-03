from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class VersionInfo(BaseModel):
    """Información sobre la versión actualmente instalada del sistema."""
    model_config = ConfigDict(from_attributes=True)

    current_commit: str = Field(default="initial", description="Hash SHA del commit instalado")
    branch: str = Field(default="main", description="Rama configurada en el sistema")
    last_updated_at: Optional[str] = Field(default=None, description="Timestamp ISO-8601 de la última actualización")
    commit_message: Optional[str] = Field(default=None, description="Mensaje o título del commit instalado")
    rollback_available: bool = Field(default=False, description="True si existe una instantánea de código previo para revertir")
    is_git_repo: bool = Field(default=False, description="True si se detecta un repositorio Git local en la raíz")


class UpdateCheckResponse(BaseModel):
    """Respuesta de la comprobación de actualizaciones remotas en GitHub."""
    model_config = ConfigDict(from_attributes=True)

    update_available: bool = Field(description="True si el commit remoto difiere del commit local activo")
    current_commit: str = Field(description="Hash del commit local activo")
    remote_commit: str = Field(description="Hash del último commit disponible en GitHub")
    remote_commit_message: str = Field(default="", description="Mensaje del último commit remoto")
    remote_commit_date: Optional[str] = Field(default=None, description="Timestamp ISO-8601 del commit en GitHub")
    branch: str = Field(description="Rama consultada en el repositorio remoto")
    checked_at: str = Field(description="Timestamp ISO-8601 del momento de la consulta")
    cached: bool = Field(default=False, description="True si la información proviene de la caché en memoria")
    rate_limit_remaining: Optional[int] = Field(default=None, description="Peticiones restantes a la API de GitHub")
    error: Optional[str] = Field(default=None, description="Mensaje de error si la consulta falló")


class UpdateApplyRequest(BaseModel):
    """Parámetros opcionales para solicitar la aplicación de una actualización."""
    model_config = ConfigDict(from_attributes=True)

    branch: Optional[str] = Field(default=None, description="Rama remota a instalar")
    remote_commit: Optional[str] = Field(default=None, description="Hash del commit objetivo")


class UpdateApplyResponse(BaseModel):
    """Resultado de la ejecución de una actualización del sistema."""
    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(description="Indica si la actualización se aplicó correctamente")
    previous_commit: str = Field(description="Hash del commit previo antes de actualizar")
    updated_to_commit: str = Field(description="Hash del nuevo commit instalado")
    files_updated_count: int = Field(ge=0, default=0, description="Total de archivos actualizados/instalados")
    obsolete_files_pruned_count: int = Field(ge=0, default=0, description="Total de archivos obsoletos eliminados")
    pre_update_backup_path: Optional[str] = Field(default=None, description="Ruta del respaldo previo de base de datos")
    new_dependencies_detected: bool = Field(default=False, description="True si se detectaron cambios en requirements/")
    requires_rebuild: bool = Field(default=False, description="True si se sugiere reiniciar el contenedor Docker o entorno")
    message: str = Field(description="Mensaje descriptivo en español para el usuario")


class CodeRollbackResponse(BaseModel):
    """Resultado de la operación de reversión de código a la instantánea previa."""
    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(description="Indica si la reversión de código tuvo éxito")
    restored_commit: str = Field(description="Hash del commit restaurado")
    message: str = Field(description="Mensaje descriptivo en español para el usuario")

