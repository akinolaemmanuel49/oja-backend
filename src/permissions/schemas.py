from typing import List

from pydantic import BaseModel


class GrantPermissionsRequest(BaseModel):
    target_type: str  # "user", "group", "role"
    target_id: str  # UUID as string
    permission_codes: List[str]


class GrantPermissionRequest(BaseModel):
    target_type: str  # "user", "group", "role"
    target_id: str  # UUID as string
    permission_code: str
