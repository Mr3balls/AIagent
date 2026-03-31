from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import TenderStatus


class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TenderBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    customer_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)


class TenderCreate(TenderBase):
    pass


class TenderDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tender_id: UUID
    original_filename: str
    stored_filename: str
    file_path: str
    file_type: str
    mime_type: str | None
    file_size: int
    checksum_sha256: str
    created_at: datetime


class TenderUploadResponse(BaseModel):
    tender_id: UUID
    uploaded_count: int
    documents: list[TenderDocumentResponse]


class TenderListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    customer_name: str
    status: TenderStatus
    tender_risk_score: float | None
    created_at: datetime
    updated_at: datetime


class TenderDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    customer_name: str
    description: str | None
    status: TenderStatus
    tender_risk_score: float | None
    analysis_summary: str | None
    extracted_requirements: dict[str, Any] | None
    report_payload: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    documents: list[TenderDocumentResponse] = []


class TenderCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    customer_name: str
    description: str | None
    status: TenderStatus
    created_at: datetime
    updated_at: datetime