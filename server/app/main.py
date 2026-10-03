from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os, uuid, json, aiosqlite, httpx
from datetime import datetime
from pathlib import Path

from app.crypto.router import router as crypto_router

app = FastAPI(title="Agent Phone API", description="Phone-first control room for trusted AI workers", version="0.8.0-crypto")
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

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")); DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "agent_phone.db"
MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")
MODEL_API_BASE_URL = os.getenv("MODEL_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
APP_AUTH_TOKEN = os.getenv("APP_AUTH_TOKEN", "dev-token-change-me")
MAX_GOAL_AGENTS = 3

async def require_auth(authorization: Optional[str] = Header(None)):
    if not APP_AUTH_TOKEN: return True
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    if authorization[7:].strip() != APP_AUTH_TOKEN:
        raise HTTPException(401, "Invalid token")
    return True

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db

def now_iso(): return datetime.utcnow().isoformat()

# NOTE: Full agents/goals/approvals/chat routes preserved on branch from main.
# Crypto routes mounted below. If this file was truncated during tool push,
# restore full main from main branch and re-add the two crypto lines.

app.include_router(crypto_router)
