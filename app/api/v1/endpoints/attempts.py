import random
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models import (
    Category,
    Question,
    QuestionOption,
    QuizAttempt,
    UserAnswer,
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


async def _load_attempt(session: AsyncSession, attempt_id: uuid.UUID) -> QuizAttempt:
    # Guest-only mode: attempts are anonymous, so they're looked up by id alone.
    # Anyone holding an attempt id can read it — acceptable for this no-stakes,
    # self-directed tool (see the deferred-decisions note in CLAUDE.md).
    stmt = select(QuizAttempt).where(QuizAttempt.id == attempt_id)
    attempt = (await session.execute(stmt)).scalar_one_or_none()
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found"
        )
    return attempt


async def _select_question_ids(
    session: AsyncSession, body: AttemptCreate
) -> list[uuid.UUID]:
    """Pick a fresh random sample of questions for a new attempt.

    The optional difficulty and category filters narrow the pool before sampling.
    """
    stmt = select(Question.id)
    if body.difficulty:
        stmt = stmt.where(Question.difficulty == body.difficulty)
    if body.category:
        stmt = stmt.join(Question.category).where(Category.slug == body.category)
    stmt = stmt.order_by(func.random()).limit(body.question_count)

    return [qid for (qid,) in (await session.execute(stmt)).all()]


@router.post(
    "",
    response_model=AttemptCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_attempt(
    body: AttemptCreate,
    session: AsyncSession = Depends(get_session),
):
    question_ids = await _select_question_ids(session, body)
    if not question_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No questions available for the requested criteria",
        )

    attempt = QuizAttempt(total_questions=len(question_ids))
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
    session: AsyncSession = Depends(get_session),
):
    attempt = await _load_attempt(session, attempt_id)

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
            category=CategoryPublic(
                id=q.category.id,
                name=q.category.name,
                slug=q.category.slug,
                position=q.category.position,
            ),
            options=random.sample(
                [OptionPublic(id=o.id, text=o.option_text) for o in q.options],
                k=len(q.options),
            ),
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
    session: AsyncSession = Depends(get_session),
):
    attempt = await _load_attempt(session, attempt_id)
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

    correct_option_id = None
    if not option.is_correct:
        correct_option_id = (
            await session.execute(
                select(QuestionOption.id).where(
                    QuestionOption.question_id == body.question_id,
                    QuestionOption.is_correct == True,
                )
            )
        ).scalar_one_or_none()

    await session.commit()
    return AnswerResult(
        correct=option.is_correct,
        explanation=explanation,
        correct_option_id=correct_option_id,
    )


@router.post("/{attempt_id}/complete", response_model=AttemptComplete)
async def complete_attempt(
    attempt_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    attempt = await _load_attempt(session, attempt_id)
    if attempt.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Attempt already completed"
        )

    answers = (
        (
            await session.execute(
                select(UserAnswer).where(UserAnswer.attempt_id == attempt.id)
            )
        )
        .scalars()
        .all()
    )
    score = sum(1 for a in answers if a.is_correct)

    attempt.score = score
    attempt.completed_at = func.now()
    await session.commit()

    total = attempt.total_questions
    percentage = (score / total * 100) if total else 0.0
    return AttemptComplete(
        score=score,
        total_questions=total,
        percentage=round(percentage, 2),
    )
