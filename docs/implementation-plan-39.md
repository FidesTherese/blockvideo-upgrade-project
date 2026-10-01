# D39 Exact-Candidate Verification Implementation Plan

> Future implementation only. The 2026-09-30 stack audit changes documentation, not source, candidate, locks or evidence. Use `docs/DTD.md` as the implementation contract and execute its probe prerequisites sequentially before claiming integration acceptance.

**Goal:** Verify immutable D35 `522775516c0797abdb313e3432339a3a444b7ae2` through external tooling, with installation, regression, migration/restore, both-mode, browser/media, automated documentation and secret-scan evidence. No release approval is inferred.

**Architecture:** A separate materializer publishes a verified read-only runtime and physical ownership marker. Independently verified runtime bytes seed exactly three fresh writable external groups: backend commands 1–5, frontend commands 6–9, and a separate smoke group. Every group rehashes tracked source before/after each command/stage; runtime and original candidate snapshots remain unchanged. Cleanup removes only owned objects, preserving bounded canonical evidence. `app` never imports evaluation tools; no tool is copied into candidate source.

**Stack:** Windows 11, Python 3.12.12, uv 0.12.15, Node 24.11.1 (24.x >=24), pnpm exactly 10.18.3, exact D35 manifests/locks, existing pytest/Ruff/Vitest/Vite/ESLint/SQLite/FFmpeg. Optional `dev` and `retrieval` extras are selected explicitly. Browser automation uses an owned installed Chrome/Chromium and the existing locked websockets 16.1.1 CDP transport, not a new candidate dependency.

## Constraints and facts not yet verified

- D38 and shared strict parser/host/index prerequisites precede this unit. D39 imports pure shared evidence/smoke contracts, never forks D37 result/protocol models or calls private evaluation.
- Fresh extras install, native launcher/esbuild availability and browser protocol/ownership roundtrip are pending. D37 already proved exact-D35 synthetic index/worker behavior; it is not D39 fresh-sandbox or new-budget acceptance. Pinned README advertises Python 3.13+/Node 20+ rather than the audited lane: the mandatory documentation check has a known blocker. No candidate edit, stack substitution or silent gate waiver is authorized; a successor candidate or explicit policy revision requires separate user scope. Absent runtime support fails rather than silently skipping or downloading weights.
- Candidate/runtime contain no venv, node_modules, caches, build output, database, media, profile, logs or evidence. All writable state is group-local outside both roots. No candidate source/config/lock mutation, real data or cloud spend.
- Hard aggregate project RAM <=4 GiB, target <=3 GiB; start no nontrivial job at >=3.5 GiB. Include agent runtime and all owned descendants; sample before/during checks and reserve headroom. One execution group/command at a time, one test/build worker and one NumPy/ONNX thread. Use bounded reads/output; stop only owned work before the cap. Earlier larger-budget gates do not establish 4 GiB compliance.
- Preserve published evidence. A candidate behavior defect requires a new candidate and D36 boundary; a tooling-only correction requires a new source attestation and new evidence/run ID. Final evaluation waits for the final committed tooling closure.
- This unit cannot tag, push a release, publish, deploy or decide readiness. Future tooling delivery follows the repository workflow; this audit specifically does not push.

The DTD's D39 implementation-precision section fixes RuntimeMaterialization,
ownership/cleanup fields and in-place marker lifecycle, per-child identities,
OwnedProcessScope/run_owned_command/long-lived child APIs, role/alias/version maps,
4 GiB group accounting, failed summary/null semantics and four bounded scan rules.
Implement those contracts verbatim; no identity-blind cleanup or guessed fields.
D40's shared canonical typed-array API belongs to evidence_json, preserving its
existing model parser; compact gate families evaluate every category without
unbounded per-category output. These precision amendments precede code.

## Task 1: Pure contracts, materialization and owned execution

**Files:** Create `backend/evaluation/smoke_contracts.py`, `runtime_materialization.py`, `release_verification.py`, materialization/verification CLIs under `backend/evaluation/scripts/`, and `backend/tests/test_d39_release_verification.py`. Extend `blinded_runtime.py` only through the DTD `run_owned_command` API. Shared JSON parsing is a prerequisite, not a second parser here.

