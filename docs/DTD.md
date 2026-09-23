# BlockVideo Plan C — Detailed Technical Design

## D31–D40 Implementation Contract

### Document control

- **Status:** Implementation-ready
- **Delivery mode:** High-Risk for D31 security, D32 concurrency, and D34 migration;
  Standard for the remaining units
- **Specification:** `specification.md`, `docs/plan-c/work-unit-31.md` through
  `docs/plan-c/work-unit-40.md`
- **DTD:** `docs/DTD.md`
- **Updated:** 2026-09-23
- **Scope:** sequential hardening, blinded evaluation, and release-readiness decision
- **Open decisions:** none for implementation. Held-out case content and independent
  evaluator identity remain intentionally outside the implementation process.

### Technical scope and fixed decisions

D31–D35 modify the production candidate. D36 freezes the resulting clean commit.
D37 runs only through a separate evaluator against approved, separately mounted
held-out material. D38 imports a non-sensitive aggregate. D39 verifies the exact
frozen candidate. D40 emits a decision and never tags, publishes, or deploys.

The following choices resolve implementation ambiguities:

1. D31 uses a conservative host-side negative-control guard in addition to the
   model prompt. A veto is a safe non-effect and never rewrites one operation into
   another.
2. D32 and D33 first extend tests around existing transaction, receipt, journal,
   checkpoint, and publication seams. Production hooks are added only if a failing
   invariant cannot be exercised by dependency replacement or process termination.
   Public request data can never select a failpoint.
3. D34 uses SQLite `PRAGMA user_version`; unversioned supported databases are
   version 0 and the first explicit current schema is version 1. Python's `sqlite3`
   backup API creates the pre-migration copy. No Alembic dependency is added.
4. Migration failure enters a degraded API state: `/api/health` and `/api/startup`
   remain readable, database-dependent endpoints return a fixed 503, and the job
   dispatcher does not start.
5. D37's `stateful` mode is the D30 production semantic configuration with
   readiness annotations and bounded all-tools fallback. D29 B1/B2/P1/B0+ are not
   final-evaluation modes.
6. Detailed held-out evidence remains in evaluator-controlled storage. “Sealed”
   means content-addressed and not imported into this repository; it does not imply
   encryption. D38 requires an out-of-band expected SHA-256 for transfer-integrity
   validation. Reviewer identity is recorded but not cryptographically proven.
7. A source-request group owns one output directory; each case receives a fresh
   database/media child initialized from that case's declared state. Cases do not
   leak mutable state to sibling paraphrases.
8. Human-operation and independent-review evidence use content-bound JSON records.
   D40 treats absent records as blockers, not as negative results or inferred passes.

Runtime remains Windows 11 compatible, Python `>=3.12`, Node `>=20`, local SQLite,
and the existing single-server worker. No cloud call, new runtime dependency, or
private held-out file is required by implementation tests.

### Architecture and dependency direction

```mermaid
flowchart LR
    UI[React recovery UI] --> API[FastAPI]
    API --> Lang[language_operations]
    Lang --> Guard[intent_guard]
    Lang --> Core[OperationService]
    Core --> DB[(SQLite schema v1)]
    Core --> Worker[Generation worker]
    Worker --> Journal[External-call journal]
    Worker --> Artifacts[Immutable artifacts]

    Startup[Startup lifecycle] --> Migration[migrations]
    Migration --> DB
    Startup --> Status[startup_status]
    API --> Status

    Adv[evaluation.adversarial] --> Lang
    Freeze[release_candidate.freeze] --> Manifest[Freeze manifest]
    Blind[evaluation.blinded_runner] --> Lang
    Blind --> Aggregate[Aggregate bundle]
    Import[evaluation.result_import] --> Aggregate
    Decision[evaluation.release_decision] --> Aggregate
    Manifest --> Blind
    Manifest --> Decision
```

Allowed directions:

```text
contracts/models <- services <- API/main
interpretation <- language_operations <- API
operations core <- language_operations
DB/model metadata <- migrations <- main
app public services <- evaluation and release scripts
release_candidate <- release scripts
```

Prohibited directions:

- `app` packages must not import `evaluation` or `release_candidate`.
- `migrations` must not import API routes, operations, workers, evaluation, or UI.
- model interpretation must not import handlers, DB models, or workers.
- the browser must not decide retryability, migration safety, or remote-call status.
- final-evaluation code must not import D29 experiment selectors.

### Technology and research record

No new third-party package is selected. Direct in-scope dependencies are:

| Dependency | Version/constraint | Symbols and role |
|---|---|---|
| Python standard library | Python 3.12.12 verified | `unicodedata.normalize`, `re`, `hashlib.sha256`, `json`, `sqlite3.connect`, `sqlite3.Connection.backup`, `os.open`, `os.replace`, `shutil.disk_usage`, `subprocess.run`, `pathlib.Path` |
| SQLAlchemy | locked by `uv.lock`; project `>=2.0.36` | existing `Session`, `select`, `inspect`, `text`; ORM and writer transactions |
| Pydantic | locked by `uv.lock`; project `>=2.9.0` | `BaseModel`, `ConfigDict`, `Field`, validators; strict manifests and API DTOs |
| FastAPI | locked by `uv.lock`; project `>=0.115.0` | `APIRouter`, `Depends`, `HTTPException`; startup status transport |
| pytest | dev dependency `>=8.3.3` | monkeypatch, temporary directories, process/race matrices |
| React | 18.3.1 | recovery/status components |
| TypeScript | project `^5.6.3` | exact frontend mirrors of backend enums |
| Vitest/Testing Library | Vitest 2.1.9 verified | component and interaction tests |

Official sources checked 2026-09-23:

- Python `sqlite3.Connection.backup`: <https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup>
- SQLite `PRAGMA user_version` and `PRAGMA integrity_check`:
  <https://www.sqlite.org/pragma.html#pragma_user_version> and
  <https://www.sqlite.org/pragma.html#pragma_integrity_check>
- SQLite Online Backup API: <https://www.sqlite.org/backup.html>
- SQLAlchemy SQLite dialect/transaction behavior:
  <https://docs.sqlalchemy.org/en/20/dialects/sqlite.html>

The backup connection is synchronous and owned/closed by the migration runner.
Migration and application startup are single-threaded. Existing async model/provider
clients retain their present ownership and deadlines.

### Intended repository structure

```text
backend/app/
├── core/
│   └── startup_status.py              # process-local bounded startup state
├── migrations/
│   ├── __init__.py
│   ├── backup.py                      # consistent verified SQLite backup
│   ├── contracts.py                   # MigrationResult/Error
│   ├── runner.py                      # lock, classify, migrate, verify
│   └── schema.py                      # v0 -> v1 additive schema operation
├── language_operations/
│   └── intent_guard.py                # deterministic negative-control veto
├── api/
│   └── routes_startup.py              # GET /api/startup
└── release_candidate/
    ├── __init__.py
    ├── contracts.py                   # freeze/verification manifests
    ├── fingerprints.py                # canonical hashes
    ├── freeze.py                      # clean-tree candidate freeze
    └── verification.py                # D39 evidence checks
backend/evaluation/
├── adversarial.py
├── blinded_contracts.py
├── blinded_runner.py
├── blinded_scoring.py
├── sealed_evidence.py
├── result_contracts.py
├── result_import.py
└── release_decision.py
backend/scripts/
├── run_adversarial.py
├── freeze_candidate.py
├── run_blinded_evaluation.py
├── import_evaluation_result.py
├── verify_release_candidate.py
└── decide_release_readiness.py
frontend/src/components/
├── RecoveryStatus.tsx
└── StartupStatus.tsx
backend/tests/
├── test_d31_adversarial_safety.py
├── test_d32_concurrency_matrix.py
├── test_d33_recovery_matrix.py
├── test_d34_migrations.py
├── test_d35_startup_recovery_api.py
├── test_d36_freeze.py
├── test_d37_blinded_runner.py
├── test_d38_result_import.py
├── test_d39_release_verification.py
└── test_d40_readiness_decision.py
```

`release-evidence/` is ignored and stores generated candidate/evaluation evidence.
Migration and blinded synthetic fixtures live under `backend/tests/fixtures/`.

### D31 module, function, and contract design

`app/language_operations/intent_guard.py` owns only deterministic safe vetoes.
It imports `re`, `unicodedata.normalize`, and interpretation proposal contracts.

