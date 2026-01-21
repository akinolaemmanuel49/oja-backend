from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# Base schema for shared fields
class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Product name")
    description: Optional[str] = Field(
        None, max_length=2000, description="Product description"
    )
    type: str = Field(
        ...,
        pattern="^(simple|variable)$",
        description="Product type: simple or variable",
    )
    base_price: Optional[Decimal] = Field(
        None, ge=0, description="Base price for the product"
    )
    sku: Optional[str] = Field(
        None, min_length=1, max_length=100, description="Unique SKU for simple products"
    )


# Create schema (input for creation)
class ProductCreate(ProductBase):
    variants: Optional[List["ProductVariantCreate"]] = Field(
        None, description="List of variants for variable products"
    )

    @field_validator("variants")
    @classmethod
    def validate_variants(cls, v, values):
        if values.get("type") == "variable" and (not v or len(v) == 0):
            raise ValueError("Variable products must have at least one variant")
        if values.get("type") == "simple" and v:
            raise ValueError("Simple products cannot have variants")
        return v


# Update schema (partial updates)
class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    base_price: Optional[Decimal] = Field(None, ge=0)
    sku: Optional[str] = Field(None, min_length=1, max_length=100)


# Output schema (response model, includes DB fields)
class ProductOut(ProductBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
    variants: Optional[List["ProductVariantOut"]] = None  # Nested variants if fetched

    class Config:
        from_attributes = True


# Variant schemas (nested under products for variable types)
class ProductVariantBase(BaseModel):
    sku: Optional[str] = Field(
        None, min_length=1, max_length=100, description="Variant-specific SKU"
    )
    price: Optional[Decimal] = Field(None, ge=0, description="Variant price override")
    stock_quantity: int = Field(default=0, ge=0, description="Available stock")
    re_order_level: int = Field(default=0, ge=0, description="Reorder threshold")
    attributes: Optional[dict] = Field(
        None, description="Variant attributes (e.g., {'size': 'M', 'color': 'blue'})"
    )


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantUpdate(BaseModel):
    sku: Optional[str] = None
    price: Optional[Decimal] = None
    stock_quantity: Optional[int] = None
    re_order_level: Optional[int] = None
    attributes: Optional[dict] = None


class ProductVariantOut(ProductVariantBase):
    id: UUID
    product_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Separate schemas for linking to storefronts (not part of core product CRUD)
class StorefrontProductLink(BaseModel):
    display_order: int = Field(
        default=0, ge=0, description="Display order in storefront"
    )
    is_visible: bool = Field(default=True, description="Visibility in storefront")


class StorefrontProductLinkUpdate(BaseModel):
    display_order: Optional[int] = None
    is_visible: Optional[bool] = None
