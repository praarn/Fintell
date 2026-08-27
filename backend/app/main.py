from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.accounts import router as accounts_router
from app.api.admin import router as admin_router
from app.api.anomalies import router as anomalies_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.statements import router as statements_router
from app.api.transactions import router as transactions_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(statements_router)
app.include_router(transactions_router)
app.include_router(accounts_router)
app.include_router(admin_router)
app.include_router(anomalies_router)
