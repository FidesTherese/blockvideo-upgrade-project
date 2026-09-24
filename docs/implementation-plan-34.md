# D34 Versioned Migration and Rollback Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace reflective startup mutation with an explicit SQLite v0-to-v1 migration that creates a verified backup, preserves supported historical data, and degrades startup safely on failure.

**Architecture:** A dependency-isolated `app.migrations` package owns one non-blocking exclusive database lease. The application acquires it before migration and holds it through shutdown; classification, backup, migration, verification, and initialization all run while that lease is held. Offline restore acquires the same lease itself and fails without waiting while any application process is live. Process-local startup status gates database dependencies and exposes fixed `/api/startup` and degraded `/api/health` responses.

**Tech Stack:** Python 3.12 `sqlite3`, `hashlib`, `os`, `shutil`, SQLAlchemy 2 metadata/inspection, Pydantic 2, FastAPI, pytest.

## Global Constraints

- Follow `docs/plan-c/work-unit-34.md` and the D34 section/roadmap in `docs/DTD.md`.
- Supported schema versions are exactly 0 and 1; values above 1 fail `schema_too_new`.
- Support only `sqlite:///` file URLs plus in-memory test setup; no Alembic and no cross-database claim.
- Preserve unknown extra tables/columns; never drop, rename, or retype a column.
- Every existing known column must have the same SQLite affinity as its counterpart
  in a scratch current-schema DB built from registered metadata; any known-name
  affinity mismatch fails `unsupported_legacy_schema`.
- A non-empty v0 database is backed up and verified before migration.
- Startup calls `register_models()` before touching the database, acquires the application-lifetime database lease non-blocking, then runs `migrate_database()` and `init_db()`/`Base.metadata.create_all()` under that lease; interrupted-job recovery and dispatcher startup remain later, and the lease is released only after database users stop during lifespan shutdown.
- A degraded application retains the lease until shutdown. A second app process and offline restore fail immediately with `database_lease_unavailable`; they never wait, migrate, restore, or modify database bytes.
- Stale lease files are never removed automatically. Operator removal is allowed only after confirming no application or restore process is live.
- HTTP errors never expose raw database/backup/lease paths.
- Final delivery commit is `[DONE] Mission 34 Add explicit SQLite migration and rollback safety`.

---

### Task 1: Migration contracts, schema classification, and historical fixtures

**Files:**
- Create: `backend/app/migrations/__init__.py`
- Create: `backend/app/migrations/contracts.py`
- Create: `backend/app/migrations/lease.py`
- Create: `backend/app/migrations/schema.py`
- Create: `backend/tests/test_d34_migrations.py`
- Create: `backend/tests/fixtures/migrations/build_fixtures.py`
- Modify: `backend/app/db.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class TableIdentity:
    table: str
    row_count: int
    primary_key_columns: tuple[str, ...]
    primary_key_sha256: str

@dataclass(frozen=True)
class MigrationResult:
    status: Literal["created", "current", "migrated"]
    from_version: int
    to_version: int
    backup_created: bool
    backup_sha256: str | None

class MigrationError(RuntimeError):
    reason_code: Literal[
        "database_lease_unavailable", "schema_too_new", "unsupported_database",
        "unsupported_legacy_schema", "backup_failed", "backup_invalid",
        "migration_failed", "migration_verification_failed",
    ]

class DatabaseLease:
    database_path: Path
    lock_path: Path
    def assert_held_for(self, database_url: str) -> None: ...
    def release(self) -> None: ...

acquire_database_lease(database_url: str) -> DatabaseLease
apply_v0_to_v1(connection: sqlite3.Connection, metadata: MetaData) -> None
classify_v0(connection: sqlite3.Connection, metadata: MetaData) -> None
sqlite_affinity(declared_type: str) -> Literal["INTEGER", "TEXT", "BLOB", "REAL", "NUMERIC"]
critical_identity_snapshot(connection: sqlite3.Connection) -> dict[str, TableIdentity]
validate_critical_references(connection: sqlite3.Connection) -> None
register_models() -> None
init_db() -> None
```

`register_models()` imports every ORM model module exactly once and performs no DDL. `init_db()` assumes registration and migration have succeeded and performs only `Base.metadata.create_all()` for the approved/current schema.

- [ ] **Step 1: Write RED classification tests**

Generate deterministic temporary fixtures for empty v0, upstream/pre-Plan-C, D30,
partially additive, malformed known-column collision, current v1, and newer v2
databases. Build the expected schema only by registering all models and applying
`Base.metadata.create_all()` to a scratch SQLite DB. For every existing known column in any non-empty supported v0 or v1 database,
compare observed and scratch affinities using SQLite's ordered affinity rules. Add one
fixture per mismatching affinity family/name collision and assert
`unsupported_legacy_schema`; assert aliases/coercible values do not pass. Assert
missing known columns remain additive, unknown extra tables/columns survive, v1 is
unchanged, and v2 fails `schema_too_new`. Assert migration entry points reject a
missing, released, or different-database lease before opening or changing the
database.

