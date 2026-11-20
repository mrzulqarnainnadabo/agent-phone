"""Regression coverage for persistent personal workspace records."""
from fastapi.testclient import TestClient
import pytest

from app import core_helpers
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(core_helpers, "DB_PATH", tmp_path / "workspace-test.sqlite3")
    monkeypatch.setattr(core_helpers, "APP_AUTH_TOKEN", "test-token")
    with TestClient(app) as test_client:
        yield test_client


def headers():
    return {"Authorization": "Bearer test-token"}


def test_workspace_projects_tasks_and_checkpoints_persist(client):
    project_response = client.post(
        "/api/v1/workspace/projects",
        headers=headers(),
        json={
            "name": "Personal Operations",
            "description": "Build a dependable personal workspace",
            "repository_url": "https://github.com/example/project",
        },
    )
    assert project_response.status_code == 200
    project = project_response.json()
    assert project["status"] == "active"

    task_response = client.post(
        "/api/v1/workspace/tasks",
        headers=headers(),
        json={
            "project_id": project["id"],
            "title": "Implement persistent checkpoints",
            "priority": "high",
            "status": "in_progress",
        },
    )
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["project_id"] == project["id"]

    checkpoint_response = client.post(
        "/api/v1/workspace/checkpoints",
        headers=headers(),
        json={
            "project_id": project["id"],
            "task_id": task["id"],
            "summary": "Workspace API foundation added",
            "completed_work": "Project, task, and checkpoint persistence",
            "next_action": "Add mobile workspace interface",
            "evidence_urls": ["https://github.com/example/project"],
        },
    )
    assert checkpoint_response.status_code == 200
    checkpoint = checkpoint_response.json()
    assert checkpoint["next_action"] == "Add mobile workspace interface"

    detail = client.get(f"/api/v1/workspace/projects/{project['id']}", headers=headers())
    assert detail.status_code == 200
    assert detail.json()["tasks"][0]["id"] == task["id"]
    assert detail.json()["checkpoints"][0]["id"] == checkpoint["id"]


def test_workspace_rejects_unknown_project_for_task(client):
    response = client.post(
        "/api/v1/workspace/tasks",
        headers=headers(),
        json={"title": "Invalid task", "project_id": "missing-project"},
    )
    assert response.status_code == 404


def test_workspace_checkpoint_requires_project_or_task(client):
    response = client.post(
        "/api/v1/workspace/checkpoints",
        headers=headers(),
        json={"summary": "Unattached checkpoint"},
    )
    assert response.status_code == 400


def test_workspace_settings_have_safe_defaults_and_are_editable(client):
    response = client.get("/api/v1/workspace/settings", headers=headers())
    assert response.status_code == 200
    assert response.json()["autonomy_mode"]["value"] == "hybrid"

    updated = client.put(
        "/api/v1/workspace/settings/autonomy_mode",
        headers=headers(),
        json={"value": "hybrid"},
    )
    assert updated.status_code == 200
    assert updated.json()["value"] == "hybrid"

    forbidden = client.put(
        "/api/v1/workspace/settings/model_api_key",
        headers=headers(),
        json={"value": "should-not-be-stored"},
    )
    assert forbidden.status_code == 400


def test_workspace_overview_returns_real_counts(client):
    response = client.get("/api/v1/workspace/overview", headers=headers())
    assert response.status_code == 200
    assert response.json()["active_projects"] == 0
    assert response.json()["tasks"]["todo"] == 0
