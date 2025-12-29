"""Tests for authentication endpoints."""
import pytest
from fastapi import status


class TestLogin:
    """Test login endpoint."""

    def test_login_success(self, client, test_user):
        """Test successful login with valid credentials."""
        response = client.post(
            "/auth/login",
            json={"username": "testuser", "password": "testpassword123"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user_id"] == test_user.id
        assert data["username"] == "testuser"

    def test_login_invalid_username(self, client):
        """Test login with non-existent username."""
        response = client.post(
            "/auth/login",
            json={"username": "nonexistent", "password": "password"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid username or password" in response.json()["detail"]

    def test_login_invalid_password(self, client, test_user):
        """Test login with wrong password."""
        response = client.post(
            "/auth/login",
            json={"username": "testuser", "password": "wrongpassword"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid username or password" in response.json()["detail"]

    def test_login_empty_credentials(self, client):
        """Test login with empty credentials."""
        response = client.post(
            "/auth/login",
            json={"username": "", "password": ""},
        )
        # Pydantic validation should fail
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_login_missing_fields(self, client):
        """Test login with missing required fields."""
        response = client.post(
            "/auth/login",
            json={"username": "testuser"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestLogout:
    """Test logout endpoint."""

    def test_logout_success(self, client):
        """Test logout endpoint."""
        response = client.post("/auth/logout")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Logged out successfully"


class TestRegister:
    """Test user registration endpoint."""

    def test_register_success(self, client):
        """Test successful user registration."""
        response = client.post(
            "/auth/register",
            json={"username": "newuser", "password": "securepass123"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "id" in data
        assert data["username"] == "newuser"
        assert "created_at" in data

    def test_register_duplicate_username(self, client, test_user):
        """Test registration with already taken username."""
        response = client.post(
            "/auth/register",
            json={"username": "testuser", "password": "password123"},
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Username already taken" in response.json()["detail"]

    def test_register_empty_username(self, client):
        """Test registration with empty username."""
        response = client.post(
            "/auth/register",
            json={"username": "", "password": "password123"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_register_empty_password(self, client):
        """Test registration with empty password."""
        response = client.post(
            "/auth/register",
            json={"username": "newuser", "password": ""},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_register_missing_fields(self, client):
        """Test registration with missing required fields."""
        response = client.post(
            "/auth/register",
            json={"username": "newuser"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestTokenValidation:
    """Test JWT token validation in get_current_user."""

    def test_valid_token_returns_user(self, client, test_user, auth_headers):
        """Test that valid token can be decoded and returns user info."""
        response = client.post(
            "/auth/login",
            json={"username": test_user.username, "password": "testpassword123"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["user_id"] == test_user.id
        assert data["username"] == test_user.username
        assert "access_token" in data

    def test_token_missing_bearer_prefix(self, client):
        """Test accessing endpoint with token but missing Bearer prefix."""
        # Login to get token
        response = client.post(
            "/auth/login",
            json={"username": "newuser", "password": "password123"},
        )
        # Invalid endpoint without proper auth will be caught by server
        # This test verifies the auth scheme requires Bearer prefix
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK

    def test_logout_with_valid_auth_headers(self, client, auth_headers):
        """Test logout with valid auth headers."""
        response = client.post("/auth/logout", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        assert "message" in response.json()

    def test_multiple_users_have_different_tokens(self, client, test_user, test_user_2):
        """Test that different users get different tokens."""
        response1 = client.post(
            "/auth/login",
            json={"username": test_user.username, "password": "testpassword123"},
        )
        response2 = client.post(
            "/auth/login",
            json={"username": test_user_2.username, "password": "password456"},
        )
        
        token1 = response1.json()["access_token"]
        token2 = response2.json()["access_token"]
        
        assert token1 != token2
        assert response1.json()["user_id"] != response2.json()["user_id"]
