# Deploy Agent Phone

This guide describes the existing hosting layout. **Do not deploy this development branch until the owner has explicitly approved the deployment and configured the new session secrets.**

## Security pre-flight

The personal-operations branch replaces the permanent browser-visible bearer token with password login and short-lived signed sessions.

Required backend environment variables:

- `APP_LOGIN_PASSWORD`: a unique owner password of at least 12 characters.
- `SESSION_SECRET`: at least 32 random bytes, generated with `openssl rand -hex 32`.
- `SESSION_TTL_SECONDS`: optional; defaults to 28,800 seconds (8 hours).
- `MODEL_API_KEY`: optional for non-AI workspace features; required for real model replies.
- `MODEL_API_BASE_URL`: defaults to `https://api.openai.com/v1`.
- `DEFAULT_MODEL`: defaults to `gpt-4o-mini`.
- `MODEL_MAX_TOKENS`: defaults to 1,024 output tokens per model call.
- `MODEL_DAILY_CALL_LIMIT`: defaults to 60 model calls per UTC day, including tool-call rounds.
- `APP_ENV=production`.
- `CORS_ORIGINS`: exact trusted frontend origin(s), for example `https://agent-phone.netlify.app`; production startup fails if this is empty.
- `DATA_DIR`: persistent SQLite directory.
- `GITHUB_TOKEN`: optional fine-grained GitHub token with read-only repository metadata, contents, pull requests, and Actions permissions.
- `GITHUB_ALLOWED_REPOS`: comma-separated exact `owner/repository` allowlist. Leave empty to disable GitHub inspection.

Never put `APP_LOGIN_PASSWORD`, `SESSION_SECRET`, `GITHUB_TOKEN`, or a model API key in a `NEXT_PUBLIC_*` variable or frontend build argument. Give the GitHub token read-only scopes and restrict it to the exact repositories in the allowlist.

Frontend environment:

- `NEXT_PUBLIC_API_URL`: public HTTPS URL of the FastAPI service.

There is no frontend authentication-token environment variable. The owner signs in through the app; the browser receives an expiring session token and stores it in the current browser session.

## Existing Railway + Netlify layout

### 1. Backend API

If/when deployment is approved:

1. Use the existing API service; do not provision a new hosting product.
2. Keep the persistent volume mounted at `/data` and set `DATA_DIR=/data`.
3. Set `APP_LOGIN_PASSWORD` and `SESSION_SECRET` in the hosting provider's server-side environment settings.
4. Set `SESSION_TTL_SECONDS=28800` unless a different session duration is deliberately chosen.
5. Keep `MODEL_API_KEY` server-side only.
6. Confirm HTTPS is enabled.
7. Verify `/health` and `/ready`.

### 2. Frontend PWA

The frontend needs only:

```text
NEXT_PUBLIC_API_URL=https://YOUR-API-URL
```

Do not add an API bearer token to Netlify or any `NEXT_PUBLIC_*` variable. Rebuild the frontend after changing the API URL because Next.js public environment variables are baked in at build time.

### 3. Phone sign-in

1. Open the PWA URL.
2. Enter the owner password configured on the API service.
3. The API issues an expiring signed session.
4. Sign out when finished; sessions also expire automatically.

## Local Docker Compose

1. Copy `.env.example` to `.env`.
2. Set a unique `APP_LOGIN_PASSWORD`.
3. Generate `SESSION_SECRET` with `openssl rand -hex 32`.
4. Optionally set `MODEL_API_KEY` for real AI replies.
5. Set `NEXT_PUBLIC_API_URL=http://localhost:8000`.
6. Run:

```bash
docker compose up --build
```

The default placeholder values intentionally do not permit login. Configure real secrets before use.

## Smoke-test checklist

- Owner login succeeds with the configured password.
- Incorrect passwords are rejected and repeated failures are rate-limited.
- Protected API routes reject missing, malformed, and expired sessions.
- Session tokens are not embedded in the frontend bundle.
- Create a project, create a task, save a checkpoint, reload, and confirm records persist.
- Restart the API and confirm SQLite data remains on the persistent volume.
- Confirm no deployment or external write action is enabled by CI.

## Existing deployment compatibility

The current `main` branch still uses the previous bearer-token contract. This branch changes the API authentication contract. Do not merge or deploy it until the new backend environment variables are configured and the frontend/API pair are deployed together under an approved change window.

Production deployment, credential changes, and merging to `main` remain separate approval decisions.