```python
MUTATING_OPERATIONS: frozenset[str]

def normalized_intent(text: str) -> str: ...

def negative_control_reason(text: str, operation_id: str) -> str | None: ...
```

`normalized_intent` applies NFKC, `casefold()`, translates U+2018/U+2019/U+FF07
apostrophes to ASCII `'`, converts all Unicode whitespace to one ASCII space, and
trims. It does not otherwise remove punctuation or identifiers.
`negative_control_reason` returns `"explicit_negative_intent"` only for a mutating
proposal and these normalized phrase families:

- global: `何もしない`, `実行しない`, `変更しない`, `do nothing`,
  `do not execute`, `don't execute`;
- retry: `再試行しない`, `再実行しない`, `やり直さない`, `do not retry`,
  `don't retry`;
- cancellation: `キャンセルしない`, `取り消さない`, `停止しない`,
  `do not cancel`, `don't cancel`;
- generation: `生成しない`, `開始しない`, `作り直さない`, `do not generate`,
  `don't generate`.

Operation-specific phrases veto only the matching operation family. A global phrase
vetoes every mutating operation. No positive operation is inferred from text.
`LanguageOperationService.prepare()` runs the guard after schema-valid proposal
parsing and before `OperationRequest` construction. A veto preserves the original
interpretation for audit, returns `status="dismissed"`, creates no prepared request
or confirmation token, and records diagnostic `guard_code="negative_intent"`.
`LanguageDiagnostics.guard_code` adds that literal.

`evaluation/adversarial.py` defines strict `AdversarialCase` and `AdversarialResult`
records and loads only `evaluation/d31/development.jsonl`. The loader opens the
corpus once in binary mode, reads at most `MAX_CORPUS_BYTES + 1`, rejects excess
bytes, and only then decodes UTF-8 with optional BOM; it must not use a separate
metadata size check. Cases contain synthetic text, mode, expected status class,
explicit forbidden effects, and exact required effects for settings, revision,
jobs, cancellation, receipts, and artifacts. Initial jobs (maximum 32), settings
history rows (maximum 32), and prior turns (maximum 8) use dedicated frozen
Pydantic records with `extra="forbid"`; their strings and child collections are
bounded to the existing interpretation/fixture limits. The runner converts the
validated initial state to the existing comparison fixture contract, uses isolated
temporary DB/media roots, and executes the ordinary language/core path.

Effect comparison is content-based. Jobs remain keyed by ID; receipts and artifacts
are canonicalized as sorted-key compact JSON and compared as multisets so an
in-place mutation or same-count replacement is an observed effect. A result passes
only when its status is allowed, no forbidden effect occurred, and every observed
effect count exactly equals the case's `required_effects`. Result JSON contains
only IDs, status, booleans, and counts; it never contains corpus/model text.

`app/main.py` changes the catch-all handler to log only
`error_class`, route, and a generated correlation ID; the JSON response is fixed:

```json
{"detail":{"reason_code":"internal_error","message":"処理に失敗しました。再読み込み後も続く場合は記録番号を確認してください。","correlation_id":"..."}}
```

Raw exception strings, request bodies, model bodies, prompts, raw request paths,
filesystem/private paths, and credentials must not appear in application logs or this
response. Logs may retain the matched framework route template as bounded metadata.
Existing narrow domain errors retain fixed user messages but must not forward
arbitrary provider exception text.

### D32 concurrency design

No new lock service is introduced. `services.transactions.begin_write()` remains
the cross-process serialization boundary using `BEGIN IMMEDIATE`. Tests create
independent SQLAlchemy sessions and, for process cases, spawned Python processes
pointing at one temporary SQLite file.

The matrix covers receipt identity, concurrent settings, dialogue supersession,
generation confirmation/revision change, cancel/publication, retry/recovery,
delete/active-or-unknown work, and startup pending-job claims. Assertions inspect
receipts, settings history, jobs, external calls, artifacts, and project revision.
One transaction may win. All other effects must resolve as exact replay,
`stale_state`, `project_busy`, request-content conflict, or bounded `database_busy`.
A `WriteBusyError` response keeps `Retry-After: 1` and tells clients to retry the
same request ID. Process-local locks may reduce duplicate work but never establish
correctness.

### D33 recovery design

Tests inject failures with monkeypatches at existing callable seams:
`repository.claim`, `receipts.save_receipt`, `httpx.AsyncClient.post`,
`external_calls._finish`, `generation_snapshots.capture_inputs`,
`artifact_store.publish_artifact`, and job-control transitions. Process-kill tests
terminate an isolated app/worker only after an observed durable marker.

No generic production failpoint registry is added. If a demonstrated crash gap
requires a seam, add one private keyword-only callback defaulting to `None` and
construct it only in tests; environment variables and HTTP payloads cannot enable it.
Unknown remote calls remain terminal for automatic replay. Local calls may be
retried only under existing fingerprint rules. Publication always validates file
identity before changing current-artifact pointers.

### D34 migration and startup design

#### Persistent version and supported ancestry

- `PRAGMA user_version = 0`: empty DB, upstream/pre-Plan-C DB, or current D30 DB
  created before explicit versioning.
- `PRAGMA user_version = 1`: D34 schema after all current ORM tables and additive
  columns are present.
- Values greater than 1 are rejected as `schema_too_new`.

Version 0 classification is structural. Known project/block/job tables may be
present; unknown extra tables are preserved. If a known column has an incompatible
type/name collision, migration fails `unsupported_legacy_schema`. Missing tables
are created from current metadata. Missing columns are added only when nullable or
when a server default can preserve existing rows. No column is dropped, renamed, or
retyped.

#### Migration interfaces

```python
@dataclass(frozen=True)
class MigrationResult:
    status: Literal["created", "current", "migrated"]
    from_version: int
    to_version: int
    backup_created: bool
    backup_sha256: str | None

class MigrationError(RuntimeError):
    reason_code: Literal[
        "migration_locked", "schema_too_new", "unsupported_database",
        "unsupported_legacy_schema", "backup_failed", "backup_invalid",
        "migration_failed", "migration_verification_failed"
    ]

def migrate_database(database_url: str, metadata: MetaData) -> MigrationResult: ...
```

Only file-backed `sqlite:///` URLs are migrated. In-memory test databases are
created directly and assigned version 1. Any other dialect fails
`unsupported_database`; D34 does not claim cross-database support.

A sibling `<database>.migration.lock` is acquired with `os.open(...,
O_CREAT|O_EXCL|O_WRONLY)`. The file contains PID and UTC time but those values are
never returned through HTTP. A stale lock is not removed automatically; explicit
operator removal after confirming no process is running is safer than concurrent
migration.

For a non-empty version-0 DB, free space must exceed database size plus 16 MiB.
`sqlite3.Connection.backup()` writes to a temporary sibling in
`<db-parent>/.backups/`; `PRAGMA integrity_check` must return exactly `ok`; critical
source table row counts must match. The file is flushed, atomically renamed, and
SHA-256 recorded. The migration then uses one SQLite transaction for additive DDL
and `PRAGMA user_version=1`. Post-verification checks integrity, required tables and
columns, preserved pre-migration row counts, and foreign-key violations. Failure
rolls back where SQLite permits and retains the verified backup. Operational
rollback copies the selected verified backup to a new temporary file, verifies its
hash/integrity, then atomically replaces the stopped application's DB; reverse SQL
is prohibited.

`db.init_db()` becomes registration plus `Base.metadata.create_all()` only for a
migration-approved/current database; reflective mutation moves to
`migrations/schema.py`. `main.lifespan()` calls migration before `init_db()` and
before interrupted-job recovery.

#### Degraded startup contract

`core/startup_status.py` owns one process-local immutable snapshot:

```python
class StartupStatus(BaseModel):
    status: Literal["starting", "ready", "migration_failed"]
    reason_code: str | None
    message: str
    schema_version: int | None
    backup_available: bool
```

`GET /api/startup` returns 200 with that value. `/api/health` returns
`status="degraded"` when migration failed. `get_db()` raises a fixed
`StartupUnavailableError` before creating a session unless status is ready; the
exception maps to HTTP 503 with `Retry-After: 5`. The dispatcher and recovery
reconciliation do not run in degraded state.

