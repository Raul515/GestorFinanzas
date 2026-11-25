"""
Servicio de Aplicación para Transacciones Personales (Spec 017).
Orquesta la eliminación de transacciones personales desacoplando la persistencia
SQLite de los efectos secundarios en disco/sincronización (MobileSyncService / JointSyncService).
"""

import logging
from typing import Any, Dict

from backend.domain.schemas import joint as joint_schema

logger = logging.getLogger(__name__)


def delete_personal_transaction(repo: Any, transaction_id: int) -> bool:
    """
    Elimina una transacción personal en base de datos y propaga los efectos secundarios:
    - Deltas Syncthing si estaba vinculada a una aportación conjunta.
    - Borrado físico de comprobantes y registro de tombstones móviles si aplica.
    """
    if hasattr(repo, "delete_transaction_with_context"):
        deleted, context = repo.delete_transaction_with_context(transaction_id)
    else:
        deleted = bool(repo.delete_transaction(transaction_id))
        context = {}

    if not deleted:
        return False

    del_info: Dict[str, Any] = context.get("joint_del_info") or {}
    if del_info and del_info.get("uuid"):
        try:
            from backend.services.joint_sync_service import JointSyncService

            sync_svc = JointSyncService()
            sync_svc.emit_event(
                entity_type=joint_schema.SyncEntityType.CONTRIBUTION,
                action=joint_schema.SyncAction.DELETE,
                payload={
                    "uuid": del_info["uuid"],
                    "month": del_info["month"],
                    "contributor_profile": del_info["contributor_profile"],
                },
                origin_device_id=sync_svc.local_device_id,
            )
            for f_data in (del_info.get("reverted_funds") or {}).values():
                sync_svc.emit_event(
                    entity_type=joint_schema.SyncEntityType.SINKING_FUND,
                    action=joint_schema.SyncAction.UPSERT,
                    payload=f_data,
                    origin_device_id=sync_svc.local_device_id,
                )
        except Exception as sync_exc:
            logger.warning("No se pudo emitir tombstone conjunto tras eliminar transacción %s: %s", transaction_id, sync_exc)

    receipt_filenames = context.get("receipt_filenames") or []
    mobile_event_ids = context.get("mobile_event_ids") or []
    if receipt_filenames or mobile_event_ids:
        try:
            from backend.services.mobile_sync_service import MobileSyncService

            mob_svc = MobileSyncService()
            for r_fn in receipt_filenames:
                mob_svc.delete_receipt_file(r_fn)
            for evt_id in mobile_event_ids:
                mob_svc.record_deleted_event_id(evt_id)
        except Exception as mob_exc:
            logger.warning("No se pudo limpiar sincronización móvil tras eliminar transacción %s: %s", transaction_id, mob_exc)

    return True
