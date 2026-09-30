from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import uuid
from datetime import datetime

app = FastAPI(
    title="Agent Phone API",
    description="Mobile-first AI agent workspace backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for prototype (replace with SQLite/Postgres)
THREADS: dict = {}
MESSAGES: dict = {}


class ChatRequest(BaseModel):
    thread_id: Optional[str] = None
    message: str
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    message_id: str


@app.get("/")
def root():
    return {
        "name": "Agent Phone API",
        "version": "0.1.0",
        "status": "ready",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Minimal chat endpoint.
    In production this will stream tokens and call the configured model provider.
    """
    thread_id = req.thread_id or f"thread-{uuid.uuid4().hex[:8]}"
    message_id = f"msg-{uuid.uuid4().hex[:8]}"

    if thread_id not in THREADS:
        THREADS[thread_id] = {
            "id": thread_id,
            "created_at": datetime.utcnow().isoformat(),
            "system_prompt": req.system_prompt or "You are a helpful, concise personal AI agent.",
        }
        MESSAGES[thread_id] = []

    MESSAGES[thread_id].append({
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "role": "user",
        "content": req.message,
        "created_at": datetime.utcnow().isoformat(),
    })

    # Placeholder reply — replace with real model call
    reply = (
        f"Received: “{req.message}”\n\n"
        "This is the Agent Phone prototype backend. "
        "Next step: wire a real model provider (OpenAI-compatible, OpenRouter, etc.) "
        "and enable streaming + tool use + approval gates."
    )

    MESSAGES[thread_id].append({
        "id": message_id,
        "role": "assistant",
        "content": reply,
        "created_at": datetime.utcnow().isoformat(),
    })

    return ChatResponse(
        thread_id=thread_id,
        reply=reply,
        message_id=message_id,
    )


@app.get("/api/v1/threads/{thread_id}/messages")
def get_messages(thread_id: str):
    return MESSAGES.get(thread_id, [])


@app.get("/api/v1/threads")
def list_threads():
    return list(THREADS.values())
