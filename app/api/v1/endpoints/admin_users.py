import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_session
from app.models import User
from app.schemas.user import UserPublic, UserUpdate

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)


async def _get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.get("", response_model=list[UserPublic])
async def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    return (await session.execute(stmt)).scalars().all()


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    return await _get_user(session, user_id)


@router.patch("/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    session: AsyncSession = Depends(get_session),
):
    user = await _get_user(session, user_id)

    if body.username is not None:
        user.username = body.username
    if body.email is not None:
        user.email = body.email

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already in use",
        ) from exc

    await session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    user = await _get_user(session, user_id)
    await session.delete(user)
    await session.commit()
