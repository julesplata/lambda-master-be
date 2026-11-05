import random
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import Row, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.analytics import track
from app.core.config import settings
from app.core.limiter import limiter
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
    AttemptQuestion,
)
from app.schemas.question import CategoryPublic, OptionPublic

router = APIRouter(prefix="/quiz-attempts", tags=["quiz-attempts"])


def _shuffled_options(attempt_id: uuid.UUID, question: Question) -> list[OptionPublic]:
    """Return a question's options in a shuffled-but-stable order.

    Seeding the shuffle from (attempt_id, question_id) keeps the order constant
    across repeated reads of the same in-progress attempt — so refreshing the
    page doesn't move the answers around — while still varying it per question.
    """
    options = [OptionPublic(id=o.id, text=o.option_text) for o in question.options]
    seed = hash((attempt_id, question.id))
    random.Random(seed).shuffle(options)
    return options


def _attempt_question(
    attempt_id: uuid.UUID,
    question: Question,
    answer: UserAnswer | None,
) -> AttemptQuestion:
    """Serialise one of an attempt's questions, with its answer if it has one.

    The answer key (`correct_option_id`, `explanation`) is filled in only for a
    question that has already been answered, matching what `submit_answer`
    returned at the time. A question with no answer row, or with a row whose
    option an admin edit has since deleted (`selected_option_id` set NULL), is
    reported as unanswered: nulls, not "wrong".
    """
    answered = answer is not None and answer.selected_option_id is not None
    correct_option_id = None
    if answered and not answer.is_correct:
        correct_option_id = next(
            (option.id for option in question.options if option.is_correct), None
        )

    return AttemptQuestion(
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
        options=_shuffled_options(attempt_id, question),
        selected_option_id=answer.selected_option_id if answered else None,
        is_correct=answer.is_correct if answered else None,
        correct_option_id=correct_option_id,
        explanation=question.explanation if answered else None,
    )


