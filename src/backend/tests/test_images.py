"""Tests for image upload endpoints."""
import io
import pytest
from fastapi import status


class TestImageUpload:
    """Test POST /chapters/{chapter_id}/images/upload endpoint."""

    def test_upload_single_jpg_image(self, client, auth_headers, db_session):
        """Test uploading a single JPG image."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Create a fake JPG file
        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"
        files = [("files", ("test.jpg", io.BytesIO(jpg_content), "image/jpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "test.jpg"
        assert data[0]["chapter_id"] == chapter.id
        assert data[0]["sequence_number"] == 1
        assert data[0]["ocr_status"] == "pending"
        assert data[0]["object_key"].startswith("images/")
        assert data[0]["file_size"] > 0

    def test_upload_multiple_images(self, client, auth_headers, db_session):
        """Test uploading multiple images."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Create multiple fake image files
        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"
        png_content = b"\x89PNG" + b"fake png content"
        
        files = [
            ("files", ("image1.jpg", io.BytesIO(jpg_content), "image/jpeg")),
            ("files", ("image2.png", io.BytesIO(png_content), "image/png")),
            ("files", ("image3.jpg", io.BytesIO(jpg_content), "image/jpeg")),
        ]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert len(data) == 3
        
        # Verify sequence numbers are correct
        for i, image in enumerate(data, 1):
            assert image["sequence_number"] == i
            assert image["ocr_status"] == "pending"
            assert image["object_key"].startswith(f"images/{chapter.id}/")

    def test_upload_png_image(self, client, auth_headers, db_session):
        """Test uploading a PNG image."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Create a fake PNG file
        png_content = b"\x89PNG\r\n\x1a\n" + b"fake png content"
        files = [("files", ("test.png", io.BytesIO(png_content), "image/png"))]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "test.png"
        assert data[0]["ocr_status"] == "pending"

    def test_upload_image_chapter_not_found(self, client, auth_headers):
        """Test uploading to non-existent chapter."""
        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"
        files = [("files", ("test.jpg", io.BytesIO(jpg_content), "image/jpeg"))]

        response = client.post(
            "/chapters/99999/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Chapter with id 99999 not found" in response.json()["detail"]

    def test_upload_invalid_file_format(self, client, auth_headers, db_session):
        """Test uploading invalid file format (e.g., PDF)."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Try to upload a PDF
        pdf_content = b"%PDF-1.4" + b"fake pdf content"
        files = [("files", ("test.pdf", io.BytesIO(pdf_content), "application/pdf"))]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid file format" in response.json()["detail"]

    def test_upload_wrong_mime_type(self, client, auth_headers, db_session):
        """Test uploading file with wrong MIME type."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Upload JPG file with PNG extension and wrong MIME type
        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"
        files = [("files", ("test.txt", io.BytesIO(jpg_content), "text/plain"))]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid file format" in response.json()["detail"]

    def test_upload_no_files(self, client, auth_headers, db_session):
        """Test uploading with no files."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=[],
            headers=auth_headers,
        )

        # FastAPI returns 422 for validation error when required files are missing
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_upload_creates_images_in_db(self, client, auth_headers, db_session):
        """Test that uploaded images are stored in database."""
        from app.models.hierarchy import Book, Chapter
        from app.models.image import Image

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"
        files = [("files", ("test.jpg", io.BytesIO(jpg_content), "image/jpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED

        # Verify image is in database
        images = db_session.query(Image).filter(Image.chapter_id == chapter.id).all()
        assert len(images) == 1
        assert images[0].filename == "test.jpg"
        assert images[0].ocr_status == "pending"
        assert images[0].object_key.startswith("images/")

    def test_upload_sequences_correctly(self, client, auth_headers, db_session):
        """Test that sequence numbers are assigned correctly."""
        from app.models.hierarchy import Book, Chapter
        from app.models.image import Image

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"

        # Upload first batch
        files1 = [
            ("files", ("image1.jpg", io.BytesIO(jpg_content), "image/jpeg")),
            ("files", ("image2.jpg", io.BytesIO(jpg_content), "image/jpeg")),
        ]
        response1 = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files1,
            headers=auth_headers,
        )
        assert response1.status_code == status.HTTP_201_CREATED
        data1 = response1.json()
        assert data1[0]["sequence_number"] == 1
        assert data1[1]["sequence_number"] == 2

        # Upload second batch
        files2 = [
            ("files", ("image3.jpg", io.BytesIO(jpg_content), "image/jpeg")),
            ("files", ("image4.jpg", io.BytesIO(jpg_content), "image/jpeg")),
        ]
        response2 = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files2,
            headers=auth_headers,
        )
        assert response2.status_code == status.HTTP_201_CREATED
        data2 = response2.json()
        assert data2[0]["sequence_number"] == 3
        assert data2[1]["sequence_number"] == 4

    def test_upload_no_auth(self, client, db_session):
        """Test uploading without authentication."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"
        files = [("files", ("test.jpg", io.BytesIO(jpg_content), "image/jpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_upload_stores_file_metadata(self, client, auth_headers, db_session):
        """Test that file metadata is stored (size, hash)."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"
        files = [("files", ("test.jpg", io.BytesIO(jpg_content), "image/jpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data[0]["file_size"] > 0
        assert data[0]["file_hash"] is not None
        assert len(data[0]["file_hash"]) == 64  # SHA256 hex is 64 chars

    def test_upload_jpeg_extension(self, client, auth_headers, db_session):
        """Test uploading with .jpeg extension (not just .jpg)."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"
        files = [("files", ("test.jpeg", io.BytesIO(jpg_content), "image/jpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data[0]["filename"] == "test.jpeg"

    def test_upload_object_key_format(self, client, auth_headers, db_session):
        """Test that object_key follows correct format: images/{chapter_id}/{image_id}.{ext}."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        jpg_content = b"\xFF\xD8\xFF\xE0" + b"fake jpg content"
        files = [("files", ("test.jpg", io.BytesIO(jpg_content), "image/jpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/images/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        image_id = data[0]["id"]
        expected_prefix = f"images/{chapter.id}/{image_id}."
        assert data[0]["object_key"].startswith(expected_prefix)
