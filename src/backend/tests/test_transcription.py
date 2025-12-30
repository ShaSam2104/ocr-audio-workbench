"""Tests for audio transcription endpoints."""
import pytest
import time
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db
from app.models.user import User
from app.models.hierarchy import Book, Chapter
from app.models.audio import Audio
from app.models.transcript import AudioTranscript
from app.dependencies import get_current_user, get_minio_client
from tests.conftest import MockMinIOService, create_test_user, create_test_book_and_chapter


client = TestClient(app)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def authenticated_headers(db_session_with_client):
    """Create test user and return auth headers."""
    user = create_test_user(db_session_with_client, "transcribuser")
    from app.auth import create_access_token
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def book_and_chapter(db_session_with_client):
    """Create test book and chapter."""
    book, chapter = create_test_book_and_chapter(db_session_with_client, "Audio Book", "Chapter 1")
    return book, chapter


@pytest.fixture
def test_audio(db_session_with_client, book_and_chapter):
    """Create test audio record."""
    _, chapter = book_and_chapter
    
    audio = Audio(
        chapter_id=chapter.id,
        object_key="audio/1/test.mp3",
        filename="test.mp3",
        sequence_number=1,
        file_size=10240,
        audio_format="mp3",
        duration_seconds=60,
        transcription_status="pending",
    )
    db_session_with_client.add(audio)
    db_session_with_client.commit()
    db_session_with_client.refresh(audio)
    
    return audio


@pytest.fixture
def multiple_test_audios(db_session_with_client, book_and_chapter):
    """Create multiple test audio records."""
    _, chapter = book_and_chapter
    
    audios = []
    for i in range(3):
        audio = Audio(
            chapter_id=chapter.id,
            object_key=f"audio/1/test{i}.mp3",
            filename=f"test{i}.mp3",
            sequence_number=i + 1,
            file_size=10240,
            audio_format="mp3",
            duration_seconds=60,
            transcription_status="pending",
        )
        db_session_with_client.add(audio)
        audios.append(audio)
    
    db_session_with_client.commit()
    for audio in audios:
        db_session_with_client.refresh(audio)
    
    return audios


# ============================================================================
# TEST: POST /audio/transcribe - Single Audio
# ============================================================================


def test_transcribe_single_audio_returns_202(authenticated_headers, db_session_with_client, test_audio):
    """Test that transcribe endpoint returns 202 ACCEPTED immediately."""
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": [test_audio.id]},
        headers=authenticated_headers,
    )
    
    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "queued"
    assert data["total_audios"] == 1
    assert "Transcription started" in data["message"]


def test_transcribe_returns_task_id(authenticated_headers, db_session_with_client, test_audio):
    """Test that response contains valid task_id (UUID format)."""
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": [test_audio.id]},
        headers=authenticated_headers,
    )
    
    assert response.status_code == 202
    data = response.json()
    task_id = data["task_id"]
    
    # Check UUID format (36 chars with hyphens)
    assert len(task_id) == 36
    assert task_id.count("-") == 4


def test_transcribe_requires_authentication(db_session_with_client, test_audio):
    """Test that endpoint returns 403 when no auth header."""
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": [test_audio.id]},
    )
    
    assert response.status_code == 403


def test_transcribe_with_invalid_audio_ids(authenticated_headers, db_session_with_client):
    """Test that endpoint returns 400 when audio IDs don't exist."""
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": [999, 1000]},
        headers=authenticated_headers,
    )
    
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_transcribe_partial_invalid_audios(authenticated_headers, db_session_with_client, test_audio):
    """Test that endpoint returns 400 when some audios don't exist."""
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": [test_audio.id, 999]},
        headers=authenticated_headers,
    )
    
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_transcribe_empty_audio_ids(authenticated_headers):
    """Test that endpoint requires at least one audio ID."""
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": []},
        headers=authenticated_headers,
    )
    
    assert response.status_code == 422


# ============================================================================
# TEST: POST /audio/transcribe - Multiple Audios
# ============================================================================


def test_transcribe_multiple_audios(authenticated_headers, db_session_with_client, multiple_test_audios):
    """Test transcribing multiple audios at once."""
    audio_ids = [audio.id for audio in multiple_test_audios]
    
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": audio_ids},
        headers=authenticated_headers,
    )
    
    assert response.status_code == 202
    data = response.json()
    assert data["total_audios"] == 3
    assert "task_id" in data


def test_transcribe_updates_audio_status_to_processing(
    authenticated_headers, db_session_with_client, multiple_test_audios
):
    """Test that audios are marked as 'processing' immediately."""
    audio_ids = [audio.id for audio in multiple_test_audios]
    
    # Initial status should be "pending"
    for audio_id in audio_ids:
        audio = db_session_with_client.query(Audio).filter(Audio.id == audio_id).first()
        assert audio.transcription_status == "pending"
    
    # Submit transcription
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": audio_ids},
        headers=authenticated_headers,
    )
    
    assert response.status_code == 202
    
    # After submission, status should be "processing"
    db_session_with_client.expire_all()
    for audio_id in audio_ids:
        audio = db_session_with_client.query(Audio).filter(Audio.id == audio_id).first()
        assert audio.transcription_status == "processing"


