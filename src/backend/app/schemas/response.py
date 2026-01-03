"""Standardized API response schemas for consistent error and success responses."""
from typing import Any, Optional, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """
    Standard success response wrapper.
    
    Usage:
        return SuccessResponse(message="Operation successful", data=result)
    """
    message: str = Field(..., description="Success message")
    data: Optional[Any] = Field(None, description="Response data")


class MessageResponse(BaseModel):
    """Simple message response for operations that don't return data."""
    message: str = Field(..., description="Response message")


class ErrorDetail(BaseModel):
    """Error response detail."""
    detail: str = Field(..., description="Error message")
