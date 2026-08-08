from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
settings = get_settings()

ALGORITHM = "HS256"

RATING_LABEL_TO_VALUE: dict[str, float] = {
    "Loved it": 2.0,
    "Liked it": 1.0,
    "Meh": 0.0,
    "Disliked it": -1.0,
    "Hated it": -2.0,
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str,
    extra: dict[str, Any] | None = None,
    token_version: int = 0,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": now,
        "jti": uuid4().hex,
        "typ": "access",
        "tv": token_version,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.api_secret_key, algorithm=ALGORITHM)


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.api_secret_key, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None or payload.get("typ") != "access":
            raise credentials_exception
        user_id = UUID(str(sub))
        token_version = int(payload.get("tv", 0))
    except (JWTError, ValueError) as exc:
        raise credentials_exception from exc
    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception
    # Reject tokens issued before the user's current version (revocation / logout-all).
    if token_version != user.token_version:
        raise credentials_exception
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin required",
        )
    return user
