# Agent Phone

**Mobile-first AI agent workspace you can sell.**

A clean, installable phone experience (PWA + future hybrid) for iOS (iPhone XR and above) and Android.  
Built for individuals and organizations who want personal AI agents with tools, approvals, and clear control — without depending on OpenAI Dots or heavy cloud lock-in.

Inspired by the open-source Open Dots project, but redesigned from the ground up for **phone-first use**, easy self-hosting, and commercial packaging.

---

## Why this exists

- OpenAI Dots (and similar products) are powerful but locked to specific plans and regions.
- Most open-source agent UIs are desktop-first.
- Organizations and serious builders need something they can **install on phones**, control, brand, and sell.

Agent Phone focuses on:

1. Excellent mobile chat + agent experience
2. Explicit approval gates for higher-risk actions
3. Simple self-host or managed deployment
4. Clear path to multi-tenant / white-label for organizations
5. Integration with tools people already use (Notion, Google, WhatsApp-style messaging later)

---

## Current status (v0.1 — foundation)

- [x] Product repo & vision
- [x] Mobile-first Next.js 15 + Tailwind foundation
- [x] PWA manifest & installability groundwork
- [x] Simple FastAPI backend skeleton (chat + auth placeholder)
- [x] Docker Compose for one-command local + production-style deploy
- [ ] Full chat streaming + agent personas
- [ ] Approval UI
- [ ] Notion / Google / basic connectors
- [ ] Multi-user / org isolation
- [ ] Capacitor hybrid build for App Store / Play Store (Phase 2)

---

## Quick start (local)

### Requirements
- Node.js 20+
- Python 3.11+
- Docker (recommended)

```bash
git clone https://github.com/mrzulqarnainnadabo/agent-phone.git
cd agent-phone
```

### Option A — Docker (easiest)

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

### Option B — Manual

**Backend**
```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MODEL_API_KEY="your_key"
export MODEL_API_BASE_URL="https://api.openai.com/v1"   # or any compatible endpoint
python run.py
```

**Frontend**
```bash
cd client
npm install
npm run dev
```

Open http://localhost:3000 on your phone (same network) or use a tunnel.

---

## Phone install (PWA)

Once deployed (or via tunnel):

1. Open the URL in Safari (iOS) or Chrome (Android)
2. “Add to Home Screen”
3. It launches full-screen like a native app

This already works on iPhone XR and above and modern Android.

---

## Architecture (intentionally simple)

```
Phone (PWA / later Capacitor)
        │
        ▼
Next.js 15 (mobile-first UI)
        │  HTTP + SSE
        ▼
FastAPI (Python)
  ├── SQLite (or Postgres later)
  ├── Model provider adapter
  ├── Approval gateway
  └── Tool connectors (Notion, etc.)
```

We deliberately avoid heavy Vercel + Supabase coupling so you can deploy anywhere:
- Railway
- Render
- Fly.io
- Your own VPS
- Docker on a customer’s server

---

## Selling path

| Stage | What you sell | Pricing idea |
|-------|---------------|--------------|
| Individual | Hosted or self-hosted Agent Phone | $9–29 / month |
| Team / Org | Multi-user + branding + shared agents | $49–199 / month |
| White-label | Full brandable instance for NGOs, civic orgs, companies | Custom |

Your existing strengths (ISEYC, civic systems, clear communication style, Hubil diagnostics) map extremely well to organizational use cases.

---

## Roadmap to “ready for deployment”

### Phase 1 — Core usable product (this week)
- Solid mobile chat UI
- Streaming responses
- Persona / system prompt management
- Basic approval cards
- Secure auth (token or magic link)
- Docker production config
- One-click deploy docs for Railway / Render

### Phase 2 — Sellable
- Multi-tenant (orgs + users)
- Billing (Stripe)
- Notion knowledge base connector
- WhatsApp / messaging bridge (optional)
- Admin dashboard

### Phase 3 — Native distribution
- Capacitor or Expo wrapper
- App Store + Google Play listings
- Push notifications

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MODEL_API_KEY` | Yes | Your LLM provider key |
| `MODEL_API_BASE_URL` | Yes | Compatible API base (OpenAI, OpenRouter, etc.) |
| `APP_AUTH_TOKEN` | Recommended | Owner / admin token |
| `DATA_DIR` | No | Where SQLite + secrets live (default `./data`) |
| `NEXT_PUBLIC_API_URL` | Yes (prod) | Public URL of the API |

---

## License

MIT — same spirit as the original Open Dots work.  
You can self-host, modify, and sell.

---

## Credits

Core inspiration and architecture patterns drawn from the excellent open-source project  
[Anil-matcha/open-dots](https://github.com/Anil-matcha/open-dots).

Agent Phone is an independent product focused on mobile experience and commercial readiness.

---

**Next actions being executed in this repo:**  
Mobile UI foundation → backend chat skeleton → Docker → first deployable build.
