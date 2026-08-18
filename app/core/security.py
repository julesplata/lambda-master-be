import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # Malformed stored hash — treat as a failed verification.
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    """Verify an access token and return its subject (user id).

    Raises jwt.InvalidTokenError (or a subclass) on any problem.
    """
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    sub = payload.get("sub")
    try:
        return uuid.UUID(sub)
    except (ValueError, TypeError) as exc:
        raise jwt.InvalidTokenError("invalid subject") from exc


def admin_key_fingerprint() -> str:
    """A stable, non-reversible marker for the *current* ADMIN_API_KEY.

    Stamped into every admin token as `akf` and re-derived from the env var on
    each verification, so rotating the key invalidates tokens minted under the
    old one. Safe to carry in a JWT payload (which is signed, not encrypted):
    it is a truncated SHA-256 of a high-entropy secret.

    Deliberately not named `kid` — that claim conventionally selects a *signing*
    key, which is JWT_SECRET's job here, not this.
    """
    return hashlib.sha256(settings.admin_api_key.encode()).hexdigest()[:16]


def create_admin_token() -> str:
    """Mint a short-lived token proving the holder presented the admin key.

    The admin console exchanges ADMIN_API_KEY for one of these at sign-in so the
    long-lived key never has to be stored in a browser. It carries no subject —
    admin access is a single capability, not a user identity.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "iat": now,
        "exp": now + timedelta(minutes=settings.admin_token_ttl_minutes),
        "type": "admin",
        "akf": admin_key_fingerprint(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_admin_token(token: str) -> None:
    """Verify an admin session token.

    Raises jwt.InvalidTokenError (or a subclass) on any problem.
    """
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "admin":
        raise jwt.InvalidTokenError("not an admin token")
    # Rotating ADMIN_API_KEY changes the fingerprint, so sessions opened with the
    # previous key stop working on their next request rather than lingering for
    # the rest of their TTL. Constant-time because it is compared per request.
    if not secrets.compare_digest(
        str(payload.get("akf", "")), admin_key_fingerprint()
    ):
        raise jwt.InvalidTokenError("token was minted under a rotated admin key")


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_refresh_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). The raw token goes to the client;
    only the hash is stored server-side."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days)
