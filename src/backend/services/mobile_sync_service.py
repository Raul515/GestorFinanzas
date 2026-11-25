"""
Servicio de Sincronización Móvil Quick-Capture (Spec 016).
Gestiona la generación del catálogo para clientes móviles, la ingesta atómica
idempotente de transacciones personales y el procesamiento complementario
de buzones de sincronización física en disco.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import base64
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from backend.domain.models.budgets import MonthlyBudget
from backend.domain.models.categories import Category, Subcategory
from backend.domain.models.emergency_fund import EmergencyFund
from backend.domain.models.transactions import Transaction
from backend.domain.schemas.mobile import (
    MobileBudgetUpdate,
    MobileCatalogResponse,
    MobileCatalogSubcategory,
    MobileCategorySummary,
    MobileMonthlySummaryResponse,
    MobileSubcategoryCreate,
    MobileSubcategoryResponse,
    MobileSyncRequest,
    MobileSyncResponse,
    MobileSyncStatusResponse,
    MobileTransactionPayload,
    MobileHistoricalTransactionItem,
    MobileSearchResponse,
)
from backend.domain.constants import (
    CategoryBlock,
    classify_category_block,
    is_income_category as is_income_cat_canonical,
)
from backend.services.financial_calculator import calculate_503020_targets
from backend.services.joint_sync_service import get_or_create_device_id
from backend.services.safety_guard import (
    evaluate_safety_status,
    get_effective_monthly_budgets,
    resolve_monthly_needs,
)

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
        self.apk_dir = self.mobile_dir / "apk"
        self.receipts_dir = self.mobile_dir / "receipts"
        self.pairing_file = self.mobile_dir / "pairing_secret.txt"
        self.pin_file = self.mobile_dir / "active_pin.json"
        self.deleted_events_file = self.mobile_dir / "deleted_event_ids.json"

        self._ensure_directories()

    def get_deleted_event_ids(self) -> Set[str]:
        """Retorna el conjunto de UUIDs de eventos móviles eliminados (tombstones)."""
        if not self.deleted_events_file.exists():
            return set()
        try:
            with open(self.deleted_events_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
                return set()
        except Exception as e:
            logger.warning("Error leyendo deleted_event_ids.json: %s", e)
            return set()

    def record_deleted_event_id(self, event_id: str) -> None:
        """Registra un UUID de evento móvil en el archivo persistente de eliminados (tombstones)."""
        if not event_id or not event_id.strip():
            return
        cleaned = event_id.strip()
        deleted_set = self.get_deleted_event_ids()
        if cleaned in deleted_set:
            return
        deleted_set.add(cleaned)
        try:
            tmp_file = self.mobile_dir / "deleted_event_ids.json.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(sorted(list(deleted_set)), f, indent=2)
            os.replace(tmp_file, self.deleted_events_file)
            logger.info("UUID móvil registrado como eliminado (tombstone): %s", cleaned)
        except Exception as e:
            logger.error("Error registrando tombstone en deleted_event_ids.json: %s", e)

    def get_or_create_pairing_token(self) -> str:
        """Obtiene o genera de forma persistente el token secreto de emparejamiento."""
        if self.pairing_file.exists():
            try:
                with open(self.pairing_file, "r", encoding="utf-8") as f:
                    token = f.read().strip()
                if token:
                    return token
            except Exception as e:
                logger.warning("Error leyendo pairing_secret.txt: %s", e)

        new_token = f"sec_{secrets.token_hex(16)}"
        try:
            with open(self.pairing_file, "w", encoding="utf-8") as f:
                f.write(new_token)
            logger.info("Nuevo token de emparejamiento móvil generado y guardado")
        except Exception as e:
            logger.error("No se pudo persistir el pairing token: %s", e)
        return new_token

    def validate_pairing_token(self, token: Optional[str]) -> bool:
        """Valida que el token proporcionado por el cliente coincida con el token maestro."""
        if not token:
            return False
        master_token = self.get_or_create_pairing_token()
        return hmac.compare_digest(token.strip(), master_token)

    def generate_pairing_pin(self, ttl_seconds: int = 600) -> Dict[str, Any]:
        """Genera un PIN de 6 dígitos aleatorio criptográfico y lo persiste con fecha de expiración."""
        pin = f"{secrets.randbelow(1000000):06d}"
        now_dt = datetime.now(timezone.utc)
        expires_at_dt = now_dt + timedelta(seconds=ttl_seconds)

        pin_data = {
            "pin": pin,
            "expires_at_timestamp": expires_at_dt.timestamp(),
            "expires_at_utc": expires_at_dt.isoformat(),
            "failed_attempts": 0,
        }
        try:
            with open(self.pin_file, "w", encoding="utf-8") as f:
                json.dump(pin_data, f)
            logger.info("Nuevo PIN de emparejamiento móvil generado: [***%s]", pin[-2:])
        except Exception as e:
            logger.error("Error guardando active_pin.json: %s", e)
            raise
        return {
            "pin": pin,
            "expires_in_seconds": ttl_seconds,
            "expires_at_utc": expires_at_dt.isoformat(),
        }

    def pair_with_pin(self, candidate_pin: str) -> Tuple[bool, Optional[str], str]:
        """
        Valida un PIN suministrado por el cliente móvil.
        Si es correcto, consume el PIN y retorna (True, master_token, mensaje).
        Si falla, incrementa intentos fallidos y retorna (False, None, error_message).
        """
        if not self.pin_file.exists():
            return False, None, "No hay ningún PIN de vinculación activo. Genéralo en tu ordenador."

        try:
            with open(self.pin_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Error leyendo active_pin.json: %s", e)
            return False, None, "Error de lectura del PIN activo."

        now_ts = datetime.now(timezone.utc).timestamp()
        if now_ts > data.get("expires_at_timestamp", 0):
            try:
                self.pin_file.unlink(missing_ok=True)
            except Exception:
                pass
            return False, None, "El código PIN ha caducado. Genera uno nuevo en tu ordenador."

        failed = data.get("failed_attempts", 0)
        if failed >= 5:
            try:
                self.pin_file.unlink(missing_ok=True)
            except Exception:
                pass
            return False, None, "Demasiados intentos erróneos. El PIN ha sido invalidado por seguridad."

        stored_pin = str(data.get("pin", "")).strip()
        if hmac.compare_digest(candidate_pin.strip(), stored_pin):
            try:
                self.pin_file.unlink(missing_ok=True)
            except Exception:
                pass
            master_token = self.get_or_create_pairing_token()
            logger.info("Emparejamiento por PIN exitoso")
            return True, master_token, "✓ Dispositivo emparejado con éxito."

        failed += 1
        data["failed_attempts"] = failed
        remaining = max(0, 5 - failed)
        try:
            with open(self.pin_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

        if remaining == 0:
            try:
                self.pin_file.unlink(missing_ok=True)
            except Exception:
                pass
            return False, None, "PIN incorrecto. Has superado el límite de 5 intentos. Genera uno nuevo en tu ordenador."

        return False, None, f"PIN incorrecto. Te quedan {remaining} intentos."

    @staticmethod
    def is_income_category(cat: Optional[Category]) -> bool:
        """Determina de forma uniforme si una categoría representa ingresos."""
        return is_income_cat_canonical(cat)

    def create_or_get_subcategory(
        self,
        db: Session,
        name: str,
        category_name: Optional[str] = None,
        category_id: Optional[int] = None,
    ) -> Tuple[Subcategory, bool]:
        """
        Crea de forma idempotente una nueva subcategoría o retorna la existente.
        Devuelve (Subcategory, is_new).
        """
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
            target_cat = (
                db.query(Category)
                .filter(func.lower(Category.name).like("%deseo%"))
                .first()
            )
            if not target_cat:
                target_cat = db.query(Category).first()

        if not target_cat:
            raise ValueError("No se puede crear subcategoría porque no existen categorías en la base de datos")

        new_subcat = Subcategory(name=clean_name, category_id=target_cat.id)
        db.add(new_subcat)
        db.commit()
        db.refresh(new_subcat)
        logger.info("Subcategoría creada al vuelo desde el móvil: '%s' (Categoría: %s)", clean_name, target_cat.name)

        try:
            self.export_catalog_file(db)
        except Exception:
            pass

        return new_subcat, True

    def _ensure_directories(self) -> None:
        """Asegura la existencia de la jerarquía de carpetas de sincronización móvil."""
        for d in [self.inbox_dir, self.outbox_dir, self.processed_dir, self.error_dir, self.catalog_dir, self.apk_dir, self.receipts_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def get_mobile_catalog(self, db: Session, local_device_id: Optional[str] = None) -> MobileCatalogResponse:
        """
        Genera el catálogo de categorías, subcategorías y conceptos frecuentes
        para clientes móviles, calculando la frecuencia de uso en los últimos 90 días.
        """
        device_id = local_device_id or get_or_create_device_id()
        now_utc = datetime.now(timezone.utc).isoformat()

        # 1. Recuperar todas las subcategorías con su categoría padre cargada ansiosamente
        subcats = (
            db.query(Subcategory)
            .options(joinedload(Subcategory.category))
            .join(Category)
            .order_by(Category.id, Subcategory.name)
            .all()
        )

        # 2. Análisis de frecuencia de los últimos 90 días delegado a SQL (sin cargar objetos en RAM)
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

        # Fallback si no hay transacciones recientes: marcar subcategorías clave cotidianas
        if not top_subcat_ids:
            common_keywords = {"café", "cafe", "supermercado", "comida", "restaurante", "gasolina", "farmacia", "ocio", "bizum", "nómina", "nomina"}
            for s in subcats:
                if any(kw in s.name.lower() for kw in common_keywords) and len(top_subcat_ids) < 6:
                    top_subcat_ids.add(s.id)

        # Construir lista de subcategorías
        personal_subcategories: List[MobileCatalogSubcategory] = []
        for s in subcats:
            cat_name = s.category.name if s.category else "General"
            cat_type = "income" if self.is_income_category(s.category) else "expense"
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

        # Ordenar: las frecuentes primero, luego alfabéticamente
        personal_subcategories.sort(key=lambda s: (not s.is_frequent, s.category_id, s.name.lower()))

        # Top 15 conceptos más recurrentes calculados en SQL
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
        deleted_ids = self.get_deleted_event_ids()

        # Mapeo rápido de subcategorías existentes por id y por nombre en minúsculas
        all_subcats = db.query(Subcategory).all()
        subcat_by_id = {s.id: s for s in all_subcats}
        subcat_by_name = {s.name.strip().lower(): s for s in all_subcats}

        try:
            for item in request.transactions:
                # 0. Comprobación de tombstone (si fue eliminada por el usuario, no reinsertar)
                if item.event_id and item.event_id in deleted_ids:
                    logger.info("Ignorando transacción móvil %s porque fue eliminada previamente (tombstone)", item.event_id)
                    ignored_duplicates_count += 1
                    continue

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

                # 3. Resolución segura de subcategoría (incluyendo creación al vuelo si viene con ID nuevo/temporal)
                eff_subcat = subcat_by_id.get(candidate_subcat_id) if candidate_subcat_id is not None else None
                if not eff_subcat and item.subcategory_name:
                    eff_subcat = subcat_by_name.get(item.subcategory_name.strip().lower())

                if not eff_subcat and item.subcategory_name:
                    is_income = (getattr(item, "type", None) or "").upper() == "INCOME"
                    fallback_cat = "Ingresos Netos" if is_income else "Deseos (30%)"
                    eff_subcat, _ = self.create_or_get_subcategory(
                        db, item.subcategory_name, category_name=fallback_cat
                    )
                    subcat_by_id[eff_subcat.id] = eff_subcat
                    subcat_by_name[eff_subcat.name.strip().lower()] = eff_subcat

                if not eff_subcat:
                    # Fallback defensivo a la primera subcategoría disponible
                    eff_subcat = all_subcats[0] if all_subcats else None
                    if not eff_subcat:
                        logger.error("No existen subcategorías en la base de datos para asignar el gasto móvil")
                        continue

                # 4. Procesamiento de comprobante de ticket si existe (Base64 o nombre previo)
                saved_receipt_filename = None
                if getattr(item, "receipt_base64", None):
                    saved_receipt_filename = self.save_receipt_base64(item.event_id, item.receipt_base64)
                elif getattr(item, "receipt_filename", None):
                    saved_receipt_filename = item.receipt_filename

                # 5. Inserción de la transacción
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

    def get_sync_status(self, db: Session, authenticated: bool = False) -> MobileSyncStatusResponse:
        """Obtiene el estado de salud y métricas de sincronización móvil sin filtrar el token secreto (SEC-01)."""
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
            pairing_token=None,
            authenticated=authenticated,
        )

    def get_mobile_monthly_summary(
        self, db: Session, month_key: Optional[str] = None, month: Optional[str] = None
    ) -> MobileMonthlySummaryResponse:
        """
        Calcula el resumen de ejecución presupuestaria del mes (50/30/20) y fondo de seguridad
        para la vista táctil 'Mi Mes'.
        """
        current_m = month_key or month or date.today().strftime("%Y-%m")

        categories = db.query(Category).order_by(Category.id).all()

        effective_budgets = get_effective_monthly_budgets(db, current_m)
        effective_map = {b.subcategory_id: float(b.amount or 0.0) for b in effective_budgets}

        year_str, month_str = current_m.split("-")
        y = int(year_str)
        m = int(month_str)
        start_d = date(y, m, 1)
        if m == 12:
            end_d = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            end_d = date(y, m + 1, 1) - timedelta(days=1)

        txs = (
            db.query(Transaction)
            .filter(Transaction.date.between(start_d, end_d))
            .all()
        )

        spent_by_subcat: Dict[int, float] = defaultdict(float)
        income_total = 0.0
        subcat_to_cat = {}
        for s in db.query(Subcategory).join(Category).all():
            subcat_to_cat[s.id] = s.category

        unassigned_spent = 0.0
        for t in txs:
            if not t.amount:
                continue
            amt = float(t.amount)
            cat = subcat_to_cat.get(t.subcategory_id)
            if self.is_income_category(cat):
                income_total += amt
            elif t.subcategory_id:
                spent_by_subcat[t.subcategory_id] += amt
            else:
                unassigned_spent += amt

        subcats = db.query(Subcategory).all()
        cat_budgeted: Dict[int, float] = defaultdict(float)
        cat_spent: Dict[int, float] = defaultdict(float)
        subcat_summary_list: List[Dict[str, Any]] = []

        if unassigned_spent > 0:
            subcat_summary_list.append({
                "subcategory_id": -1,
                "subcategory_name": "Sin Subcategoría",
                "category_name": "General",
                "spent": round(unassigned_spent, 2),
                "budget": 0.0,
            })

        income_budgeted = 0.0
        for s in subcats:
            cat = subcat_to_cat.get(s.id)
            amt_budgeted = float(effective_map.get(s.id, 0.0))
            amt_spent = float(spent_by_subcat.get(s.id, 0.0))
            if self.is_income_category(cat):
                income_budgeted += amt_budgeted
                continue
            cat_id = s.category_id
            subcat_real = amt_budgeted + amt_spent
            cat_budgeted[cat_id] += amt_budgeted
            cat_spent[cat_id] += subcat_real
            subcat_summary_list.append({
                "subcategory_id": s.id,
                "subcategory_name": s.name,
                "category_name": cat.name if cat else "General",
                "spent": round(subcat_real, 2),
                "budget": round(amt_budgeted, 2),
            })

        total_income_real = round(income_budgeted + income_total, 2)

        has_income_category = any(self.is_income_category(c) for c in categories)
        if has_income_category:
            rule_target_needs, rule_target_wants, rule_target_savings = calculate_503020_targets(
                total_income_real
            )
        else:
            rule_target_needs = None
            rule_target_wants = None
            rule_target_savings = None

        categories_summary: List[MobileCategorySummary] = []
        total_b = 0.0
        total_s = 0.0

        needs_summary = None
        wants_summary = None
        savings_summary = None

        for cat in categories:
            if self.is_income_category(cat):
                continue
            b_amt = round(float(cat_budgeted[cat.id]), 2)
            s_amt = round(float(cat_spent[cat.id]), 2)
            block = classify_category_block(cat)

            rule_pct = 0.0
            rule_budget = b_amt
            if block == CategoryBlock.NEEDS:
                rule_pct = 50.0
                if rule_target_needs is not None:
                    rule_budget = rule_target_needs
            elif block == CategoryBlock.WANTS:
                rule_pct = 30.0
                if rule_target_wants is not None:
                    rule_budget = rule_target_wants
            elif block == CategoryBlock.SAVINGS:
                rule_pct = 20.0
                if rule_target_savings is not None:
                    rule_budget = rule_target_savings

            r_amt = round(rule_budget - s_amt, 2)
            prog = round((s_amt / rule_budget * 100) if rule_budget > 0 else (100.0 if s_amt > 0 else 0.0), 1)

            cat_sum = MobileCategorySummary(
                category_id=cat.id,
                category_name=cat.name,
                budgeted_amount=b_amt,
                spent_amount=s_amt,
                remaining_amount=r_amt,
                rule_percentage=rule_pct,
                spent=s_amt,
                budget=rule_budget,
                remaining=r_amt,
                progress_percentage=prog,
            )
            total_b += b_amt
            total_s += s_amt
            categories_summary.append(cat_sum)

            if rule_pct == 50.0:
                needs_summary = cat_sum
            elif rule_pct == 30.0:
                wants_summary = cat_sum
            elif rule_pct == 20.0:
                savings_summary = cat_sum

        # Fallbacks si no existen categorías específicas
        if not needs_summary:
            needs_summary = MobileCategorySummary(
                category_id=0,
                category_name="Necesidades Básicas (50%)",
                budgeted_amount=0,
                spent_amount=0,
                remaining_amount=0,
                rule_percentage=50.0,
                budget=rule_target_needs if rule_target_needs is not None else 0.0,
            )
        if not wants_summary:
            wants_summary = MobileCategorySummary(
                category_id=0,
                category_name="Deseos (30%)",
                budgeted_amount=0,
                spent_amount=0,
                remaining_amount=0,
                rule_percentage=30.0,
                budget=rule_target_wants if rule_target_wants is not None else 0.0,
            )
        if not savings_summary:
            savings_summary = MobileCategorySummary(
                category_id=0,
                category_name="Ahorro e Inversión (20%)",
                budgeted_amount=0,
                spent_amount=0,
                remaining_amount=0,
                rule_percentage=20.0,
                budget=rule_target_savings if rule_target_savings is not None else 0.0,
            )

        if unassigned_spent > 0:
            total_s += unassigned_spent
            if wants_summary:
                wants_summary.spent_amount = round(wants_summary.spent_amount + unassigned_spent, 2)
                wants_summary.spent = wants_summary.spent_amount
                wants_summary.remaining_amount = round(wants_summary.budget - wants_summary.spent_amount, 2)
                wants_summary.remaining = wants_summary.remaining_amount
                wants_summary.progress_percentage = round(
                    (wants_summary.spent / wants_summary.budget * 100) if wants_summary.budget > 0 else (100.0 if wants_summary.spent > 0 else 0.0), 1
                )

        total_remaining = round(total_income_real - total_s, 2)
        remaining_budget = total_remaining

        ef = db.query(EmergencyFund).first()
        ef_obj = ef if ef else EmergencyFund(current_balance=0.0, target_months=3, target_amount=0.0)
        monthly_needs = resolve_monthly_needs(db, current_m)
        if monthly_needs <= 0 and not (ef_obj.target_amount and ef_obj.target_amount > 0):
            monthly_needs = 1000.0
        safety = evaluate_safety_status(ef_obj, monthly_needs)

        ef_balance = safety.current_balance
        ef_target_months = safety.target_months
        months_covered = safety.coverage_months
        ef_target_amount = safety.target_amount

        from backend.domain.schemas.mobile import MobileEmergencyFundSummary
        emergency_fund_obj = MobileEmergencyFundSummary(
            current_amount=ef_balance,
            target_amount=ef_target_amount,
            months_covered=months_covered,
            is_funded=safety.is_completed,
        )

        return MobileMonthlySummaryResponse(
            month=current_m,
            total_budgeted=round(total_b, 2),
            total_spent=round(total_s, 2),
            total_remaining=total_remaining,
            total_income=total_income_real,
            remaining_budget=remaining_budget,
            categories=categories_summary,
            emergency_fund_balance=round(ef_balance, 2),
            emergency_fund_target_months=ef_target_months,
            emergency_fund_months_covered=months_covered,
            emergency_fund=emergency_fund_obj,
            needs=needs_summary,
            wants=wants_summary,
            savings=savings_summary,
            subcategories=subcat_summary_list,
        )

    def update_mobile_budget(
        self,
        db: Session,
        update: Any,
        amount: Optional[float] = None,
        month: Optional[str] = None,
    ) -> bool:
        """Actualiza o inserta la asignación presupuestaria de una subcategoría para un mes."""
        from backend.domain.schemas.mobile import MobileBudgetUpdate
        if isinstance(update, MobileBudgetUpdate):
            target_subcat_id = update.subcategory_id
            target_amount = update.amount
            target_month = update.month or datetime.now().strftime("%Y-%m")
        elif isinstance(update, dict):
            target_subcat_id = update.get("subcategory_id", 0)
            target_amount = float(update.get("amount") or update.get("allocated_amount") or 0.0)
            target_month = update.get("month") or datetime.now().strftime("%Y-%m")
        else:
            target_subcat_id = int(update)
            target_amount = float(amount or 0.0)
            target_month = month or datetime.now().strftime("%Y-%m")

        budget_entry = (
            db.query(MonthlyBudget)
            .filter(
                MonthlyBudget.month == target_month,
                MonthlyBudget.subcategory_id == target_subcat_id,
            )
            .first()
        )
        if budget_entry:
            budget_entry.amount = target_amount
        else:
            budget_entry = MonthlyBudget(
                month=target_month,
                subcategory_id=target_subcat_id,
                amount=target_amount,
            )
            db.add(budget_entry)
        db.commit()
        logger.info("Presupuesto móvil actualizado: mes %s, subcat %d, cantidad %.2f", target_month, target_subcat_id, target_amount)
        return True

    def get_mobile_version_info(self) -> Any:
        """Retorna la versión más reciente publicada de la APK móvil para actualizaciones OTA."""
        from backend.domain.schemas.mobile import MobileVersionResponse
        version_file = self.apk_dir / "version.json"
        code = 1
        name = "1.0.0"
        notes = "Versión inicial estable Quick-Capture"
        released_utc = None
        apk_filename = None

        if version_file.exists():
            try:
                with open(version_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    code = int(data.get("version_code", 1))
                    name = str(data.get("version_name", "1.0.0"))
                    notes = data.get("release_notes", notes)
                    released_utc = data.get("released_at_utc")
                    apk_filename = data.get("apk_filename")
            except Exception as e:
                logger.warning("Error leyendo version.json: %s", e)

        # Buscar APK en el directorio
        apk_path = self.get_latest_apk_path(apk_filename)
        apk_available = apk_path is not None and apk_path.exists()
        apk_size = apk_path.stat().st_size if apk_available and apk_path else None
        final_filename = apk_path.name if apk_available and apk_path else None

        return MobileVersionResponse(
            version_code=code,
            version_name=name,
            apk_available=apk_available,
            apk_url="/api/mobile/download-apk" if apk_available else None,
            apk_filename=final_filename,
            apk_size_bytes=apk_size,
            release_notes=notes,
            released_at_utc=released_utc,
        )

    def get_latest_apk_path(self, preferred_filename: Optional[str] = None) -> Optional[Path]:
        """Obtiene la ruta al archivo APK disponible para distribución."""
        if preferred_filename:
            candidate = self.apk_dir / preferred_filename
            if candidate.exists():
                return candidate

        # Buscar cualquier archivo .apk en self.apk_dir ordenado por fecha de modificación
        apks = sorted(self.apk_dir.glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True)
        return apks[0] if apks else None

    def publish_apk_release(
        self,
        apk_bytes: bytes,
        filename: str = "app-release.apk",
        version_code: int = 2,
        version_name: str = "1.1.0",
        release_notes: str = "",
    ) -> Any:
        """Guarda un nuevo binario APK en disco y actualiza su metadata para actualizaciones OTA."""
        safe_filename = Path(filename).name
        target_apk = self.apk_dir / safe_filename
        with open(target_apk, "wb") as f:
            f.write(apk_bytes)

        released_utc = datetime.now(timezone.utc).isoformat()
        metadata = {
            "version_code": version_code,
            "version_name": version_name,
            "release_notes": release_notes or f"Actualización versión {version_name}",
            "apk_filename": safe_filename,
            "released_at_utc": released_utc,
        }
        version_file = self.apk_dir / "version.json"
        with open(version_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info("Nueva versión de APK móvil publicada: %s (v%s, código %d)", safe_filename, version_name, version_code)
        return self.get_mobile_version_info()

    def delete_mobile_transaction(self, db: Session, identifier: str) -> Optional[int]:
        """
        Elimina de forma segura y atómica una transacción identificada por su ID numérico
        o por su mobile_event_id UUID.
        Reutiliza SQLiteRepository.delete_transaction para garantizar la reversión del Fondo
        de Emergencia y la integridad referencial.
        Retorna el ID de la transacción eliminada, o None si no fue encontrada.
        """
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
                self.record_deleted_event_id(tx_mob_id)
            if receipt_to_delete:
                self.delete_receipt_file(receipt_to_delete)
            logger.info("Transacción móvil eliminada con éxito (ID: %s, event_id: %s)", tx_id, tx.mobile_event_id)
            return tx_id
        return None

    def search_transactions(
        self, db: Session, query_text: str, limit: int = 50
    ) -> MobileSearchResponse:
        """
        Buscador instantáneo de transacciones históricas en SQLite.
        Filtra por coincidencia case-insensitive en descripción o nombre de subcategoría.
        """
        clean_q = (query_text or "").strip()
        if not clean_q:
            return MobileSearchResponse(query="", total_found=0, items=[])

        search_filter = f"%{clean_q}%"
        query = (
            db.query(Transaction)
            .options(joinedload(Transaction.subcategory).joinedload(Subcategory.category))
            .join(Subcategory, Transaction.subcategory_id == Subcategory.id)
            .join(Category, Subcategory.category_id == Category.id)
            .filter(
                (Transaction.description.ilike(search_filter))
                | (Subcategory.name.ilike(search_filter))
            )
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(max(1, min(limit, 200)))
        )

        results = query.all()
        items = []
        for tx in results:
            sub = tx.subcategory
            cat_name = sub.category.name if sub and sub.category else "Sin Categoría"
            r_fn = getattr(tx, "receipt_filename", None)
            tx_type = "INCOME" if self.is_income_category(sub.category if sub else None) else "EXPENSE"
            items.append(
                MobileHistoricalTransactionItem(
                    id=tx.id,
                    date=str(tx.date),
                    amount=float(tx.amount),
                    description=tx.description or "",
                    type=tx_type,
                    subcategory_id=tx.subcategory_id,
                    subcategory_name=sub.name if sub else "",
                    category_name=cat_name,
                    receipt_filename=r_fn,
                    receipt_url=f"/api/mobile/receipts/{r_fn}" if r_fn else None,
                    mobile_event_id=getattr(tx, "mobile_event_id", None),
                )
            )

        return MobileSearchResponse(
            query=clean_q,
            total_found=len(items),
            items=items,
        )

    def get_historical_cache(
        self, db: Session, months: int = 12
    ) -> List[MobileHistoricalTransactionItem]:
        """
        Exporta las transacciones de los últimos N meses para almacenamiento en caché local del teléfono.
        """
        cutoff_date = date.today() - timedelta(days=months * 31)
        query = (
            db.query(Transaction)
            .options(joinedload(Transaction.subcategory).joinedload(Subcategory.category))
            .join(Subcategory, Transaction.subcategory_id == Subcategory.id)
            .join(Category, Subcategory.category_id == Category.id)
            .filter(Transaction.date >= cutoff_date)
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(1000)
        )

        results = query.all()
        items = []
        for tx in results:
            sub = tx.subcategory
            cat_name = sub.category.name if sub and sub.category else "Sin Categoría"
            r_fn = getattr(tx, "receipt_filename", None)
            tx_type = "INCOME" if self.is_income_category(sub.category if sub else None) else "EXPENSE"
            items.append(
                MobileHistoricalTransactionItem(
                    id=tx.id,
                    date=str(tx.date),
                    amount=float(tx.amount),
                    description=tx.description or "",
                    type=tx_type,
                    subcategory_id=tx.subcategory_id,
                    subcategory_name=sub.name if sub else "",
                    category_name=cat_name,
                    receipt_filename=r_fn,
                    receipt_url=f"/api/mobile/receipts/{r_fn}" if r_fn else None,
                    mobile_event_id=getattr(tx, "mobile_event_id", None),
                )
            )
        return items

    def save_receipt_base64(self, event_id: str, base64_str: str) -> Optional[str]:
        """
        Decodifica y guarda de forma segura una imagen de ticket en sync/mobile/receipts/.
        Devuelve el nombre del archivo guardado o None si ocurre un error.
        """
        if not base64_str or not event_id:
            return None
        try:
            data_str = base64_str
            if "," in data_str:
                data_str = data_str.split(",", 1)[1]
            raw_bytes = base64.b64decode(data_str)
            safe_id = "".join(c for c in event_id if c.isalnum() or c in ("-", "_"))
            filename = f"receipt_{safe_id}.jpg"
            target_path = self.receipts_dir / filename
            target_path.write_bytes(raw_bytes)
            logger.info("Comprobante de ticket guardado en disco: %s (%d bytes)", filename, len(raw_bytes))
            return filename
        except Exception as exc:
            logger.error("Error guardando comprobante base64 para %s: %s", event_id, exc)
            return None

    def save_receipt_file(self, event_id: str, file_bytes: bytes) -> Optional[str]:
        """Guarda un archivo de imagen recibido vía multipart en sync/mobile/receipts/."""
        if not file_bytes or not event_id:
            return None
        try:
            safe_id = "".join(c for c in event_id if c.isalnum() or c in ("-", "_"))
            filename = f"receipt_{safe_id}.jpg"
            target_path = self.receipts_dir / filename
            target_path.write_bytes(file_bytes)
            logger.info("Comprobante de ticket subido guardado en disco: %s (%d bytes)", filename, len(file_bytes))
            return filename
        except Exception as exc:
            logger.error("Error guardando archivo de ticket para %s: %s", event_id, exc)
            return None

    def get_receipt_path(self, filename: str) -> Optional[Path]:
        """Retorna la ruta física del comprobante si existe y está dentro de receipts_dir."""
        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            return None
        target = self.receipts_dir / filename
        if target.exists() and target.is_file():
            return target
        return None

    def delete_receipt_file(self, filename: Optional[str]) -> bool:
        """Elimina físicamente el archivo de comprobante de la carpeta receipts si existe."""
        if not filename:
            return False
        path = self.get_receipt_path(filename)
        if path and path.is_file():
            try:
                path.unlink(missing_ok=True)
                logger.info("Comprobante físico eliminado del disco: %s", filename)
                return True
            except Exception as exc:
                logger.warning("No se pudo eliminar el comprobante físico %s: %s", filename, exc)
        return False



