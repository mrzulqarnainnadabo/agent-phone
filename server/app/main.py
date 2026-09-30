from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import uuid
import json
import aiosqlite
from datetime import datetime
from pathlib import Path
import httpx

app = FastAPI(
    title="Agent Phone API",
    description="Mobile-first AI agent workspace backend",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ──────────────────────────────────────────────
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "agent_phone.db"

MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")
MODEL_API_BASE_URL = os.getenv("MODEL_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
APP_AUTH_TOKEN = os.getenv("APP_AUTH_TOKEN", "dev-token-change-me")

# ── Auth ────────────────────────────────────────────────
async def require_auth(authorization: Optional[str] = Header(None)):
    """Simple Bearer token check. Skip if APP_AUTH_TOKEN is empty (dev only)."""
    if not APP_AUTH_TOKEN:
        return True
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if token != APP_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return True

# ── Database ────────────────────────────────────────────
async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                title TEXT,
                system_prompt TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                role TEXT,
                content TEXT,
                created_at TEXT,
                FOREIGN KEY (thread_id) REFERENCES threads(id)
            );
        """)
        await db.commit()

@app.on_event("startup")
async def startup():
    await init_db()

# ── Schemas ─────────────────────────────────────────────
class ChatRequest(BaseModel):
    thread_id: Optional[str] = None
    message: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None

class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    message_id: str
    model: str

# ── Model call ──────────────────────────────────────────
async def call_model(messages: list, model: str) -> str:
    if not MODEL_API_KEY:
        return (
            "[No MODEL_API_KEY set]\n\n"
            "Set MODEL_API_KEY and MODEL_API_BASE_URL in your environment "
            "to get real AI replies. Example:\n"
            "export MODEL_API_KEY=sk-...\n"
            "export MODEL_API_BASE_URL=https://api.openai.com/v1"
        )

    url = f"{MODEL_API_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {MODEL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as e:
            return f"Model error ({e.response.status_code}): {e.response.text[:300]}"
        except Exception as e:
            return f"Model request failed: {str(e)}"

# ── Routes ──────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "name": "Agent Phone API",
        "version": "0.2.0",
        "status": "ready",
        "docs": "/docs",
        "model_configured": bool(MODEL_API_KEY),
    }

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, _auth=Depends(require_auth)):
    thread_id = req.thread_id or f"thread-{uuid.uuid4().hex[:8]}"
    message_id = f"msg-{uuid.uuid4().hex[:8]}"
    model = req.model or DEFAULT_MODEL
    now = datetime.utcnow().isoformat()

    default_prompt = (
        "You are a helpful, concise personal AI agent on the user's phone. "
        "Be clear, practical, and respectful. Keep replies short unless the user asks for depth."
    )
    system_prompt = req.system_prompt or default_prompt

    db = await get_db()
    try:
        # Ensure thread exists
        cur = await db.execute("SELECT id FROM threads WHERE id = ?", (thread_id,))
        row = await cur.fetchone()
        if not row:
            title = req.message[:40] + ("…" if len(req.message) > 40 else "")
            await db.execute(
                "INSERT INTO threads (id, title, system_prompt, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (thread_id, title, system_prompt, now, now),
            )
        else:
            await db.execute(
                "UPDATE threads SET updated_at = ? WHERE id = ?",
                (now, thread_id),
            )

        # Save user message
        user_msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        await db.execute(
            "INSERT INTO messages (id, thread_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_msg_id, thread_id, "user", req.message, now),
        )

        # Build history for the model
        cur = await db.execute(
            "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
            (thread_id,),
        )
        history_rows = await cur.fetchall()
        messages = [{"role": "system", "content": system_prompt}]
        for r in history_rows:
            messages.append({"role": r["role"], "content": r["content"]})

        # Call model
        reply = await call_model(messages, model)

        # Save assistant message
        await db.execute(
            "INSERT INTO messages (id, thread_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, thread_id, "assistant", reply, datetime.utcnow().isoformat()),
        )
        await db.commit()
    finally:
        await db.close()

    return ChatResponse(
        thread_id=thread_id,
        reply=reply,
        message_id=message_id,
        model=model,
    )

@app.get("/api/v1/threads/{thread_id}/messages")
async def get_messages(thread_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT id, role, content, created_at FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
            (thread_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()

@app.get("/api/v1/threads")
async def list_threads(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT id, title, created_at, updated_at FROM threads ORDER BY updated_at DESC"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