- [ ] **Step 2: Run classification tests**

```bash
cd backend
python -m uv run pytest tests/test_d34_migrations.py -k "classify or schema_version" -q
```

Expected: FAIL because `app.migrations` does not exist.

- [ ] **Step 3: Implement additive schema operations**

Move `_add_missing_columns()` behavior from `app.db` into `apply_v0_to_v1()`.
Create the scratch schema from registered metadata, read both schemas with
`PRAGMA table_info`, and compare exact derived affinities before DDL. Quote
identifiers through SQLAlchemy's dialect preparer, create missing metadata tables,
add only nullable/defaulted columns, preserve unknown tables/columns, and set
`PRAGMA user_version=1` in the migration transaction. Split model import registration into side-effect-free `register_models()` and keep `init_db()` as `Base.metadata.create_all()` only; neither may inspect/alter an unapproved legacy schema.

- [ ] **Step 4: Run Task 1 tests and lint**

```bash
cd backend
python -m uv run pytest tests/test_d34_migrations.py -k "classify or schema_version or additive" -q
python -m uv run ruff check app/migrations app/db.py tests/test_d34_migrations.py tests/fixtures/migrations/build_fixtures.py
```

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/migrations backend/app/db.py backend/tests/test_d34_migrations.py backend/tests/fixtures/migrations/build_fixtures.py
git commit -m "feat: define D34 SQLite schema migration"
```

### Task 2: Verified backup, lock, migration runner, and restore

**Files:**
- Create: `backend/app/migrations/backup.py`
- Create: `backend/app/migrations/runner.py`
- Modify: `backend/tests/test_d34_migrations.py`

**Interfaces:**

```python
migrate_database(
    database_url: str, metadata: MetaData, *, lease: DatabaseLease
) -> MigrationResult
restore_database_backup(
    database_url: str, backup_path: Path, expected_sha256: str
) -> None
sha256_file(path: Path) -> str
```

- [ ] **Step 1: Write RED backup and lock tests**

Assert `<database>.migration.lock` is acquired with `O_CREAT|O_EXCL` and non-blocking semantics, includes only PID/UTC in its file, remains present for the lease lifetime, and is not removed as stale automatically. Hold a lease in one spawned process and prove a second process immediately receives `database_lease_unavailable` without opening or changing the database; after graceful release, acquisition succeeds. For non-empty v0 fixtures, assert free space must exceed DB bytes plus 16 MiB; backup
is written under `<db-parent>/.backups/`, passes `PRAGMA integrity_check == "ok"`,
and preserves exact row counts plus canonical PK identity digests for `projects`,
`blocks`, `generation_jobs`, `operation_requests`, `external_calls`,
`generation_artifacts`, `settings_revisions`, `language_requests`, and
`language_turns`. Assert the digest uses scratch PK order, typed integer/text values,
canonical sorted compact JSON, and SHA-256. Require the source, backup, and post-DDL
snapshots to agree for pre-existing tables; newly created critical tables are empty.
Assert backup is fsynced/atomically renamed and its SHA-256 equals
`MigrationResult.backup_sha256`.

- [ ] **Step 2: Write RED failure/restore tests**

Inject backup, DDL, post-identity, and post-reference verification failures. Assert
`PRAGMA foreign_key_check` is empty and explicit checks cover blocks/jobs -> project,
job parent -> job with equal project ownership, external call -> job, artifact ->
project/job with equal ownership, settings revision -> project/restored revision in
the same project, project current artifact -> same project, and language turn request/
parent/successor existence and reciprocal linkage. Assert receipt project/job IDs are
intentional non-FKs that may outlive deleted rows and remain unchanged, while an
existing referenced job must agree with the receipt project; language
request project/core IDs are correlation references that must agree when targets
exist but may be absent after deletion/no commit. Assert the source remains current
or restorable and the verified backup remains while the caller still holds the
application lease. Operational restore acquires the same database lease internally and non-blocking before reading the backup or opening/replacing the target, holds it through hash/integrity verification and `os.replace()`, and releases it in `finally`. Reject a modified backup. With a spawned application process holding the lease, assert restore immediately fails `database_lease_unavailable` and leaves target and backup bytes unchanged; after application shutdown, the same restore succeeds.

- [ ] **Step 3: Implement the runner and backup module**

Parse only file-backed SQLite URLs. `acquire_database_lease()` creates the sibling lease file exclusively and returns immediately on contention. `migrate_database()` requires and validates the caller-owned live lease and never releases it; it classifies `PRAGMA user_version`, backs up non-empty v0 databases with `sqlite3.Connection.backup()`, executes v0-to-v1, then verifies integrity, required tables/columns, exact pre/post critical-table row
counts and canonical PK identity digests, zero `PRAGMA foreign_key_check` rows, and
all DTD-enumerated semantic ID references. It does not reinterpret intentional
receipt/history non-FKs as mandatory live-row references. Empty databases may be created directly at v1 without a backup. `restore_database_backup()` owns a separately acquired lease for its entire offline operation and releases it in `finally`.

- [ ] **Step 4: Run migration tests**

```bash
cd backend
python -m uv run pytest tests/test_d34_migrations.py -q
python -m uv run pytest tests/test_operation_storage.py tests/test_job_recovery.py tests/test_d33_recovery_matrix.py -q
python -m uv run ruff check app/migrations tests/test_d34_migrations.py
```

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/app/migrations backend/tests/test_d34_migrations.py
git commit -m "feat: add verified migration backup and restore"
```

