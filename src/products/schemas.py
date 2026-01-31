"""
Pydantic schemas for product-related operations.
Supports simple and variable products with layered variant generation.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# ───────────────────────────────────────────────
# Base / Shared
# ───────────────────────────────────────────────


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=4000)
    type: str = Field(..., pattern=r"^(simple|variable)$")


class ProductSimpleFields(BaseModel):
    """Fields that are only meaningful/required for simple products"""

    base_price: Decimal = Field(..., ge=0, description="Required for simple products")
    sku: str = Field(..., min_length=1, max_length=100, description="Tenant-unique SKU")
    stock_quantity: int = Field(0, ge=0)
    re_order_level: int = Field(0, ge=0)


class ProductVariantBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    price: Decimal = Field(..., ge=0)
    stock_quantity: int = Field(0, ge=0)
    re_order_level: int = Field(0, ge=0)
    attributes: Dict[str, str] = Field(
        ..., description="e.g. {'color': 'Red', 'size': 'M', 'ram': '16GB'}"
    )


# ───────────────────────────────────────────────
# Creation
# ───────────────────────────────────────────────


class VariantOptionInput(BaseModel):
    """Used to generate combinations for variable products"""

    options: Dict[str, List[str]] = Field(
        ..., description="e.g. {'color': ['Red', 'Blue'], 'size': ['S', 'M', 'L']}"
    )
    price: Optional[Decimal] = Field(
        None, ge=0, description="Default price for generated variants"
    )
    stock_quantity: int = Field(0, ge=0)
    re_order_level: int = Field(0, ge=0)
    sku_prefix: Optional[str] = Field(
        None, description="Prefix for auto-generated SKUs"
    )


class ProductCreate(ProductBase):
    # Simple product fields (only used when type == "simple")
    simple: Optional[ProductSimpleFields] = None

    # Variable product fields (only used when type == "variable")
    variants: Optional[List[ProductVariantBase]] = Field(
        None, description="Explicit variants (alternative to variant_options)"
    )
    variant_options: Optional[VariantOptionInput] = Field(
        None, description="Generate combinations automatically"
    )

    @model_validator(mode="after")
    def validate_type_compatibility(self):
        if self.type == "simple":
            if self.variants or self.variant_options:
                raise ValueError(
                    "Simple products cannot have variants or variant_options"
                )
            if not self.simple:
                raise ValueError(
                    "Simple products require the 'simple' field with price, sku, etc."
                )
        else:  # variable
            if self.simple:
                raise ValueError("Variable products should not include 'simple' fields")
            has_variants = bool(self.variants)
            has_options = bool(self.variant_options)
            if not (has_variants ^ has_options):  # exactly one
                raise ValueError(
                    "Variable products must provide either 'variants' OR 'variant_options'"
                )
            if has_variants and self.variants is None:
                raise ValueError("Variable products must have at least one variant")
        return self


# ───────────────────────────────────────────────
# Update (partial + variant management)
# ───────────────────────────────────────────────


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=4000)
    type: Optional[str] = Field(None, pattern=r"^(simple|variable)$")

    # Simple product fields (only applied if type is or becomes simple)
    base_price: Optional[Decimal] = Field(None, ge=0)
    sku: Optional[str] = Field(None, min_length=1, max_length=100)
    stock_quantity: Optional[int] = Field(None, ge=0)
    re_order_level: Optional[int] = Field(None, ge=0)

    # Variant management (only meaningful for variable products)
    variants_to_add: Optional[List[ProductVariantBase]] = None
    variants_to_update: Optional[List[Dict[str, Union[str, Decimal, int, Dict]]]] = (
        Field(
            None,
            description="List of dicts: {'id': UUID, 'sku': ..., 'price': ..., ...}",
        )
    )
    variants_to_remove: Optional[List[UUID]] = None  # variant IDs to delete


@field_validator("variants_to_update", mode="before")
def normalize_variant_updates(cls, v):
    if v is None:
        return None
    for item in v:
        if "id" not in item:
            raise ValueError("Each variant update must include 'id'")
    return v


# ───────────────────────────────────────────────
# Output / Response
# ───────────────────────────────────────────────


class ProductVariantOut(ProductVariantBase):
    id: UUID
    product_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductOut(ProductBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime

    # Simple product fields (present only when type == "simple")
    base_price: Optional[Decimal] = None
    sku: Optional[str] = None
    stock_quantity: Optional[int] = None
    re_order_level: Optional[int] = None

    # Variable product field
    variants: Optional[List[ProductVariantOut]] = None

    class Config:
        from_attributes = True


# ───────────────────────────────────────────────
# Storefront linking (unchanged)
# ───────────────────────────────────────────────


class StorefrontProductLink(BaseModel):
    display_order: int = Field(default=0, ge=0)
    is_visible: bool = Field(default=True)


class StorefrontProductLinkUpdate(BaseModel):
    display_order: Optional[int] = None
    is_visible: Optional[bool] = None
