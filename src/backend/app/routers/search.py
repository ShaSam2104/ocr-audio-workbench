"""Search endpoints - NO user scoping (all authenticated users see all results)."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, or_, and_
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List

from app.database import get_db
from app.dependencies import get_current_user, get_minio_client
from app.models.user import User
from app.services.minio_service import MinIOService
from app.config import MINIO_IMAGE_BUCKET, MINIO_AUDIO_BUCKET
from app.models.hierarchy import Book, Chapter
from app.models.image import Image
from app.models.audio import Audio
from app.models.ocr import OCRText
from app.models.transcript import AudioTranscript
from app.schemas.image import ImageSchema
from app.schemas.audio import AudioSchema
from app.logger import logger

router = APIRouter(prefix="/search", tags=["search"])


# ============================================================================
# SCHEMAS
# ============================================================================


class ImageSearchResult(BaseModel):
    """Search result for image with excerpt and signed URL."""

    model_config = ConfigDict(from_attributes=True)

    image: ImageSchema
    excerpt: str = Field(..., description="Text excerpt from OCR (first 200 chars)")
    image_url: Optional[str] = Field(None, description="Presigned URL for image access (30 mins)")


class AudioSearchResult(BaseModel):
    """Search result for audio with excerpt and signed URL."""

    model_config = ConfigDict(from_attributes=True)

    audio: AudioSchema
    excerpt: str = Field(..., description="Text excerpt from transcript (first 200 chars)")
    audio_url: Optional[str] = Field(None, description="Presigned URL for audio access (30 mins)")


class CombinedSearchResult(BaseModel):
    """Combined search result (image or audio)."""

    type: str = Field(..., description="'image' or 'audio'")
    image: Optional[ImageSchema] = None
    audio: Optional[AudioSchema] = None
    excerpt: str = Field(..., description="Text excerpt (first 200 chars)")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _parse_number_query(query: str) -> List[int]:
    """
    Parse number query like "5" or "5-10" into list of numbers.

    Args:
        query: Query string (e.g., "5" or "5-10")

    Returns:
        List of sequence numbers matching query
    """
    try:
        if "-" in query:
            parts = query.split("-")
            if len(parts) != 2:
                raise ValueError("Invalid range format")
            start = int(parts[0].strip())
            end = int(parts[1].strip())
            if start > end:
                raise ValueError("Start must be <= end")
            return list(range(start, end + 1))
        else:
            return [int(query.strip())]
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid number query: {query}") from e


def _get_excerpt(text: str, max_length: int = 200) -> str:
    """
    Extract excerpt from text, truncating if needed.

    Args:
        text: Full text
        max_length: Maximum excerpt length

    Returns:
        Excerpt text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


# ============================================================================
# ENDPOINTS: Number-Based Search (Sequence Numbers)
# ============================================================================


