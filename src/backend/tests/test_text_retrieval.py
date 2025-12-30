"""Tests for text retrieval endpoints (OCR and transcript)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db
from app.models.user import User
from app.models.hierarchy import Book, Chapter
from app.models.image import Image
from app.models.audio import Audio
from app.models.ocr import OCRText
from app.models.transcript import AudioTranscript
from app.dependencies import get_current_user
from tests.conftest import create_test_user, create_test_book_and_chapter


client = TestClient(app)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def authenticated_headers(db_session_with_client):
    """Create test user and return auth headers."""
    user = create_test_user(db_session_with_client, "textuser")
    from app.auth import create_access_token

    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def book_and_chapter(test_db_session):
    """Create test book and chapter."""
    book, chapter = create_test_book_and_chapter(test_db_session, "Test Book", "Test Chapter")
    return book, chapter


@pytest.fixture
def test_image(test_db_session, book_and_chapter):
    """Create test image with OCR text."""
    _, chapter = book_and_chapter

    image = Image(
        chapter_id=chapter.id,
        object_key="images/1/test.jpg",
        filename="test.jpg",
        sequence_number=1,
        file_size=1024,
        file_hash="test123",
        ocr_status="completed",
    )
    test_db_session.add(image)
    test_db_session.flush()

    # Add OCR text
    ocr_text = OCRText(
        image_id=image.id,
        raw_text_with_formatting="This is **bold** text and *italic* text",
        plain_text_for_search="This is bold text and italic text",
        detected_language="en",
        processing_time_ms=3500,
    )
    test_db_session.add(ocr_text)
    test_db_session.commit()

    return image


@pytest.fixture
def test_audio(test_db_session, book_and_chapter):
    """Create test audio with transcript."""
    _, chapter = book_and_chapter

    audio = Audio(
        chapter_id=chapter.id,
        object_key="audio/1/test.mp3",
        filename="test.mp3",
        sequence_number=1,
        duration_seconds=120,
        audio_format="mp3",
        file_size=2048,
        transcription_status="completed",
    )
    test_db_session.add(audio)
    test_db_session.flush()

    # Add transcript
    transcript = AudioTranscript(
        audio_id=audio.id,
        raw_text_with_formatting="This is the **transcribed** text from audio",
        plain_text_for_search="This is the transcribed text from audio",
        detected_language="hi",
        processing_time_ms=5200,
    )
    test_db_session.add(transcript)
    test_db_session.commit()

    return audio


@pytest.fixture
def image_without_ocr(test_db_session, book_and_chapter):
    """Create test image without OCR text."""
    _, chapter = book_and_chapter

    image = Image(
        chapter_id=chapter.id,
        object_key="images/2/test.jpg",
        filename="test2.jpg",
        sequence_number=2,
        file_size=1024,
        file_hash="test234",
        ocr_status="pending",
    )
    test_db_session.add(image)
    test_db_session.commit()

    return image


@pytest.fixture
def audio_without_transcript(test_db_session, book_and_chapter):
    """Create test audio without transcript."""
    _, chapter = book_and_chapter

    audio = Audio(
        chapter_id=chapter.id,
        object_key="audio/2/test.mp3",
        filename="test2.mp3",
        sequence_number=2,
        duration_seconds=180,
        audio_format="mp3",
        file_size=2048,
        transcription_status="pending",
    )
    test_db_session.add(audio)
    test_db_session.commit()

    return audio


# ============================================================================
# TEST: GET /images/{image_id}/text - Image Text Retrieval
# ============================================================================


def test_get_image_text_returns_200(authenticated_headers, test_db_session, test_image):
    """Test that endpoint returns 200 with OCR text."""
    response = client.get(
        f"/images/{test_image.id}/text",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["image_id"] == test_image.id
    assert data["raw_text_with_formatting"] == "This is **bold** text and *italic* text"
    assert data["plain_text"] == "This is bold text and italic text"
    assert data["detected_language"] == "en"
    assert "created_at" in data


def test_get_image_text_requires_authentication(test_db_session, test_image):
    """Test that endpoint returns 403 when no auth header."""
    response = client.get(f"/images/{test_image.id}/text")

    assert response.status_code == 403


def test_get_image_text_not_found(authenticated_headers):
    """Test that endpoint returns 404 for non-existent image."""
    response = client.get(
        "/images/999/text",
        headers=authenticated_headers,
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_image_text_not_processed(authenticated_headers, test_db_session, image_without_ocr):
    """Test that endpoint returns 404 when image not yet processed."""
    response = client.get(
        f"/images/{image_without_ocr.id}/text",
        headers=authenticated_headers,
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_image_text_response_structure(authenticated_headers, test_db_session, test_image):
    """Test that response has correct structure."""
    response = client.get(
        f"/images/{test_image.id}/text",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()

    # Check required fields
    required_fields = ["image_id", "raw_text_with_formatting", "plain_text", "created_at"]
    for field in required_fields:
        assert field in data


def test_get_image_text_no_user_filtering(authenticated_headers, test_db_session, test_image):
    """Test that any authenticated user can access any image's OCR text."""
    # User can access image's text regardless of who created it
    response = client.get(
        f"/images/{test_image.id}/text",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    assert response.json()["image_id"] == test_image.id


def test_get_image_text_formatting_preserved(authenticated_headers, test_db_session, book_and_chapter):
    """Test that text formatting is preserved in response."""
    _, chapter = book_and_chapter

    # Create image with various formatting
    image = Image(
        chapter_id=chapter.id,
        object_key="images/3/formatted.jpg",
        filename="formatted.jpg",
        sequence_number=3,
        file_size=1024,
        file_hash="fmt123",
        ocr_status="completed",
    )
    test_db_session.add(image)
    test_db_session.flush()

    # Add OCR with formatting tags
    ocr_text = OCRText(
        image_id=image.id,
        raw_text_with_formatting="**bold** *italic* __underline__ ~~strikethrough~~ ^super^ ~sub~",
        plain_text_for_search="bold italic underline strikethrough super sub",
        detected_language="en",
    )
    test_db_session.add(ocr_text)
    test_db_session.commit()

    # Retrieve text
    response = client.get(
        f"/images/{image.id}/text",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["raw_text_with_formatting"] == "**bold** *italic* __underline__ ~~strikethrough~~ ^super^ ~sub~"
    assert data["plain_text"] == "bold italic underline strikethrough super sub"


# ============================================================================
# TEST: GET /audio/{audio_id}/transcript - Audio Transcript Retrieval
# ============================================================================


def test_get_audio_transcript_returns_200(authenticated_headers, test_db_session, test_audio):
    """Test that endpoint returns 200 with transcript."""
    response = client.get(
        f"/audio/{test_audio.id}/transcript",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["audio_id"] == test_audio.id
    assert data["raw_text_with_formatting"] == "This is the **transcribed** text from audio"
    assert data["plain_text"] == "This is the transcribed text from audio"
    assert data["detected_language"] == "hi"
    assert data["duration_seconds"] == 120
    assert "created_at" in data


def test_get_audio_transcript_requires_authentication(test_db_session, test_audio):
    """Test that endpoint returns 403 when no auth header."""
    response = client.get(f"/audio/{test_audio.id}/transcript")

    assert response.status_code == 403


def test_get_audio_transcript_not_found(authenticated_headers):
    """Test that endpoint returns 404 for non-existent audio."""
    response = client.get(
        "/audio/999/transcript",
        headers=authenticated_headers,
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_audio_transcript_not_processed(authenticated_headers, test_db_session, audio_without_transcript):
    """Test that endpoint returns 404 when audio not yet processed."""
    response = client.get(
        f"/audio/{audio_without_transcript.id}/transcript",
        headers=authenticated_headers,
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_audio_transcript_response_structure(authenticated_headers, test_db_session, test_audio):
    """Test that response has correct structure."""
    response = client.get(
        f"/audio/{test_audio.id}/transcript",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()

    # Check required fields
    required_fields = ["audio_id", "raw_text_with_formatting", "plain_text", "duration_seconds", "created_at"]
    for field in required_fields:
        assert field in data


def test_get_audio_transcript_includes_duration(authenticated_headers, test_db_session, test_audio):
    """Test that transcript response includes audio duration."""
    response = client.get(
        f"/audio/{test_audio.id}/transcript",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["duration_seconds"] == 120


def test_get_audio_transcript_no_user_filtering(authenticated_headers, test_db_session, test_audio):
    """Test that any authenticated user can access any audio's transcript."""
    # User can access audio's transcript regardless of who created it
    response = client.get(
        f"/audio/{test_audio.id}/transcript",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    assert response.json()["audio_id"] == test_audio.id


def test_get_audio_transcript_formatting_preserved(authenticated_headers, test_db_session, book_and_chapter):
    """Test that transcript formatting is preserved in response."""
    _, chapter = book_and_chapter

    # Create audio with formatted transcript
    audio = Audio(
        chapter_id=chapter.id,
        object_key="audio/3/formatted.mp3",
        filename="formatted.mp3",
        sequence_number=3,
        duration_seconds=90,
        audio_format="mp3",
        file_size=2048,
        transcription_status="completed",
    )
    test_db_session.add(audio)
    test_db_session.flush()

    # Add transcript with formatting
    transcript = AudioTranscript(
        audio_id=audio.id,
        raw_text_with_formatting="**Important:** *Note* the following: __critical__ information",
        plain_text_for_search="Important: Note the following: critical information",
        detected_language="en",
    )
    test_db_session.add(transcript)
    test_db_session.commit()

    # Retrieve transcript
    response = client.get(
        f"/audio/{audio.id}/transcript",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["raw_text_with_formatting"] == "**Important:** *Note* the following: __critical__ information"
    assert data["plain_text"] == "Important: Note the following: critical information"


# ============================================================================
# TEST: No Audit Trail
# ============================================================================


def test_image_text_no_extracted_by(authenticated_headers, test_db_session, test_image):
    """Test that OCR response has NO extracted_by or extracted_at fields."""
    response = client.get(
        f"/images/{test_image.id}/text",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()

    # These fields should NOT be present
    assert "extracted_by" not in data
    assert "extracted_at" not in data
    assert "user_id" not in data

    # But created_at should be present (when transcription was done)
    assert "created_at" in data


def test_audio_transcript_no_extracted_by(authenticated_headers, test_db_session, test_audio):
    """Test that transcript response has NO extracted_by or extracted_at fields."""
    response = client.get(
        f"/audio/{test_audio.id}/transcript",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()

    # These fields should NOT be present
    assert "extracted_by" not in data
    assert "extracted_at" not in data
    assert "user_id" not in data

    # But created_at should be present (when transcription was done)
    assert "created_at" in data


# ============================================================================
# TEST: Response Models (Pydantic Schema Validation)
# ============================================================================


def test_image_text_response_model_validation(authenticated_headers, test_db_session, test_image):
    """Test that response matches OCRTextResponse schema."""
    response = client.get(
        f"/images/{test_image.id}/text",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()

    # Validate data types
    assert isinstance(data["image_id"], int)
    assert isinstance(data["raw_text_with_formatting"], str)
    assert isinstance(data["plain_text"], str)
    assert isinstance(data["detected_language"], (str, type(None)))
    assert isinstance(data["created_at"], str)  # ISO format datetime


def test_audio_transcript_response_model_validation(authenticated_headers, test_db_session, test_audio):
    """Test that response matches AudioTranscriptResponse schema."""
    response = client.get(
        f"/audio/{test_audio.id}/transcript",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()

    # Validate data types
    assert isinstance(data["audio_id"], int)
    assert isinstance(data["raw_text_with_formatting"], str)
    assert isinstance(data["plain_text"], str)
    assert isinstance(data["detected_language"], (str, type(None)))
    assert isinstance(data["duration_seconds"], (int, type(None)))
    assert isinstance(data["created_at"], str)  # ISO format datetime