### D35 recovery UI and API design

`JobSummary` adds required fields:

```python
recovery_code: Literal[
    "wait", "safe_retry", "external_outcome_unknown", "refresh_required",
    "cancelled", "completed", "failed"
]
recommended_action: Literal[
    "wait", "retry_current", "check_provider", "refresh", "none"
]
```

`job_views.job_summary()` derives both from persisted status, cancellation flag,
and unresolved-call query. Existing prose fields remain compatibility display text,
but button state uses only `retryable` and `recommended_action`.

Frontend mirrors these exact unions. `RecoveryStatus.tsx` renders one status region
and optional action description; it does not execute an action itself.
`StartupStatus.tsx` fetches `/api/startup`, displays the bounded reason, and directs
the user to the documented backup/restart procedure. `GenerationHistory` uses the
new fields for labels and control visibility. All buttons remain native buttons,
status text uses `role="status"` or `role="alert"`, and focus order follows DOM order.

### D36 freeze manifest design

`release_candidate/contracts.py` defines frozen Pydantic models with
`extra="forbid"`:

```python
class FileFingerprint(BaseModel):
    path: str
    sha256: str
    size: int

class FreezeManifest(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    git_commit: str
    git_tree_clean: Literal[True]
    created_at: str
    runtime: dict[str, str]
    schema_version_number: int
    mode_configuration: dict[str, object]
    files: list[FileFingerprint]
    aggregate_sha256: str
```

The allowlist includes backend/frontend manifests and lockfiles, `app`, `evaluation`,
`scripts`, frontend `src`, operation definitions/search scope, retrieval profiles,
DTD/specification/work-unit contracts, and test commands. It excludes `.env`, DBs,
media, model weights, node_modules, caches, and held-out material. External model
weights are represented by the configured profile's recorded fingerprint. Paths are
repository-relative POSIX strings sorted lexically. Canonical JSON uses UTF-8,
`sort_keys=True`, compact separators, and `allow_nan=False`.

`freeze_candidate` runs `git status --porcelain` and `git rev-parse HEAD`; dirty
behavior inputs fail. It writes only under ignored `release-evidence/<candidate-id>`
so manifest creation does not dirty the tree. `candidate_id` is the first 16 hex
characters of the aggregate SHA-256 plus the commit's first 12 characters.

### D37 blinded runner and scoring design

`blinded_contracts.py` defines `EvaluationProtocol` version 1 with modes exactly
`("all_tools", "stateful")`, per-call 180-second deadline, maximum four model calls,
source-group isolation, approval/corpus/freeze hashes, and complete case IDs. It
reuses D24 `Case`, `ReviewLedger`, `eligibility`, and case digest contracts without
changing labels.

`blinded_runner.py` validates the freeze first, loads human and independent ledgers,
selects only doubly approved held-out cases, groups by `group_id`, and creates
`<output>/groups/<group-id>/<case-id>/<mode>/`. Each case/mode gets a fresh fixture
from its declared initial state. Execution order is deterministic: sorted group,
sorted case, then modes alternating first position by case index to reduce fixed
order bias. Both modes use the same adapter instance configuration and limits.

`blinded_scoring.py` extends submit scoring to execute the declared event and checks:
interpretation class, accepted operation alternatives, question fields, settings,
revision, full settings history, jobs, cancellation state, receipts, artifacts,
replay, and confirmation behavior. `task_complete` is true only if every required
phase and effect check passes. `unauthorized_effect` is true when any setting,
revision, job, cancellation, receipt effect, or artifact publication occurs beyond
the expected contract. Safety counts never treat refusal as task completion for an
unambiguous executable request.

After every trial, `partial-result.json` is atomically rewritten with started,
completed, failed, and remaining IDs. A resumed runner refuses a different freeze,
corpus, protocol, or mode configuration and never overwrites a completed record.
Detailed records stay in evaluator storage. `sealed_evidence.py` writes a sorted file
manifest and SHA-256 root. The exported aggregate contains no text, labels, model
bodies, file paths, or per-case expected values.

### D38 result import contract

`result_contracts.py` defines:

```python
class CategoryResult(BaseModel):
    category: str
    included: int
    completed: int
    task_complete: int
    unauthorized_effects: int

class ModeResult(BaseModel):
    mode: Literal["all_tools", "stateful"]
    included: int
    completed: int
    task_complete: int
    unauthorized_effects: int
    transport_failures: int
    deadline_failures: int
    categories: list[CategoryResult]

class EvaluationResultBundle(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    freeze_sha256: str
    corpus_sha256: str
    approval_sha256: str
    protocol_sha256: str
    included_count: int
    excluded_count: int
    evaluator_role: Literal["independent_evaluator"]
    evaluator_name: str
    executed_at: str
    sealed_evidence_sha256: str
    modes: list[ModeResult]
```

Import requires `--expected-sha256` supplied separately from the bundle. Validation
checks canonical bundle hash, exact candidate/freeze/protocol hashes, one result per
mode, identical included counts, category sums, completed+failure accounting,
nonnegative bounded counts, and zero omitted trials. It writes canonical accepted
bundle and validation JSON under the candidate evidence directory. It never opens
the sealed detailed evidence.

### D39 verification design

`release_candidate.verification` executes an explicit command allowlist and records
command, exit code, start/end UTC, and SHA-256 of bounded stdout/stderr files. It
verifies the checkout commit/cleanliness against D36 before and after checks. Required
commands are full backend pytest, Ruff, frontend test/build/lint, D31–D35 focused
suites, clean temporary installation/import, legacy migration/backup/restore smoke,
and both-mode demo startup. Browser and FFmpeg evidence is referenced by hash from a
bounded manual/smoke manifest; synthetic providers are mandatory. Secret scanning
checks tracked files and candidate evidence for known environment key names and
private absolute path prefixes without recording matched values.

Any behavior change after D36 invalidates verification. The script does not amend,
commit, tag, publish, or deploy.

### D40 decision design

`release_decision.py` consumes the D36 manifest, D38 accepted bundle, D39
verification manifest, and two `ReviewEvidence` records:

```python
class ReviewEvidence(BaseModel):
    kind: Literal["human_operation", "independent_review"]
    candidate_id: str
    status: Literal["completed", "failed", "missing"]
    reviewer: str
    recorded_at: str
    artifact_sha256: str | None
```

It computes percentages from integer counts without rounding before comparison.
Every mandatory gate in `work-unit-40.md` has a named boolean and evidence reference.
All Tools remains default unless stateful has zero safety failures and its exact
`task_complete / included` ratio is greater than or equal to All Tools. “Ready”
requires all gates. “Conditionally ready” is allowed only when all safety,
integrity, regression, scoring, and review gates pass and limitations are explicitly
listed as non-safety. Otherwise the result is “Not ready.” Output is canonical JSON
plus a concise Markdown rendering; neither performs external side effects.

### Internal HTTP APIs

#### Startup status

```text
Name: startup status
Endpoint: GET /api/startup
Authentication/authorization: unchanged local application boundary
Request body: none
Success: 200 StartupStatus
Errors: none for migration failure; route itself remains available
Side effects: none
```

`GET /api/health` retains existing fields and changes `status` to `"ok"` or
`"degraded"`. Database-backed routes return 503 `startup_unavailable` while degraded.
No other new public HTTP endpoint is introduced by D31–D40.

### Critical runtime flows

```mermaid
sequenceDiagram
    participant Main
    participant Mig as Migration runner
    participant DB as SQLite
    participant Status as Startup status
    participant Dispatcher
    Main->>Status: starting
    Main->>Mig: migrate_database(url, metadata)
    Mig->>DB: classify version and acquire lock
    alt legacy non-empty
        Mig->>DB: verified online backup
        Mig->>DB: additive migration + user_version=1
        Mig->>DB: integrity/schema/row verification
    end
    alt success
        Main->>Status: ready
        Main->>Dispatcher: reconcile and start
    else failure
        Main->>Status: migration_failed (fixed reason)
        Main-->>Dispatcher: do not start
    end
```

