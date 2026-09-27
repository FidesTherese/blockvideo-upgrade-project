"""Verified SQLite backup and file hashing operations."""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData

from app.migrations.contracts import MigrationError, TableIdentity
from app.migrations.schema import critical_identity_snapshot

_FREE_SPACE_GUARD_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class VerifiedBackup:
    path: Path
    sha256: str


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity_is_ok(connection: sqlite3.Connection) -> bool:
    return connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


def create_verified_backup(
    database_path: Path,
    source: sqlite3.Connection,
    metadata: MetaData,
    expected_identities: dict[str, TableIdentity],
) -> VerifiedBackup:
    """Create, verify, fsync, and atomically publish a pre-migration backup."""
    temporary_path: Path | None = None
    final_path: Path | None = None
    published = False
    try:
        database_size = database_path.stat().st_size
        free_bytes = shutil.disk_usage(database_path.parent).free
        if free_bytes <= database_size + _FREE_SPACE_GUARD_BYTES:
            raise MigrationError("backup_failed")

        backup_root = database_path.parent / ".backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        unique = uuid.uuid4().hex
        temporary_path = backup_root / f".{database_path.name}.{unique}.tmp"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        final_path = backup_root / f"{database_path.name}.v0.{timestamp}.{unique}.sqlite3"

        with closing(sqlite3.connect(temporary_path)) as destination:
            with destination:
                source.backup(destination)
                if not _integrity_is_ok(destination):
                    raise MigrationError("backup_invalid")
                try:
                    backup_identities = critical_identity_snapshot(destination, metadata)
                except MigrationError as exc:
                    raise MigrationError("backup_invalid") from exc
                if backup_identities != expected_identities:
                    raise MigrationError("backup_invalid")

        with temporary_path.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, final_path)
        backup_sha256 = sha256_file(final_path)
        published = True
        return VerifiedBackup(path=final_path, sha256=backup_sha256)
    except MigrationError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise MigrationError("backup_failed") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if final_path is not None and not published:
            final_path.unlink(missing_ok=True)
