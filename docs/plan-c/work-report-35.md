# D35 Work Report — Recovery-Oriented Operational UI

## Result

D35 is implemented and technically verified. Backend job summaries expose required
`recovery_code` and `recommended_action` enums derived from persisted project-wide
recovery context. `ProjectDetail.generation_recovery` exposes the authoritative bounded
project state from one aggregate query over all project jobs and unresolved remote-side-
effect calls, independent of the 100-row history limit. The frontend requires that
contract alongside job rows for generation controls and pre-action revalidation.
Unknown external outcomes expose no retry path. A synchronous client lock prevents
duplicate recovery submissions before React state updates.

`MigrationError.backup_available` is false until verified backup publication and true
for failures after publication. Startup status preserves that value, so restore
guidance appears only when a verified backup exists.

This is automated technical evidence, not hands-on user acceptance, independent
review, publication, deployment, or a release decision.

## Dependency boundary

D35 adds no runtime dependency. `@testing-library/user-event` is the only new package
and is pinned exactly to `14.6.7` under frontend `devDependencies`; it supplies
realistic tab and Enter interaction semantics for component tests. The lockfile uses
the same exact specifier.

## Sequential full gate

Final-review commands executed from the repository root on 2026-09-30:

1. `cd backend && python -m uv run pytest` — **1304 passed, 7 skipped**, one existing
   Starlette/httpx deprecation warning, 174.81 s. The seven skips are the existing
   ONNX-runtime-dependent cases.
2. `cd backend && python -m uv run ruff check .` — **passed**.
3. `cd frontend && npx -y pnpm@10.18.3 test` — **17 files, 154 tests passed**.
4. `cd frontend && npx -y pnpm@10.18.3 build` — **passed**, 190 modules transformed.
5. `cd frontend && npx -y pnpm@10.18.3 lint` — **passed**.

Focused regression evidence also passed: 209 backend generation, operation,
startup, and migration tests; 39 focused project-history frontend tests; targeted
Ruff; TypeScript/Vite build; and ESLint.

No required command was skipped.

## Real-browser bounded checks

A local Vite app was exercised in installed headless Google Chrome through transient
Playwright 1.55.0 tooling stored only under the ignored evidence directory. Every API
response was synthetic and loopback-only; no cloud, provider, user database, model,
or real user content was used. The final run passed **18/18** checks: nine scenarios
at each of **390x844** and **1440x900**.

Covered at both viewports:

- startup `ready`;
- startup `migration_failed` with `backup_available=true`, showing documented restore
  guidance;
- startup `migration_failed` with `backup_available=false`, showing restart/support
  guidance and no backup claim;
- job `wait/wait`;
- `safe_retry/retry_current`;
- `external_outcome_unknown/check_provider` with no retry control and new generation
  disabled;
- stale project/history revisions, followed by explicit refetch to a coherent revision;
- two synchronous retry activations producing exactly one
  `project.generation.retry` POST;
- real browser Tab traversal to the retry button followed by Enter, producing exactly
  one retry POST.

All 18 page captures reported `documentElement.scrollWidth == window.innerWidth`,
including 390 px. The keyboard focus log records the DOM-order path; the retry button
was reached on the eighteenth focus stop at both viewports. The synthetic startup
reason codes were `migration_failed` and `backup_failed`; ready carried no reason
code.

Three harness-only failures were retained transparently: initial npx module resolution,
an overbroad route glob that intercepted Vite `/src/api/` modules, and one incorrect
expected wait string. Each was corrected in the ignored test harness; none changed
application code. The final browser run is `run.log` and passed 18/18.

## Evidence and privacy

Evidence is under ignored `release-evidence/d35-browser/` only. It contains 18 PNG
screenshots, four sanitized logs (three failed harness attempts plus the final run),
one structured result JSON, and the transient test/config sources. The 23 screenshot,
log, and result files are individually hashed in `evidence-manifest.json`.

- Evidence manifest SHA-256:
  `bffe688169845e9462620568597d1b2e1a1198902a0cba9544884ab181ad5790`
- Screenshots: **18**
- Logs: **4**
- Structured result files: **1**
- Total files covered by the manifest: **23**

Logs replace repository and user-home paths with aliases. Review found no credentials,
`.env` content, real user data, database, generated media, model bodies, or provider
responses. `release-evidence/`, `storage/`, and `.env` remain untracked; Git contains
none of their generated contents.

## Limits and handoff

The browser checks prove behavior against synthetic API state in a real local browser;
they do not prove a real migration failure, provider reconciliation, user acceptance,
independent review, accessibility conformance certification, load/capacity, or release
readiness. The completed D35 delivery commit is
`561677c` (`[DONE] Mission 35 Add recovery-oriented operational UI`). The final-review
correction is the commit containing this report, identified by the exact subject
`fix: align D35 project recovery and backup guidance`. **D36 has not started, and no
candidate freeze exists.**
