"""Tests for export endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.database import get_db
from app.models.image import Image
from app.models.audio import Audio
from app.dependencies import get_minio_client
from tests.conftest import (
    create_test_user,
    create_test_book,
    create_test_chapter,
    create_test_image_with_ocr,
    create_test_audio_with_transcript,
)
from tests.fixtures.minio_mock import MockMinIOService


@pytest.fixture
def mock_minio():
    """Create mock MinIO service."""
    return MockMinIOService()


@pytest.fixture
def authenticated_headers(db_session_with_client):
    """Get authenticated headers for testing."""
    user = create_test_user(db_session_with_client, username="testuser", password="password123")
    # Create a token for the user
    from app.auth import create_access_token
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def book_with_images_and_audios(db_session_with_client, authenticated_headers, mock_minio):
    """Create a book with chapters, images (with OCR), and audios (with transcripts)."""
    # Override dependencies
    def _override_get_db():
        return db_session_with_client

    def _override_get_minio():
        return mock_minio

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_minio_client] = _override_get_minio

    # Create test data
    book = create_test_book(db_session_with_client, name="Export Test Book")
    chapter = create_test_chapter(db_session_with_client, book_id=book.id, name="Chapter 1")

    # Create image with OCR
    image = create_test_image_with_ocr(
        db_session_with_client,
        chapter_id=chapter.id,
        filename="test.jpg",
        sequence_number=1,
        ocr_text="This is **bold** text from image 1",
    )

    # Create audio with transcript
    audio = create_test_audio_with_transcript(
        db_session_with_client,
        chapter_id=chapter.id,
        filename="test.mp3",
        sequence_number=1,
        transcript_text="This is *italic* text from audio 1",
        duration_seconds=120,
        audio_format="mp3",
    )

    yield {
        "book": book,
        "chapter": chapter,
        "image": image,
        "audio": audio,
        "headers": authenticated_headers,
    }

    # Cleanup
    app.dependency_overrides.clear()



class TestExportFolder:
    """Tests for POST /export/folder endpoint."""

    def test_export_folder_docx_requires_authentication(self, client):
        """POST /export/folder returns 403 without authentication."""
        response = client.post(
            "/export/folder",
            json={
                "book_id": 1,
                "format": "docx",
            },
        )
        assert response.status_code == 403

    def test_export_folder_not_found_book(self, client, authenticated_headers):
        """POST /export/folder returns 404 if book not found."""
        response = client.post(
            "/export/folder",
            headers=authenticated_headers,
            json={
                "book_id": 9999,
                "format": "docx",
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_export_folder_not_found_chapter(self, client, book_with_images_and_audios):
        """POST /export/folder returns 404 if chapter not found."""
        book = book_with_images_and_audios["book"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={
                "book_id": book.id,
                "chapter_id": 9999,
                "format": "docx",
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_export_folder_invalid_format(self, client, book_with_images_and_audios):
        """POST /export/folder returns 400 for invalid format."""
        book = book_with_images_and_audios["book"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={
                "book_id": book.id,
                "format": "pdf",  # Invalid format
            },
        )
        assert response.status_code == 400
        assert "Invalid format" in response.json()["detail"]

    def test_export_folder_docx_with_images_and_audios(self, client, book_with_images_and_audios):
        """POST /export/folder returns .docx file with images and audios."""
        book = book_with_images_and_audios["book"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={
                "book_id": book.id,
                "format": "docx",
                "include_images": True,
                "include_audio_transcripts": True,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert "attachment" in response.headers.get("content-disposition", "")
        assert len(response.content) > 0  # File has content

    def test_export_folder_txt_with_images_and_audios(self, client, book_with_images_and_audios):
        """POST /export/folder returns .txt file with images and audios."""
        book = book_with_images_and_audios["book"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={
                "book_id": book.id,
                "format": "txt",
                "include_images": True,
                "include_audio_transcripts": True,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment" in response.headers.get("content-disposition", "")
        assert b"IMAGES" in response.content
        assert b"AUDIO TRANSCRIPTS" in response.content
        assert b"bold" in response.content  # Should contain formatted text
        assert b"italic" in response.content

    def test_export_folder_docx_without_images(self, client, book_with_images_and_audios):
        """POST /export/folder excludes images if include_images=False."""
        book = book_with_images_and_audios["book"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={
                "book_id": book.id,
                "format": "docx",
                "include_images": False,
                "include_audio_transcripts": True,
            },
        )
        assert response.status_code == 200
        assert len(response.content) > 0

    def test_export_folder_txt_without_audios(self, client, book_with_images_and_audios):
        """POST /export/folder excludes audios if include_audio_transcripts=False."""
        book = book_with_images_and_audios["book"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={
                "book_id": book.id,
                "format": "txt",
                "include_images": True,
                "include_audio_transcripts": False,
            },
        )
        assert response.status_code == 200
        assert b"IMAGES" in response.content
        assert b"AUDIO TRANSCRIPTS" not in response.content

    def test_export_chapter_only(self, client, book_with_images_and_audios):
        """POST /export/folder exports only specified chapter."""
        book = book_with_images_and_audios["book"]
        chapter = book_with_images_and_audios["chapter"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={
                "book_id": book.id,
                "chapter_id": chapter.id,
                "format": "txt",
                "include_images": True,
                "include_audio_transcripts": True,
            },
        )
        assert response.status_code == 200
        assert b"Image 1" in response.content  # Should have the image from this chapter
        assert b"Audio 1" in response.content  # Should have the audio from this chapter


class TestExportSelection:
    """Tests for POST /export/selection endpoint."""

    def test_export_selection_requires_authentication(self, client):
        """POST /export/selection returns 403 without authentication."""
        response = client.post(
            "/export/selection",
            json={
                "image_ids": [1],
                "format": "docx",
            },
        )
        assert response.status_code == 403

    def test_export_selection_requires_images_or_audios(self, client, authenticated_headers):
        """POST /export/selection returns 400 if neither image_ids nor audio_ids provided."""
        response = client.post(
            "/export/selection",
            headers=authenticated_headers,
            json={
                "format": "docx",
            },
        )
        assert response.status_code == 400
        assert "Must provide" in response.json()["detail"]

    def test_export_selection_image_not_found(self, client, book_with_images_and_audios):
        """POST /export/selection returns 404 if image not found."""
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={
                "image_ids": [9999],
                "format": "docx",
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_export_selection_audio_not_found(self, client, book_with_images_and_audios):
        """POST /export/selection returns 404 if audio not found."""
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={
                "audio_ids": [9999],
                "format": "docx",
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_export_selection_invalid_format(self, client, book_with_images_and_audios):
        """POST /export/selection returns 400 for invalid format."""
        image = book_with_images_and_audios["image"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={
                "image_ids": [image.id],
                "format": "pdf",  # Invalid format
            },
        )
        assert response.status_code == 400
        assert "Invalid format" in response.json()["detail"]

    def test_export_selection_single_image_docx(self, client, book_with_images_and_audios):
        """POST /export/selection exports single image to .docx."""
        image = book_with_images_and_audios["image"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={
                "image_ids": [image.id],
                "format": "docx",
                "include_images": True,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert len(response.content) > 0

    def test_export_selection_single_audio_txt(self, client, book_with_images_and_audios):
        """POST /export/selection exports single audio to .txt."""
        audio = book_with_images_and_audios["audio"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={
                "audio_ids": [audio.id],
                "format": "txt",
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert b"Audio 1" in response.content
        assert b"italic" in response.content  # Should contain formatted text

    def test_export_selection_mixed_images_and_audios(self, client, book_with_images_and_audios):
        """POST /export/selection exports both images and audios together."""
        image = book_with_images_and_audios["image"]
        audio = book_with_images_and_audios["audio"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={
                "image_ids": [image.id],
                "audio_ids": [audio.id],
                "format": "txt",
                "include_images": True,
            },
        )
        assert response.status_code == 200
        assert b"Image 1" in response.content
        assert b"Audio 1" in response.content
        assert b"bold" in response.content  # Image text
        assert b"italic" in response.content  # Audio text

    def test_export_selection_without_images(self, client, book_with_images_and_audios):
        """POST /export/selection excludes images if include_images=False."""
        image = book_with_images_and_audios["image"]
        audio = book_with_images_and_audios["audio"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={
                "image_ids": [image.id],
                "audio_ids": [audio.id],
                "format": "txt",
                "include_images": False,
            },
        )
        assert response.status_code == 200
        assert b"Image 1" not in response.content  # Images excluded
        assert b"Audio 1" in response.content  # Audio included
