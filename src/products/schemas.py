"""
Pydantic schemas for product-related operations.
Supports simple and variable products with layered variant generation.
Includes image URL management and optional storefront linking.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# ───────────────────────────────────────────────
# Base / Shared
# ───────────────────────────────────────────────
class ProductBase(BaseModel):
    """Base product fields shared across create/update/output schemas."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=4000)
    type: str = Field(..., pattern=r"^(simple|variable)$")
    main_image_url: Optional[HttpUrl] = Field(
        None, description="Primary product image URL (Cloudinary, etc.)"
    )
    image_urls: Optional[List[HttpUrl]] = Field(
        None, description="Additional product images (Cloudinary, etc.)"
    )


class ProductSimpleFields(BaseModel):
    """Fields that are only meaningful/required for simple products."""

    base_price: Decimal = Field(..., ge=0, description="Required for simple products")
    sku: str = Field(..., min_length=1, max_length=100, description="Tenant-unique SKU")
    stock_quantity: int = Field(0, ge=0)
    re_order_level: int = Field(0, ge=0)


class ProductVariantBase(BaseModel):
    """Base variant fields for variable products."""

    sku: str = Field(..., min_length=1, max_length=100)
    price: Decimal = Field(..., ge=0)
    stock_quantity: int = Field(0, ge=0)
    re_order_level: int = Field(0, ge=0)
    attributes: Dict[str, str] = Field(
        ..., description="e.g. {'color': 'Red', 'size': 'M', 'ram': '16GB'}"
    )
    main_image_url: Optional[HttpUrl] = Field(
        None, description="Primary variant image URL (Cloudinary, etc.)"
    )
    image_urls: Optional[List[HttpUrl]] = Field(
        None, description="Additional variant images (Cloudinary, etc.)"
    )


# ───────────────────────────────────────────────
# Creation
# ───────────────────────────────────────────────
class VariantOptionInput(BaseModel):
    """
    Used to generate combinations for variable products via Cartesian product.

    Example: options={'color': ['Red', 'Blue'], 'size': ['S', 'M']}
    Generates 4 variants: Red-S, Red-M, Blue-S, Blue-M
    """

    options: Dict[str, List[str]] = Field(
        ..., description="e.g. {'color': ['Red', 'Blue'], 'size': ['S', 'M', 'L']}"
    )
    price: Optional[Decimal] = Field(
        None, ge=0, description="Default price for generated variants"
    )
    stock_quantity: int = Field(0, ge=0)
    re_order_level: int = Field(0, ge=0)
    sku_prefix: Optional[str] = Field(
        None, description="Prefix for auto-generated SKUs (e.g., 'TSHIRT')"
    )


class ProductCreate(ProductBase):
    """
    Product creation schema.

    For simple products: provide 'simple' field with pricing/SKU info
    For variable products: provide either 'variants' (explicit) OR 'variant_options' (auto-generated)
    """

    # Simple product fields (only used when type == "simple")
    simple: Optional[ProductSimpleFields] = None

    # Variable product fields (only used when type == "variable")
    variants: Optional[List[ProductVariantBase]] = Field(
        None, description="Explicit variants (alternative to variant_options)"
    )
    variant_options: Optional[VariantOptionInput] = Field(
        None, description="Generate combinations automatically"
    )

    # Optional storefront assignment during creation
    storefront_id: Optional[UUID] = Field(
        None,
        description="Optional: Link product to this storefront immediately after creation",
    )

    @model_validator(mode="after")
    def validate_type_compatibility(self) -> "ProductCreate":
        """
        Enforce type-specific field requirements.

        Simple products:
        - MUST have 'simple' field
        - CANNOT have 'variants' or 'variant_options'

        Variable products:
        - MUST have EITHER 'variants' OR 'variant_options' (XOR, not both)
        - CANNOT have 'simple' field
        """
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
            # XOR: exactly one must be true
            if not (has_variants ^ has_options):
                raise ValueError(
                    "Variable products must provide either 'variants' OR 'variant_options' (not both, not neither)"
                )
            if has_variants and self.variants is None:
                raise ValueError("Variable products must have at least one variant")
        return self


# ───────────────────────────────────────────────
# Update (partial + variant management)
# ───────────────────────────────────────────────
class ProductUpdate(BaseModel):
    """
    Partial product update schema.

    Supports:
    - Basic field updates (name, description, images, etc.)
    - Type switching (simple ↔ variable with data migration)
    - Variant management (add/update/remove for variable products)
    """

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=4000)
    type: Optional[str] = Field(None, pattern=r"^(simple|variable)$")
    main_image_url: Optional[HttpUrl] = None
    image_urls: Optional[List[HttpUrl]] = None

    # Simple product fields (only applied if type is or becomes simple)
    base_price: Optional[Decimal] = Field(None, ge=0)
    sku: Optional[str] = Field(None, min_length=1, max_length=100)
    stock_quantity: Optional[int] = Field(None, ge=0)
    re_order_level: Optional[int] = Field(None, ge=0)

    # Variant management (only meaningful for variable products)
    variants_to_add: Optional[List[ProductVariantBase]] = None
    variants_to_update: Optional[
        List[
            Dict[str, Union[str, Decimal, int, Dict[str, str], HttpUrl, List[HttpUrl]]]
        ]
    ] = Field(
        None,
        description="List of dicts with 'id' (UUID) + fields to update (e.g., {'id': UUID, 'sku': ..., 'price': ..., 'main_image_url': ...})",
    )
    variants_to_remove: Optional[List[UUID]] = None  # variant IDs to delete

    @field_validator("variants_to_update", mode="before")
    @classmethod
    def normalize_variant_updates(
        cls, v: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        """Ensure each variant update dict includes 'id' field."""
        if v is None:
            return None
        for item in v:
            if "id" not in item:
                raise ValueError("Each variant update must include 'id' field")
        return v


# ───────────────────────────────────────────────
# Output / Response
# ───────────────────────────────────────────────
class ProductVariantOut(ProductVariantBase):
    """Variant output schema with database fields."""

    id: UUID
    product_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductOut(ProductBase):
    """Product output schema with all database fields."""

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
# Storefront linking
# ───────────────────────────────────────────────
class StorefrontProductLink(BaseModel):
    """Schema for linking a product to a storefront."""

    display_order: int = Field(default=0, ge=0, description="Sort order in storefront")
    is_visible: bool = Field(default=True, description="Visibility toggle")


class StorefrontProductLinkUpdate(BaseModel):
    """Schema for updating storefront-product link metadata."""

    display_order: Optional[int] = Field(None, ge=0)
    is_visible: Optional[bool] = None
