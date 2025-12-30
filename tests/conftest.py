"""Test configuration and fixtures."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.database import Base, get_db
from app.main import app
from app.models.user import User
from app.auth import hash_password
from app.dependencies import get_minio_client
from tests.fixtures.minio_mock import MockMinIOService

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"


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
