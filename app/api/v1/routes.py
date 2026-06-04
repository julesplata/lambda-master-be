from fastapi import APIRouter

from app.api.v1.endpoints import (
    attempts,
    categories,
    questions,
    tags,
)

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
    return {"status": "ok"}


router.include_router(categories.router)
router.include_router(questions.router)
router.include_router(attempts.router)
router.include_router(tags.router)
