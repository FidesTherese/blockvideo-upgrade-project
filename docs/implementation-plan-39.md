# D39 Exact-Candidate Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify the exact clean D35 candidate commit named by the D36 freeze manifest from external verifier tooling and produce content-bound regression, migration, recovery, browser, media, documentation, and secret-scan evidence without changing the candidate.

**Architecture:** A separate external materializer validates D36 and creates an exact
read-only runtime plus canonical materialization evidence. D39 tooling derives exactly
three fresh external writable sandboxes from independently reverified runtime bytes:
the smoke producer owns one separate smoke sandbox, while the final verifier owns one
backend sandbox for commands 1–5 and one frontend sandbox for commands 6–9 and validates
the bound smoke manifest. Each tool rehashes tracked source throughout its group, runs the fixed
command allowlist with per-command evidence and all writable state external, proves the original
candidate unchanged, and cleans runtime/temp state in `finally`. The verifier has its own source attestation; behavior failures require a new D36 freeze, while verifier-only fixes require a new verifier hash and complete evidence rerun.

**Tech Stack:** Python 3.12, subprocess, Git CLI, uv, pnpm 10.18.3, pytest/Ruff/Vitest/Vite/ESLint, SQLite, FFmpeg, browser smoke evidence, canonical JSON/SHA-256.

## Global Constraints

- Follow `docs/plan-c/work-unit-39.md`, the D37 Task 1 shared D37-D40 result-schema boundary in `docs/DTD.md`, and the clarified external-tool sequencing.
- D39 produces only the separate `VerificationManifest`; it does not consume, redefine, normalize, or fork D37's shared evaluation-result schema. D40 cross-binds D39 evidence independently from the D38-accepted shared-schema bundle.
- Run only against an isolated clean checkout/worktree whose HEAD equals `FreezeManifest.git_commit`.
- Verifier code lives under `backend/evaluation`/`backend/evaluation/scripts`; production `app` never imports `evaluation`, and later verifier code is never copied into or imported by the candidate checkout.
- Candidate and materialized runtime `.venv`, `node_modules`, package-manager caches,
  build output, databases, media, browser profiles, logs, and writable runtime files
  are forbidden. Use verifier-owned writable temporary siblings outside both roots;
  runtime source directories/files remain read-only.
- Capture candidate tracked and ignored-path snapshots around each execution group and
  assert equality. Independently rehash runtime bytes/permissions/file types before
  deriving and after discarding each group. Hash each sandbox's tracked source before
  execution, after every command or fixed smoke stage, and at group end. Candidate and
  immutable runtime remain read-only and unchanged. Generated evidence is allowed only
  in the explicitly external evidence root.
- Any D39 behavior fix is made on the development branch and creates a new D36 freeze; rerun affected D37/D38/D39 evidence.
- A verifier/tooling-only fix creates a new D39 tool hash and requires a complete D39 evidence rerun; candidate ID remains unchanged.
- Synthetic/fake content providers are mandatory; no real user/private data or cloud spend.
- D39 does not tag, publish, deploy, or decide readiness.
- Final delivery commit is `[DONE] Mission 39 Verify exact frozen release candidate`.

---

### Task 1: Verification contracts, command allowlist, and drift protection

**Files:**
- Create: `backend/evaluation/runtime_materialization.py`
- Create: `backend/evaluation/scripts/materialize_candidate_runtime.py`
- Create: `backend/evaluation/release_verification.py`
- Create: `backend/evaluation/scripts/verify_release_candidate.py`
- Create: `backend/tests/test_d39_release_verification.py`

**Interfaces:**

