from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest

from evaluation import runtime_materialization as material, release_verification as release
from evaluation.tool_attestation import FileFingerprint, aggregate_fingerprints
from tests.test_d39_release_verification import publication as publication, _cleanup, _materialize


def _inputs(tmp_path: Path) -> tuple[Path, Path, SimpleNamespace]:
    work, source = tmp_path / 'work', tmp_path / 'source'
    work.mkdir()
    source.mkdir()
    (source / 'file.txt').write_bytes(b'fixture\n')
    files = (FileFingerprint(path='file.txt', size=8, sha256=hashlib.sha256(b'fixture\n').hexdigest()),)
    return work, source, SimpleNamespace(files=files, runtime_source_sha256=aggregate_fingerprints(files))


def test_m2_constructor_cleanup_loss_has_distinct_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work, source, record = _inputs(tmp_path)
    def fail_copy(*args: object) -> None:
        raise OSError('synthetic copy failure')
    def fail_cleanup(*args: object) -> None:
        raise OSError('synthetic cleanup failure')
    monkeypatch.setattr(material._OwnedTree, 'copy', fail_copy)
    monkeypatch.setattr(release._ExecutionGroup, 'cleanup', fail_cleanup)
    with pytest.raises(release._GroupCleanupFailed):
        release._ExecutionGroup(work, source, record)


def test_m2_anchor_open_failure_removes_owned_empty_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work, source, record = _inputs(tmp_path)
    original = material._open_anchor
    def open_anchor(path: Path):
        if path.name.startswith('group-'):
            raise OSError('synthetic anchor open failure')
        return original(path)
    monkeypatch.setattr(material, '_open_anchor', open_anchor)
    with pytest.raises(OSError):
        release._ExecutionGroup(work, source, record)
    assert not list(work.iterdir())


@pytest.mark.skipif(os.name != 'nt', reason='Windows dangling junction')
def test_m3_cleaned_runtime_cannot_hide_dangling_junction(publication: tuple[Path, Path, Path, Path]) -> None:
    _, root, digest = _materialize(publication)
    _cleanup(publication, root, digest)
    target = publication[2] / 'junction-target'
    target.mkdir()
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(root), str(target)], check=True, capture_output=True)
    target.rmdir()
    try:
        with pytest.raises(ValueError):
            _cleanup(publication, root, digest)
        assert os.path.lexists(root)
    finally:
        root.rmdir()


def test_m4_group_never_changes_attributes_of_hardlinked_leaf(tmp_path: Path) -> None:
    work, source, record = _inputs(tmp_path)
    group = release._ExecutionGroup(work, source, record)
    outside = tmp_path / 'outside.txt'
    outside.write_bytes(b'outside')
    leaf = group.root / 'hardlink.txt'
    os.link(outside, leaf)
    os.chmod(outside, stat.S_IREAD)
    try:
        with pytest.raises(ValueError):
            group.cleanup()
        assert outside.stat().st_mode & stat.S_IWRITE == 0
        assert leaf.exists()
    finally:
        os.chmod(outside, stat.S_IREAD | stat.S_IWRITE)
        if leaf.exists():
            leaf.unlink()
        if group.anchor is not None:
            release.freeze._close_directory_anchor(group.anchor)
        release.freeze._close_directory_anchor(group.work_anchor)


