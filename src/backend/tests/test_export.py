"""Tests for export endpoints."""
import pytest
from app.main import app
from app.database import get_db
from app.dependencies import get_minio_client
from tests.conftest import (
    create_test_user,
    create_test_book,
    create_test_chapter,
    create_test_image_with_ocr,
    create_test_audio_with_transcript,
)
from tests.fixtures.minio_mock import MockMinIOService
from app.auth import create_access_token


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_minio():
    return MockMinIOService()


@pytest.fixture
def authenticated_headers(db_session_with_client):
    user = create_test_user(db_session_with_client, username="testuser", password="password123")
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def book_with_images_and_audios(db_session_with_client, authenticated_headers, mock_minio):
    """Book with 1 chapter, 1 image (with OCR), 1 audio (with transcript)."""
    def _override_get_db():
        return db_session_with_client

    def _override_get_minio():
        return mock_minio

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_minio_client] = _override_get_minio

    book = create_test_book(db_session_with_client, name="Export Test Book")
    chapter = create_test_chapter(db_session_with_client, book_id=book.id, name="Chapter 1")

    image = create_test_image_with_ocr(
        db_session_with_client,
        chapter_id=chapter.id,
        filename="test.jpg",
        sequence_number=1,
        ocr_text="This is **bold** text from image 1",
    )

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

    app.dependency_overrides.clear()


# ============================================================================
# POST /export/folder
# ============================================================================


class TestExportFolder:

    def test_no_auth(self, client):
        response = client.post("/export/folder", json={"book_id": 1, "format": "docx"})
        assert response.status_code == 403

    def test_book_not_found(self, client, authenticated_headers):
        response = client.post(
            "/export/folder",
            headers=authenticated_headers,
            json={"book_id": 9999, "format": "docx"},
        )
        assert response.status_code == 404

    def test_chapter_not_found(self, client, book_with_images_and_audios):
        book = book_with_images_and_audios["book"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={"book_id": book.id, "chapter_id": 9999, "format": "docx"},
        )
        assert response.status_code == 404

    def test_invalid_format(self, client, book_with_images_and_audios):
        book = book_with_images_and_audios["book"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={"book_id": book.id, "format": "pdf"},
        )
        assert response.status_code == 400

    def test_docx_with_images_and_audios(self, client, book_with_images_and_audios):
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
        assert "wordprocessingml" in response.headers["content-type"]
        assert len(response.content) > 0

    def test_txt_with_images_and_audios(self, client, book_with_images_and_audios):
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
        # OCR text has markdown stripped: "This is bold text from image 1"
        assert b"bold" in response.content
        # Transcript text has markdown stripped: "This is italic text from audio 1"
        assert b"italic" in response.content

    def test_docx_without_images(self, client, book_with_images_and_audios):
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

    def test_txt_without_audios(self, client, book_with_images_and_audios):
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
        # Should have image OCR text but not audio transcript
        assert b"bold" in response.content
        assert b"italic" not in response.content

    def test_chapter_only(self, client, book_with_images_and_audios):
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
        assert b"bold" in response.content
        assert b"italic" in response.content

    def test_filename_contains_book_name(self, client, book_with_images_and_audios):
        book = book_with_images_and_audios["book"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/folder",
            headers=headers,
            json={"book_id": book.id, "format": "txt"},
        )
        assert response.status_code == 200
        disposition = response.headers.get("content-disposition", "")
        assert "Export_Test_Book" in disposition


# ============================================================================
# POST /export/selection
# ============================================================================


class TestExportSelection:

    def test_no_auth(self, client):
        response = client.post("/export/selection", json={"image_ids": [1], "format": "docx"})
        assert response.status_code == 403

    def test_requires_images_or_audios(self, client, authenticated_headers):
        response = client.post(
            "/export/selection",
            headers=authenticated_headers,
            json={"format": "docx"},
        )
        assert response.status_code == 400

    def test_image_not_found(self, client, book_with_images_and_audios):
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={"image_ids": [9999], "format": "docx"},
        )
        assert response.status_code == 404

    def test_audio_not_found(self, client, book_with_images_and_audios):
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={"audio_ids": [9999], "format": "docx"},
        )
        assert response.status_code == 404

    def test_invalid_format(self, client, book_with_images_and_audios):
        image = book_with_images_and_audios["image"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={"image_ids": [image.id], "format": "pdf"},
        )
        assert response.status_code == 400

    def test_single_image_docx(self, client, book_with_images_and_audios):
        image = book_with_images_and_audios["image"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={"image_ids": [image.id], "format": "docx", "include_images": True},
        )
        assert response.status_code == 200
        assert "wordprocessingml" in response.headers["content-type"]
        assert len(response.content) > 0

    def test_single_audio_txt(self, client, book_with_images_and_audios):
        audio = book_with_images_and_audios["audio"]
        headers = book_with_images_and_audios["headers"]
        response = client.post(
            "/export/selection",
            headers=headers,
            json={"audio_ids": [audio.id], "format": "txt"},
        )
        assert response.status_code == 200
        assert b"italic" in response.content

    def test_mixed_images_and_audios(self, client, book_with_images_and_audios):
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
        assert b"bold" in response.content
        assert b"italic" in response.content

    def test_exclude_images(self, client, book_with_images_and_audios):
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
        # Images excluded, so "bold" (from image OCR) should not appear
        assert b"bold" not in response.content
        # Audio transcript should still be present
        assert b"italic" in response.content
