# Deploy Agent Phone

Goal: a public HTTPS demo a tester can open on their phone, create agents/goals, simulate approvals, and not lose data after a restart.

---

## Pre-flight checklist

- [ ] `APP_AUTH_TOKEN` is a long random string (not `dev-token-change-me`)
- [ ] `MODEL_API_KEY` is set (or accept placeholder replies)
- [ ] SQLite lives on a **persistent volume** (`DATA_DIR=/data`)
- [ ] `/health` and `/ready` return OK
- [ ] Every non-health API route requires Bearer auth
- [ ] Frontend `NEXT_PUBLIC_API_URL` points at the **public** API URL (HTTPS)
- [ ] No real messaging/send/delete tools enabled for the public demo
- [ ] Smoke test: create agent → create goal → handoff → simulate approval → approve/reject → restart → data still there

---

## Railway (recommended)

### 1. Backend (API)

1. New Railway project → **Deploy from GitHub** → this repo.
2. Root directory / service: `server`
3. Start command: `python run.py` (or use the Dockerfile)
4. Add a **Volume** mounted at `/data`
5. Environment variables:

```
MODEL_API_KEY=sk-...
MODEL_API_BASE_URL=https://api.openai.com/v1
DEFAULT_MODEL=gpt-4o-mini
APP_AUTH_TOKEN=<long-random-string>
DATA_DIR=/data
HOST=0.0.0.0
PORT=8000
```

6. Enable **public networking** → copy the HTTPS URL (e.g. `https://agent-phone-api.up.railway.app`)

7. Verify:

```bash
curl https://YOUR-API.up.railway.app/health
curl https://YOUR-API.up.railway.app/ready
```

### 2. Frontend (PWA)

1. Add a second service from the same repo, root `client`
2. Build: `npm install && npm run build`
3. Start: `npm start` (or use Dockerfile)
4. Build-time / env vars:

```
NEXT_PUBLIC_API_URL=https://YOUR-API.up.railway.app
NEXT_PUBLIC_APP_AUTH_TOKEN=<same-as-backend>
```

**Important:** `NEXT_PUBLIC_*` values are baked in at **build** time for Next.js. If you change the API URL, rebuild the frontend.

5. Enable public networking → open the web URL on your phone.

### 3. Phone install

- **iOS Safari** → Share → Add to Home Screen  
- **Android Chrome** → Menu → Install app / Add to Home screen  

Opens full-screen as a PWA.

---

## Docker Compose (self-host / VPS)

```bash
cp .env.example .env
# edit: MODEL_API_KEY, APP_AUTH_TOKEN, NEXT_PUBLIC_API_URL

docker compose up -d --build
```

- API: http://localhost:8000  
- Web: http://localhost:3000  
- Data: Docker volume `agent_phone_data` (survives restarts)

For a public VPS, put a reverse proxy (Caddy/Nginx) with HTTPS in front and set `NEXT_PUBLIC_API_URL` to that HTTPS API URL before building the web image.

---

## Render

Same pattern:

1. **Web Service** for FastAPI (`server/`, Docker or `python run.py`)
2. Disk / persistent storage for `/data`
3. **Web Service** or static for Next.js (`client/`)
4. Env vars as above

---

## Smoke test after deploy

```text
1. Open PWA URL on phone
2. Agents → + New → create Atlas
3. Approvals → Simulate proposal → Approve
4. Goals → + New → add agent → open room → Handoff
5. Restart the API service
6. Confirm agents / goals / approvals still exist
```

If step 6 fails, the volume is not mounted correctly.

---

## Security notes for a public demo

- Change `APP_AUTH_TOKEN` before sharing the link.
- Share the token only with trusted testers (or add a simple login later).
- Do not enable real external send/delete tools yet.
- Demo approvals are safe: they record decisions only; they do not send email/SMS.
