"""Streamed immutable candidate copies with physical, marker-bound cleanup."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

from evaluation import blinded_io
from evaluation.evidence_json import parse_canonical_model
from evaluation.release_candidate import freeze
from evaluation.release_candidate.contracts import CandidateControl, FreezeManifest
from evaluation.release_candidate.fingerprints import fingerprint_files
from evaluation.smoke_contracts import (
    OwnedPathIdentity,
    RuntimeCleanupReceipt,
    RuntimeMaterialization,
    RuntimeOwnership,
)
from evaluation.tool_attestation import FileFingerprint, aggregate_fingerprints, canonical_json_bytes

MAX_MATERIALIZATION_BYTES = 16 * 1024 * 1024
MAX_OWNERSHIP_BYTES = 4096
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _descriptor_stat(descriptor: int) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if os.name != "nt":
        return metadata
    import ctypes
    import msvcrt
    information = freeze._ByHandleFileInformation()
    query = ctypes.WinDLL("kernel32", use_last_error=True).GetFileInformationByHandle
    query.argtypes = [ctypes.c_void_p, ctypes.POINTER(freeze._ByHandleFileInformation)]
    query.restype = ctypes.c_int
    if not query(msvcrt.get_osfhandle(descriptor), ctypes.byref(information)):
        raise OSError("owned file physical identity unavailable")
    if information.file_attributes & (0x400 | 0x10):
        raise ValueError("owned file must be regular and non-reparse")
    values = list(metadata)
    values[2], values[1] = _native_identity(msvcrt.get_osfhandle(descriptor))
    values[3] = information.number_of_links
    return os.stat_result(values, {"st_atime_ns": metadata.st_atime_ns, "st_mtime_ns": metadata.st_mtime_ns, "st_ctime_ns": metadata.st_ctime_ns, "st_file_attributes": information.file_attributes})


def _native_identity(handle: int) -> tuple[int, int]:
    import ctypes
    class FileId(ctypes.Structure):
        _fields_ = [("volume", ctypes.c_uint64), ("identifier", ctypes.c_ubyte * 16)]
    value = FileId()
    query = ctypes.WinDLL("kernel32", use_last_error=True).GetFileInformationByHandleEx
    query.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    query.restype = ctypes.c_int
    if not query(handle, 18, ctypes.byref(value), ctypes.sizeof(value)):
        raise OSError("physical owned identity unavailable")
    return value.volume, int.from_bytes(bytes(value.identifier), "little")


def _open_anchor(path: Path) -> freeze._DirectoryAnchor:
    anchor = freeze._open_directory_anchor(path)
    if anchor.handle is not None:
        anchor.identity = _native_identity(anchor.handle)
    return anchor


def _anchor_identity(anchor: freeze._DirectoryAnchor) -> tuple[int, int]:
    if anchor.handle is not None and not anchor.closed:
        freeze._windows_directory_information(anchor.handle)
        return _native_identity(anchor.handle)
    return freeze._anchor_identity(anchor)


def _directory_identity(path: Path) -> tuple[int, int]:
    anchor = _open_anchor(path)
    try:
        return _anchor_identity(anchor)
    finally:
        freeze._close_directory_anchor(anchor)


def _directory(path: Path) -> Path:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    blinded_io.validate_directory(current, "root alias")
    for part in absolute.parts[1:]:
        if part in {".", ".."}:
            raise ValueError("unsafe root alias")
        current /= part
        blinded_io.validate_directory(current, "root alias")
    return current


def _disjoint(*paths: Path) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise ValueError("root aliases must be disjoint")
            if _identity(left.lstat()) == _identity(right.lstat()):
                raise ValueError("root aliases must be physically distinct")


def _file_descriptor(path: Path, *, create: bool = False, writable: bool = False) -> int:
    if os.name == "nt":
        import ctypes
        import msvcrt
        create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
        create_file.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        create_file.restype = ctypes.c_void_p
        access = 0x80000000 | (0x40000000 if writable else 0)
        handle = create_file(str(path), access, 0x3, None, 1 if create else 3, 0x00200000, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            raise OSError(ctypes.get_last_error(), "owned file open failed")
        try:
            return msvcrt.open_osfhandle(int(handle), os.O_BINARY | (os.O_RDWR if writable else os.O_RDONLY))
        except BaseException:
            freeze._windows_close_handle(int(handle))
            raise
    flags = (os.O_RDWR if writable else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    return os.open(path, flags, 0o600)


def _assert_file(path: Path, descriptor: int, expected: tuple[int, int]) -> os.stat_result:
    opened = _descriptor_stat(descriptor)
    named = path.lstat()
    if any(not stat.S_ISREG(item.st_mode) or blinded_io.is_reparse(item) or item.st_nlink != 1 or _identity(item) != expected for item in (opened, named)):
        raise ValueError("owned file identity lost")
    return opened


def _read_descriptor(descriptor: int, *, maximum: int) -> bytes:
    metadata = os.fstat(descriptor)
    if metadata.st_size > maximum:
        raise ValueError("owned metadata exceeds size limit")
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    size = 0
    while chunk := os.read(descriptor, min(65536, maximum + 1 - size)):
        chunks.append(chunk)
        size += len(chunk)
        if size > maximum:
            raise ValueError("owned metadata exceeds size limit")
    if os.fstat(descriptor).st_size != metadata.st_size or size != metadata.st_size:
        raise ValueError("owned metadata changed")
    return b"".join(chunks)


def _write_descriptor(descriptor: int, value: bytes) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    remaining = memoryview(value)
    while remaining:
        written = os.write(descriptor, remaining)
        if written < 1:
            raise ValueError("owned write failed")
        remaining = remaining[written:]
    os.ftruncate(descriptor, len(value))
    os.fsync(descriptor)


@contextmanager
def _locked_marker(path: Path, *, create: bool = False) -> Iterator[int]:
    descriptor = _file_descriptor(path, create=create, writable=True)
    locked = False
    try:
        metadata = _descriptor_stat(descriptor)
        _assert_file(path, descriptor, _identity(metadata))
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield descriptor
    finally:
        if locked:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _marker_path(path: Path) -> Path:
    return path.with_name(path.name + ".ownership.json")


def _assert_directory(path: Path, anchor: freeze._DirectoryAnchor) -> None:
    _directory(path)
    if _anchor_identity(anchor) != anchor.identity or _directory_identity(path) != anchor.identity:
        raise ValueError("owned directory identity lost")


def _marker_update(path: Path, descriptor: int, marker: RuntimeOwnership, *, state: str, digest: str | None) -> RuntimeOwnership:
    _assert_file(path, descriptor, (marker.marker_device, marker.marker_inode))
    if _read_descriptor(descriptor, maximum=MAX_OWNERSHIP_BYTES) != canonical_json_bytes(marker) + b"\n":
        raise ValueError("ownership marker changed")
    updated = RuntimeOwnership.model_validate({**marker.model_dump(), "state": state, "materialization_sha256": digest}, strict=True)
    raw = canonical_json_bytes(updated) + b"\n"
    if len(raw) > MAX_OWNERSHIP_BYTES:
        raise ValueError("ownership marker exceeds size limit")
    _write_descriptor(descriptor, raw)
    _assert_file(path, descriptor, (marker.marker_device, marker.marker_inode))
    if _read_descriptor(descriptor, maximum=MAX_OWNERSHIP_BYTES) != raw:
        raise ValueError("ownership marker readback mismatch")
    return updated


def _receipt(output: Path, instance: str, digest: str | None, status: str) -> None:
    receipt = RuntimeCleanupReceipt.model_validate({"schema_version": 1, "runtime_instance_id": instance, "materialization_sha256": digest, "status": status}, strict=True)
    path = output.with_name(output.name + ".cleanup.json")
    try:
        old = blinded_io.read_regular(path, maximum=MAX_OWNERSHIP_BYTES)
    except FileNotFoundError:
        pass
    else:
        previous = parse_canonical_model(old, RuntimeCleanupReceipt, maximum=MAX_OWNERSHIP_BYTES)
        if previous.runtime_instance_id != instance or previous.materialization_sha256 != digest:
            raise ValueError("cleanup receipt binding mismatch")
    blinded_io.write_atomic(path, canonical_json_bytes(receipt) + b"\n")


def _inventory(root: Path) -> tuple[OwnedPathIdentity, ...]:
    values: list[OwnedPathIdentity] = []
    def visit(directory: Path) -> None:
        _directory(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                metadata = Path(entry.path).lstat()
                if blinded_io.is_reparse(metadata) or stat.S_ISLNK(metadata.st_mode):
                    raise ValueError("runtime contains a link or reparse")
                kind = "directory" if stat.S_ISDIR(metadata.st_mode) else "file"
                if kind == "file" and not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("runtime contains a special file")
                values.append(OwnedPathIdentity(path=Path(entry.path).relative_to(root).as_posix(), kind=kind, device=metadata.st_dev, inode=metadata.st_ino))
                if len(values) > 8192:
                    raise ValueError("runtime inventory exceeds its limit")
                if kind == "directory":
                    visit(Path(entry.path))
    visit(root)
    return tuple(sorted(values, key=lambda item: item.path))


def _readonly(path: Path, *, directory: bool) -> None:
    metadata = path.lstat()
    if os.name == "nt" and directory:
        if not metadata.st_file_attributes & 1:
            raise ValueError("runtime directory permission drift")
        return
    if metadata.st_mode & 0o222 or (os.name != "nt" and metadata.st_mode & 0o777 != (0o500 if directory else 0o400)):
        raise ValueError("runtime write permission drift")


def _verify_tree(root: Path, owned: tuple[OwnedPathIdentity, ...], files: tuple[FileFingerprint, ...], *, subset: bool = False, readonly: bool = True) -> tuple[OwnedPathIdentity, ...]:
    actual = _inventory(root)
    recorded = {item.path: item for item in owned}
    if any(recorded.get(item.path) != item for item in actual) or (not subset and actual != owned):
        raise ValueError("runtime inventory or physical identity drift")
    fingerprints = {item.path: item for item in files}
    for item in actual:
        path = root / item.path
        if readonly:
            _readonly(path, directory=item.kind == "directory")
        if item.kind == "file":
            if path.lstat().st_nlink != 1:
                raise ValueError("runtime file has an unowned hardlink alias")
            size, digest = blinded_io.fingerprint_regular(path, maximum=_MAX_FILE_BYTES)
            expected = fingerprints.get(item.path)
            if expected is not None and (size, digest) != (expected.size, expected.sha256):
                raise ValueError("runtime source content drift")
    if readonly:
        _readonly(root, directory=True)
    return actual


class _OwnedTree:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.directories: dict[str, freeze._DirectoryAnchor] = {"": _open_anchor(root)}
        self.files: dict[str, tuple[int, tuple[int, int]]] = {}
        self.fingerprints: dict[str, FileFingerprint] = {}
        self.guard: Callable[[], None] | None = None

    def assert_owned(self, target: str | None = None) -> None:
        if self.guard is not None:
            self.guard()
        required = None if target is None else {"", target, *(parent.as_posix() for parent in PurePosixPath(target).parents if parent.as_posix() != ".")}
        for relative, anchor in self.directories.items():
            if not anchor.closed and (required is None or relative in required):
                _assert_directory(self.root / relative, anchor)
        for relative, (descriptor, identity) in self.files.items():
            if descriptor >= 0 and (target is None or relative == target):
                _assert_file(self.root / relative, descriptor, identity)

    def close(self) -> None:
        for relative, (descriptor, identity) in tuple(self.files.items()):
            if descriptor >= 0:
                os.close(descriptor)
                self.files[relative] = (-1, identity)
        for anchor in self.directories.values():
            freeze._close_directory_anchor(anchor)

    def identities(self) -> tuple[OwnedPathIdentity, ...]:
        values = [OwnedPathIdentity(path=path, kind="directory", device=anchor.identity[0], inode=anchor.identity[1]) for path, anchor in self.directories.items() if path]
        values.extend(OwnedPathIdentity(path=path, kind="file", device=identity[0], inode=identity[1]) for path, (_, identity) in self.files.items())
        return tuple(sorted(values, key=lambda item: item.path))

    def copy(self, candidate: Path, expected: FileFingerprint) -> None:
        destination = self.root / expected.path
        for parent in reversed(PurePosixPath(expected.path).parents):
            relative = parent.as_posix()
            if relative == "." or relative in self.directories:
                continue
            self.assert_owned(relative)
            (self.root / relative).mkdir(mode=0o700)
            self.directories[relative] = _open_anchor(self.root / relative)
        self.assert_owned(expected.path)
        _directory((candidate / expected.path).parent)
        source = _file_descriptor(candidate / expected.path)
        descriptor = -1
        try:
            before = _descriptor_stat(source)
            _assert_file(candidate / expected.path, source, _identity(before))
            if before.st_size != expected.size or before.st_size > _MAX_FILE_BYTES:
                raise ValueError("candidate source size changed")
            descriptor = _file_descriptor(destination, create=True, writable=True)
            identity = _identity(_descriptor_stat(descriptor))
            self.files[expected.path] = (descriptor, identity)
            digest = hashlib.sha256()
            size = 0
            while chunk := os.read(source, 65536):
                size += len(chunk)
                if size > expected.size:
                    raise ValueError("candidate source grew during copy")
                digest.update(chunk)
                remaining = memoryview(chunk)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written < 1:
                        raise ValueError("runtime copy write failed")
                    remaining = remaining[written:]
            os.fsync(descriptor)
            actual = FileFingerprint(path=expected.path, size=size, sha256=digest.hexdigest())
            self.fingerprints[expected.path] = actual
            after = _assert_file(candidate / expected.path, source, _identity(before))
            if actual != expected or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("candidate source changed during copy")
            self.assert_owned(expected.path)
        finally:
            os.close(source)

    def make_readonly(self) -> None:
        self.assert_owned()
        for relative in self.files:
            self.assert_owned(relative)
            os.chmod(self.root / relative, stat.S_IREAD)
        for relative in sorted(self.directories, key=lambda value: value.count("/"), reverse=True):
            self.assert_owned(relative)
            os.chmod(self.root / relative, stat.S_IREAD | stat.S_IEXEC)
        self.assert_owned()

    def remove(self) -> None:
        self.assert_owned()
        owned = self.identities()
        files = tuple(self.fingerprints.values())
        _verify_tree(self.root, owned, files, readonly=False)
        for relative in sorted(self.files):
            self.assert_owned(relative)
            descriptor, identity = self.files[relative]
            path = self.root / relative
            _assert_file(path, descriptor, identity)
            expected = self.fingerprints.get(relative)
            size, digest = blinded_io.fingerprint_regular(path, maximum=_MAX_FILE_BYTES)
            if expected is not None and (size, digest) != (expected.size, expected.sha256):
                raise ValueError("owned file content changed before removal")
            if os.name == "nt":
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
            else:
                parent = relative.rpartition("/")[0]
                anchor = self.directories[parent]
                assert anchor.descriptor is not None
                os.fchmod(anchor.descriptor, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
            _assert_file(path, descriptor, identity)
            os.close(descriptor)
            self.files[relative] = (-1, identity)
            if _identity(path.lstat()) != identity:
                raise ValueError("owned file identity lost before unlink")
            parent = relative.rpartition("/")[0]
            parent_anchor = self.directories[parent]
            _assert_directory(path.parent, parent_anchor)
            if parent_anchor.descriptor is not None:
                os.unlink(path.name, dir_fd=parent_anchor.descriptor)
            else:
                os.unlink(path)
            del self.files[relative]
        for relative in sorted(self.directories, key=lambda value: (value.count("/"), value), reverse=True):
            self.assert_owned(relative)
            path = self.root / relative
            anchor = self.directories[relative]
            _assert_directory(path, anchor)
            if os.listdir(anchor.descriptor if anchor.descriptor is not None else path):
                raise ValueError("owned directory is not empty")
            if relative and os.name != "nt":
                parent = relative.rpartition("/")[0]
                parent_anchor = self.directories[parent]
                assert parent_anchor.descriptor is not None
                os.fchmod(parent_anchor.descriptor, 0o700)
            if os.name == "nt":
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
                _assert_directory(path, anchor)
            freeze._close_directory_anchor(anchor)
            if _directory_identity(path) != anchor.identity:
                raise ValueError("owned directory identity lost before removal")
            path.rmdir()
            del self.directories[relative]


def _freeze_inputs(candidate: Path, frozen: Path) -> tuple[FreezeManifest, str, str]:
    if frozen.name != "freeze-manifest.json":
        raise ValueError("freeze artifact name mismatch")
    publication = _directory(frozen.parent)
    raw = blinded_io.read_regular(frozen, maximum=MAX_MATERIALIZATION_BYTES)
    manifest = parse_canonical_model(raw, FreezeManifest, maximum=MAX_MATERIALIZATION_BYTES)
    if freeze.read_frozen_candidate(publication)[0] != manifest:
        raise ValueError("complete freeze publication mismatch")
    control = CandidateControl(schema_version=1, git_commit=manifest.git_commit, git_commit_subject=freeze.CANDIDATE_COMMIT_SUBJECT, git_tree_clean=True)
    freeze._candidate_identity(candidate, control)
    snapshot = freeze._snapshot_tree(candidate)
    files = fingerprint_files(candidate)
    if files != manifest.files or aggregate_fingerprints(files) != manifest.aggregate_sha256:
        raise ValueError("candidate committed source mismatch")
    if freeze._snapshot_tree(candidate) != snapshot:
        raise ValueError("candidate snapshot changed during verification")
    return manifest, hashlib.sha256(raw).hexdigest(), snapshot


def materialize_candidate_runtime(*, candidate_root: Path, freeze_manifest_path: Path, work_root: Path, output_path: Path) -> RuntimeMaterialization:
    """Create one tracked-byte runtime; never execute or modify candidate source."""
    candidate = _directory(candidate_root)
    work = _directory(work_root)
    output = output_path.absolute()
    evidence = _directory(output.parent)
    publication = _directory(freeze_manifest_path.absolute().parent)
    _disjoint(candidate, work, evidence, publication)
    marker_path = _marker_path(output)
    for path in (output, marker_path, output.with_name(output.name + ".cleanup.json")):
        if path.exists() or path.is_symlink():
            raise ValueError("materialization evidence must be new")
    manifest, freeze_digest, snapshot = _freeze_inputs(candidate, freeze_manifest_path.absolute())
    if sum(item.size for item in manifest.files) > _MAX_TOTAL_BYTES:
        raise ValueError("candidate source exceeds total size limit")
    instance = secrets.token_hex(32)
    root = work / ("runtime-" + instance)
    work_anchor = _open_anchor(work)
    evidence_anchor = _open_anchor(evidence)
    tree: _OwnedTree | None = None
    marker_entered = False
    root_created = False
    try:
        _assert_directory(work, work_anchor)
        root.mkdir(mode=0o700)
        root_created = True
        tree = _OwnedTree(root)
        with _locked_marker(marker_path, create=True) as descriptor:
            marker_entered = True
            root_id = tree.directories[""].identity
            marker_id = _identity(_descriptor_stat(descriptor))
            marker = RuntimeOwnership(schema_version=1, runtime_instance_id=instance, runtime_device=root_id[0], runtime_inode=root_id[1], marker_device=marker_id[0], marker_inode=marker_id[1], work_root_alias="work", runtime_root_alias="runtime", materialization_sha256=None, state="building")
            _write_descriptor(descriptor, canonical_json_bytes(marker) + b"\n")
            digest: str | None = None
            try:
                def guard() -> None:
                    _assert_directory(work, work_anchor)
                    _assert_directory(evidence, evidence_anchor)
                    _assert_file(marker_path, descriptor, marker_id)
                    if _read_descriptor(descriptor, maximum=MAX_OWNERSHIP_BYTES) != canonical_json_bytes(marker) + b"\n":
                        raise ValueError("runtime ownership marker lost")
                tree.guard = guard
                for item in manifest.files:
                    _assert_directory(work, work_anchor)
                    _assert_directory(evidence, evidence_anchor)
                    _assert_file(marker_path, descriptor, marker_id)
                    tree.copy(candidate, item)
                files = tuple(sorted(tree.fingerprints.values(), key=lambda item: item.path))
                if files != tuple(manifest.files) or aggregate_fingerprints(files) != manifest.aggregate_sha256:
                    raise ValueError("runtime source inventory mismatch")
                if _freeze_inputs(candidate, freeze_manifest_path.absolute()) != (manifest, freeze_digest, snapshot):
                    raise ValueError("candidate or freeze changed during materialization")
                tree.make_readonly()
                owned = tree.identities()
                _verify_tree(root, owned, files)
                result = RuntimeMaterialization(schema_version=1, candidate_id=manifest.candidate_id, git_commit=manifest.git_commit, freeze_sha256=freeze_digest, candidate_snapshot_sha256=snapshot, runtime_instance_id=instance, files=files, owned_paths=owned, runtime_source_sha256=manifest.aggregate_sha256, runtime_device=root_id[0], runtime_inode=root_id[1], marker_device=marker_id[0], marker_inode=marker_id[1], root_aliases=("candidate", "runtime", "work"), status="materialized")
                raw = canonical_json_bytes(result) + b"\n"
                parse_canonical_model(raw, RuntimeMaterialization, maximum=MAX_MATERIALIZATION_BYTES)
                _assert_directory(evidence, evidence_anchor)
                blinded_io.publish_immutable(output, raw, "materialization", maximum=MAX_MATERIALIZATION_BYTES)
                digest = hashlib.sha256(raw).hexdigest()
                marker = _marker_update(marker_path, descriptor, marker, state="active", digest=digest)
                if _freeze_inputs(candidate, freeze_manifest_path.absolute()) != (manifest, freeze_digest, snapshot):
                    raise ValueError("candidate changed before materialization return")
                _verify_tree(root, owned, files)
                return result
            except BaseException:
                try:
                    _assert_directory(work, work_anchor)
                    _assert_directory(evidence, evidence_anchor)
                    _assert_file(marker_path, descriptor, marker_id)
                    if _read_descriptor(descriptor, maximum=MAX_OWNERSHIP_BYTES) != canonical_json_bytes(marker) + b"\n":
                        raise ValueError("building ownership lost")
                    tree.remove()
                    if digest is not None:
                        marker = _marker_update(marker_path, descriptor, marker, state="cleaned", digest=digest)
                    _receipt(output, instance, digest, "completed")
                except (OSError, ValueError):
                    _receipt(output, instance, digest, "failed")
                    raise ValueError("runtime cleanup_failed") from None
                raise
    except BaseException:
        if root_created and not marker_entered:
            try:
                _assert_directory(work, work_anchor)
                _assert_directory(evidence, evidence_anchor)
                if tree is None:
                    raise ValueError("building root ownership unavailable")
                tree.remove()
                _receipt(output, instance, None, "completed")
            except (OSError, ValueError):
                _assert_directory(evidence, evidence_anchor)
                _receipt(output, instance, None, "failed")
                raise ValueError("runtime cleanup_failed") from None
        raise
    finally:
        if tree is not None:
            tree.close()
        freeze._close_directory_anchor(work_anchor)
        freeze._close_directory_anchor(evidence_anchor)


def _bound_materialization(path: Path, expected: str) -> RuntimeMaterialization:
    if type(expected) is not str or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ValueError("invalid materialization digest")
    _directory(path.parent)
    raw = blinded_io.read_regular(path, maximum=MAX_MATERIALIZATION_BYTES)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("materialization digest mismatch")
    return parse_canonical_model(raw, RuntimeMaterialization, maximum=MAX_MATERIALIZATION_BYTES)


def _bound_marker(path: Path, descriptor: int, result: RuntimeMaterialization, digest: str) -> RuntimeOwnership:
    _assert_file(path, descriptor, (result.marker_device, result.marker_inode))
    marker = parse_canonical_model(_read_descriptor(descriptor, maximum=MAX_OWNERSHIP_BYTES), RuntimeOwnership, maximum=MAX_OWNERSHIP_BYTES)
    if (marker.runtime_instance_id != result.runtime_instance_id or marker.materialization_sha256 != digest or (marker.runtime_device, marker.runtime_inode) != (result.runtime_device, result.runtime_inode) or (marker.marker_device, marker.marker_inode) != (result.marker_device, result.marker_inode)):
        raise ValueError("ownership marker binding mismatch")
    return marker


def _bound_root(runtime: Path, work: Path, result: RuntimeMaterialization) -> None:
    if runtime != work / ("runtime-" + result.runtime_instance_id):
        raise ValueError("runtime root alias mismatch")
    if _directory_identity(runtime) != (result.runtime_device, result.runtime_inode):
        raise ValueError("runtime root identity mismatch")


def read_materialized_runtime(*, runtime_root: Path, work_root: Path, materialization_path: Path, expected_materialization_sha256: str) -> RuntimeMaterialization:
    """Reverify active detached evidence, physical inventory, bytes and permissions."""
    work = _directory(work_root)
    path = materialization_path.absolute()
    _disjoint(work, _directory(path.parent))
    result = _bound_materialization(path, expected_materialization_sha256)
    runtime = runtime_root.absolute()
    with _locked_marker(_marker_path(path)) as descriptor:
        marker = _bound_marker(_marker_path(path), descriptor, result, expected_materialization_sha256)
        if marker.state != "active":
            raise ValueError("runtime ownership is not active")
        _bound_root(runtime, work, result)
        _verify_tree(runtime, result.owned_paths, result.files)
    return result


def cleanup_candidate_runtime(*, runtime_root: Path, work_root: Path, materialization_path: Path, expected_materialization_sha256: str) -> None:
    """Remove only bound owned objects, resuming a proven cleaning subset."""
    work = _directory(work_root)
    output = materialization_path.absolute()
    evidence = _directory(output.parent)
    _disjoint(work, evidence)
    result = _bound_materialization(output, expected_materialization_sha256)
    runtime = runtime_root.absolute()
    if runtime != work / ("runtime-" + result.runtime_instance_id):
        raise ValueError("runtime root alias mismatch")
    marker_path = _marker_path(output)
    work_anchor = _open_anchor(work)
    evidence_anchor = _open_anchor(evidence)
    tree: _OwnedTree | None = None
    try:
        with _locked_marker(marker_path) as descriptor:
            marker = _bound_marker(marker_path, descriptor, result, expected_materialization_sha256)
            if marker.state == "cleaned":
                if runtime.exists() or runtime.is_symlink():
                    raise ValueError("cleaned runtime has reappeared")
                _receipt(output, result.runtime_instance_id, expected_materialization_sha256, "completed")
                return
            try:
                if marker.state not in {"active", "cleaning"}:
                    raise ValueError("runtime ownership cannot be cleaned")
                if marker.state == "cleaning" and not runtime.exists() and not runtime.is_symlink():
                    _assert_directory(work, work_anchor)
                    _assert_directory(evidence, evidence_anchor)
                    _marker_update(marker_path, descriptor, marker, state="cleaned", digest=expected_materialization_sha256)
                    _receipt(output, result.runtime_instance_id, expected_materialization_sha256, "completed")
                    return
                _bound_root(runtime, work, result)
                actual = _verify_tree(runtime, result.owned_paths, result.files, subset=marker.state == "cleaning", readonly=marker.state == "active")
                tree = _OwnedTree(runtime)
                if tree.directories[""].identity != (result.runtime_device, result.runtime_inode):
                    raise ValueError("runtime root changed before cleanup")
                for item in actual:
                    path = runtime / item.path
                    if item.kind == "directory":
                        anchor = _open_anchor(path)
                        tree.directories[item.path] = anchor
                        if anchor.identity != (item.device, item.inode):
                            raise ValueError("owned directory changed before cleanup")
                    else:
                        file_descriptor = _file_descriptor(path)
                        tree.files[item.path] = (file_descriptor, (item.device, item.inode))
                        _assert_file(path, file_descriptor, (item.device, item.inode))
                tree.fingerprints = {item.path: item for item in result.files if item.path in tree.files}
                def guard() -> None:
                    _assert_directory(work, work_anchor)
                    _assert_directory(evidence, evidence_anchor)
                    current = _bound_marker(marker_path, descriptor, result, expected_materialization_sha256)
                    if current != marker:
                        raise ValueError("runtime ownership marker changed during cleanup")
                tree.guard = guard
                _assert_directory(work, work_anchor)
                _assert_directory(evidence, evidence_anchor)
                _bound_marker(marker_path, descriptor, result, expected_materialization_sha256)
                marker = _marker_update(marker_path, descriptor, marker, state="cleaning", digest=expected_materialization_sha256)
                tree.remove()
                _assert_directory(work, work_anchor)
                _assert_directory(evidence, evidence_anchor)
                marker = _marker_update(marker_path, descriptor, marker, state="cleaned", digest=expected_materialization_sha256)
                _receipt(output, result.runtime_instance_id, expected_materialization_sha256, "completed")
            except BaseException:
                _assert_directory(evidence, evidence_anchor)
                _receipt(output, result.runtime_instance_id, expected_materialization_sha256, "failed")
                raise
    finally:
        if tree is not None:
            tree.close()
        freeze._close_directory_anchor(work_anchor)
        freeze._close_directory_anchor(evidence_anchor)
