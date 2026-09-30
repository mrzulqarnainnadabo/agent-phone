# Deploy Agent Phone

## Railway (recommended simple alternative to Vercel)

1. Create a new project on Railway.
2. Add two services from this repo:
   - `server/` → Python service, start command `python run.py`
   - `client/` → Node service, build `npm run build`, start `npm start`
3. Set environment variables from `.env.example`.
4. Point `NEXT_PUBLIC_API_URL` to the public API URL Railway gives you.
5. Enable public networking on both services.

## Render

Same idea: one Web Service for the FastAPI backend, one Static Site or Web Service for the Next.js frontend.

## Self-host (Docker)

```bash
cp .env.example .env
# edit .env with real keys
docker compose up -d --build
```

## Phone install

After you have a public HTTPS URL:

- iOS Safari → Share → Add to Home Screen
- Android Chrome → Menu → Add to Home screen / Install app

It will open full-screen without browser chrome.
