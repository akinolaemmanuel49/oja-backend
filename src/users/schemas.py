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


class UserUpdate(BaseModel):
    """Schema for updating user information."""

    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)

    class Config:
        extra = "forbid"  # Prevent extra fields


class UserPermissionOut(BaseModel):
    """
    Schema for a permission assigned to a user.
    """

    id: UUID
    code: str
    name: str
    resource: str
    action: str
    description: Optional[str]
    granted_at: datetime  # When it was granted to the user

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )


class GrantPermissionsToUserRequest(BaseModel):
    """
    Request schema for granting permissions to a user.

    User will be assigned these permissions.
    """

    permission_codes: list[str] = Field(
        ...,
        description="List of permission codes to grant (e.g., ['users:read', 'products:*'])",
    )


class RevokePermissionsFromUserRequest(BaseModel):
    """
    Request schema for revoking permissions from a user.

    Users will lose these permissions (unless they have them as part of a group).
    """

    permission_codes: list[str] = Field(
        ...,
        description="List of permission codes to revoke (e.g., ['users:read', 'products:*'])",
    )


class AddUserToGroupRequest(BaseModel):
    """
    Request schema for adding a user to a group.

    User will be added to this group.
    """

    group_id: UUID = Field(
        ...,
        description="ID of the group to add the user to",
    )


class RemoveUserFromGroupRequest(BaseModel):
    """
    Request schema for removing a user from a group.

    User will be removed from this group.
    """

    group_id: UUID = Field(
        ...,
        description="ID of the group to remove the user from",
    )
