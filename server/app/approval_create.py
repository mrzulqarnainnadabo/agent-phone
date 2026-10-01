"""Create pending approvals — the agent proposes, the human decides."""
from typing import Optional
import uuid
from datetime import datetime


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
) -> dict:
    """Insert a pending approval and return the row as a dict."""
    approval_id = f"apr-{uuid.uuid4().hex[:10]}"
    await db.execute(
        """INSERT INTO approvals
           (id, agent_id, goal_id, action_type, action_level, title, description,
            proposed_input, proposed_output, reason, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (
            approval_id,
            agent_id,
            goal_id,
            action_type,
            action_level,
            title,
            description,
            proposed_input,
            proposed_output,
            reason,
            now_iso(),
        ),
    )
    cur = await db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    row = await cur.fetchone()
    return dict(row) if row else {"id": approval_id, "status": "pending"}
