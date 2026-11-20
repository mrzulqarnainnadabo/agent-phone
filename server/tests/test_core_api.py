"""Regression tests for Agent Phone's core API and approval state machine."""
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from app import core_helpers
from app.core_routes import register_core
from app.core_routes_more import register_core_more
from app.auth import router as auth_router
from app.approval_create import consume_approved_action
import app.auth as auth_module


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(core_helpers, "DB_PATH", tmp_path / "agent-phone-test.sqlite3")
    monkeypatch.setattr(core_helpers, "APP_LOGIN_PASSWORD", "test-owner-password")
    monkeypatch.setattr(core_helpers, "SESSION_SECRET", "test-session-secret-at-least-32-characters")
    monkeypatch.setattr(auth_module, "APP_LOGIN_PASSWORD", "test-owner-password")
    monkeypatch.setattr(auth_module, "SESSION_SECRET", "test-session-secret-at-least-32-characters")
    app = FastAPI()
    register_core(app)
    register_core_more(app)
    app.include_router(auth_router)
    with TestClient(app) as test_client:
        yield test_client


def auth():
    return {"Authorization": f"Bearer {core_helpers.create_session_token()}"}


def test_protected_agent_route_requires_auth(client):
    response = client.get("/api/v1/agents")
    assert response.status_code == 401


def test_agent_can_be_created_and_listed(client):
    created = client.post(
        "/api/v1/agents",
        headers=auth(),
        json={"name": "Researcher", "handle": "researcher", "purpose": "Research projects"},
    )
    assert created.status_code == 200
    assert created.json()["handle"] == "researcher"

    listed = client.get("/api/v1/agents", headers=auth())
    assert listed.status_code == 200
    assert any(agent["id"] == created.json()["id"] for agent in listed.json())


def test_unknown_approval_cannot_be_approved_or_rejected(client):
    payload = {"note": "test"}
    assert client.post("/api/v1/approvals/missing/approve", headers=auth(), json=payload).status_code == 404
    assert client.post("/api/v1/approvals/missing/reject", headers=auth(), json=payload).status_code == 404


def test_approval_decision_is_single_use(client):
    created = client.post("/api/v1/approvals/demo", headers=auth())
    assert created.status_code == 200
    approval_id = created.json()["id"]

    approved = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers=auth(),
        json={"note": "Reviewed and approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["execution_status"] == "not_executed"

    replay = client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        headers=auth(),
        json={"note": "Attempted second decision"},
    )
    assert replay.status_code == 409


