import random
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
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


def _shuffled_options(
    attempt_id: uuid.UUID, question: Question
) -> list[OptionPublic]:
    """Return a question's options in a shuffled-but-stable order.

    Seeding the shuffle from (attempt_id, question_id) keeps the order constant
    across repeated reads of the same in-progress attempt — so refreshing the
    page doesn't move the answers around — while still varying it per question.
    """
    options = [OptionPublic(id=o.id, text=o.option_text) for o in question.options]
    seed = hash((attempt_id, question.id))
    random.Random(seed).shuffle(options)
    return options


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
    # Fast path: with no filters we can use TABLESAMPLE SYSTEM_ROWS, which reads
    # roughly N random rows directly instead of scanning and sorting the whole
    # table the way ORDER BY random() does. It's approximate (it can return
    # slightly fewer rows than asked on small tables), so we only use it
    # unfiltered and fall back to the exact path when a filter is present.
    if not body.difficulty and not body.category:
        stmt = text(
            "SELECT id FROM questions TABLESAMPLE SYSTEM_ROWS(:count)"
        ).bindparams(count=body.question_count)
        return list((await session.execute(stmt)).scalars())

    # Filtered path: the WHERE clause shrinks the pool first, so ordering by
    # random() over that smaller set is cheap.
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

    # One query: join the attempt's answers to their questions (with options and
    # category eager-loaded) instead of fetching answers, then questions separately.
    rows = (
        (
            await session.execute(
                select(UserAnswer.selected_option_id, Question)
                .join(Question, Question.id == UserAnswer.question_id)
                .where(UserAnswer.attempt_id == attempt.id)
                .options(
                    selectinload(Question.options), selectinload(Question.category)
                )
            )
        )
        .unique()
        .all()
    )
    answered_count = sum(
        1 for selected_option_id, _ in rows if selected_option_id is not None
    )

    question_details = [
        QuestionDetail(
            id=question.id,
            title=question.title,
            description=question.description,
            difficulty=question.difficulty,
            category=CategoryPublic(
                id=question.category.id,
                name=question.category.name,
                slug=question.category.slug,
                position=question.category.position,
            ),
            options=_shuffled_options(attempt.id, question),
        )
        for _, question in rows
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

    # One query for everything the response needs: every option of the question
    # (to locate both the selected and the correct one) plus the explanation.
    # This replaces the previous selected-option, explanation, and conditional
    # correct-option lookups — three round-trips collapsed into one.
    rows = (
        await session.execute(
            select(QuestionOption, Question.explanation)
            .join(Question, Question.id == QuestionOption.question_id)
            .where(QuestionOption.question_id == body.question_id)
        )
    ).all()

    options = [option for option, _ in rows]
    explanation = rows[0][1] if rows else None
    selected = next(
        (o for o in options if o.id == body.selected_option_id), None
    )
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Option does not belong to the question",
        )

    answer.selected_option_id = selected.id
    answer.is_correct = selected.is_correct

    correct_option_id = None
    if not selected.is_correct:
        correct_option_id = next(
            (o.id for o in options if o.is_correct), None
        )

    await session.commit()
    return AnswerResult(
        correct=selected.is_correct,
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
