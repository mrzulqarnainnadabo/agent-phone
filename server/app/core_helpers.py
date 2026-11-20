"""Shared DB, auth, models, and model client for Agent Phone core."""
from __future__ import annotations

from typing import Optional, List, Literal
from fastapi import HTTPException, Depends, Header, Query
from pydantic import BaseModel, Field
import os, uuid, json, aiosqlite, httpx, hmac, hashlib, base64, time, binascii
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")); DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "agent_phone.db"
MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")
MODEL_API_BASE_URL = os.getenv("MODEL_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
try:
    MODEL_MAX_TOKENS = max(128, min(2048, int(os.getenv("MODEL_MAX_TOKENS", "1024"))))
except ValueError:
    MODEL_MAX_TOKENS = 1024
try:
    MODEL_DAILY_CALL_LIMIT = max(1, min(500, int(os.getenv("MODEL_DAILY_CALL_LIMIT", "60"))))
except ValueError:
    MODEL_DAILY_CALL_LIMIT = 60
APP_LOGIN_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
try:
    SESSION_TTL_SECONDS = max(300, min(86400, int(os.getenv("SESSION_TTL_SECONDS", "28800"))))
except ValueError:
    SESSION_TTL_SECONDS = 28800
MAX_GOAL_AGENTS = 3

def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _session_configured() -> bool:
    return (
        len(APP_LOGIN_PASSWORD) >= 12
        and len(SESSION_SECRET) >= 32
        and APP_LOGIN_PASSWORD not in {"change-me", "change-me-to-a-long-random-string"}
        and SESSION_SECRET not in {"change-me", "change-me-to-a-long-random-string"}
    )


def create_session_token() -> str:
    if not _session_configured():
        raise HTTPException(503, "Session authentication is not configured securely")
    now = int(time.time())
    payload = _b64url_encode(json.dumps(
        {"sub": "owner", "jti": uuid.uuid4().hex, "iat": now, "exp": now + SESSION_TTL_SECONDS},
        separators=(",", ":"),
    ).encode("utf-8"))
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return payload + "." + _b64url_encode(signature)


def decode_session_payload(token: str) -> Optional[dict]:
    if not _session_configured() or "." not in token:
        return None
    payload, supplied_signature = token.split(".", 1)
    expected = _b64url_encode(hmac.new(
        SESSION_SECRET.encode("utf-8"), payload.encode("ascii"), hashlib.sha256
    ).digest())
    if not hmac.compare_digest(supplied_signature, expected):
        return None
    try:
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if data.get("sub") != "owner" or int(data.get("exp", 0)) <= int(time.time()):
            return None
        return data
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error):
        return None


def verify_session_token(token: str) -> bool:
    return decode_session_payload(token) is not None


async def require_auth(authorization: Optional[str] = Header(None)):
    if not _session_configured():
        raise HTTPException(503, "Session authentication is not configured securely")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if not verify_session_token(token):
        raise HTTPException(401, "Session is invalid or expired")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    db = await get_db()
    try:
        revoked = await (await db.execute(
            "SELECT token_hash FROM revoked_sessions WHERE token_hash=?",
            (token_hash,),
        )).fetchone()
    finally:
        await db.close()
    if revoked:
        raise HTTPException(401, "Session has been signed out")
    return True


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db

def now_iso(): return datetime.now(timezone.utc).isoformat()

