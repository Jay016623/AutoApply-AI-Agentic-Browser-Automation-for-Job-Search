"""Review queue endpoints for human-in-the-loop actions."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, get_db
from app.config.constants import DEFAULT_PAGE_SIZE
from app.schemas.review import ReviewActionRequest, ReviewTaskListResponse, ReviewTaskResponse
from app.services import review_queue

router = APIRouter()


@router.get("/tasks", response_model=ReviewTaskListResponse)
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    status: str | None = Query(default=None),
    reason: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ReviewTaskListResponse:
    return await review_queue.list_review_tasks(db, auth, page=page, page_size=page_size, status=status, reason=reason)


@router.get("/tasks/{task_id}", response_model=ReviewTaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ReviewTaskResponse:
    task = await review_queue.get_review_task(db, auth, task_id)
    return ReviewTaskResponse.model_validate(task)


@router.post("/tasks/{task_id}/actions", response_model=ReviewTaskResponse)
async def take_action(
    task_id: str,
    payload: ReviewActionRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ReviewTaskResponse:
    task = await review_queue.apply_review_action(db, auth, task_id=task_id, action=payload.action, notes=payload.notes)
    return ReviewTaskResponse.model_validate(task)
