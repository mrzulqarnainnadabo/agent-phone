"""Market data providers. Deterministic numbers only; AI must not invent prices."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Protocol

import httpx

from .schema import MarketQuote, ProviderError, QuoteSource


_FIXTURE_CATALOG: Dict[str, dict] = {
    "bitcoin": {
        "symbol": "BTC",
        "name": "Bitcoin",
        "price_usd": 67500.0,
        "change_24h_pct": 1.25,
        "market_cap_usd": 1.33e12,
        "volume_24h_usd": 2.8e10,
        "source_url": "https://example.local/fixture/bitcoin",
    },
    "ethereum": {
        "symbol": "ETH",
        "name": "Ethereum",
        "price_usd": 3450.0,
        "change_24h_pct": -0.8,
        "market_cap_usd": 4.15e11,
        "volume_24h_usd": 1.5e10,
        "source_url": "https://example.local/fixture/ethereum",
    },
    "solana": {
        "symbol": "SOL",
        "name": "Solana",
        "price_usd": 145.0,
        "change_24h_pct": 3.1,
        "market_cap_usd": 6.7e10,
        "volume_24h_usd": 3.2e9,
        "source_url": "https://example.local/fixture/solana",
    },
}


class MarketDataProvider(Protocol):
    name: str

    async def get_quote(self, asset_id: str) -> MarketQuote: ...

    async def get_quotes(self, asset_ids: List[str]) -> List[MarketQuote]: ...

    async def search(self, query: str, limit: int = 10) -> List[dict]: ...


class FixtureProvider:
    """In-process deterministic quotes for local dev and CI."""

    name = "fixture"

    def __init__(self, *, age_seconds: int = 30, stale_after_seconds: int = 300):
        self.age_seconds = age_seconds
        self.stale_after_seconds = stale_after_seconds

    def _build(self, asset_id: str, *, force_stale: bool = False) -> MarketQuote:
        key = asset_id.strip().lower()
        row = _FIXTURE_CATALOG.get(key)
        if not row:
            raise ProviderError(f"Unknown fixture asset: {asset_id}", code="not_found", retryable=False)
        age = 400 if force_stale else self.age_seconds
        as_of = datetime.now(timezone.utc) - timedelta(seconds=age)
        return MarketQuote(
            asset_id=key,
            symbol=row["symbol"],
            name=row["name"],
            price_usd=float(row["price_usd"]),
            as_of=as_of,
            source=QuoteSource.fixture,
            source_url=row["source_url"],
            change_24h_pct=row.get("change_24h_pct"),
            market_cap_usd=row.get("market_cap_usd"),
            volume_24h_usd=row.get("volume_24h_usd"),
            stale_after_seconds=self.stale_after_seconds,
        )

    async def get_quote(self, asset_id: str) -> MarketQuote:
        return self._build(asset_id)

    async def get_quotes(self, asset_ids: List[str]) -> List[MarketQuote]:
        out: List[MarketQuote] = []
        for aid in asset_ids:
            try:
                out.append(self._build(aid))
            except ProviderError:
                continue
        return out

    async def search(self, query: str, limit: int = 10) -> List[dict]:
        q = query.strip().lower()
        hits = []
        for aid, row in _FIXTURE_CATALOG.items():
            if q in aid or q in row["symbol"].lower() or q in row["name"].lower():
                hits.append({"asset_id": aid, "symbol": row["symbol"], "name": row["name"]})
        return hits[:limit]


class CoinGeckoProvider:
    """Public/demo CoinGecko REST adapter (read-only). Attribution required."""

    name = "coingecko"
    BASE = "https://api.coingecko.com/api/v3"

    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 12.0, stale_after_seconds: int = 300):
        self.api_key = api_key or os.getenv("COINGECKO_API_KEY", "")
        self.timeout = timeout
        self.stale_after_seconds = stale_after_seconds

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.api_key:
            h["x-cg-demo-api-key"] = self.api_key
        return h

    async def get_quote(self, asset_id: str) -> MarketQuote:
        aid = asset_id.strip().lower()
        url = f"{self.BASE}/coins/markets"
        params = {"vs_currency": "usd", "ids": aid, "price_change_percentage": "24h"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException as e:
            raise ProviderError("CoinGecko timeout", code="timeout", retryable=True) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"CoinGecko network error: {e}", code="network", retryable=True) from e
        if r.status_code == 429:
            raise ProviderError("CoinGecko rate limited", code="rate_limit", retryable=True)
        if r.status_code >= 400:
            raise ProviderError(f"CoinGecko HTTP {r.status_code}", code="http_error", retryable=r.status_code >= 500)
        data = r.json()
        if not isinstance(data, list) or not data:
            raise ProviderError(f"No market data for {aid}", code="not_found", retryable=False)
        row = data[0]
        price = row.get("current_price")
        if price is None or float(price) <= 0:
            raise ProviderError("Malformed price from CoinGecko", code="malformed", retryable=False)
        as_of_raw = row.get("last_updated") or datetime.now(timezone.utc).isoformat()
        return MarketQuote(
            asset_id=aid,
            symbol=str(row.get("symbol", aid)).upper(),
            name=str(row.get("name", aid)),
            price_usd=float(price),
            as_of=as_of_raw,
            source=QuoteSource.coingecko,
            source_url=f"https://www.coingecko.com/en/coins/{aid}",
            change_24h_pct=row.get("price_change_percentage_24h"),
            market_cap_usd=row.get("market_cap"),
            volume_24h_usd=row.get("total_volume"),
            stale_after_seconds=self.stale_after_seconds,
        )

    async def get_quotes(self, asset_ids: List[str]) -> List[MarketQuote]:
        if not asset_ids:
            return []
        ids = ",".join(a.strip().lower() for a in asset_ids)
        url = f"{self.BASE}/coins/markets"
        params = {"vs_currency": "usd", "ids": ids, "price_change_percentage": "24h"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException as e:
            raise ProviderError("CoinGecko timeout", code="timeout", retryable=True) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"CoinGecko network error: {e}", code="network", retryable=True) from e
        if r.status_code == 429:
            raise ProviderError("CoinGecko rate limited", code="rate_limit", retryable=True)
        if r.status_code >= 400:
            raise ProviderError(f"CoinGecko HTTP {r.status_code}", code="http_error", retryable=True)
        data = r.json()
        if not isinstance(data, list):
            raise ProviderError("Malformed CoinGecko list", code="malformed", retryable=False)
        out: List[MarketQuote] = []
        for row in data:
            aid = str(row.get("id", "")).lower()
            price = row.get("current_price")
            if not aid or price is None or float(price) <= 0:
                continue
            out.append(
                MarketQuote(
                    asset_id=aid,
                    symbol=str(row.get("symbol", aid)).upper(),
                    name=str(row.get("name", aid)),
                    price_usd=float(price),
                    as_of=row.get("last_updated") or datetime.now(timezone.utc).isoformat(),
                    source=QuoteSource.coingecko,
                    source_url=f"https://www.coingecko.com/en/coins/{aid}",
                    change_24h_pct=row.get("price_change_percentage_24h"),
                    market_cap_usd=row.get("market_cap"),
                    volume_24h_usd=row.get("total_volume"),
                    stale_after_seconds=self.stale_after_seconds,
                )
            )
        return out

    async def search(self, query: str, limit: int = 10) -> List[dict]:
        url = f"{self.BASE}/search"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url, params={"query": query}, headers=self._headers())
        except httpx.HTTPError as e:
            raise ProviderError(f"CoinGecko search error: {e}", code="network", retryable=True) from e
        if r.status_code == 429:
            raise ProviderError("CoinGecko rate limited", code="rate_limit", retryable=True)
        if r.status_code >= 400:
            raise ProviderError(f"CoinGecko HTTP {r.status_code}", code="http_error", retryable=True)
        data = r.json()
        coins = data.get("coins") if isinstance(data, dict) else None
        if not isinstance(coins, list):
            return []
        hits = []
        for c in coins[:limit]:
            hits.append({"asset_id": c.get("id"), "symbol": str(c.get("symbol", "")).upper(), "name": c.get("name")})
        return hits


def get_provider() -> MarketDataProvider:
    mode = os.getenv("CRYPTO_PROVIDER", "fixture").strip().lower()
    if mode == "coingecko":
        return CoinGeckoProvider()
    return FixtureProvider()
