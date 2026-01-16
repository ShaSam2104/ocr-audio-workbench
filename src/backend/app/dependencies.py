"""Dependency injection for FastAPI endpoints."""
from typing import Optional
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.auth import decode_access_token
from app.services.minio_service import MinIOService
from app.config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_SECURE
from app.logger import logger


# MinIO service singleton
_minio_service: Optional[MinIOService] = None


def get_minio_client() -> MinIOService:
    """
    Get or create MinIO client singleton.

    Returns:
        MinIOService instance
    """
    global _minio_service
    if _minio_service is None:
        _minio_service = MinIOService(
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
    return _minio_service


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db),
) -> User:
    """
    Extract and validate JWT token from Authorization header.
    Return User object or raise 401 Unauthorized.

    This is used as a dependency on protected endpoints.
    NO authorization checks - only authentication is required.

    Args:
        authorization: Authorization header (Bearer token)
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: 403 if no token provided, 401 if token invalid
    """
    # Log the credentials received
    logger.debug(f"get_current_user called with credentials: {credentials}")
    print(f"[AUTH DEBUG] Credentials object: {credentials}", flush=True)
    
    if credentials:
        print(f"[AUTH DEBUG] Credentials.credentials: {credentials.credentials}", flush=True)
        logger.debug(f"Credentials.credentials: {credentials.credentials}")
    
    # If HTTPBearer returned no credentials (auto_error=False), treat as missing
    if not credentials or not getattr(credentials, "credentials", None):
        logger.warning(f"Missing authorization credentials. Credentials: {credentials}")
        print(f"[AUTH DEBUG] Missing auth - credentials={credentials}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing authorization credentials",
        )

    token = credentials.credentials
    logger.debug(f"Extracted token: {token[:20]}..." if len(token) > 20 else f"Token: {token}")
    print(f"[AUTH DEBUG] Token extracted (first 50 chars): {token[:50]}", flush=True)

    # Decode the token
    payload = decode_access_token(token)
    logger.debug(f"Token decode result: {payload}")
    print(f"[AUTH DEBUG] Token decode payload: {payload}", flush=True)
    
    if payload is None:
        logger.warning("Invalid or expired token")
        print(f"[AUTH DEBUG] Token is None/invalid", flush=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user_id from token payload (convert from string to int)
    user_id_str: Optional[str] = payload.get("sub")
    logger.debug(f"Extracted user_id from token: {user_id_str}")
    print(f"[AUTH DEBUG] User ID from token: {user_id_str}", flush=True)
    
    if user_id_str is None:
        logger.warning("Invalid token payload - no 'sub' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        logger.warning(f"Could not convert user_id to int: {user_id_str}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Query database for user
    user = db.query(User).filter(User.id == user_id).first()
    logger.debug(f"Database query for user_id {user_id}: {user}")
    print(f"[AUTH DEBUG] User found in DB: {user}", flush=True)
    
    if user is None:
        logger.warning(f"User not found for user_id: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
