from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, get_user_by_username, hash_password, verify_password
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.rate_limit import IPRateLimiter, enforce_rate_limit
from app.schemas import TokenOut, UserCreate, UserOut, UserPrefsUpdate

settings = get_settings()

router = APIRouter(prefix="/api/auth", tags=["auth"])

_login_ip_limiter = IPRateLimiter("login", settings.login_rate_limit_per_minute, 60)
_register_ip_limiter = IPRateLimiter("register", settings.register_rate_limit_per_hour, 3600)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_register_ip_limiter)],
)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if not settings.registration_enabled and db.query(User).count() > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled.",
        )
    # Return a single generic message for both collisions so an attacker cannot use
    # registration to enumerate which usernames/emails already have accounts.
    existing = (
        db.query(User)
        .filter((User.username == payload.username) | (User.email == payload.email))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="That username or email is not available."
        )
    is_first = db.query(User).count() == 0
    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        is_admin=is_first,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut, dependencies=[Depends(_login_ip_limiter)])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenOut:
    # Per-username limit as well, so one account can't be brute-forced from many IPs.
    enforce_rate_limit(
        f"rl:login:user:{form_data.username.lower()}",
        settings.login_rate_limit_per_username_per_minute,
        60,
    )
    user = get_user_by_username(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token(
        str(user.id),
        extra={"username": user.username},
        token_version=user.token_version,
    )
    return TokenOut(access_token=token)


@router.post("/logout-all")
def logout_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Invalidate every outstanding token for this user by advancing the token version.
    user.token_version = (user.token_version or 0) + 1
    db.add(user)
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UserPrefsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if payload.enabled_media_types is not None:
        user.enabled_media_types = payload.enabled_media_types
    if payload.preferences is not None:
        user.preferences = {**(user.preferences or {}), **payload.preferences}
    if payload.onboarding_complete is not None:
        user.onboarding_complete = payload.onboarding_complete
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