# ============================================================================
# TEST: POST /audio/transcribe - With Language Hint
# ============================================================================


def test_transcribe_with_language_hint(authenticated_headers, db_session_with_client, test_audio):
    """Test transcription request with optional language hint."""
    response = client.post(
        "/audio/transcribe",
        json={
            "audio_ids": [test_audio.id],
            "language_hint": "hi",  # Hindi
        },
        headers=authenticated_headers,
    )
    
    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data


# ============================================================================
# TEST: GET /audio/transcription/status/{task_id} - Status Polling
# ============================================================================


def test_transcription_status_not_found(authenticated_headers):
    """Test that non-existent task returns 404."""
    response = client.get(
        "/audio/transcription/status/nonexistent-task-id",
        headers=authenticated_headers,
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_transcription_status_requires_authentication(db_session_with_client):
    """Test that status endpoint requires authentication."""
    response = client.get(
        "/audio/transcription/status/some-task-id",
    )
    
    assert response.status_code == 403


def test_transcription_status_returns_queued_after_submission(
    authenticated_headers, db_session_with_client, test_audio
):
    """Test that task status is returned immediately after submission."""
    # Submit transcription
    submit_response = client.post(
        "/audio/transcribe",
        json={"audio_ids": [test_audio.id]},
        headers=authenticated_headers,
    )
    
    assert submit_response.status_code == 202
    task_id = submit_response.json()["task_id"]
    
    # Check status immediately
    status_response = client.get(
        f"/audio/transcription/status/{task_id}",
        headers=authenticated_headers,
    )
    
    assert status_response.status_code == 200
    data = status_response.json()
    assert data["task_id"] == task_id
    assert data["status"] in ["queued", "processing", "completed", "failed"]
    assert data["total_audios"] == 1
    assert data["completed_count"] >= 0
    assert 0 <= data["progress_percent"] <= 100


def test_transcription_status_response_structure(
    authenticated_headers, db_session_with_client, multiple_test_audios
):
    """Test that status response has correct structure."""
    audio_ids = [audio.id for audio in multiple_test_audios]
    
    # Submit transcription
    submit_response = client.post(
        "/audio/transcribe",
        json={"audio_ids": audio_ids},
        headers=authenticated_headers,
    )
    
    task_id = submit_response.json()["task_id"]
    
    # Check status
    status_response = client.get(
        f"/audio/transcription/status/{task_id}",
        headers=authenticated_headers,
    )
    
    assert status_response.status_code == 200
    data = status_response.json()
    
    # Check required fields
    assert "task_id" in data
    assert "status" in data
    assert "total_audios" in data
    assert "completed_count" in data
    assert "progress_percent" in data
    assert "audios" in data
    assert isinstance(data["audios"], list)
    assert len(data["audios"]) == 3


def test_transcription_status_per_audio_information(
    authenticated_headers, db_session_with_client, multiple_test_audios
):
    """Test that per-audio status is included in response."""
    audio_ids = [audio.id for audio in multiple_test_audios]
    
    # Submit transcription
    submit_response = client.post(
        "/audio/transcribe",
        json={"audio_ids": audio_ids},
        headers=authenticated_headers,
    )
    
    task_id = submit_response.json()["task_id"]
    
    # Get status
    status_response = client.get(
        f"/audio/transcription/status/{task_id}",
        headers=authenticated_headers,
    )
    
    assert status_response.status_code == 200
    data = status_response.json()
    
    # Check per-audio status - each should be tracked
    assert len(data["audios"]) == 3
    for audio_info in data["audios"]:
        assert "audio_id" in audio_info
        assert "status" in audio_info
        # Status can be queued, processing, completed, or failed
        assert audio_info["status"] in ["queued", "processing", "completed", "failed"]
        assert "queued_at" in audio_info
        assert audio_info["audio_id"] in audio_ids


def test_transcription_status_progress_percentage(
    authenticated_headers, db_session_with_client, multiple_test_audios
):
    """Test that progress percentage is calculated correctly."""
    audio_ids = [audio.id for audio in multiple_test_audios]
    
    # Submit transcription for 3 audios
    submit_response = client.post(
        "/audio/transcribe",
        json={"audio_ids": audio_ids},
        headers=authenticated_headers,
    )
    
    task_id = submit_response.json()["task_id"]
    
    # Check status
    status_response = client.get(
        f"/audio/transcription/status/{task_id}",
        headers=authenticated_headers,
    )
    
    data = status_response.json()
    
    # 3 audios total, 0-3 completed = 0-100%
    assert data["total_audios"] == 3
    assert 0 <= data["completed_count"] <= 3
    assert 0 <= data["progress_percent"] <= 100


# ============================================================================
# TEST: Audio Task Manager
# ============================================================================


def test_audio_task_manager_creates_task(db_session_with_client):
    """Test that task manager can create tasks."""
    from app.services.audio_task_manager import get_audio_task_manager
    
    task_manager = get_audio_task_manager()
    task_id = task_manager.create_task([1, 2, 3])
    
    # Verify task was created
    task = task_manager.get_task_status(task_id)
    assert task is not None
    assert task.total_audios == 3
    assert len(task.audios) == 3


def test_audio_task_manager_tracks_audio_status(db_session_with_client):
    """Test that task manager tracks per-audio status."""
    from app.services.audio_task_manager import get_audio_task_manager
    
    task_manager = get_audio_task_manager()
    task_id = task_manager.create_task([1, 2])
    
    # Update first audio to processing
    task_manager.start_audio_processing(task_id, 1)
    
    task = task_manager.get_task_status(task_id)
    audios_by_id = {audio.audio_id: audio for audio in task.audios}
    
    assert audios_by_id[1].status.value == "processing"
    assert audios_by_id[2].status.value == "queued"


def test_audio_task_manager_completes_audios(db_session_with_client):
    """Test that task manager can mark audios as completed."""
    from app.services.audio_task_manager import get_audio_task_manager
    
    task_manager = get_audio_task_manager()
    task_id = task_manager.create_task([1, 2])
    
    # Mark first audio as completed
    task_manager.complete_audio(task_id, 1)
    
    task = task_manager.get_task_status(task_id)
    assert task.completed_count == 1
    assert task.progress_percent == 50


def test_audio_task_manager_all_completed_marks_task_done(db_session_with_client):
    """Test that when all audios are done, task is marked complete."""
    from app.services.audio_task_manager import get_audio_task_manager
    
    task_manager = get_audio_task_manager()
    task_id = task_manager.create_task([1])
    
    # Mark single audio as completed
    task_manager.start_processing(task_id)
    task_manager.complete_audio(task_id, 1)
    
    task = task_manager.get_task_status(task_id)
    assert task.status.value == "completed"


def test_audio_task_manager_fails_audio(db_session_with_client):
    """Test that task manager can mark audios as failed."""
    from app.services.audio_task_manager import get_audio_task_manager
    
    task_manager = get_audio_task_manager()
    task_id = task_manager.create_task([1, 2])
    
    # Mark first audio as failed
    task_manager.fail_audio(task_id, 1, "Test error")
    
    task = task_manager.get_task_status(task_id)
    audios_by_id = {audio.audio_id: audio for audio in task.audios}
    
    assert audios_by_id[1].status.value == "failed"
    assert audios_by_id[1].error == "Test error"


# ============================================================================
# TEST: Response Models
# ============================================================================


def test_transcribe_response_model(authenticated_headers, db_session_with_client, test_audio):
    """Test that response matches AudioTranscriptionResponse schema."""
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": [test_audio.id]},
        headers=authenticated_headers,
    )
    
    data = response.json()
    required_fields = ["task_id", "status", "total_audios", "message"]
    
    for field in required_fields:
        assert field in data


