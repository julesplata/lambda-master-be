import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user_id
from app.core.leveling import level_for_xp, next_streak, streak_day, xp_for_correct
from app.core.spaced_repetition import schedule
from app.db.session import get_session
from app.models import (
    Question,
    QuestionOption,
    QuizAttempt,
    User,
    UserAnswer,
    UserQuestionStat,
)
from app.schemas.attempt import (
    AnswerResult,
    AnswerSubmit,
    AttemptComplete,
    AttemptCreate,
    AttemptCreateResponse,
    AttemptDetail,
)
from app.schemas.question import CategoryPublic, OptionPublic, QuestionDetail

router = APIRouter(prefix="/quiz-attempts", tags=["quiz-attempts"])


async def _load_attempt(
    session: AsyncSession, attempt_id: uuid.UUID, user_id: uuid.UUID
) -> QuizAttempt:
    stmt = select(QuizAttempt).where(
        QuizAttempt.id == attempt_id, QuizAttempt.user_id == user_id
    )
    attempt = (await session.execute(stmt)).scalar_one_or_none()
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found"
        )
    return attempt


async def _select_question_ids(
    session: AsyncSession, user_id: uuid.UUID, body: AttemptCreate
) -> list[uuid.UUID]:
    """Pick the questions for a new attempt according to ``body.mode``.

    ``random``: a fresh random sample. ``review``: the user's cards that are due
    for spaced-repetition revision (``due_at <= now``), most overdue first. The
    optional difficulty filter applies to both.
    """
    if body.mode == "review":
        stmt = (
            select(UserQuestionStat.question_id)
            .where(
                UserQuestionStat.user_id == user_id,
                UserQuestionStat.due_at <= datetime.now(timezone.utc),
            )
            .order_by(UserQuestionStat.due_at)
            .limit(body.question_count)
        )
        if body.difficulty:
            stmt = stmt.join(
                Question, Question.id == UserQuestionStat.question_id
            ).where(Question.difficulty == body.difficulty)
    else:
        stmt = select(Question.id)
        if body.difficulty:
            stmt = stmt.where(Question.difficulty == body.difficulty)
        stmt = stmt.order_by(func.random()).limit(body.question_count)

    return [qid for (qid,) in (await session.execute(stmt)).all()]


