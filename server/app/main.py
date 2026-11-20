from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.crypto.router import router as crypto_router
from app.core_routes import register_core
from app.core_routes_more import register_core_more
from app.workspace import router as workspace_router
from app.auth import router as auth_router
from app.github_tools import router as github_router

app = FastAPI(
    title="Agent Phone API",
    description="Phone-first control room for trusted AI workers",
    version="0.8.0",
)
APP_ENV = os.getenv("APP_ENV", "development").lower()
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if APP_ENV == "production" and not _cors_origins:
    raise RuntimeError("CORS_ORIGINS must explicitly list the trusted frontend origin in production")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

register_core(app)
register_core_more(app)
app.include_router(crypto_router)
app.include_router(workspace_router)
app.include_router(auth_router)
app.include_router(github_router)
