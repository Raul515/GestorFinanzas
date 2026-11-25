"""Paquete modular del router REST para el espacio conjunto del hogar (Spec 010 / Spec 017)."""

from fastapi import APIRouter

from backend.api.routers.joint import account, contributions, sinking_funds, sync, transactions
from backend.api.routers.joint.deps import (
    AssistedContributionRequest,
    get_repo,
    get_sync_service,
)

router = APIRouter(prefix="/joint", tags=["joint"])
router.include_router(account.router)
router.include_router(sinking_funds.router)
router.include_router(transactions.router)
router.include_router(contributions.router)
router.include_router(sync.router)

__all__ = [
    "AssistedContributionRequest",
    "get_repo",
    "get_sync_service",
    "router",
]
