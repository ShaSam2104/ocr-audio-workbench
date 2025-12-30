"""Test configuration and fixtures."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.database import Base, get_db
from app.main import app
from app.models.user import User
from app.models.hierarchy import Book, Chapter
from app.models.image import Image
from app.models.audio import Audio
from app.models.ocr import OCRText
from app.models.transcript import AudioTranscript
from app.auth import hash_password, create_access_token
from app.dependencies import get_minio_client
from tests.fixtures.minio_mock import MockMinIOService

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_test_user(session, username: str, password: str = "testpassword123") -> User:
    """Create a test user and return it."""
    user = User(
        username=username,
        hashed_password=hash_password(password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_test_book(session, name: str, description: str = None) -> Book:
    """Create a test book."""
    book = Book(
        name=name,
        description=description or f"Test book: {name}",
    )
    session.add(book)
    session.commit()
    session.refresh(book)
    return book


def create_test_chapter(session, book_id: int, name: str, description: str = None) -> Chapter:
    """Create a test chapter."""
    chapter = Chapter(
        book_id=book_id,
        name=name,
        description=description or f"Test chapter: {name}",
        sequence_order=1,
    )
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return chapter


def create_test_image_with_ocr(
    session,
    chapter_id: int,
    filename: str,
    sequence_number: int,
    ocr_text: str = "Test OCR text",
) -> Image:
    """Create a test image with OCR text."""
    image = Image(
        chapter_id=chapter_id,
        object_key=f"images/{chapter_id}/{filename}",
        filename=filename,
        sequence_number=sequence_number,
        file_size=1024,
        file_hash="test_hash",
        ocr_status="completed",
    )
    session.add(image)
    session.flush()

    # Add OCR text
    ocr = OCRText(
        image_id=image.id,
        raw_text_with_formatting=ocr_text,
        plain_text_for_search=ocr_text.replace("**", "").replace("*", "").replace("__", ""),
        detected_language="en",
        processing_time_ms=1000,
    )
    session.add(ocr)
    session.commit()

    return image


def create_test_audio_with_transcript(
    session,
    chapter_id: int,
    filename: str,
    sequence_number: int,
    transcript_text: str = "Test transcript text",
    duration_seconds: int = 120,
    audio_format: str = "mp3",
) -> Audio:
    """Create a test audio with transcript."""
    audio = Audio(
        chapter_id=chapter_id,
        object_key=f"audio/{chapter_id}/{filename}",
        filename=filename,
        sequence_number=sequence_number,
        duration_seconds=duration_seconds,
        audio_format=audio_format,
        file_size=2048,
        transcription_status="completed",
    )
    session.add(audio)
    session.flush()

    # Add transcript
    transcript = AudioTranscript(
        audio_id=audio.id,
        raw_text_with_formatting=transcript_text,
        plain_text_for_search=transcript_text.replace("**", "").replace("*", "").replace("__", ""),
        detected_language="en",
        processing_time_ms=2000,
    )
    session.add(transcript)
    session.commit()

    return audio



def create_test_book_and_chapter(session, book_name: str, chapter_name: str) -> tuple:
    """Create a test book and chapter."""
    book = Book(
        name=book_name,
        description="Test book",
    )
    session.add(book)
    session.commit()
    session.refresh(book)
    
    chapter = Chapter(
        book_id=book.id,
        name=chapter_name,
        description="Test chapter",
        sequence_order=1,
    )
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    
    return book, chapter


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine."""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_db_session(test_engine):
    """Create test database session."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def mock_minio_service():
    """Create mock MinIO service for testing."""
    return MockMinIOService()


@pytest.fixture(scope="function")
def db_session_with_client(test_engine, mock_minio_service):
    """Create test database session with client override for each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()

    # Override the get_db dependency with this session
    def _override_get_db():
        try:
            yield session
        finally:
            pass

    # Override MinIO dependency with mock service
    def _override_get_minio_client():
        return mock_minio_service

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_minio_client] = _override_get_minio_client
    yield session
    app.dependency_overrides.clear()
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def db_session(db_session_with_client):
    """Alias for test database session."""
    return db_session_with_client


@pytest.fixture
def client(db_session_with_client):
    """FastAPI test client with database session override."""
    return TestClient(app)


@pytest.fixture
def test_user(db_session_with_client) -> User:
    """Create a test user."""
    user = User(
        username="testuser",
        hashed_password=hash_password("testpassword123"),
    )
    db_session_with_client.add(user)
    db_session_with_client.commit()
    db_session_with_client.refresh(user)
    return user


@pytest.fixture
def test_user_2(db_session_with_client) -> User:
    """Create a second test user."""
    user = User(
        username="testuser2",
        hashed_password=hash_password("password456"),
    )
    db_session_with_client.add(user)
    db_session_with_client.commit()
    db_session_with_client.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    """Get authorization headers with valid token."""
    response = client.post(
        "/auth/login",
        json={"username": test_user.username, "password": "testpassword123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
