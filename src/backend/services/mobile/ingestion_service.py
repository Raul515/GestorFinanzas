"""Ingesta idempotente, catálogo móvil, tombstones y procesamiento de buzones en disco."""

from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from typing import Callable, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from backend.domain.constants import classify_category_block, is_income_category as is_income_cat_canonical
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
from backend.services.sync_storage import (
    archive_processed_file,
    get_or_create_device_id,
    is_sync_event_file,
    quarantine_error_file,
)
from backend.utils.files import atomic_write_json

logger = logging.getLogger(__name__)


def get_deleted_event_ids(deleted_events_file: Path) -> Set[str]:
    """Retorna el conjunto de UUIDs de eventos móviles eliminados (tombstones)."""
    if not deleted_events_file.exists():
        return set()
    try:
        with open(deleted_events_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except Exception as exc:
        logger.warning("Error leyendo deleted_event_ids.json: %s", exc)
        return set()


def record_deleted_event_id(deleted_events_file: Path, event_id: str) -> None:
    """Registra un UUID de evento móvil en el archivo persistente de eliminados (tombstones)."""
    if not event_id or not event_id.strip():
        return
    cleaned = event_id.strip()
    deleted_set = get_deleted_event_ids(deleted_events_file)
    if cleaned in deleted_set:
        return
    deleted_set.add(cleaned)
    try:
        atomic_write_json(deleted_events_file, sorted(list(deleted_set)))
        logger.info("UUID móvil registrado como eliminado (tombstone): %s", cleaned)
    except Exception as exc:
        logger.error("Error registrando tombstone en deleted_event_ids.json: %s", exc)


def create_or_get_subcategory(
    db: Session,
    name: str,
    category_name: Optional[str] = None,
    category_id: Optional[int] = None,
    on_created_export: Optional[Callable[[Session], Path]] = None,
) -> Tuple[Subcategory, bool]:
    """Crea de forma idempotente una nueva subcategoría o retorna la existente."""
    clean_name = name.strip()
    existing = (
        db.query(Subcategory)
        .filter(func.lower(Subcategory.name) == clean_name.lower())
        .first()
    )
    if existing:
        return existing, False

    target_cat = None
    if category_id:
        target_cat = db.query(Category).filter(Category.id == category_id).first()

    if not target_cat and category_name:
        all_cats = db.query(Category).all()
        block = classify_category_block(category_name)
        if block is not None:
            target_cat = next((c for c in all_cats if classify_category_block(c) == block), None)
        if not target_cat:
            c_name_lower = category_name.strip().lower()
            target_cat = (
                db.query(Category)
                .filter(func.lower(Category.name).like(f"%{c_name_lower}%"))
                .first()
            )

    if not target_cat:
        target_cat = db.query(Category).filter(func.lower(Category.name).like("%deseo%")).first()
        if not target_cat:
            target_cat = db.query(Category).first()

    if not target_cat:
        raise ValueError("No se puede crear subcategoría porque no existen categorías en la base de datos")

    new_subcat = Subcategory(name=clean_name, category_id=target_cat.id)
    db.add(new_subcat)
    db.commit()
    db.refresh(new_subcat)
    logger.info("Subcategoría creada al vuelo desde el móvil: '%s' (Categoría: %s)", clean_name, target_cat.name)

    if on_created_export:
        try:
            on_created_export(db)
        except Exception:
            pass

    return new_subcat, True


def get_mobile_catalog(db: Session, local_device_id: Optional[str] = None) -> MobileCatalogResponse:
    """Genera el catálogo de categorías, subcategorías y conceptos frecuentes para móvil."""
    device_id = local_device_id or get_or_create_device_id()
    now_utc = datetime.now(timezone.utc).isoformat()

    subcats = (
        db.query(Subcategory)
        .options(joinedload(Subcategory.category))
        .join(Category)
        .order_by(Category.id, Subcategory.name)
        .all()
    )

    cutoff_date = date.today() - timedelta(days=90)
    top_subcat_rows = (
        db.query(Transaction.subcategory_id, func.count(Transaction.id).label("freq"))
        .filter(Transaction.date >= cutoff_date, Transaction.subcategory_id.isnot(None))
        .group_by(Transaction.subcategory_id)
        .order_by(func.count(Transaction.id).desc())
        .limit(6)
        .all()
    )
    top_subcat_ids = {row[0] for row in top_subcat_rows if row[0] is not None}

    if not top_subcat_ids:
        common_keywords = {
            "café", "cafe", "supermercado", "comida", "restaurante",
            "gasolina", "farmacia", "ocio", "bizum", "nómina", "nomina",
        }
        for s in subcats:
            if any(kw in s.name.lower() for kw in common_keywords) and len(top_subcat_ids) < 6:
                top_subcat_ids.add(s.id)

    personal_subcategories = []
    for s in subcats:
        cat_name = s.category.name if s.category else "General"
        cat_type = "income" if is_income_cat_canonical(s.category) else "expense"
        personal_subcategories.append(
            MobileCatalogSubcategory(
                id=s.id,
                name=s.name,
                category_id=s.category_id,
                category_name=cat_name,
                category_type=cat_type,
                is_frequent=(s.id in top_subcat_ids),
            )
        )

    personal_subcategories.sort(key=lambda s: (not s.is_frequent, s.category_id, s.name.lower()))

    top_concept_rows = (
        db.query(func.trim(Transaction.description).label("concept"), func.count(Transaction.id).label("freq"))
        .filter(
            Transaction.date >= cutoff_date,
            Transaction.description.isnot(None),
            func.trim(Transaction.description) != "",
        )
        .group_by(func.trim(Transaction.description))
        .order_by(func.count(Transaction.id).desc())
        .limit(15)
        .all()
    )
    frequent_concepts = [row[0] for row in top_concept_rows if row[0]]

    return MobileCatalogResponse(
        device_id=device_id,
        last_updated_utc=now_utc,
        personal_subcategories=personal_subcategories,
        frequent_concepts=frequent_concepts,
    )


def process_mobile_sync(
    db: Session,
    request: MobileSyncRequest,
    deleted_events_file: Path,
    save_receipt_cb: Callable[[str, str], Optional[str]],
    on_created_export: Optional[Callable[[Session], Path]] = None,
) -> MobileSyncResponse:
    """Procesa de forma atómica e idempotente un lote de transacciones móviles personales."""
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
    deleted_ids = get_deleted_event_ids(deleted_events_file)

    all_subcats = db.query(Subcategory).all()
    subcat_by_id = {s.id: s for s in all_subcats}
    subcat_by_name = {s.name.strip().lower(): s for s in all_subcats}

    try:
        for item in request.transactions:
            if item.event_id and item.event_id in deleted_ids:
                logger.info("Ignorando transacción móvil %s porque fue eliminada previamente (tombstone)", item.event_id)
                ignored_duplicates_count += 1
                continue

            if item.event_id:
                existing = (
                    db.query(Transaction)
                    .filter(Transaction.mobile_event_id == item.event_id)
                    .first()
                )
                if existing:
                    ignored_duplicates_count += 1
                    continue

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

            eff_subcat = subcat_by_id.get(candidate_subcat_id) if candidate_subcat_id is not None else None
            if not eff_subcat and item.subcategory_name:
                eff_subcat = subcat_by_name.get(item.subcategory_name.strip().lower())

            if not eff_subcat and item.subcategory_name:
                is_income = (getattr(item, "type", None) or "").upper() == "INCOME"
                fallback_cat = "Ingresos Netos" if is_income else "Deseos (30%)"
                eff_subcat, _ = create_or_get_subcategory(
                    db,
                    item.subcategory_name,
                    category_name=fallback_cat,
                    on_created_export=on_created_export,
                )
                subcat_by_id[eff_subcat.id] = eff_subcat
                subcat_by_name[eff_subcat.name.strip().lower()] = eff_subcat

            if not eff_subcat:
                eff_subcat = all_subcats[0] if all_subcats else None
                if not eff_subcat:
                    logger.error("No existen subcategorías en la base de datos para asignar el gasto móvil")
                    continue

            saved_receipt_filename = None
            if getattr(item, "receipt_base64", None):
                saved_receipt_filename = save_receipt_cb(item.event_id, item.receipt_base64)
            elif getattr(item, "receipt_filename", None):
                saved_receipt_filename = item.receipt_filename

            new_tx = Transaction(
                date=item.date,
                subcategory_id=eff_subcat.id,
                amount=round(float(item.amount), 2),
                description=clean_desc,
                mobile_event_id=item.event_id,
                receipt_filename=saved_receipt_filename,
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


def process_mobile_inbox_folder(
    db: Session,
    inbox_dir: Path,
    processed_dir: Path,
    error_dir: Path,
    sync_cb: Callable[[Session, MobileSyncRequest], MobileSyncResponse],
) -> int:
    """Escanea sync/mobile/inbox/ para procesar archivos delta JSON depositados en disco."""
    total_processed = 0
    if not inbox_dir.exists():
        return 0

    for file_path in sorted(inbox_dir.iterdir()):
        if not is_sync_event_file(file_path, require_json=True):
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

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

            res = sync_cb(db, sync_req)
            total_processed += res.processed_count

            archive_processed_file(file_path, processed_dir)
            logger.info("Fichero móvil delta procesado y archivado: %s", file_path.name)
        except Exception as exc:
            logger.error("Error procesando fichero delta móvil %s: %s", file_path.name, exc)
            quarantine_error_file(file_path, error_dir)

    return total_processed


def export_catalog_file(db: Session, catalog_dir: Path, local_device_id: Optional[str] = None) -> Path:
    """Genera y deposita de forma atómica el archivo mobile_catalog.json en sync/mobile/catalog/."""
    catalog = get_mobile_catalog(db, local_device_id=local_device_id)
    final_path = catalog_dir / "mobile_catalog.json"
    atomic_write_json(final_path, catalog.model_dump())
    logger.info("Catálogo móvil exportado atómicamente a: %s", final_path.name)
    return final_path


def get_sync_status(db: Session, inbox_dir: Path, authenticated: bool = False) -> MobileSyncStatusResponse:
    """Obtiene el estado de salud y métricas de sincronización móvil sin filtrar el token secreto."""
    today = date.today()
    today_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.date == today)
        .scalar()
        or 0
    )

    pending_files = 0
    if inbox_dir.exists():
        pending_files = len([
            f for f in inbox_dir.iterdir()
            if is_sync_event_file(f, require_json=True)
        ])

    return MobileSyncStatusResponse(
        server_online=True,
        server_time_utc=datetime.now(timezone.utc).isoformat(),
        today_transactions_count=int(today_count),
        pending_inbox_files=pending_files,
        pairing_token=None,
        authenticated=authenticated,
    )


