# Agent Phone — Personal Operations Implementation Plan

**Target operating model:** Hybrid autonomy  
**Primary responsibilities:** Personal productivity and project execution, equally  
**Infrastructure:** Preserve current Netlify + existing API hosting initially  
**Deployment policy:** No production deployment without explicit founder approval  
**Cost policy:** No new paid service, subscription, database, model provider, or hosting commitment without explicit approval  
**Implementation branch:** `feat/personal-ops-foundation`  
**Baseline:** `main` at `4a5a1b110e1477de1b4f6955a85c8f0450328809` (2026-10-03)

## 1. Product outcome

Turn Agent Phone from an agent/goal/approval prototype into a dependable personal operations workspace. The user should be able to issue natural-language work instructions from a phone, resume work from verified checkpoints, manage personal priorities and projects, and delegate bounded tasks to specialised workers. The user remains the final decision-maker for consequential actions.

The product is a single-user personal system first. Do not introduce multi-tenant complexity until the single-user security and workflow are proven.

## 2. Evidence-based baseline

Repository inspection found:

- Next.js 15 PWA frontend in `client/`; FastAPI backend in `server/`.
- SQLite persistence in `server/app/core_helpers.py`; existing entities include threads/messages, agents/permissions/policies, approvals, goals, handoffs, and goal events.
- OpenAI-compatible chat call exists, but is a basic non-streaming request. Missing API key returns a placeholder string; model errors are converted into assistant text rather than structured failures.
- Chat accepts client-provided system prompt and model, persists conversation messages, but has no first-class personal operating charter, project context, task/checkpoint model, tool registry, or execution runtime.
- Approval endpoints currently update rows without verifying that the target exists and is pending; approval does not execute a bound, immutable action.
- Core API has no regression tests. Existing tests focus on crypto schemas/provider only.
- Shared bearer token is injected into browser code via `NEXT_PUBLIC_APP_AUTH_TOKEN`. This is not a safe boundary for a public browser application once powerful tools are enabled.
- Current main has no GitHub Actions workflows. No recent workflow runs were found.
- Frontend Dockerfile copies `.next/standalone`, while `next.config.mjs` does not enable standalone output.
- Crypto intelligence is a read-only module with fixture data by default. Preserve it; do not prioritise trading or financial automation.

## 3. Non-negotiable engineering rules

1. Preserve the existing working PWA, FastAPI API, SQLite data, agent/goal/handoff workflows, and read-only crypto module.
2. No production deployment, merge to main, destructive migration, or external communication without explicit approval.
3. No new paid services or recurring commitments without explicit approval.
4. No secrets in Git, browser bundles, logs, model prompts, or tool results.
5. Treat all model output and external content as untrusted proposals, never as authority.
6. Every tool call must pass server-side capability checks; model-generated arguments must be validated.
7. Human approval must bind to an immutable action payload/hash, expire, be single-use, and be revalidated at execution.
8. Distinguish drafted, approved, executed, verified, deployed, and production-ready states.
9. Every long-running task must have durable status, progress events, cancellation, bounded retries/timeouts, and a resumable checkpoint.
10. Tests and source evidence must support completion claims.

## 4. Implementation stages

### Stage 0 — Repository baseline and safety rails
- Establish automated backend tests and frontend production build checks in GitHub Actions.
- Record architecture, risks, decisions, and acceptance criteria.
- Verify existing tests/build before changing core behaviour.
- Keep workflow CI-only; it must never deploy.

**Exit criteria:** CI runs on pull requests and branch pushes; backend tests and frontend build produce visible results; no deployment job exists.

### Stage 1 — Personal workspace and durable memory
- Add a project registry separate from existing agent goals.
- Add actionable tasks with status, priority, due date, project association, and owner/agent assignment.
- Add durable checkpoints/handoffs with summary, completed work, next action, blockers, evidence links, and timestamps.
- Add personal operating charter and user preferences as editable structured settings.
- Add project links (repository, production URL, documentation) and decision records.
- Add daily briefing and weekly review views based on stored tasks and checkpoints.
- Use SQLite migrations that preserve existing records; add indexes and tests.

