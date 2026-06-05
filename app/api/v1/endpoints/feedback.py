import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.config import settings
from app.core.limiter import limiter, submit_global_key
from app.db.session import get_session
from app.models import AppFeedback
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackPublic,
    FeedbackStatus,
    FeedbackStatusUpdate,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_submit)
@limiter.limit(settings.rate_limit_submit_global, key_func=submit_global_key)
async def create_feedback(
    request: Request,
    body: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
):
    """Submit app-wide feedback. Open to guests."""
    feedback = AppFeedback(
        category=body.category,
        message=body.message,
        rating=body.rating,
    )
    session.add(feedback)
    await session.commit()
    return {"id": feedback.id}


@router.get(
    "/admin",
    response_model=list[FeedbackPublic],
    dependencies=[Depends(require_admin)],
)
async def list_feedback(
    status_filter: FeedbackStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(AppFeedback)
        .order_by(AppFeedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter is not None:
        stmt = stmt.where(AppFeedback.status == status_filter)
    return (await session.execute(stmt)).scalars().all()


@router.patch(
    "/admin/{feedback_id}",
    response_model=FeedbackPublic,
    dependencies=[Depends(require_admin)],
)
async def update_feedback_status(
    feedback_id: uuid.UUID,
    body: FeedbackStatusUpdate,
    session: AsyncSession = Depends(get_session),
):
    feedback = (
        await session.execute(
            select(AppFeedback).where(AppFeedback.id == feedback_id)
        )
    ).scalar_one_or_none()
    if feedback is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found"
        )

    feedback.status = body.status
    await session.commit()
    return feedback
