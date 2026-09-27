"""Non-blocking exclusive lease for one file-backed SQLite database."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.migrations.contracts import MigrationError


def database_path_from_url(database_url: str) -> Path:
    """Return the canonical path for a supported file-backed SQLite URL."""
    try:
        url = make_url(database_url)
    except Exception as exc:
        raise MigrationError("unsupported_database") from exc
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
        raise MigrationError("unsupported_database")
    return Path(url.database).expanduser().resolve()


@dataclass
class DatabaseLease:
    database_path: Path
    lock_path: Path
    _descriptor: int | None = field(repr=False)
    _identity: tuple[int, int] = field(repr=False)

    def assert_held_for(self, database_url: str) -> None:
        """Reject released leases and leases bound to another database."""
        if self._descriptor is None:
            raise MigrationError("database_lease_unavailable")
        try:
            requested_path = database_path_from_url(database_url)
        except MigrationError as exc:
            raise MigrationError("database_lease_unavailable") from exc
        if requested_path != self.database_path:
            raise MigrationError("database_lease_unavailable")
        try:
            current = self.lock_path.stat()
        except OSError as exc:
            raise MigrationError("database_lease_unavailable") from exc
        if (current.st_dev, current.st_ino) != self._identity:
            raise MigrationError("database_lease_unavailable")

    def release(self) -> None:
        """Release this lease once without deleting a replacement lock file."""
        descriptor = self._descriptor
        if descriptor is None:
            return
        self._descriptor = None
        os.close(descriptor)
        try:
            current = self.lock_path.stat()
        except FileNotFoundError:
            return
        if (current.st_dev, current.st_ino) == self._identity:
            self.lock_path.unlink()


def acquire_database_lease(database_url: str) -> DatabaseLease:
    """Acquire the sibling migration lock once without waiting or database I/O."""
    database_path = database_path_from_url(database_url)
    lock_path = database_path.with_name(f"{database_path.name}.migration.lock")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise MigrationError("database_lease_unavailable") from exc
    try:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload = f"pid={os.getpid()}\nutc={timestamp}\n".encode("ascii")
        os.write(descriptor, payload)
        os.fsync(descriptor)
        stat_result = os.fstat(descriptor)
        return DatabaseLease(
            database_path=database_path,
            lock_path=lock_path,
            _descriptor=descriptor,
            _identity=(stat_result.st_dev, stat_result.st_ino),
        )
    except Exception:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        raise
