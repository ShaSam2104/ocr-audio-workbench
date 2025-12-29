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
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    image = relationship("Image", back_populates="ocr_text")

    def __repr__(self) -> str:
        return f"<OCRText(id={self.id}, image_id={self.image_id})>"
