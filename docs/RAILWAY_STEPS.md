# Agent Phone — Existing Railway / Netlify Configuration

Repository: https://github.com/mrzulqarnainnadabo/agent-phone

**Do not perform a production deployment from this document without explicit approval.** This branch introduces a new authentication contract; the API and PWA must be upgraded together.

## Backend service (existing service)

Keep the current backend service and persistent disk. Do not create a new paid service or database.

Required server-side variables:

```text
APP_LOGIN_PASSWORD=<unique owner password, at least 12 characters>
SESSION_SECRET=<random secret generated with openssl rand -hex 32>
SESSION_TTL_SECONDS=28800
DATA_DIR=/data
HOST=0.0.0.0
PORT=8000
```

Optional AI variables:

```text
MODEL_API_KEY=<provider API key>
MODEL_API_BASE_URL=https://api.openai.com/v1
DEFAULT_MODEL=gpt-4o-mini

# Optional read-only GitHub inspection. Restrict token scopes and repository access.
GITHUB_TOKEN=<fine-grained-token-with-read-only-scopes>
GITHUB_ALLOWED_REPOS=mrzulqarnainnadabo/agent-phone
```

Keep all credentials server-side. Never expose the owner password, session secret, GitHub token, or model API key to the frontend. The GitHub integration is strictly read-only and checks an exact server-side repository allowlist.

Keep the persistent volume mounted at `/data`. Verify `/health` and `/ready` after an approved deployment.

## Frontend service (existing Netlify site)

Only set:

```text
NEXT_PUBLIC_API_URL=https://YOUR-API-URL
```

Remove the old `NEXT_PUBLIC_APP_AUTH_TOKEN` variable. The new frontend signs in through the API and receives a short-lived session token at runtime.

If the API URL changes, rebuild the frontend because Next.js public variables are baked in at build time.

## Phone sign-in smoke test

1. Open the PWA.
2. Sign in using the owner password.
3. Confirm incorrect passwords are rejected.
4. Confirm protected routes work after sign-in.
5. Sign out and confirm protected routes require a new session.
6. Create a project, task, and checkpoint; reload and confirm they persist.
7. Restart the API and confirm the SQLite data remains available.

## Important migration boundary

The existing `main` branch uses a legacy shared bearer token. The personal-operations branch uses password login and signed expiring sessions. Do not merge or deploy until the new backend variables are configured, the frontend no longer relies on a public token, and both services are ready to move together.
