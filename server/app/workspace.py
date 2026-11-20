"""Personal workspace API: projects, actionable tasks, checkpoints, decisions, and settings."""
from __future__ import annotations

import json
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core_helpers import get_db, now_iso, require_auth

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


async def ensure_workspace_tables(db):
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS workspace_projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','completed','archived')),
            priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('low','normal','high','urgent')),
            repository_url TEXT, production_url TEXT, documentation_url TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workspace_tasks (
            id TEXT PRIMARY KEY, project_id TEXT, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo','in_progress','blocked','done','cancelled')),
            priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('low','normal','high','urgent')),
            due_date TEXT, assigned_agent_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(project_id) REFERENCES workspace_projects(id) ON DELETE SET NULL,
            FOREIGN KEY(assigned_agent_id) REFERENCES agents(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS workspace_checkpoints (
            id TEXT PRIMARY KEY, project_id TEXT, task_id TEXT, summary TEXT NOT NULL,
            completed_work TEXT NOT NULL DEFAULT '', next_action TEXT NOT NULL DEFAULT '',
            blockers TEXT NOT NULL DEFAULT '', evidence_urls TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES workspace_projects(id) ON DELETE SET NULL,
            FOREIGN KEY(task_id) REFERENCES workspace_tasks(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS workspace_decisions (
            id TEXT PRIMARY KEY, project_id TEXT, title TEXT NOT NULL, decision TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES workspace_projects(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS workspace_settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_workspace_projects_status ON workspace_projects(status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_workspace_tasks_project_status ON workspace_tasks(project_id, status, priority);
        CREATE INDEX IF NOT EXISTS idx_workspace_tasks_due ON workspace_tasks(due_date);
        CREATE INDEX IF NOT EXISTS idx_workspace_checkpoints_project_created ON workspace_checkpoints(project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_workspace_decisions_project_created ON workspace_decisions(project_id, created_at DESC);
        """
    )
    now = now_iso()
    defaults = {
        "autonomy_mode": "hybrid",
        "primary_responsibility": "productivity_and_project_execution",
        "infrastructure_preference": "keep_existing",
        "operating_charter": (
            "Execution over unnecessary explanations. Evidence over assumptions. "
            "Quality over quantity. Reuse existing infrastructure and minimise recurring costs. "
            "Preserve approved decisions. Never claim completion without verification. "
            "Resume from the last verified checkpoint. Ask before consequential actions."
        ),
    }
    for key, value in defaults.items():
        await db.execute(
            "INSERT OR IGNORE INTO workspace_settings (key, value, updated_at) VALUES (?,?,?)",
            (key, value, now),
        )
    await db.commit()


async def workspace_db():
    db = await get_db()
    try:
        await ensure_workspace_tables(db)
        yield db
    finally:
        await db.close()
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str = Field(default="", max_length=4000)
    status: Literal["active", "paused", "completed", "archived"] = "active"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    repository_url: Optional[str] = None
    production_url: Optional[str] = None
    documentation_url: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=4000)
    status: Optional[Literal["active", "paused", "completed", "archived"]] = None
    priority: Optional[Literal["low", "normal", "high", "urgent"]] = None
    repository_url: Optional[str] = None
    production_url: Optional[str] = None
    documentation_url: Optional[str] = None


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(default="", max_length=8000)
    project_id: Optional[str] = None
    status: Literal["todo", "in_progress", "blocked", "done", "cancelled"] = "todo"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    due_date: Optional[str] = None
    assigned_agent_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, max_length=8000)
    project_id: Optional[str] = None
    status: Optional[Literal["todo", "in_progress", "blocked", "done", "cancelled"]] = None
    priority: Optional[Literal["low", "normal", "high", "urgent"]] = None
    due_date: Optional[str] = None
    assigned_agent_id: Optional[str] = None


class CheckpointCreate(BaseModel):
    summary: str = Field(..., min_length=3, max_length=2000)
    completed_work: str = Field(default="", max_length=8000)
    next_action: str = Field(default="", max_length=2000)
    blockers: str = Field(default="", max_length=2000)
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    evidence_urls: list[str] = Field(default_factory=list, max_length=30)


class DecisionCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    decision: str = Field(..., min_length=2, max_length=4000)
    rationale: str = Field(default="", max_length=4000)
    project_id: Optional[str] = None


class SettingUpdate(BaseModel):
    value: str = Field(..., max_length=12000)


@router.get("/overview")
async def overview(db=Depends(workspace_db), _auth=Depends(require_auth)):
    counts = {}
    for status in ("todo", "in_progress", "blocked", "done"):
        cur = await db.execute("SELECT COUNT(*) AS count FROM workspace_tasks WHERE status=?", (status,))
        counts[status] = (await cur.fetchone())["count"]
    cur = await db.execute("SELECT COUNT(*) AS count FROM workspace_projects WHERE status='active'")
    project_count = (await cur.fetchone())["count"]
    cur = await db.execute(
        "SELECT id, title, status, priority, project_id, due_date, updated_at FROM workspace_tasks "
        "WHERE status IN ('todo','in_progress','blocked') ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, due_date IS NULL, due_date LIMIT 8"
    )
    tasks = [dict(row) for row in await cur.fetchall()]
    cur = await db.execute(
        "SELECT id, project_id, task_id, summary, next_action, blockers, created_at "
        "FROM workspace_checkpoints ORDER BY created_at DESC LIMIT 5"
    )
    checkpoints = [dict(row) for row in await cur.fetchall()]
    return {"active_projects": project_count, "tasks": counts, "priority_tasks": tasks, "recent_checkpoints": checkpoints}


@router.get("/projects")
async def list_projects(status: Optional[str] = None, db=Depends(workspace_db), _auth=Depends(require_auth)):
    if status:
        cur = await db.execute(
            "SELECT p.*, COUNT(t.id) AS task_count FROM workspace_projects p LEFT JOIN workspace_tasks t ON t.project_id=p.id WHERE p.status=? GROUP BY p.id ORDER BY p.updated_at DESC",
            (status,),
        )
    else:
        cur = await db.execute(
            "SELECT p.*, COUNT(t.id) AS task_count FROM workspace_projects p LEFT JOIN workspace_tasks t ON t.project_id=p.id GROUP BY p.id ORDER BY p.updated_at DESC"
        )
    return [dict(row) for row in await cur.fetchall()]


@router.post("/projects")
async def create_project(body: ProjectCreate, db=Depends(workspace_db), _auth=Depends(require_auth)):
    project_id = f"prj-{uuid.uuid4().hex[:10]}"
    now = now_iso()
    await db.execute(
        "INSERT INTO workspace_projects (id,name,description,status,priority,repository_url,production_url,documentation_url,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (project_id, body.name.strip(), body.description, body.status, body.priority, body.repository_url, body.production_url, body.documentation_url, now, now),
    )
    await db.commit()
    cur = await db.execute("SELECT * FROM workspace_projects WHERE id=?", (project_id,))
    return dict(await cur.fetchone())


@router.get("/projects/{project_id}")
async def get_project(project_id: str, db=Depends(workspace_db), _auth=Depends(require_auth)):
    cur = await db.execute("SELECT * FROM workspace_projects WHERE id=?", (project_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    project = dict(row)
    cur = await db.execute(
        "SELECT id,title,status,priority,due_date,assigned_agent_id,updated_at FROM workspace_tasks WHERE project_id=? ORDER BY updated_at DESC",
        (project_id,),
    )
    project["tasks"] = [dict(item) for item in await cur.fetchall()]
    cur = await db.execute(
        "SELECT id,summary,completed_work,next_action,blockers,evidence_urls,created_at FROM workspace_checkpoints WHERE project_id=? ORDER BY created_at DESC LIMIT 20",
        (project_id,),
    )
    project["checkpoints"] = [dict(item) | {"evidence_urls": json.loads(item["evidence_urls"] or "[]")} for item in await cur.fetchall()]
    cur = await db.execute(
        "SELECT id,title,decision,rationale,created_at FROM workspace_decisions WHERE project_id=? ORDER BY created_at DESC",
        (project_id,),
    )
    project["decisions"] = [dict(item) for item in await cur.fetchall()]
    return project


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate, db=Depends(workspace_db), _auth=Depends(require_auth)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "No project changes supplied")
    cur = await db.execute("SELECT id FROM workspace_projects WHERE id=?", (project_id,))
    if not await cur.fetchone():
        raise HTTPException(404, "Project not found")
    fields["updated_at"] = now_iso()
    await db.execute(
        "UPDATE workspace_projects SET " + ", ".join(f"{key}=?" for key in fields) + " WHERE id=?",
        [*fields.values(), project_id],
    )
    await db.commit()
    cur = await db.execute("SELECT * FROM workspace_projects WHERE id=?", (project_id,))
    return dict(await cur.fetchone())


@router.get("/tasks")
async def list_tasks(project_id: Optional[str] = None, status: Optional[str] = None, limit: int = Query(50, ge=1, le=100), db=Depends(workspace_db), _auth=Depends(require_auth)):
    clauses, values = [], []
    if project_id:
        clauses.append("project_id=?"); values.append(project_id)
    if status:
        clauses.append("status=?"); values.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    cur = await db.execute(
        "SELECT * FROM workspace_tasks" + where +
        " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, due_date IS NULL, due_date, updated_at DESC LIMIT ?",
        [*values, limit],
    )
    return [dict(row) for row in await cur.fetchall()]


@router.post("/tasks")
async def create_task(body: TaskCreate, db=Depends(workspace_db), _auth=Depends(require_auth)):
    if body.project_id and not await (await db.execute("SELECT id FROM workspace_projects WHERE id=?", (body.project_id,))).fetchone():
        raise HTTPException(404, "Project not found")
    if body.assigned_agent_id and not await (await db.execute("SELECT id FROM agents WHERE id=? AND status!='archived'", (body.assigned_agent_id,))).fetchone():
        raise HTTPException(404, "Agent not found")
    task_id = f"tsk-{uuid.uuid4().hex[:10]}"
    now = now_iso()
    completed_at = now if body.status == "done" else None
    await db.execute(
        "INSERT INTO workspace_tasks (id,project_id,title,description,status,priority,due_date,assigned_agent_id,created_at,updated_at,completed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (task_id, body.project_id, body.title.strip(), body.description, body.status, body.priority, body.due_date, body.assigned_agent_id, now, now, completed_at),
    )
    await db.commit()
    cur = await db.execute("SELECT * FROM workspace_tasks WHERE id=?", (task_id,))
    return dict(await cur.fetchone())


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, db=Depends(workspace_db), _auth=Depends(require_auth)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "No task changes supplied")
    cur = await db.execute("SELECT id FROM workspace_tasks WHERE id=?", (task_id,))
    if not await cur.fetchone():
        raise HTTPException(404, "Task not found")
    if fields.get("project_id") and not await (await db.execute("SELECT id FROM workspace_projects WHERE id=?", (fields["project_id"],))).fetchone():
        raise HTTPException(404, "Project not found")
    if fields.get("assigned_agent_id") and not await (await db.execute("SELECT id FROM agents WHERE id=? AND status!='archived'", (fields["assigned_agent_id"],))).fetchone():
        raise HTTPException(404, "Agent not found")
    fields["updated_at"] = now_iso()
    if fields.get("status") == "done":
        fields["completed_at"] = now_iso()
    elif fields.get("status") in {"todo", "in_progress", "blocked", "cancelled"}:
        fields["completed_at"] = None
    await db.execute(
        "UPDATE workspace_tasks SET " + ", ".join(f"{key}=?" for key in fields) + " WHERE id=?",
        [*fields.values(), task_id],
    )
    await db.commit()
    cur = await db.execute("SELECT * FROM workspace_tasks WHERE id=?", (task_id,))
    return dict(await cur.fetchone())


@router.post("/checkpoints")
async def create_checkpoint(body: CheckpointCreate, db=Depends(workspace_db), _auth=Depends(require_auth)):
    if not body.project_id and not body.task_id:
        raise HTTPException(400, "A project or task is required for a checkpoint")
    if body.project_id and not await (await db.execute("SELECT id FROM workspace_projects WHERE id=?", (body.project_id,))).fetchone():
        raise HTTPException(404, "Project not found")
    if body.task_id:
        cur = await db.execute("SELECT id, project_id FROM workspace_tasks WHERE id=?", (body.task_id,))
        task = await cur.fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        if body.project_id and task["project_id"] and body.project_id != task["project_id"]:
            raise HTTPException(400, "Checkpoint project does not match task project")
    checkpoint_id = f"chk-{uuid.uuid4().hex[:10]}"
    now = now_iso()
    await db.execute(
        "INSERT INTO workspace_checkpoints (id,project_id,task_id,summary,completed_work,next_action,blockers,evidence_urls,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (checkpoint_id, body.project_id, body.task_id, body.summary, body.completed_work, body.next_action, body.blockers, json.dumps(body.evidence_urls), now),
    )
    await db.commit()
    return {"id": checkpoint_id, "project_id": body.project_id, "task_id": body.task_id, "summary": body.summary, "completed_work": body.completed_work, "next_action": body.next_action, "blockers": body.blockers, "evidence_urls": body.evidence_urls, "created_at": now}


@router.get("/checkpoints")
async def list_checkpoints(project_id: Optional[str] = None, task_id: Optional[str] = None, limit: int = Query(30, ge=1, le=100), db=Depends(workspace_db), _auth=Depends(require_auth)):
    clauses, values = [], []
    if project_id:
        clauses.append("project_id=?"); values.append(project_id)
    if task_id:
        clauses.append("task_id=?"); values.append(task_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    cur = await db.execute("SELECT * FROM workspace_checkpoints" + where + " ORDER BY created_at DESC LIMIT ?", [*values, limit])
    return [dict(row) | {"evidence_urls": json.loads(row["evidence_urls"] or "[]")} for row in await cur.fetchall()]


@router.post("/decisions")
async def create_decision(body: DecisionCreate, db=Depends(workspace_db), _auth=Depends(require_auth)):
    if body.project_id and not await (await db.execute("SELECT id FROM workspace_projects WHERE id=?", (body.project_id,))).fetchone():
        raise HTTPException(404, "Project not found")
    decision_id = f"dec-{uuid.uuid4().hex[:10]}"
    now = now_iso()
    await db.execute(
        "INSERT INTO workspace_decisions (id,project_id,title,decision,rationale,created_at) VALUES (?,?,?,?,?,?)",
        (decision_id, body.project_id, body.title, body.decision, body.rationale, now),
    )
    await db.commit()
    return {"id": decision_id, **body.model_dump(), "created_at": now}


@router.get("/decisions")
async def list_decisions(project_id: Optional[str] = None, limit: int = Query(50, ge=1, le=100), db=Depends(workspace_db), _auth=Depends(require_auth)):
    if project_id:
        cur = await db.execute("SELECT * FROM workspace_decisions WHERE project_id=? ORDER BY created_at DESC LIMIT ?", (project_id, limit))
    else:
        cur = await db.execute("SELECT * FROM workspace_decisions ORDER BY created_at DESC LIMIT ?", (limit,))
    return [dict(row) for row in await cur.fetchall()]


@router.get("/settings")
async def get_settings(db=Depends(workspace_db), _auth=Depends(require_auth)):
    cur = await db.execute("SELECT key, value, updated_at FROM workspace_settings ORDER BY key")
    return {row["key"]: {"value": row["value"], "updated_at": row["updated_at"]} for row in await cur.fetchall()}


@router.put("/settings/{key}")
async def update_setting(key: str, body: SettingUpdate, db=Depends(workspace_db), _auth=Depends(require_auth)):
    allowed = {"autonomy_mode", "primary_responsibility", "infrastructure_preference", "operating_charter"}
    if key not in allowed:
        raise HTTPException(400, "Setting is not editable")
    await db.execute(
        "INSERT INTO workspace_settings (key,value,updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, body.value, now_iso()),
    )
    await db.commit()
    return {"key": key, "value": body.value}
