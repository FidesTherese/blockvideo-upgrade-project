# Plan C D33 Work Report — Crash and recovery boundaries

## Result

D33 is complete at the automated verification gate. D34 has not started.

The final D33 matrix contains exactly **37 collected scenarios**. It reopens isolated SQLite state through a canonical snapshot covering the complete project recovery view, settings history, language requests/turns, jobs, immutable receipts, external-call journal rows, and artifacts. Response bytes are represented only by SHA-256. Process-death cases use synthetic projects, fake/local callbacks, fixed fsynced markers, and fixed non-zero exits. No public request or environment-selected failpoint, schema, dependency, real provider, user data, release, tag, publication, or deployment was added.

D33 found and corrected production recovery gaps in artifact replay/publication and application shutdown:

1. committed artifact replay now returns the existing same-job artifact before candidate validation or cancellation reconsideration;
2. a resumed generated checkpoint updates the job input snapshot/fingerprint together, and publication requires exact job/revision/settled/current-input equality;
3. initial rename and exact same-job orphan replacement occur only inside the publication writer transaction after the complete eligibility and reference recheck;
4. referenced destinations are never removed or replaced, including identical-byte destinations, while only an exact unreferenced same-job video orphan is recoverable;
5. subtitle identity is checked inside the writer transaction before rename and again before artifact construction;
6. `GenerationArtifact.manifest_json` is the sole artifact-manifest authority; publication creates no per-job `manifest.json`, including across flush/commit failure;
7. `JobRegistry` closes admission before draining, rejects post-close submission before task/cancellation/liveness creation, cancels and awaits accepted tasks, and is reopened before each lifespan dispatcher.

Request claim, receipt, and core commit boundaries required no production correction.

## Exact 37-scenario matrix

The count below is the exact pytest collection, grouped without collapsing parameterized scenarios.

| # | Scenario(s) | Count | Crash/rejection state and restart evidence |
|---:|---|---:|---|
| 1 | Canonical reopened snapshot | 1 | Two fresh sessions produce equal JSON-safe state; prior artifact identity and SHA-256-only response bytes remain present. |
| 2–3 | Request claim `before` / `after` durable claim | 2 | Before: no claim/effect, clean first execution. After: persisted interpreting owner expires to saved `interpretation_interrupted`, zero model/effect. Explicit restart calls are `(0, 0)` and replay leaves the full snapshot unchanged. |
| 4–5 | Settings core commit `before` / `after` | 2 | Either no effect or one complete revision/history/receipt effect. Restart is `(0, 0)` before and after exact replay. |
| 6–7 | Receipt save `before` / `after` during generation confirmation | 2 | Transaction rolls back in both injected branches; retry creates exactly one pending job plus matching immutable receipt. Restart is `(0, 0)` before and after replay. |
| 8–10 | Provider death after `claimed`, `sent`, or `response_saved` | 3 | Exactly one journal row. First reconciliation is `(1, 0)`; a later restart pair is `(0, 0)`. Claimed/sent become `unknown`; finished remains `succeeded` and returns cached bytes. No replay transport call occurs. |
| 11–16 | Checkpoint initial, resume, missing fingerprint, altered snapshot, changed revision, durable cancellation | 6 | Crash leaves a running row with `checkpoint_saved`. First reconciliation is `(1, 0)`, then `(0, 0)`. Valid initial/resume become pending; missing/altered/revision mismatch become failed; cancellation becomes cancelled. Terminal cases cannot reach registry submission/provider construction. |
| 17 | Actual lifespan shutdown cancellation | 1 | Durable running state survives cancellation. Marker order proves task cancellation and registry drain precede lifespan exit. Reconciliation is `(1, 0)` to pending, then `(0, 0)`; no call row exists for the job. |
| 18–20 | Artifact death before rename, after rename, after DB publication | 3 | Before/after rename reconcile `(1, 0)` then `(0, 0)`; published is `(0, 0)` immediately. Prior artifact remains. Only published has one new row/current pointer; replay returns that row without candidate validation/cancellation. |
| 21 | Resume after rename-before-commit orphan | 1 | Initial reconciliation is `(1, 0)` to pending. Real registry submits once, exact frozen input completes once, prior history remains, no external call is created, replay is stable, and final restart is `(0, 0)`. |
| 22 | Referenced same-job history destination | 1 | Publication rejects before replacing the referenced final video; prior current artifact remains and no new row exists. The assertion uses a freshly reopened canonical snapshot; this local rejection case does not invoke `restart_twice()`. |
| 23–27 | Publication blockers: cancelled, stale revision, stale job fingerprint, changed project input, unresolved remote call | 5 | Candidate remains byte-identical, destination is absent, and no artifact row is created. Each assertion reopens SQLite; these local rejection cases do not invoke `restart_twice()`. |
| 28–29 | Subtitle mutated / deleted after video rename | 2 | Publication rolls back; only the unreferenced video orphan may remain, no artifact row or manifest file exists, prior artifact bytes remain, and the reopened database snapshot is unchanged. These local post-rename rejection cases do not invoke `restart_twice()`. |
| 30–33 | Identical-byte destination referenced by artifact path, same job, project output, or project current pointer | 4 | Candidate and final bytes remain unchanged and artifact count remains one. Same-job committed replay returns the prior row; all other references reject. Each assertion reopens SQLite; these local reference cases do not invoke `restart_twice()`. |
| 34–35 | Artifact ORM `flush` / transaction `commit` failure | 2 | Candidate has renamed to the exact final path, directory contains only that video orphan, no `manifest.json` or artifact row exists, and reopened DB state equals pre-call state. These injected DB-failure cases do not invoke `restart_twice()`. |
| 36–37 | Generation core commit `before` / `after` | 2 | Either no effect or one complete job/receipt effect; retry/replay is exact. Every explicit restart pair is `(0, 0)`. |

