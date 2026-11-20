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
