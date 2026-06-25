"""Authentication router — login endpoint."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.auth import DEMO_USERS, create_access_token, verify_password

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    user: dict


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    """Authenticate a user and return a JWT access token."""
    user_record = DEMO_USERS.get(body.username)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not verify_password(body.password, user_record["hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(body.username, user_record["role"])
    return {
        "access_token": token,
        "user": {
            "username": body.username,
            "role": user_record["role"],
        },
    }
