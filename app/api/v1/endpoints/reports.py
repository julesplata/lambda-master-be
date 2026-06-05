import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.config import settings
from app.core.limiter import limiter, submit_global_key
from app.db.session import get_session
from app.models import Category, Question, QuestionReport
from app.schemas.report import (
    ReportCreate,
    ReportPublic,
    ReportStatus,
    ReportStatusUpdate,
)

router = APIRouter(tags=["reports"])


@router.post(
    "/questions/{question_id}/reports",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.rate_limit_submit)
@limiter.limit(settings.rate_limit_submit_global, key_func=submit_global_key)
async def create_report(
    request: Request,
    question_id: uuid.UUID,
    body: ReportCreate,
    session: AsyncSession = Depends(get_session),
):
    """Flag a problem with a specific question. Open to guests."""
    question = (
        await session.execute(select(Question.id).where(Question.id == question_id))
    ).scalar_one_or_none()
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )

    report = QuestionReport(
        question_id=question_id,
        attempt_id=body.attempt_id,
        reason=body.reason,
        comment=body.comment,
    )
    session.add(report)
    await session.commit()
    return {"id": report.id}


@router.get(
    "/admin/reports",
    response_model=list[ReportPublic],
    dependencies=[Depends(require_admin)],
)
async def list_reports(
    status_filter: ReportStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(
            QuestionReport,
            Question.title,
            Category.name,
        )
        .join(Question, Question.id == QuestionReport.question_id)
        .join(Category, Category.id == Question.category_id, isouter=True)
        .order_by(QuestionReport.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter is not None:
        stmt = stmt.where(QuestionReport.status == status_filter)

    rows = (await session.execute(stmt)).all()
    return [
        ReportPublic(
            id=report.id,
            question_id=report.question_id,
            question_title=title,
            category=category_name,
            attempt_id=report.attempt_id,
            reason=report.reason,
            comment=report.comment,
            status=report.status,
            created_at=report.created_at,
        )
        for report, title, category_name in rows
    ]


@router.patch(
    "/admin/reports/{report_id}",
    response_model=ReportPublic,
    dependencies=[Depends(require_admin)],
)
async def update_report_status(
    report_id: uuid.UUID,
    body: ReportStatusUpdate,
    session: AsyncSession = Depends(get_session),
):
    report = (
        await session.execute(
            select(QuestionReport).where(QuestionReport.id == report_id)
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )

    report.status = body.status
    await session.commit()

    question = (
        await session.execute(
            select(Question.title, Category.name)
            .join(Category, Category.id == Question.category_id, isouter=True)
            .where(Question.id == report.question_id)
        )
    ).one()
    return ReportPublic(
        id=report.id,
        question_id=report.question_id,
        question_title=question.title,
        category=question.name,
        attempt_id=report.attempt_id,
        reason=report.reason,
        comment=report.comment,
        status=report.status,
        created_at=report.created_at,
    )
