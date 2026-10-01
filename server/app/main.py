from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os, uuid, json, aiosqlite, httpx
from datetime import datetime
from pathlib import Path

app = FastAPI(title="Agent Phone API", description="Phone-first control room for trusted AI workers", version="0.7.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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

async def log_event(db, goal_id, event_type, actor_type="system", actor_id=None, payload=None):
    await db.execute("INSERT INTO goal_events (id, goal_id, actor_type, actor_id, event_type, payload, created_at) VALUES (?,?,?,?,?,?,?)",
        (f"evt-{uuid.uuid4().hex[:10]}", goal_id, actor_type, actor_id, event_type, json.dumps(payload or {}), now_iso()))

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS threads (id TEXT PRIMARY KEY, title TEXT, system_prompt TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, thread_id TEXT, role TEXT, content TEXT, created_at TEXT, FOREIGN KEY (thread_id) REFERENCES threads(id));
            CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, name TEXT NOT NULL, handle TEXT NOT NULL UNIQUE, purpose TEXT NOT NULL, personality TEXT, system_instructions TEXT, status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','archived')), approval_mode TEXT NOT NULL DEFAULT 'ask_consequential' CHECK (approval_mode IN ('always_ask','ask_consequential','draft_only')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS agent_permissions (id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, capability TEXT NOT NULL, level TEXT NOT NULL CHECK (level IN ('read','draft','consequential')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(agent_id, capability), FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS approval_policies (id TEXT PRIMARY KEY, agent_id TEXT NOT NULL UNIQUE, default_action TEXT NOT NULL DEFAULT 'ask' CHECK (default_action IN ('allow','ask','deny')), consequential_action TEXT NOT NULL DEFAULT 'ask' CHECK (consequential_action IN ('allow','ask','deny')), external_communication TEXT NOT NULL DEFAULT 'ask' CHECK (external_communication IN ('allow','ask','deny')), destructive_action TEXT NOT NULL DEFAULT 'deny' CHECK (destructive_action IN ('allow','ask','deny')), financial_action TEXT NOT NULL DEFAULT 'deny' CHECK (financial_action IN ('allow','ask','deny')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, goal_id TEXT, action_type TEXT NOT NULL, action_level TEXT NOT NULL CHECK (action_level IN ('read','draft','consequential')), title TEXT NOT NULL, description TEXT NOT NULL, proposed_input TEXT, proposed_output TEXT, reason TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','expired','cancelled')), decided_at TEXT, decision_note TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS goals (id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT, status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','paused','cancelled')), owner_label TEXT DEFAULT 'You', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS goal_agents (goal_id TEXT NOT NULL, agent_id TEXT NOT NULL, role TEXT NOT NULL DEFAULT '', joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(goal_id, agent_id), FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE, FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS handoffs (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, from_agent_id TEXT NOT NULL, to_agent_id TEXT NOT NULL, title TEXT NOT NULL, instruction TEXT NOT NULL, context TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','completed','rejected')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT, FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE, FOREIGN KEY(from_agent_id) REFERENCES agents(id), FOREIGN KEY(to_agent_id) REFERENCES agents(id));
            CREATE TABLE IF NOT EXISTS goal_events (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, actor_type TEXT NOT NULL CHECK (actor_type IN ('user','agent','system')), actor_id TEXT, event_type TEXT NOT NULL, payload TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE);
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
        if (await cur.fetchone())["c"] == 0:
            aid = f"agent-{uuid.uuid4().hex[:8]}"; now = datetime.utcnow().isoformat()
            await db.execute("INSERT INTO agents (id,name,handle,purpose,personality,system_instructions,status,approval_mode,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (aid,"Atlas","atlas","Research and organize project information","Concise, analytical, practical","You are Atlas, a research agent.","active","ask_consequential",now,now))
            await db.execute("INSERT INTO approval_policies (id,agent_id,default_action,consequential_action,external_communication,destructive_action,financial_action) VALUES (?,?,?,?,?,?,?)",
                (f"pol-{uuid.uuid4().hex[:8]}",aid,"allow","ask","ask","deny","deny"))
            for cap,lvl in [("files","read"),("calendar","draft"),("messaging","draft")]:
                await db.execute("INSERT INTO agent_permissions (id,agent_id,capability,level) VALUES (?,?,?,?)",(f"perm-{uuid.uuid4().hex[:8]}",aid,cap,lvl))
            await db.commit()

@app.on_event("startup")
async def startup(): await init_db()

class ChatRequest(BaseModel):
    thread_id: Optional[str]=None; message: str; system_prompt: Optional[str]=None; model: Optional[str]=None
class ChatResponse(BaseModel):
    thread_id: str; reply: str; message_id: str; model: str
class AgentCreate(BaseModel):
    name: str; handle: str; purpose: str; personality: Optional[str]=None; system_instructions: Optional[str]=None; approval_mode: str="ask_consequential"
class AgentUpdate(BaseModel):
    name: Optional[str]=None; purpose: Optional[str]=None; personality: Optional[str]=None; system_instructions: Optional[str]=None; approval_mode: Optional[str]=None; status: Optional[str]=None
class PermissionItem(BaseModel):
    capability: str; level: str
class PermissionsUpdate(BaseModel):
    permissions: List[PermissionItem]
class ApprovalPolicyUpdate(BaseModel):
    default_action: str="ask"; consequential_action: str="ask"; external_communication: str="ask"; destructive_action: str="deny"; financial_action: str="deny"
class ApprovalDecision(BaseModel):
    note: Optional[str]=None
class ApprovalCreate(BaseModel):
    agent_id: str; title: str; description: str; action_type: str="messaging.draft"; action_level: str="consequential"; proposed_output: Optional[str]=None; proposed_input: Optional[str]=None; reason: Optional[str]=None; goal_id: Optional[str]=None
class GoalCreate(BaseModel):
    title: str; description: Optional[str]=""
class GoalUpdate(BaseModel):
    title: Optional[str]=None; description: Optional[str]=None; status: Optional[str]=None
class GoalAgentIn(BaseModel):
    agent_id: str; role: str=""
class HandoffCreate(BaseModel):
    from_agent_id: str; to_agent_id: str; title: str; instruction: str; context: Optional[str]=None
class HandoffNote(BaseModel):
    note: Optional[str]=None

async def call_model(messages, model):
    if not MODEL_API_KEY: return "[No MODEL_API_KEY set]"
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            r = await client.post(f"{MODEL_API_BASE_URL}/chat/completions", headers={"Authorization": f"Bearer {MODEL_API_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 1024})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e: return f"Model error: {e}"

@app.get("/")
def root(): return {"name": "Agent Phone API", "version": "0.7.0", "status": "ready", "docs": "/docs", "model_configured": bool(MODEL_API_KEY)}
@app.get("/health")
def health(): return {"ok": True, "time": now_iso()}
@app.get("/ready")
async def ready():
    try:
        db = await get_db(); await db.execute("SELECT 1"); await db.close()
        return {"ok": True, "db": True}
    except Exception as e: raise HTTPException(503, str(e))

@app.post("/api/v1/agents")
async def create_agent(body: AgentCreate, _auth=Depends(require_auth)):
    aid = f"agent-{uuid.uuid4().hex[:8]}"; handle = body.handle.lstrip("@").lower(); now = now_iso()
    db = await get_db()
    try:
        if await (await db.execute("SELECT id FROM agents WHERE handle=?", (handle,))).fetchone():
            raise HTTPException(409, "Handle already taken")
        await db.execute("INSERT INTO agents (id,name,handle,purpose,personality,system_instructions,status,approval_mode,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (aid, body.name, handle, body.purpose, body.personality, body.system_instructions, "active", body.approval_mode, now, now))
        await db.execute("INSERT INTO approval_policies (id,agent_id,default_action,consequential_action,external_communication,destructive_action,financial_action) VALUES (?,?,?,?,?,?,?)",
            (f"pol-{uuid.uuid4().hex[:8]}", aid, "allow", "ask", "ask", "deny", "deny"))
        await db.commit()
        return {"id": aid, "name": body.name, "handle": handle, "status": "active"}
    finally: await db.close()

@app.get("/api/v1/agents")
async def list_agents(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id,name,handle,purpose,personality,status,approval_mode,created_at,updated_at FROM agents WHERE status!='archived' ORDER BY updated_at DESC")
        return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()

@app.get("/api/v1/agents/{agent_id}")
async def get_agent(agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM agents WHERE id=?", (agent_id,)); row = await cur.fetchone()
        if not row: raise HTTPException(404, "Agent not found")
        agent = dict(row)
        cur = await db.execute("SELECT capability,level FROM agent_permissions WHERE agent_id=?", (agent_id,))
        agent["permissions"] = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute("SELECT * FROM approval_policies WHERE agent_id=?", (agent_id,)); pol = await cur.fetchone()
        agent["approval_policy"] = dict(pol) if pol else None
        return agent
    finally: await db.close()

@app.patch("/api/v1/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        if not await (await db.execute("SELECT id FROM agents WHERE id=?", (agent_id,))).fetchone(): raise HTTPException(404, "Agent not found")
        updates, values = [], []
        for f in ["name","purpose","personality","system_instructions","approval_mode","status"]:
            v = getattr(body, f)
            if v is not None: updates.append(f"{f}=?"); values.append(v)
        if updates:
            updates.append("updated_at=?"); values.append(now_iso()); values.append(agent_id)
            await db.execute(f"UPDATE agents SET {', '.join(updates)} WHERE id=?", values); await db.commit()
        return {"ok": True}
    finally: await db.close()

@app.delete("/api/v1/agents/{agent_id}")
async def archive_agent(agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        await db.execute("UPDATE agents SET status='archived', updated_at=? WHERE id=?", (now_iso(), agent_id)); await db.commit()
        return {"ok": True, "status": "archived"}
    finally: await db.close()

@app.get("/api/v1/agents/{agent_id}/permissions")
async def get_permissions(agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT capability,level FROM agent_permissions WHERE agent_id=?", (agent_id,))
        return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()

@app.put("/api/v1/agents/{agent_id}/permissions")
async def set_permissions(agent_id: str, body: PermissionsUpdate, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        await db.execute("DELETE FROM agent_permissions WHERE agent_id=?", (agent_id,))
        for p in body.permissions:
            await db.execute("INSERT INTO agent_permissions (id,agent_id,capability,level) VALUES (?,?,?,?)", (f"perm-{uuid.uuid4().hex[:8]}", agent_id, p.capability, p.level))
        await db.commit(); return {"ok": True, "count": len(body.permissions)}
    finally: await db.close()

@app.get("/api/v1/agents/{agent_id}/approval-policy")
async def get_approval_policy(agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM approval_policies WHERE agent_id=?", (agent_id,)); row = await cur.fetchone()
        if not row: raise HTTPException(404, "Policy not found")
        return dict(row)
    finally: await db.close()

@app.put("/api/v1/agents/{agent_id}/approval-policy")
async def set_approval_policy(agent_id: str, body: ApprovalPolicyUpdate, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        now = now_iso()
        if await (await db.execute("SELECT id FROM approval_policies WHERE agent_id=?", (agent_id,))).fetchone():
            await db.execute("UPDATE approval_policies SET default_action=?,consequential_action=?,external_communication=?,destructive_action=?,financial_action=?,updated_at=? WHERE agent_id=?",
                (body.default_action, body.consequential_action, body.external_communication, body.destructive_action, body.financial_action, now, agent_id))
        else:
            await db.execute("INSERT INTO approval_policies (id,agent_id,default_action,consequential_action,external_communication,destructive_action,financial_action) VALUES (?,?,?,?,?,?,?)",
                (f"pol-{uuid.uuid4().hex[:8]}", agent_id, body.default_action, body.consequential_action, body.external_communication, body.destructive_action, body.financial_action))
        await db.commit(); return {"ok": True}
    finally: await db.close()

@app.get("/api/v1/approvals/count")
async def approvals_count(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT COUNT(*) as c FROM approvals WHERE status='pending'")
        return {"pending": (await cur.fetchone())["c"]}
    finally: await db.close()

@app.get("/api/v1/approvals")
async def list_approvals(status: str=Query("pending"), agent_id: Optional[str]=None, limit: int=Query(25, le=100), _auth=Depends(require_auth)):
    db = await get_db()
    try:
        if agent_id:
            cur = await db.execute("SELECT * FROM approvals WHERE status=? AND agent_id=? ORDER BY created_at DESC LIMIT ?", (status, agent_id, limit))
        else:
            cur = await db.execute("SELECT * FROM approvals WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit))
        return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()

@app.get("/api/v1/approvals/{approval_id}")
async def get_approval(approval_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)); row = await cur.fetchone()
        if not row: raise HTTPException(404, "Approval not found")
        return dict(row)
    finally: await db.close()

@app.post("/api/v1/approvals")
async def create_approval(body: ApprovalCreate, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        if not await (await db.execute("SELECT id FROM agents WHERE id=? AND status!='archived'", (body.agent_id,))).fetchone():
            raise HTTPException(404, "Agent not found")
        aid = f"apr-{uuid.uuid4().hex[:10]}"
        await db.execute("INSERT INTO approvals (id,agent_id,goal_id,action_type,action_level,title,description,proposed_input,proposed_output,reason,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?)",
            (aid, body.agent_id, body.goal_id, body.action_type, body.action_level, body.title, body.description, body.proposed_input, body.proposed_output, body.reason, now_iso()))
        if body.goal_id:
            await log_event(db, body.goal_id, "approval.created", actor_type="agent", actor_id=body.agent_id, payload={"approval_id": aid, "title": body.title})
        await db.commit()
        cur = await db.execute("SELECT * FROM approvals WHERE id=?", (aid,)); return dict(await cur.fetchone())
    finally: await db.close()

@app.post("/api/v1/approvals/demo")
async def create_demo_approval(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id,name,handle FROM agents WHERE status='active' LIMIT 1"); agent = await cur.fetchone()
        if not agent: raise HTTPException(400, "No active agent. Create an agent first.")
        aid = f"apr-{uuid.uuid4().hex[:10]}"
        title = "Send follow-up to programme partner"
        description = f"{agent['name']} (@{agent['handle']}) wants to send an external message."
        proposed = "Hi Sarah,\n\nFollowing up on the ISEYC youth programme partnership proposal. We have completed the eligibility review and the shortlist is ready for your feedback.\n\nBest regards"
        await db.execute("INSERT INTO approvals (id,agent_id,goal_id,action_type,action_level,title,description,proposed_output,reason,status,created_at) VALUES (?,?,NULL,'messaging.send','consequential',?,?,?,?,'pending',?)",
            (aid, agent["id"], title, description, proposed, "You asked for a partner follow-up after the shortlist was ready.", now_iso()))
        await db.commit()
        cur = await db.execute("SELECT * FROM approvals WHERE id=?", (aid,)); return dict(await cur.fetchone())
    finally: await db.close()

@app.post("/api/v1/approvals/{approval_id}/approve")
async def approve(approval_id: str, body: ApprovalDecision, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        if not await (await db.execute("SELECT * FROM approvals WHERE id=? AND status='pending'", (approval_id,))).fetchone():
            raise HTTPException(404, "Pending approval not found")
        await db.execute("UPDATE approvals SET status='approved', decided_at=?, decision_note=? WHERE id=?", (now_iso(), body.note, approval_id))
        await db.commit(); return {"ok": True, "status": "approved"}
    finally: await db.close()

@app.post("/api/v1/approvals/{approval_id}/reject")
async def reject(approval_id: str, body: ApprovalDecision, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        if not await (await db.execute("SELECT * FROM approvals WHERE id=? AND status='pending'", (approval_id,))).fetchone():
            raise HTTPException(404, "Pending approval not found")
        await db.execute("UPDATE approvals SET status='rejected', decided_at=?, decision_note=? WHERE id=?", (now_iso(), body.note, approval_id))
        await db.commit(); return {"ok": True, "status": "rejected"}
    finally: await db.close()

@app.post("/api/v1/goals")
async def create_goal(body: GoalCreate, _auth=Depends(require_auth)):
    gid = f"goal-{uuid.uuid4().hex[:8]}"; now = now_iso()
    db = await get_db()
    try:
        await db.execute("INSERT INTO goals (id,title,description,status,created_at,updated_at) VALUES (?,?,?,'active',?,?)", (gid, body.title, body.description or "", now, now))
        await log_event(db, gid, "goal.created", payload={"title": body.title}); await db.commit()
        return {"id": gid, "title": body.title, "description": body.description or "", "status": "active", "agents": []}
    finally: await db.close()

@app.get("/api/v1/goals")
async def list_goals(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM goals WHERE status!='cancelled' ORDER BY updated_at DESC")
        return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()

@app.get("/api/v1/goals/{goal_id}")
async def get_goal(goal_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM goals WHERE id=?", (goal_id,)); row = await cur.fetchone()
        if not row: raise HTTPException(404, "Goal not found")
        goal = dict(row)
        cur = await db.execute("SELECT ga.agent_id,a.name,a.handle,ga.role,ga.joined_at FROM goal_agents ga JOIN agents a ON a.id=ga.agent_id WHERE ga.goal_id=? ORDER BY ga.joined_at", (goal_id,))
        goal["agents"] = [dict(r) for r in await cur.fetchall()]; return goal
    finally: await db.close()

@app.patch("/api/v1/goals/{goal_id}")
async def update_goal(goal_id: str, body: GoalUpdate, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        if not await (await db.execute("SELECT * FROM goals WHERE id=?", (goal_id,))).fetchone(): raise HTTPException(404, "Goal not found")
        updates, values = [], []
        for f in ["title","description","status"]:
            v = getattr(body, f)
            if v is not None: updates.append(f"{f}=?"); values.append(v)
        if updates:
            updates.append("updated_at=?"); values.append(now_iso()); values.append(goal_id)
            await db.execute(f"UPDATE goals SET {', '.join(updates)} WHERE id=?", values); await db.commit()
        return {"ok": True}
    finally: await db.close()

@app.post("/api/v1/goals/{goal_id}/complete")
async def complete_goal(goal_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        if not await (await db.execute("SELECT * FROM goals WHERE id=?", (goal_id,))).fetchone(): raise HTTPException(404, "Goal not found")
        if await (await db.execute("SELECT 1 FROM handoffs WHERE goal_id=? AND status IN ('pending','accepted') LIMIT 1", (goal_id,))).fetchone():
            raise HTTPException(409, "Resolve open handoffs before completing the goal")
        await db.execute("UPDATE goals SET status='completed', updated_at=? WHERE id=?", (now_iso(), goal_id))
        await log_event(db, goal_id, "goal.completed"); await db.commit()
        return {"ok": True, "status": "completed"}
    finally: await db.close()

@app.get("/api/v1/goals/{goal_id}/agents")
async def list_goal_agents(goal_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT ga.agent_id,a.name,a.handle,ga.role,ga.joined_at FROM goal_agents ga JOIN agents a ON a.id=ga.agent_id WHERE ga.goal_id=? ORDER BY ga.joined_at", (goal_id,))
        return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()

@app.post("/api/v1/goals/{goal_id}/agents")
async def add_goal_agent(goal_id: str, body: GoalAgentIn, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT status FROM goals WHERE id=?", (goal_id,)); goal = await cur.fetchone()
        if not goal: raise HTTPException(404, "Goal not found")
        if goal["status"] in ("completed","cancelled"): raise HTTPException(409, f"Goal is {goal['status']}")
        cur = await db.execute("SELECT id,status FROM agents WHERE id=?", (body.agent_id,)); agent = await cur.fetchone()
        if not agent: raise HTTPException(404, "Agent not found")
        if agent["status"]=="archived": raise HTTPException(409, "Agent is archived")
        if await (await db.execute("SELECT 1 FROM goal_agents WHERE goal_id=? AND agent_id=?", (goal_id, body.agent_id))).fetchone():
            raise HTTPException(409, "Agent is already on this goal")
        if (await (await db.execute("SELECT COUNT(*) as c FROM goal_agents WHERE goal_id=?", (goal_id,))).fetchone())["c"] >= MAX_GOAL_AGENTS:
            raise HTTPException(409, f"A goal can have at most {MAX_GOAL_AGENTS} agents")
        await db.execute("INSERT INTO goal_agents (goal_id,agent_id,role,joined_at) VALUES (?,?,?,?)", (goal_id, body.agent_id, body.role, now_iso()))
        await log_event(db, goal_id, "agent.joined", actor_type="agent", actor_id=body.agent_id, payload={"role": body.role}); await db.commit()
        cur = await db.execute("SELECT ga.agent_id,a.name,a.handle,ga.role,ga.joined_at FROM goal_agents ga JOIN agents a ON a.id=ga.agent_id WHERE ga.goal_id=? AND ga.agent_id=?", (goal_id, body.agent_id))
        return dict(await cur.fetchone())
    finally: await db.close()

@app.delete("/api/v1/goals/{goal_id}/agents/{agent_id}")
async def remove_goal_agent(goal_id: str, agent_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        if not await (await db.execute("SELECT 1 FROM goal_agents WHERE goal_id=? AND agent_id=?", (goal_id, agent_id))).fetchone():
            raise HTTPException(404, "Agent is not on this goal")
        if await (await db.execute("SELECT 1 FROM handoffs WHERE goal_id=? AND status IN ('pending','accepted') AND (from_agent_id=? OR to_agent_id=?) LIMIT 1", (goal_id, agent_id, agent_id))).fetchone():
            raise HTTPException(409, "Agent has an open handoff; resolve it first")
        await db.execute("DELETE FROM goal_agents WHERE goal_id=? AND agent_id=?", (goal_id, agent_id))
        await log_event(db, goal_id, "agent.removed", actor_type="agent", actor_id=agent_id); await db.commit()
        return {"ok": True}
    finally: await db.close()

@app.post("/api/v1/goals/{goal_id}/handoffs")
async def create_handoff(goal_id: str, body: HandoffCreate, _auth=Depends(require_auth)):
    if body.from_agent_id == body.to_agent_id: raise HTTPException(400, "from_agent_id and to_agent_id must be different")
    hid = f"ho-{uuid.uuid4().hex[:8]}"
    db = await get_db()
    try:
        cur = await db.execute("SELECT status FROM goals WHERE id=?", (goal_id,)); goal = await cur.fetchone()
        if not goal: raise HTTPException(404, "Goal not found")
        if goal["status"] in ("completed","cancelled"): raise HTTPException(409, f"Goal is {goal['status']}")
        for aid in (body.from_agent_id, body.to_agent_id):
            if not await (await db.execute("SELECT 1 FROM goal_agents WHERE goal_id=? AND agent_id=?", (goal_id, aid))).fetchone():
                raise HTTPException(409, f"Agent {aid} is not on this goal")
        await db.execute("INSERT INTO handoffs (id,goal_id,from_agent_id,to_agent_id,title,instruction,context,status,created_at) VALUES (?,?,?,?,?,?,?,'pending',?)",
            (hid, goal_id, body.from_agent_id, body.to_agent_id, body.title, body.instruction, body.context, now_iso()))
        await log_event(db, goal_id, "handoff.created", actor_type="agent", actor_id=body.from_agent_id, payload={"handoff_id": hid, "to_agent_id": body.to_agent_id, "title": body.title})
        await db.commit()
        cur = await db.execute("SELECT h.*,fa.handle AS from_handle,ta.handle AS to_handle FROM handoffs h JOIN agents fa ON fa.id=h.from_agent_id JOIN agents ta ON ta.id=h.to_agent_id WHERE h.id=?", (hid,))
        return dict(await cur.fetchone())
    finally: await db.close()

@app.get("/api/v1/goals/{goal_id}/handoffs")
async def list_handoffs(goal_id: str, status: Optional[str]=None, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        sql = "SELECT h.*,fa.handle AS from_handle,ta.handle AS to_handle FROM handoffs h JOIN agents fa ON fa.id=h.from_agent_id JOIN agents ta ON ta.id=h.to_agent_id WHERE h.goal_id=?"
        args: list = [goal_id]
        if status: sql += " AND h.status=?"; args.append(status)
        sql += " ORDER BY h.created_at DESC"
        cur = await db.execute(sql, args); return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()

async def _transition_handoff(handoff_id, allowed_from, new_status, event_type, body):
    db = await get_db()
    try:
        cur = await db.execute("SELECT h.*,fa.handle AS from_handle,ta.handle AS to_handle FROM handoffs h JOIN agents fa ON fa.id=h.from_agent_id JOIN agents ta ON ta.id=h.to_agent_id WHERE h.id=?", (handoff_id,))
        h = await cur.fetchone()
        if not h: raise HTTPException(404, "Handoff not found")
        if h["status"] not in allowed_from: raise HTTPException(409, f"Handoff is {h['status']}; must be {' or '.join(allowed_from)}")
        completed_at = now_iso() if new_status in ("completed","rejected") else None
        await db.execute("UPDATE handoffs SET status=?, completed_at=COALESCE(?,completed_at) WHERE id=?", (new_status, completed_at, handoff_id))
        await log_event(db, h["goal_id"], event_type, actor_type="agent", actor_id=h["to_agent_id"], payload={"handoff_id": handoff_id, "note": body.note if body else None})
        await db.commit()
        cur = await db.execute("SELECT h.*,fa.handle AS from_handle,ta.handle AS to_handle FROM handoffs h JOIN agents fa ON fa.id=h.from_agent_id JOIN agents ta ON ta.id=h.to_agent_id WHERE h.id=?", (handoff_id,))
        return dict(await cur.fetchone())
    finally: await db.close()

@app.post("/api/v1/handoffs/{handoff_id}/accept")
async def accept_handoff(handoff_id: str, body: Optional[HandoffNote]=None, _auth=Depends(require_auth)):
    return await _transition_handoff(handoff_id, ("pending",), "accepted", "handoff.accepted", body)
@app.post("/api/v1/handoffs/{handoff_id}/complete")
async def complete_handoff(handoff_id: str, body: Optional[HandoffNote]=None, _auth=Depends(require_auth)):
    return await _transition_handoff(handoff_id, ("accepted",), "completed", "handoff.completed", body)
@app.post("/api/v1/handoffs/{handoff_id}/reject")
async def reject_handoff(handoff_id: str, body: Optional[HandoffNote]=None, _auth=Depends(require_auth)):
    return await _transition_handoff(handoff_id, ("pending",), "rejected", "handoff.rejected", body)

@app.get("/api/v1/goals/{goal_id}/events")
async def list_goal_events(goal_id: str, limit: int=Query(50, le=200), _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM goal_events WHERE goal_id=? ORDER BY created_at DESC LIMIT ?", (goal_id, limit))
        result = []
        for r in await cur.fetchall():
            d = dict(r)
            try: d["payload"] = json.loads(d.get("payload") or "{}")
            except Exception: d["payload"] = {}
            result.append(d)
        return result
    finally: await db.close()

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, _auth=Depends(require_auth)):
    thread_id = req.thread_id or f"thread-{uuid.uuid4().hex[:8]}"; message_id = f"msg-{uuid.uuid4().hex[:8]}"
    model = req.model or DEFAULT_MODEL; now = now_iso()
    system_prompt = req.system_prompt or "You are a helpful, concise personal AI agent on the user's phone. Be clear, practical, and respectful."
    db = await get_db()
    try:
        if not await (await db.execute("SELECT id FROM threads WHERE id=?", (thread_id,))).fetchone():
            title = req.message[:40] + ("…" if len(req.message) > 40 else "")
            await db.execute("INSERT INTO threads (id,title,system_prompt,created_at,updated_at) VALUES (?,?,?,?,?)", (thread_id, title, system_prompt, now, now))
        else:
            await db.execute("UPDATE threads SET updated_at=? WHERE id=?", (now, thread_id))
        await db.execute("INSERT INTO messages (id,thread_id,role,content,created_at) VALUES (?,?,?,?,?)", (f"msg-{uuid.uuid4().hex[:8]}", thread_id, "user", req.message, now))
        cur = await db.execute("SELECT role,content FROM messages WHERE thread_id=? ORDER BY created_at ASC", (thread_id,))
        messages = [{"role": "system", "content": system_prompt}]
        for r in await cur.fetchall(): messages.append({"role": r["role"], "content": r["content"]})
        reply = await call_model(messages, model)
        await db.execute("INSERT INTO messages (id,thread_id,role,content,created_at) VALUES (?,?,?,?,?)", (message_id, thread_id, "assistant", reply, now_iso()))
        await db.commit()
    finally: await db.close()
    return ChatResponse(thread_id=thread_id, reply=reply, message_id=message_id, model=model)

@app.get("/api/v1/threads/{thread_id}/messages")
async def get_messages(thread_id: str, _auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id,role,content,created_at FROM messages WHERE thread_id=? ORDER BY created_at ASC", (thread_id,))
        return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()

@app.get("/api/v1/threads")
async def list_threads(_auth=Depends(require_auth)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT id,title,created_at,updated_at FROM threads ORDER BY updated_at DESC")
        return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()
