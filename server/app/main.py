from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.crypto.router import router as crypto_router
from app.core_routes import register_core

app = FastAPI(
    title="Agent Phone API",
    description="Phone-first control room for trusted AI workers",
    version="0.8.0",
)
_cors_origins = [o.strip() for o in os.getenv(
    "CORS_ORIGINS",
    "https://agent-phone.netlify.app,http://localhost:3000,http://127.0.0.1:3000"
).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_core(app)
app.include_router(crypto_router)
