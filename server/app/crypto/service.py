"""Crypto domain services: watchlist persistence + research job contracts."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite

from .provider import get_provider
from .schema import (
    AssetDetail,
    MarketQuote,
    ProviderError,
    ResearchJob,
    ResearchJobCreate,
    ResearchJobStatus,
    WatchlistItem,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def ensure_crypto_tables(db: aiosqlite.Connection) -> None:
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS crypto_watchlist (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL UNIQUE,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS crypto_research_jobs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            query TEXT NOT NULL,
            asset_ids TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            source_urls TEXT,
            data_snapshot TEXT,
            structured_output TEXT,
            limitations TEXT,
            error TEXT,
            model_or_workflow_version TEXT
        );
        """
    )
    await db.commit()


async def list_watchlist(db: aiosqlite.Connection, *, with_quotes: bool = True) -> List[WatchlistItem]:
    await ensure_crypto_tables(db)
    cur = await db.execute(
        "SELECT id, asset_id, symbol, name, created_at FROM crypto_watchlist ORDER BY created_at DESC"
    )
    rows = await cur.fetchall()
    items: List[WatchlistItem] = []
    asset_ids = [r["asset_id"] for r in rows]
    quotes_map = {}
    if with_quotes and asset_ids:
        provider = get_provider()
        try:
            quotes = await provider.get_quotes(asset_ids)
            quotes_map = {q.asset_id: q for q in quotes}
        except ProviderError:
            quotes_map = {}
    for r in rows:
        items.append(
            WatchlistItem(
                id=r["id"],
                asset_id=r["asset_id"],
                symbol=r["symbol"],
                name=r["name"],
                created_at=r["created_at"],
                quote=quotes_map.get(r["asset_id"]),
            )
        )
    return items


async def add_watchlist(db: aiosqlite.Connection, asset_id: str) -> WatchlistItem:
    await ensure_crypto_tables(db)
    provider = get_provider()
    quote = await provider.get_quote(asset_id)
    item_id = f"wl-{uuid.uuid4().hex[:10]}"
    created = _now()
    try:
        await db.execute(
            "INSERT INTO crypto_watchlist (id, asset_id, symbol, name, created_at) VALUES (?,?,?,?,?)",
            (item_id, quote.asset_id, quote.symbol, quote.name, _iso(created)),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        cur = await db.execute(
            "SELECT id, asset_id, symbol, name, created_at FROM crypto_watchlist WHERE asset_id = ?",
            (quote.asset_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise
        return WatchlistItem(
            id=row["id"],
            asset_id=row["asset_id"],
            symbol=row["symbol"],
            name=row["name"],
            created_at=row["created_at"],
            quote=quote,
        )
    return WatchlistItem(
        id=item_id,
        asset_id=quote.asset_id,
        symbol=quote.symbol,
        name=quote.name,
        created_at=created,
        quote=quote,
    )


async def remove_watchlist(db: aiosqlite.Connection, asset_id: str) -> bool:
    await ensure_crypto_tables(db)
    cur = await db.execute("DELETE FROM crypto_watchlist WHERE asset_id = ?", (asset_id.strip().lower(),))
    await db.commit()
    return cur.rowcount > 0


async def get_asset_detail(asset_id: str) -> AssetDetail:
    provider = get_provider()
    quote = await provider.get_quote(asset_id)
    notes = None
    if quote.source.value == "coingecko":
        notes = "Data provided by CoinGecko. Not financial advice."
    elif quote.source.value == "fixture":
        notes = "Fixture data for development/tests. Not live market data."
    return AssetDetail(
        asset_id=quote.asset_id,
        symbol=quote.symbol,
        name=quote.name,
        quote=quote,
        notes=notes,
    )


async def create_research_job(db: aiosqlite.Connection, body: ResearchJobCreate) -> ResearchJob:
    """Stage 1: record job contract + optional snapshot; no live AI research yet."""
    await ensure_crypto_tables(db)
    job_id = f"rj-{uuid.uuid4().hex[:10]}"
    created = _now()
    limitations = [
        "Stage 1 records research job metadata only; AI summarization is deferred to Stage 2.",
        "Market numbers must come from MarketDataProvider, not from model text.",
        "Not financial advice. No trading or execution.",
    ]
    snapshot = None
    source_urls: List[str] = []
    status = ResearchJobStatus.completed
    error = None
    if body.asset_ids:
        provider = get_provider()
        try:
            quotes = await provider.get_quotes(body.asset_ids)
            snapshot = {"quotes": [q.model_dump(mode="json") for q in quotes]}
            source_urls = [q.source_url for q in quotes]
        except ProviderError as e:
            status = ResearchJobStatus.failed
            error = str(e)
            limitations.append(f"Provider error: {e.code}")

    await db.execute(
        """INSERT INTO crypto_research_jobs
        (id, status, query, asset_ids, created_at, completed_at, source_urls, data_snapshot,
         structured_output, limitations, error, model_or_workflow_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            job_id,
            status.value,
            body.query,
            json.dumps(body.asset_ids),
            _iso(created),
            _iso(_now()) if status != ResearchJobStatus.pending else None,
            json.dumps(source_urls),
            json.dumps(snapshot) if snapshot else None,
            None,
            json.dumps(limitations),
            error,
            "stage1-contract-v1",
        ),
    )
    await db.commit()
    return ResearchJob(
        id=job_id,
        status=status,
        query=body.query,
        asset_ids=body.asset_ids,
        created_at=created,
        completed_at=_now() if status != ResearchJobStatus.pending else None,
        source_urls=source_urls,
        data_snapshot=snapshot,
        structured_output=None,
        limitations=limitations,
        error=error,
        model_or_workflow_version="stage1-contract-v1",
    )


async def get_research_job(db: aiosqlite.Connection, job_id: str) -> Optional[ResearchJob]:
    await ensure_crypto_tables(db)
    cur = await db.execute("SELECT * FROM crypto_research_jobs WHERE id = ?", (job_id,))
    row = await cur.fetchone()
    if not row:
        return None
    return ResearchJob(
        id=row["id"],
        status=ResearchJobStatus(row["status"]),
        query=row["query"],
        asset_ids=json.loads(row["asset_ids"] or "[]"),
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        source_urls=json.loads(row["source_urls"] or "[]"),
        data_snapshot=json.loads(row["data_snapshot"]) if row["data_snapshot"] else None,
        structured_output=json.loads(row["structured_output"]) if row["structured_output"] else None,
        limitations=json.loads(row["limitations"] or "[]"),
        error=row["error"],
        model_or_workflow_version=row["model_or_workflow_version"],
    )
