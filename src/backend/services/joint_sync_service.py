"""
Motor de Sincronización Asíncrona Desacoplada (Event Sourcing Inbox/Outbox para Syncthing) (Spec 010).
Opera mediante lectura y escritura exclusiva de ficheros JSON atómicos en disco local (sync/),
garantizando resiliencia ante desconexiones, idempotencia por UUIDv4 y resolución determinista LWW.
"""

from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
import platform
import shutil
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.domain.models.joint import (
    JointAccount,
    JointAppliedSyncEvent,
    JointCategory,
    JointMonthlyContribution,
    JointSinkingFund,
    JointSubcategory,
    JointTransaction,
    JointSinkingFundTransfer,
)
from backend.domain.schemas.joint import (
    ProfileIdentifier,
    SyncAction,
    SyncEntityType,
    SyncEventPayload,
)

logger = logging.getLogger(__name__)


def get_or_create_device_id(data_dir: Optional[Path] = None) -> str:
    """
    Obtiene o genera de forma persistente un identificador único de dispositivo.
    Prioridad:
    1. Variable de entorno DEVICE_ID (si está definida y no vacía).
    2. Archivo device_id.txt en el directorio data/ (persiste en disco/volumen Docker).
    3. Generación automática y almacenamiento persistente (nombre de host + uuid parcial).
    """
    env_id = os.environ.get("DEVICE_ID")
    if env_id and env_id.strip():
        return env_id.strip()

    if data_dir is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"

    data_dir.mkdir(parents=True, exist_ok=True)
    device_id_file = data_dir / "device_id.txt"
    if device_id_file.exists():
        try:
            stored_id = device_id_file.read_text(encoding="utf-8").strip()
            if stored_id:
                return stored_id
        except Exception as exc:
            logger.warning("No se pudo leer device_id.txt: %s", exc)

    node_name = platform.node() or "device"
    clean_node = "".join(c for c in node_name if c.isalnum() or c in ("-", "_"))[:12] or "device"
    new_id = f"{clean_node}_{uuid.uuid4().hex[:8]}"
    try:
        device_id_file.write_text(new_id, encoding="utf-8")
    except Exception as exc:
        logger.warning("No se pudo persistir device_id.txt en disco: %s", exc)
    return new_id