@router.post(
    "",
    response_model=AttemptCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_attempt(
    body: AttemptCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    question_ids = await _select_question_ids(session, user_id, body)
    if not question_ids:
        detail = (
            "No questions due for review"
            if body.mode == "review"
            else "No questions available for the requested criteria"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    attempt = QuizAttempt(user_id=user_id, total_questions=len(question_ids))
    session.add(attempt)
    await session.flush()

    for qid in question_ids:
        session.add(
            UserAnswer(
                attempt_id=attempt.id,
                question_id=qid,
                selected_option_id=None,
                is_correct=False,
            )
        )

    await session.commit()
    await session.refresh(attempt)
    return AttemptCreateResponse(attempt_id=attempt.id, started_at=attempt.started_at)


@router.get("/{attempt_id}", response_model=AttemptDetail)
async def get_attempt(
    attempt_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    attempt = await _load_attempt(session, attempt_id, user_id)

    answers_stmt = select(UserAnswer).where(UserAnswer.attempt_id == attempt.id)
    answers = (await session.execute(answers_stmt)).scalars().all()
    question_ids = [a.question_id for a in answers]
    answered_count = sum(1 for a in answers if a.selected_option_id is not None)

    q_stmt = (
        select(Question)
        .where(Question.id.in_(question_ids))
        .options(selectinload(Question.options), selectinload(Question.category))
    )
    questions = (await session.execute(q_stmt)).scalars().unique().all()

    question_details = [
        QuestionDetail(
            id=q.id,
            title=q.title,
            description=q.description,
            difficulty=q.difficulty,
            category=CategoryPublic(id=q.category.id, name=q.category.name, slug=q.category.slug, position=q.category.position),
            options=random.sample([OptionPublic(id=o.id, text=o.option_text) for o in q.options], k=len(q.options)),
        )
        for q in questions
    ]

    return AttemptDetail(
        attempt_id=attempt.id,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        total_questions=attempt.total_questions,
        answered_count=answered_count,
        score=attempt.score if attempt.completed_at else None,
        questions=question_details,
    )


@router.post("/{attempt_id}/answers", response_model=AnswerResult)
async def submit_answer(
    attempt_id: uuid.UUID,
    body: AnswerSubmit,
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    attempt = await _load_attempt(session, attempt_id, user_id)
    if attempt.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Attempt already completed"
        )

    answer_stmt = select(UserAnswer).where(
        UserAnswer.attempt_id == attempt.id,
        UserAnswer.question_id == body.question_id,
    )
    answer = (await session.execute(answer_stmt)).scalar_one_or_none()
    if answer is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question is not part of this attempt",
        )
    if answer.selected_option_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Question already answered",
        )

    opt_stmt = select(QuestionOption).where(
        QuestionOption.id == body.selected_option_id,
        QuestionOption.question_id == body.question_id,
    )
    option = (await session.execute(opt_stmt)).scalar_one_or_none()
    if option is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Option does not belong to the question",
        )

    answer.selected_option_id = option.id
    answer.is_correct = option.is_correct

    explanation = (
        await session.execute(
            select(Question.explanation).where(Question.id == body.question_id)
        )
    ).scalar_one_or_none()

    await session.commit()
    return AnswerResult(correct=option.is_correct, explanation=explanation)


async def _record_question_stats(
    session: AsyncSession,
    user_id: uuid.UUID,
    answers: list[UserAnswer],
    *,
    now: datetime,
) -> None:
    """Upsert the per-question mastery rollup for each answered question.

    Skips unanswered placeholders. Reads each card's current Leitner box, then
    upserts the new box and ``due_at`` from the (unit-tested) ``schedule`` helper
    so a miss resurfaces immediately and repeated successes back off. Runs in the
    caller's transaction alongside attempt scoring.
    """
    answered = [a for a in answers if a.selected_option_id is not None]
    if not answered:
        return

    # Current boxes for the cards we're about to touch (absent → new card, box 1).
    question_ids = [a.question_id for a in answered]
    existing_boxes = dict(
        (
            await session.execute(
                select(UserQuestionStat.question_id, UserQuestionStat.box).where(
                    UserQuestionStat.user_id == user_id,
                    UserQuestionStat.question_id.in_(question_ids),
                )
            )
        ).all()
    )

    for answer in answered:
        current_box = existing_boxes.get(answer.question_id, 1)
        box, due_at = schedule(current_box, answer.is_correct, now=now)
        correct_inc = 1 if answer.is_correct else 0

        stmt = (
            pg_insert(UserQuestionStat)
            .values(
                user_id=user_id,
                question_id=answer.question_id,
                times_seen=1,
                times_correct=correct_inc,
                last_answered_at=now,
                last_correct=answer.is_correct,
                box=box,
                due_at=due_at,
            )
            .on_conflict_do_update(
                index_elements=[
                    UserQuestionStat.user_id,
                    UserQuestionStat.question_id,
                ],
                set_={
                    "times_seen": UserQuestionStat.times_seen + 1,
                    "times_correct": UserQuestionStat.times_correct + correct_inc,
                    "last_answered_at": now,
                    "last_correct": answer.is_correct,
                    "box": box,
                    "due_at": due_at,
                },
            )
        )
        await session.execute(stmt)


async def _award_gamification(
    session: AsyncSession,
    user: User,
    answers: list[UserAnswer],
    due_question_ids: set[uuid.UUID],
    *,
    now: datetime,
) -> int:
    """Grant XP for correct answers and advance the user's daily streak.

    XP scales with each correct question's difficulty and gets a bonus when the
    card was due for review (``due_question_ids``). Mutates ``user`` in the
    caller's transaction and returns the XP earned. Difficulties are fetched in
    one query rather than carried on UserAnswer.
    """
    correct = [a for a in answers if a.is_correct]
    earned = 0
    if correct:
        difficulties = dict(
            (
                await session.execute(
                    select(Question.id, Question.difficulty).where(
                        Question.id.in_([a.question_id for a in correct])
                    )
                )
            ).all()
        )
        for a in correct:
            earned += xp_for_correct(
                difficulties.get(a.question_id, ""),
                was_due=a.question_id in due_question_ids,
            )
        user.xp += earned

    # Streak advances once per active calendar day (idempotent within a day).
    today = streak_day(now)
    user.current_streak = next_streak(user.current_streak, user.last_activity_date, today)
    user.longest_streak = max(user.longest_streak, user.current_streak)
    user.last_activity_date = today
    return earned


@router.post("/{attempt_id}/complete", response_model=AttemptComplete)
async def complete_attempt(
    attempt_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    attempt = await _load_attempt(session, attempt_id, user_id)
    if attempt.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Attempt already completed"
        )

    answers = (
        await session.execute(
            select(UserAnswer).where(UserAnswer.attempt_id == attempt.id)
        )
    ).scalars().all()
    score = sum(1 for a in answers if a.is_correct)

    now = datetime.now(timezone.utc)

    # Which answered cards were due for review *before* this completion updates
    # them — captured up front so the XP bonus reflects the pre-attempt state.
    answered_ids = [a.question_id for a in answers if a.selected_option_id is not None]
    due_question_ids: set[uuid.UUID] = set()
    if answered_ids:
        due_question_ids = set(
            (
                await session.execute(
                    select(UserQuestionStat.question_id).where(
                        UserQuestionStat.user_id == user_id,
                        UserQuestionStat.question_id.in_(answered_ids),
                        UserQuestionStat.due_at <= now,
                    )
                )
            ).scalars()
        )

    await _record_question_stats(session, user_id, answers, now=now)

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    xp_earned = await _award_gamification(
        session, user, answers, due_question_ids, now=now
    )

    attempt.score = score
    attempt.completed_at = func.now()
    await session.commit()

    total = attempt.total_questions
    percentage = (score / total * 100) if total else 0.0
    return AttemptComplete(
        score=score,
        total_questions=total,
        percentage=round(percentage, 2),
        xp_earned=xp_earned,
        total_xp=user.xp,
        level=level_for_xp(user.xp),
        current_streak=user.current_streak,
    )
