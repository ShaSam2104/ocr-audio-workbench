"""Authentication routes - NO authorization checks (authentication only)."""
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from datetime import timedelta
from app.database import get_db
from app.models.user import User
from app.schemas.user import LoginSchema, TokenSchema, UserSchema
from app.schemas.response import MessageResponse
from app.auth import hash_password, verify_password, create_access_token
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenSchema, status_code=status.HTTP_200_OK)
async def login(
    credentials: LoginSchema,
    db: Session = Depends(get_db),
) -> dict:
    """
    Login endpoint - authenticate user and return JWT token.

    Args:
        credentials: Login credentials (username, password)
        db: Database session

    Returns:
        TokenSchema with access_token, token_type, user_id, username

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    # Find user by username
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Verify password
    if not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Create JWT token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username},
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
    }


@router.post("/logout", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def logout() -> MessageResponse:
    """
    Logout endpoint - optional (token invalidation is handled client-side).

    Returns:
        Confirmation message
    """
    return MessageResponse(message="Logged out successfully")


@router.post("/register", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def register(
    credentials: LoginSchema,
    db: Session = Depends(get_db),
) -> dict:
    """
    Register a new user - optional endpoint.

    Args:
        credentials: Registration credentials (username, password)
        db: Database session

    Returns:
        UserSchema with id, username, created_at

    Raises:
        HTTPException: 409 if username already exists
    """
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == credentials.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    # Hash password
    hashed_password = hash_password(credentials.password)

    # Create new user
    new_user = User(
        username=credentials.username,
        hashed_password=hashed_password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "id": new_user.id,
        "username": new_user.username,
        "created_at": new_user.created_at,
    }
