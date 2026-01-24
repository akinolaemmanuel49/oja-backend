"""
Pydantic schemas for the authentication-related operations.

Authentication allows users to log in and access protected resources. Users can log in using their email and password, and the provided schemas define the structure of the login request.
"""

from pydantic import BaseModel, EmailStr


class Login(BaseModel):
    """
    Schema for logging in a user.
    """

    email: EmailStr
    password: str
