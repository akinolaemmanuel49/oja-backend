"""
Pydantic schemas for the user-related operations.

Users are the primary entities in the system, and these schemas define the structure of the user data.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """
    Schema for creating a new user.
    """

    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: str
    last_name: str


class UserOut(BaseModel):
    """
    Schema for representing a user.
    """

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    full_name: Optional[str]
    is_active: bool
    tenant_id: Optional[UUID]
    is_root: Optional[bool]
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )


class UserWithPermissions(BaseModel):
    """
    Schema for representing a user with their permissions.
    """

    user: UserOut
    permissions: List[str]

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )
