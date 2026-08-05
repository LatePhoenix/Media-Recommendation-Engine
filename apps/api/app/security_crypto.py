from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.credentials_fernet_key.strip()
    if key:
        return Fernet(key.encode())
    # Derive a stable local-dev key from API secret (set CREDENTIALS_FERNET_KEY in production)
    digest = hashlib.sha256(settings.api_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_credentials(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_credentials(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def ensure_fernet_key() -> str:
    return Fernet.generate_key().decode()
