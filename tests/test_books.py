"""Tests for book management endpoints."""
import pytest
from fastapi import status


class TestListBooks:
    """Test GET /books endpoint."""

    def test_list_books_empty(self, client, auth_headers):
        """Test listing books when none exist."""
        response = client.get("/books", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 50

    def test_list_books_with_pagination(self, client, auth_headers, db_session):
        """Test listing books with pagination."""
        from app.models.hierarchy import Book

        # Create 3 books
        for i in range(3):
            book = Book(name=f"Book {i+1}", description=f"Description {i+1}")
            db_session.add(book)
        db_session.commit()

        # Test default pagination
        response = client.get("/books", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 50

    def test_list_books_custom_page_size(self, client, auth_headers, db_session):
        """Test listing books with custom page size."""
        from app.models.hierarchy import Book

        # Create 5 books
        for i in range(5):
            book = Book(name=f"Book {i+1}", description=f"Description {i+1}")
            db_session.add(book)
        db_session.commit()

        # Test with page_size=2
        response = client.get("/books?page=1&page_size=2", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_books_second_page(self, client, auth_headers, db_session):
        """Test listing books on second page."""
        from app.models.hierarchy import Book

        # Create 5 books
        for i in range(5):
            book = Book(name=f"Book {i+1}", description=f"Description {i+1}")
            db_session.add(book)
        db_session.commit()

        # Test second page with page_size=2
        response = client.get("/books?page=2&page_size=2", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 2
        assert data["page"] == 2

    def test_list_books_no_auth(self, client):
        """Test listing books without authentication."""
        response = client.get("/books")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestCreateBook:
    """Test POST /books endpoint."""

    def test_create_book_success(self, client, auth_headers):
        """Test successful book creation."""
        request_data = {
            "name": "My Book",
            "description": "A great book",
        }
        response = client.post("/books", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "My Book"
        assert data["description"] == "A great book"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_book_no_description(self, client, auth_headers):
        """Test creating book with no description."""
        request_data = {"name": "My Book"}
        response = client.post("/books", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "My Book"
        assert data["description"] is None

    def test_create_book_empty_name(self, client, auth_headers):
        """Test creating book with empty name."""
        request_data = {"name": "", "description": "Description"}
        response = client.post("/books", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_book_missing_name(self, client, auth_headers):
        """Test creating book without name."""
        request_data = {"description": "Description"}
        response = client.post("/books", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_book_no_auth(self, client):
        """Test creating book without authentication."""
        request_data = {"name": "My Book", "description": "Description"}
        response = client.post("/books", json=request_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestGetBook:
    """Test GET /books/{book_id} endpoint."""

    def test_get_book_success(self, client, auth_headers, db_session):
        """Test getting a specific book."""
        from app.models.hierarchy import Book

        book = Book(name="Test Book", description="Test Description")
        db_session.add(book)
        db_session.commit()

        response = client.get(f"/books/{book.id}", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Test Book"
        assert data["description"] == "Test Description"
        assert data["chapters"] == []

    def test_get_book_not_found(self, client, auth_headers):
        """Test getting a non-existent book."""
        response = client.get("/books/999", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_book_no_auth(self, client, db_session):
        """Test getting book without authentication."""
        from app.models.hierarchy import Book

        book = Book(name="Test Book", description="Test Description")
        db_session.add(book)
        db_session.commit()

        response = client.get(f"/books/{book.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestUpdateBook:
    """Test PUT /books/{book_id} endpoint."""

    def test_update_book_name(self, client, auth_headers, db_session):
        """Test updating book name."""
        from app.models.hierarchy import Book

        book = Book(name="Old Name", description="Description")
        db_session.add(book)
        db_session.commit()

        request_data = {"name": "New Name"}
        response = client.put(f"/books/{book.id}", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "New Name"
        assert data["description"] == "Description"

    def test_update_book_description(self, client, auth_headers, db_session):
        """Test updating book description."""
        from app.models.hierarchy import Book

        book = Book(name="Name", description="Old Description")
        db_session.add(book)
        db_session.commit()

        request_data = {"description": "New Description"}
        response = client.put(f"/books/{book.id}", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Name"
        assert data["description"] == "New Description"

    def test_update_book_all_fields(self, client, auth_headers, db_session):
        """Test updating all book fields."""
        from app.models.hierarchy import Book

        book = Book(name="Old", description="Old Desc")
        db_session.add(book)
        db_session.commit()

        request_data = {"name": "New", "description": "New Desc"}
        response = client.put(f"/books/{book.id}", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "New"
        assert data["description"] == "New Desc"

    def test_update_book_not_found(self, client, auth_headers):
        """Test updating non-existent book."""
        request_data = {"name": "New Name"}
        response = client.put("/books/999", json=request_data, headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_book_no_auth(self, client, db_session):
        """Test updating book without authentication."""
        from app.models.hierarchy import Book

        book = Book(name="Name", description="Description")
        db_session.add(book)
        db_session.commit()

        request_data = {"name": "New Name"}
        response = client.put(f"/books/{book.id}", json=request_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestDeleteBook:
    """Test DELETE /books/{book_id} endpoint."""

    def test_delete_book_success(self, client, auth_headers, db_session):
        """Test successful book deletion."""
        from app.models.hierarchy import Book

        book = Book(name="Test Book", description="Description")
        db_session.add(book)
        db_session.commit()
        book_id = book.id

        response = client.delete(f"/books/{book_id}", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "deleted successfully" in data["message"]

        # Verify book is deleted
        response = client.get(f"/books/{book_id}", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_book_not_found(self, client, auth_headers):
        """Test deleting non-existent book."""
        response = client.delete("/books/999", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_book_no_auth(self, client, db_session):
        """Test deleting book without authentication."""
        from app.models.hierarchy import Book

        book = Book(name="Test Book", description="Description")
        db_session.add(book)
        db_session.commit()

        response = client.delete(f"/books/{book.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestChapters:
    """Test chapter endpoints."""

    def test_list_chapters_empty(self, client, auth_headers, db_session):
        """Test listing chapters when none exist."""
        from app.models.hierarchy import Book

        book = Book(name="Book", description="Description")
        db_session.add(book)
        db_session.commit()

        response = client.get(f"/books/{book.id}/chapters", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_chapter_success(self, client, auth_headers, db_session):
        """Test creating a chapter."""
        from app.models.hierarchy import Book

        book = Book(name="Book", description="Description")
        db_session.add(book)
        db_session.commit()

        request_data = {"name": "Chapter 1", "description": "First chapter"}
        response = client.post(
            f"/books/{book.id}/chapters",
            json=request_data,
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Chapter 1"
        assert data["description"] == "First chapter"
        assert data["book_id"] == book.id

    def test_create_chapter_book_not_found(self, client, auth_headers):
        """Test creating chapter in non-existent book."""
        request_data = {"name": "Chapter 1"}
        response = client.post(
            "/books/999/chapters",
            json=request_data,
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_chapter_success(self, client, auth_headers, db_session):
        """Test getting a specific chapter."""
        from app.models.hierarchy import Book, Chapter

        book = Book(name="Book", description="Description")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Chapter 1", description="Desc")
        db_session.add(chapter)
        db_session.commit()

        response = client.get(
            f"/books/{book.id}/chapters/{chapter.id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Chapter 1"

    def test_update_chapter_success(self, client, auth_headers, db_session):
        """Test updating a chapter."""
        from app.models.hierarchy import Book, Chapter

        book = Book(name="Book", description="Description")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Old", description="Old Desc")
        db_session.add(chapter)
        db_session.commit()

        request_data = {"name": "New Chapter"}
        response = client.put(
            f"/books/{book.id}/chapters/{chapter.id}",
            json=request_data,
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "New Chapter"

    def test_delete_chapter_success(self, client, auth_headers, db_session):
        """Test deleting a chapter."""
        from app.models.hierarchy import Book, Chapter

        book = Book(name="Book", description="Description")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Chapter", description="Desc")
        db_session.add(chapter)
        db_session.commit()
        chapter_id = chapter.id

        response = client.delete(
            f"/books/{book.id}/chapters/{chapter_id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify deletion
        response = client.get(
            f"/books/{book.id}/chapters/{chapter_id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
