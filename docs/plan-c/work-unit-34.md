# D34 — Versioned migration and rollback compatibility

## Goal

Make local SQLite schema evolution explicit, reproducible, backed up, and testable
from historical BlockVideo databases.

## Scope

- Add a small ordered migration layer using Python, SQLAlchemy, and SQLite already
  present in the project; do not add Alembic for this local scope.
- Record and validate a schema version. Reject unknown newer schemas.
- Create and verify a database backup before applying pending migrations.
- Apply ordered additive migrations transactionally where SQLite permits it.
- Validate critical table/column presence, row counts, identities, and references.
- Roll back operationally by restoring the verified pre-migration backup, not by
  destructive reverse SQL.
- Test empty, current, pre-Plan-C, interrupted, malformed, and newer-version inputs.

## Non-goals

No automatic downgrade across released schemas, cross-database support, or migration
of private databases inside repository tests.

## Acceptance

Supported historical fixtures upgrade to the current schema without data loss and
remain usable. A failed or unsupported migration leaves the source restorable and
produces a bounded startup error with no secret/path leakage.