**Contracts:** Import DTD `ToolExecutionBinding`, `SmokeStageReceipt`, six discriminated summary variants and `SmokeManifest` from `smoke_contracts`; it never imports executors. `CommandEvidence` and `VerificationManifest` have exactly the fields/types in DTD D39: canonical argv plus native resolved argv/tool bindings, exact deadline/outcome, nullable failed exit, output sizes/hashes, failure-prefix commands, nullable unavailable smoke/final snapshots, and truthful bool cleanup/clean state. Strict/frozen/extra-forbid plus raw primitive guards apply to every new model. RuntimeMaterialization binds candidate/commit/freeze/snapshot, instance, sorted file fingerprints, runtime source aggregate, and `status="materialized"`.

```python
def materialize_candidate_runtime(
    *, candidate_root: Path, freeze_manifest_path: Path,
    work_root: Path, output_path: Path,
) -> RuntimeMaterialization: ...

def cleanup_candidate_runtime(
    *, runtime_root: Path, work_root: Path, materialization_path: Path,
    expected_materialization_sha256: str,
) -> None: ...

def verify_release_candidate(
    *, candidate_root: Path, freeze_manifest_path: Path,
    runtime_root: Path, materialization_path: Path,
    expected_materialization_sha256: str, work_root: Path,
    output_dir: Path, smoke_manifest_path: Path,
) -> VerificationManifest: ...
```

- [ ] Add negative tests before implementation: wrong detached hash before parse, cap+1, link/reparse/special files, changed committed source, extra runtime file, write permission drift, replaced marker/root, output inside candidate/runtime, and cleanup interruption.
- [ ] Implement exact tracked-byte copy to `<work_root>/runtime-<runtime_instance_id>`, verify complete streamed size/hash inventory and freeze aggregate, then apply/verify readonly modes. No command executes in runtime source.
- [ ] Create physical <=4 KiB marker beside materialization evidence, bound to instance, directory identity and materialization digest. Follow DTD building/active/cleaning/cleaned transitions. Remove a partial runtime only while ownership remains proven; ownership loss is failed cleanup, never deletion of a replacement.
- [ ] Reuse the existing trusted stdin gate: assign a kill-on-close Windows Job Object before releasing a byte, no breakaway, or POSIX session/group. No suspended native subsystem. Test early parent exit, pipe-holding descendants, cancellation, floods and assignment failure.
- [ ] Confirm descendants/readers are gone within 10 s after 1 s drain grace. Fail fast on deadline, output cap, memory pressure, nonzero exit, source drift or unknown teardown. A failed manifest contains only attempted prefix/actual observations; do not fabricate nine entries or successful hashes.
- [ ] Cleanup verified owned regular files/directories only, clearing Windows readonly bits after identity checks, no junction traversal/ancestor chmod/identity-blind recursive delete. Preserve bounded marker/cleanup receipts. Idempotence requires the same marker/detached binding, not merely an absent path.

## Task 2: Exact nine-command installation and regression inventory

`release_verification.D39_REQUIRED_COMMANDS` is the immutable ordered tuple below. A passed result has every entry exactly once, completed outcome, exit zero, exact deadlines and native/tool bindings. Smoke bootstrap is not a tenth entry.

```text
backend_uv_sync           ("python", "-m", "uv", "sync", "--locked", "--extra", "dev", "--extra", "retrieval", "--no-python-downloads", "--no-config")
backend_import            ("python", "-B", "-c", "import app.main")
backend_pytest            ("python", "-B", "-m", "pytest")
backend_ruff              ("python", "-B", "-m", "ruff", "check", ".")
backend_d31_d35           ("python", "-B", "-m", "pytest", "tests/test_d31_adversarial_safety.py", "tests/test_d32_concurrency_matrix.py", "tests/test_d33_recovery_matrix.py", "tests/test_d34_migrations.py", "tests/test_d35_startup_recovery_api.py", "-q")
frontend_pnpm_install     ("npx", "-y", "pnpm@10.18.3", "install", "--frozen-lockfile", "--prod=false", "--ignore-scripts")
frontend_test             ("npx", "-y", "pnpm@10.18.3", "test", "--maxWorkers=1", "--minWorkers=1", "--no-file-parallelism")
frontend_build            ("npx", "-y", "pnpm@10.18.3", "build")
frontend_lint             ("npx", "-y", "pnpm@10.18.3", "lint")
```