async def _load_attempt(
    session: AsyncSession, attempt_id: uuid.UUID, *, for_update: bool = False
) -> QuizAttempt:
    # Guest-only mode: attempts are anonymous, so they're looked up by id alone.
    # Anyone holding an attempt id can read it — acceptable for this no-stakes,
    # self-directed tool (see the deferred-decisions note in CLAUDE.md).
    stmt = select(QuizAttempt).where(QuizAttempt.id == attempt_id)
    if for_update:
        stmt = stmt.with_for_update()
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
        # Archived questions are still in the table, so the sample is taken over
        # both and filtered afterwards. Oversampling absorbs the rows the filter
        # removes; the LIMIT trims the surplus back to what was asked for.
        stmt = text(
            "SELECT id FROM questions TABLESAMPLE SYSTEM_ROWS(:sample)"
            " WHERE archived_at IS NULL LIMIT :count"
        ).bindparams(sample=body.question_count * 2, count=body.question_count)
        return list((await session.execute(stmt)).scalars())

    # Filtered path: the WHERE clause shrinks the pool first, so ordering by
    # random() over that smaller set is cheap.
    stmt = select(Question.id).where(Question.archived_at.is_(None))
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
@limiter.limit(settings.rate_limit_attempt_create)
async def create_attempt(
    request: Request,
    body: AttemptCreate,
    session: AsyncSession = Depends(get_session),
):
    """Start a new anonymous attempt.

    Writes a single quiz_attempts row that holds the picked question ids. A
    user_answers row is written only when an answer arrives, so starting a quiz
    stores one row however many questions it has. Still rate limited per IP,
    tighter than the default, because it is open and every call stores a row.
    """
    question_ids = await _select_question_ids(session, body)
    if not question_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No questions available for the requested criteria",
        )
    # This is the order the quiz is served in. The unfiltered TABLESAMPLE path
    # returns rows in on-disk order, which follows how the bank was inserted.
    random.shuffle(question_ids)

    attempt = QuizAttempt(
        total_questions=len(question_ids),
        question_ids=question_ids,
        # "" filters nothing in _select_question_ids, so it is stored as "all".
        category=body.category or None,
        difficulty=body.difficulty,
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    track(
        request,
        "quiz_started",
        {
            "attempt_id": str(attempt.id),
            "question_count": len(question_ids),
            "difficulty": attempt.difficulty,
            "category": attempt.category,
        },
    )
    return AttemptCreateResponse(attempt_id=attempt.id, started_at=attempt.started_at)


async def _questions_by_id(
    session: AsyncSession, question_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Question]:
    """Load an attempt's questions with their options and category.

    Archived questions are included on purpose: a learner must still see a
    question they were served. One deleted outright is simply missing.
    """
    result = await session.execute(
        select(Question)
        .where(Question.id.in_(question_ids))
        .options(selectinload(Question.options), selectinload(Question.category))
    )
    return {question.id: question for question in result.scalars()}


async def _answers_by_question(
    session: AsyncSession, attempt_id: uuid.UUID
) -> dict[uuid.UUID, UserAnswer]:
    result = await session.execute(
        select(UserAnswer).where(UserAnswer.attempt_id == attempt_id)
    )
    return {answer.question_id: answer for answer in result.scalars()}


@router.get("/{attempt_id}", response_model=AttemptDetail)
async def get_attempt(
    attempt_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    attempt = await _load_attempt(session, attempt_id)
    questions = await _questions_by_id(session, attempt.question_ids)
    answers = await _answers_by_question(session, attempt.id)

    # Served in the order picked at start, so a client resuming the attempt
    # sees the questions numbered the same way on every read.
    question_details = [
        _attempt_question(attempt.id, questions[question_id], answers.get(question_id))
        for question_id in attempt.question_ids
        if question_id in questions
    ]
    answered_count = sum(
        1 for detail in question_details if detail.selected_option_id is not None
    )

    return AttemptDetail(
        attempt_id=attempt.id,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        total_questions=attempt.total_questions,
        answered_count=answered_count,
        score=attempt.score if attempt.completed_at else None,
        questions=question_details,
    )


async def _stored_answer(
    session: AsyncSession, attempt_id: uuid.UUID, question_id: uuid.UUID
) -> Row | None:
    """This attempt's answer to the question, (selected_option_id, is_correct).

    None when there is no answer yet. A row whose option an admin edit deleted
    (ON DELETE SET NULL) counts as unanswered, as GET reports it, so it can be
    answered again. Columns rather than the entity, so a second read in the same
    session sees the database instead of an object cached by the first.
    """
    statement = select(UserAnswer.selected_option_id, UserAnswer.is_correct).where(
        UserAnswer.attempt_id == attempt_id,
        UserAnswer.question_id == question_id,
        UserAnswer.selected_option_id.is_not(None),
    )
    return (await session.execute(statement)).one_or_none()


async def _store_answer(
    session: AsyncSession,
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    option: QuestionOption,
) -> Row | None:
    """Record an answer and return the one stored, which may be another request's.

    The upsert inserts a missing row and fills in one without a selected option.
    Two in-flight submits for the same question (a double tap, a retry racing
    the original) are serialised by the unique (attempt_id, question_id) index:
    the second waits for the first to commit, changes nothing, and reads back
    the first one's answer.
    """
    answer = {"selected_option_id": option.id, "is_correct": option.is_correct}
    await session.execute(
        insert(UserAnswer)
        .values(attempt_id=attempt_id, question_id=question_id, **answer)
        .on_conflict_do_update(
            index_elements=[UserAnswer.attempt_id, UserAnswer.question_id],
            set_={**answer, "answered_at": func.now()},
            where=UserAnswer.selected_option_id.is_(None),
        )
    )
    return await _stored_answer(session, attempt_id, question_id)


async def _options_and_explanation(
    session: AsyncSession, question_id: uuid.UUID
) -> tuple[list[QuestionOption], str | None]:
    """Every option of the question plus its explanation, in one query.

    That covers everything an answer's result needs: the selected option, the
    correct one, and the explanation.
    """
    rows = (
        await session.execute(
            select(QuestionOption, Question.explanation)
            .join(Question, Question.id == QuestionOption.question_id)
            .where(QuestionOption.question_id == question_id)
        )
    ).all()
    options = [option for option, _ in rows]
    explanation = rows[0][1] if rows else None
    return options, explanation


@router.post("/{attempt_id}/answers", response_model=AnswerResult)
async def submit_answer(
    attempt_id: uuid.UUID,
    body: AnswerSubmit,
    session: AsyncSession = Depends(get_session),
):
    """Record the answer to one question and return its result.

    Idempotent for the same option: a client whose response was lost in transit
    retries with the answer it already sent, and gets the stored result back
    instead of a 409 it has no way past. Only a *different* option on an
    answered question conflicts.
    """
    attempt = await _load_attempt(session, attempt_id)
    if body.question_id not in attempt.question_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question is not part of this attempt",
        )

    stored = await _stored_answer(session, attempt.id, body.question_id)
    if stored is not None and stored.selected_option_id != body.selected_option_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Question already answered"
        )
    # Checked after the replay case: a retried answer is still owed its result
    # even if the attempt was completed in between.
    if stored is None and attempt.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Attempt already completed"
        )

    options, explanation = await _options_and_explanation(session, body.question_id)
    selected = next((o for o in options if o.id == body.selected_option_id), None)
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Option does not belong to the question",
        )

    if stored is None:
        stored = await _store_answer(session, attempt.id, body.question_id, selected)
        if stored is None or stored.selected_option_id != selected.id:
            # A concurrent submit answered this question first, with another option.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Question already answered"
            )

    # A replay reports the verdict as stored, which is what the score counts,
    # even if the answer key has been edited since.
    correct_option_id = None
    if not stored.is_correct:
        correct_option_id = next((o.id for o in options if o.is_correct), None)

    # Commits a new answer; a replay has nothing to write.
    await session.commit()
    return AnswerResult(
        correct=stored.is_correct,
        explanation=explanation,
        correct_option_id=correct_option_id,
    )


