from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.categorization import LLMStatsOut, PromotionJobResultOut
from app.services.categorization import tier3
from app.services.categorization.promotion import run_promotion_job

# No real admin/RBAC system exists yet — these are gated behind ordinary
# auth (get_current_user) like every other route. A proper admin role is a
# Phase 8 concern (the "cost-tracking/stats admin page" polish item).
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/llm-stats", response_model=LLMStatsOut)
async def get_llm_stats(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> LLMStatsOut:
    return LLMStatsOut(**await tier3.compute_llm_stats(db))


@router.post("/promotion-job/run", response_model=PromotionJobResultOut)
async def trigger_promotion_job(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PromotionJobResultOut:
    return PromotionJobResultOut(**await run_promotion_job(db))
