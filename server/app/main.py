from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
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
    description="Mobile-first AI agent workspace — phone-first control room for trusted AI workers",
    version="0.5.0",
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
MAX_GOAL_AGENTS = 3

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
    await db.execute("PRAGMA foreign_keys = ON")
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
                role TEXT NOT NULL DEFAULT '',
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

            CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
            CREATE INDEX IF NOT EXISTS idx_permissions_agent ON agent_permissions(agent_id);
            CREATE INDEX IF NOT EXISTS idx_approvals_status_created ON approvals(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_approvals_agent ON approvals(agent_id);
            CREATE INDEX IF NOT EXISTS idx_goal_agents_goal ON goal_agents(goal_id);
            CREATE INDEX IF NOT EXISTS idx_handoffs_goal_status ON handoffs(goal_id, status);
            CREATE INDEX IF NOT EXISTS idx_events_goal_created ON goal_events(goal_id, created_at DESC);
        """)
        await db.commit()

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

# ── Helpers ─────────────────────────────────────────────
def now_iso():
    return datetime.utcnow().isoformat()

async def log_event(db, goal_id: str, event_type: str, actor_type: str = "system",
                    actor_id: Optional[str] = None, payload: Optional[dict] = None):
    await db.execute(
        "INSERT INTO goal_events (id, goal_id, actor_type, actor_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"evt-{uuid.uuid4().hex[:10]}", goal_id, actor_type, actor_id, event_type,
         json.dumps(payload or {}), now_iso())
    )

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

class GoalCreate(BaseModel):
    title: str
    description: Optional[str] = ""

class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class GoalAgentIn(BaseModel):
    agent_id: str
    role: str = ""

class HandoffCreate(BaseModel):
    from_agent_id: str
    to_agent_id: str
    title: str
    instruction: str
    context: Optional[str] = None

class HandoffNote(BaseModel):
    note: Optional[str] = None

# ── Model call ──────────────────────────────────────────
async def call_model(messages: list, model: str) -> str:
    if not MODEL_API_KEY:
        return "[No MODEL_API_KEY set]\n\nSet MODEL_API_KEY and MODEL_API_BASE_URL to get real AI replies."
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
        "version": "0.5.0",
        "status": "ready",
        "docs": "/docs",
        "model_configured": bool(MODEL_API_KEY),
    }

@app.get("/health")
def health():
    return {"ok": True, "time": now_iso()}

# ── Agents ──────────────────────────────────────────────
@app.post("/api/v1/agents")
async def create_agent(body: AgentCreate, _auth=Depends(require_auth)):
    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    handle = body.handle.lstrip("@").lower()
    now = now_iso()
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM agents WHERE handle = ?", (handle,))
        if await cur.fetchone():
            raise HTTPException(status_code=409, detail="Handle already taken")
        await db.execute(
            "INSERT INTO agents (id, name, handle, purpose, personality, system_instructions, status, approval_mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, body.name, handle, body.purpose, body.personality, body.system_instructions,
             "active", body.approval_mode, now, now)
        )
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
        return [dict(r) for r in await cur.fetchall()]
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
        cur = await db.execute("SELECT capability, level FROM agent_permissions WHERE agent_id = ?", (agent_id,))
        agent["permissions"] = [dict(r) for r in await cur.fetchall()]
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
        updates, values = [], []
        for field in ["name", "purpose", "personality", "system_instructions", "approval_mode", "status"]:
            val = getattr(body, field)
            if val is not None:
                updates.append(f"{field} = ?")
                values.append(val)
        if not updates:
            return {"ok": True}
        updates.append("updated_at = ?")
        values.append(now_iso())
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
        await db.execute("UPDATE agents SET status = 'archived', updated_at = ? WHERE id = ?", (now_iso(), agent_id))
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
        now = now_iso()
        cur = await db.execute("SELECT id FROM approval_policies WHERE agent_id = ?", (agent_id,))
        if await cur.fetchone():
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
async def list_approvals(status: str = Query("pending"), agent_id: Optional[str] = None,
                         limit: int = Query(25, le=100), _auth=Depends(require_auth)):
    db = await get_db()
    try:
        if agent_id:
            cur = await db.execute(
                "SELECT * FROM approvals WHERE status = ? AND agent_id = ? ORDER BY created_at DESC LIMIT ?",
                (status, agent_id, limit))
        else:
            cur = await db.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit))
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
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Pending approval not found")
        await db.execute(
            "UPDATE approvals SET status = 'approved', decided_at = ?, decision_note = ? WHERE id = ?",
            (now_iso(), body.note, approval_id))
        await db.commit()
        return {"ok": True, "status": "approved"}
    finally:
        await db.close()

@app.post("/api/v1/approvals/{approval_id}/reject")
async def reject(approval_id: str, body: ApprovalDecision, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM approvals WHERE id = ? AND status = 'pending'", (approval_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Pending approval not found")
        await db.execute(
            "UPDATE approvals SET status = 'rejected', decided_at = ?, decision_note = ? WHERE id = ?",
            (now_iso(), body.note, approval_id))
        await db.commit()
        return {"ok": True, "status": "rejected"}
    finally:
        await db.close()

# ── Goals ───────────────────────────────────────────────
@app.post("/api/v1/goals")
async def create_goal(body: GoalCreate, _auth=Depends(require_auth)):
    goal_id = f"goal-{uuid.uuid4().hex[:8]}"
    now = now_iso()
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO goals (id, title, description, status, created_at, updated_at) VALUES (?, ?, ?, 'active', ?, ?)",
            (goal_id, body.title, body.description or "", now, now))
        await log_event(db, goal_id, "goal.created", payload={"title": body.title})
        await db.commit()
        return {"id": goal_id, "title": body.title, "description": body.description or "", "status": "active", "agents": []}
    finally:
        await db.close()

@app.get("/api/v1/goals")
async def list_goals(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT * FROM goals WHERE status != 'cancelled' ORDER BY updated_at DESC")
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

@app.get("/api/v1/goals/{goal_id}")
async def get_goal(goal_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Goal not found")
        goal = dict(row)
        cur = await db.execute(
            """SELECT ga.agent_id, a.name, a.handle, ga.role, ga.joined_at
               FROM goal_agents ga JOIN agents a ON a.id = ga.agent_id
               WHERE ga.goal_id = ? ORDER BY ga.joined_at""", (goal_id,))
        goal["agents"] = [dict(r) for r in await cur.fetchall()]
        return goal
    finally:
        await db.close()

@app.patch("/api/v1/goals/{goal_id}")
async def update_goal(goal_id: str, body: GoalUpdate, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Goal not found")
        updates, values = [], []
        for field in ["title", "description", "status"]:
            val = getattr(body, field)
            if val is not None:
                updates.append(f"{field} = ?")
                values.append(val)
        if updates:
            updates.append("updated_at = ?")
            values.append(now_iso())
            values.append(goal_id)
            await db.execute(f"UPDATE goals SET {', '.join(updates)} WHERE id = ?", values)
            await db.commit()
        return {"ok": True}
    finally:
        await db.close()

@app.post("/api/v1/goals/{goal_id}/complete")
async def complete_goal(goal_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Goal not found")
        cur = await db.execute(
            "SELECT 1 FROM handoffs WHERE goal_id = ? AND status IN ('pending','accepted') LIMIT 1", (goal_id,))
        if await cur.fetchone():
            raise HTTPException(status_code=409, detail="Resolve open handoffs before completing the goal")
        await db.execute("UPDATE goals SET status = 'completed', updated_at = ? WHERE id = ?", (now_iso(), goal_id))
        await log_event(db, goal_id, "goal.completed")
        await db.commit()
        return {"ok": True, "status": "completed"}
    finally:
        await db.close()

# ── Goal Agents ─────────────────────────────────────────
@app.get("/api/v1/goals/{goal_id}/agents")
async def list_goal_agents(goal_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT ga.agent_id, a.name, a.handle, ga.role, ga.joined_at
               FROM goal_agents ga JOIN agents a ON a.id = ga.agent_id
               WHERE ga.goal_id = ? ORDER BY ga.joined_at""", (goal_id,))
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

