"""
Mobile Micro-App Pydantic Schemas (Spec 016).
Defines contracts for offline-first catalog, synchronization payloads,
prevention of cross-device Wi-Fi pollution (Pairing Token),
on-the-fly subcategories, and mobile monthly summary (50/30/20 & Emergency Fund).
"""

import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class MobileCatalogSubcategory(BaseModel):
    """Subcategory item formatted for quick touch chips on mobile."""
    id: int
    name: str
    category_id: int
    category_name: str
    category_type: str = "expense"
    is_frequent: bool = False


class MobileCatalogResponse(BaseModel):
    """Full offline catalog response containing subcategories and frequent concepts."""
    device_id: str
    last_updated_utc: str
    personal_subcategories: List[MobileCatalogSubcategory]
    frequent_concepts: List[str] = Field(default_factory=list)


class MobileTransactionPayload(BaseModel):
    """Individual transaction captured on mobile."""
    event_id: str = Field(..., description="Unique client-generated event UUID")
    scope: str = Field("PERSONAL", description="Scope: currently only PERSONAL")
    type: Optional[str] = Field("EXPENSE", description="Transaction type: EXPENSE or INCOME")
    amount: float = Field(..., gt=0, description="Transaction amount in EUR, must be > 0")
    description: str = Field(..., min_length=1, description="Concept or merchant name")
    date: datetime.date = Field(..., description="Transaction date YYYY-MM-DD")
    subcategory_id: Optional[int] = Field(None, description="Subcategory ID or <= 0 for on-the-fly")
    subcategory_name: Optional[str] = Field(None, description="Subcategory name for fallback or on-the-fly")
    created_at_utc: Optional[str] = None
    receipt_base64: Optional[str] = Field(None, description="Optional client-compressed JPEG base64 receipt image")
    receipt_filename: Optional[str] = Field(None, description="Stored receipt filename if already uploaded")

    @field_validator("description")
    @classmethod
    def validate_non_empty_description(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("La descripción o concepto no puede estar vacía.")
        return stripped


class MobileSyncRequest(BaseModel):
    """Batch of offline transactions sent by mobile client upon reconnection."""
    device_id: str
    transactions: List[MobileTransactionPayload]


class MobileSyncResponse(BaseModel):
    """Server synchronization acknowledgment."""
    success: bool
    processed_count: int
    ignored_duplicates_count: int
    server_timestamp_utc: str


class MobileSyncStatusResponse(BaseModel):
    """Mobile sync diagnostic and pairing status."""
    server_online: bool = True
    pending_inbox_files: int = 0
    today_transactions_count: int = 0
    catalog_last_updated_utc: Optional[str] = None
    pairing_token: Optional[str] = None
    authenticated: bool = True


class MobileSubcategoryCreate(BaseModel):
    """Payload to create an on-the-fly subcategory from mobile UI."""
    name: str = Field(..., min_length=1, description="Subcategory name")
    category_name: Optional[str] = Field("Deseos (30%)", description="Parent category name")
    category_id: Optional[int] = Field(None, description="Parent category ID if known")


class MobileSubcategoryResponse(BaseModel):
    """Response returned after creating or resolving a subcategory."""
    id: int
    name: str
    category_id: int
    category_name: str
    is_new: bool = True


class MobileBudgetUpdate(BaseModel):
    """Payload to update budgeted amount for a subcategory in a given month."""
    month: Optional[str] = Field(None, description="Target month in YYYY-MM format")
    subcategory_id: int = Field(..., description="Subcategory identifier")
    amount: float = Field(..., ge=0, description="New budgeted amount in EUR")

    @model_validator(mode="before")
    @classmethod
    def map_allocated_amount(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "amount" not in data and "allocated_amount" in data:
                data["amount"] = data["allocated_amount"]
            if not data.get("month"):
                data["month"] = datetime.date.today().strftime("%Y-%m")
        return data


class MobileCategorySummary(BaseModel):
    """Monthly summary per 50/30/20 category."""
    category_id: int
    category_name: str
    budgeted_amount: float
    spent_amount: float
    remaining_amount: float
    # Alias / compatibilidad frontend móvil
    rule_percentage: float = 0.0
    spent: float = 0.0
    budget: float = 0.0
    remaining: float = 0.0
    progress_percentage: float = 0.0


class MobileEmergencyFundSummary(BaseModel):
    """Emergency fund summary status."""
    current_amount: float
    target_amount: float
    months_covered: float
    is_funded: bool


class MobileMonthlySummaryResponse(BaseModel):
    """Full monthly budget summary for mobile 'Mi Mes' view."""
    month: str
    total_budgeted: float
    total_spent: float
    total_remaining: float
    total_income: float = 0.0
    remaining_budget: float = 0.0
    categories: List[MobileCategorySummary] = Field(default_factory=list)
    emergency_fund_balance: float = 0.0
    emergency_fund_target_months: int = 3
    emergency_fund_months_covered: float = 0.0
    emergency_fund: Optional[MobileEmergencyFundSummary] = None
    needs: Optional[MobileCategorySummary] = None
    wants: Optional[MobileCategorySummary] = None
    savings: Optional[MobileCategorySummary] = None
    subcategories: List[Dict[str, Any]] = Field(default_factory=list)


class MobileVersionResponse(BaseModel):
    """Information about the latest published mobile APK release."""
    version_code: int = Field(1, description="Integer build version code")
    version_name: str = Field("1.0.0", description="Semantic version string")
    apk_available: bool = Field(False, description="Whether an APK binary is ready for OTA download")
    apk_url: Optional[str] = Field(None, description="Download endpoint URL")
    apk_filename: Optional[str] = Field(None, description="Name of the APK file")
    apk_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    release_notes: Optional[str] = Field(None, description="Release changelog notes")
    released_at_utc: Optional[str] = None


class MobileHistoricalTransactionItem(BaseModel):
    """Historical transaction record for fast mobile search."""
    id: int
    date: str
    amount: float
    description: str
    type: Optional[str] = "EXPENSE"
    subcategory_id: int
    subcategory_name: str
    category_name: str
    receipt_filename: Optional[str] = None
    receipt_url: Optional[str] = None


class MobileSearchResponse(BaseModel):
    """Response containing matched transactions for mobile search."""
    query: str
    total_found: int
    items: List[MobileHistoricalTransactionItem] = Field(default_factory=list)


class MobileReceiptUploadResponse(BaseModel):
    """Response returned upon uploading a receipt image."""
    success: bool
    event_id: str
    receipt_filename: str
    receipt_url: str


