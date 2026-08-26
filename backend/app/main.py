from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.statements import router as statements_router
from app.api.transactions import router as transactions_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(statements_router)
app.include_router(transactions_router)
