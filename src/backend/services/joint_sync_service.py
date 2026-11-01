"""
Motor de Sincronización Asíncrona Desacoplada (Event Sourcing Inbox/Outbox para Syncthing) (Spec 010).
Opera mediante lectura y escritura exclusiva de ficheros JSON atómicos en disco local (sync/),
garantizando resiliencia ante desconexiones, idempotencia por UUIDv4 y resolución determinista LWW.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from backend.domain.models.joint import (
    JointAppliedSyncEvent,
    JointMonthlyContribution,
    JointSinkingFund,
    JointSubcategory,
    JointTransaction,
)
from backend.domain.schemas.joint import (
    ProfileIdentifier,
    SyncAction,
    SyncEntityType,
    SyncEventPayload,
)

logger = logging.getLogger(__name__)


class JointSyncService:
    """Servicio de gestión de buzones de sincronización y resolución de conflictos LWW."""

    def __init__(self, base_sync_dir: Optional[str] = None, local_device_id: str = "LOCAL_DEVICE"):
        if base_sync_dir:
            self.base_dir = Path(base_sync_dir)
        else:
            # Por defecto: directorio 'sync' en la raíz del proyecto
            root_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.base_dir = root_dir / "sync"

        self.outbox_dir = self.base_dir / "outbox"
        self.inbox_dir = self.base_dir / "inbox"
        self.processed_dir = self.base_dir / "processed"
        self.error_dir = self.base_dir / "error"
        self.local_device_id = local_device_id

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
        except Exception as exc:
            logger.error("Error emitiendo evento delta a outbox (%s): %s", eff_event_id, exc)
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

        return event_payload

    def process_inbox(self, db: Session) -> Dict[str, Any]:
        """
        Escanea la bandeja sync/inbox/, ordena los eventos por timestamp_utc, aplica
        los cambios en SQLite de forma idempotente con resolución LWW y archiva los procesados.
        """
        inbox_files = [
            f for f in self.inbox_dir.iterdir()
            if f.is_file() and f.suffix == ".json" and not f.name.endswith(".tmp")
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

            # Aplicar evento según tipo de entidad
            try:
                self._apply_event(db, event)

                # Registrar evento en la tabla de aplicados para idempotencia futura
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
        payload = event.payload

        if event.entity_type == SyncEntityType.TRANSACTION:
            self._apply_transaction_event(db, event)
        elif event.entity_type == SyncEntityType.CONTRIBUTION:
            self._apply_contribution_event(db, event)
        elif event.entity_type == SyncEntityType.SINKING_FUND:
            self._apply_sinking_fund_event(db, event)
        else:
            logger.warning("Tipo de entidad no manejada en sincronización: %s", event.entity_type)

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
                # Revertir saldo de hucha si estaba vinculada
                if existing_tx.joint_sinking_fund_id:
                    fund = db.query(JointSinkingFund).filter(JointSinkingFund.id == existing_tx.joint_sinking_fund_id).first()
                    if fund:
                        fund.current_balance += existing_tx.amount
                db.delete(existing_tx)
            return

        if event.action == SyncAction.UPSERT:
            # Resolver subcategoría por nombre si viene en el payload, para evitar colisión de IDs locales
            subcat_id = payload.get("joint_subcategory_id")
            subcat_name = payload.get("subcategory_name")
            if subcat_name and not subcat_id:
                subcat = db.query(JointSubcategory).filter(JointSubcategory.name == subcat_name).first()
                if subcat:
                    subcat_id = subcat.id

            sinking_id = payload.get("joint_sinking_fund_id")
            sinking_name = payload.get("sinking_fund_name")
            if sinking_name and not sinking_id:
                fund = db.query(JointSinkingFund).filter(JointSinkingFund.name == sinking_name).first()
                if fund:
                    sinking_id = fund.id

            tx_date = datetime.strptime(payload["date"], "%Y-%m-%d").date() if isinstance(payload["date"], str) else payload["date"]
            amount = float(payload["amount"])
            desc = payload["description"]
            profile = payload.get("created_by_profile", "REMOTE")

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
                        old_fund.current_balance += existing_tx.amount

                existing_tx.date = tx_date
                existing_tx.amount = amount
                existing_tx.description = desc
                existing_tx.joint_subcategory_id = subcat_id
                existing_tx.joint_sinking_fund_id = sinking_id
                existing_tx.created_by_profile = profile
                existing_tx.updated_at = event_dt

                if sinking_id:
                    new_fund = db.query(JointSinkingFund).filter(JointSinkingFund.id == sinking_id).first()
                    if new_fund:
                        new_fund.current_balance = max(0.0, new_fund.current_balance - amount)
            else:
                new_tx = JointTransaction(
                    uuid=tx_uuid,
                    joint_account_id=1,
                    date=tx_date,
                    amount=amount,
                    description=desc,
                    joint_subcategory_id=subcat_id,
                    joint_sinking_fund_id=sinking_id,
                    created_by_profile=profile,
                    created_at=event_dt,
                    updated_at=event_dt,
                )
                db.add(new_tx)

                if sinking_id:
                    fund = db.query(JointSinkingFund).filter(JointSinkingFund.id == sinking_id).first()
                    if fund:
                        fund.current_balance = max(0.0, fund.current_balance - amount)

    def _apply_contribution_event(self, db: Session, event: SyncEventPayload) -> None:
        """Aplica aportación mensual sincronizada."""
        payload = event.payload
        month = payload["month"]
        profile = payload["contributor_profile"]
        amount = float(payload["amount"])
        c_date = datetime.strptime(payload["contribution_date"], "%Y-%m-%d").date() if isinstance(payload["contribution_date"], str) else payload["contribution_date"]

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

        if existing_c:
            existing_c.amount = amount
            existing_c.contribution_date = c_date
        else:
            new_c = JointMonthlyContribution(
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
        outbox_pending = len([f for f in self.outbox_dir.iterdir() if f.is_file() and f.suffix == ".json" and not f.name.endswith(".tmp")])
        inbox_pending = len([f for f in self.inbox_dir.iterdir() if f.is_file() and f.suffix == ".json" and not f.name.endswith(".tmp")])
        error_count = len([f for f in self.error_dir.iterdir() if f.is_file()])

        last_applied_dt: Optional[datetime] = None
        if db:
            last_event = (
                db.query(JointAppliedSyncEvent)
                .order_by(JointAppliedSyncEvent.applied_at.desc())
                .first()
            )
            if last_event:
                last_applied_dt = last_event.applied_at

        return {
            "outbox_pending_count": outbox_pending,
            "inbox_pending_count": inbox_pending,
            "error_count": error_count,
            "last_applied_at": last_applied_dt.isoformat() if last_applied_dt else None,
            "is_synchronized": outbox_pending == 0 and inbox_pending == 0,
        }

    def clear_sync_folders(self) -> None:
        """Elimina todos los archivos delta de las carpetas de sincronización para volver al Estado Cero."""
        for folder in (self.outbox_dir, self.inbox_dir, self.processed_dir, self.error_dir):
            if folder.exists():
                for file_path in folder.glob("*"):
                    if file_path.is_file():
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
            if f.is_file() and f.suffix == ".json" and not f.name.endswith(".tmp")
        ]
        for file_path in inbox_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entity = data.get("entity_type")
                if entity == SyncEntityType.ACCOUNT.value or entity == "ACCOUNT":
                    if data.get("origin_device_id") != self.local_device_id:
                        payload = data.get("payload", {})
                        return {
                            "event_id": data.get("event_id"),
                            "origin_device_id": data.get("origin_device_id"),
                            "household_name": payload.get("household_name") or payload.get("account_name", "Hogar Compartido"),
                            "cohabitation_stage": payload.get("cohabitation_stage", "PRE_COHABITATION"),
                            "split_mode": payload.get("split_mode", "EQUAL_50_50"),
                            "contribution_strategy": payload.get("contribution_strategy", "NOMINAL_TEMPLATE"),
                            "member_a_reference_income": payload.get("member_a_reference_income", 0.0),
                            "member_b_reference_income": payload.get("member_b_reference_income", 0.0),
                            "member_a_name": payload.get("member_a_name", "Miembro A"),
                            "member_b_name": payload.get("member_b_name", "Miembro B"),
                        }
            except Exception as exc:
                logger.warning("Error inspeccionando posible invitación en %s: %s", file_path.name, exc)
        return None
