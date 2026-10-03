"""Crypto Intelligence HTTP routes — read-only market research."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from .provider import get_provider
from .schema import (
    AssetDetail,
    MarketQuote,
    ProviderError,
    ResearchJob,
    ResearchJobCreate,
    WatchlistAdd,
    WatchlistItem,
)
from . import service

router = APIRouter(prefix="/api/v1/crypto", tags=["crypto"])


async def require_auth(authorization: Optional[str] = Header(None)):
    import os

    token = os.getenv("APP_AUTH_TOKEN", "dev-token-change-me")
    if not token:
        return True
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    if authorization[7:].strip() != token:
        raise HTTPException(401, "Invalid token")
    return True


async def get_db():
    import os
    from pathlib import Path
    import aiosqlite

    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(data_dir / "agent_phone.db")
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
    finally:
        await db.close()


@router.get("/health")
async def crypto_health():
    provider = get_provider()
    return {
        "ok": True,
        "provider": provider.name,
        "mode": "read_only",
        "trading_enabled": False,
        "disclaimer": "Research and paper-trading foundation only. Not financial advice.",
    }


@router.get("/watchlist", response_model=List[WatchlistItem])
async def api_list_watchlist(db=Depends(get_db), _auth=Depends(require_auth)):
    return await service.list_watchlist(db)


@router.post("/watchlist", response_model=WatchlistItem)
async def api_add_watchlist(body: WatchlistAdd, db=Depends(get_db), _auth=Depends(require_auth)):
    try:
        return await service.add_watchlist(db, body.asset_id)
    except ProviderError as e:
        status = 404 if e.code == "not_found" else 502
        raise HTTPException(status, {"detail": str(e), "code": e.code, "retryable": e.retryable})


@router.delete("/watchlist/{asset_id}")
async def api_remove_watchlist(asset_id: str, db=Depends(get_db), _auth=Depends(require_auth)):
    ok = await service.remove_watchlist(db, asset_id)
    if not ok:
        raise HTTPException(404, "Not on watchlist")
    return {"ok": True, "asset_id": asset_id}


@router.get("/assets/{asset_id}", response_model=AssetDetail)
async def api_asset_detail(asset_id: str, _auth=Depends(require_auth)):
    try:
        return await service.get_asset_detail(asset_id)
    except ProviderError as e:
        status = 404 if e.code == "not_found" else 502
        raise HTTPException(status, {"detail": str(e), "code": e.code, "retryable": e.retryable})


@router.get("/quotes", response_model=List[MarketQuote])
async def api_quotes(ids: str = Query(..., description="Comma-separated asset ids"), _auth=Depends(require_auth)):
    asset_ids = [x.strip() for x in ids.split(",") if x.strip()]
    if not asset_ids:
        raise HTTPException(400, "ids required")
    provider = get_provider()
    try:
        return await provider.get_quotes(asset_ids)
    except ProviderError as e:
        raise HTTPException(502, {"detail": str(e), "code": e.code, "retryable": e.retryable})


@router.get("/search")
async def api_search(q: str = Query(..., min_length=1), limit: int = Query(10, le=25), _auth=Depends(require_auth)):
    provider = get_provider()
    try:
        return await provider.search(q, limit=limit)
    except ProviderError as e:
        raise HTTPException(502, {"detail": str(e), "code": e.code, "retryable": e.retryable})


@router.post("/research/jobs", response_model=ResearchJob)
async def api_create_research(body: ResearchJobCreate, db=Depends(get_db), _auth=Depends(require_auth)):
    return await service.create_research_job(db, body)


@router.get("/research/jobs/{job_id}", response_model=ResearchJob)
async def api_get_research(job_id: str, db=Depends(get_db), _auth=Depends(require_auth)):
    job = await service.get_research_job(db, job_id)
    if not job:
        raise HTTPException(404, "Research job not found")
    return job
