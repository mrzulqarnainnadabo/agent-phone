from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os, uuid, json, aiosqlite, httpx
from datetime import datetime
from pathlib import Path

app = FastAPI(title="Agent Phone API", description="Phone-first control room for trusted AI workers", version="0.7.0")
# Browsers reject allow_origins=["*"] combined with allow_credentials=True.
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