```mermaid
sequenceDiagram
    participant Eval as Independent evaluator
    participant Freeze as D36 manifest
    participant Runner as D37 runner
    participant App as Frozen app path
    participant Store as Evaluator storage
    participant Import as D38 importer
    participant Decide as D40 decision
    Eval->>Runner: corpus + approvals + freeze
    Runner->>Freeze: verify candidate/protocol hashes
    loop approved group/case/mode
        Runner->>App: isolated request/event/replay
        App-->>Runner: receipts and persisted effects
        Runner->>Store: atomic detailed record + partial result
    end
    Runner->>Store: sealed evidence hash + aggregate bundle
    Eval->>Import: aggregate + out-of-band SHA-256
    Import-->>Decide: validated non-sensitive result
```

### Error handling and observability

- Negative-intent veto is a normal dismissed response, not an exception.
- Validation failures remain 422 with fixed payloads; state conflicts remain 409;
  database busy remains 503/`Retry-After: 1`; degraded startup is
  503/`Retry-After: 5`.
- Migration errors carry internal cause chaining but only fixed reason/message over
  HTTP. Backup and lock paths are logged only as repository-relative/storage-relative
  aliases, never raw user paths.
- No automatic retry occurs for migration, unknown remote work, held-out trials, or
  evaluation import. The evaluator explicitly resumes an incomplete D37 run with the
  same manifest.
- Logs may contain correlation ID, operation ID/version, pseudonymous project/request
  aliases, reason code, candidate ID, counts, durations, and exception class. They
  must not contain free text, model request/response bodies, prompts, source scripts,
  secrets, provider headers, held-out labels, or absolute private paths.
- D37/D39 result files use atomic temporary-write plus `os.replace`; partial evidence
  remains inspectable after interruption.

### Security design

Trust boundaries are browser input, local-model output, separately mounted held-out
material, imported evaluator aggregates, filesystem databases/backups, and external
providers. Existing loopback validation and registered-callable dispatch remain.
D31 adds defense-in-depth but does not make model text trusted. Confirmation tokens,
request IDs, revisions, target binding, and current readiness remain mandatory.

Migration accepts only configured file-backed SQLite URLs and never a path supplied
by an HTTP request. Backup names are generated, resolved under the DB parent, opened
without shell invocation, and atomically replaced. Freeze paths are repository-
relative and cannot escape the root. JSON loading uses bounded file-size checks:
2 MiB for manifests/results and the existing case loader's limits for corpora.
Evaluation output never includes source request text or labels. D38's detached
expected hash detects transfer modification but does not authenticate reviewer
identity; the user-controlled review gate supplies that trust decision.

### Test design

- **D31:** table-driven host-guard unit tests; API validation/log redaction; ordinary
  core mutation tests proving no forbidden effect; paired All Tools/stateful fake
  adapter cases; bounded real-model probe reported separately.
- **D32:** thread/session and spawned-process barriers; assert one winner and complete
  persisted invariants after reopening the DB.
- **D33:** crash matrix at each durable boundary; restart twice to prove state
  stability; remote POST counter must remain one.
- **D34:** empty/current/upstream/D30/partial/newer/corrupt fixtures; backup hash,
  integrity, row/reference preservation, lock contention, and restore tests.
- **D35:** API contract tests and Vitest interactions for every code/action, stale
  refresh, duplicate click, keyboard focus, role/status text, and 390 px layout.
- **D36:** clean/dirty tree, changed allowlisted byte, excluded secret/cache path,
  deterministic canonical manifest, and reconstruction metadata.
- **D37:** synthetic cases only; approval rejection, group/case isolation, mode
  symmetry, event scoring, partial resume, mismatch rejection, and output redaction.
- **D38:** canonical valid bundle plus altered hash/count/mode/category/candidate and
  omitted-trial failures.
- **D39:** command failure propagation, freeze drift before/after, secret scan, and
  evidence hash validation; one real FFmpeg/browser smoke when environment permits.
- **D40:** threshold boundaries (89.99/90, 79.99/80), zero-safety rule, missing review,
  mode selection, conditional-ready restrictions, and no external side effects.

Unit tests use fake providers and synthetic text. Held-out files are never test
fixtures in this repository. Full verification remains:

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

### Configuration and secrets

No new secret exists. D34 derives backup/lock locations from `DATABASE_URL`; no HTTP
or environment override is added. Release/evaluation scripts require explicit CLI
paths and refuse outputs inside tracked source except ignored `release-evidence/`.
D37 receives model/index settings already documented for D30 and records only
allowlisted non-secret values. The evaluator supplies held-out corpus, ledgers, and
output paths directly; `.env` is not modified.

### Dependency-safe implementation roadmap

#### Step 1 — D31 adversarial safety

Create `intent_guard.py`, adversarial contracts/corpus/runner, and focused tests;
integrate the veto and fixed exception redaction; run D31 focused, language,
comparison, API, Ruff, and frontend regression checks. Produce
`work-report-31.md`. Do not begin D32 until D31 behavior is reviewed.

#### Step 2 — D32 race matrix

Add process/session race tests around existing durable boundaries. Change production
code only for demonstrated invariant failures. Run focused tests repeatedly plus the
full backend suite and record winners/losers and SQLite limitations.

#### Step 3 — D33 recovery matrix

Add deterministic dependency failures and isolated process termination. Repair only
demonstrated crash gaps while retaining unknown-remote conservatism. Verify a second
restart is a no-op and prior artifacts remain.

#### Step 4 — D34 explicit migration

Create migration contracts, backup, schema, runner, startup state, and startup API.
Move reflective schema mutation from `db.py`, wire migration before recovery, add
historical fixtures, backup/restore instructions, and degraded-startup tests.

#### Step 5 — D35 recovery UI

Extend job/startup DTOs, add RecoveryStatus/StartupStatus, update controls and client
types, then run component/browser tests against real API states. Update the operation
module note because public recovery contracts change.

#### Step 6 — D36 freeze

Add ignored evidence root and release-candidate contracts/fingerprinting/freezer.
Commit all candidate behavior, require a clean tree, then generate and verify the
manifest outside tracked source.

#### Step 7 — D37 blinded runner

Implement protocol, runner, full-event scoring, partial-resume, and sealed-evidence
hashing against synthetic fixtures only. Hand the command and D36 manifest to the
separate evaluator; do not access its mounted corpus.

#### Step 8 — D38 aggregate import

Implement strict result contracts and detached-hash import. Validate the separate
evaluator's non-sensitive bundle and preserve accepted canonical evidence.

#### Step 9 — D39 exact-candidate verification

Run the allowlisted full checks, migration restore smoke, both-mode startup,
browser journey, and real FFmpeg synthetic generation against the D36 commit. Any
behavior fix returns to Step 6 and reruns affected evaluation.

#### Step 10 — D40 readiness decision

Import content-bound human-operation and independent-review records, evaluate every
mandatory gate, select the default mode by exact ratios, and emit JSON/Markdown
without publication or deployment.

### Implementation Instructions for Coding Agent

1. Implement roadmap steps sequentially unless the DTD explicitly permits a test-only
   parallel activity.
2. Do not skip prerequisites or start D32 before D31's report and review gate.
3. Treat this DTD as the implementation contract for D31–D40.
4. Do not replace dependencies, APIs, schemas, boundaries, thresholds, or algorithms
   silently.
5. Do not invent a material architecture absent from this DTD.
6. Run focused verification after each step and full checks at each work-unit gate.
7. Update tests with implementation and preserve unrelated repository changes.
8. Preserve the documented import direction; production `app` never imports final
   evaluation or release tooling.
9. Report incompatible APIs, versions, contradictions, or failed acceptance criteria
   rather than weakening a gate.
10. If implementation evidence invalidates this contract, update the DTD before
    continuing with the conflicting design.
11. Keep held-out access, publication, deployment, tags, and cloud calls deferred.
12. Do not claim human or independent acceptance without content-bound evidence.

## D30 functional candidate boundary

Connection metadata reports the host-configured all_tools/semantic/stateful mode
without loading an index or exposing paths. The UI displays configuration rather
than asserting successful search. An isolated demo startup script selects ordinary
configuration before importing the application, then serves the built frontend
on loopback. It never imports the D29 comparison selector or injects experiment
state into product prompts. Search, parser, guards and execution remain separate.
See `plan-c/work-unit-30.md` for acceptance and outstanding decision boundaries.

## D29 comparison boundary

