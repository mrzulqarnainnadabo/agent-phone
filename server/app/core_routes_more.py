"""Register remaining core HTTP routes (goals, handoffs, chat)."""
from __future__ import annotations

from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Query

from app.core_helpers import (
    require_auth, get_db, now_iso, log_event, call_model,
    ChatRequest, ChatResponse, GoalCreate, GoalUpdate, GoalAgentIn,
    HandoffCreate, HandoffNote, MAX_GOAL_AGENTS, DEFAULT_MODEL,
)
import uuid

def register_core_more(app: FastAPI) -> None:
    @app.post("/api/v1/goals")
    async def create_goal(body: GoalCreate, _auth=Depends(require_auth)):
        gid = f"goal-{uuid.uuid4().hex[:8]}"; now = now_iso()
        db = await get_db()
        try:
            await db.execute("INSERT INTO goals (id,title,description,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (gid, body.title, body.description or "", "active", now, now))
            await db.commit()
            return {"id": gid, "title": body.title, "status": "active", "created_at": now, "updated_at": now}
        finally:
            await db.close()

    @app.get("/api/v1/goals")
    async def list_goals(_auth=Depends(require_auth)):
        db = await get_db()
        try:
            cur = await db.execute("SELECT * FROM goals ORDER BY updated_at DESC")
            return [dict(r) for r in await cur.fetchall()]
        finally:
            await db.close()

    @app.get("/api/v1/goals/{goal_id}")
    async def get_goal(goal_id: str, _auth=Depends(require_auth)):
        db = await get_db()
        try:
            cur = await db.execute("SELECT * FROM goals WHERE id=?", (goal_id,)); row = await cur.fetchone()
            if not row: raise HTTPException(404, "Goal not found")
            goal = dict(row)
            cur = await db.execute(
                "SELECT ga.agent_id, ga.role, ga.joined_at, a.name, a.handle FROM goal_agents ga JOIN agents a ON a.id=ga.agent_id WHERE ga.goal_id=?",
                (goal_id,))
            goal["agents"] = [dict(r) for r in await cur.fetchall()]
            return goal
        finally:
            await db.close()

    @app.post("/api/v1/goals/{goal_id}/agents")
    async def add_goal_agent(goal_id: str, body: GoalAgentIn, _auth=Depends(require_auth)):
        db = await get_db()
        try:
            cur = await db.execute("SELECT COUNT(*) as c FROM goal_agents WHERE goal_id=?", (goal_id,))
            if (await cur.fetchone())["c"] >= MAX_GOAL_AGENTS:
                raise HTTPException(400, f"Max {MAX_GOAL_AGENTS} agents per goal")
            await db.execute("INSERT OR REPLACE INTO goal_agents (goal_id,agent_id,role,joined_at) VALUES (?,?,?,?)",
                (goal_id, body.agent_id, body.role or "Member", now_iso()))
            await db.commit()
            return {"ok": True}
        finally:
            await db.close()

    @app.get("/api/v1/goals/{goal_id}/handoffs")
    async def list_handoffs(goal_id: str, _auth=Depends(require_auth)):
        db = await get_db()
        try:
            cur = await db.execute("SELECT * FROM handoffs WHERE goal_id=? ORDER BY created_at DESC", (goal_id,))
            return [dict(r) for r in await cur.fetchall()]
        finally:
            await db.close()

    @app.get("/api/v1/goals/{goal_id}/events")
    async def list_events(goal_id: str, _auth=Depends(require_auth)):
        db = await get_db()
        try:
            cur = await db.execute("SELECT * FROM goal_events WHERE goal_id=? ORDER BY created_at DESC LIMIT 100", (goal_id,))
            return [dict(r) for r in await cur.fetchall()]
        finally:
            await db.close()

    @app.post("/api/v1/goals/{goal_id}/handoffs")
    async def create_handoff(goal_id: str, body: HandoffCreate, _auth=Depends(require_auth)):
        hid = f"ho-{uuid.uuid4().hex[:8]}"; now = now_iso()
        db = await get_db()
        try:
            await db.execute(
                "INSERT INTO handoffs (id,goal_id,from_agent_id,to_agent_id,title,instruction,context,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (hid, goal_id, body.from_agent_id, body.to_agent_id, body.title, body.instruction, body.context, "pending", now))
            await log_event(db, goal_id, "handoff_created", "user", None, {"handoff_id": hid})
            await db.commit()
            return {"id": hid, "status": "pending"}
        finally:
            await db.close()

    @app.post("/api/v1/handoffs/{handoff_id}/accept")
    async def accept_handoff(handoff_id: str, body: HandoffNote, _auth=Depends(require_auth)):
        db = await get_db()
        try:
            await db.execute("UPDATE handoffs SET status='accepted' WHERE id=?", (handoff_id,)); await db.commit()
            return {"ok": True, "status": "accepted"}
        finally:
            await db.close()

    @app.post("/api/v1/handoffs/{handoff_id}/complete")
    async def complete_handoff(handoff_id: str, body: HandoffNote, _auth=Depends(require_auth)):
        db = await get_db()
        try:
            await db.execute("UPDATE handoffs SET status='completed', completed_at=? WHERE id=?", (now_iso(), handoff_id)); await db.commit()
            return {"ok": True, "status": "completed"}
        finally:
            await db.close()

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
        finally:
            await db.close()
        return ChatResponse(thread_id=thread_id, reply=reply, message_id=message_id, model=model)

    @app.get("/api/v1/threads")
    async def list_threads(_auth=Depends(require_auth)):
        db = await get_db()
        try:
            cur = await db.execute("SELECT id,title,created_at,updated_at FROM threads ORDER BY updated_at DESC")
            return [dict(r) for r in await cur.fetchall()]
        finally:
            await db.close()
