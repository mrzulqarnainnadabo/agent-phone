"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const AUTH_TOKEN = process.env.NEXT_PUBLIC_APP_AUTH_TOKEN || "dev-token-change-me";

type CryptoQuote = {
  asset_id: string;
  symbol: string;
  name: string;
  price_usd: number;
  as_of: string;
  source: string;
  source_url: string;
  change_24h_pct?: number;
  is_stale: boolean;
};
type WatchlistItem = {
  id: string;
  asset_id: string;
  symbol: string;
  name: string;
  created_at: string;
  quote?: CryptoQuote;
};
type AssetDetail = {
  asset_id: string;
  symbol: string;
  name: string;
  quote: CryptoQuote;
  notes?: string;
};

async function api(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${AUTH_TOKEN}`,
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail?.detail || err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export default function MarketsPanel() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [selected, setSelected] = useState<AssetDetail | null>(null);
  const [addId, setAddId] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const list: WatchlistItem[] = await api("/api/v1/crypto/watchlist");
      setWatchlist(list);
      setStale(list.some((i) => i.quote?.is_stale));
    } catch (e: any) {
      setError(e.message || "Failed to load markets");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function add() {
    const id = addId.trim().toLowerCase();
    if (!id) return;
    setLoading(true);
    setError("");
    try {
      await api("/api/v1/crypto/watchlist", {
        method: "POST",
        body: JSON.stringify({ asset_id: id }),
      });
      setAddId("");
      await load();
    } catch (e: any) {
      setError(typeof e.message === "string" ? e.message : "Failed to add");
      setLoading(false);
    }
  }

  async function openAsset(assetId: string) {
    setLoading(true);
    setError("");
    try {
      const detail: AssetDetail = await api(`/api/v1/crypto/assets/${assetId}`);
      setSelected(detail);
    } catch (e: any) {
      setError(e.message || "Failed to load asset");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Markets</h1>
          <p className="text-xs text-gray-500">Read-only research. Not financial advice.</p>
        </div>
        <button onClick={load} disabled={loading} className="text-xs bg-gray-800 border border-gray-700 px-3 py-1.5 rounded-full text-gray-300">
          Retry
        </button>
      </div>
      {stale && (
        <div className="bg-amber-950/40 border border-amber-800 text-amber-200 text-xs rounded-xl px-3 py-2">
          Some quotes may be stale. Tap Retry to refresh.
        </div>
      )}
      {error && (
        <div className="bg-red-950/40 border border-red-800 text-red-200 text-xs rounded-xl px-3 py-2">{error}</div>
      )}
      <div className="flex gap-2">
        <input value={addId} onChange={(e) => setAddId(e.target.value)} placeholder="Asset id (bitcoin, ethereum, solana)" className="flex-1 bg-gray-900 border border-gray-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-sky-500" />
        <button onClick={add} disabled={loading || !addId.trim()} className="bg-sky-600 disabled:opacity-40 text-white text-sm px-3 py-2 rounded-xl font-medium">
          Add
        </button>
      </div>
      {loading && <p className="text-sm text-gray-400">Loading…</p>}
      {!loading && watchlist.length === 0 && !error && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 text-center">
          <p className="text-gray-400 text-sm">Watchlist empty</p>
          <p className="text-xs text-gray-500 mt-1">Add bitcoin, ethereum, or solana (fixture mode).</p>
        </div>
      )}
      {watchlist.map((item) => (
        <button key={item.id} onClick={() => openAsset(item.asset_id)} className="w-full text-left bg-gray-900 border border-gray-800 rounded-2xl p-4 active:bg-gray-800">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="font-medium">{item.name} <span className="text-gray-500 text-xs">{item.symbol}</span></div>
              <div className="text-xs text-gray-500">{item.quote?.source || "—"}{item.quote?.is_stale ? " · stale" : ""}</div>
            </div>
            <div className="text-right">
              <div className="font-medium">{item.quote ? `$${item.quote.price_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—"}</div>
              {item.quote?.change_24h_pct != null && (
                <div className={`text-xs ${item.quote.change_24h_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>{item.quote.change_24h_pct.toFixed(2)}%</div>
              )}
            </div>
          </div>
        </button>
      ))}
      {selected && (
        <div className="bg-gray-900 border border-gray-700 rounded-2xl p-4 space-y-2">
          <div className="flex justify-between items-start">
            <div>
              <div className="font-semibold">{selected.name}</div>
              <div className="text-xs text-gray-400">{selected.symbol} · {selected.quote.source}</div>
            </div>
            <button onClick={() => setSelected(null)} className="text-xs text-gray-400">Close</button>
          </div>
          <div className="text-2xl font-semibold">${selected.quote.price_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
          <div className="text-xs text-gray-500">As of {new Date(selected.quote.as_of).toLocaleString()}{selected.quote.is_stale ? " · STALE" : ""}</div>
          <a href={selected.quote.source_url} target="_blank" rel="noreferrer" className="text-xs text-sky-500 underline break-all">{selected.quote.source_url}</a>
          {selected.notes && <p className="text-xs text-gray-400">{selected.notes}</p>}
          <p className="text-[11px] text-gray-600">Not financial advice. No trading from this app.</p>
        </div>
      )}
    </div>
  );
}
