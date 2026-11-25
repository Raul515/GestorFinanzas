"""Sub-router de huchas de amortización (sinking funds) y traspasos de cuenta conjunta."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.routers.joint.deps import get_repo, get_sync_service
from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.schemas import joint as schemas
from backend.services.joint_application_service import (
    JointNotFoundError,
    JointValidationError,
    build_sinking_fund_sync_payload,
    delete_joint_sinking_fund_with_refund,
)
from backend.services.joint_sync_service import JointSyncService

router = APIRouter()


@router.get("/sinking-funds", response_model=List[schemas.JointSinkingFundResponse])
def get_joint_sinking_funds(
    fund_status: Optional[str] = Query(default=None, alias="status"),
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointSinkingFundResponse]:
    """Consulta las huchas de amortización del hogar."""
    return [schemas.JointSinkingFundResponse.model_validate(f) for f in repo.get_joint_sinking_funds(status=fund_status)]


@router.post("/sinking-funds", response_model=schemas.JointSinkingFundResponse, status_code=status.HTTP_201_CREATED)
def create_joint_sinking_fund(
    fund_create: schemas.JointSinkingFundCreate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointSinkingFundResponse:
    """Crea una nueva meta de amortización para el hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe configurar la cuenta conjunta antes de añadir huchas.",
        )

    fund = repo.create_joint_sinking_fund(fund_create)
    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SINKING_FUND,
        action=schemas.SyncAction.UPSERT,
        payload=fund_create.model_dump(mode="json"),
        origin_device_id=sync_service.local_device_id,
    )
    return schemas.JointSinkingFundResponse.model_validate(fund)


@router.put("/sinking-funds/{fund_id}", response_model=schemas.JointSinkingFundResponse)
def update_joint_sinking_fund(
    fund_id: int,
    fund_update: schemas.JointSinkingFundUpdate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointSinkingFundResponse:
    """Edita las metas, cuotas o estado de una hucha de amortización."""
    fund = repo.update_joint_sinking_fund(fund_id, fund_update)
    if not fund:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hucha no encontrada.")

    payload = fund_update.model_dump(exclude_unset=True, mode="json")
    payload["name"] = fund.name
    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SINKING_FUND,
        action=schemas.SyncAction.UPSERT,
        payload=payload,
        origin_device_id=sync_service.local_device_id,
    )
    return schemas.JointSinkingFundResponse.model_validate(fund)


@router.delete("/sinking-funds/{fund_id}")
def delete_joint_sinking_fund(
    fund_id: int,
    reallocate_to_fund_id: Optional[int] = Query(default=None),
    action_on_balance: Optional[str] = Query(default=None),
    refund_personal_entry: bool = Query(default=True),
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Elimina una hucha de amortización aplicando el destino obligatorio a su saldo remanente."""
    try:
        return delete_joint_sinking_fund_with_refund(
            repo=repo,
            sync_service=sync_service,
            fund_id=fund_id,
            reallocate_to_fund_id=reallocate_to_fund_id,
            action_on_balance=action_on_balance,
            refund_personal_entry=refund_personal_entry,
        )
    except JointNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except JointValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/sinking-funds/transfer", response_model=schemas.JointSinkingFundTransferResponse, status_code=status.HTTP_201_CREATED)
def transfer_joint_sinking_fund(
    transfer_req: schemas.JointSinkingFundTransferCreate,
    repo: SQLiteRepository = Depends(get_repo),
    sync_service: JointSyncService = Depends(get_sync_service),
) -> schemas.JointSinkingFundTransferResponse:
    """Ejecuta un traspaso/rebalanceo directo de saldo entre dos huchas de amortización del hogar."""
    account = repo.get_joint_account()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cuenta conjunta no configurada.",
        )

    if transfer_req.source_fund_id == transfer_req.target_fund_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La hucha de origen y de destino no pueden ser la misma.",
        )

    try:
        transfer = repo.transfer_sinking_fund_balance(transfer_req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    source_fund = repo.get_joint_sinking_fund(transfer.source_fund_id)
    target_fund = repo.get_joint_sinking_fund(transfer.target_fund_id)

    for fund in (source_fund, target_fund):
        if fund:
            sync_service.emit_event(
                entity_type=schemas.SyncEntityType.SINKING_FUND,
                action=schemas.SyncAction.UPSERT,
                payload=build_sinking_fund_sync_payload(fund),
                origin_device_id=sync_service.local_device_id,
            )

    sync_service.emit_event(
        entity_type=schemas.SyncEntityType.SINKING_FUND_TRANSFER,
        action=schemas.SyncAction.UPSERT,
        payload={
            "uuid": transfer.uuid,
            "source_fund_id": transfer.source_fund_id,
            "source_fund_name": source_fund.name if source_fund else None,
            "target_fund_id": transfer.target_fund_id,
            "target_fund_name": target_fund.name if target_fund else None,
            "amount": transfer.amount,
            "date": transfer.date.isoformat() if hasattr(transfer.date, "isoformat") else str(transfer.date),
            "notes": transfer.notes,
            "created_by_profile": transfer.created_by_profile,
        },
        origin_device_id=sync_service.local_device_id,
    )

    resp = schemas.JointSinkingFundTransferResponse.model_validate(transfer)
    if source_fund:
        resp.source_fund_name = source_fund.name
    if target_fund:
        resp.target_fund_name = target_fund.name
    return resp


@router.get("/sinking-funds/transfers", response_model=List[schemas.JointSinkingFundTransferResponse])
def get_joint_sinking_fund_transfers(
    limit: int = Query(default=100, ge=1, le=500),
    repo: SQLiteRepository = Depends(get_repo),
) -> List[schemas.JointSinkingFundTransferResponse]:
    """Obtiene el historial cronológico de traspasos y rebalanceos entre huchas."""
    transfers = repo.get_joint_sinking_fund_transfers(limit=limit)
    funds_all = {f.id: f.name for f in repo.get_joint_sinking_funds()}
    result = []
    for t in transfers:
        item = schemas.JointSinkingFundTransferResponse.model_validate(t)
        item.source_fund_name = funds_all.get(t.source_fund_id, f"Hucha #{t.source_fund_id}")
        item.target_fund_name = funds_all.get(t.target_fund_id, f"Hucha #{t.target_fund_id}")
        result.append(item)
    return result