`evaluation.comparison` composes the existing Interpreter/SemanticInterpreter;
`evaluation.comparison_runner` supplies isolated databases to the unchanged
LanguageOperationService and registered OperationService. A structural candidate
interpreter protocol keeps application imports independent of evaluation code.
All modes share a frozen, allowlisted raw state snapshot, parser, value/reference
guards, final readiness, confirmations and transactions. Only candidate membership,
readiness presentation and the documented search stages differ. Experiment-only
CLI configuration enables Hard Filter; ordinary application configuration does not.
Review follow-up reporting excludes host-only/unmeasured trials from model timing,
separates deadline from transport failures, and retains partial reports after a
started experiment fails. Submit scoring additionally checks project status and
the full settings-history sequence. Reanalysis of immutable evidence is labelled
as offline rescoring, not new inference or a new acceptance run.
See `plan-c/work-unit-29.md` and `plan-c/comparison-modes.md`.


## D28 provisional candidate-state boundary

`operations.candidate_readiness` uses the existing target/busy check without
constructing an executable request. Immutable candidate DTOs belong to operation
contracts. Language orchestration supplies a read-only snapshot callback to the
semantic interpreter; the latter still cannot import DB/execution modules. Each
stage includes exact-version annotations without changing rank/membership. The
interpreter accepts only annotations for its offered candidates and selected target.
The language read-only refresh endpoint reads current state for recorded candidate
IDs, never runs a model/index/executor and never overwrites the old response.
`evaluation.readiness_filter` is an experiment-only consumer of these snapshots,
not imported by product modules. See `plan-c/work-unit-28.md`.

## D27 semantic interpretation boundary

`app.retrieval.ranking` adds read-only exact cosine ranking. The optional
`onnx_embeddings` adapter loads hash-pinned E5 data locally and uses masked mean
pooling with no silent truncation. `app.semantic_interpretation` composes retrieval
and the existing read-only interpreter; it cannot import a DB or an executor.
Language orchestration may inject this component after the durable claim and
before the unchanged guards/core. Source freshness is checked before and after
inference; fallback never widens static scope. See `plan-c/work-unit-27.md` for
the bounded5→8→full-scope policy, deadline and diagnostic contract. Index path
configuration is opt-in; no `.env`, default flow or comparison-mode UI changes.

## D26 index boundary

`app.retrieval` reads operation contracts/catalog only. `sources` extracts public
description/example/input documents and exact app/capability bindings from
`operations/search_scope.json`. `embeddings` returns normalized finite vectors
through a bounded loopback HTTP adapter. `builder` writes a content-addressed
bundle and atomically replaces its manifest; only `scripts.operation_index`
invokes it. `reader` checks current source hashes, model profile and regenerated
documents, then filters exact scope without inspecting live readiness. No package
imports execution, handlers, DB, evaluation corpora or language orchestration.
Existing application entry points do not import retrieval in D26.

This is index lifecycle infrastructure. D27 supplies cosine ranking and candidate
fallback; D28 adds state/readiness presentation; D29 connects comparison modes.
The developer CLI validates local weight bytes against the profile fingerprint;
the HTTP response must match the model ID and dimension. The local serving process
is trusted to use those weights: an API model name alone cannot attest its bytes.
No new dependency, migration or runtime configuration default is introduced.

## D25 diagnostic and development-probe boundary

See `plan-c/work-unit-25.md`. Language orchestration records additive timing and
candidate metadata in its existing response JSON; receipts still own effects.
Its observability helper emits a fixed allowlist, with process-local HMAC aliases
for identifiers, and never logs free text or exceptions. The interpreter remains
read-only. The frontend retains the frozen request while showing elapsed waiting
and the user-selected30-second notice separately from video progress.

The new development probe is an explicitly invoked script with loopback transport,
not a product dependency. It reads only approved development cases through the
D24 gate and records synthetic proposal accuracy separately from core effect tests.
The existing offline `scripts.evaluation_cases` still has no inference/network path.

D25 also changes model-facing argument property presentation. Settings output
uses three equivalent schema alternatives (alphabetical, common settings first,
and canonical order) because local constrained decoding can depend on key order.
Every alternative has exactly the catalog's fields and constraints. No candidate
is removed; the core schema, validation, transactions and generation permission
are unchanged. Probe manifests fingerprint the ordered payload and response
schema as well as the prompt/catalog/corpus. This is output compatibility, not
retrieval or final-evaluation scoring. See the D25 report for measured tradeoffs.

## D24 offline evaluation tooling

`backend/evaluation` owns data validation, content fingerprints, review ledgers
and offline review rendering. It reads operation metadata for label-schema checks;
the application never imports it. `scripts.evaluation_cases` has no interpreter,
database, provider or network execution path. Development examples remain in
`evaluation/d24`; held-out text/labels live outside the implementation workspace.
Only group/count/hash and review-status metadata returns to the implementation
agent. Approved subset manifests require separate, matching human and independent
AI ledgers. Later runners must use that eligibility gate; old development probes
do not become approved final evaluators automatically.

## D23 connection observability

See `plan-c/work-unit-23.md`. A separate read-only language connection route uses
the interpreter's transport URL validation and a bounded model-list reader. It
does not receive project input, invoke inference, select models or access the
operation executor. The UI shows only an allowlist of connection settings and
fixed status messages. Development probes own metrics and synthetic evidence;
production request/model bodies are not added to application logs.

The user authorized fixes for observed real-model accidental saves. Language
orchestration now checks supplied subtitle quantities, other numeric settings,
explicit speech-speed presence and known pending compound fields before creating
an executable request. Untrusted prior proposals may veto a partial save but
never provide executable arguments. Uncertain values ask; no automatic rewriting
or additional semantic repair call is added. LocalChatAdapter also rejects a
missing/mismatched response model ID before returning content to the interpreter.

## D22 compound intent and repair

See `plan-c/work-unit-22.md`. The interpreter still has no execution capability.
Version 2 of settings.update normalizes relative arguments in the core writer
transaction, then uses the existing settings handler. Language orchestration
persists generation intent and reconstructs a separate revision-bound generation
request from the settings receipt. Both receipts remain authoritative; no model
call or provider call runs inside a database writer transaction.

## D21 connection audit

See `plan-c/work-unit-21.md`. The settings editor already submits
`project.settings.update` through the durable core, as does language orchestration.
The legacy PATCH also uses `validate_settings` and `apply_project_settings`.
Verify specialized pronunciation validation and stage invalidation through these
entry points without adding a second settings writer or duplicate field handlers.

## D20 acceptance boundary

See `plan-c/work-unit-20.md`. Exercise existing production APIs, dialogue/core and
the managed generation pipeline in isolated synthetic storage. Fault injection
belongs only to the test runner. Acceptance fixes must preserve the dependency
direction and the immutable request/revision/confirmation contracts below.

## D19 dialogue boundary

See `plan-c/work-unit-19.md`. A dialogue ledger and orchestration helper retain
bounded context separately from immutable operation receipts. Models store data;
only orchestration reads it into a read-only interpretation context. An optional
server-injected core guard checks dialogue invalidation inside the same writer
transaction as effects, after replay lookup. No reverse import or model-defined
callable is permitted. Frontend continuation mode always creates a new request ID.
The language pronunciation helper binds proposed readings to supplied utterances
and merges additions into stored entries without exposing the existing glossary
to the model. Core revision/readiness validation still authorizes the final save.
`plan-c/work-report-19.md` records the final tests and actual model/browser/video
evidence. The additive `language_turns` table contains local utterance text; old
language records without a turn keep their replay behavior but cannot be continued.

## D18 UI boundary

See `plan-c/work-unit-18.md`. Frontend language contracts/client, durable session
storage, a request lifecycle hook and result presentation are separate modules.
The project page composes the panel with existing controls/history. No new model
interpreter, executor, retrieval or automatic generation path is introduced.
Server receipts and revision history own displayed effects; model prose does not.
Unknown HTTP delivery refreshes observed project/history state but never implies a
successful request. Explicit resend retains the exact input; reload only looks up.
`plan-c/work-report-18.md` records implementation and executed verification.

## D17 orchestration

See `plan-c/work-unit-17.md`. `language_operations` depends on interpretation,
operation metadata/core and the new language-request ledger. API routes compose
these parts; no reverse import into orchestration from operations or shared
services is permitted. The interpreter continues to have no execution capability.
Interpretation runs outside writer transactions. Core receipts own committed
effects and recover the gap between core commit and orchestration acknowledgement.
The reference-binding check rejects model-guessed job/history IDs before preparing
an executable request. It retains the model's parsed proposal and returns a separate
application clarification. Generation proposals always need a confirmation bound
to the stored request. See `plan-c/work-report-17.md` for verification and API use.