@router.post("/{attempt_id}/complete", response_model=AttemptComplete)
async def complete_attempt(
    request: Request,
    attempt_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Score and close the attempt.

    Idempotent: completing an attempt that is already complete returns the
    stored score, so a client whose response was lost can simply retry. An
    attempt with no answers yet cannot be completed (409).
    """
    # Locked so concurrent completes serialise: the second one then sees
    # completed_at set and replays, rather than scoring (and tracking) twice.
    attempt = await _load_attempt(session, attempt_id, for_update=True)
    total = attempt.total_questions
    if attempt.completed_at is not None:
        score = attempt.score or 0
        return AttemptComplete(
            score=score,
            total_questions=total,
            percentage=round((score / total * 100) if total else 0.0, 2),
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
    # The frontend completes only after the last answer, so an attempt with none
    # comes from a script starting and completing quizzes in a loop. Left in
    # progress, the purge job deletes it after attempt_retention_days; completed,
    # it would be kept forever.
    if not answers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Answer at least one question before completing the attempt",
        )
    score = sum(1 for a in answers if a.is_correct)

    attempt.score = score
    attempt.completed_at = func.now()
    await session.commit()

    percentage = round((score / total * 100) if total else 0.0, 2)
    track(
        request,
        "quiz_completed",
        {
            "attempt_id": str(attempt.id),
            "score": score,
            "total_questions": total,
            "percentage": percentage,
            "difficulty": attempt.difficulty,
            "category": attempt.category,
        },
    )
    return AttemptComplete(
        score=score,
        total_questions=total,
        percentage=percentage,
    )
