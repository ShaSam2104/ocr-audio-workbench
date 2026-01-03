"""Book and Chapter Pydantic schemas - fully shared across all users."""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from typing import Optional, List


class BookCreateSchema(BaseModel):
    """Schema for creating a new book."""

    name: str = Field(..., min_length=1, description="Book name")
    description: Optional[str] = Field(None, description="Book description")
    languages: Optional[List[str]] = Field(None, description="List of language codes (e.g., ['en', 'hi', 'gu'])", min_length=1)


class BookUpdateSchema(BaseModel):
    """Schema for updating a book."""

    name: Optional[str] = Field(None, min_length=1, description="Book name")
    description: Optional[str] = Field(None, description="Book description")
    languages: Optional[List[str]] = Field(None, description="List of language codes (e.g., ['en', 'hi', 'gu'])")


class BookSchema(BaseModel):
    """Schema for book response - NO user_id (fully shared)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    languages: Optional[List[str]] = None  # Parsed from comma-separated string
    created_at: datetime
    updated_at: datetime
    
    @field_validator('languages', mode='before')
    @classmethod
    def parse_languages(cls, v: Optional[str | List[str]]) -> Optional[List[str]]:
        """Convert comma-separated string to list of languages."""
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [lang.strip() for lang in v.split(",") if lang.strip()]
        return None


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

    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    name: str
    description: Optional[str] = None
    sequence_order: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class BookDetailSchema(BookSchema):
    """Extended schema for book with chapters."""

    chapters: list[ChapterSchema] = Field(default_factory=list)