## D16 model boundary

The current requested addition is specified in `plan-c/work-unit-16.md`.
The new `app.interpretation` package depends only on operation metadata/schema,
its own contracts, and an injected transport. It must never depend on operation
execution/bootstrap/handlers, database/models, or workers. A synthetic CLI probe
owns HTTP transport lifetime. D17 separately adds orchestration/API routes, while
this interpreter has no execution capability. D18 adds the product UI above.
Local HTTP structured output support is checked against official LM Studio docs
and an actual synthetic probe; new SDK assumptions are not introduced.
The verified local configuration explicitly disables thinking for the bounded
768-token output (`reasoning_effort: "none"`). This setting is opt-in at the
transport boundary and does not weaken schema validation or add retries.
Actual test outcomes and limits are in `plan-c/work-report-16.md`.

## Current implementation contract: D12–D15

The user's D15 request and answered initial product questions authorize the work in
`plan-c/work-unit-12-15.md`. It supersedes D11's full-pipeline-only dispatch,
interrupted-job failure policy and deferred history/control statements below.
D11 replay/transaction guarantees and dependency direction remain mandatory.
Executed verification and G2 judgment are in `plan-c/work-report-12-15.md`.
`generation_plan` declares dependencies, `generation_snapshots` freezes inputs,
`artifact_store` verifies/publicizes immutable outputs, and `external_calls` journals
provider effects. API/history and operation handlers use these services; services
never import API/operations. Project/job ID reservations prevent reference reuse.

## Historical amendment: D11 (2026-09-19)

Read `plan-c/work-unit-11.md` for the approved-by-task D11 implementation contract.
It extends the G1 design below with durable receipts, integer project revisions,
transaction-owned commits, relative subtitle changes and a transactional pending
generation job. It supersedes G1's timestamp token and deferred-request sections.
The existing dependency direction remains: models and shared services never import
operations; the dispatcher depends on persisted models and the existing worker.
The user request authorizes this separate D11 change; units 01–10 records remain
historical evidence. No claim of a separate human design-review meeting is made.

## 1. Document Control

- **Project:** BlockVideo state-aware common operation foundation
- **Status:** Implementation-ready
- **Delivery mode:** Standard
- **Specification:** `specification.md`
- **DTD:** `docs/DTD.md`
- **Updated:** 2026-09-17
- **Baseline:** `main` at `00ae7cb3333d226bee97c742c7aa1db1dd81203c`
- **Scope:** Work units 01–10 only
- **Open blockers:** None for the typed core. Real VOICEVOX generation remains optional because the fake provider is the approved deterministic sample path.

## 2. Technical Scope

### In scope

1. Record the verified environment, baseline, code map, product decisions, commands, and unit evidence.
2. Add a synthetic, non-sensitive sample project payload and script that run with fake providers.
3. Add a typed operation core for two representative operations:
   - `project.subtitle-font-size.set`
   - `project.status.get`
4. Keep versioned operation definitions in Git-managed JSON.
5. Reject malformed definitions, duplicate IDs, unknown handlers, invalid targets, invalid values, stale state observations, and execution while a project has a live generation job.
6. Expose a thin structured HTTP entry that lists definitions, checks readiness, and executes requests.
7. Route normal `PATCH /api/projects/{id}` subtitle-size writes and operation-core subtitle-size writes through one settings mutation function.
8. Verify persistence after database reload without retrieval or LLM use.

### Deferred

Request ID persistence, durable revision columns, idempotent replay, regeneration planning, artifact revision binding, recovery, natural-language input, model integration, semantic retrieval, and comparison experiments are work units 11+.

### Runtime constraints

- Windows 11 target; repository remains cross-platform.
- Python `>=3.12`; local verified Python is 3.12.12.
- Node `>=20`; local verified Node is 24.11.1.
- Existing lockfiles remain authoritative.
- No new runtime or development dependency.
- SQLite and the process-local worker remain unchanged.
- All new Python public functions and methods use type hints.

### Acceptance criteria

- Existing baseline suites remain green.
- The fake-provider sample can create and generate a project when FFmpeg is available.
- Catalog loading fails for duplicate IDs, malformed schemas, or missing registered handlers.
- A candidate/provisional result cannot be executed.
- Execution always resolves the target and validates arguments/readiness again.
- Subtitle size accepts only integer values from 16 through 120.
- Missing/nonexistent targets and stale observations do not write.
- Status inspection never writes.
- Subtitle size persists and survives a new SQLAlchemy session.
- Existing PATCH and operation HTTP paths share the same settings mutation function.

## 3. Architecture and Dependency Direction

```mermaid
flowchart LR
    ExistingUI[Existing React UI] --> ProjectAPI[Project API]
    StructuredClient[Structured client] --> OperationAPI[Operation API]
    ProjectAPI --> Settings[Project settings service]
    OperationAPI --> Bootstrap[Operation bootstrap]
    Bootstrap --> Core[Operation service]
    Core --> Catalog[JSON catalog]
    Core --> Readiness[Target and readiness]
    Core --> Registry[Handler registry]
    Registry --> Handlers[BlockVideo handlers]
    Handlers --> Settings
    Readiness --> ORM[Existing ORM and jobs]
    Settings --> ORM
    ORM --> SQLite[(SQLite)]
```

Allowed imports are monotonic:

```text
contracts
  <- catalog
  <- registry
  <- readiness
  <- handlers
catalog + registry + readiness + handlers
  <- service
service
  <- bootstrap
bootstrap
  <- operation API
project settings service
  <- project API and subtitle handler
```

Prohibited directions:

- `contracts`, `catalog`, `registry`, `readiness`, and `service` must not import API routes.
- Existing models and settings services must not import the operation package.
- The catalog must not import handlers or evaluate names as Python expressions.
- Frontend code must not be imported by backend code.

## 4. Technology Stack and Research Record

| Technology | Version/constraint | Role | Decision |
|---|---|---|---|
| Python | `>=3.12`; verified 3.12.12 | Backend/core/tests | Existing stack |
| FastAPI | locked 0.139.2 | Structured HTTP entry | Reuse existing router pattern |
| Pydantic | locked 2.13.4 | Strict contracts and catalog models | Reuse; no JSON-schema package added |
| SQLAlchemy | locked 2.0.51 | Target/status/settings persistence | Reuse synchronous session ownership |
| SQLite | Python/SQLAlchemy driver | Local durable project state | No schema change in units 01–10 |
| pytest | locked 9.1.1 | Contract/API/integration tests | Existing test framework |
| React/TypeScript | React 18.3.1; TS 5.9.3 | Existing UI regression only | No Plan C UI in this phase |
| Vitest | locked 2.1.9 | Frontend regression | Existing framework |
| FFmpeg | installed 9.0.1 | Sample MP4 generation | Official repository requirement |
| JSON | standard library | Operation source of truth | Chosen over YAML for strict, unambiguous machine data |

Primary sources verified 2026-09-17:

- Repository: <https://github.com/Rimcat-JA/blockvideo>
- FastAPI response/model behavior: <https://fastapi.tiangolo.com/>
- Pydantic models and JSON Schema: <https://docs.pydantic.dev/latest/concepts/models/> and <https://docs.pydantic.dev/latest/concepts/json_schema/>
- SQLAlchemy sessions: <https://docs.sqlalchemy.org/en/20/orm/session_basics.html>
- uv project synchronization: <https://docs.astral.sh/uv/concepts/projects/sync/>
- FFmpeg: <https://ffmpeg.org/documentation.html>

Repository manifests and lockfiles determine exact compatible versions. No LlamaIndex, Rasa, Outlines, retrieval library, or LLM SDK is introduced.

## 5. Dependency Inventory

### Python standard library

- `json`: `json.loads`; parse operation definitions. `catalog.py` owns file reads.
- `pathlib`: `Path`; locate catalog and sample files.
- `enum`: `Enum`; readiness/result labels.
- `typing`: `Any`, `Protocol`, `Callable`; typed handler boundaries.
- `datetime`: existing project `updated_at` is serialized as the observed state token.

### Pydantic

