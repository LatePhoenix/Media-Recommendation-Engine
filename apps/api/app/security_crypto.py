from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet

from app.config import get_settings


def _load_keys() -> tuple[Fernet, MultiFernet]:
    """Build the encrypt/decrypt Fernets from configuration.

    A dedicated ``CREDENTIALS_FERNET_KEY`` is required — the key is deliberately
    *not* derived from ``api_secret_key`` so that at-rest credential encryption is
    independent from the JWT signing key, and rotating the signing key never
    silently invalidates stored credentials.

    ``CREDENTIALS_FERNET_KEYS_OLD`` (comma-separated) may hold prior keys so that
    ciphertext written before a rotation can still be decrypted. New tokens are
    always encrypted with the primary key.
    """
    settings = get_settings()
    primary = settings.credentials_fernet_key.strip()
    if not primary:
        raise RuntimeError(
            "CREDENTIALS_FERNET_KEY is required to encrypt import-source credentials. "
            "Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    try:
        primary_fernet = Fernet(primary.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "CREDENTIALS_FERNET_KEY is not a valid Fernet key (expected 32 url-safe base64 bytes)."
        ) from exc

    old_keys = [k.strip() for k in settings.credentials_fernet_keys_old.split(",") if k.strip()]
    try:
        rotation = MultiFernet([primary_fernet, *(Fernet(k.encode()) for k in old_keys)])
    except (ValueError, TypeError) as exc:
        raise RuntimeError("CREDENTIALS_FERNET_KEYS_OLD contains an invalid Fernet key.") from exc

    return primary_fernet, rotation


def encrypt_credentials(plaintext: str) -> str:
    primary, _ = _load_keys()
    return primary.encrypt(plaintext.encode()).decode()


def decrypt_credentials(token: str) -> str:
    _, rotation = _load_keys()
    return rotation.decrypt(token.encode()).decode()


def ensure_fernet_key() -> str:
    return Fernet.generate_key().decode()
