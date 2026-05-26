from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Any

from .errors import ValidationError

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 210_000
SESSION_TOKEN_BYTES = 32


def normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if "@" not in email or len(email) > 254:
        raise ValidationError("A valid email is required.")
    local, domain = email.rsplit("@", 1)
    if not local or "." not in domain:
        raise ValidationError("A valid email is required.")
    return email


def validate_password(value: str) -> str:
    password = str(value or "")
    if len(password) < 12:
        raise ValidationError("Password must be at least 12 characters.")
    if len(password) > 256:
        raise ValidationError("Password is too long.")
    return password


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PASSWORD_ITERATIONS) -> str:
    safe_password = validate_password(password)
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", safe_password.encode("utf-8"), actual_salt, iterations)
    return "$".join(
        [
            PASSWORD_SCHEME,
            str(iterations),
            _b64(actual_salt),
            _b64(digest),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, raw_iterations, raw_salt, raw_digest = encoded.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(raw_iterations)
        salt = _unb64(raw_salt)
        expected = _unb64(raw_digest)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "tenant_id": user["tenant_id"],
        "email": user["email"],
        "role": user["role"],
    }


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
