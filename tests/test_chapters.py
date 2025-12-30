"""Tests for chapter management endpoints."""
import pytest
from fastapi import status


class TestListChapters:
    """Test GET /books/{book_id}/chapters endpoint."""

    def test_list_chapters_empty(self, client, auth_headers, db_session):
        """Test listing chapters when none exist."""
        from app.models.hierarchy import Book

        # Create a book
        book = Book(name="Test Book", description="Test Description")
        db_session.add(book)
        db_session.commit()

        response = client.get(f"/books/{book.id}/chapters", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 50

    def test_list_chapters_with_pagination(self, client, auth_headers, db_session):
        """Test listing chapters with pagination."""
        from app.models.hierarchy import Book, Chapter

        # Create a book
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        # Create 3 chapters
        for i in range(3):
            chapter = Chapter(
                book_id=book.id,
                name=f"Chapter {i+1}",
                description=f"Description {i+1}",
                sequence_order=i+1,
            )
            db_session.add(chapter)
        db_session.commit()

        response = client.get(f"/books/{book.id}/chapters", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3
        assert data["page"] == 1

    def test_list_chapters_custom_page_size(self, client, auth_headers, db_session):
        """Test listing chapters with custom page size."""
        from app.models.hierarchy import Book, Chapter

        # Create a book
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        # Create 5 chapters
        for i in range(5):
            chapter = Chapter(book_id=book.id, name=f"Chapter {i+1}", sequence_order=i+1)
            db_session.add(chapter)
        db_session.commit()

        response = client.get(
            f"/books/{book.id}/chapters?page=1&page_size=2", headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page_size"] == 2

    def test_list_chapters_second_page(self, client, auth_headers, db_session):
        """Test listing chapters on second page."""
        from app.models.hierarchy import Book, Chapter

        # Create a book
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        # Create 5 chapters
        for i in range(5):
            chapter = Chapter(book_id=book.id, name=f"Chapter {i+1}", sequence_order=i+1)
            db_session.add(chapter)
        db_session.commit()

        response = client.get(
            f"/books/{book.id}/chapters?page=2&page_size=2", headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 2
        assert data["page"] == 2

    def test_list_chapters_book_not_found(self, client, auth_headers):
        """Test listing chapters for non-existent book."""
        response = client.get("/books/99999/chapters", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Book with id 99999 not found" in response.json()["detail"]

    def test_list_chapters_no_auth(self, client):
        """Test listing chapters without authentication."""
        response = client.get("/books/1/chapters")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestCreateChapter:
    """Test POST /books/{book_id}/chapters endpoint."""

    def test_create_chapter_success(self, client, auth_headers, db_session):
        """Test creating a chapter successfully."""
        from app.models.hierarchy import Book

        # Create a book
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        response = client.post(
            f"/books/{book.id}/chapters",
            json={
                "name": "New Chapter",
                "description": "New Description",
                "sequence_order": 1,
            },
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "New Chapter"
        assert data["description"] == "New Description"
        assert data["sequence_order"] == 1
        assert data["book_id"] == book.id

    def test_create_chapter_minimal(self, client, auth_headers, db_session):
        """Test creating a chapter with minimal data."""
        from app.models.hierarchy import Book

        # Create a book
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        response = client.post(
            f"/books/{book.id}/chapters",
            json={"name": "New Chapter"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "New Chapter"
        assert data["description"] is None
        assert data["sequence_order"] is None

    def test_create_chapter_book_not_found(self, client, auth_headers):
        """Test creating a chapter in non-existent book."""
        response = client.post(
            "/books/99999/chapters",
            json={"name": "New Chapter"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Book with id 99999 not found" in response.json()["detail"]

    def test_create_chapter_missing_name(self, client, auth_headers, db_session):
        """Test creating a chapter without name."""
        from app.models.hierarchy import Book

        # Create a book
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        response = client.post(
            f"/books/{book.id}/chapters",
            json={"description": "Missing name"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_chapter_no_auth(self, client):
        """Test creating a chapter without authentication."""
        response = client.post(
            "/books/1/chapters",
            json={"name": "New Chapter"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestUpdateChapter:
    """Test PUT /books/{book_id}/chapters/{chapter_id} endpoint."""

    def test_update_chapter_success(self, client, auth_headers, db_session):
        """Test updating a chapter successfully."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Original Name", sequence_order=1)
        db_session.add(chapter)
        db_session.commit()

        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json={"name": "Updated Name", "sequence_order": 5},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["sequence_order"] == 5

    def test_update_chapter_partial(self, client, auth_headers, db_session):
        """Test updating only some chapter fields."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(
            book_id=book.id,
            name="Original Name",
            description="Original Description",
            sequence_order=1,
        )
        db_session.add(chapter)
        db_session.commit()

        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json={"name": "Updated Name"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Original Description"  # Unchanged
        assert data["sequence_order"] == 1  # Unchanged

    def test_update_chapter_book_not_found(self, client, auth_headers):
        """Test updating chapter in non-existent book."""
        response = client.put(
            "/books/99999/chapters/1",
            json={"name": "Updated Name"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Book with id 99999 not found" in response.json()["detail"]

    def test_update_chapter_not_found(self, client, auth_headers, db_session):
        """Test updating non-existent chapter."""
        from app.models.hierarchy import Book

        # Create a book
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        response = client.put(
            f"/books/{book.id}/chapters/99999",
            json={"name": "Updated Name"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Chapter with id 99999 not found" in response.json()["detail"]

    def test_update_chapter_wrong_book(self, client, auth_headers, db_session):
        """Test updating chapter from different book."""
        from app.models.hierarchy import Book, Chapter

        # Create two books with chapters
        book1 = Book(name="Book 1")
        book2 = Book(name="Book 2")
        db_session.add(book1)
        db_session.add(book2)
        db_session.commit()

        chapter1 = Chapter(book_id=book1.id, name="Chapter 1")
        db_session.add(chapter1)
        db_session.commit()

        # Try to update chapter1 via book2
        response = client.put(
            f"/books/{book2.id}/chapters/{chapter1.id}",
            json={"name": "Updated Name"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_chapter_no_auth(self, client):
        """Test updating a chapter without authentication."""
        response = client.put(
            "/books/1/chapters/1",
            json={"name": "Updated Name"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestDeleteChapter:
    """Test DELETE /books/{book_id}/chapters/{chapter_id} endpoint."""

    def test_delete_chapter_success(self, client, auth_headers, db_session):
        """Test deleting a chapter successfully."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Chapter to Delete")
        db_session.add(chapter)
        db_session.commit()

        chapter_id = chapter.id

        response = client.delete(
            f"/books/{book.id}/chapters/{chapter_id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        assert "deleted successfully" in response.json()["message"]

        # Verify chapter is deleted
        deleted_chapter = db_session.query(Chapter).filter(Chapter.id == chapter_id).first()
        assert deleted_chapter is None

    def test_delete_chapter_cascades_images(self, client, auth_headers, db_session):
        """Test deleting a chapter cascades to delete images."""
        from app.models.hierarchy import Book, Chapter
        from app.models.image import Image

        # Create book and chapter with image
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Chapter with Images")
        db_session.add(chapter)
        db_session.commit()

        image = Image(
            chapter_id=chapter.id,
            object_key="images/1/test.jpg",
            filename="test.jpg",
            sequence_number=1,
        )
        db_session.add(image)
        db_session.commit()

        image_id = image.id
        chapter_id = chapter.id

        # Delete chapter
        response = client.delete(
            f"/books/{book.id}/chapters/{chapter_id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify both chapter and image are deleted
        deleted_chapter = db_session.query(Chapter).filter(Chapter.id == chapter_id).first()
        deleted_image = db_session.query(Image).filter(Image.id == image_id).first()
        assert deleted_chapter is None
        assert deleted_image is None

    def test_delete_chapter_book_not_found(self, client, auth_headers):
        """Test deleting chapter from non-existent book."""
        response = client.delete(
            "/books/99999/chapters/1",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Book with id 99999 not found" in response.json()["detail"]

    def test_delete_chapter_not_found(self, client, auth_headers, db_session):
        """Test deleting non-existent chapter."""
        from app.models.hierarchy import Book

        # Create a book
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        response = client.delete(
            f"/books/{book.id}/chapters/99999",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Chapter with id 99999 not found" in response.json()["detail"]

    def test_delete_chapter_wrong_book(self, client, auth_headers, db_session):
        """Test deleting chapter from different book."""
        from app.models.hierarchy import Book, Chapter

        # Create two books with chapters
        book1 = Book(name="Book 1")
        book2 = Book(name="Book 2")
        db_session.add(book1)
        db_session.add(book2)
        db_session.commit()

        chapter1 = Chapter(book_id=book1.id, name="Chapter 1")
        db_session.add(chapter1)
        db_session.commit()

        # Try to delete chapter1 via book2
        response = client.delete(
            f"/books/{book2.id}/chapters/{chapter1.id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_chapter_no_auth(self, client):
        """Test deleting a chapter without authentication."""
        response = client.delete(
            "/books/1/chapters/1",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
