"""Fixture provider and error-path tests."""
import pytest

from app.crypto.provider import FixtureProvider
from app.crypto.schema import ProviderError, QuoteSource


@pytest.mark.asyncio
async def test_fixture_quote_bitcoin():
    p = FixtureProvider(age_seconds=10)
    q = await p.get_quote("bitcoin")
    assert q.asset_id == "bitcoin"
    assert q.symbol == "BTC"
    assert q.price_usd > 0
    assert q.source == QuoteSource.fixture
    assert q.source_url
    assert q.is_stale is False


@pytest.mark.asyncio
async def test_fixture_unknown_asset():
    p = FixtureProvider()
    with pytest.raises(ProviderError) as ei:
        await p.get_quote("not-a-real-coin-xyz")
    assert ei.value.code == "not_found"
    assert ei.value.retryable is False


@pytest.mark.asyncio
async def test_fixture_stale():
    p = FixtureProvider(age_seconds=400, stale_after_seconds=300)
    q = await p.get_quote("ethereum")
    assert q.is_stale is True


@pytest.mark.asyncio
async def test_fixture_search():
    p = FixtureProvider()
    hits = await p.search("bit")
    assert any(h["asset_id"] == "bitcoin" for h in hits)


@pytest.mark.asyncio
async def test_get_quotes_skips_unknown():
    p = FixtureProvider()
    quotes = await p.get_quotes(["bitcoin", "nope", "solana"])
    ids = {q.asset_id for q in quotes}
    assert "bitcoin" in ids
    assert "solana" in ids
    assert "nope" not in ids
