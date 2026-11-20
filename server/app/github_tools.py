"""Strictly read-only GitHub API tools for allowlisted repositories."""
from __future__ import annotations

import base64
import os
import re
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core_helpers import require_auth

router = APIRouter(prefix="/api/v1/github", tags=["github-read-only"])
OWNER_RE = re.compile(r"^[A-Za-z0-9-]{1,39}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def _configuration():
    token = os.getenv("GITHUB_TOKEN", "").strip()
    allowed = {
        item.strip().lower()
        for item in os.getenv("GITHUB_ALLOWED_REPOS", "").split(",")
        if item.strip()
    }
    return token, allowed


def _validate_repository(owner: str, repo: str):
    if not OWNER_RE.fullmatch(owner) or not REPO_RE.fullmatch(repo):
        raise HTTPException(400, "Invalid GitHub repository identifier")
    token, allowed = _configuration()
    if not token:
        raise HTTPException(503, "GitHub read-only integration is not configured")
    full_name = f"{owner}/{repo}".lower()
    if full_name not in allowed:
        raise HTTPException(403, "Repository is not on the server-side GitHub allowlist")
    return token


async def _get(owner: str, repo: str, endpoint: str, params: Optional[dict] = None):
    token = _validate_repository(owner, repo)
    url = f"https://api.github.com/repos/{owner}/{repo}/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            response = await client.get(url, headers=headers, params=params or {})
        if response.status_code == 404:
            raise HTTPException(404, "GitHub resource not found")
        if response.status_code == 403:
            if response.headers.get("X-RateLimit-Remaining") == "0":
                raise HTTPException(429, "GitHub API rate limit reached")
            raise HTTPException(403, "GitHub denied access to this resource")
        response.raise_for_status()
        return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "GitHub request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "GitHub request failed") from exc
    except ValueError as exc:
        raise HTTPException(502, "GitHub returned an invalid response") from exc


def tool_definitions():
    """OpenAI-compatible function schemas; every function is read-only."""
    return [
        {"type": "function", "function": {
            "name": "github_get_repository",
            "description": "Read metadata for an allowlisted GitHub repository.",
            "parameters": {"type": "object", "properties": {
                "owner": {"type": "string"}, "repo": {"type": "string"}
            }, "required": ["owner", "repo"], "additionalProperties": False},
        }},
        {"type": "function", "function": {
            "name": "github_list_pull_requests",
            "description": "List recent pull requests for an allowlisted GitHub repository.",
            "parameters": {"type": "object", "properties": {
                "owner": {"type": "string"}, "repo": {"type": "string"},
                "state": {"type": "string", "enum": ["open", "closed", "all"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            }, "required": ["owner", "repo"], "additionalProperties": False},
        }},
        {"type": "function", "function": {
            "name": "github_list_workflow_runs",
            "description": "Read recent GitHub Actions workflow runs for an allowlisted repository.",
            "parameters": {"type": "object", "properties": {
                "owner": {"type": "string"}, "repo": {"type": "string"},
                "branch": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            }, "required": ["owner", "repo"], "additionalProperties": False},
        }},
        {"type": "function", "function": {
            "name": "github_get_repository_tree",
            "description": "Read the file tree for an allowlisted repository and ref.",
            "parameters": {"type": "object", "properties": {
                "owner": {"type": "string"}, "repo": {"type": "string"}, "ref": {"type": "string"},
            }, "required": ["owner", "repo"], "additionalProperties": False},
        }},
        {"type": "function", "function": {
            "name": "github_get_repository_file",
            "description": "Read a UTF-8 text file from an allowlisted repository.",
            "parameters": {"type": "object", "properties": {
                "owner": {"type": "string"}, "repo": {"type": "string"},
                "path": {"type": "string"}, "ref": {"type": "string"},
            }, "required": ["owner", "repo", "path"], "additionalProperties": False},
        }},
    ]


async def execute_readonly_tool(name: str, arguments: dict):
    """Validate and execute only the five registered read-only GitHub tools."""
    if not isinstance(arguments, dict):
        raise HTTPException(400, "Tool arguments must be an object")
    owner, repo = arguments.get("owner"), arguments.get("repo")
    if not isinstance(owner, str) or not isinstance(repo, str):
        raise HTTPException(400, "GitHub tool requires owner and repo")
    allowed_fields = {
        "github_get_repository": {"owner", "repo"},
        "github_list_pull_requests": {"owner", "repo", "state", "limit"},
        "github_list_workflow_runs": {"owner", "repo", "branch", "limit"},
        "github_get_repository_tree": {"owner", "repo", "ref"},
        "github_get_repository_file": {"owner", "repo", "path", "ref"},
    }
    if name not in allowed_fields or set(arguments) - allowed_fields[name]:
        raise HTTPException(400, "Tool is not registered or contains unsupported arguments")
    if name == "github_get_repository":
        data = await _get(owner, repo, "")
        return {key: data.get(key) for key in (
            "name", "full_name", "description", "default_branch", "private",
            "updated_at", "html_url", "language", "open_issues_count",
        )}
    if name == "github_list_pull_requests":
        state = arguments.get("state", "open")
        limit = arguments.get("limit", 10)
        if state not in {"open", "closed", "all"} or type(limit) is not int or not 1 <= limit <= 20:
            raise HTTPException(400, "Invalid pull request tool arguments")
        data = await _get(owner, repo, "pulls", {"state": state, "per_page": limit, "sort": "updated", "direction": "desc"})
        return [{"number": item.get("number"), "title": item.get("title"), "state": item.get("state"),
                 "draft": item.get("draft"), "html_url": item.get("html_url"),
                 "updated_at": item.get("updated_at"), "head": (item.get("head") or {}).get("ref"),
                 "base": (item.get("base") or {}).get("ref")} for item in data]
    if name == "github_list_workflow_runs":
        limit = arguments.get("limit", 10)
        branch = arguments.get("branch")
        if type(limit) is not int or not 1 <= limit <= 20 or (branch is not None and (not isinstance(branch, str) or len(branch) > 120)):
            raise HTTPException(400, "Invalid workflow run tool arguments")
        params = {"per_page": limit}
        if branch:
            params["branch"] = branch
        data = await _get(owner, repo, "actions/runs", params)
        return [{"id": item.get("id"), "name": item.get("name"), "display_title": item.get("display_title"),
                 "status": item.get("status"), "conclusion": item.get("conclusion"),
                 "head_branch": item.get("head_branch"), "html_url": item.get("html_url"),
                 "created_at": item.get("created_at")} for item in data.get("workflow_runs", [])]
    if name == "github_get_repository_tree":
        ref = arguments.get("ref", "main")
        if not isinstance(ref, str) or not ref or len(ref) > 120 or ".." in ref:
            raise HTTPException(400, "Invalid Git reference")
        data = await _get(owner, repo, f"git/trees/{quote(ref, safe='')}", {"recursive": "1"})
        return {"sha": data.get("sha"), "truncated": data.get("truncated", False),
                "entries": [{"path": item.get("path"), "type": item.get("type"), "size": item.get("size")}
                            for item in data.get("tree", [])[:1000]]}
    if name == "github_get_repository_file":
        path, ref = arguments.get("path"), arguments.get("ref", "main")
        if not isinstance(path, str) or not path or len(path) > 500 or path.startswith("/") or ".." in path.split("/"):
            raise HTTPException(400, "Invalid repository file path")
        if not isinstance(ref, str) or not ref or ".." in ref:
            raise HTTPException(400, "Invalid Git reference")
        data = await _get(owner, repo, f"contents/{quote(path, safe='/')}", {"ref": ref})
        if data.get("type") != "file" or data.get("encoding") != "base64":
            raise HTTPException(400, "Requested GitHub resource is not a text file")
        try:
            raw = base64.b64decode(data.get("content", ""), validate=False)
            if len(raw) > 100_000:
                raise HTTPException(413, "File is too large for model context")
            return {"path": data.get("path"), "sha": data.get("sha"), "content": raw.decode("utf-8")}
        except UnicodeDecodeError as exc:
            raise HTTPException(415, "File is not UTF-8 text") from exc
    raise HTTPException(400, "Tool is not registered or is not read-only")


@router.get("/status")
async def github_status(_auth=Depends(require_auth)):
    token, allowed = _configuration()
    return {
        "configured": bool(token and allowed),
        "allowed_repository_count": len(allowed),
        "access": "read-only",
    }


@router.get("/repos/{owner}/{repo}")
async def repository(owner: str, repo: str, _auth=Depends(require_auth)):
    data = await _get(owner, repo, "")
    return {
        "name": data.get("name"),
        "full_name": data.get("full_name"),
        "description": data.get("description"),
        "default_branch": data.get("default_branch"),
        "private": data.get("private"),
        "updated_at": data.get("updated_at"),
        "html_url": data.get("html_url"),
        "language": data.get("language"),
        "open_issues_count": data.get("open_issues_count"),
    }


@router.get("/repos/{owner}/{repo}/pull-requests")
async def pull_requests(
    owner: str,
    repo: str,
    state: str = Query("open", pattern="^(open|closed|all)$"),
    limit: int = Query(20, ge=1, le=50),
    _auth=Depends(require_auth),
):
    data = await _get(owner, repo, "pulls", {"state": state, "per_page": limit, "sort": "updated", "direction": "desc"})
    return [{
        "number": item.get("number"),
        "title": item.get("title"),
        "state": item.get("state"),
        "draft": item.get("draft"),
        "html_url": item.get("html_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "head": (item.get("head") or {}).get("ref"),
        "base": (item.get("base") or {}).get("ref"),
    } for item in data]


@router.get("/repos/{owner}/{repo}/workflow-runs")
async def workflow_runs(
    owner: str,
    repo: str,
    branch: Optional[str] = None,
    limit: int = Query(10, ge=1, le=30),
    _auth=Depends(require_auth),
):
    params = {"per_page": limit}
    if branch:
        params["branch"] = branch
    data = await _get(owner, repo, "actions/runs", params)
    return [{
        "id": item.get("id"),
        "name": item.get("name"),
        "display_title": item.get("display_title"),
        "status": item.get("status"),
        "conclusion": item.get("conclusion"),
        "head_branch": item.get("head_branch"),
        "head_sha": item.get("head_sha"),
        "html_url": item.get("html_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    } for item in data.get("workflow_runs", [])]


@router.get("/repos/{owner}/{repo}/tree")
async def repository_tree(
    owner: str,
    repo: str,
    ref: str = Query("main", min_length=1, max_length=120),
    _auth=Depends(require_auth),
):
    if ".." in ref or "/" in ref and ref.startswith("/"):
        raise HTTPException(400, "Invalid Git reference")
    data = await _get(owner, repo, f"git/trees/{quote(ref, safe='')}", {"recursive": "1"})
    tree = data.get("tree", [])
    return {
        "sha": data.get("sha"),
        "truncated": data.get("truncated", False),
        "entries": [{
            "path": item.get("path"),
            "type": item.get("type"),
            "size": item.get("size"),
            "sha": item.get("sha"),
        } for item in tree[:1500]],
    }


@router.get("/repos/{owner}/{repo}/file")
async def repository_file(
    owner: str,
    repo: str,
    path: str = Query(..., min_length=1, max_length=500),
    ref: str = Query("main", min_length=1, max_length=120),
    _auth=Depends(require_auth),
):
    if ".." in path.split("/") or path.startswith("/") or ".." in ref:
        raise HTTPException(400, "Invalid repository path or Git reference")
    data = await _get(owner, repo, f"contents/{quote(path, safe='/')}", {"ref": ref})
    if data.get("type") != "file" or data.get("encoding") != "base64":
        raise HTTPException(400, "Requested GitHub resource is not a text file")
    try:
        raw = base64.b64decode(data.get("content", ""), validate=False)
        if len(raw) > 200_000:
            raise HTTPException(413, "File is too large to inspect in one request")
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(415, "File is not UTF-8 text") from exc
    return {
        "name": data.get("name"),
        "path": data.get("path"),
        "sha": data.get("sha"),
        "size": len(raw),
        "html_url": data.get("html_url"),
        "content": content,
    }
