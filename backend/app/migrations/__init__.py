"""Dependency-isolated SQLite migration interfaces."""
from app.migrations.contracts import MigrationError, MigrationResult, TableIdentity
from app.migrations.lease import DatabaseLease, acquire_database_lease
from app.migrations.schema import (
    apply_v0_to_v1,
    classify_v0,
    critical_identity_snapshot,
    sqlite_affinity,
    validate_critical_references,
)

__all__ = [
    "DatabaseLease",
    "MigrationError",
    "MigrationResult",
    "TableIdentity",
    "acquire_database_lease",
    "apply_v0_to_v1",
    "classify_v0",
    "critical_identity_snapshot",
    "sqlite_affinity",
    "validate_critical_references",
]
