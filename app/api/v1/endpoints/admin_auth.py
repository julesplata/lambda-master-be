import secrets

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import create_admin_token
from app.schemas.admin import AdminSession, AdminSessionCreate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/session", response_model=AdminSession)
@limiter.limit(settings.rate_limit_admin_session)
async def create_admin_session(request: Request, body: AdminSessionCreate):
    """Exchange the admin key for a short-lived session token.

    The console calls this once at sign-in and stores only the returned token, so
    ADMIN_API_KEY never sits in browser storage where a script injection could
    read it. Rate limited per IP: the key is a single shared secret with no
    lockout, so the limit is what makes online guessing impractical.
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
    if not secrets.compare_digest(body.key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key"
        )

    return AdminSession(
        token=create_admin_token(),
        expires_in_minutes=settings.admin_token_ttl_minutes,
    )
