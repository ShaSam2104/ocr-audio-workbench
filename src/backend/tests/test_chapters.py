"""Tests for chapter management endpoints."""
import time
import pytest
from fastapi import status
from app.models.hierarchy import Book, Chapter
from app.models.image import Image
from tests.conftest import create_test_book, create_test_chapter, create_test_book_and_chapter


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def book(db_session) -> Book:
    """Create a single book."""
    return create_test_book(db_session, name="Test Book")


@pytest.fixture
def book_with_chapter(db_session) -> tuple[Book, Chapter]:
    """Create a book with one chapter."""
    return create_test_book_and_chapter(db_session, "Test Book", "Original Chapter")


@pytest.fixture
def book_with_chapters(db_session) -> tuple[Book, list[Chapter]]:
    """Create a book with 5 chapters."""
    book = create_test_book(db_session, name="Test Book")
    chapters = []
    for i in range(5):
        ch = Chapter(book_id=book.id, name=f"Chapter {i+1}", sequence_order=i + 1)
        db_session.add(ch)
    db_session.commit()
    chapters = db_session.query(Chapter).filter(Chapter.book_id == book.id).order_by(Chapter.sequence_order).all()
    return book, chapters


# ============================================================================
# List chapters
# ============================================================================


class TestListChapters:
    """Test GET /books/{book_id}/chapters."""

    def test_empty(self, client, auth_headers, book):
        response = client.get(f"/books/{book.id}/chapters", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 50

    def test_returns_all(self, client, auth_headers, book_with_chapters):
        book, chapters = book_with_chapters
        response = client.get(f"/books/{book.id}/chapters", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 5

    def test_custom_page_size(self, client, auth_headers, book_with_chapters):
        book, _ = book_with_chapters
        response = client.get(f"/books/{book.id}/chapters?page=1&page_size=2", headers=auth_headers)
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page_size"] == 2

    def test_second_page(self, client, auth_headers, book_with_chapters):
        book, _ = book_with_chapters
        response = client.get(f"/books/{book.id}/chapters?page=2&page_size=2", headers=auth_headers)
        data = response.json()
        assert len(data["items"]) == 2
        assert data["page"] == 2

    def test_book_not_found(self, client, auth_headers):
        response = client.get("/books/99999/chapters", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_no_auth(self, client):
        response = client.get("/books/1/chapters")
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# Create chapter
# ============================================================================


class TestCreateChapter:
    """Test POST /books/{book_id}/chapters."""

    def test_full_fields(self, client, auth_headers, book):
        response = client.post(
            f"/books/{book.id}/chapters",
            json={"name": "New Chapter", "description": "Desc", "sequence_order": 1},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "New Chapter"
        assert data["description"] == "Desc"
        assert data["sequence_order"] == 1
        assert data["book_id"] == book.id

    def test_name_only(self, client, auth_headers, book):
        response = client.post(
            f"/books/{book.id}/chapters",
            json={"name": "Minimal Chapter"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Minimal Chapter"
        assert data["description"] is None
        assert data["sequence_order"] is None

    def test_missing_name(self, client, auth_headers, book):
        response = client.post(
            f"/books/{book.id}/chapters",
            json={"description": "no name"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_empty_name(self, client, auth_headers, book):
        response = client.post(
            f"/books/{book.id}/chapters",
            json={"name": ""},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_book_not_found(self, client, auth_headers):
        response = client.post(
            "/books/99999/chapters",
            json={"name": "New Chapter"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_no_auth(self, client):
        response = client.post("/books/1/chapters", json={"name": "X"})
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# Update / Rename chapter
# ============================================================================


class TestUpdateChapter:
    """Test PUT /books/{book_id}/chapters/{chapter_id}."""

    def test_rename(self, client, auth_headers, book_with_chapter):
        """Rename a chapter — the primary edit use case."""
        book, chapter = book_with_chapter
        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json={"name": "Renamed Chapter"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Renamed Chapter"
        assert data["description"] == "Test chapter"  # unchanged
        assert data["sequence_order"] == 1  # unchanged

    def test_rename_preserves_description(self, client, auth_headers, db_session):
        """Renaming should not clobber existing description."""
        book = create_test_book(db_session, name="B")
        chapter = Chapter(book_id=book.id, name="Ch", description="Important notes", sequence_order=1)
        db_session.add(chapter)
        db_session.commit()
        db_session.refresh(chapter)

        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json={"name": "Ch v2"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["description"] == "Important notes"

    def test_update_multiple_fields(self, client, auth_headers, book_with_chapter):
        book, chapter = book_with_chapter
        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json={"name": "Updated", "description": "New desc", "sequence_order": 5},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated"
        assert data["description"] == "New desc"
        assert data["sequence_order"] == 5

    def test_update_description_only(self, client, auth_headers, book_with_chapter):
        book, chapter = book_with_chapter
        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json={"description": "Just desc"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Original Chapter"  # unchanged
        assert data["description"] == "Just desc"

    def test_update_sequence_order_only(self, client, auth_headers, book_with_chapter):
        book, chapter = book_with_chapter
        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json={"sequence_order": 42},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["sequence_order"] == 42
        assert response.json()["name"] == "Original Chapter"

    def test_empty_body_is_noop(self, client, auth_headers, book_with_chapter):
        """Sending {} should succeed and change nothing."""
        book, chapter = book_with_chapter
        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Original Chapter"
        assert data["sequence_order"] == 1

    def test_rename_empty_string_rejected(self, client, auth_headers, book_with_chapter):
        """Empty string name should be rejected by validation."""
        book, chapter = book_with_chapter
        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json={"name": ""},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_book_not_found(self, client, auth_headers):
        response = client.put(
            "/books/99999/chapters/1",
            json={"name": "X"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_chapter_not_found(self, client, auth_headers, book):
        response = client.put(
            f"/books/{book.id}/chapters/99999",
            json={"name": "X"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_chapter_wrong_book(self, client, auth_headers, db_session):
        """Cannot update a chapter through a different book's URL."""
        book1 = create_test_book(db_session, name="Book 1")
        book2 = create_test_book(db_session, name="Book 2")
        chapter = Chapter(book_id=book1.id, name="Ch1")
        db_session.add(chapter)
        db_session.commit()
        db_session.refresh(chapter)

        response = client.put(
            f"/books/{book2.id}/chapters/{chapter.id}",
            json={"name": "Hacked"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_no_auth(self, client):
        response = client.put("/books/1/chapters/1", json={"name": "X"})
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# Delete chapter
# ============================================================================


class TestDeleteChapter:
    """Test DELETE /books/{book_id}/chapters/{chapter_id}."""

    def test_delete_success(self, client, auth_headers, db_session, book_with_chapter):
        book, chapter = book_with_chapter
        cid = chapter.id
        response = client.delete(f"/books/{book.id}/chapters/{cid}", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        assert "deleted successfully" in response.json()["message"]
        assert db_session.query(Chapter).filter(Chapter.id == cid).first() is None

    def test_delete_cascades_images(self, client, auth_headers, db_session, book_with_chapter):
        book, chapter = book_with_chapter
        image = Image(
            chapter_id=chapter.id,
            object_key="images/1/test.jpg",
            filename="test.jpg",
            sequence_number=1,
        )
        db_session.add(image)
        db_session.commit()
        img_id = image.id
        cid = chapter.id

        response = client.delete(f"/books/{book.id}/chapters/{cid}", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        assert db_session.query(Chapter).filter(Chapter.id == cid).first() is None
        assert db_session.query(Image).filter(Image.id == img_id).first() is None

    def test_book_not_found(self, client, auth_headers):
        response = client.delete("/books/99999/chapters/1", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_chapter_not_found(self, client, auth_headers, book):
        response = client.delete(f"/books/{book.id}/chapters/99999", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_chapter_wrong_book(self, client, auth_headers, db_session):
        book1 = create_test_book(db_session, name="Book 1")
        book2 = create_test_book(db_session, name="Book 2")
        chapter = Chapter(book_id=book1.id, name="Ch1")
        db_session.add(chapter)
        db_session.commit()
        db_session.refresh(chapter)

        response = client.delete(f"/books/{book2.id}/chapters/{chapter.id}", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_no_auth(self, client):
        response = client.delete("/books/1/chapters/1")
        assert response.status_code == status.HTTP_403_FORBIDDEN