| Command, in order | Deadline seconds |
|---|---:|
| backend_uv_sync | 600 |
| backend_import | 30 |
| backend_pytest | 1800 |
| backend_ruff | 120 |
| backend_d31_d35 | 600 |
| frontend_pnpm_install | 600 |
| frontend_test | 600 |
| frontend_build | 300 |
| frontend_lint | 180 |

- [ ] Prove native bootstrap Python 3.12.12 and its uv 0.12.15 origin/version/hash. Set `UV_PYTHON` to the verified absolute executable, `UV_PROJECT_ENVIRONMENT` and uv cache inside the backend group. Optional extras are not default dev groups; `--locked` rejects stale metadata rather than updating it. Check the created interpreter/base and package origins, including NumPy/ONNXRuntime/tokenizers, before command 2.
- [ ] Resolve commands 2–5 directly to that sandbox venv Python. No `uv run` resync, global pytest/Ruff fallback or ambient Python imports. Retrieval extras eliminate NumPy-based ONNX unit-test skips; fake loopback runtime embeddings need HTTPX, not optional ONNX wheels, and do not load weights.
- [ ] Resolve `node.exe` plus installed `npx-cli.js`, run `(node_exe, npx_cli, *canonical_argv[1:])` with `shell=False`, and bind actual pnpm.cjs 10.18.3 hash/version. Never launch .cmd/.bat. Canonical argv and alias-resolved native argv are different evidence fields, not a false assertion they were identical.
- [ ] Apply the exact DTD group-local env/cache/temp/config policy and low concurrency: uv downloads 2/builds 1/installs 1, pnpm network 2/child 1, Node heap 512 MiB, Vitest one worker and thread limits one. Strip inherited provider credentials/config/production-only settings; writable generated `.npmrc` is untracked sandbox state, not candidate mutation.
- [ ] Stream/drain shared stdout+stderr <=2 MiB per command, record complete sizes/hashes without raw content in the manifest, stop subsequent commands on first failure and clean the group in finally.
- [ ] Check locked native esbuild after ignored-script install before build. Candidate `allowBuilds` is not assumed valid authorization under pinned v10. There is no automatic rebuild, new v12 flag, lock repair or broad dependency script approval. Missing native build capability blocks the lane; a future narrowly authorized v10 change needs a new documented/probed run contract.
- [ ] Explicit pinned package test/build/lint scripts may internally use a shell; trusted script source and fixed args are the boundary, not a claim of shell-free npm internals.

## Task 3: Genuine synthetic smoke and six typed receipts

**Files:** Create `backend/evaluation/browser_smoke.py`, `backend/evaluation/scripts/d39_smoke.py` and internal candidate-rooted bootstrap `backend/evaluation/scripts/d39_candidate_smoke.py`; extend the focused D39 tests. No candidate modules are imported into the external smoke-controller process.

```python
def run_candidate_smokes(
    *, candidate_root: Path, freeze_manifest_path: Path,
    runtime_root: Path, materialization_path: Path,
    expected_materialization_sha256: str, work_root: Path, output_dir: Path,
) -> SmokeManifest: ...
```

