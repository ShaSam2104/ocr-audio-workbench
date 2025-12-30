"""Audio file model - NO user_id (fully shared across all users)."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Audio(Base):
    """Audio model - NO user_id, NO uploader_id (fully shared across all authenticated users)."""

    __tablename__ = "audios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    object_key = Column(String(500), nullable=False)  # Path in MinIO: audio/{chapter_id}/{audio_id}.{ext}
    filename = Column(String(255), nullable=False)
    sequence_number = Column(Integer, nullable=False)  # Per chapter scope
    duration_seconds = Column(Integer, nullable=True)  # Audio duration in seconds
    audio_format = Column(String(50), nullable=True)  # mp3, wav, m4a, ogg, flac
    file_size = Column(Integer, nullable=True)  # Size in bytes
    detected_language = Column(String(50), nullable=True)
    transcription_status = Column(
        String(50), default="pending", nullable=False
    )  # pending, processing, completed, failed
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    chapter = relationship("Chapter", back_populates="audios")
    transcript = relationship("AudioTranscript", uselist=False, back_populates="audio", cascade="all, delete-orphan")

    __table_args__ = (
        # Ensure sequence numbers are unique per chapter
        # (This would be a UNIQUE constraint in the actual SQL)
    )

    def __repr__(self) -> str:
        return f"<Audio(id={self.id}, chapter_id={self.chapter_id}, sequence_number={self.sequence_number})>"