def delete_mobile_transaction(
    db: Session,
    identifier: str,
    deleted_events_file: Path,
    delete_receipt_cb: Callable[[Optional[str]], bool],
) -> Optional[int]:
    """Elimina una transacción identificada por ID o mobile_event_id y limpia su comprobante."""
    clean_id = identifier.strip()
    tx = None
    if clean_id.isdigit():
        tx = db.query(Transaction).filter(Transaction.id == int(clean_id)).first()

    if not tx:
        tx = db.query(Transaction).filter(Transaction.mobile_event_id == clean_id).first()

    if not tx:
        logger.warning("No se encontró transacción para eliminar con identificador: %s", clean_id)
        return None

    tx_id = tx.id
    tx_mob_id = getattr(tx, "mobile_event_id", None)
    receipt_to_delete = getattr(tx, "receipt_filename", None)
    from backend.database.componentes.sqlite_crud import SQLiteRepository

    repo = SQLiteRepository(db)
    success = repo.delete_transaction(tx_id)
    if success:
        if tx_mob_id:
            record_deleted_event_id(deleted_events_file, tx_mob_id)
        if receipt_to_delete:
            delete_receipt_cb(receipt_to_delete)
        logger.info("Transacción móvil eliminada con éxito (ID: %s, event_id: %s)", tx_id, tx_mob_id)
        return tx_id
    return None
