"""
Pydantic schemas for group-related operations.

Groups allow organizing users and assigning permissions at the group level.
When a user is added to a group, they inherit all permissions assigned to that group.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    """
    Schema for creating a new group.

    Group names must be unique within a tenant.
    """

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class GroupUpdate(BaseModel):
    """
    Schema for updating an existing group.

    All fields are optional - only provided fields will be updated.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class GroupOut(BaseModel):
    """
    Schema for group output (basic info, no members or permissions).

    Used in list views where we don't need to load full group details.
    """

    id: UUID
    tenant_id: UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )


class GroupMemberOut(BaseModel):
    """
    Schema for a group member (user in a group).

    Used when listing members of a group.
    """

    id: UUID
    email: str
    first_name: str
    last_name: str
    full_name: Optional[str]
    is_active: bool
    added_at: datetime  # When they were added to the group

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )


class GroupPermissionOut(BaseModel):
    """
    Schema for a permission assigned to a group.
    """

    id: UUID
    code: str
    name: str
    resource: str
    action: str
    description: Optional[str]
    granted_at: datetime  # When it was granted to the group

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )


class GroupDetailOut(BaseModel):
    """
    Schema for detailed group info including members and permissions.

    Used when viewing a single group's details.
    """

    id: UUID
    tenant_id: UUID
    name: str
    description: Optional[str]
    member_count: int
    permission_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )


class AddUsersToGroupRequest(BaseModel):
    """
    Request schema for adding users to a group.
    """

    user_ids: List[UUID]


class RemoveUsersFromGroupRequest(BaseModel):
    """
    Request schema for removing users from a group.
    """

    user_ids: List[UUID]


class GrantPermissionsToGroupRequest(BaseModel):
    """
    Request schema for granting permissions to a group.

    All members of the group will inherit these permissions.
    """

    permission_codes: list[str] = Field(
        ...,
        description="List of permission codes to grant (e.g., ['users:read', 'products:*'])",
    )


class RevokePermissionsFromGroupRequest(BaseModel):
    """
    Request schema for revoking permissions from a group.

    All members of the group will lose these permissions (unless they have them directly).
    """

    permission_codes: list[str] = Field(
        ...,
        description="List of permission codes to revoke (e.g., ['users:read', 'products:*'])",
    )
