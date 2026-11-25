"""Dependencias compartidas y modelos de petición del router de cuenta conjunta."""

from datetime import date
from typing import Optional

from fastapi import Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.database.componentes.sqlite_db import get_db
from backend.domain.schemas import joint as schemas
from backend.services.joint_sync_service import JointSyncService


def get_repo(db: Session = Depends(get_db)) -> SQLiteRepository:
    return SQLiteRepository(db)


def get_sync_service() -> JointSyncService:
    return JointSyncService()


class AssistedContributionRequest(BaseModel):
    """Petición para el asiento asistido en 1 clic de inicio de mes."""

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: float = Field(gt=0.0)
    contributor_profile: schemas.ProfileIdentifier
    personal_subcategory_id: Optional[int] = None
    contribution_date: Optional[date] = None
    target_sinking_fund_id: Optional[int] = None
