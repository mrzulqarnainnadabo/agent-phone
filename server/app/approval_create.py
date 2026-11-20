"""Create pending approvals — the agent proposes, the human decides."""
from typing import Optional
import uuid, json, hashlib
from datetime import datetime, timedelta, timezone
import hmac
from fastapi import HTTPException


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    try:
        canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Action payload must contain JSON-compatible values") from exc
    if len(canonical_payload) > 12000:
        raise HTTPException(413, "Action payload is too large to approve")
    payload_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=max(60, min(ttl_seconds, 604800)))).isoformat()
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



async def consume_approved_action(db, *, approval_id: str, expected_payload_hash: str) -> dict:
    """Atomically consume one approved, unexpired action bound to the expected payload hash."""
    row = await (await db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,))).fetchone()
    if not row:
        raise HTTPException(404, "Approval not found")
    if row["status"] != "approved":
        raise HTTPException(409, "Action has not been approved")
    if row["executed_at"]:
        raise HTTPException(409, "Approval has already been consumed")
    if not row["action_payload_json"] or not row["payload_hash"] or not row["expires_at"]:
        raise HTTPException(409, "Approval is not bound to a verifiable action payload")
    if not hmac.compare_digest(row["payload_hash"], expected_payload_hash):
        raise HTTPException(409, "Approved action payload does not match the requested execution")
    try:
        payload = json.loads(row["action_payload_json"])
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        expiry = datetime.fromisoformat(row["expires_at"])
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(409, "Approved action payload is invalid") from exc
    if not hmac.compare_digest(digest, row["payload_hash"]):
        raise HTTPException(409, "Approved action payload has been altered")
    if expiry <= datetime.now(timezone.utc):
        await db.execute(
            "UPDATE approvals SET status='expired', decided_at=?, decision_note=? WHERE id=? AND status='approved' AND executed_at IS NULL",
            (now_iso(), "Approval expired before execution.", approval_id),
        )
        await db.commit()
        raise HTTPException(409, "Approval has expired")
    cur = await db.execute(
        "UPDATE approvals SET executed_at=? WHERE id=? AND status='approved' AND executed_at IS NULL AND payload_hash=?",
        (now_iso(), approval_id, expected_payload_hash),
    )
    if cur.rowcount != 1:
        await db.rollback()
        raise HTTPException(409, "Approval was already consumed")
    await db.commit()
    return payload


async def record_approval_execution_result(db, *, approval_id: str, result: dict) -> None:
    """Persist the outcome of an already-consumed action without changing its approval decision."""
    await db.execute(
        "UPDATE approvals SET execution_result_json=? WHERE id=? AND executed_at IS NOT NULL",
        (json.dumps(result, ensure_ascii=False)[:12000], approval_id),
    )
    await db.commit()
