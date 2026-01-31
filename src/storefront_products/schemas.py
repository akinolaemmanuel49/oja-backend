"""
Pydantic schemas for storefront-product relationship operations.
Allows managing which products are visible in which storefronts.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.products.schemas import ProductVariantOut


class StorefrontProductAdd(BaseModel):
    """
    Schema for adding a product to a storefront.
    """

    product_id: UUID
    display_order: int = Field(default=0, ge=0)
    is_visible: bool = Field(default=True)


class StorefrontProductUpdate(BaseModel):
    """
    Schema for updating a product's settings in a storefront.
    """

    display_order: Optional[int] = Field(default=None, ge=0)
    is_visible: Optional[bool] = None


class StorefrontProductOut(BaseModel):
    """
    Schema for representing a product in a storefront context.
    Includes both product details and storefront-specific settings.
    """

    # Product details
    product_id: UUID
    product_name: str
    product_type: str
    product_description: Optional[str] = None
    base_price: Optional[float] = None
    sku: Optional[str] = None
    main_image_url: Optional[str] = None

    # Storefront-specific settings
    display_order: int
    is_visible: bool

    # Variants
    variants: list[ProductVariantOut] = []

    class Config:
        from_attributes = True


class StorefrontProductBulkAdd(BaseModel):
    """
    Schema for adding multiple products to a storefront at once.
    """

    product_ids: List[UUID] = Field(..., min_length=1)
    is_visible: bool = Field(default=True)
