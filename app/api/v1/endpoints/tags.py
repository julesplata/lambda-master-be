from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Tag

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[str])
async def list_tags(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Tag.name).order_by(Tag.name))
    return [name for (name,) in result.all()]
