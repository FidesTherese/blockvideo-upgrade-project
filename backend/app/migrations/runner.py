"""Lease-bound SQLite migration runner and offline backup restore."""
from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

from app.migrations.backup import create_verified_backup, sha256_file
from app.migrations.contracts import MigrationError, MigrationResult, TableIdentity
from app.migrations.lease import DatabaseLease, acquire_database_lease
from app.migrations.schema import (
    CRITICAL_TABLES,
    apply_v0_to_v1,
    classify_v0,
    critical_identity_snapshot,
    validate_critical_references,
)

_SQLITE_ASCII_FOLD = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"
)


def _canonical(identifier: str) -> str:
    return identifier.translate(_SQLITE_ASCII_FOLD)


def _quote(identifier: str) -> str:
    return sqlite_dialect().identifier_preparer.quote(identifier)


def _identifier_map(identifiers: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for identifier in identifiers:
        key = _canonical(identifier)
        if key in result:
            raise MigrationError("migration_verification_failed")
        result[key] = identifier
    return result


def _validate_current_schema(
    connection: sqlite3.Connection, metadata: MetaData
) -> None:
    observed_tables = _identifier_map(
        [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
    )
    for expected_table in metadata.tables.values():
        actual_table = observed_tables.get(_canonical(expected_table.name))
        if actual_table is None:
            raise MigrationError("migration_verification_failed")
        observed_columns = _identifier_map(
            [
                str(row[1])
                for row in connection.execute(
                    f"PRAGMA table_info({_quote(actual_table)})"
                )
            ]
        )
        if any(
            _canonical(column.name) not in observed_columns
            for column in expected_table.columns
        ):
            raise MigrationError("migration_verification_failed")


def _integrity_is_ok(connection: sqlite3.Connection) -> bool:
    return connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


def _verify_database(
    connection: sqlite3.Connection,
    metadata: MetaData,
    before: dict[str, TableIdentity],
) -> None:
    if not _integrity_is_ok(connection):
        raise MigrationError("migration_verification_failed")
    classify_v0(connection, metadata)
    _validate_current_schema(connection, metadata)
    validate_critical_references(connection)
    after = critical_identity_snapshot(connection, metadata)
    for table, identity in before.items():
        if after.get(table) != identity:
            raise MigrationError("migration_verification_failed")
    for table in set(CRITICAL_TABLES) - set(before):
        identity = after.get(table)
        if identity is None or identity.row_count != 0:
            raise MigrationError("migration_verification_failed")


def migrate_database(
    database_url: str,
    metadata: MetaData,
    *,
    lease: DatabaseLease | None,
) -> MigrationResult:
    """Classify, back up, migrate, and verify one lease-bound SQLite database."""
    if lease is None:
        raise MigrationError("database_lease_unavailable")
    lease.assert_held_for(database_url)
    database_path = lease.database_path

    try:
        with closing(sqlite3.connect(database_path)) as connection:
            version_row = connection.execute("PRAGMA user_version").fetchone()
            version = int(version_row[0]) if version_row else 0
            if version > 1:
                raise MigrationError("schema_too_new")
            if version < 0:
                raise MigrationError("unsupported_legacy_schema")

            classify_v0(connection, metadata)
            table_count_row = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()
            table_count = int(table_count_row[0]) if table_count_row else 0

            if version == 1:
                before = critical_identity_snapshot(connection, metadata)
                _verify_database(connection, metadata, before)
                return MigrationResult(
                    status="current",
                    from_version=1,
                    to_version=1,
                    backup_created=False,
                    backup_sha256=None,
                )

            validate_critical_references(connection)
            before = critical_identity_snapshot(connection, metadata)
            backup = None
            if table_count:
                backup = create_verified_backup(
                    database_path, connection, metadata, before
                )

            apply_v0_to_v1(connection, metadata)
            _verify_database(connection, metadata, before)
            return MigrationResult(
                status="migrated" if table_count else "created",
                from_version=0,
                to_version=1,
                backup_created=backup is not None,
                backup_sha256=backup.sha256 if backup is not None else None,
            )
    except MigrationError:
        raise
    except sqlite3.Error as exc:
        raise MigrationError("migration_verification_failed") from exc


def restore_database_backup(
    database_url: str, backup_path: Path, expected_sha256: str
) -> None:
    """Restore a hash- and integrity-verified backup while owning the DB lease."""
    lease = acquire_database_lease(database_url)
    temporary_path: Path | None = None
    try:
        database_path = lease.database_path
        temporary_path = database_path.with_name(
            f".{database_path.name}.restore.{uuid.uuid4().hex}.tmp"
        )
        try:
            with backup_path.open("rb") as source, temporary_path.open("xb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            if sha256_file(temporary_path) != expected_sha256:
                raise MigrationError("backup_invalid")
            with closing(sqlite3.connect(temporary_path)) as connection:
                if not _integrity_is_ok(connection):
                    raise MigrationError("backup_invalid")
            os.replace(temporary_path, database_path)
            temporary_path = None
        except MigrationError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise MigrationError("backup_invalid") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        lease.release()
