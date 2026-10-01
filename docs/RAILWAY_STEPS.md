# Deploy Agent Phone on Railway — exact steps

Repo: https://github.com/mrzulqarnainnadabo/agent-phone

You need a free Railway account: https://railway.app

---

## Part A — API (backend)

1. Open https://railway.app/new
2. Choose **Deploy from GitHub repo**
3. Select **mrzulqarnainnadabo/agent-phone** (authorize GitHub if asked)
4. After the service is created, open **Settings**:
   - **Root Directory** → set to `server`
   - **Watch Paths** → `server/**` (optional)
5. Open **Variables** → add:

```
APP_AUTH_TOKEN=<paste a long random string, e.g. openssl rand -hex 32>
MODEL_API_KEY=<your OpenAI or OpenRouter key>
MODEL_API_BASE_URL=https://api.openai.com/v1
DEFAULT_MODEL=gpt-4o-mini
DATA_DIR=/data
HOST=0.0.0.0
```

6. **Volume** (critical for SQLite):
   - Right-click canvas or Command Palette → **Volume**
   - Attach to the API service
   - Mount path: `/data`

7. **Networking** → **Generate Domain** → copy the HTTPS URL  
   Example: `https://agent-phone-api-production.up.railway.app`

8. Wait for deploy (green). Test:

```bash
curl https://YOUR-API-URL/health
curl https://YOUR-API-URL/ready
```

Both should return `ok`.

---

## Part B — Web (PWA frontend)

1. In the **same** Railway project → **+ New** → **GitHub Repo** → same repo
2. Settings:
   - **Root Directory** → `client`
3. Variables:

```
NEXT_PUBLIC_API_URL=https://YOUR-API-URL
NEXT_PUBLIC_APP_AUTH_TOKEN=<same token as API>
```

4. If using Nixpacks (no Dockerfile pick):
   - Build command: `npm install && npm run build`
   - Start command: `npm start`

   Or set builder to **Dockerfile** (client/Dockerfile) and pass build args in Railway:
   - `NEXT_PUBLIC_API_URL`
   - `NEXT_PUBLIC_APP_AUTH_TOKEN`

5. **Generate Domain** for the web service
6. Open the web URL on your phone → Safari/Chrome → **Add to Home Screen**

---

## Part C — Smoke test

1. Approvals → **Simulate proposal** → Approve  
2. Agents → create one  
3. Goals → create one → handoff  
4. Restart the API service in Railway  
5. Confirm agents/goals still exist (volume worked)

---

## If build fails

| Symptom | Fix |
|---------|-----|
| Python module not found | Root Directory must be `server` |
| Next build can't find package.json | Root Directory must be `client` |
| Data lost after restart | Volume not mounted at `/data` |
| Frontend talks to localhost | Rebuild web with correct `NEXT_PUBLIC_API_URL` |
| 401 on all API calls | Token mismatch between web and API |

---

## After you have both URLs

Paste them back here:

- API: `https://...`
- Web: `https://...`

We will verify the smoke test and lock down anything still open.
