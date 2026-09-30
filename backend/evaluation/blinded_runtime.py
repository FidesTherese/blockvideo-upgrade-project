"""Candidate anchoring and supervised trial-host execution for D37."""
from __future__ import annotations

import asyncio
import ctypes
import os
import signal
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from evaluation import blinded_io

HOST_WATCHDOG_SECONDS = 180 * 4 + 30
HOST_OUTPUT_CAP_BYTES = 2 * 1024 * 1024
HOST_PIPE_DRAIN_GRACE_SECONDS = 1.0
HOST_TEARDOWN_SECONDS = 10.0
_REPARSE_POINT = 0x400
_FILE_SHARE_READ = 0x1
_FILE_SHARE_WRITE = 0x2
_GENERIC_READ = 0x80000000
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


@dataclass
class CandidateAnchor:
    canonical_path: Path
    execution_path: Path
    identity: tuple[int, int]
    descriptor: int | None = None
    handle: int | None = None
    closed: bool = False


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("read_operation_count", ctypes.c_uint64),
        ("write_operation_count", ctypes.c_uint64),
        ("other_operation_count", ctypes.c_uint64),
        ("read_transfer_count", ctypes.c_uint64),
        ("write_transfer_count", ctypes.c_uint64),
        ("other_transfer_count", ctypes.c_uint64),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("per_process_user_time_limit", ctypes.c_int64),
        ("per_job_user_time_limit", ctypes.c_int64),
        ("limit_flags", ctypes.c_uint32),
        ("minimum_working_set_size", ctypes.c_size_t),
        ("maximum_working_set_size", ctypes.c_size_t),
        ("active_process_limit", ctypes.c_uint32),
        ("affinity", ctypes.c_size_t),
        ("priority_class", ctypes.c_uint32),
        ("scheduling_class", ctypes.c_uint32),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("basic_limit_information", _BasicLimitInformation),
        ("io_info", _IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory_used", ctypes.c_size_t),
        ("peak_job_memory_used", ctypes.c_size_t),
    ]


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("file_attributes", ctypes.c_uint32),
        ("creation_time_low", ctypes.c_uint32),
        ("creation_time_high", ctypes.c_uint32),
        ("last_access_time_low", ctypes.c_uint32),
        ("last_access_time_high", ctypes.c_uint32),
        ("last_write_time_low", ctypes.c_uint32),
        ("last_write_time_high", ctypes.c_uint32),
        ("volume_serial_number", ctypes.c_uint32),
        ("file_size_high", ctypes.c_uint32),
        ("file_size_low", ctypes.c_uint32),
        ("number_of_links", ctypes.c_uint32),
        ("file_index_high", ctypes.c_uint32),
        ("file_index_low", ctypes.c_uint32),
    ]


def _windows_directory_identity(handle: int) -> tuple[int, int]:
    information = _ByHandleFileInformation()
    get_information = ctypes.WinDLL("kernel32", use_last_error=True).GetFileInformationByHandle
    get_information.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ByHandleFileInformation)]
    get_information.restype = ctypes.c_int
    if not get_information(ctypes.c_void_p(handle), ctypes.byref(information)):
        error = ctypes.get_last_error()
        raise OSError(error, "GetFileInformationByHandle failed for candidate directory")
    if (
        not information.file_attributes & _FILE_ATTRIBUTE_DIRECTORY
        or information.file_attributes & _REPARSE_POINT
    ):
        raise ValueError("candidate anchor must be a non-reparse directory")
    file_index = (information.file_index_high << 32) | information.file_index_low
    return information.volume_serial_number, file_index


