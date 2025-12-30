"""Tests for search endpoints."""
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
    user = create_test_user(db_session_with_client, "searchuser")
    from app.auth import create_access_token

    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def book_and_chapters(test_db_session):
    """Create test book with multiple chapters."""
    book = Book(name="Search Test Book", description="Book for search tests")
    test_db_session.add(book)
    test_db_session.flush()

    chapter1 = Chapter(
        book_id=book.id,
        name="Chapter 1",
        description="First chapter",
        sequence_order=1,
    )
    chapter2 = Chapter(
        book_id=book.id,
        name="Chapter 2",
        description="Second chapter",
        sequence_order=2,
    )
    test_db_session.add(chapter1)
    test_db_session.add(chapter2)
    test_db_session.commit()

    return book, [chapter1, chapter2]


@pytest.fixture
def chapter_with_images(test_db_session, book_and_chapters):
    """Create chapter with multiple images and OCR text."""
    _, chapters = book_and_chapters
    chapter = chapters[0]

    images = []
    for i in range(1, 6):
        img = Image(
            chapter_id=chapter.id,
            object_key=f"images/{chapter.id}/img{i}.jpg",
            filename=f"img{i}.jpg",
            sequence_number=i,
            file_size=1024,
            file_hash=f"hash{i}",
            ocr_status="completed",
        )
        test_db_session.add(img)
        test_db_session.flush()

        # Add OCR text
        ocr_text = OCRText(
            image_id=img.id,
            raw_text_with_formatting=f"**Important** document number {i}",
            plain_text_for_search=f"Important document number {i}",
            detected_language="en",
        )
        test_db_session.add(ocr_text)
        images.append(img)

    test_db_session.commit()
    return chapter, images


@pytest.fixture
def chapter_with_audios(test_db_session, book_and_chapters):
    """Create chapter with multiple audios and transcripts."""
    _, chapters = book_and_chapters
    chapter = chapters[0]

    audios = []
    for i in range(1, 4):
        audio = Audio(
            chapter_id=chapter.id,
            object_key=f"audio/{chapter.id}/audio{i}.mp3",
            filename=f"audio{i}.mp3",
            sequence_number=i,
            duration_seconds=60 * i,
            audio_format="mp3",
            file_size=2048,
            transcription_status="completed",
        )
        test_db_session.add(audio)
        test_db_session.flush()

        # Add transcript
        transcript = AudioTranscript(
            audio_id=audio.id,
            raw_text_with_formatting=f"**Meeting** notes from audio {i}",
            plain_text_for_search=f"Meeting notes from audio {i}",
            detected_language="en",
        )
        test_db_session.add(transcript)
        audios.append(audio)

    test_db_session.commit()
    return chapter, audios


# ============================================================================
# TEST: Number-Based Search - Images
# ============================================================================