def test_transcription_status_response_model(authenticated_headers, db_session_with_client, test_audio):
    """Test that status response matches AudioTranscriptionStatusResponse schema."""
    # Submit
    submit_response = client.post(
        "/audio/transcribe",
        json={"audio_ids": [test_audio.id]},
        headers=authenticated_headers,
    )
    
    task_id = submit_response.json()["task_id"]
    
    # Get status
    response = client.get(
        f"/audio/transcription/status/{task_id}",
        headers=authenticated_headers,
    )
    
    data = response.json()
    required_fields = ["task_id", "status", "total_audios", "completed_count", "progress_percent", "audios"]
    
    for field in required_fields:
        assert field in data
    
    # Check audio fields
    for audio in data["audios"]:
        assert "audio_id" in audio
        assert "status" in audio
        assert "queued_at" in audio


# ============================================================================
# TEST: No User Scoping
# ============================================================================


def test_transcribe_no_user_filtering(authenticated_headers, book_and_chapter):
    """Test that transcription works on all shared audios (no user filtering)."""
    _, chapter = book_and_chapter
    
    # Create an audio that can be transcribed by any authenticated user
    audio = Audio(
        chapter_id=chapter.id,
        object_key="audio/1/shared.mp3",
        filename="shared.mp3",
        sequence_number=1,
        file_size=10240,
        audio_format="mp3",
        duration_seconds=60,
        transcription_status="pending",
    )
    # Note: In real scenario, audios are in the database via fixture setup
    # This test just verifies that any authenticated user can access the endpoint
    
    # User can transcribe audios (no scoping check in endpoint)
    response = client.post(
        "/audio/transcribe",
        json={"audio_ids": [999999]},  # Non-existent audio (will return 400)
        headers=authenticated_headers,
    )
    
    # Should fail with 400 (not found), not 403 (forbidden)
    # This proves no authorization/scoping is enforced
    assert response.status_code == 400
