"""Book management routes - NO user_id filtering (fully shared)."""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.hierarchy import Book, Chapter
from app.models.user import User
from app.schemas.hierarchy import (
    BookCreateSchema,
    BookUpdateSchema,
    BookSchema,
    BookDetailSchema,
    ChapterSchema,
    ChapterCreateSchema,
    ChapterUpdateSchema,
)
from app.schemas.response import MessageResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/books", tags=["books"])

# Constants
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


@router.get("", response_model=dict)
async def list_books(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    List all books with pagination - NO user_id filtering (all books visible).

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        current_user: Current authenticated user
        db: Database session

    Returns:
        Paginated list of books with total count
    """
    # Query all books (NO user_id filtering)
    query = db.query(Book)
    total = query.count()

    # Calculate offset
    offset = (page - 1) * page_size

    # Get paginated results
    books = query.offset(offset).limit(page_size).all()

    return {
        "items": [BookSchema.model_validate(book) for book in books],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", response_model=BookSchema, status_code=status.HTTP_201_CREATED)
async def create_book(
    request: BookCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BookSchema:
    """
    Create a new book - NO user_id assignment (shared across all users).

    Args:
        request: Book creation data (name, description, languages)
        current_user: Current authenticated user
        db: Database session

    Returns:
        Created book
    """
    # Convert languages list to comma-separated string
    languages_str = None
    if request.languages:
        languages_str = ",".join(request.languages)
    
    # Create new book WITHOUT user_id
    new_book = Book(
        name=request.name,
        description=request.description,
        languages=languages_str,
    )

    db.add(new_book)
    db.commit()
    db.refresh(new_book)

    return BookSchema.model_validate(new_book)


@router.get("/{book_id}", response_model=BookDetailSchema)
async def get_book(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BookDetailSchema:
    """
    Get a specific book with all chapters - NO authorization check.

    Args:
        book_id: Book ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Book with chapters

    Raises:
        HTTPException: 404 if book not found
    """
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )

    return BookDetailSchema.model_validate(book)


@router.put("/{book_id}", response_model=BookSchema)
async def update_book(
    book_id: int,
    request: BookUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BookSchema:
    """
    Update a book - NO authorization check (all users can edit).

    Args:
        book_id: Book ID
        request: Book update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated book

    Raises:
        HTTPException: 404 if book not found
    """
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )

    # Update fields if provided
    if request.name is not None:
        book.name = request.name
    if request.description is not None:
        book.description = request.description

    db.commit()
    db.refresh(book)

    return BookSchema.model_validate(book)


@router.delete("/{book_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def delete_book(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    Delete a book - NO authorization check (all users can delete).

    Args:
        book_id: Book ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Confirmation message

    Raises:
        HTTPException: 404 if book not found
    """
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found",
        )

    db.delete(book)
    db.commit()

    return MessageResponse(message=f"Book {book_id} deleted successfully")


# ============================================================================
# Chapter endpoints (nested under books)
# ============================================================================


@router.get("/{book_id}/chapters", response_model=dict)
async def list_chapters(
    book_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    List all chapters in a book with pagination.

    Args:
        book_id: Book ID
        page: Page number
        page_size: Items per page
        current_user: Current authenticated user
        db: Database session

    Returns:
        Paginated list of chapters

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

    # Query chapters for this book
    query = db.query(Chapter).filter(Chapter.book_id == book_id)
    total = query.count()

    # Calculate offset and paginate
    offset = (page - 1) * page_size
    chapters = query.offset(offset).limit(page_size).all()

    return {
        "items": [ChapterSchema.model_validate(chapter) for chapter in chapters],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{book_id}/chapters", response_model=ChapterSchema, status_code=status.HTTP_201_CREATED)
async def create_chapter(
    book_id: int,
    request: ChapterCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChapterSchema:
    """
    Create a new chapter in a book.

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

    # Create new chapter
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


@router.get("/{book_id}/chapters/{chapter_id}", response_model=ChapterSchema)
async def get_chapter(
    book_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChapterSchema:
    """
    Get a specific chapter.

    Args:
        book_id: Book ID
        chapter_id: Chapter ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Chapter

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

    # Verify chapter exists and belongs to book
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.book_id == book_id,
    ).first()
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found in book {book_id}",
        )

    return ChapterSchema.model_validate(chapter)


@router.put("/{book_id}/chapters/{chapter_id}", response_model=ChapterSchema)
async def update_chapter(
    book_id: int,
    chapter_id: int,
    request: ChapterUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChapterSchema:
    """
    Update a chapter.

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

    # Verify chapter exists and belongs to book
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


@router.delete("/{book_id}/chapters/{chapter_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def delete_chapter(
    book_id: int,
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    Delete a chapter.

    Args:
        book_id: Book ID
        chapter_id: Chapter ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Confirmation message

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

    # Verify chapter exists and belongs to book
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.book_id == book_id,
    ).first()
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chapter with id {chapter_id} not found in book {book_id}",
        )

    db.delete(chapter)
    db.commit()

    return MessageResponse(message=f"Chapter {chapter_id} deleted successfully")
