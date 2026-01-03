"""Chapter management routes - NO user_id filtering (fully shared)."""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.hierarchy import Book, Chapter
from app.models.user import User
from app.schemas.hierarchy import (
    ChapterSchema,
    ChapterCreateSchema,
    ChapterUpdateSchema,
)
from app.schemas.response import MessageResponse
from app.dependencies import get_current_user

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
