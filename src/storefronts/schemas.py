"""
Pydantic schemas for the storefront-related operations.

Storefronts allow users to create and manage their own storefronts, which can be used to sell products and services. Storefronts can be created, updated, and deleted using the provided schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class StorefrontCreate(BaseModel):
    """
    Schema for creating a new storefront.
    """

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    domain: Optional[str] = None
    status: str = Field(default="active", pattern="^(active|suspended|deleted)$")


class StorefrontUpdate(BaseModel):
    """
    Schema for updating an existing storefront.
    """

    name: Optional[str] = None
    slug: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = None


class StorefrontOut(BaseModel):
    """
    Schema for representing a storefront.
    """

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
