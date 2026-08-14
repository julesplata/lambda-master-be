import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_admin
from app.db.session import get_session
from app.models import Category, Question, QuestionOption
from app.schemas.admin import (
    AdminBulkPatch,
    AdminBulkResult,
    AdminOption,
    AdminQuestion,
    AdminQuestionIds,
    AdminQuestionWrite,
)

router = APIRouter(
    prefix="/admin/questions",
    tags=["admin-questions"],
    dependencies=[Depends(require_admin)],
)

# The console filters, sorts and counts the whole bank client-side so every
# interaction is instant. This cap is the point at which that stops being a fair
# trade and the list needs server-side paging.
MAX_QUESTIONS = 2000


def _serialize(question: Question) -> AdminQuestion:
    return AdminQuestion(
        id=question.id,
        title=question.title,
        description=question.description,
        difficulty=question.difficulty,
        explanation=question.explanation,
        category=question.category.slug,
        options=[
            AdminOption(id=o.id, text=o.option_text, is_correct=o.is_correct)
            for o in question.options
        ],
        updated_at=question.updated_at,
        archived_at=question.archived_at,
    )


async def _category_id_for_slug(session: AsyncSession, slug: str) -> uuid.UUID:
    category_id = (
        await session.execute(select(Category.id).where(Category.slug == slug))
    ).scalar_one_or_none()
    if category_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown category slug: {slug}",
        )
    return category_id


async def _load_question(session: AsyncSession, question_id: uuid.UUID) -> Question:
    """Load a question as the database currently has it.

    populate_existing matters on the write paths: the question is already in the
    session's identity map with its original category relationship loaded, and
    without this a re-query hands that stale object back rather than refreshing
    it — so a response to a category change would echo the previous category.
    """
    stmt = (
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.options), selectinload(Question.category))
        .execution_options(populate_existing=True)
    )
    question = (await session.execute(stmt)).scalar_one_or_none()
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )
    return question


async def _commit_or_conflict(session: AsyncSession, title: str) -> None:
    """Commit, translating the (title, category) unique violation into a 409."""
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'A question titled "{title}" already exists in that category',
        ) from exc


@router.get("", response_model=list[AdminQuestion])
async def list_questions_for_admin(
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
):
    """Return the whole bank, correct answers and explanations included."""
    stmt = (
        select(Question)
        .options(selectinload(Question.options), selectinload(Question.category))
        .order_by(Question.updated_at.desc())
        .limit(MAX_QUESTIONS)
    )
    if not include_archived:
        stmt = stmt.where(Question.archived_at.is_(None))

    questions = (await session.execute(stmt)).scalars().unique().all()
    return [_serialize(q) for q in questions]


@router.post("", response_model=AdminQuestion, status_code=status.HTTP_201_CREATED)
async def create_question(
    body: AdminQuestionWrite,
    session: AsyncSession = Depends(get_session),
):
    question = Question(
        title=body.title,
        description=body.description,
        difficulty=body.difficulty,
        explanation=body.explanation,
        category_id=await _category_id_for_slug(session, body.category),
        created_by=None,
    )
    question.options = [
        QuestionOption(
            option_text=option.text, is_correct=option.is_correct, position=position
        )
        for position, option in enumerate(body.options)
    ]
    session.add(question)
    await _commit_or_conflict(session, body.title)

    return _serialize(await _load_question(session, question.id))


@router.patch("/bulk", response_model=AdminBulkResult)
async def bulk_patch_questions(
    body: AdminBulkPatch,
    session: AsyncSession = Depends(get_session),
):
    """Set category and/or difficulty across a selection."""
    values: dict[str, object] = {"updated_at": func.now()}
    if body.category is not None:
        values["category_id"] = await _category_id_for_slug(session, body.category)
    if body.difficulty is not None:
        values["difficulty"] = body.difficulty

    stmt = update(Question).where(Question.id.in_(body.ids)).values(**values)
    try:
        result = await session.execute(stmt)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # Moving questions into a category that already holds a question with
        # the same title trips the (title, category) unique constraint.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "That move would collide with an existing question title in the "
                "target category; nothing was changed"
            ),
        ) from exc

    return AdminBulkResult(affected=result.rowcount or 0)


@router.post("/archive", response_model=AdminBulkResult)
async def archive_questions(
    body: AdminQuestionIds,
    session: AsyncSession = Depends(get_session),
):
    """Remove questions from circulation without destroying attempt history.

    Archived questions disappear from browsing and from new attempts, but the
    rows stay, so past answers keep resolving and the console can restore them.
    """
    stmt = (
        update(Question)
        .where(Question.id.in_(body.ids), Question.archived_at.is_(None))
        .values(archived_at=func.now(), updated_at=func.now())
    )
    result = await session.execute(stmt)
    await session.commit()
    return AdminBulkResult(affected=result.rowcount or 0)


@router.post("/restore", response_model=AdminBulkResult)
async def restore_questions(
    body: AdminQuestionIds,
    session: AsyncSession = Depends(get_session),
):
    """Undo an archive, putting the questions back into circulation."""
    stmt = (
        update(Question)
        .where(Question.id.in_(body.ids), Question.archived_at.is_not(None))
        .values(archived_at=None, updated_at=func.now())
    )
    result = await session.execute(stmt)
    await session.commit()
    return AdminBulkResult(affected=result.rowcount or 0)


@router.patch("/{question_id}", response_model=AdminQuestion)
async def update_question(
    question_id: uuid.UUID,
    body: AdminQuestionWrite,
    session: AsyncSession = Depends(get_session),
):
    """Replace a question and its full option list.

    The console edits a whole draft and saves it as a unit, so options are
    replaced wholesale rather than diffed. Existing option rows are deleted,
    which means user_answers.selected_option_id goes NULL (ON DELETE SET NULL)
    for anyone who picked one — the answer's is_correct flag was already
    recorded at submit time, so past scores are unaffected.
    """
    question = await _load_question(session, question_id)
    question.title = body.title
    question.description = body.description
    question.difficulty = body.difficulty
    question.explanation = body.explanation
    question.category_id = await _category_id_for_slug(session, body.category)

    # Drop the old options in their own flush. question_options has a
    # (question_id, position) unique constraint and the replacements start again
    # at position 0, so the DELETEs have to reach the database before the
    # INSERTs — a single flush would emit them the other way round and collide.
    question.options.clear()
    await session.flush()
    question.options = [
        QuestionOption(
            option_text=option.text, is_correct=option.is_correct, position=position
        )
        for position, option in enumerate(body.options)
    ]

    await _commit_or_conflict(session, body.title)
    return _serialize(await _load_question(session, question_id))
