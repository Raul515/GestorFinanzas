"""Sub-router de transacciones comunes y liquidación de gastos adelantados."""

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.routers.joint.deps import get_repo, get_sync_service
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.schemas import joint as schemas
from backend.services.joint_accounting_service import calculate_settlement_summary
from backend.services.joint_application_service import build_joint_transaction_sync_payload
from backend.services.joint_sync_service import JointSyncService

router = APIRouter()


@router.get("/transactions", response_model=List[schemas.JointTransactionResponse])
def get_joint_transactions(
    year: Optional[int] = None,
    month: Optional[str] = None,
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointTransactionResponse]:
    """Obtiene transacciones de necesidades o cargos a huchas comunes."""
    return [schemas.JointTransactionResponse.model_validate(t) for t in repo.get_joint_transactions(year=year, month=month)]


@router.get("/transactions/search", response_model=List[schemas.JointTransactionResponse])
def search_joint_transactions(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    query: Optional[str] = None,
    joint_subcategory_id: Optional[int] = None,
    paid_by: Optional[str] = None,
    settlement_status: Optional[str] = None,
    is_sinking_fund: Optional[bool] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointTransactionResponse]:
    """Búsqueda global y filtrado multicriterio de transacciones del hogar."""
    txs = repo.search_joint_transactions(
        start_date=start_date,
        end_date=end_date,
        query_text=query,
        joint_subcategory_id=joint_subcategory_id,
        paid_by=paid_by,
        settlement_status=settlement_status,
        is_sinking_fund=is_sinking_fund,
        min_amount=min_amount,
        max_amount=max_amount,
    )
    return [schemas.JointTransactionResponse.model_validate(t) for t in txs]


@router.post("/transactions", response_model=schemas.JointTransactionResponse, status_code=status.HTTP_201_CREATED)
def create_joint_transaction(
    tx_create: schemas.JointTransactionCreate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointTransactionResponse:
    """Registra un nuevo gasto común del hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cuenta conjunta no configurada.",
        )

    tx = repo.create_joint_transaction(tx_create)
    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.TRANSACTION,
        action=schemas.SyncAction.UPSERT,
        payload=build_joint_transaction_sync_payload(repo, tx),
        origin_device_id=sync_service.local_device_id,
    )
    return schemas.JointTransactionResponse.model_validate(tx)


@router.delete("/transactions/{transaction_id}")
def delete_joint_transaction(
    transaction_id: int,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Elimina un gasto común y emite el tombstone correspondiente a Syncthing."""
    tx_uuid = repo.delete_joint_transaction(transaction_id)
    if not tx_uuid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transacción no encontrada.")

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.TRANSACTION,
        action=schemas.SyncAction.DELETE,
        payload={"uuid": tx_uuid},
        origin_device_id=sync_service.local_device_id,
    )

    return {"deleted": True, "uuid": tx_uuid}


@router.get("/settlement/summary", response_model=schemas.JointSettlementSummaryResponse)
def get_joint_settlement_summary(
    repo: SQLiteRepository = Depends(get_repo),
) -> schemas.JointSettlementSummaryResponse:
    """Obtiene el resumen consolidado de deudas y saldos pendientes de reembolso."""
    account = repo.get_joint_account()
    transactions = repo.get_joint_transactions()
    summary = calculate_settlement_summary(transactions, account)
    return schemas.JointSettlementSummaryResponse.model_validate(summary)


@router.post("/settlement/settle-transaction/{transaction_id}", response_model=schemas.JointTransactionResponse)
def settle_joint_transaction(
    transaction_id: int,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointTransactionResponse:
    """Marca un gasto común adelantado como liquidado/reembolsado y emite el delta de sincronización."""
    tx = repo.settle_joint_transaction(transaction_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transacción {transaction_id} no encontrada.",
        )

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.TRANSACTION,
        action=schemas.SyncAction.UPSERT,
        payload=build_joint_transaction_sync_payload(repo, tx),
        origin_device_id=sync_service.local_device_id,
    )

    return schemas.JointTransactionResponse.model_validate(tx)


@router.post("/settlement/settle-all", response_model=List[schemas.JointTransactionResponse])
def settle_all_joint_transactions(
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> List[schemas.JointTransactionResponse]:
    """Marca en bloque todas las transacciones pendientes como liquidadas/reembolsadas y emite sus deltas."""
    settled_txs = repo.settle_all_joint_transactions()
    for tx in settled_txs:
        sync_service.emit_event(
            entity_type=schemas.SyncEntityType.TRANSACTION,
            action=schemas.SyncAction.UPSERT,
            payload=build_joint_transaction_sync_payload(repo, tx),
            origin_device_id=sync_service.local_device_id,
        )

    return [schemas.JointTransactionResponse.model_validate(tx) for tx in settled_txs]