@app.post("/api/v1/goals/{goal_id}/agents")
async def add_goal_agent(goal_id: str, body: GoalAgentIn, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT status FROM goals WHERE id = ?", (goal_id,))
        goal = await cur.fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")
        if goal["status"] in ("completed", "cancelled"):
            raise HTTPException(status_code=409, detail=f"Goal is {goal['status']}")

        cur = await db.execute("SELECT id, status FROM agents WHERE id = ?", (body.agent_id,))
        agent = await cur.fetchone()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent["status"] == "archived":
            raise HTTPException(status_code=409, detail="Agent is archived")

        cur = await db.execute("SELECT 1 FROM goal_agents WHERE goal_id = ? AND agent_id = ?",
                               (goal_id, body.agent_id))
        if await cur.fetchone():
            raise HTTPException(status_code=409, detail="Agent is already on this goal")

        cur = await db.execute("SELECT COUNT(*) as c FROM goal_agents WHERE goal_id = ?", (goal_id,))
        count = (await cur.fetchone())["c"]
        if count >= MAX_GOAL_AGENTS:
            raise HTTPException(status_code=409, detail=f"A goal can have at most {MAX_GOAL_AGENTS} agents")

        await db.execute(
            "INSERT INTO goal_agents (goal_id, agent_id, role, joined_at) VALUES (?, ?, ?, ?)",
            (goal_id, body.agent_id, body.role, now_iso()))
        await log_event(db, goal_id, "agent.joined", actor_type="agent", actor_id=body.agent_id,
                        payload={"role": body.role})
        await db.commit()

        cur = await db.execute(
            """SELECT ga.agent_id, a.name, a.handle, ga.role, ga.joined_at
               FROM goal_agents ga JOIN agents a ON a.id = ga.agent_id
               WHERE ga.goal_id = ? AND ga.agent_id = ?""", (goal_id, body.agent_id))
        return dict(await cur.fetchone())
    finally:
        await db.close()

@app.delete("/api/v1/goals/{goal_id}/agents/{agent_id}")
async def remove_goal_agent(goal_id: str, agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT 1 FROM goal_agents WHERE goal_id = ? AND agent_id = ?",
                               (goal_id, agent_id))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Agent is not on this goal")
        cur = await db.execute(
            """SELECT 1 FROM handoffs WHERE goal_id = ? AND status IN ('pending','accepted')
               AND (from_agent_id = ? OR to_agent_id = ?) LIMIT 1""", (goal_id, agent_id, agent_id))
        if await cur.fetchone():
            raise HTTPException(status_code=409, detail="Agent has an open handoff; resolve it first")
        await db.execute("DELETE FROM goal_agents WHERE goal_id = ? AND agent_id = ?", (goal_id, agent_id))
        await log_event(db, goal_id, "agent.removed", actor_type="agent", actor_id=agent_id)
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

# ── Handoffs ────────────────────────────────────────────
@app.post("/api/v1/goals/{goal_id}/handoffs")
async def create_handoff(goal_id: str, body: HandoffCreate, _auth=Depends(require_auth)):
    if body.from_agent_id == body.to_agent_id:
        raise HTTPException(status_code=400, detail="from_agent_id and to_agent_id must be different")
    handoff_id = f"ho-{uuid.uuid4().hex[:8]}"
    db = await get_db()
    try:
        cur = await db.execute("SELECT status FROM goals WHERE id = ?", (goal_id,))
        goal = await cur.fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")
        if goal["status"] in ("completed", "cancelled"):
            raise HTTPException(status_code=409, detail=f"Goal is {goal['status']}")

        for aid in (body.from_agent_id, body.to_agent_id):
            cur = await db.execute("SELECT 1 FROM goal_agents WHERE goal_id = ? AND agent_id = ?",
                                   (goal_id, aid))
            if not await cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Agent {aid} is not on this goal")

        await db.execute(
            "INSERT INTO handoffs (id, goal_id, from_agent_id, to_agent_id, title, instruction, context, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (handoff_id, goal_id, body.from_agent_id, body.to_agent_id, body.title, body.instruction,
             body.context, now_iso()))
        await log_event(db, goal_id, "handoff.created", actor_type="agent", actor_id=body.from_agent_id,
                        payload={"handoff_id": handoff_id, "to_agent_id": body.to_agent_id, "title": body.title})
        await db.commit()

        cur = await db.execute(
            """SELECT h.*, fa.handle AS from_handle, ta.handle AS to_handle
               FROM handoffs h
               JOIN agents fa ON fa.id = h.from_agent_id
               JOIN agents ta ON ta.id = h.to_agent_id
               WHERE h.id = ?""", (handoff_id,))
        return dict(await cur.fetchone())
    finally:
        await db.close()

