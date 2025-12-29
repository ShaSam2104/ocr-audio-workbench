"""User-related Pydantic schemas."""
from pydantic import BaseModel, Field
from datetime import datetime


class LoginSchema(BaseModel):
    """Schema for user login request."""

    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class TokenSchema(BaseModel):
    """Schema for token response."""

    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str

    class Config:
        from_attributes = True


class UserSchema(BaseModel):
    """Schema for user response (public data only)."""

    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True
