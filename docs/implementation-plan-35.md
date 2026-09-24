# D35 Recovery-Oriented Operational UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present backend-authoritative recovery and startup states with accurate, accessible user actions and no browser-side retry authority.

**Architecture:** Backend job summaries derive exact recovery/action enums from persisted jobs and unresolved calls. Small `RecoveryStatus` and `StartupStatus` components render those contracts; existing operation hooks remain the only action path and durable receipts remain authoritative.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, React 18, TypeScript 5.6, TanStack Query, Vitest, Testing Library.

## Global Constraints

- Follow `docs/plan-c/work-unit-35.md` and the D35 section/roadmap in `docs/DTD.md`.
- The browser never decides retryability, migration safety, remote outcome, or receipt state.
- `JobSummary.recovery_code` and `recommended_action` are required exact enums, not prose inference.
- Unknown external outcomes never expose retry controls.
- Native buttons, DOM-order focus, `role="status"`/`role="alert"`, keyboard operation, and 390 px layout are mandatory.
- Duplicate action clicks remain safe through existing request IDs/locks.
- Final delivery commit is `[DONE] Mission 35 Add recovery-oriented operational UI`.

---

### Task 1: Backend recovery and startup contracts

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/services/job_views.py`
- Modify: `backend/tests/test_d35_startup_recovery_api.py`
- Modify: existing job-view tests discovered by `rg "job_summary|retryable" backend/tests`

**Interfaces:**

```python
RecoveryCode = Literal[
    "wait", "safe_retry", "external_outcome_unknown", "refresh_required",
    "cancelled", "completed", "failed",
]
RecommendedAction = Literal[
    "wait", "retry_current", "check_provider", "refresh", "none",
]
```

`JobSummary` adds required `recovery_code: RecoveryCode` and `recommended_action: RecommendedAction`. `job_summary(job: GenerationJob) -> JobSummary` derives them from persisted status, cancellation, object-session availability, and unresolved calls.

- [ ] **Step 1: Write RED table-driven job mapping tests**

Cover pending/running, cancel requested, failed retryable, failed blocked by unknown call, unknown, cancelled, completed, and detached-session failed jobs. Assert exact `(recovery_code, recommended_action, retryable)` tuples and fixed non-sensitive messages.

- [ ] **Step 2: Run backend RED tests**

```bash
cd backend
python -m uv run pytest tests/test_d35_startup_recovery_api.py -k recovery_code -q
```

Expected: FAIL because required fields do not exist.

- [ ] **Step 3: Implement exact mappings**

Use these rules: active/cancel-requested -> `wait/wait`; failed with safe retry -> `safe_retry/retry_current`; failed with unresolved remote work or unknown -> `external_outcome_unknown/check_provider`; detached state requiring a fresh read -> `refresh_required/refresh`; cancelled -> `cancelled/none` unless existing retry permission makes it `safe_retry/retry_current`; completed -> `completed/none`; terminal non-retryable local failure -> `failed/none`.

- [ ] **Step 4: Run backend API/regression tests**

```bash
cd backend
python -m uv run pytest tests/test_d35_startup_recovery_api.py tests/test_job_recovery.py tests/test_external_call_recovery.py tests/test_operation_api.py -q
python -m uv run ruff check app/schemas/__init__.py app/services/job_views.py tests/test_d35_startup_recovery_api.py
```

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/schemas/__init__.py backend/app/services/job_views.py backend/tests
git commit -m "feat: expose authoritative recovery actions"
```

### Task 2: Typed recovery and startup components

**Files:**
- Create: `frontend/src/components/RecoveryStatus.tsx`
- Create: `frontend/src/components/StartupStatus.tsx`
- Create: `frontend/src/test/recovery-status.test.tsx`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/GenerationHistory.tsx`

**Interfaces:**

```typescript
export type RecoveryCode = 'wait' | 'safe_retry' | 'external_outcome_unknown' |
  'refresh_required' | 'cancelled' | 'completed' | 'failed';
