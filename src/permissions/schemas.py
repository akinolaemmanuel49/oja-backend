from typing import List

from pydantic import BaseModel


class PermissionsRequest(BaseModel):
    target_type: str  # "user", "group", "role"
    target_id: str  # UUID as string
    permission_codes: List[str]


class PermissionRequest(BaseModel):
    target_type: str  # "user", "group", "role"
    target_id: str  # UUID as string
    permission_code: str