@router.get("/images", response_model=List[ImageSchema])
async def search_images_by_number(
    chapter_id: int = Query(..., description="Chapter ID"),
    query: str = Query(..., description="Image number or range (e.g., '5' or '5-10')"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Search images by sequence number within a chapter.

    Supports exact number or range (e.g., "5" or "5-10").
    NO user filtering - all authenticated users see all images.

    Args:
        chapter_id: Chapter ID
        query: Image number or range
        current_user: Authenticated user
        db: Database session

    Returns:
        List of ImageSchema matching the query
        404 if chapter not found
    """
    logger.debug(f"Searching images in chapter {chapter_id} with query '{query}'")

    # Verify chapter exists
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        logger.warning(f"Chapter {chapter_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter {chapter_id} not found",
        )

    # Parse number query
    try:
        sequence_numbers = _parse_number_query(query)
    except ValueError as e:
        logger.warning(f"Invalid query format: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Query images by sequence number in chapter
    images = (
        db.query(Image)
        .filter(Image.chapter_id == chapter_id, Image.sequence_number.in_(sequence_numbers))
        .order_by(Image.sequence_number)
        .all()
    )

    logger.debug(f"Found {len(images)} images matching query in chapter {chapter_id}")
    return [ImageSchema.model_validate(img) for img in images]


@router.get("/audios", response_model=List[AudioSchema])
async def search_audios_by_number(
    chapter_id: int = Query(..., description="Chapter ID"),
    query: str = Query(..., description="Audio number or range (e.g., '5' or '5-10')"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Search audios by sequence number within a chapter.

    Supports exact number or range (e.g., "5" or "5-10").
    NO user filtering - all authenticated users see all audios.

    Args:
        chapter_id: Chapter ID
        query: Audio number or range
        current_user: Authenticated user
        db: Database session

    Returns:
        List of AudioSchema matching the query
        404 if chapter not found
    """
    logger.debug(f"Searching audios in chapter {chapter_id} with query '{query}'")

    # Verify chapter exists
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        logger.warning(f"Chapter {chapter_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter {chapter_id} not found",
        )

    # Parse number query
    try:
        sequence_numbers = _parse_number_query(query)
    except ValueError as e:
        logger.warning(f"Invalid query format: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Query audios by sequence number in chapter
    audios = (
        db.query(Audio)
        .filter(Audio.chapter_id == chapter_id, Audio.sequence_number.in_(sequence_numbers))
        .order_by(Audio.sequence_number)
        .all()
    )

    logger.debug(f"Found {len(audios)} audios matching query in chapter {chapter_id}")
    return [AudioSchema.model_validate(audio) for audio in audios]


# ============================================================================
# ENDPOINTS: Text Search (FTS5)
# ============================================================================


@router.get("/images/text", response_model=List[ImageSearchResult])
async def search_images_by_text(
    text_query: str = Query(..., description="Text to search in OCR (FTS5 full-text search)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
):
    """
    Search OCR text of images globally across all books and chapters using FTS5.

    Uses FTS5 (Full-Text Search 5) for fast, efficient searching.
    Supports phrase queries, AND/OR operators, and proximity search.
    NO user filtering - all authenticated users see all results.
    Includes presigned URLs for image access (valid for 30 minutes).

    Args:
        text_query: Text to search (supports FTS5 syntax)
        current_user: Authenticated user
        db: Database session
        minio_service: MinIO service for generating signed URLs

    Returns:
        List of image search results with text excerpts and signed URLs from all chapters/books
    """
    logger.debug(f"FTS5 searching images for '{text_query}'")

    try:
        # Use raw SQL for FTS5 MATCH operator
        # Escape single quotes in the query
        escaped_query = text_query.replace("'", "''")
        
        # Query OCR texts using FTS5
        # Create subquery to search FTS5 virtual table
        fts_subquery = db.query(text(f"ocr_texts_fts.rowid")).select_from(
            text(f"ocr_texts_fts WHERE ocr_texts_fts MATCH '{escaped_query}'")
        ).subquery()
        
        ocr_texts = (
            db.query(OCRText, Image)
            .join(Image, OCRText.image_id == Image.id)
            .filter(OCRText.id.in_(db.query(fts_subquery.c.rowid)))
            .order_by(Image.created_at.desc())
            .all()
        )
    except Exception as e:
        # Fallback to ILIKE if FTS5 fails (e.g., syntax error or virtual table not available)
        logger.warning(f"FTS5 search failed ({e}). Falling back to ILIKE search.")
        ocr_texts = (
            db.query(OCRText, Image)
            .join(Image, OCRText.image_id == Image.id)
            .filter(
                or_(
                    OCRText.plain_text_for_search.ilike(f"%{text_query}%"),
                    OCRText.edited_plain_text.ilike(f"%{text_query}%")
                )
            )
            .order_by(Image.created_at.desc())
            .all()
        )

    results = []
    for ocr_text, img in ocr_texts:
        # Generate presigned URL for image (30 mins = 1800 seconds)
        image_url = None
        try:
            image_url = await minio_service.get_presigned_url(
                bucket=MINIO_IMAGE_BUCKET,
                object_key=img.object_key,
                expiration=1800,  # 30 minutes
            )
        except Exception as e:
            logger.warning(f"Failed to generate presigned URL for image {img.id}: {e}")
            # Don't fail the request, just skip the URL
        
        results.append(
            ImageSearchResult(
                image=ImageSchema.model_validate(img),
                excerpt=_get_excerpt(ocr_text.edited_plain_text or ocr_text.plain_text_for_search),
                image_url=image_url,
            )
        )

    logger.debug(f"Found {len(results)} images matching FTS5 query globally")
    return results


@router.get("/audios/text", response_model=List[AudioSearchResult])
async def search_audios_by_text(
    text_query: str = Query(..., description="Text to search in transcriptions (FTS5 full-text search)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
):
    """
    Search transcription text of audios globally across all books and chapters using FTS5.

    Uses FTS5 (Full-Text Search 5) for fast, efficient searching.
    Supports phrase queries, AND/OR operators, and proximity search.
    NO user filtering - all authenticated users see all results.
    Includes presigned URLs for audio access (valid for 30 minutes).

    Args:
        text_query: Text to search (supports FTS5 syntax)
        current_user: Authenticated user
        db: Database session
        minio_service: MinIO service for generating signed URLs

    Returns:
        List of audio search results with text excerpts and signed URLs from all chapters/books
    """
    logger.debug(f"FTS5 searching audios for '{text_query}'")

    try:
        # Use raw SQL for FTS5 MATCH operator
        # Escape single quotes in the query
        escaped_query = text_query.replace("'", "''")
        
        # Query transcripts using FTS5
        # Create subquery to search FTS5 virtual table
        fts_subquery = db.query(text(f"audio_transcripts_fts.rowid")).select_from(
            text(f"audio_transcripts_fts WHERE audio_transcripts_fts MATCH '{escaped_query}'")
        ).subquery()
        
        transcripts = (
            db.query(AudioTranscript, Audio)
            .join(Audio, AudioTranscript.audio_id == Audio.id)
            .filter(AudioTranscript.id.in_(db.query(fts_subquery.c.rowid)))
            .order_by(Audio.created_at.desc())
            .all()
        )
    except Exception as e:
        # Fallback to ILIKE if FTS5 fails (e.g., syntax error or virtual table not available)
        logger.warning(f"FTS5 search failed ({e}). Falling back to ILIKE search.")
        transcripts = (
            db.query(AudioTranscript, Audio)
            .join(Audio, AudioTranscript.audio_id == Audio.id)
            .filter(
                or_(
                    AudioTranscript.plain_text_for_search.ilike(f"%{text_query}%"),
                    AudioTranscript.edited_plain_text.ilike(f"%{text_query}%")
                )
            )
            .order_by(Audio.created_at.desc())
            .all()
        )

    results = []
    for transcript, audio in transcripts:
        # Generate presigned URL for audio (30 mins = 1800 seconds)
        audio_url = None
        try:
            audio_url = await minio_service.get_presigned_url(
                bucket=MINIO_AUDIO_BUCKET,
                object_key=audio.object_key,
                expiration=1800,  # 30 minutes
            )
        except Exception as e:
            logger.warning(f"Failed to generate presigned URL for audio {audio.id}: {e}")
            # Don't fail the request, just skip the URL
        
        results.append(
            AudioSearchResult(
                audio=AudioSchema.model_validate(audio),
                excerpt=_get_excerpt(transcript.edited_plain_text or transcript.plain_text_for_search),
                audio_url=audio_url,
            )
        )

    logger.debug(f"Found {len(results)} audios matching FTS5 query globally")
    return results


# ============================================================================
# ENDPOINTS: Combined Search (Images + Audios)
# ============================================================================


@router.get("/chapter", response_model=List[CombinedSearchResult])
async def search_chapter(
    chapter_id: int = Query(..., description="Chapter ID"),
    text_query: str = Query(..., description="Text to search in OCR and transcriptions"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Search across all images and audios in a chapter.

    Combines image OCR text and audio transcriptions in single result set.
    Results ordered by sequence number.
    NO user filtering - all authenticated users see all results.

    Args:
        chapter_id: Chapter ID
        text_query: Text to search
        current_user: Authenticated user
        db: Database session

    Returns:
        List of combined search results (images and audios)
        404 if chapter not found
    """
    logger.debug(f"Combined search in chapter {chapter_id} for '{text_query}'")

    # Verify chapter exists
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        logger.warning(f"Chapter {chapter_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter {chapter_id} not found",
        )

    results = []

    # Search images
    ocr_texts = (
        db.query(OCRText, Image)
        .join(Image, OCRText.image_id == Image.id)
        .filter(
            Image.chapter_id == chapter_id,
            OCRText.plain_text_for_search.ilike(f"%{text_query}%"),
        )
        .all()
    )

    for ocr_text, img in ocr_texts:
        results.append(
            CombinedSearchResult(
                type="image",
                image=ImageSchema.model_validate(img),
                excerpt=_get_excerpt(ocr_text.plain_text_for_search),
            )
        )

    # Search audios
    transcripts = (
        db.query(AudioTranscript, Audio)
        .join(Audio, AudioTranscript.audio_id == Audio.id)
        .filter(
            Audio.chapter_id == chapter_id,
            AudioTranscript.plain_text_for_search.ilike(f"%{text_query}%"),
        )
        .all()
    )

    for transcript, audio in transcripts:
        results.append(
            CombinedSearchResult(
                type="audio",
                audio=AudioSchema.model_validate(audio),
                excerpt=_get_excerpt(transcript.plain_text_for_search),
            )
        )

    # Sort by sequence number (images and audios have their own sequences)
    results.sort(
        key=lambda x: (
            0 if x.type == "image" else 1,
            x.image.sequence_number if x.type == "image" else x.audio.sequence_number,
        )
    )

    logger.debug(f"Combined search found {len(results)} results in chapter {chapter_id}")
    return results


@router.get("/book", response_model=List[CombinedSearchResult])
async def search_book(
    book_id: int = Query(..., description="Book ID"),
    text_query: str = Query(..., description="Text to search in OCR and transcriptions"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Search across all images and audios in a book (all chapters).

    Combines image OCR text and audio transcriptions across all chapters.
    Results grouped by chapter and sequence.
    NO user filtering - all authenticated users see all results.

    Args:
        book_id: Book ID
        text_query: Text to search
        current_user: Authenticated user
        db: Database session

    Returns:
        List of combined search results (images and audios from all chapters)
        404 if book not found
    """
    logger.debug(f"Combined search in book {book_id} for '{text_query}'")

    # Verify book exists
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        logger.warning(f"Book {book_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book {book_id} not found",
        )

    results = []

    # Get all chapters in book
    chapters = db.query(Chapter).filter(Chapter.book_id == book_id).all()
    chapter_ids = [c.id for c in chapters]

    if not chapter_ids:
        logger.debug(f"Book {book_id} has no chapters")
        return results

    # Search images in all chapters
    ocr_texts = (
        db.query(OCRText, Image, Chapter)
        .join(Image, OCRText.image_id == Image.id)
        .join(Chapter, Image.chapter_id == Chapter.id)
        .filter(
            Chapter.id.in_(chapter_ids),
            OCRText.plain_text_for_search.ilike(f"%{text_query}%"),
        )
        .all()
    )

    for ocr_text, img, chapter in ocr_texts:
        results.append(
            CombinedSearchResult(
                type="image",
                image=ImageSchema.model_validate(img),
                excerpt=_get_excerpt(ocr_text.plain_text_for_search),
            )
        )

    # Search audios in all chapters
    transcripts = (
        db.query(AudioTranscript, Audio, Chapter)
        .join(Audio, AudioTranscript.audio_id == Audio.id)
        .join(Chapter, Audio.chapter_id == Chapter.id)
        .filter(
            Chapter.id.in_(chapter_ids),
            AudioTranscript.plain_text_for_search.ilike(f"%{text_query}%"),
        )
        .all()
    )

    for transcript, audio, chapter in transcripts:
        results.append(
            CombinedSearchResult(
                type="audio",
                audio=AudioSchema.model_validate(audio),
                excerpt=_get_excerpt(transcript.plain_text_for_search),
            )
        )

    # Sort by chapter and sequence
    results.sort(
        key=lambda x: (
            x.image.chapter_id if x.type == "image" else x.audio.chapter_id,
            0 if x.type == "image" else 1,
            x.image.sequence_number if x.type == "image" else x.audio.sequence_number,
        )
    )

    logger.debug(f"Combined search found {len(results)} results in book {book_id}")
    return results


@router.get("/global", response_model=List[CombinedSearchResult])
async def search_global(
    text_query: str = Query(..., description="Text to search in all OCR and transcriptions"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Global search across all images and audios in all books.

    Searches all OCR text and all audio transcriptions.
    Results grouped by book and chapter.
    NO user filtering - all authenticated users see all results.

    Args:
        text_query: Text to search
        current_user: Authenticated user
        db: Database session

    Returns:
        List of combined search results (all matching resources)
    """
    logger.debug(f"Global search for '{text_query}'")

    results = []

    # Search all images
    ocr_texts = (
        db.query(OCRText, Image, Chapter, Book)
        .join(Image, OCRText.image_id == Image.id)
        .join(Chapter, Image.chapter_id == Chapter.id)
        .join(Book, Chapter.book_id == Book.id)
        .filter(OCRText.plain_text_for_search.ilike(f"%{text_query}%"))
        .all()
    )

    for ocr_text, img, chapter, book in ocr_texts:
        results.append(
            CombinedSearchResult(
                type="image",
                image=ImageSchema.model_validate(img),
                excerpt=_get_excerpt(ocr_text.plain_text_for_search),
            )
        )

    # Search all audios
    transcripts = (
        db.query(AudioTranscript, Audio, Chapter, Book)
        .join(Audio, AudioTranscript.audio_id == Audio.id)
        .join(Chapter, Audio.chapter_id == Chapter.id)
        .join(Book, Chapter.book_id == Book.id)
        .filter(AudioTranscript.plain_text_for_search.ilike(f"%{text_query}%"))
        .all()
    )

    for transcript, audio, chapter, book in transcripts:
        results.append(
            CombinedSearchResult(
                type="audio",
                audio=AudioSchema.model_validate(audio),
                excerpt=_get_excerpt(transcript.plain_text_for_search),
            )
        )

    # Sort by book, chapter, and sequence
    results.sort(
        key=lambda x: (
            x.image.chapter_id if x.type == "image" else x.audio.chapter_id,
            0 if x.type == "image" else 1,
            x.image.sequence_number if x.type == "image" else x.audio.sequence_number,
        )
    )

    logger.debug(f"Global search found {len(results)} results")
    return results