The scenarios with startup-recoverable running work explicitly prove first/second transition counts. The remaining local publication rejection/rollback cases prove reopened database and filesystem state but do **not** call the restart helper; this report does not overstate them as separate restart executions.

## Durable marker and remote-attempt evidence

| Process boundary | Exact fsynced marker sequence | Exit | First/second reconciliation | New-job remote attempts after replay |
|---|---|---:|---|---:|
| provider claimed | `claimed` | 71 | `(1, 0)` to `unknown`; later `(0, 0)` | 0 |
| provider sent | `claimed`, `sent` | 72 | `(1, 0)` to `unknown`; later `(0, 0)` | 1 total |
| provider response saved | `claimed`, `sent`, `response_saved` | 73 | `(1, 0)` to `succeeded`; later `(0, 0)` | 1 total; cached response reused |
| each checkpoint/cancellation case | `checkpoint_saved` | 81–86 | `(1, 0)` to the scenario result; later `(0, 0)` | 0 |
| lifespan shutdown | `durable_running`, `registry_shutdown_started`, `task_cancelled`, `registry_shutdown_finished`, `lifespan_exit` | 0 | `(1, 0)` to pending; later `(0, 0)` | 0 |
| artifact before rename | `checkpoint_saved` | 91 | `(1, 0)`; later `(0, 0)` | 0 |
| artifact after rename | `checkpoint_saved`, `artifact_renamed` | 92 | `(1, 0)`; later `(0, 0)` | 0 |
| artifact published | `checkpoint_saved`, `artifact_renamed` | 93 | `(0, 0)` | 0 |
| resumed orphan setup | `checkpoint_saved`, `artifact_renamed` | 92 | `(1, 0)` before submit; `(0, 0)` after completion | 0 |

The marker count is an append-only synthetic observation, not a provider log. The provider scenarios additionally install a replay transport that would count any attempted POST; it remains zero on replay. Thus the observed total `sent` marker count is exactly 0/1/1 for claim/send/finished, never two. Checkpoint, shutdown, and resumed-local completion paths create no new-job external-call row.

## Artifact and frozen-input evidence

- Every process-death seed retains the prior successful artifact ID. Cases that materialize it also retain exact bytes `prior-success`.
- Before rename, the candidate remains and no final video/new artifact exists. After rename-before-commit, only the exact unreferenced same-job `video.mp4` orphan exists; it is not current and does not replace history.
- A resumed job is dispatched once through a real `JobRegistry`; job input, resume checkpoint, current project capture, fingerprint, and revision must all agree before a verified candidate can replace that exact orphan and publish one row.
- Completed publication replay returns the same artifact ID without validation, cancellation reconsideration, a second row, or file replacement.
- Cancelled, stale-revision, stale-job-input, changed-project-input, unresolved-call, referenced-destination, and identical-byte-reference cases cannot mutate the destination or create a row.
- Subtitle mutation/deletion after rename and ORM flush/commit failure leave no row and no per-job `manifest.json`; only the permitted unreferenced video orphan may remain. Successful artifacts carry the complete transactional `manifest_json`. Retrieval-index manifests are a separate unchanged subsystem.
- Prior artifact/current pointers remain unchanged on every failed publication path; successful publication updates project/job/current references together.

## RED/GREEN history and production fixes

### Request/core boundaries

