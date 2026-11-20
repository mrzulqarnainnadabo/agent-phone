"""Tests for allowlisted, read-only GitHub inspection routes."""
import base64

from fastapi.testclient import TestClient
import pytest

from app import core_helpers
from app.main import app
import app.auth as auth_module
import app.github_tools as github_tools


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(core_helpers, "DB_PATH", tmp_path / "github-tools-test.sqlite3")
    monkeypatch.setattr(core_helpers, "APP_LOGIN_PASSWORD", "test-owner-password")
    monkeypatch.setattr(core_helpers, "SESSION_SECRET", "test-session-secret-at-least-32-characters")
    monkeypatch.setattr(auth_module, "APP_LOGIN_PASSWORD", "test-owner-password")
    monkeypatch.setattr(auth_module, "SESSION_SECRET", "test-session-secret-at-least-32-characters")
    with TestClient(app) as test_client:
        yield test_client


def headers():
    return {"Authorization": f"Bearer {core_helpers.create_session_token()}"}


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, response, **kwargs):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, headers=None, params=None):
        assert url.startswith("https://api.github.com/repos/")
        assert headers["Authorization"] == "Bearer server-only-token"
        return self.response


def test_github_status_reports_unconfigured_without_exposing_credentials(client, monkeypatch):
    monkeypatch.setattr(github_tools, "_configuration", lambda: ("", set()))
    response = client.get("/api/v1/github/status", headers=headers())
    assert response.status_code == 200
    assert response.json() == {"configured": False, "allowed_repository_count": 0, "access": "read-only"}


def test_github_repository_requires_server_side_allowlist(client, monkeypatch):
    monkeypatch.setattr(github_tools, "_configuration", lambda: ("server-only-token", {"someone/else"}))
    response = client.get("/api/v1/github/repos/mrzulqarnainnadabo/agent-phone", headers=headers())
    assert response.status_code == 403


def test_github_repository_returns_only_selected_metadata(client, monkeypatch):
    monkeypatch.setattr(github_tools, "_configuration", lambda: ("server-only-token", {"mrzulqarnainnadabo/agent-phone"}))
    payload = {
        "name": "agent-phone", "full_name": "mrzulqarnainnadabo/agent-phone",
        "description": "Personal operations PWA", "default_branch": "main",
        "private": False, "updated_at": "2026-11-20T00:00:00Z",
        "html_url": "https://github.com/mrzulqarnainnadabo/agent-phone",
        "language": "TypeScript", "open_issues_count": 2, "secret_field": "must-not-return",
    }
    monkeypatch.setattr(github_tools.httpx, "AsyncClient", lambda **kwargs: FakeClient(FakeResponse(payload), **kwargs))
    response = client.get("/api/v1/github/repos/mrzulqarnainnadabo/agent-phone", headers=headers())
    assert response.status_code == 200
    assert response.json()["full_name"] == "mrzulqarnainnadabo/agent-phone"
    assert "secret_field" not in response.json()


def test_github_file_endpoint_decodes_text_and_enforces_allowlist(client, monkeypatch):
    monkeypatch.setattr(github_tools, "_configuration", lambda: ("server-only-token", {"mrzulqarnainnadabo/agent-phone"}))
    encoded = base64.b64encode(b"# safe text file\n").decode("ascii")
    payload = {"type": "file", "encoding": "base64", "name": "README.md", "path": "README.md", "sha": "abc", "content": encoded, "html_url": "https://github.com/example"}
    monkeypatch.setattr(github_tools.httpx, "AsyncClient", lambda **kwargs: FakeClient(FakeResponse(payload), **kwargs))
    response = client.get("/api/v1/github/repos/mrzulqarnainnadabo/agent-phone/file?path=README.md", headers=headers())
    assert response.status_code == 200
    assert response.json()["content"] == "# safe text file\n"


def test_github_tool_endpoints_are_read_only_and_require_auth(client):
    response = client.get("/api/v1/github/status")
    assert response.status_code == 401
