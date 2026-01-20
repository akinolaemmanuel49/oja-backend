from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class StorefrontCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    domain: Optional[str] = None
    status: str = Field(default="active", pattern="^(active|suspended|deleted)$")


class StorefrontUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = None


class StorefrontOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    domain: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
