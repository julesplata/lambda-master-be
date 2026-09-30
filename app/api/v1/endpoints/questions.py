from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_session
from app.models import Category, Question, QuestionOption
from app.schemas.question import BulkCreateResponse, BulkQuestionCreate

# Only the admin bulk import lives here. The public GET /questions and
# GET /questions/{id} reads were removed: nothing called them, and the detail
# route returned options in stored position order, which for the seed bank put
# the correct answer first almost every time. Learners get questions through
# quiz attempts, which shuffle options per attempt (attempts._shuffled_options).
# If a public read comes back, it must shuffle the same way.
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

    # A title may be reused across categories, so duplicates are keyed on
    # (title, category). Reject in-payload collisions before hitting the DB,
    # since the unique constraint would surface this as an opaque IntegrityError.
    title_category_pairs = [(item.title, item.category) for item in payload.questions]
    duplicate_pairs = sorted(
        {pair for pair in title_category_pairs if title_category_pairs.count(pair) > 1}
    )
    if duplicate_pairs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate (title, category) pairs in payload: {duplicate_pairs}",
        )

    # Report exactly which (title, category) pairs already exist rather than
    # failing on an opaque IntegrityError. One indexed lookup keyed on the
    # composite unique constraint, joined to resolve the category slug.
    titles = [item.title for item in payload.questions]
    existing = await session.execute(
        select(Question.title, Category.slug)
        .join(Category, Question.category_id == Category.id)
        .where(Question.title.in_(titles))
    )
    existing_pairs = {(title, slug) for title, slug in existing}
    already_present = sorted(
        pair for pair in title_category_pairs if pair in existing_pairs
    )
    if already_present:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "(title, category) pairs already exist; no questions were "
                f"created: {already_present}"
            ),
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
        # The pre-check above already rules out duplicate titles, so report the
        # underlying database error instead of assuming it was a title conflict.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Database constraint violation; no questions were created: {exc.orig}",
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

