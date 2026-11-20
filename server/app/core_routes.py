"""Register core HTTP routes on the FastAPI app (part 1)."""
from __future__ import annotations

from typing import Optional, List
import hashlib, hmac, json
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Query

from app.core_helpers import (
    require_auth, get_db, now_iso, init_db, log_event, call_model,
    ChatRequest, ChatResponse, AgentCreate, AgentUpdate, PermissionItem, PermissionsUpdate,
    ApprovalPolicyUpdate, ApprovalDecision, ApprovalCreate, GoalCreate, GoalUpdate,
    GoalAgentIn, HandoffCreate, HandoffNote, MAX_GOAL_AGENTS,
)
import uuid
from app.approval_create import create_pending_approval

def register_core(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _startup():
        await init_db()

    @app.get("/")
    def root():
        return {"name": "Agent Phone API", "version": "0.8.0", "status": "ready", "docs": "/docs"}

    @app.get("/health")
    def health():
        return {"ok": True, "time": now_iso()}

    @app.get("/ready")
    async def ready():
        try:
            db = await get_db(); await db.execute("SELECT 1"); await db.close()
            return {"ok": True, "db": True}
        except Exception as e:
            raise HTTPException(503, str(e))

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
        finally:
            await db.close()

    @app.get("/api/v1/agents")
    async def list_agents(_auth=Depends(require_auth)):
        db = await get_db()
        try:
            cur = await db.execute("SELECT id,name,handle,purpose,personality,status,approval_mode,created_at,updated_at FROM agents WHERE status!='archived' ORDER BY updated_at DESC")
            return [dict(r) for r in await cur.fetchall()]
        finally:
            await db.close()

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
        finally:
            await db.close()

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
        finally:
            await db.close()

    @app.delete("/api/v1/agents/{agent_id}")
    async def archive_agent(agent_id: str, _auth=Depends(require_auth)):
        db = await get_db()
        try:
            await db.execute("UPDATE agents SET status='archived', updated_at=? WHERE id=?", (now_iso(), agent_id)); await db.commit()
            return {"ok": True, "status": "archived"}
        finally:
            await db.close()

    @app.get("/api/v1/approvals/count")
    async def approvals_count(_auth=Depends(require_auth)):
        db = await get_db()
        try:
            cur = await db.execute("SELECT COUNT(*) as c FROM approvals WHERE status='pending'")
            return {"pending": (await cur.fetchone())["c"]}
        finally:
            await db.close()

    @app.get("/api/v1/approvals")
    async def list_approvals(status: str=Query("pending"), agent_id: Optional[str]=None, limit: int=Query(25, le=100), _auth=Depends(require_auth)):
        db = await get_db()
        try:
            if agent_id:
                cur = await db.execute("SELECT * FROM approvals WHERE status=? AND agent_id=? ORDER BY created_at DESC LIMIT ?", (status, agent_id, limit))
            else:
                cur = await db.execute("SELECT * FROM approvals WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit))
            return [dict(r) for r in await cur.fetchall()]
        finally:
            await db.close()

    @app.post("/api/v1/approvals")
    async def create_approval(body: ApprovalCreate, _auth=Depends(require_auth)):
        db = await get_db()
        try:
            agent = await (await db.execute(
                "SELECT id FROM agents WHERE id=? AND status='active'", (body.agent_id,)
            )).fetchone()
            if not agent:
                raise HTTPException(404, "Active agent not found")
            if body.goal_id:
                goal = await (await db.execute(
                    "SELECT id FROM goals WHERE id=? AND status='active'", (body.goal_id,)
                )).fetchone()
                if not goal:
                    raise HTTPException(404, "Active goal not found")
            approval = await create_pending_approval(
                db,
                agent_id=body.agent_id,
                title=body.title,
                description=body.description,
                action_type=body.action_type,
                action_level=body.action_level,
                proposed_output=body.proposed_output,
                proposed_input=body.proposed_input,
                reason=body.reason,
                goal_id=body.goal_id,
                action_payload=body.action_payload,
            )
            await db.commit()
            return approval
        finally:
            await db.close()

    @app.post("/api/v1/approvals/demo")
    async def create_demo_approval(_auth=Depends(require_auth)):
        db = await get_db()
        try:
            cur = await db.execute("SELECT id FROM agents WHERE status='active' LIMIT 1")
            row = await cur.fetchone()
            if not row:
                raise HTTPException(400, "No active agent")
            message = "Hi Sarah,\\n\\nFollowing up on the partnership proposal.\\n\\nBest regards"
            approval = await create_pending_approval(
                db,
                agent_id=row["id"],
                action_type="messaging.send",
                action_level="consequential",
                title="Send follow-up to programme partner",
                description="Agent wants to send an external message.",
                proposed_input="Follow up on the partnership proposal.",
                proposed_output=message,
                reason="Partner follow-up after shortlist.",
                action_payload={
                    "channel": "email",
                    "recipient_name": "Sarah",
                    "recipient_address": None,
                    "subject": "Partnership proposal follow-up",
                    "body": message,
                },
            )
            await db.commit()
            return approval
        finally:
            await db.close()

    async def _decide_approval(approval_id: str, decision: str, note: Optional[str]):
        db = await get_db()
        try:
            cur = await db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(404, "Approval not found")
            if row["status"] != "pending":
                raise HTTPException(409, f"Approval is already {row['status']}")

            if decision == "approved":
                payload_json = row["action_payload_json"]
                payload_hash = row["payload_hash"]
                expires_at = row["expires_at"]
                if not payload_json or not payload_hash or not expires_at:
                    raise HTTPException(409, "Approval is not bound to a verifiable action payload")
                try:
                    payload = json.loads(payload_json)
                    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    computed_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                    expiry = datetime.fromisoformat(expires_at)
                except (ValueError, TypeError, json.JSONDecodeError):
                    raise HTTPException(409, "Approval payload or expiry is invalid")
                if not hmac.compare_digest(computed_hash, payload_hash):
                    await db.execute(
                        "UPDATE approvals SET status='cancelled', decided_at=?, decision_note=? WHERE id=? AND status='pending'",
                        (now_iso(), "Action payload integrity check failed.", approval_id),
                    )
                    await db.commit()
                    raise HTTPException(409, "Approval payload has changed; proposal was cancelled")
                if expiry <= datetime.utcnow():
                    await db.execute(
                        "UPDATE approvals SET status='expired', decided_at=?, decision_note=? WHERE id=? AND status='pending'",
                        (now_iso(), "Approval expired before decision.", approval_id),
                    )
                    await db.commit()
                    raise HTTPException(409, "Approval has expired")
                if row["executed_at"]:
                    raise HTTPException(409, "Approval has already been consumed")

            cur = await db.execute(
                "UPDATE approvals SET status=?, decided_at=?, decision_note=? WHERE id=? AND status='pending'",
                (decision, now_iso(), note or decision.capitalize(), approval_id),
            )
            if cur.rowcount != 1:
                await db.rollback()
                raise HTTPException(409, "Approval was already decided")
            await db.commit()
            result = {"ok": True, "status": decision}
            if decision == "approved":
                result["execution_status"] = "not_executed"
            return result
        finally:
            await db.close()

    @app.post("/api/v1/approvals/{approval_id}/approve")
    async def approve(approval_id: str, body: ApprovalDecision, _auth=Depends(require_auth)):
        return await _decide_approval(approval_id, "approved", body.note)

    @app.post("/api/v1/approvals/{approval_id}/reject")
    async def reject(approval_id: str, body: ApprovalDecision, _auth=Depends(require_auth)):
        return await _decide_approval(approval_id, "rejected", body.note)
