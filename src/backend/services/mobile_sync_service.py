"""
Fachada del Servicio de Sincronización Móvil Quick-Capture (Spec 016 / Spec 017).
Delega en el paquete modular backend.services.mobile manteniendo compatibilidad total de contratos.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from backend.domain.constants import is_income_category as is_income_cat_canonical
from backend.domain.models.categories import Category, Subcategory
from backend.domain.schemas.mobile import (
    MobileCatalogResponse,
    MobileHistoricalTransactionItem,
    MobileMonthlySummaryResponse,
    MobileSearchResponse,
    MobileSyncRequest,
    MobileSyncResponse,
    MobileSyncStatusResponse,
    MobileVersionResponse,
)
from backend.services.mobile import (
    ingestion_service,
    ota_service,
    pairing_service,
    receipt_storage,
    summary_service,
)
from backend.services.sync_storage import resolve_sync_dir


class MobileSyncService:
    """Fachada unificada para la operativa de sincronización con clientes móviles."""

    def __init__(self, base_sync_dir: Optional[str] = None):
        self.base_dir = resolve_sync_dir(base_sync_dir)
        self.mobile_dir = self.base_dir / "mobile"
        self.inbox_dir = self.mobile_dir / "inbox"
        self.processed_dir = self.mobile_dir / "processed"
        self.error_dir = self.mobile_dir / "error"
        self.catalog_dir = self.mobile_dir / "catalog"
        self.apk_dir = self.mobile_dir / "apk"
        self.receipts_dir = self.mobile_dir / "receipts"
        self.pairing_file = self.mobile_dir / "pairing_secret.txt"
        self.pin_file = self.mobile_dir / "active_pin.json"
        self.deleted_events_file = self.mobile_dir / "deleted_event_ids.json"

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Asegura la existencia de la jerarquía de carpetas de sincronización móvil."""
        for d in [
            self.inbox_dir,
            self.processed_dir,
            self.error_dir,
            self.catalog_dir,
            self.apk_dir,
            self.receipts_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def is_income_category(cat: Optional[Category]) -> bool:
        """Determina de forma uniforme si una categoría representa ingresos."""
        return is_income_cat_canonical(cat)

    def get_deleted_event_ids(self) -> Set[str]:
        return ingestion_service.get_deleted_event_ids(self.deleted_events_file)

    def record_deleted_event_id(self, event_id: str) -> None:
        ingestion_service.record_deleted_event_id(self.deleted_events_file, event_id)

    def get_or_create_pairing_token(self) -> str:
        return pairing_service.get_or_create_pairing_token(self.pairing_file)

    def validate_pairing_token(self, token: Optional[str]) -> bool:
        return pairing_service.validate_pairing_token(self.pairing_file, token)

    def generate_pairing_pin(self, ttl_seconds: int = 600) -> Dict[str, Any]:
        return pairing_service.generate_pairing_pin(self.pin_file, ttl_seconds=ttl_seconds)

    def pair_with_pin(self, candidate_pin: str) -> Tuple[bool, Optional[str], str]:
        return pairing_service.pair_with_pin(self.pin_file, self.pairing_file, candidate_pin)

    def create_or_get_subcategory(
        self,
        db: Session,
        name: str,
        category_name: Optional[str] = None,
        category_id: Optional[int] = None,
    ) -> Tuple[Subcategory, bool]:
        return ingestion_service.create_or_get_subcategory(
            db=db,
            name=name,
            category_name=category_name,
            category_id=category_id,
            on_created_export=self.export_catalog_file,
        )

    def get_mobile_catalog(self, db: Session, local_device_id: Optional[str] = None) -> MobileCatalogResponse:
        return ingestion_service.get_mobile_catalog(db, local_device_id=local_device_id)

    def process_mobile_sync(self, db: Session, request: MobileSyncRequest) -> MobileSyncResponse:
        return ingestion_service.process_mobile_sync(
            db=db,
            request=request,
            deleted_events_file=self.deleted_events_file,
            save_receipt_cb=self.save_receipt_base64,
            on_created_export=self.export_catalog_file,
        )

    def process_mobile_inbox_folder(self, db: Session) -> int:
        return ingestion_service.process_mobile_inbox_folder(
            db=db,
            inbox_dir=self.inbox_dir,
            processed_dir=self.processed_dir,
            error_dir=self.error_dir,
            sync_cb=self.process_mobile_sync,
        )

    def export_catalog_file(self, db: Session) -> Path:
        return ingestion_service.export_catalog_file(db, self.catalog_dir)

    def get_sync_status(self, db: Session, authenticated: bool = False) -> MobileSyncStatusResponse:
        return ingestion_service.get_sync_status(db, self.inbox_dir, authenticated=authenticated)

    def get_mobile_monthly_summary(
        self, db: Session, month_key: Optional[str] = None, month: Optional[str] = None
    ) -> MobileMonthlySummaryResponse:
        return summary_service.get_mobile_monthly_summary(db, month_key=month_key, month=month)

    def update_mobile_budget(
        self,
        db: Session,
        update: Any,
        amount: Optional[float] = None,
        month: Optional[str] = None,
    ) -> bool:
        return summary_service.update_mobile_budget(db, update, amount=amount, month=month)

    def get_mobile_version_info(self) -> MobileVersionResponse:
        return ota_service.get_mobile_version_info(self.apk_dir)

    def get_latest_apk_path(self, preferred_filename: Optional[str] = None) -> Optional[Path]:
        return ota_service.get_latest_apk_path(self.apk_dir, preferred_filename=preferred_filename)

    def publish_apk_release(
        self,
        apk_bytes: bytes,
        filename: str = "app-release.apk",
        version_code: int = 2,
        version_name: str = "1.1.0",
        release_notes: str = "",
    ) -> MobileVersionResponse:
        return ota_service.publish_apk_release(
            self.apk_dir,
            apk_bytes=apk_bytes,
            filename=filename,
            version_code=version_code,
            version_name=version_name,
            release_notes=release_notes,
        )

    def delete_mobile_transaction(self, db: Session, identifier: str) -> Optional[int]:
        return ingestion_service.delete_mobile_transaction(
            db=db,
            identifier=identifier,
            deleted_events_file=self.deleted_events_file,
            delete_receipt_cb=self.delete_receipt_file,
        )

    def search_transactions(
        self, db: Session, query_text: str, limit: int = 50
    ) -> MobileSearchResponse:
        return summary_service.search_transactions(db, query_text=query_text, limit=limit)

    def get_historical_cache(
        self, db: Session, months: int = 12
    ) -> List[MobileHistoricalTransactionItem]:
        return summary_service.get_historical_cache(db, months=months)

    def save_receipt_base64(self, event_id: str, base64_str: str) -> Optional[str]:
        return receipt_storage.save_receipt_base64(self.receipts_dir, event_id, base64_str)

    def save_receipt_file(self, event_id: str, file_bytes: bytes) -> Optional[str]:
        return receipt_storage.save_receipt_file(self.receipts_dir, event_id, file_bytes)

    def get_receipt_path(self, filename: str) -> Optional[Path]:
        return receipt_storage.get_receipt_path(self.receipts_dir, filename)

    def delete_receipt_file(self, filename: Optional[str]) -> bool:
        return receipt_storage.delete_receipt_file(self.receipts_dir, filename)