- [ ] Independently verify runtime/candidate, derive a third fresh group, and install its own backend extras/frontend frozen dev state with the same native/environment policy. Do not reuse either command group.
- [ ] Run exactly six DTD stages in order: legacy_migration (120 s), restore (120 s), all_tools_startup (180 s), stateful_startup (180 s), browser (300 s), ffmpeg (300 s). Enable/read back SQLite foreign_keys on every new synchronous test connection before transactions.
- [ ] Generate/load a genuine candidate-compatible index through committed candidate load_sources/publish_index/load_index in a candidate-rooted subprocess. Pinned D35 demo_settings hardcodes ONNX profile/endpoints; do not assume env overrides work. The external d39_candidate_smoke bootstrap uses exact verified prepare_storage/exclusive_demo/demo_settings/create_demo_app seams, explicitly sets synthetic chat/profile/embedding/index values before create_demo_app, then runs owned loopback Uvicorn (one worker/no reload). No source/.env mutation, current-demo substitution, arbitrary Python expression, dummy index, fallback-only proof, ONNX weights or provider spend.
- [ ] Emit <=64 KiB strict discriminated receipt per stage with exact candidate/commit/freeze/materialization/runtime bindings, actual outcome, typed summary, tool executable/launcher versions/hashes and complete artifact sizes/hashes. Stream transient media <=32 MiB and hash before disposal; retain only bounded canonical receipts/summaries and allowed evidence. No arbitrary supplied six hashes stand for performed stages.
- [ ] `SmokeManifest` retains exactly its six named stage hash fields plus exactly six embedded `stage_receipts` in fixed order. Each named hash is SHA-256 of that receipt's complete LF-terminated canonical bytes. The <=1 MiB complete smoke manifest hashes with LF too. Final verifier independently validates receipt bytes/sizes, summary schemas/results, versions and bindings before embedding it.
- [ ] Exercise an owned installed native Chrome/Chromium through DTD fixed CDP methods and websockets signature, never attach to a user's browser. Verify installed /json/protocol before automation. Check 390/1440 layouts, waiting/safe-retry/unknown-remote/migration-failed states, actual Tab/Enter, one POST from duplicate action, no overflow and playback. Missing browser/driver/method fails, not skipped acceptance.
- [ ] Verify the exact six automated documentation checks from DTD BrowserSummary. These prove paths/version/contracts/commands, not semantic human review. Human/independent acceptance remains separate D40 evidence.
- [ ] Real fake-provider FFmpeg/ffprobe run must bind present video/subtitle and current artifact identities. Scan tracked source and bounded public evidence for secret/private/generated-artifact rules; record only rule IDs/counts, never matched values.
- [ ] Rehash tracked sandbox after every stage; rehash runtime and candidate after group discard. Failed/partial smoke retains only actual receipts, never a fabricated complete SmokeManifest.

## Task 4: Integration gate, source lifecycle and delivery

Examples below are future commands from `backend/` with operator-supplied paths/detached digest, not commands executed in the design audit. Paths name new external owned work/evidence roots. Do not discover or normalize real evaluator evidence.

```bash
python -m evaluation.scripts.materialize_candidate_runtime --candidate-root "$CANDIDATE_ROOT" --freeze-manifest "$FREEZE_PATH" --work-root "$WORK_ROOT" --output "$MATERIALIZATION_PATH"
python -m evaluation.scripts.d39_smoke --candidate-root "$CANDIDATE_ROOT" --freeze-manifest "$FREEZE_PATH" --runtime-root "$RUNTIME_ROOT" --materialization "$MATERIALIZATION_PATH" --expected-materialization-sha256 "$MATERIALIZATION_SHA256" --work-root "$WORK_ROOT" --output "$SMOKE_OUTPUT"
python -m evaluation.scripts.verify_release_candidate --candidate-root "$CANDIDATE_ROOT" --freeze-manifest "$FREEZE_PATH" --runtime-root "$RUNTIME_ROOT" --materialization "$MATERIALIZATION_PATH" --expected-materialization-sha256 "$MATERIALIZATION_SHA256" --work-root "$WORK_ROOT" --output "$VERIFICATION_OUTPUT" --smoke-manifest "$SMOKE_MANIFEST_PATH"
```

- [ ] Run focused synthetic D39 tests/Ruff first, then DTD native/fresh-install/pinned-worker probes sequentially. Full repository checks are future implementation verification, not counted as run by this audit.
- [ ] Before real verification, commit all attested tooling and validate actual project Git root/HEAD/clean source bytes. D39 source attestation covers every imported behavior-affecting helper plus materialization/verify/smoke/browser/internal candidate bootstrap code and dependency manifests. It is distinct from D36/D37/D38 source hashes and candidate identity.
- [ ] Passed verification requires the exact full nine inventory/native bindings, six fully validated receipts, secret scan true, actual clean/snapshot equality, runtime/source equality and completed marker-bound cleanup. A failed run records truthful prefix/nulls and fixed reasons, never synthetic success to fit a model.
- [ ] Final verification cleans runtime in finally; if verifier never starts, the operator invokes the same dedicated cleanup CLI with the bound materialization record. Do not delete previous evidence, candidate data or unrelated roots.
- [ ] Update work-report-39/handoff and affected module notes only during implementation. Distinguish automated results, blocked facts and pending reviews. Real D37 evaluation is deferred until final D38–D40 source closure is committed/pinned and D36 refreshed.
- [ ] Inspect for secrets/generated/private data and deliver tooling under `[DONE] Mission 39 Verify exact frozen release candidate` only after that later task's verification. This plan/audit does not implement, generate evidence or push.
