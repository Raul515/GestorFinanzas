from datetime import datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class DatabaseHealthResponse(BaseModel):
    """Diagnóstico de salud, integridad y estado de la base de datos SQLite activa."""
    model_config = ConfigDict(from_attributes=True)

    status: Literal["HEALTHY", "DEGRADED", "CORRUPTED"] = Field(
        description="Estado general de salud de la base de datos"
    )
    database_path: str = Field(description="Ruta normalizada del fichero SQLite activo")
    file_size_bytes: int = Field(ge=0, description="Tamaño del archivo en bytes")
    file_size_formatted: str = Field(description="Tamaño legible para humanos (ej. 1.25 MB)")
    sha256: str = Field(description="Hash criptográfico SHA-256 de la base de datos activa")
    last_modified: Optional[str] = Field(
        default=None, description="Timestamp ISO-8601 de última modificación en disco"
    )
    integrity_check_passed: bool = Field(
        description="Indica si PRAGMA integrity_check devolvió 'ok'"
    )
    table_counts: Dict[str, int] = Field(
        default_factory=dict, description="Recuento de registros de tablas maestras"
    )
    days_since_last_backup: Optional[int] = Field(
        default=None, ge=0, description="Días transcurridos desde el último respaldo registrado"
    )
    last_backup_at: Optional[str] = Field(
        default=None, description="Timestamp ISO-8601 del último respaldo disponible"
    )
    backup_warning_needed: bool = Field(
        default=False, description="True si han pasado más de 14 días sin respaldo o no hay copias"
    )


class BackupMetadata(BaseModel):
    """Metadatos descriptivos de un archivo de copia de seguridad."""
    model_config = ConfigDict(from_attributes=True)

    filename: str = Field(description="Nombre del archivo (ej. manual_backup_20261103_093000.db)")
    created_at: str = Field(description="Fecha y hora de creación ISO-8601")
    file_size_bytes: int = Field(ge=0, description="Tamaño en bytes")
    file_size_formatted: str = Field(description="Tamaño legible")
    sha256: str = Field(description="Hash SHA-256 del archivo de respaldo")
    backup_type: Literal["MANUAL", "AUTOMATIC", "SAFETY_PRERESTORE"] = Field(
        description="Origen de la copia: manual, programada o instantánea de seguridad"
    )


class BackupListResponse(BaseModel):
    """Catálogo de instantáneas locales disponibles en el servidor."""
    model_config = ConfigDict(from_attributes=True)

    backups: List[BackupMetadata] = Field(
        default_factory=list, description="Lista de respaldos ordenados cronológicamente descendente"
    )
    total_count: int = Field(ge=0, description="Total de copias de seguridad almacenadas")
    latest_safety_snapshot: Optional[str] = Field(
        default=None, description="Nombre del snapshot previo más reciente disponible para rollback"
    )


class BackupValidationResult(BaseModel):
    """Resultado de la inspección e integridad de un archivo SQLite antes de restaurar."""
    is_valid: bool = Field(description="Indica si el archivo es apto y válido para restaurar")
    integrity_status: str = Field(description="Resultado de PRAGMA integrity_check (ej. 'ok')")
    table_counts: Dict[str, int] = Field(
        default_factory=dict, description="Conteo de registros detectados por tabla"
    )
    sha256: str = Field(description="Hash SHA-256 del archivo analizado")
    error_message: Optional[str] = Field(
        default=None, description="Detalle del error en caso de invalidez"
    )


class RestoreResponse(BaseModel):
    """Resultado de la ejecución de una restauración o rollback de base de datos."""
    success: bool = Field(description="True si la restauración se completó exitosamente")
    message: str = Field(description="Mensaje descriptivo para el usuario")
    safety_snapshot_filename: Optional[str] = Field(
        default=None, description="Nombre de la instantánea previa creada antes de sobrescribir"
    )
    can_rollback: bool = Field(
        default=False, description="True si es posible deshacer la restauración"
    )
    restored_table_counts: Dict[str, int] = Field(
        default_factory=dict, description="Registros existentes por tabla tras la restauración"
    )


class BackupScheduleResponse(BaseModel):
    """Estado y configuración de la programación periódica de copias automáticas."""
    model_config = ConfigDict(from_attributes=True)

    enabled: bool = Field(description="Indica si las copias automáticas están activas")
    frequency_days: int = Field(ge=1, le=365, description="Frecuencia en días (ej. 7, 14, 30)")
    keep_max_copies: int = Field(ge=3, le=20, description="Máximo de instantáneas a conservar")
    last_automated_backup_at: Optional[str] = Field(
        default=None, description="Fecha/hora ISO-8601 del último respaldo automático"
    )
    next_backup_estimated_at: Optional[str] = Field(
        default=None, description="Fecha estimada de la próxima ejecución automática"
    )
    last_backup_sha256: Optional[str] = Field(
        default=None, description="Hash SHA-256 de la última copia para evitar duplicados"
    )


class BackupScheduleUpdate(BaseModel):
    """Esquema de actualización para la configuración de copias periódicas."""
    enabled: bool = Field(default=True, description="Habilitar o pausar copias periódicas")
    frequency_days: int = Field(
        default=14, ge=1, le=365, description="Frecuencia de ejecución en días"
    )
    keep_max_copies: int = Field(
        default=5, ge=3, le=20, description="Límite de copias a retener (3 a 20)"
    )
