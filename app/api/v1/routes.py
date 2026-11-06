import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import (
    admin_auth,
    admin_questions,
    attempts,
    categories,
    feedback,
    questions,
    reports,
    tags,
)
from app.db.session import get_session

# A database slower than this to answer SELECT 1 counts as down. Uptime
# monitors time out after ~30 s, so without a bound a hung connection would read
# as a slow page instead of a failed check.
READY_TIMEOUT_SECONDS = 2

# Guest-only mode: the auth, stats, and admin_users routers are intentionally
# left unmounted. They (and their endpoint modules) are kept on disk so user
# accounts can be re-enabled later by restoring the imports/include_router calls.
#   from app.api.v1.endpoints import admin_users, auth, stats
#   router.include_router(auth.router)
#   router.include_router(stats.router)
#   router.include_router(admin_users.router)

router = APIRouter()


@router.get("/health")
def health_check():
    """Liveness: the process answers. Touches nothing, so it stays cheap."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(session: AsyncSession = Depends(get_session)):
    """Readiness: the database answers too, or 503.

    Railway's deploy healthcheck should point here, so a deploy that cannot
    reach the database never goes live. Railway checks only during a deploy;
    an external uptime monitor watches this afterwards.
    """
    try:
        await asyncio.wait_for(
            session.execute(text("SELECT 1")), timeout=READY_TIMEOUT_SECONDS
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error
    return {"status": "ok"}


router.include_router(categories.router)
router.include_router(questions.router)
router.include_router(attempts.router)
router.include_router(tags.router)
router.include_router(reports.router)
router.include_router(feedback.router)
router.include_router(admin_auth.router)
router.include_router(admin_questions.router)
