"""Audio Transcript model - NO user tracking (fully shared across all users)."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class AudioTranscript(Base):
    """AudioTranscript model - NO extracted_by, NO extracted_at (uses created_at instead)."""

    __tablename__ = "audio_transcripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_id = Column(Integer, ForeignKey("audios.id", ondelete="CASCADE"), nullable=False, unique=True)
    raw_text_with_formatting = Column(Text, nullable=False)  # Text with markdown tags (**bold**, *italic*, etc.)
    plain_text_for_search = Column(Text, nullable=False)  # Plain text without tags (for FTS5 indexing)
    detected_language = Column(String(50), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)  # Time Gemini took to transcribe
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    audio = relationship("Audio", back_populates="transcript")

    def __repr__(self) -> str:
        return f"<AudioTranscript(id={self.id}, audio_id={self.audio_id})>"
