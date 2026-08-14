import secrets
import uuid

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.security import decode_access_token, decode_admin_token

bearer_scheme = HTTPBearer(auto_error=False)


def require_admin(
    x_admin_key: str | None = Header(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Admin guard accepting either credential.

    ``X-Admin-Key`` is the raw shared secret, used by seeding scripts and curl.
    ``Authorization: Bearer <token>`` is a short-lived admin session token from
    POST /admin/session, used by the admin console so the long-lived key is
    never stored in a browser. Either one grants the same access.
    """
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API not configured",
        )

    if credentials is not None:
        try:
            decode_admin_token(credentials.credentials)
            return
        except jwt.InvalidTokenError:
            # Fall through to the key check — a user access token on an admin
            # route is just a missing credential, not a distinct failure.
            pass

    if not x_admin_key or not secrets.compare_digest(
        x_admin_key, settings.admin_api_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> uuid.UUID:
    # DEV ONLY: short-circuit auth when AUTH_BYPASS_USER_ID is set. Never set in prod.
    if settings.auth_bypass_user_id:
        return uuid.UUID(settings.auth_bypass_user_id)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
