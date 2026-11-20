"use client";

import { FormEvent, useState } from "react";
import { setSessionToken } from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AuthScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `Login failed (${response.status})`);
      if (!data.access_token) throw new Error("The server did not issue a session.");
      setSessionToken(data.access_token);
      setPassword("");
      onAuthenticated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-dvh flex items-center justify-center bg-gray-950 px-5 text-gray-100">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-3xl border border-gray-800 bg-gray-900 p-6 shadow-2xl">
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-sky-400">Private workspace</p>
          <h1 className="text-2xl font-semibold tracking-tight">Agent Phone</h1>
          <p className="text-sm text-gray-400">Sign in to your personal operations assistant.</p>
        </div>
        {error && <div role="alert" className="rounded-xl border border-red-900 bg-red-950/50 px-3 py-2 text-sm text-red-200">{error}</div>}
        <label className="block space-y-2">
          <span className="text-sm text-gray-300">Owner password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
            className="w-full rounded-xl border border-gray-700 bg-gray-950 px-4 py-3 text-base outline-none focus:border-sky-500"
            placeholder="Enter your password"
          />
        </label>
        <button disabled={loading || !password} className="w-full rounded-xl bg-sky-600 py-3 text-sm font-semibold text-white disabled:opacity-40">
          {loading ? "Signing in…" : "Sign in"}
        </button>
        <p className="text-center text-[11px] text-gray-600">Sessions expire automatically. Your password stays on the server.</p>
      </form>
    </main>
  );
}