def test_l11_first_marker_write_failure_cleans_owned_root(publication: tuple[Path, Path, Path, Path],
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    original = material._write_descriptor
    def fail(descriptor: int, raw: bytes) -> None:
        if b'"state":"building"' in raw:
            os.write(descriptor, raw[:8])
            raise OSError('synthetic ENOSPC during first marker')
        original(descriptor, raw)
    monkeypatch.setattr(material, '_write_descriptor', fail)
    with pytest.raises(OSError):
        material.materialize_candidate_runtime(candidate_root=publication[0], freeze_manifest_path=publication[1],
                                               work_root=publication[2], output_path=publication[3])
    assert not list(publication[2].iterdir())
    receipt = json.loads(publication[3].with_name(publication[3].name + '.cleanup.json').read_bytes())
    assert receipt['status'] == 'completed'


def test_l12_copy_uses_bounded_file_descriptors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    target.mkdir()
    tree = material._OwnedTree(target)
    original = material._file_descriptor
    def bounded(path: Path, **kwargs: bool) -> int:
        if sum(fd >= 0 for fd, _ in tree.files.values()) >= 8:
            raise OSError('synthetic descriptor limit')
        return original(path, **kwargs)
    monkeypatch.setattr(material, '_file_descriptor', bounded)
    try:
        for index in range(32):
            name = f'{index}.txt'
            (source / name).write_bytes(b'x')
            tree.copy(source, FileFingerprint(path=name, size=1, sha256=hashlib.sha256(b'x').hexdigest()))
        tree.make_readonly()
        tree.remove()
        assert not target.exists()
    finally:
        tree.close()


@pytest.mark.skipif(os.name != 'nt', reason='Windows long-path API boundary')
def test_b8_copy_and_cleanup_use_extended_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work, source, record = _inputs(tmp_path)
    group = release._ExecutionGroup(work, source, record)
    deep = group.root
    for _ in range(8):
        deep /= 'long-component-abcdefghijklmnop'
    extended = Path('\\\\?\\' + str(deep))
    extended.mkdir(parents=True)
    (extended / 'generated.txt').write_bytes(b'x')
    assert len(str(deep)) > 260
    original = os.stat
    def limited(path: object, *args: object, **kwargs: object):
        if isinstance(path, int):
            return original(path, *args, **kwargs)
        value = os.fspath(path)
        if len(value) > 260 and not value.startswith('\\\\?\\'):
            raise OSError('synthetic legacy Win32 path limit')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'stat', limited)
    try:
        group.cleanup()
        assert not group.root.exists()
    finally:
        if group.anchor is not None:
            release.freeze._close_directory_anchor(group.anchor)
        release.freeze._close_directory_anchor(group.work_anchor)


@pytest.mark.skipif(os.name != 'nt', reason='Windows handle deletion race')
def test_m4_replacement_after_identity_check_survives(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work, source, record = _inputs(tmp_path)
    group = release._ExecutionGroup(work, source, record)
    leaf = group.root / 'leaf.txt'
    leaf.write_bytes(b'owned')
    expected = material._identity(leaf.stat())
    moved = group.root / 'moved-owned.txt'
    attacked = False
    native_identity = material._native_identity
    unlink = os.unlink
    def swap() -> None:
        nonlocal attacked
        if attacked or not leaf.exists():
            return
        try:
            leaf.rename(moved)
        except PermissionError:
            return  # A retained no-delete handle still protects this phase.
        leaf.write_bytes(b'replacement')
        attacked = True
    def identity(handle: int) -> tuple[int, int]:
        result = native_identity(handle)
        if result == expected:
            swap()
        return result
    def remove(path: object, *args: object, **kwargs: object) -> None:
        if Path(path).name == leaf.name:
            swap()
        unlink(path, *args, **kwargs)
    monkeypatch.setattr(material, '_native_identity', identity)
    monkeypatch.setattr(os, 'unlink', remove)
    try:
        with pytest.raises((OSError, ValueError)):
            group.cleanup()
        assert attacked
        assert leaf.read_bytes() == b'replacement'
    finally:
        if group.anchor is not None:
            release.freeze._close_directory_anchor(group.anchor)
        release.freeze._close_directory_anchor(group.work_anchor)
def test_step5_candidate_boundaries_batch_blobs_and_still_reject_drift(publication, monkeypatch):
    from evaluation import runtime_materialization as materialization
    import subprocess
    candidate, frozen, _, _ = publication
    calls = []
    original = subprocess.Popen
    def observed(argv, *args, **kwargs):
        calls.append(argv)
        return original(argv, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', observed)
    first = materialization._freeze_inputs(candidate, frozen)
    second = materialization._freeze_inputs(candidate, frozen)
    assert first == second
    assert len(calls) < 40
    (candidate / first[0].files[0].path).write_bytes(b'changed\n')
    import pytest
    with pytest.raises(ValueError):
        materialization._freeze_inputs(candidate, frozen)


@pytest.mark.skipif(os.name != 'nt', reason='Windows screenshot ancestor junction')
def test_l10_screenshot_fingerprint_rejects_ancestor_junction(tmp_path: Path) -> None:
    from evaluation.scripts import d39_smoke as producer
    target = tmp_path / 'real'
    target.mkdir()
    (target / '390-waiting.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    link = tmp_path / 'screenshots'
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], check=True, capture_output=True)
    try:
        with pytest.raises(ValueError):
            producer._screenshot_fingerprint(link / '390-waiting.png')
    finally:
        link.rmdir()
