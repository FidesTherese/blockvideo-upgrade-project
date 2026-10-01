"""Separate owned D39 six-stage synthetic smoke producer; never release approval."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import shutil
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterator, NoReturn

import httpx
from pydantic import TypeAdapter, ValidationError

from evaluation import blinded_io, blinded_runtime, browser_smoke, release_verification as verification
from evaluation import runtime_materialization as materialization
from evaluation.evidence_json import parse_canonical_model
from evaluation.smoke_contracts import (
    AllToolsStartupSummary, BrowserSummary, FFmpegSummary, MigrationSummary, RestoreSummary,
    SMOKE_STAGES, SmokeManifest, SmokeStageReceipt, StatefulStartupSummary, ToolExecutionBinding,
)
from evaluation.tool_attestation import FileFingerprint, canonical_json_bytes

_DEADLINES = (120, 120, 180, 180, 300, 300)
_SUMMARIES = (MigrationSummary, RestoreSummary, AllToolsStartupSummary, StatefulStartupSummary, BrowserSummary, FFmpegSummary)
DOC_KEYS = ('setup_paths', 'locked_versions', 'mode_commands', 'recovery_codes', 'migration_restore', 'limitation_boundary')
_BOOTSTRAP = "import runpy,sys; p=sys.argv.pop(1); runpy.run_path(p,run_name='__main__')"


@contextmanager
def fake_providers() -> Iterator[tuple[str, dict[str, int]]]:
    counts = {'chat': 0, 'embedding': 0}
    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)
        def log_message(self, *arguments: Any) -> None:
            pass
        def do_GET(self) -> None:
            if self.path != '/v1/speakers':
                self.send_error(404)
                return
            raw = json.dumps([{'name': 'D39 synthetic', 'speaker_uuid': 'd39-synthetic', 'styles': [{'name': 'synthetic', 'id': 1}], 'version': 'synthetic'}]).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_POST(self) -> None:
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                self.send_error(400)
                return
            if not 0 < length <= 131072:
                self.send_error(413)
                return
            try:
                body = browser_smoke._json(self.rfile.read(length), maximum=131072)
                if type(body) is not dict:
                    raise ValueError
            except (ValueError, TypeError, RecursionError):
                self.send_error(400)
                return
            if self.path == '/v1/embeddings' and body.get('model') == 'synthetic-d39-embedding':
                counts['embedding'] += 1
                response = {'object': 'list', 'model': body['model'], 'data': [{'object': 'embedding', 'index': 0, 'embedding': [1.0, 0.0]}]}
            elif self.path == '/v1/chat/completions' and body.get('model') == 'synthetic-d39-chat':
                counts['chat'] += 1
                proposal = {'result': {'kind': 'operation', 'operation_id': 'project.subtitle-font-size.set', 'operation_version': 1, 'arguments': {'value': 64}}}
                response = {'model': body['model'], 'choices': [{'message': {'role': 'assistant', 'content': json.dumps(proposal)}, 'finish_reason': 'stop'}]}
            else:
                self.send_error(400)
                return
            if max(counts.values()) > 8:
                self.send_error(429)
                return
            raw = json.dumps(response, allow_nan=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = HTTPServer(('127.0.0.1', 0), Handler)
    server.timeout = 1
    thread = threading.Thread(target=server.serve_forever, daemon=True, name='d39-fake-provider')
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', counts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        if thread.is_alive():
            raise ValueError('fake provider teardown unconfirmed')


def documentation_checks(source: Path, *, contracts_passed: bool) -> dict[str, bool]:
    checks = dict.fromkeys(DOC_KEYS, False)
    required = ('README.md', 'Makefile', 'backend/.env.example', 'backend/pyproject.toml',
                'backend/uv.lock', 'frontend/package.json', 'frontend/pnpm-lock.yaml',
                'backend/scripts/plan_c_demo.py', 'backend/tests/test_d34_migrations.py',
                'backend/tests/test_d35_startup_recovery_api.py', 'specification.md')
    values = {}
    for name in required:
        try:
            materialization._directory((source / name).parent)
            values[name] = blinded_io.read_regular(source / name, maximum=8 * 1024 * 1024).decode('utf-8')
        except (OSError, ValueError, UnicodeError):
            return checks
    checks['setup_paths'] = True
    readme = values['README.md']
    # Exact audited lane; a vague lower minimum is not this promised setup contract.
    checks['locked_versions'] = '3.12' in readme and ('Node.js 24' in readme or 'Node 24' in readme) and '10.18.3' in values['frontend/package.json']
    demo = values['backend/scripts/plan_c_demo.py']
    checks['mode_commands'] = all(name in demo for name in ('all_tools', 'stateful', 'prepare_storage', 'exclusive_demo', 'demo_settings', 'create_demo_app'))
    api_tests = values['backend/tests/test_d35_startup_recovery_api.py']
    checks['recovery_codes'] = contracts_passed and all(name in api_tests for name in ('safe_retry', 'external_outcome_unknown', 'migration_failed'))
    checks['migration_restore'] = contracts_passed and all(name in values['backend/tests/test_d34_migrations.py'] for name in ('restore_database_backup', 'database_lease_unavailable'))
    specification = values['specification.md'].lower()
    checks['limitation_boundary'] = all(name in specification for name in ('held-out', 'human', 'external'))
    return checks


def _installed_browser(value: Path | None) -> Path:
    if value is not None:
        before = value.absolute().lstat()
        if value.is_symlink() or blinded_io.is_reparse(before):
            raise ValueError('browser executable link refused')
        return verification._native_path(value)
    choices = [Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
               Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Google/Chrome/Application/chrome.exe'] if os.name == 'nt' else [Path(p) for name in ('google-chrome', 'chromium', 'chromium-browser') if (p := shutil.which(name))]
    for path in choices:
        if path.is_file():
            return verification._native_path(path)
    raise ValueError('installed native browser unavailable')


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _profile() -> dict[str, Any]:
    return dict(model='synthetic-d39-embedding', weights_sha256='0' * 64, dimensions=2,
                document_prefix='passage: ', query_prefix='query: ', normalization='l2-full-v1',
                transport='local-openai-embeddings-v1', tokenizer_sha256=None, source_revision=None)


async def _candidate_action(scope: blinded_runtime.OwnedProcessScope, group: verification._ExecutionGroup,
                            python: verification._ToolSet, environment: dict[str, str],
                            configuration: dict[str, Any], action: str, *, deadline: int,
                            serving: bool = False) -> Any:
    token = secrets.token_hex(16)
    config_path = group.root / (token + '.config.json')
    await asyncio.to_thread(blinded_io.write_exclusive, config_path, canonical_json_bytes(configuration) + b'\n')
    path = Path(__file__).with_name('d39_candidate_smoke.py')
    # Origin fixed to the current attested bootstrap; caller cannot replace its path.
    await asyncio.to_thread(group.assert_source)
    await asyncio.to_thread(python.verify)
    argv = (str(python.executable), '-B', '-c', _BOOTSTRAP, str(path), '--action', action, '--configuration', str(config_path))
    arguments = dict(scope=scope, argv=argv, cwd=group.source / 'backend', env=environment,
                     stdout_path=group.root / (token + '.out'), stderr_path=group.root / (token + '.err'), deadline_seconds=deadline)
    if serving:
        return await blinded_runtime.start_owned_process(**arguments)
    outcome = await blinded_runtime.run_owned_command(**arguments)
    if outcome.outcome != 'completed' or outcome.exit_code != 0:
        raise ValueError('candidate smoke action failed')
    await asyncio.to_thread(group.assert_source)
    await asyncio.to_thread(python.verify)
    if action == 'contract_tests':
        return None
    return verification._probe_json(await asyncio.to_thread(blinded_io.read_regular, Path(configuration['summary_path']), maximum=65536))


async def _http_health(port: int, *, owner_token: str, child: blinded_runtime.OwnedProcess,
                       deadline: float, expected: str = 'ok') -> None:
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=2) as client:
        async def read(path: str) -> dict[str, Any] | None:
            async with client.stream('GET', f'http://127.0.0.1:{port}' + path) as response:
                if response.status_code != 200:
                    return None
                raw = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    raw.extend(chunk)
                    if len(raw) > 4096:
                        raise ValueError('owned health size exceeded')
                return verification._probe_json(bytes(raw))
        while time.monotonic() < deadline:
            if child.outcome is not None or child.pid < 1:
                raise ValueError('owned server terminated before readiness')
            try:
                owner = await read('/__d39-owned')
                if owner == {'owner': owner_token}:
                    health = await read('/api/health')
                    if health is not None and health.get('status') == expected:
                        return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.05)
    raise ValueError('owned server startup deadline exceeded')


def _make_receipt(*, summary: Any, **fields: Any) -> SmokeStageReceipt:
    try:
        return SmokeStageReceipt(stage=summary.stage, outcome='passed', summary=summary, **fields)
    except ValidationError:
        # Passed-only constraints fail without changing any observed field.
        return SmokeStageReceipt(stage=summary.stage, outcome='failed', summary=summary, **fields)


async def _browser_stage(scope: blinded_runtime.OwnedProcessScope, group: verification._ExecutionGroup,
                         python: verification._ToolSet, env: dict[str, str], config: dict[str, Any],
                         browser_executable: Path | None, base_tools: tuple[ToolExecutionBinding, ...]) -> tuple[dict[str, Any], tuple[ToolExecutionBinding, ...], tuple[FileFingerprint, ...]]:
    chrome = await asyncio.to_thread(_installed_browser, browser_executable)
    chrome_fp = await asyncio.to_thread(verification._native_file, chrome, 'tools/chrome')
    # The sandbox owns browser transport packages too; prove its installed origin/version.
    probe = verification._probe_json(await verification._probe(scope, group, (str(python.executable), '-I', '-B', '-c', "import importlib.metadata,websockets.sync.client,json; print(json.dumps({'version':importlib.metadata.version('websockets'),'origin':websockets.sync.client.__file__}))"), env))
    if probe.get('version') != '16.1.1' or not Path(str(probe.get('origin'))).is_relative_to(group.root / 'env'):
        raise ValueError('websockets sandbox origin/version mismatch')
    sockets_fp = await asyncio.to_thread(verification._tool_file, Path(str(probe['origin'])), 'tools/websockets_module')
    version = (await verification._probe(scope, group, (str(chrome), '--version'), env)).decode('utf-8').strip()
    tools = tuple(sorted((*base_tools, ToolExecutionBinding(role='chrome', version=version, executable=chrome_fp, launcher=None),
                          ToolExecutionBinding(role='websockets', version='16.1.1', executable=python.bindings[0].executable, launcher=sockets_fp)), key=lambda item: item.role))
    normal = config | {'storage': str(group.root / 'media-storage'), 'port': _port(), 'summary_path': str(group.root / 'post-count.json'), 'owner_token': secrets.token_hex(32)}
    failed = config | {'storage': str(group.root / 'failed-storage'), 'port': _port(), 'scenario': 'migration_failed', 'summary_path': str(group.root / 'failed-post-count.json'), 'owner_token': secrets.token_hex(32)}
    server = None
    broken = None
    owned_browser = None
    try:
        # Real fake-provider media gives a usable playback target.
        media_config = config | {'storage': str(group.root / 'media-storage'), 'summary_path': str(group.root / 'browser-media-summary.json')}
        media = await _candidate_action(scope, group, python, env, media_config, 'ffmpeg', deadline=240)
        if not all(media.get(name) is True for name in ('providers_fake', 'video_present', 'subtitle_present', 'publication_bound')):
            raise ValueError('browser media generation failed')
        media_record = verification._probe_json(blinded_io.read_regular(Path(media_config['summary_path']).with_suffix('.media.json'), maximum=65536))
        for kind in ('video', 'subtitle'):
            await asyncio.to_thread(_media_fingerprint, Path(media_config['storage']), media_record, kind)
        # Playback server is the same real candidate app started on the media storage.
        normal['storage'] = media_config['storage']
        server = await _candidate_action(scope, group, python, env, normal, 'serve', deadline=300, serving=True)
        await _http_health(normal['port'], owner_token=normal['owner_token'], child=server, deadline=time.monotonic() + 30)
        projects = await _candidate_action(scope, group, python, env, normal | {'summary_path': str(group.root / 'media-browser-projects.json')}, 'seed_browser', deadline=30)
        projects['media'] = media_record['project_id']
        broken = await _candidate_action(scope, group, python, env, failed, 'serve', deadline=300, serving=True)
        await _http_health(failed['port'], owner_token=failed['owner_token'], child=broken, deadline=time.monotonic() + 30, expected='degraded')
        profile = group.root / 'browser-profile'
        profile.mkdir()
        owned_browser = await blinded_runtime.start_owned_process(scope=scope, argv=(str(chrome), '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-component-update', '--disable-sync', '--disable-extensions', '--disable-default-apps', '--no-proxy-server', '--renderer-process-limit=1', '--disk-cache-size=1048576', '--media-cache-size=1048576', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', '--user-data-dir=' + str(profile), 'about:blank'), cwd=group.root, env=env, stdout_path=group.root / 'chrome.out', stderr_path=group.root / 'chrome.err', deadline_seconds=300)
        screenshots = group.root / 'screenshots'
        screenshots.mkdir()
        browser_config = group.root / 'browser.config.json'
        browser_summary = group.root / 'browser-cdp.summary.json'
        await asyncio.to_thread(blinded_io.write_exclusive, browser_config, canonical_json_bytes(dict(profile=str(profile), base_url=f"http://127.0.0.1:{normal['port']}", migration_url=f"http://127.0.0.1:{failed['port']}/", projects=projects, screenshots=str(screenshots), summary_path=str(browser_summary))) + b'\n')
        # Actual CDP transport uses the attested sandbox module, not the controller's.
        browser_result = await blinded_runtime.run_owned_command(scope=scope, argv=(str(python.executable), '-I', '-B', '-c', _BOOTSTRAP, str(Path(browser_smoke.__file__)), '--configuration', str(browser_config)), cwd=group.root, env=env, stdout_path=group.root / 'browser-cdp.out', stderr_path=group.root / 'browser-cdp.err', deadline_seconds=180)
        if browser_result.outcome != 'completed' or browser_result.exit_code != 0:
            raise ValueError('owned browser observations failed')
        observations = verification._probe_json(await asyncio.to_thread(blinded_io.read_regular, browser_summary, maximum=65536))
        # Backend observer counts actual fixed operation POSTs, not JS click attempts.
        counter_path = Path(normal['summary_path'])
        observations['duplicate_post_count'] = verification._probe_json(blinded_io.read_regular(counter_path, maximum=4096))['operation_posts']
        await _candidate_action(scope, group, python, env, config | {'summary_path': str(group.root / 'contract-test-summary.json')}, 'contract_tests', deadline=180)
        observations.update(stage='browser', narrow_width=390, wide_width=1440,
                            documentation_checks=await asyncio.to_thread(documentation_checks, group.source, contracts_passed=True))
        artifacts = []
        for path in sorted(screenshots.iterdir()):
            size, digest = await asyncio.to_thread(blinded_io.fingerprint_regular, path, maximum=4 * 1024 * 1024)
            artifacts.append(FileFingerprint(path='screenshots/' + path.name, size=size, sha256=digest))
        if await asyncio.to_thread(verification._native_file, chrome, 'tools/chrome') != chrome_fp or await asyncio.to_thread(verification._tool_file, Path(probe['origin']), 'tools/websockets_module') != sockets_fp:
            raise ValueError('browser transport/tool source changed')
        return observations, tools, tuple(artifacts)
    finally:
        for child in (owned_browser, broken, server):
            if child is not None:
                await child.stop()
                await child.wait()


def _media_fingerprint(storage: Path, media: dict[str, Any], name: str) -> FileFingerprint:
    # Internal transient output still cannot select a path outside owned storage.
    relative = FileFingerprint(path=media[name], size=0, sha256='0' * 64).path
    file = storage / relative
    materialization._directory(file.parent)
    size, digest = blinded_io.fingerprint_regular(file, maximum=32 * 1024 * 1024)
    expected = media['manifest'][name]
    if type(expected) is not dict or expected.get('path') != relative or type(expected.get('size')) is not int or expected['size'] != size or expected.get('sha256') != digest:
        raise ValueError('media publication fingerprint mismatch')
    return FileFingerprint(path='media/' + name, size=size, sha256=digest)


async def _run(*, candidate: Path, frozen_path: Path, runtime: Path, path: Path, digest: str,
               work: Path, output: Path, browser_executable: Path | None) -> SmokeManifest:
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1, thread_name_prefix='d39-smoke'))
    record = materialization._bound_materialization(path, digest)
    root = verification._trusted_tool_root()
    attestation = await asyncio.to_thread(verification._attest_verifier, root)
    verification._validate_output(output, root, candidate, runtime, work, path, work / 'not-used-input' / 'smoke.json', frozen_path)
    output.mkdir()
    output_anchor = materialization._open_anchor(output)
    output_identity = output_anchor.identity
    group = None
    scope = blinded_runtime.OwnedProcessScope()
    entered = False
    receipts = []
    async def boundary() -> None:
        await asyncio.to_thread(verification._inventory_boundary, candidate, runtime, work, path, digest, record, root, attestation, frozen_path)
        materialization._assert_directory(output, output_anchor)
    try:
        await boundary()
        group = await asyncio.to_thread(verification._ExecutionGroup, work, runtime, record)
        native = await asyncio.to_thread(verification._native_path, Path(getattr(sys, '_base_executable', sys.executable)))
        node = await asyncio.to_thread(verification._installed_node)
        env = await asyncio.to_thread(verification.build_group_environment, group.root, python_executable=native, node_executable=node)
        await scope.__aenter__()
        entered = True
        bootstrap = await verification._bootstrap_python(scope, group, env)
        install = await verification._execute_command(index=0, group=group, scope=scope, tools=bootstrap, env=env, commands=[])
        if install.outcome != 'completed' or install.exit_code != 0:
            raise ValueError('smoke backend extras installation failed')
        python = await verification._sandbox_python(scope, group, env, bootstrap)
        frontend = await verification._frontend_tools(scope, group, env, node)
        for index in (5, 7):
            command = await verification._execute_command(index=index, group=group, scope=scope, tools=frontend, env=env, commands=[])
            if command.outcome != 'completed' or command.exit_code != 0:
                raise ValueError('smoke frontend bootstrap failed')
            if index == 5:
                await verification._esbuild_preflight(scope, group, frontend, env)
        base_tools = tuple(sorted((*bootstrap.bindings, *python.bindings, *frontend.bindings), key=lambda item: item.role))
        profile = group.root / 'embedding-profile.json'
        await asyncio.to_thread(blinded_io.write_exclusive, profile, canonical_json_bytes(_profile()) + b'\n')
        # Actual installed media executables are mandatory; never package-downloaded.
        media_tools = []
        media_paths = {}
        for role in ('ffmpeg', 'ffprobe'):
            found = shutil.which(role)
            if found is None:
                raise ValueError('installed media executable missing')
            executable = await asyncio.to_thread(verification._native_path, Path(found))
            fingerprint = await asyncio.to_thread(verification._native_file, executable, 'tools/' + role)
            version = (await verification._probe(scope, group, (str(executable), '-version'), env)).decode('utf-8').splitlines()[0]
            media_tools.append(ToolExecutionBinding(role=role, version=version[:512], executable=fingerprint, launcher=None))
            media_paths[role] = str(executable)
        with fake_providers() as (provider_url, provider_counts):
            config: dict[str, Any] = dict(group_root=str(group.root), source_root=str(group.source), storage=str(group.root / 'startup-storage'), frontend=str(group.source / 'frontend/dist'),
                          profile=str(profile), index=str(group.root / 'index'), provider_url=provider_url,
                          model='synthetic-d39-chat', port=_port(), summary_path=str(group.root / 'index-summary.json'), scenario='normal', owner_token=secrets.token_hex(32), **media_paths)
            await _candidate_action(scope, group, python, env, config, 'build_index', deadline=60)
            for position, stage in enumerate(SMOKE_STAGES):
                await boundary()
                await asyncio.to_thread(group.assert_source)
                summary_path = group.root / (stage + '.summary.json')
                stage_config = config | {'summary_path': str(summary_path)}
                if stage in ('legacy_migration', 'restore'):
                    stage_config['storage'] = str(group.root / 'migration-storage')
                elif stage.endswith('_startup'):
                    stage_config['storage'] = str(group.root / (stage + '-storage'))
                elif stage == 'ffmpeg':
                    stage_config['storage'] = str(group.root / 'ffmpeg-storage')
                tools = base_tools
                artifacts: tuple[FileFingerprint, ...] = ()
                started = time.monotonic()
                if stage == 'browser':
                    observations, tools, artifacts = await asyncio.wait_for(_browser_stage(scope, group, python, env, stage_config, browser_executable, base_tools), timeout=_DEADLINES[position])
                else:
                    calls = dict(provider_counts)
                    observations = await _candidate_action(scope, group, python, env, stage_config, stage, deadline=_DEADLINES[position])
                    if stage.endswith('_startup'):
                        if observations['model_calls'] != provider_counts['chat'] - calls['chat']:
                            raise ValueError('startup model counter mismatch')
                        if stage == 'stateful_startup' and observations['embedding_calls'] != provider_counts['embedding'] - calls['embedding']:
                            raise ValueError('startup embedding counter mismatch')
                    if stage == 'ffmpeg':
                        tools = tuple(sorted((*base_tools, *media_tools), key=lambda item: item.role))
                        media = verification._probe_json(blinded_io.read_regular(summary_path.with_suffix('.media.json'), maximum=65536))
                        items = []
                        for name in ('video', 'subtitle'):
                            items.append(await asyncio.to_thread(_media_fingerprint, Path(stage_config['storage']), media, name))
                        artifacts = tuple(items)
                if time.monotonic() - started > _DEADLINES[position]:
                    raise ValueError('smoke stage deadline exceeded')
                summary = TypeAdapter(_SUMMARIES[position]).validate_python(observations, strict=True)
                raw_summary = canonical_json_bytes(summary) + b'\n'
                # Bind only observations bracketed by all source/tool boundaries.
                await asyncio.to_thread(group.assert_source)
                for tool in (bootstrap, python, frontend):
                    await asyncio.to_thread(tool.verify)
                for media_tool in media_tools:
                    if await asyncio.to_thread(verification._native_file, Path(media_paths[media_tool.role]), media_tool.executable.path) != media_tool.executable:
                        raise ValueError('media tool source changed')
                await boundary()
                # Child summary output is disposable; persist only the validated model.
                materialization._assert_directory(output, output_anchor)
                blinded_io.publish_immutable(output / (stage + '.summary.json'), raw_summary, 'smoke_summary', maximum=65536)
                summary_artifact = FileFingerprint(path=stage + '.summary.json', size=len(raw_summary), sha256=hashlib.sha256(raw_summary).hexdigest())
                artifacts = tuple(sorted((*artifacts, summary_artifact), key=lambda item: item.path))
                binding = dict(candidate_id=record.candidate_id, git_commit=record.git_commit, freeze_sha256=record.freeze_sha256,
                               materialization_sha256=digest, runtime_instance_id=record.runtime_instance_id, runtime_source_sha256=record.runtime_source_sha256)
                receipt = _make_receipt(schema_version=1, tools=tools, artifacts=artifacts, summary=summary, **binding)
                raw = canonical_json_bytes(receipt) + b'\n'
                blinded_io.publish_immutable(output / (stage + '.receipt.json'), raw, 'smoke_receipt', maximum=65536)
                if parse_canonical_model(blinded_io.read_regular(output / (stage + '.receipt.json'), maximum=65536), SmokeStageReceipt, maximum=65536) != receipt:
                    raise ValueError('smoke receipt readback drift')
                receipts.append(receipt)
                if receipt.outcome != 'passed':
                    raise ValueError('required smoke observation failed')
        smoke = SmokeManifest(schema_version=1, stage_receipts=tuple(receipts), **binding,
                              **{r.stage + '_sha256': hashlib.sha256(canonical_json_bytes(r) + b'\n').hexdigest() for r in receipts})
    finally:
        try:
            if entered:
                await asyncio.shield(scope.close())
            if group is not None:
                try:
                    await asyncio.to_thread(group.assert_source)
                finally:
                    await asyncio.to_thread(group.cleanup)
        finally:
            if group is not None:
                if group.anchor is not None:
                    verification.freeze._close_directory_anchor(group.anchor)
                verification.freeze._close_directory_anchor(group.work_anchor)
            verification.freeze._close_directory_anchor(output_anchor)
            await asyncio.to_thread(verification._inventory_boundary, candidate, runtime, work, path, digest, record, root, attestation, frozen_path)
    await asyncio.to_thread(verification._inventory_boundary, candidate, runtime, work, path, digest, record, root, attestation, frozen_path)
    # No completed publication until owned group teardown/source checks succeed.
    final_anchor = materialization._open_anchor(output)
    try:
        if final_anchor.identity != output_identity:
            raise ValueError('smoke publication output identity changed')
        materialization._assert_directory(output, final_anchor)
        blinded_io.publish_immutable(output / 'smoke-manifest.json', canonical_json_bytes(smoke) + b'\n', 'smoke_manifest', maximum=1024 * 1024)
    finally:
        verification.freeze._close_directory_anchor(final_anchor)
    return smoke


def run_candidate_smokes(*, candidate_root: Path, freeze_manifest_path: Path, runtime_root: Path,
                         materialization_path: Path, expected_materialization_sha256: str,
                         work_root: Path, output_dir: Path, browser_executable: Path | None = None) -> SmokeManifest:
    try:
        return asyncio.run(_run(candidate=candidate_root.absolute(), frozen_path=freeze_manifest_path.absolute(), runtime=runtime_root.absolute(),
                                path=materialization_path.absolute(), digest=expected_materialization_sha256, work=work_root.absolute(),
                                output=output_dir.absolute(), browser_executable=browser_executable))
    except (OSError, ValueError, TimeoutError, RuntimeError):
        raise ValueError('D39 smoke refused; no complete smoke evidence') from None


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError('D39 smoke arguments refused')


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    for name in ('candidate-root', 'freeze-manifest', 'runtime-root', 'materialization', 'work-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-materialization-sha256', required=True)
    parser.add_argument('--browser-executable', type=Path)
    try:
        values = parser.parse_args(argv)
        run_candidate_smokes(candidate_root=values.candidate_root, freeze_manifest_path=values.freeze_manifest,
                             runtime_root=values.runtime_root, materialization_path=values.materialization,
                             expected_materialization_sha256=values.expected_materialization_sha256,
                             work_root=values.work_root, output_dir=values.output, browser_executable=values.browser_executable)
        print('{"status":"completed"}')
        return 0
    except (OSError, ValueError, RuntimeError):
        print('D39 smoke refused', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
