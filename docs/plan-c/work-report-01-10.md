# Work Report — Work Units 01–10

## Baseline

- Repository: `https://github.com/Rimcat-JA/blockvideo.git`
- Branch: `main`
- Baseline commit: `00ae7cb3333d226bee97c742c7aa1db1dd81203c`
- Baseline backend: 326 passed, 2 skipped, 1 third-party warning before FFmpeg installation.
- Baseline frontend: 23 passed; build and ESLint passed.

## Delivered

- G0 environment, command, map, decision, catalog, contract, and task records.
- Synthetic sample: `samples/plan_c_operation_demo.txt` and `.json`.
- DTD-first architecture and acyclic dependency contract.
- Strict JSON operation catalog with fail-closed metadata/schema checks.
- Explicit handler registry and process bootstrap validation.
- Typed target/request/readiness/result contracts.
- Final target, argument, live-state, and stale-observation checks.
- Subtitle-size setter and read-only project-status handler.
- Shared settings mutation for project PATCH and operation execution.
- Thin structured operation HTTP routes.
- Contract, service, API, persistence, and negative tests.

## Sample evidence

The synthetic JSON was loaded into a fresh SQLite database with fake providers and the existing pipeline. FFmpeg produced:

- Project status: `completed`
- Subtitle size: `48`
- File: `storage/plan-c-smoke/projects/0001/output/video.mp4`
- Size: `190,052` bytes

Generated storage is ignored and is not part of the submission.

## Review

Independent review found no critical issue. Important findings led to:

- fail-closed precondition/postcondition/artifact metadata;
- constraint type/applicability checks;
- a second readiness check immediately before dispatch;
- HTTP 409 for non-ready readiness responses;
- expanded bootstrap, stale, busy, missing, conflict, and no-write tests;
- explicit documentation of the work-unit-11 concurrency boundary.

## Verification

Final post-review run on 2026-09-17:

| Command | Result |
|---|---|
| `cd backend && python -m uv run pytest` | 371 passed; 0 failed; 0 skipped; one Starlette/httpx third-party deprecation warning |
| `cd backend && python -m uv run ruff check .` | Passed |
| `cd frontend && npx -y pnpm@10.18.3 test` | 5 files, 23 tests passed |
| `cd frontend && npx -y pnpm@10.18.3 build` | TypeScript and Vite build passed |
| `cd frontend && npx -y pnpm@10.18.3 lint` | ESLint passed |
| Operation-package AST import graph | 8 modules, acyclic |
| `python -m json.tool samples/plan_c_operation_demo.json` | Passed |
| `git diff --check` | Passed |

The full backend run included the FFmpeg timing test and fake-provider end-to-end integration test; neither was skipped after FFmpeg installation.

## Gate status

- **G0:** passed — environment, baseline, scope, decisions, and verification path are recorded.
- **G1:** passed — representative operations work without retrieval/LLM, all entry paths share validation/persistence rules, and final checks passed.

## Deferred deliberately

Work units 11+ remain out of scope: durable request/revision/idempotency, generation planning, recovery, natural language, model integration, retrieval, and evaluation comparison.