def _windows_open_candidate_directory(path: Path) -> int:
    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    handle = create_file(
        str(path),
        _GENERIC_READ,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        error = ctypes.get_last_error()
        raise OSError(error, "CreateFileW failed for candidate directory")
    return int(handle)


def _windows_close_handle(handle: int) -> None:
    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    if not close_handle(ctypes.c_void_p(handle)):
        error = ctypes.get_last_error()
        raise OSError(error, "CloseHandle failed for candidate directory")


def canonical_candidate_root(candidate_root: Path) -> Path:
    supplied = candidate_root.absolute()
    metadata = supplied.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or blinded_io.is_reparse(metadata)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise ValueError("candidate root must be a non-link directory")
    resolved = supplied.resolve(strict=True)
    if resolved != supplied:
        raise ValueError("candidate root contains an unsafe path component")
    blinded_io.validate_directory(resolved / "backend", "candidate backend")
    return resolved


def open_candidate_anchor(candidate_root: Path) -> CandidateAnchor:
    canonical = canonical_candidate_root(candidate_root)
    if os.name == "nt":
        handle = _windows_open_candidate_directory(canonical)
        try:
            identity = _windows_directory_identity(handle)
        except BaseException:
            _windows_close_handle(handle)
            raise
        return CandidateAnchor(canonical, canonical, identity, handle=handle)
    if os.name != "posix" or not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("candidate directory anchoring is unsupported on this platform")
    descriptor = os.open(canonical, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode) or blinded_io.is_reparse(metadata):
            raise ValueError("candidate anchor must be a non-reparse directory")
        execution = Path(f"/proc/{os.getpid()}/fd/{descriptor}")
        if not execution.exists() or execution.resolve(strict=True) != canonical:
            raise ValueError("stable candidate fd path is unavailable on this POSIX host")
        return CandidateAnchor(
            canonical,
            execution,
            (metadata.st_dev, metadata.st_ino),
            descriptor=descriptor,
        )
    except BaseException:
        os.close(descriptor)
        raise


def close_candidate_anchor(anchor: CandidateAnchor) -> None:
    if anchor.closed:
        return
    anchor.closed = True
    if anchor.handle is not None:
        handle = anchor.handle
        anchor.handle = None
        _windows_close_handle(handle)
    if anchor.descriptor is not None:
        descriptor = anchor.descriptor
        anchor.descriptor = None
        os.close(descriptor)


def _candidate_path_identity(path: Path) -> tuple[int, int]:
    if os.name == "nt":
        handle = _windows_open_candidate_directory(path)
        try:
            return _windows_directory_identity(handle)
        finally:
            _windows_close_handle(handle)
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or blinded_io.is_reparse(metadata)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise ValueError("candidate root must remain a non-link directory")
    return metadata.st_dev, metadata.st_ino


def assert_candidate_anchor(anchor: CandidateAnchor) -> None:
    if anchor.closed:
        raise ValueError("candidate directory anchor is closed")
    if anchor.handle is not None:
        retained = _windows_directory_identity(anchor.handle)
    elif anchor.descriptor is not None:
        metadata = os.fstat(anchor.descriptor)
        if not stat.S_ISDIR(metadata.st_mode) or blinded_io.is_reparse(metadata):
            raise ValueError("candidate directory anchor changed type")
        retained = metadata.st_dev, metadata.st_ino
    else:
        raise ValueError("candidate directory anchor is unavailable")
    if retained != anchor.identity or _candidate_path_identity(anchor.canonical_path) != anchor.identity:
        raise ValueError("candidate directory identity changed during evaluation")


def clean_subprocess_environment(tool_root: Path) -> dict[str, str]:
    retained = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    environment = {name: os.environ[name] for name in retained if name in os.environ}
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(tool_root / "backend"),
        }
    )
    return environment


