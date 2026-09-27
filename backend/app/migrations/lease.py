"""Non-blocking exclusive lease for one file-backed SQLite database."""
from __future__ import annotations

import os
import uuid
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


def _descriptor_bytes(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while chunk := os.read(descriptor, 4096):
        chunks.append(chunk)
    return b"".join(chunks)


@dataclass
class DatabaseLease:
    database_path: Path
    lock_path: Path
    _descriptor: int | None = field(repr=False)
    _identity: tuple[int, int] = field(repr=False)
    _token: str = field(repr=False)

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
        """Atomically isolate and delete only this owner's lock inode and token."""
        descriptor = self._descriptor
        if descriptor is None:
            return
        owned_bytes = _descriptor_bytes(descriptor)
        owned_identity = self._identity
        self._descriptor = None
        os.close(descriptor)
        tombstone = self.lock_path.with_name(
            f"{self.lock_path.name}.release-{self._token}"
        )
        try:
            os.replace(self.lock_path, tombstone)
        except FileNotFoundError:
            return
        moved = tombstone.stat()
        moved_owned_file = (
            (moved.st_dev, moved.st_ino) == owned_identity
            and tombstone.read_bytes() == owned_bytes
        )
        if moved_owned_file:
            tombstone.unlink()
            return

        try:
            os.link(tombstone, self.lock_path)
        except OSError as exc:
            raise MigrationError("database_lease_unavailable") from exc
        tombstone.unlink()


def acquire_database_lease(database_url: str) -> DatabaseLease:
    """Acquire the sibling migration lock once without waiting or database I/O."""
    database_path = database_path_from_url(database_url)
    lock_path = database_path.with_name(f"{database_path.name}.migration.lock")
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0)
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise MigrationError("database_lease_unavailable") from exc
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    token = uuid.uuid4().hex
    stat_result = os.fstat(descriptor)
    lease = DatabaseLease(
        database_path=database_path,
        lock_path=lock_path,
        _descriptor=descriptor,
        _identity=(stat_result.st_dev, stat_result.st_ino),
        _token=token,
    )
    try:
        payload = f"pid={os.getpid()}\nutc={timestamp}\ntoken={token}\n".encode("ascii")
        if os.write(descriptor, payload) != len(payload):
            raise OSError("incomplete lease write")
        os.fsync(descriptor)
        return lease
    except Exception:
        lease.release()
        raise
