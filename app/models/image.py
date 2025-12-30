"""Image model - NO user_id (fully shared across all users)."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Image(Base):
    """Image model - NO user_id, NO uploaded_by (fully shared across all authenticated users)."""

    __tablename__ = "images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    object_key = Column(String(500), nullable=False)  # Path in MinIO: images/{chapter_id}/{image_id}.{ext}
    filename = Column(String(255), nullable=False)
    sequence_number = Column(Integer, nullable=False)  # Per chapter scope
    page_number = Column(Integer, nullable=True)  # For PDFs (which page it came from)
    file_size = Column(Integer, nullable=True)  # Size in bytes
    file_hash = Column(String(64), nullable=True)  # SHA256 hash for deduplication
    detected_language = Column(String(50), nullable=True)
    ocr_status = Column(String(50), default="pending", nullable=False)  # pending, processing, completed, failed
    is_cropped = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    chapter = relationship("Chapter", back_populates="images")
    ocr_text = relationship("OCRText", uselist=False, back_populates="image", cascade="all, delete-orphan")

    __table_args__ = (
        # Ensure sequence numbers are unique per chapter
        # (This would be a UNIQUE constraint in the actual SQL)
    )

    def __repr__(self) -> str:
        return f"<Image(id={self.id}, chapter_id={self.chapter_id}, sequence_number={self.sequence_number})>"
