# Crypto Intelligence — Stage 1 Foundation

Read-only market research module inside Agent Phone. **Not financial advice. No live trading.**

## What is included

- Market data schemas with `as_of`, `source`, `source_url`, and `is_stale`
- `FixtureProvider` (default) for local/CI
- Optional `CoinGeckoProvider` (`CRYPTO_PROVIDER=coingecko`)
- Watchlist CRUD, asset detail, quotes, search
- Research job **contract** (metadata + optional quote snapshot; AI summarization deferred)

## What is forbidden

- Exchange order execution, private API keys, wallets, deposits, custody
- AI inventing prices or citations
- Redistributing raw aggregator data dumps against provider terms

## Environment (names only)

| Variable | Purpose |
|----------|--------|
| `CRYPTO_PROVIDER` | `fixture` (default) or `coingecko` |
| `COINGECKO_API_KEY` | Optional demo/pro key (server-side only) |
| `APP_AUTH_TOKEN` | Existing Bearer auth |
| `DATA_DIR` | SQLite path |

## Attribution

When using CoinGecko, UI and API notes must show: **Data provided by CoinGecko**.

## API (Bearer required)

- `GET /api/v1/crypto/health`
- `GET/POST /api/v1/crypto/watchlist`
- `DELETE /api/v1/crypto/watchlist/{asset_id}`
- `GET /api/v1/crypto/assets/{asset_id}`
- `GET /api/v1/crypto/quotes?ids=bitcoin,ethereum`
- `GET /api/v1/crypto/search?q=btc`
- `POST /api/v1/crypto/research/jobs`
- `GET /api/v1/crypto/research/jobs/{id}`

## Stage 2 boundary (AI Platform)

Summarization may call AI Platform only with explicit capability and **allowed source excerpts**; market numbers stay on `MarketDataProvider`.

## Rollback

Remove crypto router include from `main.py` and delete `server/app/crypto/`. Existing agents/goals/approvals are unchanged.
