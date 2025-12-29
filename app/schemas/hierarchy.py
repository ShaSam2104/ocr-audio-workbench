"""Book and Chapter Pydantic schemas - fully shared across all users."""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class BookCreateSchema(BaseModel):
    """Schema for creating a new book."""

    name: str = Field(..., min_length=1, description="Book name")
    description: Optional[str] = Field(None, description="Book description")


class BookUpdateSchema(BaseModel):
    """Schema for updating a book."""

    name: Optional[str] = Field(None, min_length=1, description="Book name")
    description: Optional[str] = Field(None, description="Book description")


class BookSchema(BaseModel):
    """Schema for book response - NO user_id (fully shared)."""

    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChapterCreateSchema(BaseModel):
    """Schema for creating a new chapter."""

    name: str = Field(..., min_length=1, description="Chapter name")
    description: Optional[str] = Field(None, description="Chapter description")
    sequence_order: Optional[int] = Field(None, description="Sequence order in book")


class ChapterUpdateSchema(BaseModel):
    """Schema for updating a chapter."""

    name: Optional[str] = Field(None, min_length=1, description="Chapter name")
    description: Optional[str] = Field(None, description="Chapter description")
    sequence_order: Optional[int] = Field(None, description="Sequence order in book")


class ChapterSchema(BaseModel):
    """Schema for chapter response."""

    id: int
    book_id: int
    name: str
    description: Optional[str] = None
    sequence_order: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BookDetailSchema(BookSchema):
    """Extended schema for book with chapters."""

    chapters: list[ChapterSchema] = Field(default_factory=list)
