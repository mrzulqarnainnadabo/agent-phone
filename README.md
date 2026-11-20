# Agent Phone

**A phone-first control room for trusted AI workers.**

Installable PWA for iOS (iPhone XR+) and Android.  
Agents have clear roles, limited access, visible work, and must ask before consequential actions.

Built to sell to individuals and organizations — without Vercel/Supabase lock-in.

---

## Current status (personal operations foundation — in progress)

### Existing foundation
- [x] Mobile-first Next.js 15 PWA (Add to Home Screen)
- [x] FastAPI + SQLite persistence
- [x] Agent identity, permissions, and approval policies
- [x] Approval inbox and proposal simulation
- [x] Goals, bounded agent membership, and handoffs
- [x] Read-only Crypto Intelligence module (fixture provider by default)
- [x] Docker Compose and existing hosting documentation

### Personal operations foundation (working branch)
- [x] CI-only GitHub Actions for backend tests and frontend production builds
- [x] Regression coverage for core API authentication and approval lifecycle
- [x] Password-based owner login, rate-limited sign-in, and short-lived signed sessions
- [x] No permanent bearer token or privileged credential embedded in the browser bundle
- [x] Single-use approval decisions (missing and previously decided approvals rejected)
- [x] Persistent project registry, tasks, checkpoints, decision records, and operating preferences
- [x] Mobile Work tab for projects, tasks, preferences, and progress checkpoints
- [x] Chat receives saved operating charter, project/task context, and recent checkpoints
- [x] Server-controlled model selection and bounded chat history
- [x] Structured model configuration/provider errors instead of placeholder assistant replies
- [x] Frontend Dockerfile aligned with the existing non-standalone Next.js configuration

### Not yet production-ready
- [ ] Add session revocation and a complete security review before enabling external tools
- [ ] Complete approval payload binding, expiry, and audit semantics
- [ ] Typed tool registry and real tool execution after approval
- [ ] GitHub read-only integration and verified engineering workflows
- [ ] Usage budgets, token accounting, and cost limits
- [ ] Daily briefing, reminders, and weekly review
- [ ] Voice, calendar/email connectors, multi-user support

**Important:** This branch is under development. The existing production deployment has not been changed. No production deployment, paid service, or merge to `main` is authorised by this work.

---

## Quick start

```bash
git clone https://github.com/mrzulqarnainnadabo/agent-phone.git
cd agent-phone
cp .env.example .env
# Set APP_LOGIN_PASSWORD and SESSION_SECRET; add MODEL_API_KEY for real AI replies

docker compose up --build
```

- Frontend: http://localhost:3000  
- API docs: http://localhost:8000/docs  

### Manual

**Backend**
```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MODEL_API_KEY=sk-...
export APP_LOGIN_PASSWORD="your-long-owner-password"
export SESSION_SECRET="$(openssl rand -hex 32)"
python run.py
```

**Frontend**
```bash
cd client
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_APP_AUTH_TOKEN=dev-token-change-me \
npm run dev
```

---

## Try the approval loop

1. Open the app → **Approvals**
2. Tap **Simulate proposal**
3. See exact message payload → **Approve** or **Reject**
4. Badge count updates on the nav

Also: **Agents → + New**, **Goals → + New** → Goal Room → **Handoff**.

---

## Deploy

See **[docs/DEPLOY.md](docs/DEPLOY.md)** for Railway, Docker, and the public-demo safety checklist.

---

## Architecture

```
Phone (PWA)
    │
    ▼
Next.js 15 (mobile-first)
    │  Bearer token
    ▼
FastAPI
  ├── Agents + permissions + approval policies
  ├── Approvals inbox (propose → human decides)
  ├── Goals + handoffs (max 3 agents)
  ├── SQLite (volume-backed)
  └── OpenAI-compatible models
```

The model can only **propose**. The application decides permission and approval.

---

## Selling path

| Stage | Offer | Pricing idea |
|-------|--------|--------------|
| Individual | Hosted or self-hosted | $9–29 / month |
| Team / Org | Shared goals + audit trail | $49–199 / month |
| White-label | Brandable for NGOs / civic orgs | Custom |

Maps well to ISEYC, civic programmes, and small operational teams.

---

## License

MIT. Self-host, modify, and sell.

Inspiration: [Anil-matcha/open-dots](https://github.com/Anil-matcha/open-dots)
