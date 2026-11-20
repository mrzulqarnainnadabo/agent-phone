"""Password login and short-lived signed bearer sessions for the single-owner PWA."""
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core_helpers import (
    APP_LOGIN_PASSWORD,
    SESSION_SECRET,
    SESSION_TTL_SECONDS,
    create_session_token,
    get_db,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=1024)


def _client_key(request: Request) -> str:
    address = request.client.host if request.client else "unknown"
    return hmac.new(SESSION_SECRET.encode("utf-8"), address.encode("utf-8"), hashlib.sha256).hexdigest()


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    if (
        len(APP_LOGIN_PASSWORD) < 12
        or len(SESSION_SECRET) < 32
        or APP_LOGIN_PASSWORD in {"change-me", "change-me-to-a-long-random-string"}
        or SESSION_SECRET in {"change-me", "change-me-to-a-long-random-string"}
    ):
        raise HTTPException(503, "Owner login is not configured securely")

    db = await get_db()
    try:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_login_attempts (
                client_key TEXT PRIMARY KEY,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                window_started_at REAL NOT NULL,
                blocked_until REAL
            )
            """
        )
        now = time.time()
        key = _client_key(request)
        row = await (await db.execute(
            "SELECT failed_attempts, window_started_at, blocked_until FROM auth_login_attempts WHERE client_key=?",
            (key,),
        )).fetchone()

        if row and row["blocked_until"] and row["blocked_until"] > now:
            raise HTTPException(429, "Too many login attempts. Try again later.")

        if not hmac.compare_digest(body.password, APP_LOGIN_PASSWORD):
            failures = 1
            window_start = now
            if row and now - row["window_started_at"] < 900:
                failures = row["failed_attempts"] + 1
                window_start = row["window_started_at"]
            blocked_until = now + 900 if failures >= 5 else None
            await db.execute(
                """
                INSERT INTO auth_login_attempts (client_key, failed_attempts, window_started_at, blocked_until)
                VALUES (?,?,?,?)
                ON CONFLICT(client_key) DO UPDATE SET
                    failed_attempts=excluded.failed_attempts,
                    window_started_at=excluded.window_started_at,
                    blocked_until=excluded.blocked_until
                """,
                (key, failures, window_start, blocked_until),
            )
            await db.commit()
            raise HTTPException(401, "Incorrect password")

        await db.execute("DELETE FROM auth_login_attempts WHERE client_key=?", (key,))
        await db.commit()
    finally:
        await db.close()

    token = create_session_token()
    response.headers["Cache-Control"] = "no-store"
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": SESSION_TTL_SECONDS,
    }