The initial REDs were missing/incomplete test helpers and assertions: the first canonical helper omitted project settings and language-turn state. The strengthened snapshot added exact settings, complete language request/turn rows, bidirectional job/receipt identity, exact receipt JSON, replay equality, and post-owner-death reconciliation. Existing production transactions passed; no request/core production file changed.

### Provider, checkpoint, and committed replay

The process-death harness first required a test-only escaped-newline correction. The first production RED occurred when committed publication replay tried to validate the already-renamed missing candidate. `publish_artifact()` now returns the existing same-job artifact first. Journal-row cardinality, exact checkpoint fingerprints, terminal non-dispatch, and replay checks were then strengthened without further production change.

### Resumed publication and shutdown

Further RED cases showed that rename could happen before cancellation/staleness/unresolved-call checks, stale revision/fingerprint combinations could publish, identical-byte references could bypass protection, and lifespan exit could precede callback cancellation. Production changes moved rename/orphan replacement under the writer transaction's complete eligibility/reference checks, synchronized accepted pipeline input identity, added registry admission/drain lifecycle, and ordered lifespan close/dispatcher stop/registry shutdown. Follow-up races closed post-rename subtitle mutation and concurrent shutdown/submit, and verified repeated lifespan reopen.

### Transactional manifest authority

Final RED cases showed successful publication and database flush/commit rollback still created per-job `manifest.json`. Production now stores complete artifact metadata only in transactional `GenerationArtifact.manifest_json`. Flush/commit rollback can leave only the exact video orphan and no second manifest authority.

## Verification

All commands ran sequentially; backend and frontend checks did not overlap.

### Focused D33/recovery gate

```bash
cd backend
python -m uv run pytest tests/test_d33_recovery_matrix.py tests/test_external_call_recovery.py tests/test_job_recovery.py tests/test_artifact_history.py tests/test_operation_durability.py tests/test_generation_controls.py -q
```

Result: **145 passed, 0 skipped, 0 failed, 1 warning in 36.92s**. The D33 file contributed exactly **37 passed scenarios**. The warning is the existing Starlette `TestClient`/`httpx` deprecation warning.

### Full repository gate

The first full backend run was **not green**: **1170 passed, 7 skipped, 1 failed, 1 warning in 161.46s**. The failure was the known timing-sensitive `tests/test_d22_compound.py::test_simultaneous_confirmation_creates_one_job` diagnostics-equality mismatch. No D22 or production source was changed. Its immediate isolated rerun passed (**1 passed, 1 warning in 1.45s**), which is only isolated evidence and is not reported as a full-suite pass. One fresh sequential full-suite rerun then passed: **1171 passed, 7 skipped, 0 failed, 1 warning in 155.15s**. The seven skips are existing ONNX runtime/asset-dependent tests; the warning is the same existing Starlette/httpx deprecation.

| Command | Result |
|---|---|
| `cd backend && python -m uv run ruff check .` | exit 0, `All checks passed!` |
| `cd frontend && npx -y pnpm@10.18.3 test` | **16 files / 123 tests passed**, 0 failed, in 9.68s |
| `cd frontend && npx -y pnpm@10.18.3 build` | exit 0; TypeScript/Vite transformed **188 modules**, build 1.97s |
| `cd frontend && npx -y pnpm@10.18.3 lint` | exit 0; ESLint emitted no errors or warnings |

The later green full rerun does not erase or reclassify the first failure; it demonstrates that the complete suite also passed once under the required sequential load.

## Repository and artifact checks

After documentation reconciliation:

- `git status --short` showed only modified `docs/plan-c/handoff.md` and untracked `docs/plan-c/work-report-33.md`;
- `git diff --check` exited 0 with no output;
- `git ls-files .env storage release-evidence` exited 0 with no output, so no `.env`, `storage`, or `release-evidence` file is tracked;
- generated frontend `dist/`, caches, virtual environments, and synthetic storage remained ignored;
- the D33 delivery diff was inspected for credentials, private/user data, and generated media before staging; none was added.

## Acceptance and limits

- The covered recoverable/terminal startup states have zero second-restart transitions; exact local rejection cases retain reopened durable state as recorded above.
- No tested scenario duplicates a remote send, adopts changed frozen input, publishes an incomplete artifact, loses the prior successful artifact, or changes a state checked by the explicit second restart.
- This is single-server SQLite crash/recovery correctness evidence, not multi-server, distributed-lock, load, throughput, latency, or capacity evidence.
- Tests use synthetic projects and fake/local providers. No real provider, paid API, real user data, human operation, or independent acceptance was exercised.
- Filesystem rollback cannot undo an atomic rename; the explicit safe remainder is one exact unreferenced same-job video orphan. Database references and prior history remain authoritative.
- D34 has not started. No release, tag, publication, or deployment occurred.
