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
  const [messages, setMessages] = useState([{ id: "welcome", role: "assistant" as const, content: "Welcome to Agent Phone.\n\nYour control room for trusted AI workers." }]);
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

function CreateGoalForm({ agents, onClose, onCreated }: { agents: Agent[]; onClose: () => void; onCreated: (goalId: string) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [selected, setSelected] = useState<{ agent_id: string; role: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function toggleAgent(id: string) {
    setSelected((prev) => {
      if (prev.find((s) => s.agent_id === id)) return prev.filter((s) => s.agent_id !== id);
      if (prev.length >= 3) return prev;
      return [...prev, { agent_id: id, role: "" }];
    });
  }

  async function create() {
    if (!title.trim()) return;
    setSaving(true); setError("");
    try {
      const goal = await api("/api/v1/goals", { method: "POST", body: JSON.stringify({ title: title.trim(), description: description.trim() }) });
      for (const s of selected) {
        await api(`/api/v1/goals/${goal.id}/agents`, { method: "POST", body: JSON.stringify({ agent_id: s.agent_id, role: s.role || "Member" }) });
      }
      onCreated(goal.id);
    } catch (e: any) { setError(e.message || "Failed"); } finally { setSaving(false); }
  }

  return (
    <div className="flex flex-col h-dvh max-w-lg mx-auto bg-gray-950 text-gray-100">
      <header className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <button onClick={onClose} className="text-sm text-gray-400">Cancel</button>
        <span className="text-sm font-medium">New Goal</span>
        <div className="w-12" />
      </header>
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        <div>
          <label className="text-sm text-gray-400">What is the goal?</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Prepare partnership proposal" className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-[15px] focus:outline-none focus:border-brand-500" />
        </div>
        <div>
          <label className="text-sm text-gray-400">Description (optional)</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} placeholder="One-page proposal for the partner" className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-[15px] focus:outline-none focus:border-brand-500" />
        </div>
        <div>
          <label className="text-sm text-gray-400">Add agents (max 3)</label>
          <div className="mt-2 space-y-2">
            {agents.map((a) => {
              const isSelected = selected.some((s) => s.agent_id === a.id);
              return (
                <button key={a.id} onClick={() => toggleAgent(a.id)} className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left ${isSelected ? "border-brand-500 bg-brand-600/10" : "border-gray-700 bg-gray-900"}`}>
                  <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-sm font-bold">{a.name[0]}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{a.name}</div>
                    <div className="text-xs text-gray-400">@{a.handle}</div>
                  </div>
                  {isSelected && <span className="text-brand-500 text-sm">✓</span>}
                </button>
              );
            })}
            {agents.length === 0 && <p className="text-sm text-gray-500">Create agents first.</p>}
          </div>
        </div>
        {error && <p className="text-red-400 text-sm">{error}</p>}
      </div>
      <div className="p-4 border-t border-gray-800">
        <button onClick={create} disabled={saving || !title.trim()} className="w-full py-3.5 rounded-2xl bg-brand-600 text-white font-medium disabled:opacity-40">{saving ? "Creating…" : "Create goal"}</button>
      </div>
    </div>
  );
}

function GoalRoom({ goalId, agents, onBack, onApprovalsChange }: { goalId: string; agents: Agent[]; onBack: () => void; onApprovalsChange: () => void }) {
  const [goal, setGoal] = useState<Goal | null>(null);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [roomTab, setRoomTab] = useState<"goal" | "work" | "approvals">("goal");
  const [loading, setLoading] = useState(false);
  const [showHandoff, setShowHandoff] = useState(false);

  useEffect(() => { load(); }, [goalId]);

  async function load() {
    try {
      const [g, h, e] = await Promise.all([api(`/api/v1/goals/${goalId}`), api(`/api/v1/goals/${goalId}/handoffs`), api(`/api/v1/goals/${goalId}/events`)]);
      setGoal(g); setHandoffs(h); setEvents(e);
    } catch (err) { console.error(err); }
  }

  async function transitionHandoff(id: string, action: "accept" | "complete" | "reject") {
    setLoading(true);
    try {
      await api(`/api/v1/handoffs/${id}/${action}`, { method: "POST", body: JSON.stringify({ note: action }) });
      await load();
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }

  function statusLine(): string {
    if (!goal) return "Loading…";
    if (goal.status === "completed") return "Goal completed.";
    const pendingH = handoffs.filter((h) => h.status === "pending");
    const acceptedH = handoffs.filter((h) => h.status === "accepted");
    if (pendingH.length > 0) {
      const h = pendingH[0];
      return `@${h.from_handle} handed “${h.title}” to @${h.to_handle} — waiting to accept.`;
    }
    if (acceptedH.length > 0) {
      const h = acceptedH[0];
      return `@${h.to_handle} is working on “${h.title}” — waiting for completion.`;
    }
    const agentNames = (goal.agents || []).map((a) => a.name).join(", ") || "No agents";
    return `${agentNames} · ${goal.status}`;
  }

  if (showHandoff && goal) return <CreateHandoffForm goal={goal} onClose={() => setShowHandoff(false)} onCreated={() => { setShowHandoff(false); load(); }} />;

  return (
    <div className="flex flex-col h-dvh max-w-lg mx-auto bg-gray-950 text-gray-100">
      <header className="px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-gray-400 text-sm">←</button>
          <div className="flex-1 min-w-0"><h1 className="text-base font-semibold truncate">{goal?.title || "Goal"}</h1></div>
          {goal?.status === "active" && <button onClick={() => setShowHandoff(true)} className="text-xs bg-brand-600 text-white px-2.5 py-1 rounded-full">Handoff</button>}
        </div>
        <p className="text-xs text-amber-300/90 mt-2 leading-relaxed">{statusLine()}</p>
      </header>
      <div className="flex border-b border-gray-800">
        {(["goal", "work", "approvals"] as const).map((t) => (
          <button key={t} onClick={() => setRoomTab(t)} className={`flex-1 py-2.5 text-sm capitalize ${roomTab === t ? "text-brand-500 border-b-2 border-brand-500" : "text-gray-500"}`}>{t}</button>
        ))}
      </div>
      <main className="flex-1 overflow-y-auto p-4 space-y-3">
        {roomTab === "goal" && goal && (
          <>
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 space-y-2">
              <div className="text-xs text-gray-500 uppercase tracking-wide">Objective</div>
              <p className="text-sm">{goal.description || "No description"}</p>
              <div className="flex items-center gap-2 pt-2">
                <span className={`text-xs px-2 py-0.5 rounded-full ${goal.status === "active" ? "bg-emerald-900/50 text-emerald-300" : "bg-gray-800 text-gray-400"}`}>{goal.status}</span>
              </div>
            </div>
            <div className="text-xs text-gray-500 uppercase tracking-wide pt-2">Agents</div>
            {(goal.agents || []).length === 0 && <p className="text-sm text-gray-500">No agents on this goal yet.</p>}
            {(goal.agents || []).map((a) => (
              <div key={a.agent_id} className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5">
                <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-sm font-bold">{a.name[0]}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium">{a.name}</div>
                  <div className="text-xs text-gray-400">@{a.handle} · {a.role || "Member"}</div>
                </div>
              </div>
            ))}
            {goal.status === "active" && (
              <button onClick={async () => { setLoading(true); try { await api(`/api/v1/goals/${goalId}/complete`, { method: "POST" }); await load(); } catch (e: any) { alert(e.message); } finally { setLoading(false); } }} disabled={loading} className="w-full mt-4 py-2.5 rounded-xl border border-gray-700 text-sm text-gray-300">Mark goal complete</button>
            )}
          </>
        )}
        {roomTab === "work" && (
          <>
            <div className="text-xs text-gray-500 uppercase tracking-wide">Handoffs & activity</div>
            {handoffs.length === 0 && events.length === 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 text-center">
                <p className="text-gray-400 text-sm">No work yet.</p>
                <p className="text-xs text-gray-500 mt-1">Create a handoff to move work between agents.</p>
              </div>
            )}
            {handoffs.map((h) => (
              <div key={h.id} className="bg-gray-900 border border-gray-800 rounded-2xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-xs text-gray-400">@{h.from_handle} → @{h.to_handle}</div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${h.status === "pending" ? "bg-amber-900/50 text-amber-300" : h.status === "accepted" ? "bg-blue-900/50 text-blue-300" : h.status === "completed" ? "bg-emerald-900/50 text-emerald-300" : "bg-gray-800 text-gray-400"}`}>{h.status}</span>
                </div>
                <div className="font-medium text-sm">{h.title}</div>
                <p className="text-sm text-gray-400">{h.instruction}</p>
                {h.context && <div className="text-xs text-gray-500 bg-gray-950 rounded-lg p-2 border border-gray-800">Context: {h.context}</div>}
                {h.status === "pending" && (
                  <div className="flex gap-2 pt-1">
                    <button onClick={() => transitionHandoff(h.id, "reject")} disabled={loading} className="flex-1 py-2 rounded-xl border border-gray-700 text-xs">Reject</button>
                    <button onClick={() => transitionHandoff(h.id, "accept")} disabled={loading} className="flex-1 py-2 rounded-xl bg-brand-600 text-white text-xs">Accept</button>
                  </div>
                )}
                {h.status === "accepted" && (
                  <button onClick={() => transitionHandoff(h.id, "complete")} disabled={loading} className="w-full py-2 rounded-xl bg-brand-600 text-white text-xs mt-1">Mark complete</button>
                )}
              </div>
            ))}
            {events.length > 0 && (
              <div className="pt-4">
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">Timeline</div>
                {events.slice(0, 15).map((e) => (
                  <div key={e.id} className="text-xs text-gray-500 py-1.5 border-b border-gray-900">
                    <span className="text-gray-400">{e.event_type}</span>
                    {e.payload?.title && <span> · {e.payload.title}</span>}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
        {roomTab === "approvals" && (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 text-center">
            <p className="text-gray-400 text-sm">Goal-scoped approvals appear here.</p>
            <p className="text-xs text-gray-500 mt-1">Global approvals are in the Approvals tab.</p>
          </div>
        )}
      </main>
    </div>
  );
}

function CreateHandoffForm({ goal, onClose, onCreated }: { goal: Goal; onClose: () => void; onCreated: () => void }) {
  const goalAgents = goal.agents || [];
  const [fromId, setFromId] = useState(goalAgents[0]?.agent_id || "");
  const [toId, setToId] = useState(goalAgents[1]?.agent_id || "");
  const [title, setTitle] = useState("");
  const [instruction, setInstruction] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function create() {
    if (!fromId || !toId || !title.trim() || !instruction.trim()) return;
    setSaving(true); setError("");
    try {
      await api(`/api/v1/goals/${goal.id}/handoffs`, { method: "POST", body: JSON.stringify({ from_agent_id: fromId, to_agent_id: toId, title: title.trim(), instruction: instruction.trim() }) });
      onCreated();
    } catch (e: any) { setError(e.message || "Failed"); } finally { setSaving(false); }
  }

  return (
    <div className="flex flex-col h-dvh max-w-lg mx-auto bg-gray-950 text-gray-100">
      <header className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <button onClick={onClose} className="text-sm text-gray-400">Cancel</button>
        <span className="text-sm font-medium">New Handoff</span>
        <div className="w-12" />
      </header>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <label className="text-sm text-gray-400">From</label>
          <select value={fromId} onChange={(e) => setFromId(e.target.value)} className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-[15px]">
            {goalAgents.map((a) => <option key={a.agent_id} value={a.agent_id}>@{a.handle} ({a.name})</option>)}
          </select>
        </div>
        <div>
          <label className="text-sm text-gray-400">To</label>
          <select value={toId} onChange={(e) => setToId(e.target.value)} className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-[15px]">
            {goalAgents.map((a) => <option key={a.agent_id} value={a.agent_id}>@{a.handle} ({a.name})</option>)}
          </select>
        </div>
        <div>
          <label className="text-sm text-gray-400">Title</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Turn research into proposal" className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-[15px] focus:outline-none focus:border-brand-500" />
        </div>
        <div>
          <label className="text-sm text-gray-400">Instruction</label>
          <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} rows={3} placeholder="Use the completed research to produce a one-page proposal." className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-[15px] focus:outline-none focus:border-brand-500" />
        </div>
        {error && <p className="text-red-400 text-sm">{error}</p>}
      </div>
      <div className="p-4 border-t border-gray-800">
        <button onClick={create} disabled={saving || !title.trim() || !instruction.trim() || fromId === toId} className="w-full py-3.5 rounded-2xl bg-brand-600 text-white font-medium disabled:opacity-40">{saving ? "Creating…" : "Create handoff"}</button>
      </div>
    </div>
  );
}

function CreateAgentWizard({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [handle, setHandle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [personality, setPersonality] = useState("Concise and practical");
  const [permissions, setPermissions] = useState<{ capability: string; level: string }[]>([
    { capability: "files", level: "read" }, { capability: "calendar", level: "draft" }, { capability: "messaging", level: "draft" },
  ]);
  const [approvalMode, setApprovalMode] = useState("ask_consequential");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function create() {
    setSaving(true); setError("");
    try {
      const cleanHandle = handle.replace(/^@/, "").toLowerCase();
      const agent = await api("/api/v1/agents", { method: "POST", body: JSON.stringify({ name, handle: cleanHandle, purpose, personality, approval_mode: approvalMode }) });
      await api(`/api/v1/agents/${agent.id}/permissions`, { method: "PUT", body: JSON.stringify({ permissions }) });
      onCreated();
    } catch (e: any) { setError(e.message || "Failed to create agent"); } finally { setSaving(false); }
  }

  return (
    <div className="flex flex-col h-dvh max-w-lg mx-auto bg-gray-950 text-gray-100">
      <header className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <button onClick={onClose} className="text-sm text-gray-400">Cancel</button>
        <span className="text-sm text-gray-400">Step {step} of 5</span>
        <div className="w-12" />
      </header>
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {step === 1 && (
          <>
            <h2 className="text-xl font-semibold">Create your agent</h2>
            <div>
              <label className="text-sm text-gray-400">What should I call it?</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Atlas" className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-[15px] focus:outline-none focus:border-brand-500" />
            </div>
            <div>
              <label className="text-sm text-gray-400">Handle</label>
              <div className="mt-1 flex items-center bg-gray-900 border border-gray-700 rounded-xl px-4 py-3">
                <span className="text-gray-500">@</span>
                <input value={handle} onChange={(e) => setHandle(e.target.value.replace(/^@/, "").toLowerCase())} placeholder="atlas" className="flex-1 bg-transparent focus:outline-none text-[15px] ml-1" />
              </div>
            </div>
          </>
        )}
        {step === 2 && (
          <>
            <h2 className="text-xl font-semibold">What is {name || "this agent"} for?</h2>
            <textarea value={purpose} onChange={(e) => setPurpose(e.target.value)} rows={3} placeholder="Research and organize project information" className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-[15px] focus:outline-none focus:border-brand-500" />
            <div className="flex flex-wrap gap-2">
              {["Research", "Planning", "Writing", "Operations", "Personal admin"].map((ex) => (
                <button key={ex} onClick={() => setPurpose(ex + " assistant")} className="text-xs px-3 py-1.5 rounded-full bg-gray-800 text-gray-300">{ex}</button>
              ))}
            </div>
          </>
        )}
        {step === 3 && (
          <>
            <h2 className="text-xl font-semibold">How should it work?</h2>
            <div className="space-y-2">
              {["Concise and practical", "Detailed and thorough", "Warm and conversational", "Formal and precise"].map((p) => (
                <button key={p} onClick={() => setPersonality(p)} className={`w-full text-left px-4 py-3 rounded-xl border ${personality === p ? "border-brand-500 bg-brand-600/10" : "border-gray-700 bg-gray-900"}`}>{p}</button>
              ))}
            </div>
          </>
        )}
        {step === 4 && (
          <>
            <h2 className="text-xl font-semibold">What can it access?</h2>
            <p className="text-sm text-gray-400">Read = inspect · Draft = prepare · Consequential = change something</p>
            {["files", "calendar", "messaging"].map((cap) => {
              const current = permissions.find((p) => p.capability === cap)?.level || "none";
              return (
                <div key={cap} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                  <div className="font-medium capitalize mb-2">{cap}</div>
                  <div className="flex gap-2">
                    {["none", "read", "draft"].map((lvl) => (
                      <button key={lvl} onClick={() => {
                        setPermissions((prev) => {
                          const rest = prev.filter((p) => p.capability !== cap);
                          if (lvl === "none") return rest;
                          return [...rest, { capability: cap, level: lvl }];
                        });
                      }} className={`flex-1 py-2 rounded-lg text-sm capitalize ${current === lvl ? "bg-brand-600 text-white" : "bg-gray-800 text-gray-400"}`}>{lvl}</button>
                    ))}
                  </div>
                </div>
              );
            })}
          </>
        )}
        {step === 5 && (
          <>
            <h2 className="text-xl font-semibold">When should it ask you?</h2>
            <div className="space-y-2">
              {[{ value: "ask_consequential", label: "Ask before consequential actions" }, { value: "always_ask", label: "Ask before every action" }, { value: "draft_only", label: "Draft only — never execute" }].map((opt) => (
                <button key={opt.value} onClick={() => setApprovalMode(opt.value)} className={`w-full text-left px-4 py-3 rounded-xl border ${approvalMode === opt.value ? "border-brand-500 bg-brand-600/10" : "border-gray-700 bg-gray-900"}`}>{opt.label}</button>
              ))}
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 mt-6 space-y-2">
              <div className="font-medium">{name || "Agent"} is ready</div>
              <div className="text-sm text-gray-400">{purpose}</div>
              <div className="text-xs text-gray-500 pt-2">{permissions.map((p) => `${p.capability}: ${p.level}`).join(" · ")}</div>
              <div className="text-xs text-gray-500">Approval: {approvalMode.replace(/_/g, " ")}</div>
            </div>
            {error && <p className="text-red-400 text-sm">{error}</p>}
          </>
        )}
      </div>
      <div className="p-4 border-t border-gray-800">
        {step < 5 ? (
          <button onClick={() => setStep(step + 1)} disabled={(step === 1 && (!name || !handle)) || (step === 2 && !purpose)} className="w-full py-3.5 rounded-2xl bg-brand-600 text-white font-medium disabled:opacity-40">Continue</button>
        ) : (
          <button onClick={create} disabled={saving} className="w-full py-3.5 rounded-2xl bg-brand-600 text-white font-medium disabled:opacity-40">{saving ? "Creating…" : "Create agent"}</button>
        )}
      </div>
    </div>
  );
}