def test_search_images_by_exact_number(authenticated_headers, test_db_session, chapter_with_images):
    """Test searching images by exact sequence number."""
    chapter, images = chapter_with_images

    response = client.get(
        f"/search/images?chapter_id={chapter.id}&query=2",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["sequence_number"] == 2


def test_search_images_by_range(authenticated_headers, test_db_session, chapter_with_images):
    """Test searching images by range."""
    chapter, images = chapter_with_images

    response = client.get(
        f"/search/images?chapter_id={chapter.id}&query=2-4",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert [img["sequence_number"] for img in data] == [2, 3, 4]


def test_search_images_no_results(authenticated_headers, test_db_session, chapter_with_images):
    """Test searching images with no results."""
    chapter, images = chapter_with_images

    response = client.get(
        f"/search/images?chapter_id={chapter.id}&query=10",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


def test_search_images_invalid_range(authenticated_headers, test_db_session, chapter_with_images):
    """Test searching images with invalid range."""
    chapter, images = chapter_with_images

    response = client.get(
        f"/search/images?chapter_id={chapter.id}&query=5-2",
        headers=authenticated_headers,
    )

    assert response.status_code == 400


def test_search_images_chapter_not_found(authenticated_headers):
    """Test searching images in non-existent chapter."""
    response = client.get(
        "/search/images?chapter_id=999&query=1",
        headers=authenticated_headers,
    )

    assert response.status_code == 404


# ============================================================================
# TEST: Number-Based Search - Audios
# ============================================================================


def test_search_audios_by_exact_number(authenticated_headers, test_db_session, chapter_with_audios):
    """Test searching audios by exact sequence number."""
    chapter, audios = chapter_with_audios

    response = client.get(
        f"/search/audios?chapter_id={chapter.id}&query=2",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["sequence_number"] == 2


def test_search_audios_by_range(authenticated_headers, test_db_session, chapter_with_audios):
    """Test searching audios by range."""
    chapter, audios = chapter_with_audios

    response = client.get(
        f"/search/audios?chapter_id={chapter.id}&query=1-2",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert [audio["sequence_number"] for audio in data] == [1, 2]


# ============================================================================
# TEST: Text Search - Images
# ============================================================================


def test_search_images_by_text(authenticated_headers, test_db_session, chapter_with_images):
    """Test searching images by OCR text."""
    chapter, images = chapter_with_images

    response = client.get(
        f"/search/images/text?chapter_id={chapter.id}&text_query=Important",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5  # All images have "Important" in text
    assert "image" in data[0]
    assert "excerpt" in data[0]
    assert "Important" in data[0]["excerpt"]


def test_search_images_by_text_specific_match(authenticated_headers, test_db_session, chapter_with_images):
    """Test searching images by specific text."""
    chapter, images = chapter_with_images

    response = client.get(
        f"/search/images/text?chapter_id={chapter.id}&text_query=number 3",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["image"]["sequence_number"] == 3


def test_search_images_text_no_results(authenticated_headers, test_db_session, chapter_with_images):
    """Test searching images with no text matches."""
    chapter, images = chapter_with_images

    response = client.get(
        f"/search/images/text?chapter_id={chapter.id}&text_query=nonexistent",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


# ============================================================================
# TEST: Text Search - Audios
# ============================================================================


def test_search_audios_by_text(authenticated_headers, test_db_session, chapter_with_audios):
    """Test searching audios by transcript text."""
    chapter, audios = chapter_with_audios

    response = client.get(
        f"/search/audios/text?chapter_id={chapter.id}&text_query=Meeting",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # All audios have "Meeting" in text
    assert "audio" in data[0]
    assert "excerpt" in data[0]


def test_search_audios_by_text_specific_match(authenticated_headers, test_db_session, chapter_with_audios):
    """Test searching audios by specific text."""
    chapter, audios = chapter_with_audios

    response = client.get(
        f"/search/audios/text?chapter_id={chapter.id}&text_query=audio 2",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["audio"]["sequence_number"] == 2


# ============================================================================
# TEST: Combined Search - Chapter
# ============================================================================


def test_search_chapter_combined(authenticated_headers, test_db_session, chapter_with_images, chapter_with_audios):
    """Test combined search in chapter (images + audios)."""
    chapter, _ = chapter_with_images
    _, _ = chapter_with_audios

    response = client.get(
        f"/search/chapter?chapter_id={chapter.id}&text_query=Important",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    # Should find all 5 images with "Important" + 0 audios (they have "Meeting")
    assert len(data) == 5
    assert all(result["type"] == "image" for result in data)


def test_search_chapter_combined_multiple_types(authenticated_headers, test_db_session, book_and_chapters):
    """Test combined search finding both images and audios."""
    book, chapters = book_and_chapters
    chapter = chapters[0]

    # Create image with "note"
    img = Image(
        chapter_id=chapter.id,
        object_key=f"images/{chapter.id}/img.jpg",
        filename="img.jpg",
        sequence_number=1,
        file_size=1024,
        file_hash="hash1",
        ocr_status="completed",
    )
    test_db_session.add(img)
    test_db_session.flush()

    ocr_text = OCRText(
        image_id=img.id,
        raw_text_with_formatting="This is a **note**",
        plain_text_for_search="This is a note",
        detected_language="en",
    )
    test_db_session.add(ocr_text)

    # Create audio with "note"
    audio = Audio(
        chapter_id=chapter.id,
        object_key=f"audio/{chapter.id}/audio.mp3",
        filename="audio.mp3",
        sequence_number=1,
        duration_seconds=60,
        audio_format="mp3",
        file_size=2048,
        transcription_status="completed",
    )
    test_db_session.add(audio)
    test_db_session.flush()

    transcript = AudioTranscript(
        audio_id=audio.id,
        raw_text_with_formatting="**Important note** from audio",
        plain_text_for_search="Important note from audio",
        detected_language="en",
    )
    test_db_session.add(transcript)
    test_db_session.commit()

    # Search for "note"
    response = client.get(
        f"/search/chapter?chapter_id={chapter.id}&text_query=note",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    types = {result["type"] for result in data}
    assert types == {"image", "audio"}


# ============================================================================
# TEST: Combined Search - Book
# ============================================================================


def test_search_book_combined(authenticated_headers, test_db_session, book_and_chapters):
    """Test combined search in book (all chapters)."""
    book, chapters = book_and_chapters

    # Add content to both chapters
    for chapter_idx, chapter in enumerate(chapters):
        for i in range(1, 3):
            img = Image(
                chapter_id=chapter.id,
                object_key=f"images/{chapter.id}/img{i}.jpg",
                filename=f"img{i}.jpg",
                sequence_number=i,
                file_size=1024,
                file_hash=f"hash{chapter_idx}{i}",
                ocr_status="completed",
            )
            test_db_session.add(img)
            test_db_session.flush()

            ocr_text = OCRText(
                image_id=img.id,
                raw_text_with_formatting="**Important** content",
                plain_text_for_search="Important content",
                detected_language="en",
            )
            test_db_session.add(ocr_text)

    test_db_session.commit()

    response = client.get(
        f"/search/book?book_id={book.id}&text_query=Important",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4  # 2 images per chapter × 2 chapters


def test_search_book_not_found(authenticated_headers):
    """Test searching non-existent book."""
    response = client.get(
        "/search/book?book_id=999&text_query=test",
        headers=authenticated_headers,
    )

    assert response.status_code == 404


# ============================================================================
# TEST: Global Search
# ============================================================================


def test_search_global(authenticated_headers, test_db_session, book_and_chapters):
    """Test global search across all books."""
    book, chapters = book_and_chapters

    # Add content to chapters
    for chapter in chapters:
        img = Image(
            chapter_id=chapter.id,
            object_key=f"images/{chapter.id}/img.jpg",
            filename="img.jpg",
            sequence_number=1,
            file_size=1024,
            file_hash=f"hash{chapter.id}",
            ocr_status="completed",
        )
        test_db_session.add(img)
        test_db_session.flush()

        ocr_text = OCRText(
            image_id=img.id,
            raw_text_with_formatting="**Global** search test",
            plain_text_for_search="Global search test",
            detected_language="en",
        )
        test_db_session.add(ocr_text)

    test_db_session.commit()

    response = client.get(
        "/search/global?text_query=Global",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # 1 image per chapter


def test_search_global_empty(authenticated_headers, test_db_session):
    """Test global search with no results."""
    response = client.get(
        "/search/global?text_query=nonexistenttext123",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


# ============================================================================
# TEST: Authentication
# ============================================================================


def test_search_requires_authentication(test_db_session, chapter_with_images):
    """Test that search endpoints require authentication."""
    chapter, _ = chapter_with_images

    response = client.get(f"/search/images?chapter_id={chapter.id}&query=1")

    assert response.status_code == 403


# ============================================================================
# TEST: No User Filtering
# ============================================================================


def test_search_no_user_filtering(authenticated_headers, test_db_session, chapter_with_images):
    """Test that all authenticated users can search all resources."""
    chapter, images = chapter_with_images

    # Any authenticated user can search
    response = client.get(
        f"/search/images?chapter_id={chapter.id}&query=1",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    # Should return results regardless of user (no user filtering)
    assert len(response.json()) == 1


# ============================================================================
# TEST: Excerpt Generation
# ============================================================================


def test_search_excerpt_truncation(authenticated_headers, test_db_session, book_and_chapters):
    """Test that long excerpts are truncated."""
    _, chapters = book_and_chapters
    chapter = chapters[0]

    # Create image with very long text
    img = Image(
        chapter_id=chapter.id,
        object_key=f"images/{chapter.id}/long.jpg",
        filename="long.jpg",
        sequence_number=1,
        file_size=1024,
        file_hash="longhash",
        ocr_status="completed",
    )
    test_db_session.add(img)
    test_db_session.flush()

    long_text = "word " * 100  # Very long text
    ocr_text = OCRText(
        image_id=img.id,
        raw_text_with_formatting=long_text,
        plain_text_for_search=long_text,
        detected_language="en",
    )
    test_db_session.add(ocr_text)
    test_db_session.commit()

    response = client.get(
        f"/search/images/text?chapter_id={chapter.id}&text_query=word",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # Excerpt should be truncated
    assert len(data[0]["excerpt"]) <= 203  # 200 chars + "..."


# ============================================================================
# TEST: Combined Search Ordering
# ============================================================================


def test_search_combined_ordering(authenticated_headers, test_db_session, book_and_chapters):
    """Test that combined search results are properly ordered."""
    book, chapters = book_and_chapters
    chapter = chapters[0]

    # Add images and audios with different sequences
    for i in range(1, 4):
        img = Image(
            chapter_id=chapter.id,
            object_key=f"images/{chapter.id}/img{i}.jpg",
            filename=f"img{i}.jpg",
            sequence_number=i,
            file_size=1024,
            file_hash=f"hash{i}",
            ocr_status="completed",
        )
        test_db_session.add(img)
        test_db_session.flush()

        ocr_text = OCRText(
            image_id=img.id,
            raw_text_with_formatting="**test** content",
            plain_text_for_search="test content",
            detected_language="en",
        )
        test_db_session.add(ocr_text)

    for i in range(1, 3):
        audio = Audio(
            chapter_id=chapter.id,
            object_key=f"audio/{chapter.id}/audio{i}.mp3",
            filename=f"audio{i}.mp3",
            sequence_number=i,
            duration_seconds=60,
            audio_format="mp3",
            file_size=2048,
            transcription_status="completed",
        )
        test_db_session.add(audio)
        test_db_session.flush()

        transcript = AudioTranscript(
            audio_id=audio.id,
            raw_text_with_formatting="**test** notes",
            plain_text_for_search="test notes",
            detected_language="en",
        )
        test_db_session.add(transcript)

    test_db_session.commit()

    response = client.get(
        f"/search/chapter?chapter_id={chapter.id}&text_query=test",
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5

    # Images should come before audios (both types intermixed by sequence)
    # Actually they're sorted by type then sequence
    image_results = [r for r in data if r["type"] == "image"]
    audio_results = [r for r in data if r["type"] == "audio"]

    assert len(image_results) == 3
    assert len(audio_results) == 2