```python
D39_REQUIRED_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...]

class CommandEvidence(BaseModel):
    name: str
    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    started_at: str
    finished_at: str
    stdout_sha256: str
    stderr_sha256: str

class RuntimeMaterialization(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    git_commit: str
    freeze_sha256: str
    candidate_snapshot_sha256: str
    runtime_instance_id: str
    runtime_files: tuple[FileFingerprint, ...]
    runtime_source_sha256: str
    status: Literal["materialized"]

class VerificationManifest(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    git_commit: str
    freeze_sha256: str
    verifier_tool_sha256: str
    status: Literal["passed", "failed"]
    commands: tuple[CommandEvidence, ...]
    smoke_manifest_sha256: str
    smoke_manifest: SmokeManifest
    secret_scan_passed: bool
    candidate_clean_before: Literal[True]
    candidate_clean_after: Literal[True]
    candidate_snapshot_before_sha256: str
    candidate_snapshot_after_sha256: str
    materialization_sha256: str
    runtime_instance_id: str
    runtime_source_sha256: str
    runtime_snapshot_after_sha256: str
    cleanup_status: Literal["completed", "failed"]

materialize_candidate_runtime(
    *, candidate_root: Path, freeze_manifest_path: Path,
    work_root: Path, output_path: Path,
) -> RuntimeMaterialization
cleanup_candidate_runtime(
    *, runtime_root: Path, work_root: Path, materialization_path: Path,
    expected_materialization_sha256: str,
) -> None
verify_release_candidate(
    *, candidate_root: Path, freeze_manifest_path: Path,
    runtime_root: Path, materialization_path: Path,
    expected_materialization_sha256: str, work_root: Path,
    cache_root: Path, output_dir: Path, smoke_manifest_path: Path,
) -> VerificationManifest
```

CLI (Git Bash):

```bash
python -m evaluation.scripts.materialize_candidate_runtime --candidate-root ../../blockvideo-d35-candidate --freeze-manifest "$(find ../release-evidence/d36 -mindepth 2 -maxdepth 2 -name freeze-manifest.json -print -quit)" --work-root D:/blockvideo-verifier/work --output D:/blockvideo-verifier/evidence/d39-materialization/runtime-materialization.json
python -m evaluation.scripts.verify_release_candidate --candidate-root ../../blockvideo-d35-candidate --freeze-manifest "$(find ../release-evidence/d36 -mindepth 2 -maxdepth 2 -name freeze-manifest.json -print -quit)" --runtime-root D:/blockvideo-verifier/work/runtime-<instance> --materialization D:/blockvideo-verifier/evidence/d39-materialization/runtime-materialization.json --expected-materialization-sha256 <DETACHED_64_HEX_SHA256> --work-root D:/blockvideo-verifier/work --cache-root D:/blockvideo-verifier/cache --output D:/blockvideo-verifier/evidence/d39 --smoke-manifest D:/blockvideo-verifier/evidence/d39-smoke/manual-smoke.json
```

- [ ] **Step 1: Write RED command/drift tests**

Assert the separate materializer verifies the detached candidate commit/fingerprints,
creates exactly `<work_root>/runtime-<runtime_instance_id>` as a new non-symlink
runtime, copies only tracked verified
regular files, rejects special files/escaping links, independently verifies every
hash/size plus freeze aggregate, emits canonical materialization evidence, and marks
runtime source read-only. Assert a partial runtime is removed on any failure. Then
assert only fixed argv tuples run with `shell=False`; no command executes directly in
that read-only source. Across D39 tooling, create exactly three random non-symlink
external sandboxes from independently reverified runtime tracked files: the final
verifier owns one backend group for commands 1–5 and one frontend group for commands
6–9; the smoke producer owns one separate smoke group. Verify each
sandbox's tracked-source hash before execution, after every command or fixed smoke
stage, and at group end. The backend uv environment persists through commands 1–5
only; frontend `node_modules`, pnpm/npm cache/store, and build state persist through
commands 6–9 only; smoke reuses neither sandbox. Use sandbox backend/frontend paths as
cwd and discard each sandbox and all non-evidence state in `finally`. None is the
candidate or immutable runtime root. Record a full candidate tracked-file hash plus
ignored/untracked inventory around each group. Each responsible D39 tool verifies the
detached expected materialization hash before parse, cross-binds candidate/freeze/
runtime instance/source hash, then independently walks runtime bytes, permissions,
and file types before deriving and after discarding its group. The final verifier
repeats the runtime/candidate checks before accepting smoke evidence. Modify a candidate or runtime tracked byte/permission, add a runtime file, or
create an ignored `.venv`, `node_modules`, cache, DB, media, or runtime file in either
source root during a fake command and assert `status="failed"` with no subsequent
commands.

- [ ] **Step 2: Define the exact nine-entry allowlist**

Use exactly these ordered `(name, argv)` entries once each. Entries 1–5 share the
single fresh backend sandbox in order; entries 6–9 share the single fresh frontend
sandbox in order. The separate fresh smoke sandbox contributes no command entry:

```text
backend_uv_sync           ("python", "-m", "uv", "sync", "--frozen")
backend_import            ("python", "-m", "uv", "run", "python", "-c", "import app.main")
backend_pytest            ("python", "-m", "uv", "run", "pytest")
backend_ruff              ("python", "-m", "uv", "run", "ruff", "check", ".")
backend_d31_d35           ("python", "-m", "uv", "run", "pytest", "tests/test_d31_adversarial_safety.py", "tests/test_d32_concurrency_matrix.py", "tests/test_d33_recovery_matrix.py", "tests/test_d34_migrations.py", "tests/test_d35_startup_recovery_api.py", "-q")
frontend_pnpm_install     ("npx", "-y", "pnpm@10.18.3", "install", "--frozen-lockfile")
frontend_test             ("npx", "-y", "pnpm@10.18.3", "test")
frontend_build            ("npx", "-y", "pnpm@10.18.3", "build")
frontend_lint             ("npx", "-y", "pnpm@10.18.3", "lint")
```

The verifier records one unchanged `CommandEvidence` per command; grouping never
coalesces command evidence. It records argv as arrays and never accepts an arbitrary
command from CLI/input JSON. Missing, duplicate, extra, reordered, or name/argv-
mismatched entries fail verification, and every recorded `exit_code` must equal zero.

- [ ] **Step 3: Implement bounded execution and evidence hashing**

Limit each stdout/stderr file to 2 MiB, retain exit code/timestamps/hash, use process timeouts fixed per command, and atomically rewrite the verification manifest. Set `UV_PROJECT_ENVIRONMENT`, `UV_CACHE_DIR`, pnpm store/cache, npm cache, temporary
directory, application storage, browser profile, and build-output variables/arguments
to the current group's verifier-owned writable execution/temp root outside candidate
and immutable runtime. In `finally`, call
`cleanup_candidate_runtime()` to validate the single-use marker, evidence hash, and
containment, then remove read-only runtime plus environment/cache/temp/browser/DB/
media roots while preserving bounded evidence. Cleanup is idempotent; cleanup failure
sets both manifest status and `cleanup_status` to failed. The materializer cleanup CLI
handles a successful runtime whose verifier never started and refuses unbound or
out-of-root paths. Attest `evaluation/runtime_materialization.py`,
`evaluation/release_verification.py`, `evaluation/tool_attestation.py`,
`evaluation/scripts/materialize_candidate_runtime.py`,
`evaluation/scripts/d39_smoke.py`, and `evaluation/scripts/verify_release_candidate.py` separately from D36. Atomically emit the canonical attestation as `verifier-tool-attestation.json`; require its `aggregate_sha256` to equal `VerificationManifest.verifier_tool_sha256`. Record the exact D36 freeze-manifest raw-byte SHA-256 as `VerificationManifest.freeze_sha256`. No production `app` module may import any of them.

- [ ] **Step 4: Run focused tests**

