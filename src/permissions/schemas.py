"""
Pydantic schemas for permission-related operations

Permissions for users, groups and roles.
"""

from typing import List, Literal, Union

from pydantic import BaseModel


class PermissionsRequest(BaseModel):
    """
    Schema for requesting permissions for a user, group or role.
    """

    target_type: Union[
        Literal["user"], Literal["group"], Literal["role"]
    ]  # "user", "group", "role"
    target_id: str  # UUID as string
    permission_codes: List[str]


class PermissionRequest(BaseModel):
    """
    Schema for requesting a permission for a user, group or role.
    """

    target_type: Union[
        Literal["user"], Literal["group"], Literal["role"]
    ]  # "user", "group", "role"
    target_id: str  # UUID as string
    permission_code: str
