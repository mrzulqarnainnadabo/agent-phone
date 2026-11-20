"use client";

import { FormEvent, useEffect, useState } from "react";
import { expireSession, getSessionToken } from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Project = {
  id: string; name: string; description: string; status: string; priority: string;
  repository_url?: string | null; production_url?: string | null; task_count?: number;
};
type Task = {
  id: string; project_id?: string | null; title: string; description: string;
  status: "todo" | "in_progress" | "blocked" | "done" | "cancelled";
  priority: string; due_date?: string | null;
};
type ToolAudit = { id: string; thread_id: string; tool_name: string; arguments_json: string; outcome: string; created_at: string };
type Overview = {
  active_projects: number;
  tasks: Record<string, number>;
  priority_tasks: Task[];
  recent_checkpoints: { id: string; summary: string; next_action: string; blockers: string; created_at: string }[];
};

async function api(path: string, options: RequestInit = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getSessionToken()}`,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    if (response.status === 401) expireSession();
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

export default function WorkspacePanel() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [productionUrl, setProductionUrl] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [taskProject, setTaskProject] = useState("");
  const [taskPriority, setTaskPriority] = useState("normal");
  const [saving, setSaving] = useState(false);
  const [checkpointTaskId, setCheckpointTaskId] = useState<string | null>(null);
  const [checkpointSummary, setCheckpointSummary] = useState("");
  const [checkpointCompleted, setCheckpointCompleted] = useState("");
  const [checkpointNext, setCheckpointNext] = useState("");
  const [checkpointBlockers, setCheckpointBlockers] = useState("");
  const [operatingCharter, setOperatingCharter] = useState("");
  const [autonomyMode, setAutonomyMode] = useState("hybrid");
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [githubConfigured, setGithubConfigured] = useState(false);
  const [githubRepo, setGithubRepo] = useState("mrzulqarnainnadabo/agent-phone");
  const [githubSummary, setGithubSummary] = useState<any>(null);
  const [githubPulls, setGithubPulls] = useState<any[]>([]);
  const [githubRuns, setGithubRuns] = useState<any[]>([]);
  const [githubLoading, setGithubLoading] = useState(false);
  const [githubError, setGithubError] = useState("");
  const [toolAudit, setToolAudit] = useState<ToolAudit[]>([]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [projectList, taskList, summary, settings, githubStatus, audit] = await Promise.all([
        api("/api/v1/workspace/projects"),
        api("/api/v1/workspace/tasks?limit=50"),
        api("/api/v1/workspace/overview"),
        api("/api/v1/workspace/settings"),
        api("/api/v1/github/status"),
        api("/api/v1/tools/audit?limit=10"),
      ]);
      setProjects(projectList);
      setTasks(taskList);
      setOverview(summary);
      setOperatingCharter(settings.operating_charter?.value || "");
      setAutonomyMode(settings.autonomy_mode?.value || "hybrid");
      setGithubConfigured(Boolean(githubStatus.configured));
      setToolAudit(audit);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load workspace");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function inspectGitHubRepository() {
    const parts = githubRepo.trim().split("/");
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      setGithubError("Enter a repository as owner/name.");
      return;
    }
    setGithubLoading(true);
    setGithubError("");
    try {
      const base = `/api/v1/github/repos/${encodeURIComponent(parts[0])}/${encodeURIComponent(parts[1])}`;
      const [summary, pulls, runs] = await Promise.all([
        api(base),
        api(`${base}/pull-requests?state=open&limit=10`),
        api(`${base}/workflow-runs?limit=10`),
      ]);
      setGithubSummary(summary);
      setGithubPulls(pulls);
      setGithubRuns(runs);
    } catch (err) {
      setGithubError(err instanceof Error ? err.message : "Could not inspect repository");
      setGithubSummary(null); setGithubPulls([]); setGithubRuns([]);
    } finally { setGithubLoading(false); }
  }

  async function saveOperatingPreferences() {
    setSettingsSaving(true);
    setError("");
    try {
      await Promise.all([
        api("/api/v1/workspace/settings/operating_charter", {
          method: "PUT", body: JSON.stringify({ value: operatingCharter }),
        }),
        api("/api/v1/workspace/settings/autonomy_mode", {
          method: "PUT", body: JSON.stringify({ value: autonomyMode }),
        }),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save preferences");
    } finally { setSettingsSaving(false); }
  }

  async function createProject(event: FormEvent) {
    event.preventDefault();
    if (!projectName.trim()) return;
    setSaving(true);
    setError("");
    try {
      await api("/api/v1/workspace/projects", {
        method: "POST",
        body: JSON.stringify({
          name: projectName.trim(), description: projectDescription.trim(),
          repository_url: repositoryUrl.trim() || null,
          production_url: productionUrl.trim() || null,
        }),
      });
      setProjectName(""); setProjectDescription(""); setRepositoryUrl(""); setProductionUrl("");
      setShowProjectForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create project");
    } finally { setSaving(false); }
  }

  async function createTask(event: FormEvent) {
    event.preventDefault();
    if (!taskTitle.trim()) return;
    setSaving(true);
    setError("");
    try {
      await api("/api/v1/workspace/tasks", {
        method: "POST",
        body: JSON.stringify({
          title: taskTitle.trim(), description: taskDescription.trim(),
          project_id: taskProject || null, priority: taskPriority,
        }),
      });
      setTaskTitle(""); setTaskDescription(""); setTaskProject(""); setTaskPriority("normal");
      setShowTaskForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create task");
    } finally { setSaving(false); }
  }

  async function updateTask(task: Task, status: Task["status"]) {
    setError("");
    try {
      await api(`/api/v1/workspace/tasks/${task.id}`, {
        method: "PATCH", body: JSON.stringify({ status }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update task");
    }
  }

  async function saveCheckpoint(event: FormEvent, task: Task) {
    event.preventDefault();
    if (!checkpointSummary.trim()) return;
    setSaving(true);
    setError("");
    try {
      await api("/api/v1/workspace/checkpoints", {
        method: "POST",
        body: JSON.stringify({
          project_id: task.project_id || null,
          task_id: task.id,
          summary: checkpointSummary.trim(),
          completed_work: checkpointCompleted.trim(),
          next_action: checkpointNext.trim(),
          blockers: checkpointBlockers.trim(),
        }),
      });
      setCheckpointTaskId(null);
      setCheckpointSummary(""); setCheckpointCompleted(""); setCheckpointNext(""); setCheckpointBlockers("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save checkpoint");
    } finally { setSaving(false); }
  }

  const activeTasks = tasks.filter((task) => !["done", "cancelled"].includes(task.status));

  return (
    <div className="p-4 space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Work</h1>
          <p className="text-xs text-gray-500">Projects, priorities and resumable work</p>
        </div>
        <button onClick={load} disabled={loading} className="text-xs border border-gray-700 rounded-full px-3 py-1.5 text-gray-300">Refresh</button>
      </header>

      {error && <div role="alert" className="rounded-xl border border-red-900 bg-red-950/40 p-3 text-sm text-red-200">{error}</div>}

      <section className="grid grid-cols-3 gap-2">
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-3">
          <div className="text-xl font-semibold">{overview?.active_projects ?? "—"}</div>
          <div className="text-[11px] text-gray-500">Active projects</div>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-3">
          <div className="text-xl font-semibold">{overview?.tasks?.in_progress ?? "—"}</div>
          <div className="text-[11px] text-gray-500">In progress</div>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-3">
          <div className="text-xl font-semibold">{overview?.tasks?.blocked ?? "—"}</div>
          <div className="text-[11px] text-gray-500">Blocked</div>
        </div>
      </section>

      <section className="space-y-3 rounded-2xl border border-gray-800 bg-gray-900 p-3">
        <div>
          <h2 className="font-semibold">Operating preferences</h2>
          <p className="mt-1 text-xs text-gray-500">The rules your assistant should follow across projects.</p>
        </div>
        <label className="block space-y-1">
          <span className="text-xs text-gray-400">Autonomy</span>
          <select value={autonomyMode} onChange={(e) => setAutonomyMode(e.target.value)} className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm">
            <option value="assistant">Assistant — research and draft</option>
            <option value="hybrid">Hybrid — execute approved work</option>
            <option value="highly_autonomous">Highly autonomous — bounded routine work</option>
          </select>
        </label>
        <label className="block space-y-1">
          <span className="text-xs text-gray-400">Operating charter</span>
          <textarea value={operatingCharter} onChange={(e) => setOperatingCharter(e.target.value)} rows={5} maxLength={12000} className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm" />
        </label>
        <button onClick={saveOperatingPreferences} disabled={settingsSaving} className="w-full rounded-xl bg-sky-600 py-2.5 text-sm font-medium disabled:opacity-40">{settingsSaving ? "Saving…" : "Save operating preferences"}</button>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Projects</h2>
          <button onClick={() => setShowProjectForm((value) => !value)} className="text-xs rounded-full bg-sky-600 px-3 py-1.5 font-medium text-white">+ Project</button>
        </div>
        {showProjectForm && (
          <form onSubmit={createProject} className="space-y-2 rounded-2xl border border-gray-800 bg-gray-900 p-3">
            <input value={projectName} onChange={(e) => setProjectName(e.target.value)} required minLength={2} maxLength={120} placeholder="Project name" className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm" />
            <textarea value={projectDescription} onChange={(e) => setProjectDescription(e.target.value)} placeholder="What outcome are we working toward?" rows={2} className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm" />
            <input type="url" value={repositoryUrl} onChange={(e) => setRepositoryUrl(e.target.value)} placeholder="GitHub repository URL (optional)" className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm" />
            <input type="url" value={productionUrl} onChange={(e) => setProductionUrl(e.target.value)} placeholder="Live project URL (optional)" className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm" />
            <div className="flex gap-2">
              <button type="button" onClick={() => setShowProjectForm(false)} className="flex-1 rounded-xl border border-gray-700 py-2 text-sm">Cancel</button>
              <button disabled={saving || !projectName.trim()} className="flex-1 rounded-xl bg-sky-600 py-2 text-sm font-medium disabled:opacity-40">{saving ? "Saving…" : "Save project"}</button>
            </div>
          </form>
        )}
        {loading && <p className="text-sm text-gray-500">Loading workspace…</p>}
        {!loading && projects.length === 0 && <p className="rounded-xl border border-dashed border-gray-800 p-4 text-sm text-gray-500">No projects yet. Add the work you want your assistant to help manage.</p>}
        {projects.map((project) => (
          <article key={project.id} className="rounded-2xl border border-gray-800 bg-gray-900 p-3 space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="font-medium">{project.name}</h3>
                {project.description && <p className="mt-1 text-xs text-gray-400">{project.description}</p>}
              </div>
              <span className="shrink-0 rounded-full bg-gray-800 px-2 py-1 text-[10px] text-gray-400">{project.status}</span>
            </div>
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span>{project.task_count ?? 0} tasks</span>
              <span className="flex gap-3">
                {project.repository_url && <a href={project.repository_url} target="_blank" rel="noreferrer" className="text-sky-400 underline">Repository</a>}
                {project.production_url && <a href={project.production_url} target="_blank" rel="noreferrer" className="text-sky-400 underline">Live app</a>}
              </span>
            </div>
          </article>
        ))}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Tasks</h2>
          <button onClick={() => setShowTaskForm((value) => !value)} className="text-xs rounded-full bg-sky-600 px-3 py-1.5 font-medium text-white">+ Task</button>
        </div>
        {showTaskForm && (
          <form onSubmit={createTask} className="space-y-2 rounded-2xl border border-gray-800 bg-gray-900 p-3">
            <input value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} required minLength={2} maxLength={200} placeholder="What needs to be done?" className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm" />
            <textarea value={taskDescription} onChange={(e) => setTaskDescription(e.target.value)} placeholder="Details or completion criteria" rows={2} className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm" />
            <select value={taskProject} onChange={(e) => setTaskProject(e.target.value)} className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm">
              <option value="">Personal task (no project)</option>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
            <select value={taskPriority} onChange={(e) => setTaskPriority(e.target.value)} className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm">
              <option value="normal">Normal priority</option><option value="high">High priority</option><option value="urgent">Urgent</option><option value="low">Low priority</option>
            </select>
            <div className="flex gap-2">
              <button type="button" onClick={() => setShowTaskForm(false)} className="flex-1 rounded-xl border border-gray-700 py-2 text-sm">Cancel</button>
              <button disabled={saving || !taskTitle.trim()} className="flex-1 rounded-xl bg-sky-600 py-2 text-sm font-medium disabled:opacity-40">{saving ? "Saving…" : "Save task"}</button>
            </div>
          </form>
        )}
        {!loading && activeTasks.length === 0 && <p className="rounded-xl border border-dashed border-gray-800 p-4 text-sm text-gray-500">No active tasks. Capture your next action when you're ready.</p>}
        {activeTasks.map((task) => (
          <article key={task.id} className="rounded-2xl border border-gray-800 bg-gray-900 p-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="text-sm font-medium">{task.title}</h3>
                {task.description && <p className="mt-1 text-xs text-gray-500">{task.description}</p>}
              </div>
              <span className="shrink-0 text-[10px] uppercase tracking-wide text-gray-500">{task.priority}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-gray-500">{task.status.replace("_", " ")}</span>
              <div className="flex gap-2">
                {task.status === "todo" && <button onClick={() => updateTask(task, "in_progress")} className="rounded-lg border border-gray-700 px-2.5 py-1.5 text-xs">Start</button>}
                {task.status !== "blocked" && <button onClick={() => updateTask(task, "blocked")} className="rounded-lg border border-gray-700 px-2.5 py-1.5 text-xs">Block</button>}
                <button onClick={() => updateTask(task, "done")} className="rounded-lg bg-emerald-700 px-2.5 py-1.5 text-xs font-medium">Complete</button>
              </div>
            </div>
            <button onClick={() => { setCheckpointTaskId(checkpointTaskId === task.id ? null : task.id); setCheckpointSummary(""); }} className="text-xs text-sky-400 underline">Save progress checkpoint</button>
            {checkpointTaskId === task.id && (
              <form onSubmit={(event) => saveCheckpoint(event, task)} className="space-y-2 rounded-xl border border-gray-700 bg-gray-950 p-3">
                <input value={checkpointSummary} onChange={(e) => setCheckpointSummary(e.target.value)} required minLength={3} maxLength={2000} placeholder="What has been verified so far?" className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm" />
                <textarea value={checkpointCompleted} onChange={(e) => setCheckpointCompleted(e.target.value)} rows={2} placeholder="Completed work" className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm" />
                <textarea value={checkpointNext} onChange={(e) => setCheckpointNext(e.target.value)} rows={2} placeholder="Next action to resume" className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm" />
                <textarea value={checkpointBlockers} onChange={(e) => setCheckpointBlockers(e.target.value)} rows={2} placeholder="Blockers or unknowns (optional)" className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm" />
                <div className="flex gap-2">
                  <button type="button" onClick={() => setCheckpointTaskId(null)} className="flex-1 rounded-lg border border-gray-700 py-2 text-xs">Cancel</button>
                  <button disabled={saving || !checkpointSummary.trim()} className="flex-1 rounded-lg bg-sky-600 py-2 text-xs font-medium disabled:opacity-40">{saving ? "Saving…" : "Save checkpoint"}</button>
                </div>
              </form>
            )}
          </article>
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Recent checkpoints</h2>
        {!loading && (overview?.recent_checkpoints?.length ?? 0) === 0 && <p className="text-sm text-gray-500">No saved checkpoints yet. Record verified progress before switching tasks.</p>}
        {overview?.recent_checkpoints?.map((checkpoint) => (
          <article key={checkpoint.id} className="rounded-xl border border-gray-800 bg-gray-900 p-3 space-y-1">
            <p className="text-sm font-medium">{checkpoint.summary}</p>
            {checkpoint.next_action && <p className="text-xs text-gray-400">Next: {checkpoint.next_action}</p>}
            {checkpoint.blockers && <p className="text-xs text-amber-300">Blocker: {checkpoint.blockers}</p>}
            <p className="text-[10px] text-gray-600">{new Date(checkpoint.created_at).toLocaleString()}</p>
          </article>
        ))}
      </section>

      <section className="space-y-3 rounded-2xl border border-gray-800 bg-gray-900 p-3">
        <div>
          <h2 className="font-semibold">GitHub repository inspector</h2>
          <p className="mt-1 text-xs text-gray-500">Read-only repository, pull request and workflow information. No code changes or write access.</p>
        </div>
        <input value={githubRepo} onChange={(e) => setGithubRepo(e.target.value)} placeholder="owner/repository" className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm" />
        {!githubConfigured && <p className="text-xs text-amber-300">Not connected. Configure GITHUB_TOKEN and GITHUB_ALLOWED_REPOS on the API server to enable inspection.</p>}
        {githubError && <p role="alert" className="text-xs text-red-300">{githubError}</p>}
        <button onClick={inspectGitHubRepository} disabled={!githubConfigured || githubLoading} className="w-full rounded-xl border border-gray-700 py-2.5 text-sm disabled:opacity-40">{githubLoading ? "Inspecting…" : "Inspect repository"}</button>
        {githubSummary && (
          <div className="space-y-3 border-t border-gray-800 pt-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium text-sm">{githubSummary.full_name}</p>
                <p className="text-xs text-gray-500">{githubSummary.description || "No description"} · {githubSummary.language || "Language not detected"}</p>
              </div>
              <a href={githubSummary.html_url} target="_blank" rel="noreferrer" className="text-xs text-sky-400 underline">Open</a>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
              <span>Default branch: {githubSummary.default_branch}</span>
              <span>Open issues: {githubSummary.open_issues_count}</span>
            </div>
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-300">Open pull requests ({githubPulls.length})</p>
              {githubPulls.length === 0 && <p className="text-xs text-gray-500">No open pull requests.</p>}
              {githubPulls.map((pull) => <a key={pull.number} href={pull.html_url} target="_blank" rel="noreferrer" className="block rounded-lg border border-gray-800 p-2 text-xs"><span className="text-gray-500">#{pull.number}</span> {pull.title}</a>)}
            </div>
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-300">Recent workflow runs</p>
              {githubRuns.length === 0 && <p className="text-xs text-gray-500">No workflow runs returned.</p>}
              {githubRuns.slice(0, 5).map((run) => <a key={run.id} href={run.html_url} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-2 rounded-lg border border-gray-800 p-2 text-xs"><span className="truncate">{run.display_title || run.name}</span><span className={run.conclusion === "success" ? "text-emerald-400" : run.conclusion === "failure" ? "text-red-400" : "text-gray-400"}>{run.conclusion || run.status}</span></a>)}
            </div>
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="font-semibold">Tool activity</h2>
          <p className="mt-1 text-xs text-gray-500">Auditable history of read-only tool calls made by the assistant.</p>
        </div>
        {toolAudit.length === 0 && <p className="rounded-xl border border-dashed border-gray-800 p-3 text-xs text-gray-500">No tool calls have been recorded.</p>}
        {toolAudit.map((item) => (
          <article key={item.id} className="flex items-start justify-between gap-3 rounded-xl border border-gray-800 bg-gray-900 p-3">
            <div className="min-w-0">
              <p className="text-xs font-medium">{item.tool_name}</p>
              <p className="mt-1 truncate text-[10px] text-gray-500">{item.arguments_json}</p>
              <p className="mt-1 text-[10px] text-gray-600">{new Date(item.created_at).toLocaleString()}</p>
            </div>
            <span className={item.outcome === "success" ? "text-[10px] text-emerald-400" : "text-[10px] text-amber-300"}>{item.outcome}</span>
          </article>
        ))}
      </section>
    </div>
  );
}
