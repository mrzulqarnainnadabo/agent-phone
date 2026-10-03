"""Normalized crypto market schemas with provenance. Prices are never invented by AI."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class QuoteSource(str, Enum):
    fixture = "fixture"
    coingecko = "coingecko"


class MarketQuote(BaseModel):
    asset_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    price_usd: float = Field(..., gt=0)
    as_of: datetime
    source: QuoteSource
    source_url: str = Field(..., min_length=1)
    change_24h_pct: Optional[float] = None
    market_cap_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    is_stale: bool = False
    stale_after_seconds: int = Field(default=300, ge=30)

    @field_validator("as_of", mode="before")
    @classmethod
    def parse_as_of(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, str):
            s = v.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        raise ValueError("as_of must be ISO-8601 datetime")

    @model_validator(mode="after")
    def compute_stale(self) -> "MarketQuote":
        now = datetime.now(timezone.utc)
        age = (now - self.as_of.astimezone(timezone.utc)).total_seconds()
        object.__setattr__(self, "is_stale", age > self.stale_after_seconds)
        return self


class WatchlistItem(BaseModel):
    id: str
    asset_id: str
    symbol: str
    name: str
    created_at: datetime
    quote: Optional[MarketQuote] = None


class WatchlistAdd(BaseModel):
    asset_id: str = Field(..., min_length=1, description="e.g. bitcoin, ethereum")


class AssetDetail(BaseModel):
    asset_id: str
    symbol: str
    name: str
    quote: MarketQuote
    notes: Optional[str] = None


class ResearchJobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ResearchJobCreate(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    asset_ids: List[str] = Field(default_factory=list)


class ResearchJob(BaseModel):
    id: str
    status: ResearchJobStatus
    query: str
    asset_ids: List[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None
    source_urls: List[str] = Field(default_factory=list)
    data_snapshot: Optional[dict] = None
    structured_output: Optional[dict] = None
    limitations: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    model_or_workflow_version: Optional[str] = None


class ProviderError(Exception):
    """Provider-level failure (timeout, rate limit, malformed upstream)."""

    def __init__(self, message: str, *, code: str = "provider_error", retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
