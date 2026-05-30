import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.leveling import level_for_xp
from app.db.session import get_session
from app.models import (
    Question,
    QuestionTag,
    QuizAttempt,
    Tag,
    User,
    UserAnswer,
    UserQuestionStat,
)
from app.schemas.stats import (
    AttemptHistoryItem,
    DifficultyAccuracy,
    StatsOverview,
    TagAccuracy,
)

router = APIRouter(prefix="/stats", tags=["stats"])


def _answered_for_user(user_id: uuid.UUID):
    """Answered (non-placeholder) rows belonging to the current user's attempts.

    Every stats query starts from this user-scoped answer filter.
    """
    return (
        select(UserAnswer)
        .join(QuizAttempt, UserAnswer.attempt_id == QuizAttempt.id)
        .where(
            QuizAttempt.user_id == user_id,
            UserAnswer.selected_option_id.is_not(None),
        )
    )


def _ratio(correct: int, answered: int) -> float:
    return round(correct / answered, 4) if answered else 0.0


@router.get("/me", response_model=StatsOverview)
async def my_stats(
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    answered_subq = _answered_for_user(user_id).subquery()
    totals = (
        await session.execute(
            select(
                func.count().label("answered"),
                func.count()
                .filter(answered_subq.c.is_correct.is_(True))
                .label("correct"),
            ).select_from(answered_subq)
        )
    ).one()

    attempts_completed = (
        await session.execute(
            select(func.count())
            .select_from(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.completed_at.is_not(None),
            )
        )
    ).scalar_one()

    questions_due = (
        await session.execute(
            select(func.count())
            .select_from(UserQuestionStat)
            .where(
                UserQuestionStat.user_id == user_id,
                UserQuestionStat.due_at <= datetime.now(timezone.utc),
            )
        )
    ).scalar_one()

    gamification = (
        await session.execute(
            select(User.xp, User.current_streak, User.longest_streak).where(
                User.id == user_id
            )
        )
    ).one()

    return StatsOverview(
        attempts_completed=attempts_completed,
        questions_answered=totals.answered,
        questions_correct=totals.correct,
        accuracy=_ratio(totals.correct, totals.answered),
        questions_due=questions_due,
        xp=gamification.xp,
        level=level_for_xp(gamification.xp),
        current_streak=gamification.current_streak,
        longest_streak=gamification.longest_streak,
    )


@router.get("/me/by-tag", response_model=list[TagAccuracy])
async def my_stats_by_tag(
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    answered_subq = _answered_for_user(user_id).subquery()
    stmt = (
        select(
            Tag.name,
            func.count().label("answered"),
            func.count()
            .filter(answered_subq.c.is_correct.is_(True))
            .label("correct"),
        )
        .select_from(answered_subq)
        .join(QuestionTag, QuestionTag.question_id == answered_subq.c.question_id)
        .join(Tag, Tag.id == QuestionTag.tag_id)
        .group_by(Tag.name)
        .order_by(Tag.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        TagAccuracy(
            tag=name,
            answered=answered,
            correct=correct,
            accuracy=_ratio(correct, answered),
        )
        for name, answered, correct in rows
    ]


@router.get("/me/by-difficulty", response_model=list[DifficultyAccuracy])
async def my_stats_by_difficulty(
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    answered_subq = _answered_for_user(user_id).subquery()
    stmt = (
        select(
            Question.difficulty,
            func.count().label("answered"),
            func.count()
            .filter(answered_subq.c.is_correct.is_(True))
            .label("correct"),
        )
        .select_from(answered_subq)
        .join(Question, Question.id == answered_subq.c.question_id)
        .group_by(Question.difficulty)
    )
    rows = (await session.execute(stmt)).all()
    # Stable easy → hard ordering regardless of how rows come back.
    order = {"easy": 0, "medium": 1, "hard": 2}
    rows = sorted(rows, key=lambda r: order.get(r[0], 99))
    return [
        DifficultyAccuracy(
            difficulty=difficulty,
            answered=answered,
            correct=correct,
            accuracy=_ratio(correct, answered),
        )
        for difficulty, answered, correct in rows
    ]


@router.get("/me/history", response_model=list[AttemptHistoryItem])
async def my_attempt_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(QuizAttempt)
        .where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.completed_at.is_not(None),
        )
        .order_by(QuizAttempt.completed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    attempts = (await session.execute(stmt)).scalars().all()
    return [
        AttemptHistoryItem(
            attempt_id=a.id,
            score=a.score,
            total_questions=a.total_questions,
            percentage=round(a.score / a.total_questions * 100, 2)
            if a.total_questions
            else 0.0,
            completed_at=a.completed_at,
        )
        for a in attempts
    ]