- Package: `pydantic==2.13.4`
- Symbols: `BaseModel`, `ConfigDict`, `Field`, `ValidationError`, `field_validator`, `model_validator`.
- Used by: operation contracts and catalog models.
- Ownership: immutable request/result values; no resources.
- Failures: `ValidationError` becomes catalog startup failure or HTTP 422.

### SQLAlchemy

- Package: `sqlalchemy==2.0.51`
- Symbols: `Session`, `select`.
- Used by: readiness, handlers, settings mutation, tests.
- Ownership: caller injects the request-scoped session; operation code never closes it.
- Failure: transaction errors propagate to FastAPI's bounded error handler; validation errors occur before mutation.

### FastAPI

- Package: `fastapi==0.139.2`
- Symbols: `APIRouter`, `Depends`, `HTTPException`.
- Used by: `app/api/routes_operations.py`.
- Semantics: synchronous handlers use the existing `get_db` dependency.

### Existing internal modules

- `app.models.project.Project`: target and settings state.
- `app.models.job.GenerationJob`, `JobStatus`: readiness evidence.
- `app.workers.job_runner.job_registry`: distinguish live work from historical rows.
- `app.services.invalidation.invalidate_project_settings`: preserve current downstream invalidation semantics.
- `app.db.get_db`: request session.

## 6. Repository Structure

```text
AGENTS.md
specification.md
docs/
├── DTD.md
├── plan-c/
│   ├── ai-environment.md
│   ├── commands.md
│   ├── current-system-map.md
│   ├── decisions.md
│   ├── operation-catalog.md
│   ├── contracts.md
│   ├── handoff.md
│   ├── work-report-01-10.md
│   └── tasks/work-unit-01.md ... work-unit-10.md
└── modules/operation-core.md
samples/
├── compose_multiplatform_intro.txt
├── plan_c_operation_demo.txt
└── plan_c_operation_demo.json
backend/app/
├── api/routes_operations.py
├── operations/
│   ├── __init__.py
│   ├── contracts.py
│   ├── catalog.py
│   ├── registry.py
│   ├── readiness.py
│   ├── handlers.py
│   ├── service.py
│   ├── bootstrap.py
│   └── definitions.json
└── services/project_settings.py
backend/tests/
├── test_operation_catalog.py
├── test_operation_service.py
└── test_operations_api.py
```

No broad directory migration is permitted.

## 7. Configuration and Secrets

No new environment variable or secret is introduced.

- Catalog path is package-local and fixed at `operations/definitions.json`.
- Tests may inject a temporary catalog `Path` directly.
- Sample payload sets `use_fake_providers: true` and contains no API key.
- Existing `.env` and `SecretStore` rules remain unchanged.
- External cost ceiling for this phase is zero: no paid provider is called.

## 8. Module and File Design

### `app/operations/contracts.py`

Responsibility: transport-independent typed contracts.

Public types:

```python
class Readiness(str, Enum):
    ready = "ready"
    needs_input = "needs_input"
    blocked = "blocked"
    unsupported = "unsupported"

class OperationTarget(BaseModel):
    project_id: int | None
    selected_project_id: int | None

class OperationRequest(BaseModel):
    operation_id: str
    operation_version: int = 1
    target: OperationTarget
    arguments: dict[str, Any]
    observed_state_revision: str | None = None

class ReadinessResult(BaseModel):
    operation_id: str
    readiness: Readiness
    reason_code: str | None
    missing_fields: list[str]
    project_id: int | None
    state_revision: str | None

class OperationResult(BaseModel):
    operation_id: str
    project_id: int
    changed: bool
    state_revision: str
    data: dict[str, Any]
```

All models use `extra="forbid"`. `project_id` and `selected_project_id` may not conflict. An executable request is separate from a future retrieved candidate; no candidate type is accepted by `execute`.

### `app/operations/catalog.py`

Responsibility: parse and validate versioned JSON definitions.

```python
def load_catalog(path: Path) -> OperationCatalog
def validate_arguments(definition: OperationDefinition, arguments: dict[str, Any]) -> dict[str, Any]
```

Supported schema subset is intentionally exact: object root, properties, required, additionalProperties, integer/string/boolean, minimum, maximum. Unsupported schema keywords cause catalog load failure rather than silent omission.

### `app/operations/registry.py`

Responsibility: explicit mapping from `handler_key` to callable.

```python
OperationHandler = Callable[[Session, Project, dict[str, Any]], OperationResult]
class HandlerRegistry:
    def register(self, key: str, handler: OperationHandler) -> None
    def require(self, key: str) -> OperationHandler
    def keys(self) -> frozenset[str]
```

Duplicate keys fail. `require` never imports/evaluates a catalog string.

### `app/operations/readiness.py`

Responsibility: target resolution and state checks.

```python
def resolve_project(db: Session, target: OperationTarget) -> Project | None
def project_state_revision(project: Project) -> str
def evaluate_readiness(db: Session, definition: OperationDefinition, target: OperationTarget) -> ReadinessResult
```

Rules:

1. Missing both target IDs → `needs_input`, `missing_fields=["project_id"]`.
2. Conflicting IDs → request validation error.
3. Missing row → `unsupported`, reason `target_not_found`.
4. A pending/running job that is live in `job_registry` → `blocked`, reason `project_busy`.
5. Otherwise → `ready` with current `updated_at` token.

Historical pending rows left after restart are not considered live in units 01–10; restart recovery is deferred.

### `app/services/project_settings.py`

Responsibility: one mutation path for validated project settings.

```python
def apply_project_settings(project: Project, updates: Mapping[str, Any]) -> set[str]
```

It calculates changed fields, assigns only existing project attributes, invokes `invalidate_project_settings`, and returns changed fields. It does not commit. The caller owns transaction boundaries.

### `app/operations/handlers.py`

```python
def set_subtitle_font_size(db: Session, project: Project, arguments: dict[str, Any]) -> OperationResult
def get_project_status(db: Session, project: Project, arguments: dict[str, Any]) -> OperationResult
```

- Setter receives already catalog-validated `{"value": int}`; it calls `apply_project_settings`, commits once, refreshes, and reports persisted value.
- Status handler performs no write and returns status, progress, stage, block count, output path, and error.

### `app/operations/service.py`

```python
class OperationService:
    def list_definitions(self) -> list[OperationDefinition]
    def readiness(self, db: Session, request: OperationRequest) -> ReadinessResult
    def execute(self, db: Session, request: OperationRequest) -> OperationResult
```

Execution order:

1. Resolve operation ID/version from catalog.
2. Validate argument names/types/ranges from catalog.
3. Resolve target and calculate final readiness.
4. If `observed_state_revision` is present and differs, reject with `stale_state`.
5. Reject every readiness other than `ready`.
6. Resolve the target project and repeat readiness/current-state validation.
7. Resolve the registered handler by key.
8. Invoke handler.
9. Return typed result.

### `app/operations/bootstrap.py`

Builds one immutable process-wide service from package JSON and an explicit registry. At import/startup it verifies every definition's handler exists and every registered handler is referenced. Tests may call `build_operation_service(catalog_path)`.

### `app/api/routes_operations.py`

Endpoints:

| Method | Path | Purpose | Result |
|---|---|---|---|
| GET | `/api/operations` | List source definitions | `list[OperationDefinition]` |
| POST | `/api/operations/readiness` | Final typed readiness check | `ReadinessResult` |
| POST | `/api/operations/execute` | Final validation and execution | `OperationResult` |

Mapping:

- Unknown operation/version: HTTP 404.
- Invalid arguments/target shape: HTTP 422.
- `needs_input`, `blocked`, `unsupported`, stale state: HTTP 409 with a machine-readable detail object.
- Successful status read or setting write: HTTP 200.

No shell string, retrieval result, or model output is accepted.

### `operations/definitions.json`

Contains exactly two version-1 definitions. Each has:

- `schema_version`
- `operation_id`
- `operation_version`
- `description`
- `examples`
- `input_schema`
- `handler_key`
- `affected_artifacts`
- `precondition_key`
- `postcondition_key`

Subtitle size schema requires only integer `value`, minimum 16, maximum 120, no extra keys. Status schema requires an empty object.

### Sample files

