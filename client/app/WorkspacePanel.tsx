"use client";

import { FormEvent, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const AUTH_TOKEN = process.env.NEXT_PUBLIC_APP_AUTH_TOKEN || "dev-token-change-me";

type Project = {
  id: string; name: string; description: string; status: string; priority: string;
  repository_url?: string | null; production_url?: string | null; task_count?: number;
};
type Task = {
  id: string; project_id?: string | null; title: string; description: string;
  status: "todo" | "in_progress" | "blocked" | "done" | "cancelled";
  priority: string; due_date?: string | null;
};
type Overview = {
  active_projects: number;
  tasks: Record<string, number>;
  priority_tasks: Task[];
};

async function api(path: string, options: RequestInit = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${AUTH_TOKEN}`,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
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

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [projectList, taskList, summary] = await Promise.all([
        api("/api/v1/workspace/projects"),
        api("/api/v1/workspace/tasks?limit=50"),
        api("/api/v1/workspace/overview"),
      ]);
      setProjects(projectList);
      setTasks(taskList);
      setOverview(summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load workspace");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

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
          </article>
        ))}
      </section>
    </div>
  );
}