**Exit criteria:** A user can create/manage projects and tasks, record decisions/checkpoints, and resume work after a restart without losing context.

### Stage 2 — Secure single-user access and action governance
- [x] Replace browser-exposed shared API token with password login and short-lived HMAC-signed owner sessions; token is stored in sessionStorage, not in build-time configuration.
- [x] Add SQLite-backed login-attempt tracking and rate-limit repeated failed password attempts.
- [x] Add server-side session revocation on sign-out; revoked token hashes are stored server-side and checked on protected requests.
- [ ] Complete XSS/sessionStorage review and enforce a stricter Content Security Policy before enabling privileged tools.
- [x] Keep owner password, session signing secret, and provider credentials server-side only.
- Add CSRF protection where cookie sessions are used, secure cookie flags, rate limits, and security headers.
- Harden approval lifecycle: validate pending state, action type/level, actor, expiry, immutable payload hash, and single-use execution.
- Separate read, draft, reversible, and consequential capabilities.
- Require explicit approval for outbound communication, merges to protected branches, deploys, purchases, destructive actions, and financial activity.
- Do not enable real external actions until this stage passes security tests.

**Exit criteria:** No privileged credential in client bundle; unauthorized requests fail; approvals cannot be replayed or altered; all sensitive actions are audited.

### Stage 3 — Model adapter, orchestration, and controlled tool runtime
- Keep a provider-independent model adapter; configure provider/model server-side with safe allowlists.
- Add cost/usage accounting, request budgets, timeouts, token caps, and graceful failure handling.
- Add a central orchestrator with a small number of role profiles: Research, Engineering, Operations, Learning, Communications, and QA. These are instruction/tool profiles, not separate paid model subscriptions.
- [x] Add typed GitHub read-only tool schemas, exact repository allowlists, argument validation, bounded tool rounds/calls, and structured results.
- [x] Add a tool audit record for each read-only model tool call.
- [ ] Add idempotency and write-action execution only after full security review.
- [x] Add read-only GitHub inspection endpoints (repository metadata, pull requests, workflow runs, trees, and text files), protected by server-side token and exact repository allowlist.
- [x] Add a mobile repository inspector in the Work tab.
- [x] Connect bounded model-driven read-only GitHub tool calls to chat. No GitHub write scopes or write endpoints are implemented.
- Add model-driven tool calling over the read-only registry and project/task operations.
- Add draft-only code change preparation; create branches/PRs only after capability and approval policy allows it.
- Add resumable execution jobs and progress updates.
- Model may propose a tool call; the server authorises and executes it. Never trust model claims as evidence.

**Exit criteria:** A natural-language request can be planned, delegated, executed through approved tools, and reported with verifiable evidence; tool permissions are enforced server-side.

### Stage 4 — Personal productivity workflows
- Daily plan, task capture, priorities, follow-up reminders, meeting preparation, and weekly review.
- Project health summaries with blockers, next actions, last verified activity, and links to source records.
- Draft professional correspondence and reports; sending requires approval.
- Learning mode that explains code and decisions using current project context.
- Keep schedules and notifications opt-in and bounded.

**Exit criteria:** Daily and weekly workflows use real persisted records and can be corrected by the user.

### Stage 5 — Integrations and optional advanced capabilities
- GitHub first; then local files/documents and optional calendar/email connectors.
- Read-only integrations before write capabilities.
- Voice interface and local-model support are optional, only after the core experience is stable.
- Multi-user/team isolation is deferred until there is a genuine need.

**Exit criteria:** Each integration has documented scopes, user consent, revocation, tests, audit logs, and no new paid dependency without approval.

## 5. Proposed low-cost architecture