def test_authentication_fails_closed_when_token_is_unconfigured(client, monkeypatch):
    monkeypatch.setattr(core_helpers, "SESSION_SECRET", "")
    response = client.get("/api/v1/agents", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Session authentication is not configured securely"


def test_chat_reports_missing_model_configuration_as_service_unavailable(client):
    response = client.post(
        "/api/v1/chat",
        headers=auth(),
        json={"message": "Hello", "system_prompt": "client-controlled prompt", "model": "arbitrary-model"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "AI model provider is not configured"


def test_chat_rejects_empty_and_oversized_messages(client):
    empty = client.post("/api/v1/chat", headers=auth(), json={"message": ""})
    oversized = client.post("/api/v1/chat", headers=auth(), json={"message": "x" * 12001})
    assert empty.status_code == 422
    assert oversized.status_code == 422


@pytest.mark.parametrize("placeholder", ["change-me", "change-me-to-a-long-random-string"])
def test_auth_rejects_known_placeholder_session_secrets(client, monkeypatch, placeholder):
    monkeypatch.setattr(core_helpers, "SESSION_SECRET", placeholder)
    response = client.get("/api/v1/agents", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 503


def test_owner_login_issues_a_valid_short_lived_session(client):
    denied = client.post("/api/v1/auth/login", json={"password": "wrong-password"})
    assert denied.status_code == 401

    accepted = client.post("/api/v1/auth/login", json={"password": "test-owner-password"})
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["token_type"] == "Bearer"
    assert payload["expires_in"] > 0

    response = client.get(
        "/api/v1/agents",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert response.status_code == 200

    session_headers = {"Authorization": f"Bearer {payload['access_token']}"}
    signed_out = client.post("/api/v1/auth/logout", headers=session_headers)
    assert signed_out.status_code == 200
    reused = client.get("/api/v1/agents", headers=session_headers)
    assert reused.status_code == 401


def test_invalid_session_token_is_rejected(client):
    response = client.get("/api/v1/agents", headers={"Authorization": "Bearer not.a.valid.signature"})
    assert response.status_code == 401



def test_approval_payload_tampering_cancels_proposal(client):
    approval = client.post("/api/v1/approvals/demo", headers=auth()).json()

    async def tamper():
        db = await core_helpers.get_db()
        try:
            await db.execute(
                "UPDATE approvals SET action_payload_json=? WHERE id=?",
                ('{"body":"changed after approval request"}', approval["id"]),
            )
            await db.commit()
        finally:
            await db.close()

    asyncio.run(tamper())
    response = client.post(
        f"/api/v1/approvals/{approval['id']}/approve",
        headers=auth(),
        json={"note": "Approve"},
    )
    assert response.status_code == 409

    cancelled = client.get("/api/v1/approvals?status=cancelled", headers=auth())
    assert any(item["id"] == approval["id"] for item in cancelled.json())


def test_expired_approval_cannot_be_approved(client):
    approval = client.post("/api/v1/approvals/demo", headers=auth()).json()

    async def expire():
        db = await core_helpers.get_db()
        try:
            await db.execute(
                "UPDATE approvals SET expires_at=? WHERE id=?",
                ("2000-01-01T00:00:00", approval["id"]),
            )
            await db.commit()
        finally:
            await db.close()

    asyncio.run(expire())
    response = client.post(
        f"/api/v1/approvals/{approval['id']}/approve",
        headers=auth(),
        json={"note": "Too late"},
    )
    assert response.status_code == 409
    expired = client.get("/api/v1/approvals?status=expired", headers=auth())
    assert any(item["id"] == approval["id"] for item in expired.json())


def test_approved_action_can_only_be_consumed_once(client):
    approval = client.post("/api/v1/approvals/demo", headers=auth()).json()
    decided = client.post(
        f"/api/v1/approvals/{approval['id']}/approve",
        headers=auth(),
        json={"note": "Approved"},
    )
    assert decided.status_code == 200

    async def consume():
        db = await core_helpers.get_db()
        try:
            return await consume_approved_action(
                db, approval_id=approval["id"], expected_payload_hash=approval["payload_hash"]
            )
        finally:
            await db.close()

    async def consume_wrong_hash():
        db = await core_helpers.get_db()
        try:
            return await consume_approved_action(
                db, approval_id=approval["id"], expected_payload_hash="0" * 64
            )
        finally:
            await db.close()

    with pytest.raises(HTTPException) as wrong_hash:
        asyncio.run(consume_wrong_hash())
    assert wrong_hash.value.status_code == 409

    payload = asyncio.run(consume())
    assert payload["channel"] == "email"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(consume())
    assert exc.value.status_code == 409


def test_create_approval_endpoint_stores_bound_action_payload(client):
    agent = client.get("/api/v1/agents", headers=auth()).json()[0]
    response = client.post(
        "/api/v1/approvals",
        headers=auth(),
        json={
            "agent_id": agent["id"],
            "title": "Create a pull request",
            "description": "Prepare a proposed code change",
            "action_type": "github.create_pull_request",
            "action_level": "consequential",
            "action_payload": {"repository": "mrzulqarnainnadabo/agent-phone", "base": "main", "head": "feature"},
        },
    )
    assert response.status_code == 200
    assert response.json()["payload_hash"]
    assert response.json()["action_payload_json"]
    assert response.json()["expires_at"]
