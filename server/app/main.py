from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import uuid
import aiosqlite
from datetime import datetime
from pathlib import Path
import httpx

app = FastAPI(
    title="Agent Phone API",
    description="Mobile-first AI agent workspace — phone-first control room for trusted AI workers",
    version="0.3.0",
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
            -- Existing chat tables
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

            -- Priority 1 + 2 tables
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                handle TEXT NOT NULL UNIQUE,
                purpose TEXT NOT NULL,
                personality TEXT,
                system_instructions TEXT,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'paused', 'archived')),
                approval_mode TEXT NOT NULL DEFAULT 'ask_consequential'
                    CHECK (approval_mode IN ('always_ask', 'ask_consequential', 'draft_only')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agent_permissions (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                level TEXT NOT NULL
                    CHECK (level IN ('read', 'draft', 'consequential')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(agent_id, capability),
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS approval_policies (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL UNIQUE,
                default_action TEXT NOT NULL DEFAULT 'ask'
                    CHECK (default_action IN ('allow', 'ask', 'deny')),
                consequential_action TEXT NOT NULL DEFAULT 'ask'
                    CHECK (consequential_action IN ('allow', 'ask', 'deny')),
                external_communication TEXT NOT NULL DEFAULT 'ask'
                    CHECK (external_communication IN ('allow', 'ask', 'deny')),
                destructive_action TEXT NOT NULL DEFAULT 'deny'
                    CHECK (destructive_action IN ('allow', 'ask', 'deny')),
                financial_action TEXT NOT NULL DEFAULT 'deny'
                    CHECK (financial_action IN ('allow', 'ask', 'deny')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                goal_id TEXT,
                action_type TEXT NOT NULL,
                action_level TEXT NOT NULL
                    CHECK (action_level IN ('read', 'draft', 'consequential')),
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                proposed_input TEXT,
                proposed_output TEXT,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')),
                decided_at TEXT,
                decision_note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'completed', 'paused', 'cancelled')),
                owner_label TEXT DEFAULT 'You',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS goal_agents (
                goal_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(goal_id, agent_id),
                FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS handoffs (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                from_agent_id TEXT NOT NULL,
                to_agent_id TEXT NOT NULL,
                title TEXT NOT NULL,
                instruction TEXT NOT NULL,
                context TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'accepted', 'completed', 'rejected')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE,
                FOREIGN KEY(from_agent_id) REFERENCES agents(id),
                FOREIGN KEY(to_agent_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS goal_events (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                actor_type TEXT NOT NULL
                    CHECK (actor_type IN ('user', 'agent', 'system')),
                actor_id TEXT,
                event_type TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
            CREATE INDEX IF NOT EXISTS idx_permissions_agent ON agent_permissions(agent_id);
            CREATE INDEX IF NOT EXISTS idx_approvals_status_created ON approvals(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_approvals_agent ON approvals(agent_id);
            CREATE INDEX IF NOT EXISTS idx_goal_agents_goal ON goal_agents(goal_id);
            CREATE INDEX IF NOT EXISTS idx_handoffs_goal_status ON handoffs(goal_id, status);
            CREATE INDEX IF NOT EXISTS idx_events_goal_created ON goal_events(goal_id, created_at DESC);
        """)
        await db.commit()

        # Seed a default agent if none exist
        cur = await db.execute("SELECT COUNT(*) as c FROM agents")
        row = await cur.fetchone()
        if row["c"] == 0:
            agent_id = f"agent-{uuid.uuid4().hex[:8]}"
            now = datetime.utcnow().isoformat()
            await db.execute(
                "INSERT INTO agents (id, name, handle, purpose, personality, system_instructions, status, approval_mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (agent_id, "Atlas", "atlas", "Research and organize project information",
                 "Concise, analytical, practical",
                 "You are Atlas, a research and organization agent. Be clear, practical, and concise.",
                 "active", "ask_consequential", now, now)
            )
            await db.execute(
                "INSERT INTO approval_policies (id, agent_id, default_action, consequential_action, external_communication, destructive_action, financial_action) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"pol-{uuid.uuid4().hex[:8]}", agent_id, "allow", "ask", "ask", "deny", "deny")
            )
            for cap, level in [("files", "read"), ("calendar", "draft"), ("messaging", "draft")]:
                await db.execute(
                    "INSERT INTO agent_permissions (id, agent_id, capability, level) VALUES (?, ?, ?, ?)",
                    (f"perm-{uuid.uuid4().hex[:8]}", agent_id, cap, level)
                )
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

class AgentCreate(BaseModel):
    name: str
    handle: str
    purpose: str
    personality: Optional[str] = None
    system_instructions: Optional[str] = None
    approval_mode: str = "ask_consequential"

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    purpose: Optional[str] = None
    personality: Optional[str] = None
    system_instructions: Optional[str] = None
    approval_mode: Optional[str] = None
    status: Optional[str] = None

class PermissionItem(BaseModel):
    capability: str
    level: str

class PermissionsUpdate(BaseModel):
    permissions: List[PermissionItem]

class ApprovalPolicyUpdate(BaseModel):
    default_action: str = "ask"
    consequential_action: str = "ask"
    external_communication: str = "ask"
    destructive_action: str = "deny"
    financial_action: str = "deny"

class ApprovalDecision(BaseModel):
    note: Optional[str] = None

# ── Model call ──────────────────────────────────────────
async def call_model(messages: list, model: str) -> str:
    if not MODEL_API_KEY:
        return (
            "[No MODEL_API_KEY set]\n\n"
            "Set MODEL_API_KEY and MODEL_API_BASE_URL in your environment "
            "to get real AI replies."
        )
    url = f"{MODEL_API_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {MODEL_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 1024}
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
        "version": "0.3.0",
        "status": "ready",
        "docs": "/docs",
        "model_configured": bool(MODEL_API_KEY),
    }

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

# ── Agents ──────────────────────────────────────────────
@app.post("/api/v1/agents")
async def create_agent(body: AgentCreate, _auth=Depends(require_auth)):
    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    handle = body.handle.lstrip("@").lower()
    now = datetime.utcnow().isoformat()
    db = await get_db()
    try:
        # Check handle uniqueness
        cur = await db.execute("SELECT id FROM agents WHERE handle = ?", (handle,))
        if await cur.fetchone():
            raise HTTPException(status_code=409, detail="Handle already taken")
        await db.execute(
            "INSERT INTO agents (id, name, handle, purpose, personality, system_instructions, status, approval_mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, body.name, handle, body.purpose, body.personality, body.system_instructions,
             "active", body.approval_mode, now, now)
        )
        # Default approval policy
        await db.execute(
            "INSERT INTO approval_policies (id, agent_id, default_action, consequential_action, external_communication, destructive_action, financial_action) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"pol-{uuid.uuid4().hex[:8]}", agent_id, "allow", "ask", "ask", "deny", "deny")
        )
        await db.commit()
        return {"id": agent_id, "name": body.name, "handle": handle, "status": "active"}
    finally:
        await db.close()

@app.get("/api/v1/agents")
async def list_agents(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT id, name, handle, purpose, personality, status, approval_mode, created_at, updated_at FROM agents WHERE status != 'archived' ORDER BY updated_at DESC"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()

@app.get("/api/v1/agents/{agent_id}")
async def get_agent(agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent = dict(row)
        # Attach permissions
        cur = await db.execute("SELECT capability, level FROM agent_permissions WHERE agent_id = ?", (agent_id,))
        agent["permissions"] = [dict(r) for r in await cur.fetchall()]
        # Attach policy
        cur = await db.execute("SELECT * FROM approval_policies WHERE agent_id = ?", (agent_id,))
        pol = await cur.fetchone()
        agent["approval_policy"] = dict(pol) if pol else None
        return agent
    finally:
        await db.close()

@app.patch("/api/v1/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM agents WHERE id = ?", (agent_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Agent not found")
        updates = []
        values = []
        for field in ["name", "purpose", "personality", "system_instructions", "approval_mode", "status"]:
            val = getattr(body, field)
            if val is not None:
                updates.append(f"{field} = ?")
                values.append(val)
        if not updates:
            return {"ok": True}
        updates.append("updated_at = ?")
        values.append(datetime.utcnow().isoformat())
        values.append(agent_id)
        await db.execute(f"UPDATE agents SET {', '.join(updates)} WHERE id = ?", values)
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

@app.delete("/api/v1/agents/{agent_id}")
async def archive_agent(agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE agents SET status = 'archived', updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), agent_id)
        )
        await db.commit()
        return {"ok": True, "status": "archived"}
    finally:
        await db.close()

# ── Permissions ─────────────────────────────────────────
@app.get("/api/v1/agents/{agent_id}/permissions")
async def get_permissions(agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT capability, level FROM agent_permissions WHERE agent_id = ?", (agent_id,))
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

@app.put("/api/v1/agents/{agent_id}/permissions")
async def set_permissions(agent_id: str, body: PermissionsUpdate, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        await db.execute("DELETE FROM agent_permissions WHERE agent_id = ?", (agent_id,))
        for p in body.permissions:
            await db.execute(
                "INSERT INTO agent_permissions (id, agent_id, capability, level) VALUES (?, ?, ?, ?)",
                (f"perm-{uuid.uuid4().hex[:8]}", agent_id, p.capability, p.level)
            )
        await db.commit()
        return {"ok": True, "count": len(body.permissions)}
    finally:
        await db.close()

# ── Approval Policy ─────────────────────────────────────
@app.get("/api/v1/agents/{agent_id}/approval-policy")
async def get_approval_policy(agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM approval_policies WHERE agent_id = ?", (agent_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found")
        return dict(row)
    finally:
        await db.close()

@app.put("/api/v1/agents/{agent_id}/approval-policy")
async def set_approval_policy(agent_id: str, body: ApprovalPolicyUpdate, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        now = datetime.utcnow().isoformat()
        cur = await db.execute("SELECT id FROM approval_policies WHERE agent_id = ?", (agent_id,))
        existing = await cur.fetchone()
        if existing:
            await db.execute(
                "UPDATE approval_policies SET default_action=?, consequential_action=?, external_communication=?, destructive_action=?, financial_action=?, updated_at=? WHERE agent_id=?",
                (body.default_action, body.consequential_action, body.external_communication,
                 body.destructive_action, body.financial_action, now, agent_id)
            )
        else:
            await db.execute(
                "INSERT INTO approval_policies (id, agent_id, default_action, consequential_action, external_communication, destructive_action, financial_action) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"pol-{uuid.uuid4().hex[:8]}", agent_id, body.default_action, body.consequential_action,
                 body.external_communication, body.destructive_action, body.financial_action)
            )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

# ── Approvals Inbox ─────────────────────────────────────
@app.get("/api/v1/approvals/count")
async def approvals_count(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT COUNT(*) as c FROM approvals WHERE status = 'pending'")
        row = await cur.fetchone()
        return {"pending": row["c"]}
    finally:
        await db.close()

@app.get("/api/v1/approvals")
async def list_approvals(
    status: str = Query("pending"),
    agent_id: Optional[str] = None,
    limit: int = Query(25, le=100),
    _auth=Depends(require_auth),
):
    db = await get_db()
    try:
        if agent_id:
            cur = await db.execute(
                "SELECT * FROM approvals WHERE status = ? AND agent_id = ? ORDER BY created_at DESC LIMIT ?",
                (status, agent_id, limit)
            )
        else:
            cur = await db.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

@app.get("/api/v1/approvals/{approval_id}")
async def get_approval(approval_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Approval not found")
        return dict(row)
    finally:
        await db.close()

@app.post("/api/v1/approvals/{approval_id}/approve")
async def approve(approval_id: str, body: ApprovalDecision, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM approvals WHERE id = ? AND status = 'pending'", (approval_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pending approval not found")
        now = datetime.utcnow().isoformat()
        await db.execute(
            "UPDATE approvals SET status = 'approved', decided_at = ?, decision_note = ? WHERE id = ?",
            (now, body.note, approval_id)
        )
        await db.commit()
        return {"ok": True, "status": "approved"}
    finally:
        await db.close()

@app.post("/api/v1/approvals/{approval_id}/reject")
async def reject(approval_id: str, body: ApprovalDecision, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM approvals WHERE id = ? AND status = 'pending'", (approval_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pending approval not found")
        now = datetime.utcnow().isoformat()
        await db.execute(
            "UPDATE approvals SET status = 'rejected', decided_at = ?, decision_note = ? WHERE id = ?",
            (now, body.note, approval_id)
        )
        await db.commit()
        return {"ok": True, "status": "rejected"}
    finally:
        await db.close()

# ── Chat (kept working) ─────────────────────────────────
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
        cur = await db.execute("SELECT id FROM threads WHERE id = ?", (thread_id,))
        row = await cur.fetchone()
        if not row:
            title = req.message[:40] + ("…" if len(req.message) > 40 else "")
            await db.execute(
                "INSERT INTO threads (id, title, system_prompt, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (thread_id, title, system_prompt, now, now),
            )
        else:
            await db.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
        user_msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        await db.execute(
            "INSERT INTO messages (id, thread_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_msg_id, thread_id, "user", req.message, now),
        )
        cur = await db.execute(
            "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY created_at ASC", (thread_id,)
        )
        history_rows = await cur.fetchall()
        messages = [{"role": "system", "content": system_prompt}]
        for r in history_rows:
            messages.append({"role": r["role"], "content": r["content"]})
        reply = await call_model(messages, model)
        await db.execute(
            "INSERT INTO messages (id, thread_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, thread_id, "assistant", reply, datetime.utcnow().isoformat()),
        )
        await db.commit()
    finally:
        await db.close()
    return ChatResponse(thread_id=thread_id, reply=reply, message_id=message_id, model=model)

@app.get("/api/v1/threads/{thread_id}/messages")
async def get_messages(thread_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT id, role, content, created_at FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
            (thread_id,),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

@app.get("/api/v1/threads")
async def list_threads(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT id, title, created_at, updated_at FROM threads ORDER BY updated_at DESC"
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()
