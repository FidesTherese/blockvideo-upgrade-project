"""Lease-bound SQLite migration runner and offline backup restore."""
from __future__ import annotations

import os
import shutil
import sqlite3
import stat
import uuid
from contextlib import closing
from pathlib import Path

from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

from app.migrations.backup import (
    backup_metadata_path,
    create_verified_backup,
    fsync_directory,
    parse_backup_metadata,
    sha256_file,
    target_database_path_sha256,
)
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
_MAX_METADATA_BYTES = 1024 * 1024
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


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
                lease.assert_held_for(database_url)
                backup = create_verified_backup(
                    database_path, connection, metadata, before, version
                )

            lease.assert_held_for(database_url)
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


def _require_regular_file(path: Path) -> os.stat_result:
    try:
        result = path.lstat()
    except OSError as exc:
        raise MigrationError("backup_invalid") from exc
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
        raise MigrationError("backup_invalid")
    return result


def _validate_backup_location(database_path: Path, backup_path: Path) -> None:
    backup_root = database_path.parent / ".backups"
    try:
        root_stat = backup_root.lstat()
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise MigrationError("backup_invalid")
        if backup_path.parent.resolve(strict=True) != backup_root.resolve(strict=True):
            raise MigrationError("backup_invalid")
        if backup_path.resolve(strict=True).parent != backup_root.resolve(strict=True):
            raise MigrationError("backup_invalid")
    except MigrationError:
        raise
    except OSError as exc:
        raise MigrationError("backup_invalid") from exc


def _stable_file_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _open_verified_regular(path: Path, expected: os.stat_result) -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise MigrationError("backup_invalid") from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
    ):
        os.close(descriptor)
        raise MigrationError("backup_invalid")
    return descriptor


def _read_metadata(path: Path) -> bytes:
    expected = _require_regular_file(path)
    if expected.st_size > _MAX_METADATA_BYTES:
        raise MigrationError("backup_invalid")
    descriptor = _open_verified_regular(path, expected)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(_MAX_METADATA_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > _MAX_METADATA_BYTES:
        raise MigrationError("backup_invalid")
    return raw


def _copy_backup_to_temp(backup_path: Path, temporary_path: Path) -> None:
    expected = _require_regular_file(backup_path)
    descriptor = _open_verified_regular(backup_path, expected)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            with temporary_path.open("xb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
    finally:
        os.close(descriptor)


def _validate_restore_candidate(
    path: Path,
    metadata: MetaData,
    expected_schema_version: int,
    expected_identities: dict[str, TableIdentity],
) -> None:
    try:
        with closing(sqlite3.connect(path)) as connection:
            if not _integrity_is_ok(connection):
                raise MigrationError("backup_invalid")
            version_row = connection.execute("PRAGMA user_version").fetchone()
            version = int(version_row[0]) if version_row else 0
            if version != expected_schema_version:
                raise MigrationError("backup_invalid")
            classify_v0(connection, metadata)
            validate_critical_references(connection)
            if critical_identity_snapshot(connection, metadata) != expected_identities:
                raise MigrationError("backup_invalid")
    except MigrationError as exc:
        raise MigrationError("backup_invalid") from exc
    except sqlite3.Error as exc:
        raise MigrationError("backup_invalid") from exc


def restore_database_backup(
    database_url: str,
    backup_path: Path,
    expected_sha256: str,
    metadata: MetaData,
) -> None:
    """Restore one target-bound backup after complete offline validation."""
    lease = acquire_database_lease(database_url)
    temporary_path: Path | None = None
    try:
        database_path = lease.database_path
        lease.assert_held_for(database_url)
        _validate_backup_location(database_path, backup_path)
        backup_stat = _require_regular_file(backup_path)
        metadata_path = backup_metadata_path(backup_path)
        _require_regular_file(metadata_path)
        parsed = parse_backup_metadata(_read_metadata(metadata_path))
        if (
            parsed.target_database_path_sha256
            != target_database_path_sha256(database_path)
            or parsed.backup_sha256 != expected_sha256
        ):
            raise MigrationError("backup_invalid")

        temporary_path = database_path.with_name(
            f".{database_path.name}.restore.{uuid.uuid4().hex}.tmp"
        )
        _copy_backup_to_temp(backup_path, temporary_path)
        if sha256_file(temporary_path) != expected_sha256:
            raise MigrationError("backup_invalid")
        if _stable_file_identity(backup_path.lstat()) != _stable_file_identity(
            backup_stat
        ):
            raise MigrationError("backup_invalid")
        _validate_restore_candidate(
            temporary_path,
            metadata,
            parsed.source_schema_version,
            parsed.source_critical_identities,
        )

        for suffix in _SQLITE_SIDECAR_SUFFIXES:
            lease.assert_held_for(database_url)
            sidecar = Path(f"{database_path}{suffix}")
            try:
                sidecar.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise MigrationError("backup_invalid") from exc
        fsync_directory(database_path.parent)

        lease.assert_held_for(database_url)
        os.replace(temporary_path, database_path)
        temporary_path = None
        with database_path.open("r+b") as target:
            target.flush()
            os.fsync(target.fileno())
        fsync_directory(database_path.parent)

        if sha256_file(database_path) != expected_sha256:
            raise MigrationError("backup_invalid")
        _validate_restore_candidate(
            database_path,
            metadata,
            parsed.source_schema_version,
            parsed.source_critical_identities,
        )
    except MigrationError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise MigrationError("backup_invalid") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        lease.release()
