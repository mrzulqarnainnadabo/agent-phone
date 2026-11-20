"""Create pending approvals — the agent proposes, the human decides."""
from typing import Optional
import uuid, json, hashlib
from datetime import datetime, timedelta


def now_iso() -> str:
    return datetime.utcnow().isoformat()


async def create_pending_approval(
    db,
    *,
    agent_id: str,
    title: str,
    description: str,
    action_type: str = "messaging.draft",
    action_level: str = "consequential",
    proposed_output: Optional[str] = None,
    proposed_input: Optional[str] = None,
    reason: Optional[str] = None,
    goal_id: Optional[str] = None,
    action_payload: Optional[dict] = None,
    ttl_seconds: int = 86400,
) -> dict:
    """Insert a pending approval and return the row as a dict."""
    approval_id = f"apr-{uuid.uuid4().hex[:10]}"
    created_at = now_iso()
    payload = action_payload if action_payload is not None else {
        "goal_id": goal_id,
        "action_type": action_type,
        "action_level": action_level,
        "title": title,
        "description": description,
        "proposed_input": proposed_input,
        "proposed_output": proposed_output,
        "reason": reason,
    }
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(seconds=max(60, min(ttl_seconds, 604800)))).isoformat()
    await db.execute(
        """INSERT INTO approvals
           (id, agent_id, goal_id, action_type, action_level, title, description,
            proposed_input, proposed_output, reason, status, created_at,
            action_payload_json, payload_hash, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (
            approval_id, agent_id, goal_id, action_type, action_level, title, description,
            proposed_input, proposed_output, reason, created_at, canonical_payload, payload_hash, expires_at,
        ),
    )
    cur = await db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    row = await cur.fetchone()
    return dict(row) if row else {"id": approval_id, "status": "pending"}
