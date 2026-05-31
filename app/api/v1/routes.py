from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin_users,
    attempts,
    auth,
    categories,
    questions,
    stats,
    tags,
)

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok"}


router.include_router(auth.router)
router.include_router(categories.router)
router.include_router(questions.router)
router.include_router(attempts.router)
router.include_router(tags.router)
router.include_router(stats.router)
router.include_router(admin_users.router)
