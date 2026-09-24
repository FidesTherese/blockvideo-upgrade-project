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
  stop at shutdown.
- Create and verify a database backup before applying pending migrations.
- Apply ordered additive migrations transactionally where SQLite permits it and only
  while the application owns that lease.
- Build a scratch current-schema SQLite database from registered metadata and require
  every existing known column's observed SQLite affinity to equal its scratch affinity;
  preserve unknown extra tables/columns and fail known-name affinity collisions.
- For `projects`, `blocks`, `generation_jobs`, `operation_requests`, `external_calls`,
  `generation_artifacts`, `settings_revisions`, `language_requests`, and
  `language_turns`, compare pre/post exact row counts and canonical PK-identity
  digests, then validate declared FKs and every DTD-enumerated ownership/reference ID.
  Preserve the intentional non-FK project/job references in immutable receipts.
- Roll back operationally by restoring the verified pre-migration backup, not by
  destructive reverse SQL. Offline restore must acquire the same lease non-blocking
  and fail without touching the database when an application process is live.
- Test empty, current, pre-Plan-C, interrupted, malformed, and newer-version inputs,
  plus spawned-process app/app and app/restore exclusion.

## Non-goals

No automatic downgrade across released schemas, cross-database support, or migration
of private databases inside repository tests.

## Acceptance

Supported historical fixtures upgrade to the current schema without data loss and
remain usable. Every existing known-column affinity exactly matches scratch current
metadata; critical row counts and PK identity digests are unchanged; required
references pass; unknown extras and intentional receipt non-FKs survive. A failed or unsupported migration leaves the source restorable and
produces a bounded startup error with no secret/path leakage. Migration, live use,
and restore are mutually excluded across processes; contention returns immediately,
and restore succeeds only after the application lease is released.
