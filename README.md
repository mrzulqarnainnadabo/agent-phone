# Agent Phone

**A phone-first control room for trusted AI workers.**

Installable PWA for iOS (iPhone XR+) and Android.  
Agents have clear roles, limited access, visible work, and must ask before consequential actions.

Built to sell to individuals and organizations — without Vercel/Supabase lock-in.

---

## Current status (v0.8)

- [x] Mobile-first Next.js 15 PWA (Add to Home Screen)
- [x] FastAPI + SQLite + Bearer auth
- [x] Agent identity (name, handle, purpose, personality)
- [x] Permissions (read / draft / consequential)
- [x] Approval policies + inbox (approve / reject)
- [x] **Simulate proposal** for testing the approval loop
- [x] Goals + max 3 agents per goal
- [x] Explicit handoffs (create / accept / complete / reject)
- [x] Goal Room UI with status line (Manus guidance)
- [x] Docker Compose + persistent volume
- [x] `/health` + `/ready`
- [x] Railway / self-host deploy docs
- [ ] Streaming model replies
- [ ] Real tool execution after approval
- [ ] Notion / calendar connectors
- [ ] Multi-user / org isolation
- [ ] Capacitor native shells

---

## Quick start

```bash
git clone https://github.com/mrzulqarnainnadabo/agent-phone.git
cd agent-phone
cp .env.example .env
# Set MODEL_API_KEY and APP_AUTH_TOKEN

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
export APP_AUTH_TOKEN=dev-token-change-me
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
