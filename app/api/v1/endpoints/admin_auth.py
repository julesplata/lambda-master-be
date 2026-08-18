import secrets

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import settings
from app.core.limiter import admin_session_global_key, limiter
from app.core.security import create_admin_token
from app.schemas.admin import AdminSession, AdminSessionCreate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/session", response_model=AdminSession)
@limiter.limit(settings.rate_limit_admin_session)
@limiter.limit(
    settings.rate_limit_admin_session_global, key_func=admin_session_global_key
)
async def create_admin_session(request: Request, body: AdminSessionCreate):
    """Exchange the admin key for a short-lived session token.

    The console calls this once at sign-in and stores only the returned token, so
    ADMIN_API_KEY never sits in browser storage where a script injection could
    read it. The token is stamped with a fingerprint of the key that minted it,
    so rotating ADMIN_API_KEY revokes outstanding sessions immediately instead of
    leaving them valid for the rest of their TTL.

    Rate limited per IP and globally: the key is a single shared secret with no
    lockout, so the limits are what make online guessing impractical.
    """
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API not configured",
        )
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin sessions require JWT_SECRET to be set",
        )
    # Bytes, not str: compare_digest raises TypeError on non-ASCII strings, and
    # body.key is attacker-controlled — comparing as str lets anyone turn this
    # unauthenticated endpoint into a 500 by posting a non-ASCII key.
    if not secrets.compare_digest(body.key.encode(), settings.admin_api_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key"
        )

    return AdminSession(
        token=create_admin_token(),
        expires_in_minutes=settings.admin_token_ttl_minutes,
    )
