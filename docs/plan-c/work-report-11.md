# Work Report — D11: durable requests and revisions

## Delivery

Implemented the user's D11 request from the production schedule on baseline
`c6924d7`, in branch `codex/plan-c-d11`. The change remains local and uncommitted;
no merge, push, deployment, real-data migration, or paid provider call was performed.
Historical work-unit-01–10 reports remain unchanged.

| D11 requirement | Implementation and evidence |
|---|---|
| Persist identity, target, base revision, resolved value, generation intent, result reference | `OperationReceipt` / `operation_requests`, with original normalized content and immutable response JSON |
| Same ID/content returns original result | Lookup precedes current readiness, revision validation and relative resolution; verified after later edits and in fresh interpreters |
| Same ID/different content is rejected | `request_id_conflict` / HTTP 409; includes target, original arguments, operation/version, base revision, observation token and generation flag |
| Uniqueness in persistent storage | SQLite primary key on request ID; direct duplicate insert raises `IntegrityError` |
| Atomic resolution/revision/receipt/settings | Short `BEGIN IMMEDIATE` writer transaction; handlers flush but never commit; injected failure and process death roll back the whole unit |
| No lost generation request between save and submission | Pending job and receipt commit together; startup dispatcher recovers the pending job after forced process death immediately after commit |
| Concurrent delivery and restart replay | Six-thread same-ID test; three independent interpreters for same content, ID conflicts and revision conflicts; before/after-commit `os._exit` fault injection |
| Migration and rollback | Additive, repeatable initialization; tested on a database with the D11 table/column removed; upgrade/backup/rollback instructions in `work-unit-11.md` |

The subtitle relative operation resolves `delta: 2` once (48 -> 50). A new ID
with the current revision intentionally applies another increment (50 -> 52).
Replaying the original request always returns its original 50/revision-2 response.

Project/user block PATCH writes advance integer revision only when values change.
Unchanged requests, status reads, progress and artifact writes do not advance it.
Legacy entry points share busy checks; job creation rechecks them under the writer
lock. Historical job IDs remain reserved after project deletion so receipts cannot
accidentally refer to a later job. Active jobs block project deletion.

## Verification executed on 2026-09-19

| Command/check | Result |
|---|---|
| Baseline `cd backend && python -m uv run pytest -q` | 371 passed |
| Final `cd backend && python -m uv run pytest -q` | **414 passed**, 0 failed, 0 skipped, 29.74 s |
| `cd backend && python -m uv run ruff check .` | Passed |
| `cd frontend && npx -y pnpm@10.18.3 test` | 23 passed in 5 files |
| `cd frontend && npx -y pnpm@10.18.3 build` | TypeScript and Vite passed |
| `cd frontend && npx -y pnpm@10.18.3 lint` | ESLint passed |
| Operation AST import graph and reverse-dependency scan | Acyclic; models/services/workers do not import operations |
| `git diff --check` (existing line-ending configuration) | Passed |

The 43 added tests are in `test_operation_durability.py`,
`test_operation_processes.py`, `test_operation_dispatcher.py` and
`test_operation_storage.py`. They cover receipts, strict relative input/bounds,
required metadata, no-op generation, immutable status snapshots, rollback including
render invalidation, legacy revision changes, migration, lock contention, process
crashes, pending recovery, duplicate worker claims, cancellation and interrupted jobs.
The existing FFmpeg/fake-provider end-to-end tests ran without skips.

One existing third-party Starlette/httpx deprecation warning remains. No dependency
upgrade was needed. The existing unplanned-block test now injects its transient
selector after opening the write boundary, preserving the scenario without passing
an already-dirty session into the new transaction contract. Catalog-list assertions
now include the added relative operation. Build-generated Vite config changes were
restored; there are no frontend source changes.

Environment: Windows, Python 3.13.13, uv 0.11.31, Node 24.13.0, pnpm 10.18.3.
All fixtures use synthetic projects and temporary storage/SQLite files.

## Current boundary

- D11's automated acceptance conditions pass. Human hands-on acceptance and an
  independent reviewer/session have not been claimed. The original schedule's
  human acceptance checkbox was not changed.
- Durable replay is available on the structured operation API. Existing UI/PATCH
  and legacy absolute operations without an ID retain their previous request style
  and do not gain replay guarantees automatically.
- The dispatcher recovers **pending** D11 jobs. Jobs interrupted after the running
  claim are marked failed, without blindly repeating provider work. The runtime
  still supports one application server per database.
- Receipts describe acceptance and saved settings. They do not promise exactly-once
  external provider execution, artifact revision binding, or recovery of a partially
  completed pipeline. D12 planning, D13 artifact binding and D14 recovery are future work.
- Pending jobs still need available provider configuration; process-local BYOK secrets
  are neither persisted in receipts nor reconstructed after restart.

API examples, migration/rollback instructions and the complete current contract are
in `work-unit-11.md`. README, contracts, catalog, module design, specification/DTD
amendments and handoff now point to that contract.
