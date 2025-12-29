"""Book and Chapter models - shared across all users."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Book(Base):
    """Book model - NO user_id (fully shared across all authenticated users)."""

    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    chapters = relationship("Chapter", back_populates="book", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Book(id={self.id}, name='{self.name}')>"


class Chapter(Base):
    """Chapter model - part of a Book, NO user_id (inherited shared access)."""

    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sequence_order = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    book = relationship("Book", back_populates="chapters")
    images = relationship("Image", back_populates="chapter", cascade="all, delete-orphan")
    audios = relationship("Audio", back_populates="chapter", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Chapter(id={self.id}, book_id={self.book_id}, name='{self.name}')>"
