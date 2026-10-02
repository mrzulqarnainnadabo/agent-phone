"use client";

import { useState, useEffect, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const AUTH_TOKEN = process.env.NEXT_PUBLIC_APP_AUTH_TOKEN || "dev-token-change-me";

type Tab = "home" | "agents" | "goals" | "approvals";
type Agent = { id: string; name: string; handle: string; purpose: string; personality?: string; status: string; approval_mode: string };
type Approval = { id: string; agent_id: string; title: string; description: string; proposed_output?: string; status: string; created_at: string };
type Goal = { id: string; title: string; description?: string; status: string; created_at: string; updated_at: string; agents?: GoalAgent[] };
type GoalAgent = { agent_id: string; name: string; handle: string; role: string; joined_at: string };
type Handoff = { id: string; goal_id: string; from_agent_id: string; from_handle: string; to_agent_id: string; to_handle: string; title: string; instruction: string; context?: string; status: string; created_at: string; completed_at?: string };
type Message = { id: string; role: "user" | "assistant"; content: string };

async function api(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${AUTH_TOKEN}`, ...(options.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("home");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [showCreateGoal, setShowCreateGoal] = useState(false);
  const [activeGoalId, setActiveGoalId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([{ id: "welcome", role: "assistant", content: "Welcome to Agent Phone.\n\nYour control room for trusted AI workers." }]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { loadAgents(); loadApprovals(); loadGoals(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function loadAgents() { try { setAgents(await api("/api/v1/agents")); } catch (e) { console.error(e); } }
  async function loadApprovals() {
    try {
      const [list, count] = await Promise.all([api("/api/v1/approvals?status=pending"), api("/api/v1/approvals/count")]);
      setApprovals(list); setPendingCount(count.pending || 0);
    } catch (e) { console.error(e); }
  }
  async function loadGoals() { try { setGoals(await api("/api/v1/goals")); } catch (e) { console.error(e); } }

  async function sendChat() {
    const text = input.trim();
    if (!text || chatLoading) return;
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", content: text }]);
    setInput(""); setChatLoading(true);
    try {
      const data = await api("/api/v1/chat", { method: "POST", body: JSON.stringify({ thread_id: threadId, message: text }) });
      setThreadId(data.thread_id);
      setMessages((m) => [...m, { id: data.message_id, role: "assistant", content: data.reply }]);
    } catch (err: any) {
      setMessages((m) => [...m, { id: `err-${Date.now()}`, role: "assistant", content: err.message }]);
    } finally { setChatLoading(false); }
  }

  async function decideApproval(id: string, action: "approve" | "reject") {
    setLoading(true);
    try {
      await api(`/api/v1/approvals/${id}/${action}`, { method: "POST", body: JSON.stringify({ note: action === "approve" ? "Approved" : "Rejected" }) });
      await loadApprovals();
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }

  async function simulateProposal() {
    setLoading(true);
    try {
      await api("/api/v1/approvals/demo", { method: "POST" });
      await loadApprovals();
    } catch (e: any) { alert(e.message || "Failed"); } finally { setLoading(false); }
  }

  if (showCreate) return <CreateAgentWizard onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); loadAgents(); setTab("agents"); }} />;
  if (showCreateGoal) return <CreateGoalForm agents={agents} onClose={() => setShowCreateGoal(false)} onCreated={(goalId) => { setShowCreateGoal(false); loadGoals(); setActiveGoalId(goalId); setTab("goals"); }} />;
  if (activeGoalId) return <GoalRoom goalId={activeGoalId} agents={agents} onBack={() => { setActiveGoalId(null); loadGoals(); }} onApprovalsChange={loadApprovals} />;

  return (
    <div className="flex flex-col h-dvh max-w-lg mx-auto bg-gray-950 text-gray-100">
      <main className="flex-1 overflow-y-auto">
        {tab === "home" && (
          <div className="flex flex-col h-full">
            <header className="px-4 py-3 border-b border-gray-800">
              <h1 className="text-lg font-semibold">Agent Phone</h1>
              <p className="text-xs text-gray-400">Control room</p>
            </header>
            <div className="flex-1 px-3 py-4 space-y-3 overflow-y-auto">
              {messages.map((msg) => (
                <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[15px] whitespace-pre-wrap ${msg.role === "user" ? "bg-brand-600 text-white rounded-br-md" : "bg-gray-800 rounded-bl-md"}`}>{msg.content}</div>
                </div>
              ))}
              {chatLoading && <div className="flex justify-start"><div className="bg-gray-800 rounded-2xl px-4 py-3 text-gray-400 text-sm">Thinking…</div></div>}
              <div ref={bottomRef} />
            </div>
            <div className="border-t border-gray-800 px-3 py-3">
              <div className="flex gap-2 items-end">
                <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } }} rows={1} placeholder="Message…" className="flex-1 resize-none bg-gray-900 border border-gray-700 rounded-2xl px-4 py-3 text-[15px] focus:outline-none focus:border-brand-500 max-h-28" />
                <button onClick={sendChat} disabled={chatLoading || !input.trim()} className="bg-brand-600 disabled:opacity-40 text-white rounded-full w-11 h-11 flex items-center justify-center shrink-0">↑</button>
              </div>
            </div>
          </div>
        )}

        {tab === "agents" && (
          <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h1 className="text-lg font-semibold">Agents</h1>
              <button onClick={() => setShowCreate(true)} className="bg-brand-600 text-white text-sm px-3 py-1.5 rounded-full font-medium">+ New</button>
            </div>
            {agents.length === 0 && <p className="text-gray-400 text-sm">No agents yet. Create your first one.</p>}
            {agents.map((a) => (
              <div key={a.id} className="bg-gray-900 border border-gray-800 rounded-2xl p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-brand-600 flex items-center justify-center font-bold text-sm">{a.name[0]}</div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium">{a.name}</div>
                    <div className="text-xs text-gray-400">@{a.handle}</div>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300">{a.status}</span>
                </div>
                <p className="text-sm text-gray-400 mt-2 line-clamp-2">{a.purpose}</p>
              </div>
            ))}
          </div>
        )}

        {tab === "goals" && (
          <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h1 className="text-lg font-semibold">Goals</h1>
              <button onClick={() => setShowCreateGoal(true)} className="bg-brand-600 text-white text-sm px-3 py-1.5 rounded-full font-medium">+ New</button>
            </div>
            {goals.length === 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 text-center">
                <p className="text-gray-400 text-sm">No goals yet.</p>
                <p className="text-xs text-gray-500 mt-1">Create a goal and add up to 3 agents.</p>
              </div>
            )}
            {goals.map((g) => (
              <button key={g.id} onClick={() => setActiveGoalId(g.id)} className="w-full text-left bg-gray-900 border border-gray-800 rounded-2xl p-4 active:bg-gray-800">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium truncate">{g.title}</div>
                  <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${g.status === "active" ? "bg-emerald-900/50 text-emerald-300" : g.status === "completed" ? "bg-blue-900/50 text-blue-300" : "bg-gray-800 text-gray-400"}`}>{g.status}</span>
                </div>
                {g.description && <p className="text-sm text-gray-400 mt-1 line-clamp-2">{g.description}</p>}
              </button>
            ))}
          </div>
        )}

        {tab === "approvals" && (
          <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h1 className="text-lg font-semibold">Approvals</h1>
              <button onClick={simulateProposal} disabled={loading} className="text-xs bg-gray-800 border border-gray-700 px-3 py-1.5 rounded-full text-gray-300">Simulate proposal</button>
            </div>
            {approvals.length === 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 text-center">
                <p className="text-gray-400 text-sm">No pending approvals</p>
                <p className="text-xs text-gray-500 mt-2">Tap Simulate proposal to create a sample agent request.</p>
              </div>
            )}
            {approvals.map((a) => (
              <div key={a.id} className="bg-gray-900 border border-gray-800 rounded-2xl p-4 space-y-3">
                <div className="text-xs text-amber-400 font-medium uppercase tracking-wide">Needs your approval</div>
                <div className="font-medium">{a.title}</div>
                <p className="text-sm text-gray-400">{a.description}</p>
                {a.proposed_output && (
                  <div className="bg-gray-950 rounded-xl p-3 text-sm text-gray-300 whitespace-pre-wrap border border-gray-800">{a.proposed_output}</div>
                )}
                <div className="flex gap-2 pt-1">
                  <button onClick={() => decideApproval(a.id, "reject")} disabled={loading} className="flex-1 py-2.5 rounded-xl border border-gray-700 text-sm font-medium">Reject</button>
                  <button onClick={() => decideApproval(a.id, "approve")} disabled={loading} className="flex-1 py-2.5 rounded-xl bg-brand-600 text-white text-sm font-medium">Approve</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <nav className="border-t border-gray-800 bg-gray-950 px-2 py-2 flex justify-around">
        {([{ id: "home", label: "Home" }, { id: "agents", label: "Agents" }, { id: "goals", label: "Goals" }, { id: "approvals", label: "Approvals" }] as const).map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} className={`relative flex flex-col items-center px-3 py-1.5 rounded-xl text-xs font-medium ${tab === t.id ? "text-brand-500" : "text-gray-500"}`}>
            <span className="text-lg leading-none mb-0.5">{t.id === "home" ? "⌂" : t.id === "agents" ? "◎" : t.id === "goals" ? "◇" : "✓"}</span>
            {t.label}
            {t.id === "approvals" && pendingCount > 0 && (
              <span className="absolute -top-0.5 right-1 bg-red-500 text-white text-[10px] w-4 h-4 rounded-full flex items-center justify-center">{pendingCount}</span>
            )}
          </button>
        ))}
      </nav>
    </div>
  );
}