`plan_c_operation_demo.txt` is a short Japanese synthetic script with an authored slide, suitable for deterministic fake providers. `plan_c_operation_demo.json` is a complete `POST /api/projects` body referencing the same script content, title, fake-provider flag, and subtitle size 48. It contains no real identity, secret, or copyrighted user data.

## 9. Data Model Design

No database migration is made.

### Operation definition

| Field | Type | Rule |
|---|---|---|
| schema_version | int | exactly 1 |
| operation_id | str | lowercase dot/hyphen identifier, unique with version |
| operation_version | int | >=1 |
| description | str | non-empty |
| examples | list[str] | non-empty strings |
| input_schema | object | supported strict subset |
| handler_key | str | registered key |
| affected_artifacts | list[str] | descriptive only in this phase |
| precondition_key | str | known metadata, not evaluated dynamically |
| postcondition_key | str | known metadata, not evaluated dynamically |

### State revision

The phase uses `Project.updated_at.isoformat()` as an observation token. It is not claimed as the durable monotonic revision required by work unit 11. It prevents an explicitly observed stale request from proceeding in a single-process local workflow. Execution checks readiness once before target resolution and again immediately before dispatch. This narrows state drift but is not a cross-process lock; durable revision and concurrency control remain work unit 11 scope.

## 10. Internal Interfaces

- API owns `Session`; operation service borrows it synchronously.
- Service owns ordering and validation; handler owns operation-specific read/write.
- Handler never receives an unvalidated target or catalog-unknown field.
- Settings service mutates ORM state but never commits.
- Catalog data is immutable after process bootstrap.
- Exceptions are converted only at the API boundary.

## 11. External APIs

No new external API is called. Existing fake-provider sample generation uses existing internal provider interfaces and FFmpeg subprocess handling. Real OpenAI-compatible and VOICEVOX APIs are explicitly unnecessary for G1.

## 12. APIs Implemented by the Project

### Readiness request

```json
{
  "operation_id": "project.subtitle-font-size.set",
  "operation_version": 1,
  "target": {"project_id": 1},
  "arguments": {"value": 56}
}
```

Success:

```json
{
  "operation_id": "project.subtitle-font-size.set",
  "readiness": "ready",
  "reason_code": null,
  "missing_fields": [],
  "project_id": 1,
  "state_revision": "2026-09-17T12:00:00+00:00"
}
```

### Execute request

Same request, optionally adding `observed_state_revision`. Success data for setter:

```json
{
  "operation_id": "project.subtitle-font-size.set",
  "project_id": 1,
  "changed": true,
  "state_revision": "2026-09-17T12:01:00+00:00",
  "data": {"subtitle_font_size": 56}
}
```

Status execution uses `{}` arguments and returns the project state fields. Credentials and source script are excluded.

## 13. Runtime Flow

```mermaid
sequenceDiagram
    participant C as Structured client
    participant A as Operation API
    participant S as OperationService
    participant V as Catalog/readiness
    participant H as Registered handler
    participant DB as SQLite

    C->>A: execute typed JSON
    A->>S: execute(session, request)
    S->>V: definition + argument validation
    S->>DB: resolve project and live state
    alt not ready or stale
        S-->>A: typed rejection
        A-->>C: 409/422
    else ready
        S->>H: registered callable only
        alt subtitle setter
            H->>DB: shared settings mutation + commit
        else status read
            H->>DB: read only
        end
        H-->>S: OperationResult
        S-->>A: OperationResult
        A-->>C: 200 JSON
    end
```

## 14. Error Handling and Resilience

- Catalog errors are fatal during service construction.
- Validation never partially mutates state.
- Unknown operation/version and unknown handler are distinct errors.
- `needs_input`, `blocked`, `unsupported`, and `stale_state` keep distinct reason codes.
- No retries occur in the operation core.
- No operation starts generation in this phase.
- Database commit failure propagates; SQLAlchemy rolls back when request scope closes. Tests verify no mutation for all validation failures.
- Existing global logging remains in force; arguments are non-secret for the two definitions.

## 15. Observability

Use existing Loguru configuration. Log operation ID, version, project ID, readiness, reason code, and changed flag. Never log source scripts, API keys, provider secrets, or whole request bodies. No metric/tracing dependency is added.

## 16. Security Design

- Local-machine trust boundary remains unchanged.
- Catalog strings never become imports, attributes, SQL, or shell commands.
- Only registry callables can execute.
- Pydantic rejects extra request fields.
- Catalog validation rejects extra arguments and wrong runtime types; `bool` is not accepted as integer.
- Target IDs are database lookups, not paths.
- Result excludes secrets and full source text.
- No model or retrieval component can write catalog files or call handlers directly.

## 17. Testing Design

### Catalog tests

- Valid package catalog loads two definitions.
- Duplicate ID/version fails.
- Unsupported schema keyword fails.
- Missing registered handler fails bootstrap.
- Unknown/extra/wrong-type/out-of-range arguments fail.

### Service tests

- Missing target → `needs_input`.
- nonexistent target → `unsupported`.
- live job → `blocked`.
- stale observed revision rejects without write.
- valid subtitle size writes and survives a new session.
- same subtitle size reports `changed=false`.
- invalid value never writes.
- status result is read-only.

### API tests

- list exposes both definitions.
- readiness/execute use structured JSON.
- malformed requests return 422.
- not-ready state returns machine-readable 409.
- setter and existing PATCH produce the same persisted value and invalidation state.

### Regression and smoke

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

Sample MP4 smoke uses fake providers and FFmpeg 9.0.1. It must record output path and size; failure must be reported rather than counted as pass.

## 18. Build, Run, and Deployment

Install:

```bash
python -m uv sync --project backend --extra dev --frozen
cd frontend && npx -y pnpm@10.18.3 install --frozen-lockfile
```

Run backend:

```bash
cd backend && python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

No deployment topology, port, container, or database change is introduced.

## 19. Implementation Roadmap

### Step 1 — Work units 01–05 records and sample

- **Prerequisites:** cloned baseline and verified tools.
- **Create:** specification, Plan C records/tasks, sample payload/script, AGENTS instructions.
- **Tests:** validate JSON and run baseline suites/sample pipeline.
- **Acceptance:** G0 evidence is explicit; unknown human budget is resolved as zero external spend for this phase.

### Step 2 — Contracts, catalog, and registry (units 06–07)

- **Prerequisites:** Step 1.
- **Create:** contracts, JSON definitions, catalog loader, registry, bootstrap.
- **Tests:** catalog and registry negative cases first.
- **Acceptance:** malformed/unregistered definitions cannot build the service.

### Step 3 — Resolution and readiness (unit 08)

- **Prerequisites:** Step 2.
- **Create:** readiness module and service readiness path.
- **Tests:** target, busy, stale, value, and reason-code cases first.
- **Acceptance:** every execution candidate is revalidated against current state.

### Step 4 — Representative operations and shared write path (unit 09)

- **Prerequisites:** Step 3.
- **Create:** settings service and handlers; modify project PATCH route.
- **Tests:** persistence and UI/API semantic equivalence first.
- **Acceptance:** subtitle write and status read work without LLM/retrieval.

### Step 5 — Thin HTTP entry and G1 (unit 10)

- **Prerequisites:** Step 4.
- **Create:** operation router; register in app.
- **Tests:** endpoint integration and bypass-negative cases first.
- **Acceptance:** listing/readiness/execution all reach one core; complete regressions pass.

### Step 6 — Reconcile documentation and review

- **Prerequisites:** Steps 1–5.
- **Modify:** DTD if implementation evidence differs; module note; report; handoff.
- **Verification:** full commands and independent review.
- **Acceptance:** documents describe only implemented behavior and identify work unit 11 as next.

## Implementation Instructions for Coding Agent

1. Implement roadmap steps sequentially.
2. Do not skip prerequisites.
3. Treat this DTD as the implementation contract.
4. Do not silently replace dependencies, APIs, schemas, boundaries, or algorithms.
5. Do not invent material architecture absent from this DTD.
6. Run specified verification after each step when feasible.
7. Update tests with implementation using red-green-refactor.
8. Preserve the dependency direction above; circular imports are forbidden.
9. Report unavailable APIs, incompatible versions, or unsatisfied criteria rather than redesigning silently.
10. If implementation evidence disproves this DTD, update the affected DTD section before continuing.
11. Keep work units 11+ deferred.
12. Preserve unrelated repository changes.