async def _bounded_stream(
    stream: asyncio.StreamReader,
    descriptor: int,
    overflow: asyncio.Event,
    budget: list[int],
    budget_lock: asyncio.Lock,
) -> None:
    try:
        while chunk := await stream.read(65536):
            async with budget_lock:
                remaining = HOST_OUTPUT_CAP_BYTES - budget[0]
                written = chunk[: max(0, remaining)]
                budget[0] += len(written)
                if len(chunk) > remaining:
                    overflow.set()
            offset = 0
            while offset < len(written):
                offset += os.write(descriptor, written[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _attach_windows_job(process: asyncio.subprocess.Process) -> None:
    if os.name != "nt":
        return
    create_job = ctypes.WinDLL("kernel32", use_last_error=True).CreateJobObjectW
    create_job.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    create_job.restype = ctypes.c_void_p
    job = create_job(None, None)
    invalid_handle = ctypes.c_void_p(-1).value
    if job in (None, invalid_handle):
        error = ctypes.get_last_error()
        raise OSError(error, "CreateJobObjectW failed for trial host")
    job_handle = int(job)
    try:
        information = _ExtendedLimitInformation()
        information.basic_limit_information.limit_flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        set_information = ctypes.WinDLL("kernel32", use_last_error=True).SetInformationJobObject
        set_information.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        set_information.restype = ctypes.c_int
        if not set_information(
            ctypes.c_void_p(job_handle),
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            error = ctypes.get_last_error()
            raise OSError(error, "SetInformationJobObject failed for trial host")
        open_process = ctypes.WinDLL("kernel32", use_last_error=True).OpenProcess
        open_process.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        open_process.restype = ctypes.c_void_p
        process_handle = open_process(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, 0, process.pid
        )
        if process_handle in (None, invalid_handle):
            error = ctypes.get_last_error()
            raise OSError(error, "OpenProcess failed for trial host")
        try:
            assign = ctypes.WinDLL("kernel32", use_last_error=True).AssignProcessToJobObject
            assign.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            assign.restype = ctypes.c_int
            if not assign(ctypes.c_void_p(job_handle), ctypes.c_void_p(process_handle)):
                error = ctypes.get_last_error()
                raise OSError(error, "AssignProcessToJobObject failed for trial host")
        finally:
            _windows_close_handle(int(process_handle))
        setattr(process, "_d37_job_handle", job_handle)
    except BaseException:
        _windows_close_handle(job_handle)
        raise


async def _release_windows_bootstrap(process: asyncio.subprocess.Process) -> None:
    if os.name != "nt":
        return
    if process.stdin is None:
        raise ValueError("trial host bootstrap pipe is unavailable")
    process.stdin.write(b"1")
    await process.stdin.drain()
    process.stdin.close()
    await process.stdin.wait_closed()


def _close_windows_job(process: asyncio.subprocess.Process) -> None:
    handle = getattr(process, "_d37_job_handle", None)
    if handle is None:
        return
    setattr(process, "_d37_job_handle", None)
    _windows_close_handle(handle)


async def _wait_for_parent_exit(process: asyncio.subprocess.Process) -> int:
    while process.returncode is None:
        await asyncio.sleep(0.01)
    return process.returncode


async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
    if os.name == "nt" and getattr(process, "_d37_job_handle", None) is not None:
        _close_windows_job(process)
    elif os.name == "nt" and hasattr(process, "pid") and process.returncode is None:
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    elif os.name == "posix" and hasattr(process, "pid"):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.returncode is None:
        process.kill()
    try:
        await asyncio.wait_for(process.wait(), timeout=HOST_TEARDOWN_SECONDS)
    except TimeoutError:
        if process.returncode is None:
            process.kill()
        raise ValueError("trial host process teardown could not be confirmed") from None


async def invoke_trial_host(
    *,
    tool_root: Path,
    candidate_root: Path,
    mode: str,
    input_path: Path,
    output_path: Path,
    storage: Path,
    model: str,
    index: Path,
    stdout_path: Path,
    stderr_path: Path,
    candidate_identity: tuple[int, int] | None = None,
    embedding_profile: Path | None = None,
    embedding_base_url: str | None = None,
) -> str:
    arguments = [
        sys.executable,
        "-B",
        "-m",
        "evaluation.scripts.evaluation_trial_host",
        "--candidate-root",
        str(candidate_root),
        "--mode",
        mode,
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--storage",
        str(storage),
        "--model",
        model,
    ]
    if os.name == "posix" and candidate_identity is not None:
        arguments.extend(
            (
                "--expected-candidate-dev",
                str(candidate_identity[0]),
                "--expected-candidate-ino",
                str(candidate_identity[1]),
            )
        )
    if (embedding_profile is None) != (embedding_base_url is None):
        raise ValueError("invalid embedding configuration")
    if mode == "all_tools" and embedding_profile is not None:
        raise ValueError("invalid embedding configuration")
    if mode == "stateful":
        arguments.extend(("--index", str(index)))
        if embedding_profile is not None and embedding_base_url is not None:
            arguments.extend(("--embedding-profile", str(embedding_profile),
                              "--embedding-base-url", embedding_base_url))
    process_options: dict[str, object] = {}
    launch_arguments = arguments
    process_stdin: int = asyncio.subprocess.DEVNULL
    if os.name == "posix":
        process_options["start_new_session"] = True
    elif os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        bootstrap = (
            "import subprocess,sys; "
            "ready=sys.stdin.buffer.read(1); "
            "raise SystemExit(125) if ready != b'1' else "
            "SystemExit(subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL))"
        )
        launch_arguments = [sys.executable, "-B", "-c", bootstrap, *arguments]
        process_stdin = asyncio.subprocess.PIPE
    stdout_descriptor = blinded_io.open_exclusive_regular(stdout_path, "trial stdout")
    try:
        stderr_descriptor = blinded_io.open_exclusive_regular(stderr_path, "trial stderr")
    except BaseException:
        os.close(stdout_descriptor)
        raise
    try:
        process = await asyncio.create_subprocess_exec(
            *launch_arguments,
            cwd=tool_root / "backend",
            env=clean_subprocess_environment(tool_root),
            stdin=process_stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **process_options,
        )
        _attach_windows_job(process)
        await _release_windows_bootstrap(process)
    except BaseException:
        if "process" in locals():
            if getattr(process, "_d37_job_handle", None) is not None:
                _close_windows_job(process)
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        os.close(stdout_descriptor)
        os.close(stderr_descriptor)
        raise
    if process.stdout is None or process.stderr is None:
        os.close(stdout_descriptor)
        os.close(stderr_descriptor)
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise ValueError("trial host output pipes are unavailable")
    overflow = asyncio.Event()
    budget = [0]
    budget_lock = asyncio.Lock()
    readers = (
        asyncio.create_task(
            _bounded_stream(process.stdout, stdout_descriptor, overflow, budget, budget_lock)
        ),
        asyncio.create_task(
            _bounded_stream(process.stderr, stderr_descriptor, overflow, budget, budget_lock)
        ),
    )
    wait_task = asyncio.create_task(_wait_for_parent_exit(process))
    overflow_task = asyncio.create_task(overflow.wait())
    outcome: str
    try:
        done, _ = await asyncio.wait(
            (wait_task, overflow_task),
            timeout=HOST_WATCHDOG_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            outcome = "deadline_failure"
        elif overflow_task in done and overflow.is_set():
            outcome = "transport_failure"
        else:
            await wait_task
            outcome = "completed" if process.returncode == 0 else "transport_failure"
            _, pending_readers = await asyncio.wait(
                readers, timeout=HOST_PIPE_DRAIN_GRACE_SECONDS
            )
            if not pending_readers:
                await asyncio.gather(*readers, return_exceptions=False)
        await _terminate_process_tree(process)
        try:
            await asyncio.wait_for(
                asyncio.gather(*readers, return_exceptions=False),
                timeout=HOST_TEARDOWN_SECONDS,
            )
        except TimeoutError:
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            raise ValueError("trial host pipe teardown could not be confirmed") from None
        return outcome
    except BaseException:
        await _terminate_process_tree(process)
        try:
            await asyncio.wait_for(
                asyncio.gather(*readers, return_exceptions=True),
                timeout=HOST_TEARDOWN_SECONDS,
            )
        except TimeoutError:
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            raise ValueError("trial host teardown could not be confirmed") from None
        raise
    finally:
        overflow_task.cancel()
        await asyncio.gather(overflow_task, return_exceptions=True)
