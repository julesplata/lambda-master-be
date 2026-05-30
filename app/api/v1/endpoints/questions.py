import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_admin
from app.db.session import get_session
from app.models import Question, QuestionOption, Tag
from app.schemas.question import (
    BulkCreateResponse,
    BulkQuestionCreate,
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
    # Resolve all tag names across the batch up front, reusing existing tags
    # and creating any that are missing. A shared name->Tag map avoids duplicate
    # inserts and unique-constraint races within this request.
    tag_names = {name for q in payload.questions for name in q.tags}
    tags_by_name: dict[str, Tag] = {}
    if tag_names:
        existing = await session.execute(select(Tag).where(Tag.name.in_(tag_names)))
        tags_by_name = {tag.name: tag for tag in existing.scalars()}
        for name in tag_names:
            if name not in tags_by_name:
                tag = Tag(name=name)
                session.add(tag)
                tags_by_name[name] = tag

    questions: list[Question] = []
    for item in payload.questions:
        question = Question(
            title=item.title,
            description=item.description,
            difficulty=item.difficulty,
            explanation=item.explanation,
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
        question.tags = [tags_by_name[name] for name in item.tags]
        session.add(question)
        questions.append(question)

    try:
        await session.flush()
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create questions: {exc}",
        ) from exc

    question_ids = [question.id for question in questions]
    await session.commit()
    return BulkCreateResponse(created=len(question_ids), question_ids=question_ids)


@router.get("", response_model=list[QuestionSummary])
async def list_questions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    difficulty: Difficulty | None = Query(default=None),
    tag: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Question)
    if difficulty:
        stmt = stmt.where(Question.difficulty == difficulty)
    if tag:
        stmt = stmt.join(Question.tags).where(Tag.name == tag)
    stmt = stmt.order_by(Question.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().unique().all()


@router.get("/{question_id}", response_model=QuestionDetail)
async def get_question(
    question_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.options))
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
        options=[OptionPublic(id=o.id, text=o.option_text) for o in question.options],
    )
