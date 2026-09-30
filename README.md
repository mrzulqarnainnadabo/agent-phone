# Agent Phone

**Mobile-first AI agent workspace you can sell.**

A clean, installable phone experience (PWA) for iOS (iPhone XR and above) and Android.  
Built for individuals and organizations who want personal AI agents with clear control — without depending on OpenAI Dots or heavy cloud lock-in.

---

## Current status (v0.2)

- [x] Product repo & vision
- [x] Mobile-first Next.js 15 + Tailwind chat UI
- [x] PWA manifest (Add to Home Screen)
- [x] FastAPI backend with real OpenAI-compatible model calls
- [x] SQLite persistence (conversations survive restarts)
- [x] Simple Bearer token auth
- [x] Docker Compose
- [ ] Streaming responses
- [ ] Approval UI for higher-risk actions
- [ ] Notion / Google connectors
- [ ] Multi-user / org isolation
- [ ] Capacitor hybrid for App Store / Play Store

---

## Quick start

### Requirements
- Node.js 20+
- Python 3.11+
- Docker (recommended)
- An OpenAI-compatible API key (OpenAI, OpenRouter, Groq, etc.)

```bash
git clone https://github.com/mrzulqarnainnadabo/agent-phone.git
cd agent-phone
cp .env.example .env
# edit .env → set MODEL_API_KEY and APP_AUTH_TOKEN
```

### Docker (easiest)

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000/docs

### Manual

**Backend**
```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MODEL_API_KEY="sk-..."
export MODEL_API_BASE_URL="https://api.openai.com/v1"
export APP_AUTH_TOKEN="dev-token-change-me"
python run.py
```

**Frontend**
```bash
cd client
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_APP_AUTH_TOKEN=dev-token-change-me npm run dev
```

Open on your phone (same Wi-Fi) or use a tunnel (ngrok / Cloudflare Tunnel).

---

## Phone install (PWA)

1. Open the public URL in Safari (iOS) or Chrome (Android)
2. Add to Home Screen
3. It opens full-screen like a native app

Works on iPhone XR and above + modern Android.

---

## Best next steps (in order)

1. **Get real replies working** ← you are here  
   Set `MODEL_API_KEY` + `MODEL_API_BASE_URL` and test on phone.

2. **Deploy once**  
   Railway or Render (see `docs/DEPLOY.md`). Get a public HTTPS URL so you can install the PWA properly.

3. **Streaming**  
   Make replies appear token-by-token for better phone UX.

4. **Personas**  
   Let users create named agents with different system prompts.

5. **Approval gates**  
   Higher-risk actions pause for confirmation (key for selling to orgs).

6. **Multi-tenant**  
   Orgs + users so you can charge.

7. **Connectors**  
   Notion, Google, later WhatsApp-style bridges.

8. **Capacitor**  
   Real App Store / Play Store builds when the core is solid.

---

## Selling path

| Stage | What you sell | Pricing idea |
|-------|---------------|--------------|
| Individual | Hosted or self-hosted Agent Phone | $9–29 / month |
| Team / Org | Multi-user + branding + shared agents | $49–199 / month |
| White-label | Brandable instance for NGOs, civic orgs, companies | Custom |

Your ISEYC / civic / Hubil work maps very well to organizational use cases.

---

## Architecture

```
Phone (PWA)
    │
    ▼
Next.js 15 (mobile-first)
    │  HTTP + Bearer token
    ▼
FastAPI
  ├── SQLite
  ├── OpenAI-compatible model adapter
  └── (next) Approval gateway + connectors
```

Deploy anywhere: Railway, Render, Fly.io, VPS, Docker. No forced Vercel + Supabase.

---

## License

MIT. You can self-host, modify, and sell.

Inspiration: [Anil-matcha/open-dots](https://github.com/Anil-matcha/open-dots)
