"""
Servicio de Sincronización Móvil Quick-Capture (Spec 016).
Gestiona la generación del catálogo para clientes móviles, la ingesta atómica
idempotente de transacciones personales y el procesamiento complementario
de buzones de sincronización física en disco.
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.domain.models.categories import Category, Subcategory
from backend.domain.models.transactions import Transaction
from backend.domain.schemas.mobile import (
    MobileCatalogResponse,
    MobileCatalogSubcategory,
    MobileSyncRequest,
    MobileSyncResponse,
    MobileSyncStatusResponse,
    MobileTransactionPayload,
)
from backend.services.joint_sync_service import get_or_create_device_id

logger = logging.getLogger(__name__)


class MobileSyncService:
    """Servicio desacoplado para la operativa de sincronización con clientes móviles."""

    def __init__(self, base_sync_dir: Optional[str] = None):
        env_sync_dir = os.environ.get("BASE_SYNC_DIR")
        if base_sync_dir:
            self.base_dir = Path(base_sync_dir)
        elif env_sync_dir and env_sync_dir.strip():
            self.base_dir = Path(env_sync_dir.strip())
        else:
            root_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.base_dir = root_dir / "sync"

        self.mobile_dir = self.base_dir / "mobile"
        self.inbox_dir = self.mobile_dir / "inbox"
        self.outbox_dir = self.mobile_dir / "outbox"
        self.processed_dir = self.mobile_dir / "processed"
        self.error_dir = self.mobile_dir / "error"
        self.catalog_dir = self.mobile_dir / "catalog"

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Asegura la existencia de la jerarquía de carpetas de sincronización móvil."""
        for d in [self.inbox_dir, self.outbox_dir, self.processed_dir, self.error_dir, self.catalog_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def get_mobile_catalog(self, db: Session, local_device_id: Optional[str] = None) -> MobileCatalogResponse:
        """
        Genera el catálogo de categorías, subcategorías y conceptos frecuentes
        para clientes móviles, calculando la frecuencia de uso en los últimos 90 días.
        """
        device_id = local_device_id or get_or_create_device_id()
        now_utc = datetime.now(timezone.utc).isoformat()

        # 1. Recuperar todas las subcategorías con su categoría padre
        subcats = (
            db.query(Subcategory)
            .join(Category)
            .order_by(Category.id, Subcategory.name)
            .all()
        )

        # 2. Análisis de frecuencia de los últimos 90 días
        cutoff_date = date.today() - timedelta(days=90)
        recent_txs = (
            db.query(Transaction)
            .filter(Transaction.date >= cutoff_date)
            .all()
        )

        subcat_counter = Counter(t.subcategory_id for t in recent_txs if t.subcategory_id)
        concept_counter = Counter(
            t.description.strip()
            for t in recent_txs
            if t.description and t.description.strip()
        )

        # Determinar los IDs de las 6 subcategorías más usadas
        top_subcat_ids = {subcat_id for subcat_id, _ in subcat_counter.most_common(6)}

        # Fallback si no hay transacciones recientes: marcar subcategorías clave cotidianas
        if not top_subcat_ids:
            common_keywords = {"café", "cafe", "supermercado", "comida", "restaurante", "gasolina", "farmacia", "ocio"}
            for s in subcats:
                if any(kw in s.name.lower() for kw in common_keywords) and len(top_subcat_ids) < 6:
                    top_subcat_ids.add(s.id)

        # Construir lista de subcategorías
        personal_subcategories: List[MobileCatalogSubcategory] = []
        for s in subcats:
            cat_name = s.category.name if s.category else "General"
            personal_subcategories.append(
                MobileCatalogSubcategory(
                    id=s.id,
                    name=s.name,
                    category_id=s.category_id,
                    category_name=cat_name,
                    is_frequent=(s.id in top_subcat_ids),
                )
            )

        # Ordenar: las frecuentes primero, luego alfabéticamente
        personal_subcategories.sort(key=lambda s: (not s.is_frequent, s.category_id, s.name.lower()))

        # Top 15 conceptos más recurrentes
        frequent_concepts = [concept for concept, _ in concept_counter.most_common(15)]

        return MobileCatalogResponse(
            device_id=device_id,
            last_updated_utc=now_utc,
            personal_subcategories=personal_subcategories,
            frequent_concepts=frequent_concepts,
        )

    def process_mobile_sync(self, db: Session, request: MobileSyncRequest) -> MobileSyncResponse:
        """
        Procesa de forma atómica e idempotente un lote de transacciones móviles personales.
        Garantiza que ningún fallo de red duplique gastos en la base de datos.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        if not request.transactions:
            return MobileSyncResponse(
                success=True,
                processed_count=0,
                ignored_duplicates_count=0,
                server_timestamp_utc=now_utc,
            )

        processed_count = 0
        ignored_duplicates_count = 0

        # Mapeo rápido de subcategorías existentes por id y por nombre en minúsculas
        all_subcats = db.query(Subcategory).all()
        subcat_by_id = {s.id: s for s in all_subcats}
        subcat_by_name = {s.name.strip().lower(): s for s in all_subcats}

        try:
            for item in request.transactions:
                # 1. Comprobación idempotente primaria por UUID (mobile_event_id)
                if item.event_id:
                    existing = (
                        db.query(Transaction)
                        .filter(Transaction.mobile_event_id == item.event_id)
                        .first()
                    )
                    if existing:
                        ignored_duplicates_count += 1
                        continue

                # 2. Comprobación secundaria por contenido exacto (misma fecha, importe, subcategoría y concepto)
                candidate_subcat_id = item.subcategory_id
                if candidate_subcat_id not in subcat_by_id and item.subcategory_name:
                    matched = subcat_by_name.get(item.subcategory_name.strip().lower())
                    if matched:
                        candidate_subcat_id = matched.id

                clean_desc = item.description.strip()
                exact_match = (
                    db.query(Transaction)
                    .filter(
                        Transaction.date == item.date,
                        Transaction.subcategory_id == candidate_subcat_id,
                        func.abs(Transaction.amount - item.amount) < 0.001,
                        Transaction.description == clean_desc,
                    )
                    .first()
                )
                if exact_match and exact_match.mobile_event_id == item.event_id:
                    ignored_duplicates_count += 1
                    continue

                # 3. Resolución segura de subcategoría
                eff_subcat = subcat_by_id.get(candidate_subcat_id)
                if not eff_subcat and item.subcategory_name:
                    eff_subcat = subcat_by_name.get(item.subcategory_name.strip().lower())

                if not eff_subcat:
                    # Fallback defensivo a la primera subcategoría disponible
                    eff_subcat = all_subcats[0] if all_subcats else None
                    if not eff_subcat:
                        logger.error("No existen subcategorías en la base de datos para asignar el gasto móvil")
                        continue

                # 4. Inserción de la transacción
                new_tx = Transaction(
                    date=item.date,
                    subcategory_id=eff_subcat.id,
                    amount=round(float(item.amount), 2),
                    description=clean_desc,
                    mobile_event_id=item.event_id,
                )
                db.add(new_tx)
                processed_count += 1

            db.commit()
            logger.info(
                "Sincronización móvil completada con éxito: %d procesados, %d duplicados ignorados",
                processed_count,
                ignored_duplicates_count,
            )
        except Exception as exc:
            db.rollback()
            logger.error("Error crítico durante la ingesta de transacciones móviles: %s", exc)
            raise

        return MobileSyncResponse(
            success=True,
            processed_count=processed_count,
            ignored_duplicates_count=ignored_duplicates_count,
            server_timestamp_utc=now_utc,
        )

    def process_mobile_inbox_folder(self, db: Session) -> int:
        """
        Escanea sync/mobile/inbox/ para procesar archivos delta JSON depositados
        (por ejemplo mediante sincronización de carpetas de Syncthing).
        """
        total_processed = 0
        if not self.inbox_dir.exists():
            return 0

        for file_path in sorted(self.inbox_dir.iterdir()):
            if not file_path.is_file() or file_path.name.startswith(".") or file_path.suffix.lower() != ".json":
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                # Puede ser un MobileSyncRequest completo o un payload de transacción única
                if isinstance(raw_data, dict):
                    if "transactions" in raw_data:
                        sync_req = MobileSyncRequest.model_validate(raw_data)
                    else:
                        tx_payload = MobileTransactionPayload.model_validate(raw_data)
                        sync_req = MobileSyncRequest(device_id="syncthing-file", transactions=[tx_payload])
                elif isinstance(raw_data, list):
                    txs = [MobileTransactionPayload.model_validate(item) for item in raw_data]
                    sync_req = MobileSyncRequest(device_id="syncthing-file", transactions=txs)
                else:
                    raise ValueError(f"Formato JSON desconocido en {file_path.name}")

                res = self.process_mobile_sync(db, sync_req)
                total_processed += res.processed_count

                # Mover a processed de forma atómica
                dest_path = self.processed_dir / file_path.name
                if dest_path.exists():
                    dest_path.unlink()
                file_path.rename(dest_path)
                logger.info("Fichero móvil delta procesado y archivado: %s", file_path.name)
            except Exception as exc:
                logger.error("Error procesando fichero delta móvil %s: %s", file_path.name, exc)
                error_dest = self.error_dir / file_path.name
                if error_dest.exists():
                    error_dest.unlink()
                try:
                    file_path.rename(error_dest)
                except OSError:
                    pass

        return total_processed

    def export_catalog_file(self, db: Session) -> Path:
        """
        Genera y deposita de forma atómica el archivo mobile_catalog.json
        en sync/mobile/catalog/ para que Syncthing pueda propagarlo al móvil.
        """
        catalog = self.get_mobile_catalog(db)
        final_path = self.catalog_dir / "mobile_catalog.json"
        tmp_path = self.catalog_dir / "mobile_catalog.json.tmp"

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(catalog.model_dump(), f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, final_path)
        logger.info("Catálogo móvil exportado atómicamente a: %s", final_path.name)
        return final_path

    def get_sync_status(self, db: Session) -> MobileSyncStatusResponse:
        """Obtiene el estado de salud y métricas de sincronización móvil."""
        today = date.today()
        today_count = (
            db.query(func.count(Transaction.id))
            .filter(Transaction.date == today)
            .scalar()
            or 0
        )

        pending_files = 0
        if self.inbox_dir.exists():
            pending_files = len([
                f for f in self.inbox_dir.iterdir()
                if f.is_file() and not f.name.startswith(".") and f.suffix.lower() == ".json"
            ])

        return MobileSyncStatusResponse(
            server_online=True,
            server_time_utc=datetime.now(timezone.utc).isoformat(),
            today_transactions_count=int(today_count),
            pending_inbox_files=pending_files,
        )
