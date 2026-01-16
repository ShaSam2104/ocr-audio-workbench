"""Chapter management routes - NO user_id filtering (fully shared)."""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.hierarchy import Book, Chapter
from app.models.image import Image
from app.models.audio import Audio
from app.models.ocr import OCRText
from app.models.transcript import AudioTranscript
from app.models.user import User
from app.schemas.hierarchy import (
    ChapterSchema,
    ChapterCreateSchema,
    ChapterUpdateSchema,
    ChapterDetailSchema,
    ImageContentSchema,
    AudioContentSchema,
    ChapterWithContentResponse,
)
from app.schemas.response import MessageResponse
from app.dependencies import get_current_user, get_minio_client
from app.services.minio_service import MinIOService
from app.config import MINIO_IMAGE_BUCKET
from app.logger import logger

router = APIRouter(tags=["chapters"])

# Constants
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


@router.get("/books/{book_id}/chapters", response_model=dict)
async def list_chapters(
    book_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    List all chapters in a book with pagination - NO user_id filtering.

    Args:
        book_id: Book ID
        page: Page number (1-indexed)
        page_size: Items per page
        current_user: Current authenticated user
        db: Database session

    Returns:
        Paginated list of chapters with total count
        
    Raises:
        HTTPException: 404 if book not found
    """
    # Verify book exists
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )

    # Query chapters for this book (NO user_id filtering)
    query = db.query(Chapter).filter(Chapter.book_id == book_id)
    total = query.count()

    # Calculate offset
    offset = (page - 1) * page_size

    # Get paginated results
    chapters = query.offset(offset).limit(page_size).all()

    return {
        "items": [ChapterSchema.model_validate(chapter) for chapter in chapters],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/books/{book_id}/chapters/{chapter_id}", response_model=ChapterWithContentResponse)
async def get_chapter_with_content(
    book_id: int,
    chapter_id: int,
    page: int = Query(1, ge=1, description="Page number for images and audio"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page for images and audio"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minio_service: MinIOService = Depends(get_minio_client),
) -> ChapterWithContentResponse:
    """
    Retrieve chapter details along with paginated images and audio content.

    Returns chapter metadata with:
    - Paginated images in the chapter with their OCR status and text (if extracted)
    - Paginated audio files in the chapter with their transcription status and transcript (if extracted)
    - Content is sorted by sequence_number

    Args:
        book_id: Book ID
        chapter_id: Chapter ID
        page: Page number (1-indexed) for pagination
        page_size: Items per page for pagination
        current_user: Current authenticated user
        db: Database session

    Returns:
        Chapter with paginated images and audio content
        
    Raises:
        HTTPException: 404 if book or chapter not found
    """
    # Verify book exists
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )

    # Verify chapter exists and belongs to this book
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.book_id == book_id,
    ).first()
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found in book {book_id}",
        )

    # Calculate offset for pagination
    offset = (page - 1) * page_size

    # ========== IMAGES PAGINATION ==========
    # Get total image count
    images_query = db.query(Image).filter(Image.chapter_id == chapter_id)
    total_images = images_query.count()

    # Get paginated images, sorted by sequence_number
    images = images_query.order_by(Image.sequence_number).offset(offset).limit(page_size).all()
    
    # Build image content list with OCR text
    images_content = []
    for image in images:
        ocr_text = db.query(OCRText).filter(OCRText.image_id == image.id).first()
        ocr_data = None
        if ocr_text:
            # Use edited text if available, fallback to raw text
            display_text = ocr_text.edited_text_with_formatting or ocr_text.raw_text_with_formatting
            ocr_data = {
                "id": ocr_text.id,
                "image_id": ocr_text.image_id,
                "raw_text_with_formatting": ocr_text.raw_text_with_formatting,
                "edited_text_with_formatting": display_text,
                "model_used": getattr(ocr_text, 'model_used', None),
                "created_at": ocr_text.created_at,
            }
        
        # Generate presigned URL for image (30 mins = 1800 seconds)
        image_url = None
        try:
            image_url = await minio_service.get_presigned_url(
                bucket=MINIO_IMAGE_BUCKET,
                object_key=image.object_key,
                expiration=1800,  # 30 minutes
            )
        except Exception as e:
            logger.warning(f"Failed to generate presigned URL for image {image.id}: {e}")
        
        image_content = ImageContentSchema(
            id=image.id,
            sequence_number=image.sequence_number,
            page_number=image.page_number,
            ocr_status=image.ocr_status,
            image_url=image_url,
            ocr_text=ocr_data,
        )
        images_content.append(image_content)

    # ========== AUDIO PAGINATION ==========
    # Get total audio count
    audios_query = db.query(Audio).filter(Audio.chapter_id == chapter_id)
    total_audios = audios_query.count()

    # Get paginated audio files, sorted by sequence_number
    audios = audios_query.order_by(Audio.sequence_number).offset(offset).limit(page_size).all()
    
    # Build audio content list with transcripts
    audios_content = []
    for audio in audios:
        transcript = db.query(AudioTranscript).filter(AudioTranscript.audio_id == audio.id).first()
        transcript_data = None
        if transcript:
            # Use edited text if available, fallback to raw text
            display_text = transcript.edited_text_with_formatting or transcript.raw_text_with_formatting
            transcript_data = {
                "id": transcript.id,
                "audio_id": transcript.audio_id,
                "raw_text_with_formatting": transcript.raw_text_with_formatting,
                "edited_text_with_formatting": display_text,
                "model_used": getattr(transcript, 'model_used', None),
                "created_at": transcript.created_at,
            }
        
        audio_content = AudioContentSchema(
            id=audio.id,
            sequence_number=audio.sequence_number,
            duration_seconds=audio.duration_seconds,
            audio_format=audio.audio_format,
            transcription_status=audio.transcription_status,
            transcript=transcript_data,
        )
        audios_content.append(audio_content)
    
    # Build and return chapter detail response with pagination metadata
    return ChapterWithContentResponse(
        chapter=ChapterSchema(
            id=chapter.id,
            book_id=chapter.book_id,
            name=chapter.name,
            description=chapter.description,
            sequence_order=chapter.sequence_order,
            created_at=chapter.created_at,
            updated_at=chapter.updated_at,
        ),
        images={
            "items": images_content,
            "total": total_images,
            "page": page,
            "page_size": page_size,
        },
        audios={
            "items": audios_content,
            "total": total_audios,
            "page": page,
            "page_size": page_size,
        },
    )


@router.post("/books/{book_id}/chapters", response_model=ChapterSchema, status_code=status.HTTP_201_CREATED)
async def create_chapter(
    book_id: int,
    request: ChapterCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChapterSchema:
    """
    Create a new chapter under a book - NO user_id assignment.

    Args:
        book_id: Book ID
        request: Chapter creation data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Created chapter
        
    Raises:
        HTTPException: 404 if book not found
    """
    # Verify book exists
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )

    # Create new chapter WITHOUT user_id
    new_chapter = Chapter(
        book_id=book_id,
        name=request.name,
        description=request.description,
        sequence_order=request.sequence_order,
    )

    db.add(new_chapter)
    db.commit()
    db.refresh(new_chapter)

    return ChapterSchema.model_validate(new_chapter)


@router.put("/books/{book_id}/chapters/{chapter_id}", response_model=ChapterSchema)
async def update_chapter(
    book_id: int,
    chapter_id: int,
    request: ChapterUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChapterSchema:
    """
    Update a chapter - NO authorization check (all users can update).

    Args:
        book_id: Book ID
        chapter_id: Chapter ID
        request: Chapter update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated chapter
        
    Raises:
        HTTPException: 404 if book or chapter not found
    """
    # Verify book exists
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )

    # Verify chapter exists and belongs to this book
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.book_id == book_id,
    ).first()
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found in book {book_id}",
        )

    # Update fields if provided
    if request.name is not None:
        chapter.name = request.name
    if request.description is not None:
        chapter.description = request.description
    if request.sequence_order is not None:
        chapter.sequence_order = request.sequence_order

    db.commit()
    db.refresh(chapter)

    return ChapterSchema.model_validate(chapter)


@router.delete("/books/{book_id}/chapters/{chapter_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def delete_chapter(
    book_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    Delete a chapter - cascades to delete images and ocr_texts.

    Args:
        book_id: Book ID
        chapter_id: Chapter ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
        
    Raises:
        HTTPException: 404 if book or chapter not found
    """
    # Verify book exists
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )

    # Verify chapter exists and belongs to this book
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.book_id == book_id,
    ).first()
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found in book {book_id}",
        )

    # Delete chapter (CASCADE will delete images + ocr_texts + audios + transcripts)
    db.delete(chapter)
    db.commit()

    return MessageResponse(message=f"Chapter {chapter_id} deleted successfully")