@app.get("/api/v1/goals/{goal_id}/handoffs")
async def list_handoffs(goal_id: str, status: Optional[str] = None, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        sql = """SELECT h.*, fa.handle AS from_handle, ta.handle AS to_handle
                 FROM handoffs h
                 JOIN agents fa ON fa.id = h.from_agent_id
                 JOIN agents ta ON ta.id = h.to_agent_id
                 WHERE h.goal_id = ?"""
        args: list = [goal_id]
        if status:
            sql += " AND h.status = ?"
            args.append(status)
        sql += " ORDER BY h.created_at DESC"
        cur = await db.execute(sql, args)
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

@app.post("/api/v1/handoffs/{handoff_id}/accept")
async def accept_handoff(handoff_id: str, body: Optional[HandoffNote] = None, _auth=Depends(require_auth)):
    return await _transition_handoff(handoff_id, ("pending",), "accepted", "handoff.accepted", body)

@app.post("/api/v1/handoffs/{handoff_id}/complete")
async def complete_handoff(handoff_id: str, body: Optional[HandoffNote] = None, _auth=Depends(require_auth)):
    return await _transition_handoff(handoff_id, ("accepted",), "completed", "handoff.completed", body)

@app.post("/api/v1/handoffs/{handoff_id}/reject")
async def reject_handoff(handoff_id: str, body: Optional[HandoffNote] = None, _auth=Depends(require_auth)):
    return await _transition_handoff(handoff_id, ("pending",), "rejected", "handoff.rejected", body)

async def _transition_handoff(handoff_id: str, allowed_from: tuple, new_status: str,
                              event_type: str, body: Optional[HandoffNote]):
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT h.*, fa.handle AS from_handle, ta.handle AS to_handle
               FROM handoffs h
               JOIN agents fa ON fa.id = h.from_agent_id
               JOIN agents ta ON ta.id = h.to_agent_id
               WHERE h.id = ?""", (handoff_id,))
        h = await cur.fetchone()
        if not h:
            raise HTTPException(status_code=404, detail="Handoff not found")
        if h["status"] not in allowed_from:
            raise HTTPException(status_code=409,
                                detail=f"Handoff is {h['status']}; must be {' or '.join(allowed_from)}")
        completed_at = now_iso() if new_status in ("completed", "rejected") else None
        await db.execute(
            "UPDATE handoffs SET status = ?, completed_at = COALESCE(?, completed_at) WHERE id = ?",
            (new_status, completed_at, handoff_id))
        await log_event(db, h["goal_id"], event_type, actor_type="agent", actor_id=h["to_agent_id"],
                        payload={"handoff_id": handoff_id, "note": body.note if body else None})
        await db.commit()
        cur = await db.execute(
            """SELECT h.*, fa.handle AS from_handle, ta.handle AS to_handle
               FROM handoffs h
               JOIN agents fa ON fa.id = h.from_agent_id
               JOIN agents ta ON ta.id = h.to_agent_id
               WHERE h.id = ?""", (handoff_id,))
        return dict(await cur.fetchone())
    finally:
        await db.close()

@app.get("/api/v1/goals/{goal_id}/events")
async def list_goal_events(goal_id: str, limit: int = Query(50, le=200), _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT * FROM goal_events WHERE goal_id = ? ORDER BY created_at DESC LIMIT ?",
            (goal_id, limit))
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.get("payload") or "{}")
            except Exception:
                d["payload"] = {}
            result.append(d)
        return result
    finally:
        await db.close()

# ── Chat (kept working) ─────────────────────────────────
@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, _auth=Depends(require_auth)):
    thread_id = req.thread_id or f"thread-{uuid.uuid4().hex[:8]}"
    message_id = f"msg-{uuid.uuid4().hex[:8]}"
    model = req.model or DEFAULT_MODEL
    now = now_iso()
    default_prompt = (
        "You are a helpful, concise personal AI agent on the user's phone. "
        "Be clear, practical, and respectful. Keep replies short unless the user asks for depth."
    )
    system_prompt = req.system_prompt or default_prompt
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM threads WHERE id = ?", (thread_id,))
        if not await cur.fetchone():
            title = req.message[:40] + ("…" if len(req.message) > 40 else "")
            await db.execute(
                "INSERT INTO threads (id, title, system_prompt, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (thread_id, title, system_prompt, now, now))
        else:
            await db.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
        await db.execute(
            "INSERT INTO messages (id, thread_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (f"msg-{uuid.uuid4().hex[:8]}", thread_id, "user", req.message, now))
        cur = await db.execute(
            "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY created_at ASC", (thread_id,))
        history = await cur.fetchall()
        messages = [{"role": "system", "content": system_prompt}]
        for r in history:
            messages.append({"role": r["role"], "content": r["content"]})
        reply = await call_model(messages, model)
        await db.execute(
            "INSERT INTO messages (id, thread_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, thread_id, "assistant", reply, now_iso()))
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
            (thread_id,))
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

@app.get("/api/v1/threads")
async def list_threads(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id, title, created_at, updated_at FROM threads ORDER BY updated_at DESC")
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()