```bash
cd backend
python -m uv run pytest tests/test_d39_release_verification.py -k "command or drift or failure" -q
python -m uv run ruff check evaluation/runtime_materialization.py evaluation/release_verification.py evaluation/scripts/materialize_candidate_runtime.py evaluation/scripts/verify_release_candidate.py tests/test_d39_release_verification.py
```

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/evaluation/runtime_materialization.py backend/evaluation/release_verification.py backend/evaluation/scripts/materialize_candidate_runtime.py backend/evaluation/scripts/verify_release_candidate.py backend/tests/test_d39_release_verification.py
git commit -m "feat: add exact-candidate verification runner"
```

### Task 2: Installation, migration, mode, secret, and evidence verification

**Files:**
- Modify: `backend/evaluation/release_verification.py`
- Modify: `backend/tests/test_d39_release_verification.py`
- Create: `backend/evaluation/scripts/d39_smoke.py`

**Interfaces:**

```python
class SmokeManifest(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    git_commit: str
    freeze_sha256: str
    materialization_sha256: str
    runtime_instance_id: str
    runtime_source_sha256: str
    legacy_migration_sha256: str
    restore_sha256: str
    all_tools_startup_sha256: str
    stateful_startup_sha256: str
    browser_sha256: str
    ffmpeg_sha256: str

run_candidate_smokes(
    runtime_root: Path, materialization: RuntimeMaterialization, output_dir: Path
) -> SmokeManifest
scan_candidate(candidate_root: Path, evidence_root: Path) -> bool
```

- [ ] **Step 1: Write RED smoke/evidence tests**

Assert the exact nine ordered command name/argv entries occur once each with zero
exit codes. Assert clean install/import in an external temporary environment,
migration of the committed synthetic legacy fixture, backup hash/integrity/restore,
all-tools and stateful startup health, and exact lowercase 64-hex validation for the
legacy migration, restore, both startup, browser, and FFmpeg evidence hashes. Cross-bind candidate ID, D35 commit, freeze hash, materialization hash, runtime
instance, and runtime source hash. Canonicalize and hash the complete `SmokeManifest`,
embed it in `VerificationManifest`, and require the embedded content's hash to equal
`smoke_manifest_sha256`. Missing, altered, empty-hash, or differently bound smoke
evidence fails.

- [ ] **Step 2: Implement candidate-side smoke orchestration externally**

`evaluation/scripts/d39_smoke.py` consumes the already materialized runtime and
record; it never materializes or mutates source. After an independent runtime recheck,
it invokes only committed candidate CLIs/tests in subprocesses from the third fresh
runtime-derived writable sandbox and writes to external evidence. It does not reuse
backend/frontend installed state, contributes no entry to `D39_REQUIRED_COMMANDS`,
verifies tracked source before/after each fixed smoke stage, and discards the sandbox. It starts each D30 demo mode on loopback with external synthetic storage and browser profile, polls `/api/startup` and `/api/health`, records fixed response fields, then terminates it cleanly. It invokes real FFmpeg with fake providers through the existing synthetic test path. It never imports candidate modules into the verifier process.

- [ ] **Step 3: Implement secret/private/generated-artifact scanning**

Scan tracked candidate bytes and D39 evidence for known environment key names, credential patterns, `.env`, DB/media/model/cache/runtime artifacts, and private absolute path prefixes. Record rule ID/count only; never record matched values. Reject files exceeding the documented evidence size bounds.

- [ ] **Step 4: Run full verifier tests**

```bash
cd backend
python -m uv run pytest tests/test_d39_release_verification.py -q
python -m uv run ruff check evaluation/runtime_materialization.py evaluation/release_verification.py evaluation/scripts/materialize_candidate_runtime.py evaluation/scripts/verify_release_candidate.py evaluation/scripts/d39_smoke.py tests/test_d39_release_verification.py
```

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/evaluation/runtime_materialization.py backend/evaluation/release_verification.py backend/evaluation/scripts/materialize_candidate_runtime.py backend/evaluation/scripts/verify_release_candidate.py backend/evaluation/scripts/d39_smoke.py backend/tests/test_d39_release_verification.py
git commit -m "feat: verify D39 smoke and evidence integrity"
```

### Task 3: Browser/media manifest and exact D36 run

**Files:**
- Create outside every repository during execution: `D:/blockvideo-verifier/evidence/d39-materialization/runtime-materialization.json`
- Create outside every repository during execution: `D:/blockvideo-verifier/evidence/d39-smoke/manual-smoke.json`
- Create outside every repository during execution: `D:/blockvideo-verifier/evidence/d39/verification-manifest.json`
- Create outside every repository during execution: `D:/blockvideo-verifier/evidence/d39/verifier-tool-attestation.json`

**Interfaces:**
- Materialization evidence binds exact candidate/freeze bytes to one read-only runtime
  instance. Manual/smoke manifest binds that same materialization/runtime and
  references hashed bounded evidence for both modes, recovery UI journey, one real
  FFmpeg fake-provider MP4, migration/restore, and documentation review.
- No file path in canonical evidence is absolute; aliases are `candidate`, `tooling`, and `evidence`.

- [ ] **Step 1: Recreate or verify the detached candidate checkout**

```bash
python -c "import json,pathlib,subprocess; manifests=list(pathlib.Path('release-evidence/d36').glob('*/freeze-manifest.json')); assert len(manifests)==1; m=json.loads(manifests[0].read_text()); p=pathlib.Path('../blockvideo-d35-candidate'); subprocess.run(['git','worktree','add','--detach',str(p),m['git_commit']],check=True) if not p.exists() else None; assert subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()==m['git_commit']; assert not subprocess.check_output(['git','-C',str(p),'status','--porcelain'],text=True).strip(); assert not subprocess.check_output(['git','-C',str(p),'status','--ignored','--porcelain'],text=True).strip()"
```

- [ ] **Step 2: Materialize the candidate runtime and detach its evidence hash**

Run `evaluation.scripts.materialize_candidate_runtime` into new external work/evidence
roots. Compute the canonical materialization file's SHA-256 through a separate
operator channel, verify runtime source is read-only and exactly matches D36, and use
that detached digest for smoke/final verification. If materialization fails, assert no
partial runtime remains.

- [ ] **Step 3: Produce bounded synthetic browser/media evidence**

Exercise all-tools and stateful startup, D35 waiting/safe-retry/unknown/migration-failed states, keyboard flow, 390 px layout, and playback of a real FFmpeg MP4 generated with fake providers. Independently reverify the exact materialized runtime, derive the separate fresh smoke sandbox, rehash its tracked source before/after every fixed smoke stage, discard it, and save evidence only under
`D:/blockvideo-verifier/evidence/d39-smoke/`; create canonical `manual-smoke.json`
containing candidate ID, commit, freeze hash, materialization hash, runtime instance,
runtime source hash, evidence SHA-256/size, environment versions, and explicit
pass/fail values. Recheck the candidate tracked/ignored snapshot after browser and media work.

- [ ] **Step 4: Run the external verifier**

```bash
cd backend
python -m uv run python -m evaluation.scripts.verify_release_candidate --candidate-root ../../blockvideo-d35-candidate --freeze-manifest "$(find ../release-evidence/d36 -mindepth 2 -maxdepth 2 -name freeze-manifest.json -print -quit)" --runtime-root D:/blockvideo-verifier/work/runtime-<instance> --materialization D:/blockvideo-verifier/evidence/d39-materialization/runtime-materialization.json --expected-materialization-sha256 <DETACHED_64_HEX_SHA256> --work-root D:/blockvideo-verifier/work --cache-root D:/blockvideo-verifier/cache --output D:/blockvideo-verifier/evidence/d39 --smoke-manifest D:/blockvideo-verifier/evidence/d39-smoke/manual-smoke.json
cd ..
git -C ../blockvideo-d35-candidate status --porcelain
git -C ../blockvideo-d35-candidate status --ignored --porcelain
```

Both final candidate status outputs must match their recorded pre-run snapshots
exactly. The verification manifest must record the exact nine command entries once each with
zero exits, embedded smoke content/hash and six mandatory smoke hashes, matching
materialization/runtime hashes, `secret_scan_passed is true`, both clean flags true,
`candidate_snapshot_before_sha256 == candidate_snapshot_after_sha256`,
`runtime_snapshot_after_sha256 == runtime_source_sha256`, and
`cleanup_status="completed"`; the runtime and all non-evidence temp roots must no
longer exist after verifier exit, and the verifier's final pre-cleanup runtime byte
snapshot must match. Candidate status remains normally empty; the worktree's `.git`
administrative file is outside status output. No `.venv`, `node_modules`, cache, build, DB, media, browser, log, or runtime artifact may exist in the candidate. A failing candidate command is not repaired in this checkout.

- [ ] **Step 5: Classify failures exactly**

If failure is candidate behavior, stop and return to D36 with a new candidate; invalidate/rerun affected D37-D39 evidence. If failure is only verifier code, update tooling, ensure a new verifier attestation hash, delete no prior evidence, and run D39 again into a new evidence directory.

### Task 4: Documentation reconciliation and D39 gate

**Files:**
- Create: `docs/plan-c/work-report-39.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `docs/DTD.md`, `specification.md`, and `docs/modules/operation-core.md` only on the tooling branch; any candidate-behavior documentation change requires a new D36 freeze if fingerprinted

**Interfaces:**
- Report candidate ID/commit, D36 freeze hash, verification-manifest hash, verifier source-attestation hash, every command/evidence hash/status, skipped environment check, and failure classification.

- [ ] **Step 1: Verify later tooling itself**

```bash
cd backend && python -m uv run pytest tests/test_d39_release_verification.py tests/test_d38_result_import.py tests/test_d37_blinded_runner.py -q
cd backend && python -m uv run ruff check .
```

- [ ] **Step 2: Reconcile documentation and inspect outputs**

```bash
git status --short
git diff --check
git ls-files .env storage release-evidence
```

Do not edit the D36 worktree. Record whether candidate verification passed; do not infer release readiness.

- [ ] **Step 3: Commit and push the verifier tooling task**

```bash
git add backend docs/plan-c/work-report-39.md docs/plan-c/handoff.md docs/DTD.md specification.md docs/modules/operation-core.md
git commit -m "[DONE] Mission 39 Verify exact frozen release candidate"
git push
```

Do not tag, publish, deploy, create a GitHub release, or start D40 with missing mandatory D39 evidence.
