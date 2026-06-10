import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_admin
from app.db.session import get_session
from app.models import Category, Question, QuestionOption
from app.schemas.question import (
    BulkCreateResponse,
    BulkQuestionCreate,
    CategoryPublic,
    Difficulty,
    OptionPublic,
    QuestionDetail,
    QuestionSummary,
)

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post(
    "/bulk",
    response_model=BulkCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def bulk_create_questions(
    payload: BulkQuestionCreate,
    session: AsyncSession = Depends(get_session),
):
    # Validate all referenced category slugs against the closed set
    slugs = {q.category for q in payload.questions}
    existing = await session.execute(select(Category).where(Category.slug.in_(slugs)))
    cats_by_slug = {c.slug: c for c in existing.scalars()}

    unknown = slugs - cats_by_slug.keys()
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown category slugs: {sorted(unknown)}",
        )

    # Reject duplicate titles within the payload itself before hitting the DB,
    # since the unique constraint would surface this as an opaque IntegrityError.
    titles = [item.title for item in payload.questions]
    duplicate_titles = sorted({title for title in titles if titles.count(title) > 1})
    if duplicate_titles:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate titles in payload: {duplicate_titles}",
        )

    questions: list[Question] = []
    for item in payload.questions:
        question = Question(
            title=item.title,
            description=item.description,
            difficulty=item.difficulty,
            explanation=item.explanation,
            category_id=cats_by_slug[item.category].id,
            created_by=None,
        )
        question.options = [
            QuestionOption(
                option_text=option.text,
                is_correct=option.is_correct,
                position=position,
            )
            for position, option in enumerate(item.options)
        ]
        session.add(question)
        questions.append(question)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more question titles already exist; no questions were created.",
        ) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create questions: {exc}",
        ) from exc

    question_ids = [question.id for question in questions]
    await session.commit()
    return BulkCreateResponse(created=len(question_ids), question_ids=question_ids)


def _category_public(c: Category) -> CategoryPublic:
    return CategoryPublic(id=c.id, name=c.name, slug=c.slug, position=c.position)


@router.get("", response_model=list[QuestionSummary])
async def list_questions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    difficulty: Difficulty | None = Query(default=None),
    category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Question).options(selectinload(Question.category))
    if difficulty:
        stmt = stmt.where(Question.difficulty == difficulty)
    if category:
        stmt = stmt.join(Question.category).where(Category.slug == category)
    stmt = stmt.order_by(Question.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    questions = result.scalars().unique().all()
    return [
        QuestionSummary(
            id=q.id,
            title=q.title,
            difficulty=q.difficulty,
            category=_category_public(q.category),
        )
        for q in questions
    ]


@router.get("/{question_id}", response_model=QuestionDetail)
async def get_question(
    question_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.options), selectinload(Question.category))
    )
    question = (await session.execute(stmt)).scalar_one_or_none()
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )

    return QuestionDetail(
        id=question.id,
        title=question.title,
        description=question.description,
        difficulty=question.difficulty,
        category=_category_public(question.category),
        options=[OptionPublic(id=o.id, text=o.option_text) for o in question.options],
    )