async def log_event(db, goal_id, event_type, actor_type="system", actor_id=None, payload=None):
    await db.execute("INSERT INTO goal_events (id, goal_id, actor_type, actor_id, event_type, payload, created_at) VALUES (?,?,?,?,?,?,?)",
        (f"evt-{uuid.uuid4().hex[:10]}", goal_id, actor_type, actor_id, event_type, json.dumps(payload or {}), now_iso()))

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS threads (id TEXT PRIMARY KEY, title TEXT, system_prompt TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS revoked_sessions (token_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL, revoked_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_revoked_sessions_expiry ON revoked_sessions(expires_at);
            CREATE TABLE IF NOT EXISTS tool_audit (id TEXT PRIMARY KEY, thread_id TEXT, tool_name TEXT NOT NULL, arguments_json TEXT NOT NULL, outcome TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_tool_audit_thread_created ON tool_audit(thread_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS model_call_usage (id TEXT PRIMARY KEY, thread_id TEXT, model TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_model_call_usage_created ON model_call_usage(created_at DESC);
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
        approval_columns = await (await db.execute("PRAGMA table_info(approvals)")).fetchall()
        existing_columns = {row["name"] for row in approval_columns}
        for column, column_type in (
            ("action_payload_json", "TEXT"),
            ("payload_hash", "TEXT"),
            ("expires_at", "TEXT"),
            ("executed_at", "TEXT"),
            ("execution_result_json", "TEXT"),
        ):
            if column not in existing_columns:
                await db.execute(f"ALTER TABLE approvals ADD COLUMN {column} {column_type}")

        legacy_cur = await db.execute(
            "SELECT id, goal_id, action_type, action_level, title, description, proposed_input, proposed_output, reason, status "
            "FROM approvals WHERE payload_hash IS NULL"
        )
        for row in await legacy_cur.fetchall():
            payload = {
                "goal_id": row["goal_id"],
                "action_type": row["action_type"],
                "action_level": row["action_level"],
                "title": row["title"],
                "description": row["description"],
                "proposed_input": row["proposed_input"],
                "proposed_output": row["proposed_output"],
                "reason": row["reason"],
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            migration_time = datetime.now(timezone.utc).isoformat()
            if row["status"] == "pending":
                await db.execute(
                    "UPDATE approvals SET action_payload_json=?, payload_hash=?, expires_at=?, status='expired', decided_at=?, decision_note=? WHERE id=?",
                    (canonical, digest, migration_time, migration_time,
                     "Expired during secure approval migration; create a new proposal.", row["id"]),
                )
            else:
                await db.execute(
                    "UPDATE approvals SET action_payload_json=?, payload_hash=?, expires_at=? WHERE id=?",
                    (canonical, digest, migration_time, row["id"]),
                )
        await db.commit()
        cur = await db.execute("SELECT COUNT(*) as c FROM agents")
        if (await cur.fetchone())["c"] == 0:
            aid = f"agent-{uuid.uuid4().hex[:8]}"; now = datetime.now(timezone.utc).isoformat()
            await db.execute("INSERT INTO agents (id,name,handle,purpose,personality,system_instructions,status,approval_mode,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (aid,"Atlas","atlas","Research and organize project information","Concise, analytical, practical","You are Atlas, a research agent.","active","ask_consequential",now,now))
            await db.execute("INSERT INTO approval_policies (id,agent_id,default_action,consequential_action,external_communication,destructive_action,financial_action) VALUES (?,?,?,?,?,?,?)",
                (f"pol-{uuid.uuid4().hex[:8]}",aid,"allow","ask","ask","deny","deny"))
            for cap,lvl in [("files","read"),("calendar","draft"),("messaging","draft")]:
                await db.execute("INSERT INTO agent_permissions (id,agent_id,capability,level) VALUES (?,?,?,?)",(f"perm-{uuid.uuid4().hex[:8]}",aid,cap,lvl))
            await db.commit()

class ChatRequest(BaseModel):
    thread_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=12000)
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
    agent_id: str
    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(..., min_length=2, max_length=4000)
    action_type: str = Field(default="messaging.draft", min_length=2, max_length=100)
    action_level: Literal["read", "draft", "consequential"] = "consequential"
    proposed_output: Optional[str] = Field(default=None, max_length=12000)
    proposed_input: Optional[str] = Field(default=None, max_length=8000)
    reason: Optional[str] = Field(default=None, max_length=2000)
    goal_id: Optional[str] = None
    action_payload: Optional[dict] = None
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

async def reserve_model_call(db, thread_id: str, model: str) -> str:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    cur = await db.execute("SELECT COUNT(*) AS count FROM model_call_usage WHERE created_at>=?", (day_start,))
    count = (await cur.fetchone())["count"]
    if count >= MODEL_DAILY_CALL_LIMIT:
        raise HTTPException(429, "Daily AI call limit reached; increase MODEL_DAILY_CALL_LIMIT deliberately or try again tomorrow")
    call_id = f"mdl-{uuid.uuid4().hex[:12]}"
    await db.execute(
        "INSERT INTO model_call_usage (id,thread_id,model,status,created_at) VALUES (?,?,?,?,?)",
        (call_id, thread_id, model, "reserved", now.isoformat()),
    )
    await db.commit()
    return call_id


async def complete_model_call(db, call_id: str, status: str) -> None:
    await db.execute("UPDATE model_call_usage SET status=? WHERE id=?", (status, call_id))
    await db.commit()


async def call_model(messages, model):
    if not MODEL_API_KEY:
        raise HTTPException(503, "AI model provider is not configured")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{MODEL_API_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {MODEL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "messages": messages, "temperature": 0.4, "max_tokens": MODEL_MAX_TOKENS},
            )
            response.raise_for_status()
            payload = response.json()
            reply = payload["choices"][0]["message"]["content"]
            if not isinstance(reply, str) or not reply.strip():
                raise HTTPException(502, "AI model returned an empty or invalid response")
            return reply.strip()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "AI model request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "AI model provider request failed") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(502, "AI model returned an invalid response") from exc



async def call_model_with_tools(messages, model, tools):
    if not MODEL_API_KEY:
        raise HTTPException(503, "AI model provider is not configured")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{MODEL_API_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {MODEL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.2,
                    "max_tokens": 1024,
                },
            )
            response.raise_for_status()
            payload = response.json()
            message = payload["choices"][0]["message"]
            if not isinstance(message, dict):
                raise HTTPException(502, "AI model returned an invalid tool response")
            if not message.get("content") and not message.get("tool_calls"):
                raise HTTPException(502, "AI model returned neither a reply nor a tool call")
            return message
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "AI model request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "AI model provider request failed") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(502, "AI model returned an invalid tool response") from exc