export type RecommendedAction = 'wait' | 'retry_current' | 'check_provider' | 'refresh' | 'none';
export interface StartupState {
  status: 'starting' | 'ready' | 'migration_failed';
  reason_code: string | null;
  message: string;
  schema_version: number | null;
  backup_available: boolean;
}
```

- `api.startup(): Promise<StartupState>` calls `GET /api/startup`.
- `RecoveryStatus({ job }: { job: JobSummary })` renders one status region and action guidance only.
- `StartupStatus()` fetches startup state, renders `role="alert"` on migration failure, and directs the operator to stop/restart and documented backup restoration; it executes no migration/restore.

- [ ] **Step 1: Write RED component tests**

For every recovery/action enum pair, assert exact Japanese label/guidance, one status region, and no retry button inside `RecoveryStatus`. Test startup starting/ready/migration-failed/network-failure states and ensure no private path is rendered.

- [ ] **Step 2: Run frontend RED tests**

```bash
cd frontend
npx -y pnpm@10.18.3 test -- recovery-status.test.tsx
```

Expected: FAIL because components/types do not exist.

- [ ] **Step 3: Implement types, API, and components**

Make new `JobSummary` fields required. Replace status-specific prose in `GenerationHistory` with `RecoveryStatus`; show retry only when `recommended_action === 'retry_current' && retryable`, and keep unknown/check-provider states button-free.

- [ ] **Step 4: Run component tests, type build, and lint**

```bash
cd frontend
npx -y pnpm@10.18.3 test -- recovery-status.test.tsx project-history.test.tsx durable-operation.test.tsx
npx -y pnpm@10.18.3 build
npx -y pnpm@10.18.3 lint
```

- [ ] **Step 5: Commit Task 2**

```bash
git add frontend/src/components/RecoveryStatus.tsx frontend/src/components/StartupStatus.tsx frontend/src/test/recovery-status.test.tsx frontend/src/lib/types.ts frontend/src/api/client.ts frontend/src/components/GenerationHistory.tsx
git commit -m "feat: render typed recovery and startup status"
```

### Task 3: Page integration, stale transitions, and accessibility

**Files:**
- Modify: `frontend/src/pages/ProjectDetailPage.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/test/recovery-status.test.tsx`
- Modify: `frontend/src/test/project-history.test.tsx`
- Modify: `frontend/src/test/durable-operation.test.tsx`

**Interfaces:**
- `StartupStatus` is mounted once in `Layout` above routed content.
- Project controls use refreshed `JobSummary.recommended_action`; stale revision/history disables actions until refetch.
- `GenerationHistory` invokes existing `onRetry(job.id)` and `onCancel(job.id)` callbacks only from enabled native buttons.

- [ ] **Step 1: Add RED interaction tests**

Test stale history -> refresh -> safe retry, unknown external outcome with no retry, cancellation wait, completed state, duplicate retry click while locked, keyboard tab/Enter activation, one live status announcement, and component containment at a 390 px viewport without horizontal overflow.

- [ ] **Step 2: Implement page integration**

Mount `StartupStatus`, preserve current polling/refetch behavior, disable controls while history/project revisions differ, and key action visibility only from typed fields. Do not add automatic resend/retry intervals.

- [ ] **Step 3: Run focused frontend and backend contract tests**

```bash
cd frontend
npx -y pnpm@10.18.3 test -- recovery-status.test.tsx project-history.test.tsx durable-operation.test.tsx history-polling.test.tsx
npx -y pnpm@10.18.3 build
npx -y pnpm@10.18.3 lint
cd backend
python -m uv run pytest tests/test_d35_startup_recovery_api.py tests/test_operation_api.py -q
```

- [ ] **Step 4: Commit Task 3**

```bash
git add frontend/src/pages/ProjectDetailPage.tsx frontend/src/components/Layout.tsx frontend/src/test/recovery-status.test.tsx frontend/src/test/project-history.test.tsx frontend/src/test/durable-operation.test.tsx
git commit -m "test: verify D35 recovery interactions"
```

### Task 4: Browser evidence, documentation, and D35 gate

**Files:**
- Create: `docs/plan-c/work-report-35.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `docs/modules/operation-core.md`
- Modify: `specification.md` and `docs/DTD.md` if implementation evidence differs

**Interfaces:**
- Browser evidence uses synthetic states/API responses and records viewport, keyboard path, actions available, and observed backend reason codes; it is not human acceptance.

- [ ] **Step 1: Run full verification sequentially**

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

- [ ] **Step 2: Run bounded browser checks**

Start the synthetic local app, exercise wait/safe-retry/unknown/migration-failed/stale-refresh states, keyboard navigation, duplicate click locking, and 390 px layout. Store screenshots/logs only under ignored `release-evidence/d35-browser/`; record hashes/counts in the report and do not claim hands-on user acceptance.

- [ ] **Step 3: Inspect and write evidence**

```bash
git status --short
git diff --check
git ls-files .env storage release-evidence
```

State D36 has not started and list any skipped browser/environment check exactly.

- [ ] **Step 4: Commit and push the implementation task**

```bash
git add backend frontend docs/plan-c/work-report-35.md docs/plan-c/handoff.md docs/modules/operation-core.md specification.md docs/DTD.md
git commit -m "[DONE] Mission 35 Add recovery-oriented operational UI"
git push
```

Do not freeze, tag, publish, or deploy in D35.