- Frontend: existing Next.js PWA.
- API: existing FastAPI service.
- Storage: existing SQLite on the existing persistent disk/volume; migrations only. Do not switch database.
- Background work: begin with SQLite-backed jobs and a bounded worker loop; no paid queue.
- Model: provider adapter using existing configured API if already available; optional local inference exploration. Do not assume ChatGPT subscription includes API usage.
- Tools: typed internal registry, starting with GitHub read-only access; never place GitHub credentials in frontend.
- CI: GitHub Actions for tests/build only.
- Hosting: keep current deployment configuration until separately reviewed and approved.

## 6. Immediate security and reliability blockers

- Session token is held in browser sessionStorage; enforce a strong CSP and complete XSS review before privileged tools.
- Missing tests for core API, approval state transitions, and chat.
- Approval endpoints lack robust not-found/pending/replay checks.
- Chat lets clients choose arbitrary system prompts and model names; errors are not returned as structured failures.
- No usage budgets or execution time limits.
- No persistent task/checkpoint/project layer.
- No CI.
- Docker standalone-output mismatch.

These are to be addressed in the order above; do not paper over them with UI-only changes.

## 7. Acceptance test matrix

- Existing crypto fixture/provider/schema tests continue passing.
- Existing agent, goal, handoff, approval, chat, and thread workflows receive regression coverage.
- SQLite migrations preserve existing rows and are safe to run repeatedly.
- Invalid, missing, expired, altered, and replayed approvals are rejected.
- Missing model key and provider timeout produce explicit, safe, structured failures.
- Browser bundle contains no privileged server credential.
- Tool calls without permission are rejected before execution.
- Consequential actions cannot execute without a valid approval.
- Tasks/checkpoints survive API restarts.
- Frontend production build and backend test suite pass in CI.
- No workflow deploys or changes production infrastructure.

## 8. Current execution checkpoint

**Branch:** `feat/personal-ops-foundation`  
**Baseline main SHA:** `4a5a1b110e1477de1b4f6955a85c8f0450328809`

### Implemented on the branch
- CI-only GitHub Actions workflow for backend tests and frontend production builds; no deployment steps.
- Core API regression tests and workspace persistence tests.
- Authentication fails closed when the server token is missing; comparisons use constant-time comparison.
- Approval proposals now carry canonical immutable payload JSON, SHA-256 hashes, and expiry. Decisions reject unknown/replayed/tampered/expired proposals; an approved payload can be atomically consumed once. Approval does not itself execute the action.
- New SQLite-backed workspace API: projects, tasks, checkpoints, decisions, settings, and overview.
- Mobile Work tab for project/task capture, task status changes, operating preferences, and resumable checkpoints.
- Chat system prompt now uses server-controlled operating charter, current projects, active tasks, and recent checkpoints.
- Chat model selection is server-controlled; chat history is bounded to the most recent 20 messages.
- Missing model configuration and provider failures return structured HTTP errors rather than placeholder replies.
- Frontend Dockerfile no longer assumes Next.js standalone output.

### Verification
- Initial CI baseline passed both backend tests and frontend production build.
- Workspace API test run passed backend tests and frontend production build before the latest chat-context changes.
- Latest backend/frontend verification is running against the newest changes; see GitHub Actions for the exact commit and conclusion.
- No local shell execution was available through the GitHub repository connector; CI is the source of build/test verification.

### Remaining blockers before tool execution
1. Complete the CSP/XSS review, validate session revocation under realistic deployment conditions, and then begin read-only tool integration.
2. Bind approvals to immutable action payloads, add expiry and audit semantics, and prevent replay.
3. Add typed tool registry, per-tool permissions, and a server-side executor.
4. Add provider usage/cost accounting and request budgets.
5. Add approved GitHub write actions (branch/file/PR operations) only after idempotency, full approval-consumption integration, and end-to-end security tests.
6. Complete frontend and deployment configuration review.

**Next action:** Verify the latest CI run; then finish Stage 1 acceptance (including settings/checkpoint UX and docs) and begin the secure session/authentication design.

**Not done:** No production deployment, no merge to main, no paid service, no new production credentials, no external write integration.
