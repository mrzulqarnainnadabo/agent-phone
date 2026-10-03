# Stage 1 Handover — Crypto Intelligence Foundation

**Branch:** `feat/crypto-intelligence-foundation`  
**Scope:** Read-only market research module inside Agent Phone.  
**Not financial advice. No live trading.**

## What shipped

### Backend
- `server/app/crypto/` — schema (provenance + stale), FixtureProvider, CoinGeckoProvider, service, router
- Routes: `GET /api/v1/crypto/health`, watchlist CRUD, asset detail, quotes, search, research jobs
- Core preserved: `core_helpers.py`, `core_routes.py`, `core_routes_more.py` + thin `main.py`

### Frontend
- Markets tab + `client/app/MarketsPanel.tsx`
- States: loading, empty, error, stale, retry

### Docs / config
- `docs/CRYPTO.md`
- `.env.example`: `CRYPTO_PROVIDER=fixture` (default), optional `COINGECKO_API_KEY`
- `server/tests/test_crypto_schema.py`, `test_crypto_provider.py`
- `server/pytest.ini`

## Tests executed (sandbox)
- Schema: positive price, source_url, stale detection — PASS
- FixtureProvider: quote, search, not_found — PASS

## Env variables (names only)
- `CRYPTO_PROVIDER` — `fixture` | `coingecko`
- `COINGECKO_API_KEY` — optional, server-side only
- Existing: `APP_AUTH_TOKEN`, `MODEL_*`, `DATA_DIR`, `CORS_ORIGINS`, `NEXT_PUBLIC_*`

## Deployment checklist (founder only)
1. Review and merge this PR to `main`
2. Redeploy API (Render) — default fixture mode needs no new secrets
3. Redeploy PWA (Netlify) so Markets tab is live
4. Optional later: set `CRYPTO_PROVIDER=coingecko` + key on Render; show CoinGecko attribution
5. Do **not** enable trading, wallets, or private exchange keys

## Rollback
- Revert merge commit, or remove crypto router include and `server/app/crypto/`
- Production remains on previous `main` until merge + deploy

## Deferred (Stage 2+)
- AI Platform research summarization boundary
- Durable volume / Postgres
- Paper trading lab
- Multi-tenant workspaces

## Security notes
- Bearer auth on crypto endpoints
- No secrets in repo
- Market numbers from providers only; AI must not invent prices