class JointSyncService:
    """Servicio de gestión de buzones de sincronización y resolución de conflictos LWW."""

    def __init__(self, base_sync_dir: Optional[str] = None, local_device_id: Optional[str] = None):
        env_sync_dir = os.environ.get("BASE_SYNC_DIR")
        if base_sync_dir:
            self.base_dir = Path(base_sync_dir)
        elif env_sync_dir and env_sync_dir.strip():
            self.base_dir = Path(env_sync_dir.strip())
        else:
            # Por defecto: directorio 'sync' en la raíz del proyecto
            root_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.base_dir = root_dir / "sync"

        self.outbox_dir = self.base_dir / "outbox"
        self.inbox_dir = self.base_dir / "inbox"
        self.processed_dir = self.base_dir / "processed"
        self.error_dir = self.base_dir / "error"
        self.local_device_id = local_device_id or get_or_create_device_id()

        # Asegurar creación de la jerarquía de carpetas
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Crea las carpetas de sincronización locales si no existen."""
        for d in [self.outbox_dir, self.inbox_dir, self.processed_dir, self.error_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def emit_event(
        self,
        entity_type: SyncEntityType,
        action: SyncAction,
        payload: Dict[str, Any],
        origin_device_id: Optional[str] = None,
        event_id: Optional[str] = None,
        timestamp_utc: Optional[str] = None,
    ) -> SyncEventPayload:
        """
        Genera y deposita de forma atómica un fichero JSON delta en sync/outbox/.
        Utiliza escritura temporal y renombramiento atómico para evitar que Syncthing lea archivos parciales.
        """
        eff_event_id = event_id or str(uuid.uuid4())
        eff_timestamp = timestamp_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        eff_device_id = origin_device_id or self.local_device_id

        event_payload = SyncEventPayload(
            event_id=eff_event_id,
            entity_type=entity_type,
            action=action,
            origin_device_id=eff_device_id,
            timestamp_utc=eff_timestamp,
            payload=payload,
        )

        filename = f"evt_{eff_event_id}.json"
        tmp_path = self.outbox_dir / f"{filename}.tmp"
        final_path = self.outbox_dir / filename

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(event_payload.model_dump(), f, indent=2, ensure_ascii=False)
            # Renombrado atómico en el mismo sistema de ficheros
            os.replace(tmp_path, final_path)
            logger.info("Evento delta emitido con éxito a outbox: %s", final_path.name)
            self.rotate_outbox()
        except Exception as exc:
            logger.error("Error emitiendo evento delta a outbox (%s): %s", eff_event_id, exc)
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

        return event_payload

    @staticmethod
    def _is_sync_file(file_path: Path, require_json: bool = True) -> bool:
        """
        Determina si un archivo es un artefacto de sincronización válido:
        - Debe ser un archivo regular (no directorio ni enlace roto).
        - No debe ser un archivo oculto ni de sistema (empieza por '.').
        - No debe ser .gitkeep ni un archivo temporal (.tmp).
        - Opcionalmente requiere extensión .json.
        """
        if not file_path.is_file():
            return False
        name = file_path.name
        if name.startswith(".") or name == ".gitkeep" or name.endswith(".tmp"):
            return False
        if require_json and file_path.suffix.lower() != ".json":
            return False
        return True

    def rotate_outbox(self, max_files: int = 50) -> None:
        """
        Mantiene un límite máximo de archivos en sync/outbox/ eliminando los más
        antiguos para evitar saturación indefinida del disco.
        """
        try:
            outbox_files = [
                f for f in self.outbox_dir.iterdir()
                if self._is_sync_file(f, require_json=True)
            ]
            if len(outbox_files) > max_files:
                outbox_files.sort(key=lambda f: f.stat().st_mtime)
                excess = len(outbox_files) - max_files
                for old_f in outbox_files[:excess]:
                    try:
                        old_f.unlink()
                    except OSError:
                        pass
        except Exception as exc:
            logger.warning("Error en rotación de outbox: %s", exc)

    _rotate_outbox = rotate_outbox

    def process_inbox(self, db: Session) -> Dict[str, Any]:
        """
        Escanea la bandeja sync/inbox/, ordena los eventos por timestamp_utc, aplica
        los cambios en SQLite de forma idempotente con resolución LWW y archiva los procesados.
        """
        inbox_files = [
            f for f in self.inbox_dir.iterdir()
            if self._is_sync_file(f, require_json=True)
        ]

        if not inbox_files:
            return {"processed_count": 0, "skipped_count": 0, "error_count": 0, "errors": []}

        parsed_events: List[tuple[SyncEventPayload, Path]] = []
        error_count = 0
        errors: List[str] = []

        # 1. Parsear y validar contratos Pydantic
        for file_path in inbox_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                event = SyncEventPayload.model_validate(data)
                parsed_events.append((event, file_path))
            except Exception as exc:
                error_count += 1
                err_msg = f"Fichero inválido en inbox ({file_path.name}): {exc}"
                logger.error(err_msg)
                errors.append(err_msg)
                # Mover archivo corrupto a carpeta de error para no bloquear la cola
                dest = self.error_dir / file_path.name
                shutil.move(str(file_path), str(dest))

        # 2. Ordenar cronológicamente por timestamp_utc ascendente
        parsed_events.sort(key=lambda pair: pair[0].timestamp_utc)

        processed_count = 0
        skipped_count = 0

        for event, file_path in parsed_events:
            # Ignorar ecos si el evento fue originado por este mismo dispositivo
            if event.origin_device_id == self.local_device_id:
                logger.debug("Descartando eco de origen local: %s", event.event_id)
                self._archive_file(file_path)
                skipped_count += 1
                continue

            # Comprobar idempotencia en base de datos
            already_applied = (
                db.query(JointAppliedSyncEvent)
                .filter(JointAppliedSyncEvent.event_id == event.event_id)
                .first()
            )
            if already_applied:
                logger.info("Evento %s ya fue aplicado previamente. Descartando silenciosamente.", event.event_id)
                self._archive_file(file_path)
                skipped_count += 1
                continue

            # Comprobar si es un evento ACCOUNT DELETE dirigido a la cuenta local
            if event.entity_type == SyncEntityType.ACCOUNT and event.action == SyncAction.DELETE:
                account = db.query(JointAccount).filter(JointAccount.id == 1).first()
                if account:
                    event_dt = datetime.fromisoformat(event.timestamp_utc.replace("Z", "+00:00"))
                    account_dt = account.created_at
                    if account_dt and account_dt.tzinfo is None:
                        account_dt = account_dt.replace(tzinfo=timezone.utc)
                    if account_dt and event_dt < account_dt:
                        logger.info("Descartando ACCOUNT DELETE obsoleto emitido antes de la creación de la cuenta local.")
                        self._archive_file(file_path)
                        skipped_count += 1
                        continue
                    else:
                        # Evento de borrado válido: retener en inbox para confirmación del usuario en UI
                        logger.info("Evento ACCOUNT DELETE retenido en inbox a la espera de confirmación del usuario.")
                        continue
                else:
                    logger.info("ACCOUNT DELETE recibido pero no existe cuenta conjunta local activa. Archivando.")
                    self._archive_file(file_path)
                    skipped_count += 1
                    continue

            # Aplicar evento según tipo de entidad
            try:
                self._apply_event(db, event)

                # Registrar evento en la tabla de aplicados para idempotencia futura (salvo reset total a Estado Cero)
                if not (event.entity_type == SyncEntityType.ACCOUNT and event.action == SyncAction.DELETE):
                    applied_record = JointAppliedSyncEvent(
                        event_id=event.event_id,
                        entity_type=event.entity_type.value,
                        action=event.action.value,
                    )
                    db.add(applied_record)
                    db.commit()

                self._archive_file(file_path)
                processed_count += 1
                logger.info("Evento %s (%s - %s) aplicado con éxito.", event.event_id, event.entity_type, event.action)
            except Exception as exc:
                db.rollback()
                error_count += 1
                err_msg = f"Fallo al aplicar evento {event.event_id}: {exc}"
                logger.error(err_msg)
                errors.append(err_msg)
                # Mover a error
                dest = self.error_dir / file_path.name
                shutil.move(str(file_path), str(dest))

        return {
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "errors": errors,
        }

    def _apply_event(self, db: Session, event: SyncEventPayload) -> None:
        """Aplica la mutación en SQLite bajo reglas de Last-Write-Wins (LWW)."""
        if event.entity_type == SyncEntityType.TRANSACTION:
            self._apply_transaction_event(db, event)
        elif event.entity_type == SyncEntityType.CONTRIBUTION:
            self._apply_contribution_event(db, event)
        elif event.entity_type == SyncEntityType.SINKING_FUND:
            self._apply_sinking_fund_event(db, event)
        elif event.entity_type == SyncEntityType.ACCOUNT:
            self._apply_account_event(db, event)
        elif event.entity_type == SyncEntityType.SUBCATEGORY:
            self._apply_subcategory_event(db, event)
        elif event.entity_type == SyncEntityType.SINKING_FUND_TRANSFER:
            self._apply_sinking_fund_transfer_event(db, event)
        else:
            logger.warning("Tipo de entidad no manejada en sincronización: %s", event.entity_type)

    def _apply_subcategory_event(self, db: Session, event: SyncEventPayload) -> None:
        """Aplica mutación sobre subcategorías de necesidades comunes sincronizadas."""
        payload = event.payload
        name = payload.get("name")
        if not name:
            logger.warning("Evento SUBCATEGORY ignorado por falta de 'name' en payload.")
            return

        subcat = db.query(JointSubcategory).filter(func.lower(JointSubcategory.name) == name.strip().lower()).first()

        if event.action == SyncAction.DELETE:
            if subcat:
                # VETO DE BORRADO ANTE CONCURRENCIA OFFLINE (SPEC-015 FASE 4)
                # Si en el nodo local existen transacciones vinculadas a esta subcategoría, se VETA el DELETE remoto
                # para evitar violar la integridad referencial y dejar transacciones huérfanas.
                tx_count = db.query(JointTransaction).filter(JointTransaction.joint_subcategory_id == subcat.id).count()
                if tx_count > 0:
                    logger.warning(
                        "VETO DE BORRADO: La subcategoría conjunta '%s' tiene %d transacciones locales. "
                        "Se veta el DELETE remoto y se re-emite UPSERT para mantener la consistencia contable.",
                        name, tx_count
                    )
                    cat_obj = db.query(JointCategory).filter(JointCategory.id == subcat.joint_category_id).first()
                    self.emit_event(
                        entity_type=SyncEntityType.SUBCATEGORY,
                        action=SyncAction.UPSERT,
                        payload={
                            "name": subcat.name,
                            "monthly_budget": subcat.monthly_budget,
                            "category_name": cat_obj.name if cat_obj else None,
                        },
                        origin_device_id=self.local_device_id,
                    )
                    return

                db.delete(subcat)
                logger.info("Subcategoría conjunta '%s' eliminada por evento remoto.", name)
            return

        cat_name = payload.get("category_name")
        target_cat = None
        if cat_name:
            target_cat = db.query(JointCategory).filter(
                JointCategory.joint_account_id == 1, JointCategory.name == cat_name
            ).first()
        if not target_cat:
            target_cat = db.query(JointCategory).filter(JointCategory.joint_account_id == 1).first()

        if not target_cat:
            logger.warning("No se encontró categoría para asociar la subcategoría conjunta: %s", name)
            return

        monthly_budget = float(payload.get("monthly_budget", 0.0))

        if not subcat:
            subcat = JointSubcategory(
                joint_category_id=target_cat.id,
                name=name,
                monthly_budget=monthly_budget,
            )
            db.add(subcat)
            logger.info("Subcategoría conjunta '%s' creada con éxito por evento remoto.", name)
        else:
            if "monthly_budget" in payload:
                subcat.monthly_budget = monthly_budget
            if target_cat and subcat.joint_category_id != target_cat.id:
                subcat.joint_category_id = target_cat.id
            logger.info("Subcategoría conjunta '%s' actualizada por evento remoto.", name)


    def _apply_sinking_fund_transfer_event(self, db: Session, event: SyncEventPayload) -> None:
        """Aplica registro de transferencia entre huchas con idempotencia por UUID."""
        payload = event.payload
        t_uuid = payload.get("uuid")
        if not t_uuid:
            raise ValueError("Payload de transferencia entre huchas sin campo 'uuid'.")

        existing_t = db.query(JointSinkingFundTransfer).filter(JointSinkingFundTransfer.uuid == t_uuid).first()
        if existing_t:
            logger.info("Transferencia entre huchas ya aplicada (UUID %s), omitiendo.", t_uuid)
            return

        source_id = None
        source_name = payload.get("source_fund_name")
        if source_name:
            sf = db.query(JointSinkingFund).filter(JointSinkingFund.joint_account_id == 1, JointSinkingFund.name == source_name).first()
            if sf:
                source_id = sf.id
        if source_id is None and payload.get("source_fund_id"):
            source_id = payload.get("source_fund_id")

        target_id = None
        target_name = payload.get("target_fund_name")
        if target_name:
            tf = db.query(JointSinkingFund).filter(JointSinkingFund.joint_account_id == 1, JointSinkingFund.name == target_name).first()
            if tf:
                target_id = tf.id
        if target_id is None and payload.get("target_fund_id"):
            target_id = payload.get("target_fund_id")

        if not source_id or not target_id:
            logger.warning("No se pudieron resolver las huchas para la transferencia %s.", t_uuid)
            return

        t_date = datetime.strptime(payload["date"], "%Y-%m-%d").date() if isinstance(payload["date"], str) else payload["date"]
        new_transfer = JointSinkingFundTransfer(
            uuid=t_uuid,
            joint_account_id=1,
            source_fund_id=source_id,
            target_fund_id=target_id,
            amount=float(payload["amount"]),
            date=t_date,
            notes=payload.get("notes"),
            created_by_profile=payload.get("created_by_profile", "REMOTE"),
        )
        db.add(new_transfer)

    def _apply_account_event(self, db: Session, event: SyncEventPayload) -> None:
        """Aplica eventos sobre la cuenta del hogar (ej. DELETE para reset remoto a Estado Cero)."""
        if event.action == SyncAction.DELETE:
            account = db.query(JointAccount).filter(JointAccount.id == 1).first()
            if account and account.created_at:
                try:
                    event_dt = datetime.fromisoformat(event.timestamp_utc.replace("Z", "+00:00"))
                    account_dt = account.created_at
                    if account_dt.tzinfo is None:
                        account_dt = account_dt.replace(tzinfo=timezone.utc)
                    if event_dt < account_dt:
                        logger.info(
                            "LWW: Descartando evento ACCOUNT DELETE obsoleto emitido (%s) antes de la creación de la cuenta actual (%s).",
                            event_dt,
                            account_dt,
                        )
                        return
                except Exception as exc:
                    logger.warning("Error comparando timestamps en ACCOUNT DELETE: %s", exc)

            from backend.database.componentes.sqlite_crud import SQLiteRepository
            repo = SQLiteRepository(db)
            repo.reset_joint_account()
            logger.info("Cuenta conjunta reseteada al Estado Cero mediante evento remoto ACCOUNT (DELETE).")
        elif event.action == SyncAction.UPSERT:
            logger.info("Evento ACCOUNT (UPSERT) procesado en inbox.")
            account = db.query(JointAccount).filter(JointAccount.id == 1).first()
            if account:
                payload = event.payload
                fields_to_sync = [
                    "household_name", "cohabitation_stage", "contribution_strategy",
                    "split_mode", "member_a_reference_income", "member_b_reference_income",
                    "member_a_contribution_pct", "member_b_contribution_pct",
                    "member_a_name", "member_b_name", "custom_total_monthly_budget",
                ]
                for field in fields_to_sync:
                    if field in payload and payload[field] is not None:
                        val = payload[field]
                        val_to_set = val.value if hasattr(val, "value") else val
                        setattr(account, field, val_to_set)
                db.flush()

    def _apply_transaction_event(self, db: Session, event: SyncEventPayload) -> None:
        """Aplica mutación sobre transacciones del hogar con resolución determinista LWW por timestamp_utc."""
        payload = event.payload
        tx_uuid = payload.get("uuid")
        if not tx_uuid:
            raise ValueError("Payload de transacción sin campo 'uuid'.")

        existing_tx = db.query(JointTransaction).filter(JointTransaction.uuid == tx_uuid).first()
        event_dt = datetime.fromisoformat(event.timestamp_utc.replace("Z", "+00:00"))

        if event.action == SyncAction.DELETE:
            if existing_tx:
                # Revertir saldo de hucha únicamente por el importe efectivamente descontado
                if existing_tx.joint_sinking_fund_id:
                    fund = db.query(JointSinkingFund).filter(JointSinkingFund.id == existing_tx.joint_sinking_fund_id).first()
                    if fund:
                        deduction_to_restore = getattr(existing_tx, "sinking_fund_deduction", 0.0) or 0.0
                        fund.current_balance = round(float(fund.current_balance) + float(deduction_to_restore), 2)
                db.delete(existing_tx)
            return

        if event.action == SyncAction.UPSERT:
            # Resolver subcategoría con prioridad estricta por nombre para evitar colisión de IDs locales
            subcat_id = None
            subcat_name = payload.get("subcategory_name")
            if subcat_name:
                subcat = db.query(JointSubcategory).filter(func.lower(JointSubcategory.name) == subcat_name.strip().lower()).first()
                if subcat:
                    subcat_id = subcat.id
                else:
                    # RESURRECCIÓN AUTOMÁTICA ANTE CONCURRENCIA OFFLINE (SPEC-015 FASE 4)
                    # Si la subcategoría fue borrada en el nodo local porque creía que estaba vacía,
                    # pero la pareja registró transacciones mientras estaba desconectada, se recrea automáticamente
                    target_cat = db.query(JointCategory).filter(JointCategory.joint_account_id == 1).first()
                    if target_cat:
                        subcat = JointSubcategory(
                            joint_category_id=target_cat.id,
                            name=subcat_name.strip(),
                            monthly_budget=0.0,
                        )
                        db.add(subcat)
                        db.flush()
                        subcat_id = subcat.id
                        logger.info("Resurrección automática: Subcategoría conjunta '%s' recreada para alojar transacción remota.", subcat_name)
            if subcat_id is None and payload.get("joint_subcategory_id"):
                subcat_id = payload.get("joint_subcategory_id")

            # Resolver hucha con prioridad estricta por nombre para evitar colisión de IDs locales
            sinking_id = None
            sinking_name = payload.get("sinking_fund_name")
            if sinking_name:
                fund = db.query(JointSinkingFund).filter(
                    JointSinkingFund.joint_account_id == 1,
                    JointSinkingFund.name == sinking_name,
                ).first()
                if fund:
                    sinking_id = fund.id
            if sinking_id is None and payload.get("joint_sinking_fund_id"):
                sinking_id = payload.get("joint_sinking_fund_id")

            tx_date = datetime.strptime(payload["date"], "%Y-%m-%d").date() if isinstance(payload["date"], str) else payload["date"]
            amount = float(payload["amount"])
            desc = payload["description"]
            profile = payload.get("created_by_profile", "REMOTE")
            paid_by = str(payload.get("paid_by") or "COMMON")
            mech_raw = payload.get("settlement_mechanism")
            settlement_mechanism = str(mech_raw) if mech_raw is not None else None
            settlement_status = str(payload.get("settlement_status") or ("SETTLED" if paid_by == "COMMON" else "PENDING"))
            settled_at_str = payload.get("settled_at")
            settled_at_val = None
            if settled_at_str:
                try:
                    settled_at_val = datetime.fromisoformat(settled_at_str.replace("Z", "+00:00"))
                except Exception as exc:
                    logger.warning("Error parseando settled_at en sync: %s", exc)

            if existing_tx:
                # Resolución LWW: Solo actualizar si el evento es más reciente que updated_at
                existing_updated = existing_tx.updated_at
                if existing_updated and existing_updated.tzinfo is None:
                    existing_updated = existing_updated.replace(tzinfo=timezone.utc)

                if existing_updated and event_dt <= existing_updated:
                    logger.info("LWW: Evento descartado porque el registro local es más reciente (%s vs %s)", event_dt, existing_updated)
                    return

                # Ajustar diferencias de saldo en huchas si cambió el importe
                if existing_tx.joint_sinking_fund_id:
                    old_fund = db.query(JointSinkingFund).filter(JointSinkingFund.id == existing_tx.joint_sinking_fund_id).first()
                    if old_fund:
                        old_deduction = getattr(existing_tx, "sinking_fund_deduction", 0.0) or 0.0
                        old_fund.current_balance = round(float(old_fund.current_balance) + float(old_deduction), 2)

                existing_tx.date = tx_date
                existing_tx.amount = amount
                existing_tx.description = desc
                existing_tx.joint_subcategory_id = subcat_id
                existing_tx.joint_sinking_fund_id = sinking_id
                existing_tx.created_by_profile = profile
                existing_tx.paid_by = paid_by
                existing_tx.settlement_mechanism = settlement_mechanism
                existing_tx.settlement_status = settlement_status
                existing_tx.settled_at = settled_at_val
                existing_tx.updated_at = event_dt

                deducted = 0.0
                if sinking_id:
                    new_fund = db.query(JointSinkingFund).filter(JointSinkingFund.id == sinking_id).first()
                    payload_deduction = payload.get("sinking_fund_deduction")
                    if payload_deduction is not None:
                        deducted = float(payload_deduction)
                    elif new_fund and new_fund.current_balance > 0:
                        deducted = min(float(new_fund.current_balance), float(amount))

                    if new_fund and new_fund.current_balance > 0 and deducted > 0:
                        new_fund.current_balance = round(max(0.0, float(new_fund.current_balance) - deducted), 2)
                existing_tx.sinking_fund_deduction = deducted
            else:
                deducted = 0.0
                if sinking_id:
                    fund = db.query(JointSinkingFund).filter(JointSinkingFund.id == sinking_id).first()
                    payload_deduction = payload.get("sinking_fund_deduction")
                    if payload_deduction is not None:
                        deducted = float(payload_deduction)
                    elif fund and fund.current_balance > 0:
                        deducted = min(float(fund.current_balance), float(amount))

                    if fund and fund.current_balance > 0 and deducted > 0:
                        fund.current_balance = round(max(0.0, float(fund.current_balance) - deducted), 2)

                new_tx = JointTransaction(
                    uuid=tx_uuid,
                    joint_account_id=1,
                    date=tx_date,
                    amount=amount,
                    description=desc,
                    joint_subcategory_id=subcat_id,
                    joint_sinking_fund_id=sinking_id,
                    sinking_fund_deduction=deducted,
                    created_by_profile=profile,
                    paid_by=paid_by,
                    settlement_mechanism=settlement_mechanism,
                    settlement_status=settlement_status,
                    settled_at=settled_at_val,
                    created_at=event_dt,
                    updated_at=event_dt,
                )
                db.add(new_tx)

    def _apply_contribution_event(self, db: Session, event: SyncEventPayload) -> None:
        """Aplica aportación mensual sincronizada con resolución por UUID único."""
        payload = event.payload
        month = payload.get("month")
        profile = payload.get("contributor_profile")
        amount = float(payload.get("amount", 0.0))
        c_uuid = payload.get("uuid")

        existing_c = None
        if c_uuid:
            existing_c = (
                db.query(JointMonthlyContribution)
                .filter(
                    JointMonthlyContribution.joint_account_id == 1,
                    JointMonthlyContribution.uuid == c_uuid,
                )
                .first()
            )
        elif month and profile:
            # Fallback por compatibilidad con deltas legacy sin UUID
            existing_c = (
                db.query(JointMonthlyContribution)
                .filter(
                    JointMonthlyContribution.joint_account_id == 1,
                    JointMonthlyContribution.month == month,
                    JointMonthlyContribution.contributor_profile == profile,
                )
                .first()
            )

        if event.action == SyncAction.DELETE:
            if existing_c:
                db.delete(existing_c)
            return

        raw_date = payload.get("contribution_date")
        if isinstance(raw_date, str):
            c_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        elif raw_date:
            c_date = raw_date
        else:
            c_date = date.today()

        if existing_c:
            existing_c.amount = amount
            existing_c.contribution_date = c_date
            if c_uuid:
                existing_c.uuid = c_uuid
        else:
            new_c = JointMonthlyContribution(
                uuid=c_uuid or str(uuid.uuid4()),
                joint_account_id=1,
                month=month,
                contributor_profile=profile,
                amount=amount,
                contribution_date=c_date,
            )
            db.add(new_c)

    def _apply_sinking_fund_event(self, db: Session, event: SyncEventPayload) -> None:
        """Aplica mutación sobre huchas de amortización sincronizadas."""
        payload = event.payload
        name = payload["name"]
        fund = db.query(JointSinkingFund).filter(JointSinkingFund.joint_account_id == 1, JointSinkingFund.name == name).first()

        if event.action == SyncAction.DELETE:
            action_on_balance = payload.get("action_on_balance")
            refund_shares = payload.get("refund_shares") or {}
            account = db.query(JointAccount).filter(JointAccount.id == 1).first()
            if action_on_balance == "REFUND_MEMBERS" and account and refund_shares:
                local_prof_str = account.local_profile.value if hasattr(account.local_profile, "value") else account.local_profile
                local_share = float(refund_shares.get(local_prof_str, 0.0) or 0.0)
                if local_share > 0:
                    try:
                        from backend.database.componentes.sqlite_crud import SQLiteRepository
                        from backend.domain.schemas import categories as personal_cat_schemas
                        from backend.domain.schemas import transactions as personal_tx_schemas
                        repo = SQLiteRepository(db)
                        cats = repo.get_categories()
                        income_cat = next((c for c in cats if getattr(c, "type", "") == "ingreso"), None)
                        if not income_cat:
                            income_cat = repo.create_category(
                                personal_cat_schemas.CategoryCreate(name="Ingresos Netos", type="ingreso")
                            )
                        if income_cat:
                            subcats = repo.get_subcategories(category_id=income_cat.id)
                            target_subcat = next(
                                (
                                    s for s in subcats
                                    if s.name in (
                                        "Reintegros por Cierres de Huchas Conjuntas",
                                        "Reintegro Hucha Conjunta",
                                    )
                                    or "reintegro" in s.name.lower()
                                    or "cierre" in s.name.lower()
                                ),
                                None,
                            )
                            if not target_subcat:
                                target_subcat = repo.create_subcategory(
                                    personal_cat_schemas.SubcategoryCreate(
                                        name="Reintegros por Cierres de Huchas Conjuntas",
                                        category_id=income_cat.id,
                                    )
                                )
                            event_date = datetime.fromisoformat(event.timestamp_utc.replace("Z", "+00:00")).date()
                            repo.create_transaction(
                                personal_tx_schemas.TransactionCreate(
                                    date=event_date,
                                    amount=local_share,
                                    description=f"Reintegro por cierre hucha '{name}'",
                                    subcategory_id=target_subcat.id,
                                )
                            )
                            logger.info(
                                "Reintegro remoto por liquidación de hucha '%s' aplicado en la cuenta personal local (%s €).",
                                name, local_share
                            )
                    except Exception as exc:
                        logger.warning("Error aplicando reintegro personal remoto por cierre de hucha %s: %s", name, exc)

            if fund:
                db.delete(fund)
            return

        target_amount = float(payload["target_amount"])
        current_balance = float(payload.get("current_balance", 0.0))
        monthly_target = float(payload.get("monthly_target_amount", 0.0))
        alloc_pct = float(payload.get("allocation_percentage", 0.0))
        status = payload.get("status", "ACTIVE")
        priority = int(payload.get("priority", 1))

        if fund:
            fund.target_amount = target_amount
            fund.current_balance = current_balance
            fund.monthly_target_amount = monthly_target
            fund.allocation_percentage = alloc_pct
            fund.status = status
            fund.priority = priority
        else:
            new_fund = JointSinkingFund(
                joint_account_id=1,
                name=name,
                target_amount=target_amount,
                current_balance=current_balance,
                monthly_target_amount=monthly_target,
                allocation_percentage=alloc_pct,
                status=status,
                priority=priority,
            )
            db.add(new_fund)

    def _archive_file(self, file_path: Path) -> None:
        """Mueve un archivo procesado a la carpeta sync/processed/ reemplazando si existe."""
        dest = self.processed_dir / file_path.name
        try:
            shutil.move(str(file_path), str(dest))
        except Exception as exc:
            logger.warning("Error moviendo archivo %s a processed: %s", file_path.name, exc)
            if file_path.exists():
                file_path.unlink()

    def get_sync_status(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """Calcula el estado del buzón de sincronización y métricas de deltas pendientes."""
        outbox_pending = len([f for f in self.outbox_dir.iterdir() if self._is_sync_file(f, require_json=True)])
        inbox_pending = len([f for f in self.inbox_dir.iterdir() if self._is_sync_file(f, require_json=True)])
        error_count = len([f for f in self.error_dir.iterdir() if self._is_sync_file(f, require_json=False)])

        last_applied_dt: Optional[datetime] = None
        if db:
            last_event = (
                db.query(JointAppliedSyncEvent)
                .order_by(JointAppliedSyncEvent.applied_at.desc())
                .first()
            )
            if last_event:
                last_applied_dt = last_event.applied_at

        is_synced = (inbox_pending == 0 and error_count == 0)

        return {
            "outbox_pending_count": outbox_pending,
            "inbox_pending_count": inbox_pending,
            "error_count": error_count,
            "last_applied_at": last_applied_dt.isoformat() if last_applied_dt else None,
            "is_synchronized": is_synced,
        }

    def clear_sync_folders(self, keep_outbox: bool = False) -> None:
        """Elimina todos los archivos delta de las carpetas de sincronización para volver al Estado Cero."""
        target_folders = (self.inbox_dir, self.processed_dir, self.error_dir) if keep_outbox else (self.outbox_dir, self.inbox_dir, self.processed_dir, self.error_dir)
        for folder in target_folders:
            if folder.exists():
                for file_path in folder.iterdir():
                    if self._is_sync_file(file_path, require_json=False):
                        try:
                            file_path.unlink()
                        except Exception as exc:
                            logger.warning("Error eliminando archivo delta %s: %s", file_path, exc)

    def get_pending_invitation(self) -> Optional[Dict[str, Any]]:
        """
        Inspecciona sync/inbox/ buscando si hay un evento entrante de tipo ACCOUNT emitido por la pareja.
        Retorna el payload de la cuenta si existe, o None si no hay invitaciones.
        """
        if not self.inbox_dir.exists():
            return None

        inbox_files = [
            f for f in self.inbox_dir.iterdir()
            if self._is_sync_file(f, require_json=True)
        ]
        for file_path in inbox_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entity = data.get("entity_type")
                action = data.get("action")
                if (entity == SyncEntityType.ACCOUNT.value or entity == "ACCOUNT") and (action in (SyncAction.UPSERT.value, "UPSERT")):
                    origin = data.get("origin_device_id")
                    if origin != self.local_device_id or origin == "LOCAL_DEVICE":
                        payload = data.get("payload", {})
                        return {
                            "event_id": data.get("event_id"),
                            "origin_device_id": origin,
                            "household_name": payload.get("household_name") or payload.get("account_name", "Hogar Compartido"),
                            "cohabitation_stage": payload.get("cohabitation_stage", "PRE_COHABITATION"),
                            "split_mode": payload.get("split_mode", "EQUAL_50_50"),
                            "contribution_strategy": payload.get("contribution_strategy", "NOMINAL_TEMPLATE"),
                            "member_a_reference_income": payload.get("member_a_reference_income", 0.0),
                            "member_b_reference_income": payload.get("member_b_reference_income", 0.0),
                            "member_a_contribution_pct": payload.get("member_a_contribution_pct", 50.0),
                            "member_b_contribution_pct": payload.get("member_b_contribution_pct", 50.0),
                            "member_a_name": payload.get("member_a_name", "Miembro A"),
                            "member_b_name": payload.get("member_b_name", "Miembro B"),
                            "custom_total_monthly_budget": float(payload.get("custom_total_monthly_budget", 0.0) or 0.0),
                        }
            except Exception as exc:
                logger.warning("Error inspeccionando posible invitación en %s: %s", file_path.name, exc)
        return None

    def get_pending_account_deletion(self, db: Session) -> Optional[Dict[str, Any]]:
        """
        Inspecciona sync/inbox/ buscando si hay un evento entrante ACCOUNT DELETE
        emitido por la pareja y posterior a la creación de la cuenta local.
        """
        if not self.inbox_dir.exists():
            return None
        account = db.query(JointAccount).filter(JointAccount.id == 1).first()
        if not account:
            return None

        inbox_files = [
            f for f in self.inbox_dir.iterdir()
            if self._is_sync_file(f, require_json=True)
        ]
        for file_path in inbox_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entity = data.get("entity_type")
                action = data.get("action")
                if (entity == SyncEntityType.ACCOUNT.value or entity == "ACCOUNT") and (action in (SyncAction.DELETE.value, "DELETE")):
                    origin = data.get("origin_device_id")
                    if origin != self.local_device_id and origin != "LOCAL_DEVICE":
                        event_dt_str = data.get("timestamp_utc", "")
                        event_dt = datetime.fromisoformat(event_dt_str.replace("Z", "+00:00"))
                        account_dt = account.created_at
                        if account_dt and account_dt.tzinfo is None:
                            account_dt = account_dt.replace(tzinfo=timezone.utc)
                        if not account_dt or event_dt >= account_dt:
                            partner_name = account.member_b_name if account.local_profile == "MEMBER_A" else account.member_a_name
                            return {
                                "event_id": data.get("event_id"),
                                "filename": file_path.name,
                                "origin_device_id": origin,
                                "timestamp_utc": event_dt_str,
                                "household_name": account.household_name,
                                "partner_name": partner_name,
                            }
            except Exception as exc:
                logger.warning("Error inspeccionando posible borrado remoto en %s: %s", file_path.name, exc)
        return None

    def resolve_remote_account_deletion(self, db: Session, accept: bool) -> Dict[str, Any]:
        """
        Resuelve una petición de borrado remoto pendiente:
        - accept=True: Purga la cuenta conjunta local, vuelve a Estado Cero y archiva el evento.
        - accept=False: Conserva la cuenta conjunta local y archiva el evento sin tocar la base de datos.
        """
        pending = self.get_pending_account_deletion(db)
        if not pending:
            return {"status": "error", "message": "No hay ninguna petición de borrado remoto pendiente."}

        event_id = pending["event_id"]
        filename = pending["filename"]
        file_path = self.inbox_dir / filename

        if file_path.exists():
            self._archive_file(file_path)

        if accept:
            from backend.database.componentes.sqlite_crud import SQLiteRepository
            repo = SQLiteRepository(db)
            repo.reset_joint_account()
            self.clear_sync_folders(keep_outbox=False)
            logger.info("Borrado remoto aceptado por el usuario: cuenta reseteada a Estado Cero.")
        else:
            logger.info("Borrado remoto rechazado por el usuario: se conservan los datos locales.")
            applied_record = JointAppliedSyncEvent(
                event_id=event_id,
                entity_type="ACCOUNT",
                action="DELETE",
            )
            db.add(applied_record)
            db.commit()

        return {
            "status": "success",
            "accepted": accept,
            "message": "Cuenta reseteada a Estado Cero." if accept else "Datos locales conservados.",
        }

    def get_sync_events_detail(self, max_processed: int = 30) -> Dict[str, Any]:
        """
        Inspecciona detalladamente los buzones de sincronizacion:
        - outbox: deltas pendientes de salida generados localmente.
        - inbox: deltas pendientes de entrada recibidos por Syncthing.
        - processed: ultimos N eventos archivados tras su aplicacion exitosa.
        - error: eventos en cuarentena que fallaron durante el procesamiento.
        """
        outbox_files = [f.name for f in self.outbox_dir.iterdir() if self._is_sync_file(f, require_json=True)] if self.outbox_dir.exists() else []
        inbox_files = [f.name for f in self.inbox_dir.iterdir() if self._is_sync_file(f, require_json=True)] if self.inbox_dir.exists() else []

        processed_files = [f for f in self.processed_dir.iterdir() if self._is_sync_file(f, require_json=True)] if self.processed_dir.exists() else []
        processed_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        processed_events = []
        for pf in processed_files[:max_processed]:
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    ev_data = json.load(f)
                processed_events.append({
                    "filename": pf.name,
                    "event_id": ev_data.get("event_id", ""),
                    "entity_type": ev_data.get("entity_type", ""),
                    "action": ev_data.get("action", ""),
                    "timestamp_utc": ev_data.get("timestamp_utc", ""),
                    "origin_device_id": ev_data.get("origin_device_id", ""),
                })
            except Exception as exc:
                logger.warning("Error leyendo evento procesado %s: %s", pf.name, exc)

        error_files = [f for f in self.error_dir.iterdir() if self._is_sync_file(f, require_json=False)] if self.error_dir.exists() else []
        error_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        error_events = []
        for ef in error_files:
            try:
                with open(ef, "r", encoding="utf-8", errors="replace") as f:
                    snippet = f.read(250)
                error_events.append({
                    "filename": ef.name,
                    "preview": snippet,
                })
            except Exception as exc:
                error_events.append({"filename": ef.name, "preview": f"Error: {exc}"})

        return {
            "outbox_count": len(outbox_files),
            "inbox_count": len(inbox_files),
            "processed_count": len(processed_files),
            "error_count": len(error_files),
            "processed_events": processed_events,
            "error_events": error_events,
        }

    def retry_failed_events(self, db: Session) -> Dict[str, Any]:
        """
        Recupera los archivos de sync/error/, los devuelve a sync/inbox/ y dispara
        inmediatamente el procesamiento para reintentar su aplicacion.
        """
        if not self.error_dir.exists():
            return {"retried_count": 0, "status": "No existe directorio de error."}

        error_files = [
            f for f in self.error_dir.iterdir()
            if self._is_sync_file(f, require_json=True)
        ]
        retried = 0
        for ef in error_files:
            dest = self.inbox_dir / ef.name
            try:
                shutil.move(str(ef), str(dest))
                retried += 1
            except Exception as exc:
                logger.warning("Error moviendo evento fallido %s a inbox: %s", ef.name, exc)

        summary = self.process_inbox(db)
        return {
            "retried_count": retried,
            "process_summary": summary,
        }

    def clear_failed_events(self) -> int:
        """Elimina todos los archivos delta en cuarentena de sync/error/."""
        if not self.error_dir.exists():
            return 0
        deleted = 0
        for ef in self.error_dir.iterdir():
            if self._is_sync_file(ef, require_json=False):
                try:
                    ef.unlink()
                    deleted += 1
                except Exception as exc:
                    logger.warning("Error eliminando archivo fallido %s: %s", ef.name, exc)
        return deleted

