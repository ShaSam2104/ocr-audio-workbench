"""User-related Pydantic schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class LoginSchema(BaseModel):
    """Schema for user login request."""

    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class TokenSchema(BaseModel):
    """Schema for token response."""

    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


class UserSchema(BaseModel):
    """Schema for user response (public data only)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime
