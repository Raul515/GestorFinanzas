"""
Servicio de Sincronización Móvil Quick-Capture (Spec 016).
Gestiona la generación del catálogo para clientes móviles, la ingesta atómica
idempotente de transacciones personales y el procesamiento complementario
de buzones de sincronización física en disco.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

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
        self.apk_dir = self.mobile_dir / "apk"
        self.pairing_file = self.mobile_dir / "pairing_secret.txt"

        self._ensure_directories()

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
        for d in [self.inbox_dir, self.outbox_dir, self.processed_dir, self.error_dir, self.catalog_dir, self.apk_dir]:
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

                # 3. Resolución segura de subcategoría (incluyendo creación al vuelo si viene con ID nuevo/temporal)
                eff_subcat = subcat_by_id.get(candidate_subcat_id) if candidate_subcat_id is not None else None
                if not eff_subcat and item.subcategory_name:
                    eff_subcat = subcat_by_name.get(item.subcategory_name.strip().lower())

                if not eff_subcat and item.subcategory_name:
                    eff_subcat, _ = self.create_or_get_subcategory(
                        db, item.subcategory_name, category_name="Deseos (30%)"
                    )
                    subcat_by_id[eff_subcat.id] = eff_subcat
                    subcat_by_name[eff_subcat.name.strip().lower()] = eff_subcat

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

        pairing_tok = self.get_or_create_pairing_token()
        return MobileSyncStatusResponse(
            server_online=True,
            server_time_utc=datetime.now(timezone.utc).isoformat(),
            today_transactions_count=int(today_count),
            pending_inbox_files=pending_files,
            pairing_token=pairing_tok,
            authenticated=True,
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

        budgets_month = db.query(MonthlyBudget).filter(MonthlyBudget.month == current_m).all()
        base_budgets = db.query(MonthlyBudget).filter(MonthlyBudget.month == "BASE").all()
        base_map = {b.subcategory_id: b.amount for b in base_budgets}
        month_map = {b.subcategory_id: b.amount for b in budgets_month}

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

        for t in txs:
            if not t.amount:
                continue
            amt = float(t.amount)
            cat = subcat_to_cat.get(t.subcategory_id)
            if cat and getattr(cat, "type", "").lower() == "income":
                income_total += amt
            elif t.subcategory_id:
                spent_by_subcat[t.subcategory_id] += amt

        subcats = db.query(Subcategory).all()
        cat_budgeted: Dict[int, float] = defaultdict(float)
        cat_spent: Dict[int, float] = defaultdict(float)
        subcat_summary_list: List[Dict[str, Any]] = []

        for s in subcats:
            cat = subcat_to_cat.get(s.id)
            if cat and getattr(cat, "type", "").lower() == "income":
                continue
            cat_id = s.category_id
            amt_budgeted = float(month_map.get(s.id, base_map.get(s.id, 0.0)))
            amt_spent = float(spent_by_subcat.get(s.id, 0.0))
            cat_budgeted[cat_id] += amt_budgeted
            cat_spent[cat_id] += amt_spent
            subcat_summary_list.append({
                "subcategory_id": s.id,
                "subcategory_name": s.name,
                "category_name": cat.name if cat else "General",
                "spent": round(amt_spent, 2),
                "budget": round(amt_budgeted, 2),
            })

        categories_summary: List[MobileCategorySummary] = []
        total_b = 0.0
        total_s = 0.0

        needs_summary = None
        wants_summary = None
        savings_summary = None

        for cat in categories:
            if getattr(cat, "type", "").lower() == "income":
                continue
            b_amt = round(float(cat_budgeted[cat.id]), 2)
            s_amt = round(float(cat_spent[cat.id]), 2)
            r_amt = round(b_amt - s_amt, 2)
            prog = round((s_amt / b_amt * 100) if b_amt > 0 else (100.0 if s_amt > 0 else 0.0), 1)

            cat_sum = MobileCategorySummary(
                category_id=cat.id,
                category_name=cat.name,
                budgeted_amount=b_amt,
                spent_amount=s_amt,
                remaining_amount=r_amt,
                spent=s_amt,
                budget=b_amt,
                remaining=r_amt,
                progress_percentage=prog,
            )
            total_b += b_amt
            total_s += s_amt
            categories_summary.append(cat_sum)

            c_low = cat.name.lower()
            if "necesidad" in c_low or "50%" in c_low:
                cat_sum.rule_percentage = 50.0
                needs_summary = cat_sum
            elif "deseo" in c_low or "30%" in c_low:
                cat_sum.rule_percentage = 30.0
                wants_summary = cat_sum
            elif "ahorro" in c_low or "20%" in c_low or "invers" in c_low:
                cat_sum.rule_percentage = 20.0
                savings_summary = cat_sum

        # Fallbacks si no existen categorías específicas
        if not needs_summary:
            needs_summary = MobileCategorySummary(category_id=0, category_name="Necesidades Básicas (50%)", budgeted_amount=0, spent_amount=0, remaining_amount=0, rule_percentage=50.0)
        if not wants_summary:
            wants_summary = MobileCategorySummary(category_id=0, category_name="Deseos (30%)", budgeted_amount=0, spent_amount=0, remaining_amount=0, rule_percentage=30.0)
        if not savings_summary:
            savings_summary = MobileCategorySummary(category_id=0, category_name="Ahorro e Inversión (20%)", budgeted_amount=0, spent_amount=0, remaining_amount=0, rule_percentage=20.0)

        ef = db.query(EmergencyFund).first()
        ef_balance = float(ef.current_balance) if ef else 0.0
        ef_target_months = ef.target_months if ef else 3

        necesidades_cat = next((c for c in categories if "necesidad" in c.name.lower() or "50%" in c.name.lower()), None)
        necesidades_mensual = float(cat_budgeted[necesidades_cat.id]) if necesidades_cat else 0.0
        if necesidades_mensual <= 0:
            necesidades_mensual = 1000.0
        months_covered = round(ef_balance / necesidades_mensual, 1)
        ef_target_amount = round(necesidades_mensual * ef_target_months, 2)

        from backend.domain.schemas.mobile import MobileEmergencyFundSummary
        emergency_fund_obj = MobileEmergencyFundSummary(
            current_amount=round(ef_balance, 2),
            target_amount=ef_target_amount,
            months_covered=months_covered,
            is_funded=(months_covered >= 3.0),
        )

        return MobileMonthlySummaryResponse(
            month=current_m,
            total_budgeted=round(total_b, 2),
            total_spent=round(total_s, 2),
            total_remaining=round(total_b - total_s, 2),
            total_income=round(income_total, 2),
            remaining_budget=round(income_total - total_s if income_total > 0 else (total_b - total_s), 2),
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
