"""OCR Text model - NO user tracking (fully shared across all users)."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class OCRText(Base):
    """OCRText model - NO extracted_by, NO extracted_at (uses created_at instead)."""

    __tablename__ = "ocr_texts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False, unique=True)
    raw_text_with_formatting = Column(Text, nullable=False)  # Text with markdown tags (**bold**, *italic*, etc.)
    plain_text_for_search = Column(Text, nullable=False)  # Plain text without tags (for FTS5 indexing)
    detected_language = Column(String(50), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)  # Time Gemini took to extract
    model_used = Column(String(50), nullable=True)  # Which model was used (e.g., 'gemini-3.0-flash', 'gemini-2.5-pro')
    created_at = Column(DateTime, default=func.now(), nullable=False)
    # Manual edit columns - store user-corrected text separately
    edited_text_with_formatting = Column(Text, nullable=True)  # User-edited text with markdown formatting
    edited_plain_text = Column(Text, nullable=True)  # User-edited plain text (for search)
    edited_at = Column(DateTime, nullable=True)  # When user last edited the text

    # Relationships
    image = relationship("Image", back_populates="ocr_text")

    def __repr__(self) -> str:
        return f"<OCRText(id={self.id}, image_id={self.image_id})>"