### Task 3: Degraded startup API and dispatcher gating

**Files:**
- Create: `backend/app/core/startup_status.py`
- Create: `backend/app/api/routes_startup.py`
- Create: `backend/tests/test_d35_startup_recovery_api.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/db.py`
- Modify: `backend/app/api/routes_health.py`

**Interfaces:**

```python
class StartupStatus(BaseModel):
    status: Literal["starting", "ready", "migration_failed"]
    reason_code: str | None
    message: str
    schema_version: int | None
    backup_available: bool

class StartupUnavailableError(RuntimeError):
    reason_code: Literal["startup_unavailable"] = "startup_unavailable"

get_startup_status() -> StartupStatus
set_startup_status(status: StartupStatus) -> None
reset_startup_status_for_tests() -> None
```

HTTP contracts:
- `GET /api/startup` always returns 200 `StartupStatus`.
- `GET /api/health` returns existing fields with `status="degraded"` after migration failure.
- Database dependencies return 503 with `{"detail":{"reason_code":"startup_unavailable","message":"データベースを利用できません。起動状態を確認してください。"}}` and `Retry-After: 5`.

- [ ] **Step 1: Write RED lifecycle/API tests**

Assert lifespan sets `starting` and calls, in exact order, `register_models()`, `acquire_database_lease(database_url)`, `migrate_database(database_url, Base.metadata, lease=lease)`, and `init_db()` before reaching `ready`, recovery, or dispatcher startup. Assert migration receives metadata containing every registered model table and the exact live lease. Keep the lease held while ready or migration-degraded, stop dispatcher/database users before releasing it in lifespan `finally`, and release it exactly once at normal/degraded shutdown. A later post-acquisition startup exception that aborts lifespan releases it in `finally`; lease-acquisition failure aborts startup without migration/recovery/dispatcher calls or a release attempt. While one spawned app lifespan holds the lease, assert a second app startup fails immediately. On each migration `MigrationError`, assert `init_db()`, `mark_interrupted_operation_jobs()`, and `run_operation_dispatcher()` are not called. Assert startup/health remain readable during migration-degraded operation while `/api/projects` returns the fixed 503.

- [ ] **Step 2: Implement startup state and routing**

Add `routes_startup.router`, map `StartupUnavailableError` in `create_app()`, and gate `get_db()` before session creation. Keep internal cause chaining in logs by exception class/reason only; expose no path.

- [ ] **Step 3: Run startup and migration regressions**

```bash
cd backend
python -m uv run pytest tests/test_d35_startup_recovery_api.py tests/test_d34_migrations.py tests/test_health.py tests/test_job_recovery.py -q
python -m uv run ruff check app/core/startup_status.py app/api/routes_startup.py app/api/routes_health.py app/main.py app/db.py tests/test_d35_startup_recovery_api.py
```

- [ ] **Step 4: Commit Task 3**

```bash
git add backend/app/core/startup_status.py backend/app/api/routes_startup.py backend/app/api/routes_health.py backend/app/main.py backend/app/db.py backend/tests/test_d35_startup_recovery_api.py
git commit -m "feat: degrade startup safely on migration failure"
```

### Task 4: Documentation and D34 gate

**Files:**
- Create: `docs/plan-c/work-report-34.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `docs/modules/operation-core.md`
- Modify: `specification.md` and `docs/DTD.md` if implementation evidence changes the approved contract

**Interfaces:**
- Document backup location derivation, application-lifetime lease handling, supported ancestry, reason codes, the non-blocking stopped-application restore requirement, stale-lease operator procedure, and verification evidence without private paths.

- [ ] **Step 1: Run full verification sequentially**

```bash
cd backend && python -m uv run pytest tests/test_d34_migrations.py tests/test_d35_startup_recovery_api.py -q
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

- [ ] **Step 2: Inspect and reconcile documentation**

```bash
git status --short
git diff --check
git ls-files .env storage release-evidence
```

Record fixture ancestry, scratch-schema affinity comparisons, every mismatch case,
backup hashes, the nine critical tables' pre/post row-count and PK-digest equality,
declared and semantic reference checks, intentional receipt non-FK survival,
injected failures, restore checks, and exact test counts. State D35 has not started.

- [ ] **Step 3: Commit and push the implementation task**

```bash
git add backend docs/plan-c/work-report-34.md docs/plan-c/handoff.md docs/modules/operation-core.md specification.md docs/DTD.md
git commit -m "[DONE] Mission 34 Add explicit SQLite migration and rollback safety"
git push
```

Do not tag, publish, deploy, or start D35 before review.
