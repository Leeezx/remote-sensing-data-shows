"""Authentication utilities — JWT handling and role-based access control."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# --- Configuration ---

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# Generate default demo user hashes at module load time.
_default_viewer_hash = bcrypt.hashpw(b"viewer123", bcrypt.gensalt()).decode()
_default_researcher_hash = bcrypt.hashpw(b"researcher123", bcrypt.gensalt()).decode()

_raw_users = os.getenv(
    "DEMO_USERS",
    f"viewer:{_default_viewer_hash}:viewer,"
    f"researcher:{_default_researcher_hash}:researcher",
)

security = HTTPBearer(auto_error=False)


def _parse_demo_users(raw: str) -> dict[str, dict]:
    """Parse the DEMO_USERS env string into a dict of {username: {hash, role}}."""
    users = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":", 2)
        if len(parts) == 3:
            users[parts[0]] = {"hash": parts[1], "role": parts[2]}
    return users


DEMO_USERS = _parse_demo_users(_raw_users)


# --- Password helpers ---

def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# --- Token helpers ---

def create_access_token(username: str, role: str) -> str:
    """Create a JWT access token."""
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token. Raises on invalid/expired."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# --- FastAPI dependencies ---

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Extract and validate the JWT from the Authorization header.

    Returns a dict with `username` and `role` keys.
    Raises 401 if the token is missing, invalid, or expired.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return {"username": payload["sub"], "role": payload["role"]}


def require_role(*allowed_roles: str):
    """Dependency factory: only allows access if the current user has one of the allowed roles.

    Usage:
        @router.get("/protected", dependencies=[Depends(require_role("researcher"))])
    """

    async def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return role_checker
