# D34 — Versioned migration and rollback compatibility

## Goal

Make local SQLite schema evolution explicit, reproducible, backed up, and testable
from historical BlockVideo databases.

## Scope

- Add a small ordered migration layer using Python, SQLAlchemy, and SQLite already
  present in the project; do not add Alembic for this local scope.
- Record and validate a schema version. Reject unknown newer schemas.
- Acquire one non-blocking exclusive database lease before migration and hold it for
  the full application lifetime, including degraded startup, until database users
  stop at shutdown. The cached SQLAlchemy engine/pool and sessionmaker are scoped to
  that lease: after dispatcher and registry drain, mark startup non-ready, dispose
  and clear the caches without DDL, then release the lease as the final database
  lifecycle action.
- Create and verify a database backup before applying pending migrations. Hash,
  integrity-check, identity-check, and fsync temporary bytes before atomic publication;
  require a live-lease callback immediately before each backup/metadata replacement,
  rehash published bytes, and atomically/fsynced publish canonical target-bound metadata.
  Lease loss must remove every temporary or partially published pair.
- After creating `.backups`, reject a symlink, Windows reparse point, or non-directory,
  and require its strict resolved path to equal the canonical database-parent sibling
  before writing backup bytes.
- Apply ordered additive migrations transactionally where SQLite permits it and only
  while the application owns that lease.
- Build a scratch current-schema SQLite database from registered metadata and apply one
  reusable version-aware compatibility check. Version 1 requires every registered table
  and column with its scratch affinity. Version 0 may omit tables and additive
  nullable/defaulted columns, but an existing known table missing a non-null column
  without a server default is unsupported. After columns exist, derive exact required
  ordinary and unique column sets from `Table.indexes`, `UniqueConstraint`, and column
  `unique` metadata; inspect `PRAGMA index_list/index_info` with the same ASCII-only
  case folding; and create deterministic quoted named indexes only for missing sets.
  A unique index may satisfy an ordinary requirement for the same exact set, but an
  ordinary index never satisfies uniqueness. Preserve every existing index. Version 1
  rejects a missing required ordinary or unique set. Match known names with SQLite-compatible
  ASCII-only folding (A--Z to a--z, non-ASCII unchanged), preserve unknown extras and
  their actual spellings, and reject ASCII-case-colliding duplicate known identifiers
  before DDL. Semantic-reference presence checks use the same canonical keys; SQL quotes
  observed spellings.
- Freeze upstream and D30 ancestry fixtures as explicit historical SQL rather than
  deriving either schema by subtracting current metadata.
- For `projects`, `blocks`, `generation_jobs`, `operation_requests`, `external_calls`,
  `generation_artifacts`, `settings_revisions`, `language_requests`, and
  `language_turns`, compare pre/post exact row counts and canonical PK-identity
  digests using exact ordered PK columns from scratch current metadata; reject a missing,
  unreadable, or altered legacy PK. Validate declared FKs and every DTD-enumerated
  ownership/reference ID. A language request linked to an existing core receipt must
  have the same non-null project owner, and turn links must be explicitly reciprocal.
  Preserve the intentional non-FK project/job references in immutable receipts.
- Roll back operationally by restoring the verified pre-migration backup, not by
  destructive reverse SQL. Offline restore must acquire the same lease non-blocking
  and fail without touching the database when an application process is live. It
  accepts only regular non-symlink backup/metadata files under the exact target sibling
  `.backups`, validates canonical target binding, hash, version-aware schema
  compatibility, critical identity, integrity, and references, then removes stale
  `-wal`, `-shm`, and `-journal` files
  under the lease before atomic replacement and final fsync/reopen verification.
- Store the exact canonical lease payload at acquisition. Both ownership assertion and
  release read the retained descriptor and current path and require exact acquired bytes
  plus descriptor/path inode identity. In-place tampering invalidates ownership.
- Release a lease through an identity/payload-bound atomic owner tombstone. If a raced
  replacement is moved, restore it without overwrite or fail while retaining it; never
  delete another owner's lease.
- Create missing database parent directories before lock creation, then test empty,
  current, pre-Plan-C, interrupted, malformed, mixed-case, nested-path, and newer-version
  inputs, plus spawned-process app/app and app/restore exclusion.

## Non-goals

No automatic downgrade across released schemas, cross-database support, or migration
of private databases inside repository tests.

## Acceptance

Supported historical fixtures upgrade to the current schema without data loss and
remain usable. Partial v0 fixtures missing `generation_artifacts.job_id`,
`operation_requests.job_id`, and `language_turns.parent_request_id` regain their
metadata-defined unique indexes and reject duplicate non-null values. Every existing
known-column affinity exactly matches scratch current metadata; v1 rejects missing
required ordinary or unique index sets; critical row counts and PK identity digests
are unchanged; required references pass; unknown extras, existing indexes, and
intentional receipt non-FKs survive. Every backup
has a canonical target-bound metadata sidecar and identical pre/post-publication hash.
A failed or unsupported migration leaves the source restorable and produces a bounded
startup error with no secret/path leakage. Lease loss before either publication leaves
no backup or metadata partial, and a redirected/symlink/reparse/non-directory backup
root is rejected before writes. In-place lock tampering fails assertion and release.
Wrong-target, escaping, symlink, special, schema/identity/reference-incompatible restores fail before target mutation. Migration,
live use, and restore are mutually excluded across processes; contention returns
immediately, raced lease release preserves the other owner, and restore succeeds only
after the application lease is released. Between lifespans `get_db()` rejects access;
no cached connection survives lease release; and a second lifespan after offline
restore reads restored state rather than the replaced pre-restore inode.
