"""Schema validation tests for crypto domain."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.crypto.schema import MarketQuote, QuoteSource, ResearchJobCreate


def test_quote_requires_positive_price():
    with pytest.raises(ValidationError):
        MarketQuote(
            asset_id="bitcoin",
            symbol="BTC",
            name="Bitcoin",
            price_usd=0,
            as_of=datetime.now(timezone.utc),
            source=QuoteSource.fixture,
            source_url="https://example.local/btc",
        )


def test_quote_requires_source_url():
    with pytest.raises(ValidationError):
        MarketQuote(
            asset_id="bitcoin",
            symbol="BTC",
            name="Bitcoin",
            price_usd=100.0,
            as_of=datetime.now(timezone.utc),
            source=QuoteSource.fixture,
            source_url="",
        )


def test_stale_detection():
    old = datetime.now(timezone.utc) - timedelta(seconds=600)
    q = MarketQuote(
        asset_id="bitcoin",
        symbol="BTC",
        name="Bitcoin",
        price_usd=100.0,
        as_of=old,
        source=QuoteSource.fixture,
        source_url="https://example.local/btc",
        stale_after_seconds=300,
    )
    assert q.is_stale is True


def test_fresh_quote():
    q = MarketQuote(
        asset_id="bitcoin",
        symbol="BTC",
        name="Bitcoin",
        price_usd=100.0,
        as_of=datetime.now(timezone.utc),
        source=QuoteSource.fixture,
        source_url="https://example.local/btc",
        stale_after_seconds=300,
    )
    assert q.is_stale is False


def test_research_job_query_min_length():
    with pytest.raises(ValidationError):
        ResearchJobCreate(query="ab")
