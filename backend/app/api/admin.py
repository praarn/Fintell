from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.admin import ResumeMetricsOut
from app.schemas.categorization import LLMStatsOut, PromotionJobResultOut
from app.services import metrics_service
from app.services.categorization import tier3
from app.services.categorization.promotion import run_promotion_job

# No real admin/RBAC system exists — these are gated behind ordinary auth
# like every other route. A proper admin role is out of scope; the
# cost/metrics data here is system-wide but not sensitive per-user.
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/llm-stats", response_model=LLMStatsOut)
async def get_llm_stats(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> LLMStatsOut:
    return LLMStatsOut(**await tier3.compute_llm_stats(db))


@router.get("/metrics", response_model=ResumeMetricsOut)
async def get_resume_metrics(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ResumeMetricsOut:
    return ResumeMetricsOut(**await metrics_service.compute_resume_metrics(db))


@router.post("/promotion-job/run", response_model=PromotionJobResultOut)
async def trigger_promotion_job(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PromotionJobResultOut:
    return PromotionJobResultOut(**await run_promotion_job(db))
