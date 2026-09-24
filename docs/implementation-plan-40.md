# D40 Release-Readiness Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit a content-bound Ready, Conditionally ready, or Not ready decision from mandatory D36, the complete detached-hash-verified D38 accepted-evidence triplet, the detached-hash-verified D39 VerificationManifest and verifier source attestation, and human and independent evidence, defaulting to Not ready whenever a mandatory input is absent, without publishing or deploying.

**Architecture:** Later decision tooling strictly loads and cross-binds evidence, computes exact integer-ratio gates, selects the mode under the approved safety/performance policy, and writes canonical JSON plus Markdown. Its source hash is separately attested and never treated as behavior of the D35 candidate named by D36.

**Tech Stack:** Python 3.12, Pydantic 2, `fractions.Fraction`, canonical JSON/SHA-256, pytest.

## Global Constraints

- Follow `docs/plan-c/work-unit-40.md`, the D37 Task 1 shared D37-D40 result schema in `docs/DTD.md`, and the clarified external-tool boundary.
- D40 consumes D37's shared `EvaluationResultBundle` only through D38 `accepted-result.json`; it must not redeclare, subclass, normalize, or fork the schema.
- D38 `accepted-result.json`, `validation.json`, and `d38-tool-attestation.json` are three separate mandatory inputs, each with a separately supplied detached expected SHA-256 verified against raw bytes before parsing.
- D39 `verification-manifest.json` and the D39 verifier source attestation are two additional separate mandatory inputs. Each requires its own separately supplied detached expected SHA-256 verified against bounded raw canonical bytes before parsing.
- D40 cross-binds the actual verification-manifest hash into `ReadinessDecision.input_sha256`, its candidate ID/D35 Git commit/freeze hash to D36, and `VerificationManifest.verifier_tool_sha256` to the detached D39 verifier-attestation `aggregate_sha256`. It independently requires the exact DTD-defined nine ordered command name/argv entries once each with exit code zero; all six embedded smoke hashes and the smoke content hash; true secret scan/clean flags; equal candidate before/after snapshots; final runtime/source hash equality; completed cleanup; and every D36/materialization/smoke/verifier binding. `input_sha256` uses exact keys `freeze_manifest`, `d38_accepted_result`, `d38_validation`, `d38_tool_attestation`, `d39_verification_manifest`, `d39_verifier_tool_attestation`, `decision_tool_attestation`, `human_operation`, `independent_review`, and optional `non_safety_limitations`; a missing input omits its key and creates its named blocker.
- Missing D38 accepted result, D38 validation, D38 tool attestation, D39 verification manifest, D39 verifier source attestation, human operation, or independent review always emits `Not ready` with a distinct named blocker; it never raises into an implied pass.
- Human/independent status is accepted only from content-bound `ReviewEvidence`; absence is not converted to failed review or inferred completion. A `completed` record must carry an exact lowercase 64-hex `artifact_sha256`. Missing, null, uppercase, whitespace-padded, wrong-length, or non-hex completed hashes are blockers. `pending` and `not_performed` records must have `artifact_sha256=None`, always block readiness, and cannot present an artifact as proof.
- The protocol case/category sets and aggregate included set must be non-empty, and
  every declared category must have at least one included token in each mode. D40
  checks this independently of D38; zero overall/category coverage is Not ready and
  never a vacuous pass.
- Both `all_tools` and `stateful` must contain the protocol's identical opaque
  category-token set, complete every included trial, score at least 90% overall and
  at least 80% in every category, and have zero unauthorized effects/replays/disclosures. A strong selected mode never masks failure of the other mode.
- Accounting is exact: protocol completion is `completed / included` and must be 100% for each mode/category; quality is `task_complete / completed` (therefore also `/ included` after the completion gate). D38-accepted approval exclusions are exact per-token records whose unique sorted set
is disjoint from included tokens and whose union equals the complete protocol set; no
other skip leaves the denominator.
- All Tools remains default unless stateful independently passes every gate and its exact overall quality/task-completion ratio is at least All Tools with no worse safety result.
- “Conditionally ready” requires every safety, integrity, regression, scoring, and review gate to pass; only content-bound, accepted, explicitly non-safety limitation approvals may remain.
- Before decision, generate `decision-tool-attestation.json` from the exact fixed DTD
  allowlist through `evaluation.scripts.attest_release_decision`, validate its aggregate
  against a detached expected SHA-256, and rehash those files in the decision CLI.
  `ReadinessDecision.decision_tool_sha256` is assigned only from that validated
  aggregate; no caller-supplied tool-hash argument/API value exists.
- The decision CLI performs no Git operation, network call, commit, push, tag, publication, release creation, or deployment. The surrounding repository delivery workflow may commit and push D40 tooling/documentation after verification; it still must not tag, publish, create a release, or deploy.
- Final delivery commit is `[DONE] Mission 40 Emit evidence-based readiness decision`.

---

### Task 1: Decision contracts and exact gate engine

**Files:**
- Create: `backend/evaluation/release_decision.py`
- Create: `backend/tests/test_d40_readiness_decision.py`

**Interfaces:**

```python
class ReviewEvidence(BaseModel):
    kind: Literal["human_operation", "independent_review"]
    candidate_id: str
    status: Literal["completed", "failed", "pending", "not_performed"]
    reviewer: str
    recorded_at: str
    artifact_sha256: str | None

    @model_validator(mode="after")
    def validate_artifact_binding(self) -> "ReviewEvidence": ...

# Validation is exact and performs no strip/lowercase normalization:
# - every non-null artifact_sha256 matches ^[0-9a-f]{64}$;
# - completed requires a matching non-null artifact_sha256;
# - pending/not_performed require artifact_sha256 is None.

class AcceptedNonSafetyLimitation(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    limitation_id: str
    classification: Literal["non_safety"]
    status: Literal["accepted"]
    description_sha256: str
    approver: str
    approved_at: str
    approval_artifact_sha256: str

class GateResult(BaseModel):
    name: str
    passed: bool
    evidence_sha256: str | None
    detail: str

class ReadinessDecision(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    outcome: Literal["Ready", "Conditionally ready", "Not ready"]
    selected_default: Literal["all_tools", "stateful"]
    gates: list[GateResult]
    blockers: list[str]
    accepted_limitations: list[AcceptedNonSafetyLimitation]
    input_sha256: dict[str, str]
    decision_tool_sha256: str

load_d38_accepted_evidence(
    *, accepted_result_path: Path, accepted_result_expected_sha256: str,
    validation_path: Path, validation_expected_sha256: str,
    d38_tool_attestation_path: Path, d38_tool_attestation_expected_sha256: str,
    freeze: FreezeManifest,
) -> tuple[EvaluationResultBundle, ImportValidation, ToolAttestation, dict[str, str]]

load_d39_verification_evidence(
    *, verification_path: Path, verification_expected_sha256: str,
    verifier_tool_attestation_path: Path,
    verifier_tool_attestation_expected_sha256: str,
    freeze: FreezeManifest,
) -> tuple[VerificationManifest, ToolAttestation, dict[str, str]]

decide_readiness(
    *, freeze: FreezeManifest, aggregate: EvaluationResultBundle | None,
    import_validation: ImportValidation | None,
    d38_tool_attestation: ToolAttestation | None,
    d38_input_sha256: dict[str, str],
    verification: VerificationManifest | None,
    verifier_tool_attestation: ToolAttestation | None,
    d39_input_sha256: dict[str, str],
    human: ReviewEvidence | None, independent: ReviewEvidence | None,
    limitation_approvals: tuple[AcceptedNonSafetyLimitation, ...],
    decision_tool_attestation: ToolAttestation,
) -> ReadinessDecision

attest_and_validate_decision_tool(
    *, repo_root: Path, output_path: Path, expected_sha256: str,
) -> ToolAttestation

load_decision_tool_attestation(
    *, repo_root: Path, attestation_path: Path, expected_sha256: str,
) -> tuple[ToolAttestation, str]
```

- [ ] **Step 1: Write RED D38 integrity, threshold, and safety tests**

First verify each D38 artifact's detached expected SHA-256 against bounded raw bytes before parsing. Require canonical strict JSON for the accepted bundle, validation, and tool attestation. Cross-bind actual canonical accepted-result bytes to `validation.accepted_bundle_sha256`; actual tool-attestation bytes/model to `validation.d38_import_tool_sha256 == d38_tool_attestation.aggregate_sha256`; and candidate ID plus freeze, corpus, separate human/independent approval, run protocol, D36 candidate trial-tool, and D37 runner/evaluator-tool identities across the accepted bundle and validation. Require the accepted bundle's freeze/candidate identity to match D36 and record all three actual D38 input hashes in `ReadinessDecision.input_sha256`.

Independently verify detached expected SHA-256 values for bounded raw canonical D39 `verification-manifest.json` and verifier source-attestation bytes before parsing. Record both actual hashes in `ReadinessDecision.input_sha256`; bind verification candidate ID, D35 Git commit, and freeze hash to D36; and require `verification.verifier_tool_sha256 == verifier_tool_attestation.aggregate_sha256`. Reject any D38 or D39 detached-hash mismatch, non-canonical file, extra field, swapped artifact, importer/verifier-tool mismatch, or upstream-identity mismatch before evaluating quality.

Then use integer counts that represent 89.99/90 and 79.99/80 boundaries without floats. Independently reject an empty protocol case/category set, empty included set,
or any declared category with zero included tokens in either mode, even when synthetic
D38 evidence claims acceptance. For both modes, assert identical opaque protocol
category-token sets and the D38-validated complete included/excluded token partition
with only the shared schema's typed `both_not_approved`/single-missing-approval reasons, `completed == included` overall and per category, exact `task_complete / completed >= 90%` overall and `>= 80%` per category, zero unauthorized effects/replays/disclosures, explicit approval-attested exclusions only, complete non-vacuous accounting, D39
passed status, the exact nine command entries/zero exits, all smoke hash/content and
D36/materialization/verifier bindings, secret scan, clean/snapshot/runtime equality,
completed cleanup, and selected-default policy. Include one-mode-only threshold/category/completion failures, stateful ties, stateful better but unsafe, and All Tools better cases; every one-mode failure must block readiness.

- [ ] **Step 2: Write RED outcome tests**

Assert Ready only with every gate and no limitation approvals; Conditionally ready only with all gates plus one or more strict, candidate-bound `AcceptedNonSafetyLimitation` records. Reject free strings, unaccepted/pending approvals, safety classifications, mismatched candidate IDs, duplicate limitation IDs, malformed content hashes, or missing approval artifacts. For each review kind, test that only `status="completed"` plus an exact lowercase 64-hex artifact hash can pass. Missing/null, 63/65-character, uppercase, non-hex, and whitespace-padded completed hashes must produce a named review blocker rather than a parse crash or inferred pass. `pending` and `not_performed` with no artifact parse but block; either status with any artifact is rejected and blocks. `failed` always blocks, and any supplied artifact hash must still be syntactically valid. Not ready applies to any safety/integrity/regression/scoring/review failure. Missing D38 accepted result, D38 validation, D38 tool attestation, D39 verification manifest, D39 verifier source attestation, human operation, or independent review yields a valid Not ready record listing each absent mandatory input separately; an absent detached expected hash is a missing/invalid mandatory D38 or D39 input, never an inferred digest.

- [ ] **Step 3: Implement exact gate computation**

Import the immutable ordered `D39_REQUIRED_COMMANDS` contract from
`evaluation.release_verification` and independently compare every parsed
`CommandEvidence.name`/`argv` pair and exit code; do not accept
`VerificationManifest.status` as proof of inventory. After the D38 triplet and D39 manifest/attestation detached-hash and upstream cross-bind gates pass, independently require the exact nine ordered name/argv entries once each with every exit code zero; recompute the embedded canonical smoke-manifest hash; validate all six smoke hashes and every D36/materialization/runtime binding; require `verification.status == "passed"`, `secret_scan_passed is True`, clean before/after, identical candidate snapshots, `runtime_snapshot_after_sha256 == runtime_source_sha256`, and completed cleanup. Require `completed == included` for each mode and category. Then compare `task_complete * 100` to `completed * threshold` or use `Fraction`; never round percentages before gate comparison. Validate exclusions against the accepted aggregate's separate approval hashes/reasons before omitting them from `included`. Load each review independently: schema/validation errors become that review's named failed gate and blocker. A review gate passes only for matching kind/candidate, `status="completed"`, and exact lowercase 64-hex `artifact_sha256`; pending, not-performed, failed, absent, or malformed evidence cannot pass. Emit separate named D38 transfer/import/tool/upstream-identity gates, D39 transfer/verifier-tool/candidate-freeze/regression gates, plus all-tools and stateful completion, overall, per-category, safety, human-operation, and independent-review gates with evidence hashes.

- [ ] **Step 4: Run focused tests and lint**

```bash
cd backend
python -m uv run pytest tests/test_d40_readiness_decision.py -q
python -m uv run ruff check evaluation/release_decision.py tests/test_d40_readiness_decision.py
```

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/evaluation/release_decision.py backend/tests/test_d40_readiness_decision.py
git commit -m "feat: compute strict D40 readiness gates"
```

### Task 2: Side-effect-free CLI, canonical JSON, and Markdown

**Files:**
- Create: `backend/evaluation/scripts/attest_release_decision.py`
- Create: `backend/scripts/decide_release_readiness.py`
- Modify: `backend/tests/test_d40_readiness_decision.py`

**Interfaces:**

CLI (Git Bash):

```bash
python -m evaluation.scripts.attest_release_decision --repo-root . --output ../release-evidence/d40/decision-tool-attestation.json --expected-sha256 <DETACHED_D40_DECISION_TOOL_AGGREGATE_SHA256>
python -m scripts.decide_release_readiness --decision-tool-attestation ../release-evidence/d40/decision-tool-attestation.json --decision-tool-expected-sha256 <DETACHED_D40_DECISION_TOOL_AGGREGATE_SHA256> --freeze "$(find ../release-evidence/d36 -mindepth 2 -maxdepth 2 -name freeze-manifest.json -print -quit)" --aggregate ../release-evidence/d38/accepted-result.json --aggregate-expected-sha256 <DETACHED_ACCEPTED_RESULT_SHA256> --import-validation ../release-evidence/d38/validation.json --import-validation-expected-sha256 <DETACHED_VALIDATION_SHA256> --d38-tool-attestation ../release-evidence/d38/d38-tool-attestation.json --d38-tool-attestation-expected-sha256 <DETACHED_D38_TOOL_ATTESTATION_SHA256> --verification ../release-evidence/d39/verification-manifest.json --verification-expected-sha256 <DETACHED_D39_VERIFICATION_MANIFEST_SHA256> --verifier-tool-attestation ../release-evidence/d39/verifier-tool-attestation.json --verifier-tool-attestation-expected-sha256 <DETACHED_D39_VERIFIER_TOOL_ATTESTATION_SHA256> --human ../release-evidence/reviews/human-operation.json --independent ../release-evidence/reviews/independent-review.json --limitations ../release-evidence/reviews/non-safety-limitations.json --output ../release-evidence/d40
```

The source-attestation CLI covers exactly `evaluation/release_decision.py`,
`evaluation/result_contracts.py`, `evaluation/result_import.py`,
`evaluation/release_verification.py`, `evaluation/tool_attestation.py`,
`evaluation/scripts/attest_release_decision.py`, and
`scripts/decide_release_readiness.py`. It allows no caller path list, glob, omission,
extra, or duplicate; it computes the shared canonical aggregate and validates the
out-of-band expected aggregate before atomic output. The decision CLI rehashes the
same exact list and requires artifact/current/expected equality before loading
readiness evidence. There is no `--decision-tool-sha256` option.

After the decision source attestation has passed its pre-decision gate, readiness evidence arguments except `--freeze` may point to absent files; the CLI then emits Not ready and lists each missing mandatory input. Each D38 and D39 file requires its corresponding detached expected hash argument; a missing digest, malformed digest, or present file with a mismatched digest is a named blocker and must not be replaced by a hash read from any evidence file. Review files are strict canonical `ReviewEvidence`: malformed files, completed records without an exact lowercase 64-hex artifact hash, and pending/not-performed records carrying any artifact become named blockers while still permitting a valid Not ready output. `--limitations` absent means no accepted limitations. When present, it must contain only canonical `AcceptedNonSafetyLimitation` records whose approval artifact/content hashes and candidate ID validate; free-text limitation arrays are rejected.

- [ ] **Step 1: Write RED CLI/output tests**

Assert detached raw-byte validation and strict canonical parsing for all three D38 inputs and both D39 inputs; accepted-bundle/importer-tool/upstream-identity cross-binding; verification-manifest hash, verifier-tool hash, D35 commit/freeze/candidate cross-binding; independent exact-nine command/zero-exit inventory, all smoke hash/content and materialization bindings, secret/clean/snapshot/runtime/cleanup state; exact ReviewEvidence status/hash validation for both review kinds; accepted-limitation content/approval hash binding; exact-file D40 source-attestation generation, detached expected aggregate validation, runtime rehash, and derived-only `decision_tool_sha256`; atomic `decision.json`/`decision.md`; deterministic gate ordering; concise Markdown; and output refusal inside tracked source. Monkeypatch `subprocess`, sockets, Git commands, HTTP clients, and filesystem locations outside declared input/output roots as forbidden; decision generation must call none. Specifically prove the CLI cannot commit, push, tag, publish, create a release, or deploy.

- [ ] **Step 2: Implement canonical output**

Write canonical compact JSON for hashing and a Markdown rendering containing outcome, selected mode, separate D38 transfer/importer/upstream-identity gates, separate quality/safety gates for both modes, blockers, accepted limitation IDs/content hashes/approval hashes, the exact accepted-result/validation/D38-tool-attestation/verification-manifest/verifier-tool-attestation input hashes, other input hashes, and validated decision attestation aggregate/tool hash. Do not include free text from held-out cases, model responses, limitation prose, private paths, or detailed evidence.

- [ ] **Step 3: Add missing-input and no-side-effect regression tests**

First generate and validate the decision source attestation. Then run the decision CLI with only that attestation and D36 freeze and assert exit code 2 plus a valid Not ready JSON/Markdown separately naming missing D38 accepted result, D38 validation, D38 tool attestation, D39 verification manifest, D39 verifier source attestation, human operation, and independent review. A missing/mismatched decision source attestation instead refuses to create either decision output because the decision code itself is unattested. Run a fully passing synthetic set and assert exit code 0. A Conditionally ready synthetic set exits 0 only when both modes and all other mandatory gates pass and every limitation has a content-bound accepted non-safety approval.

- [ ] **Step 4: Run focused tests**

```bash
cd backend
python -m uv run pytest tests/test_d40_readiness_decision.py tests/test_d39_release_verification.py tests/test_d38_result_import.py -q
python -m uv run ruff check evaluation/release_decision.py evaluation/scripts/attest_release_decision.py scripts/decide_release_readiness.py tests/test_d40_readiness_decision.py
```

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/evaluation/scripts/attest_release_decision.py backend/scripts/decide_release_readiness.py backend/tests/test_d40_readiness_decision.py
git commit -m "feat: emit side-effect-free readiness decision"
```

### Task 3: Missing-evidence baseline, final evidence run, and D40 gate

**Files:**
- Create: `docs/plan-c/work-report-40.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `specification.md` and `docs/DTD.md` only to reconcile final tooling behavior; never mutate the D35 candidate checkout
- Generated outside Git: `release-evidence/d40/decision.json`
- Generated outside Git: `release-evidence/d40/decision.md`

**Interfaces:**
- The actual decision uses only content-bound files present at execution. Pending, not-performed, absent, or malformed review evidence is reported as Not ready. No operator may attach an artifact to pending/not-performed status or synthesize/normalize a completed artifact hash.

- [ ] **Step 1: Run full tooling verification**

```bash
cd backend && python -m uv run pytest tests/test_d40_readiness_decision.py tests/test_d39_release_verification.py tests/test_d38_result_import.py tests/test_d37_blinded_runner.py -q
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

- [ ] **Step 2: Prove mandatory missing inputs emit Not ready**

```bash
rm -rf release-evidence/d40-missing
cd backend
python -m uv run python -m evaluation.scripts.attest_release_decision --repo-root . --output ../release-evidence/d40-missing/decision-tool-attestation.json --expected-sha256 <DETACHED_D40_DECISION_TOOL_AGGREGATE_SHA256>
python -m uv run python -m scripts.decide_release_readiness --decision-tool-attestation ../release-evidence/d40-missing/decision-tool-attestation.json --decision-tool-expected-sha256 <DETACHED_D40_DECISION_TOOL_AGGREGATE_SHA256> --freeze "$(find ../release-evidence/d36 -mindepth 2 -maxdepth 2 -name freeze-manifest.json -print -quit)" --aggregate ../release-evidence/missing/accepted-result.json --aggregate-expected-sha256 <DETACHED_ACCEPTED_RESULT_SHA256> --import-validation ../release-evidence/missing/validation.json --import-validation-expected-sha256 <DETACHED_VALIDATION_SHA256> --d38-tool-attestation ../release-evidence/missing/d38-tool-attestation.json --d38-tool-attestation-expected-sha256 <DETACHED_D38_TOOL_ATTESTATION_SHA256> --verification ../release-evidence/missing/verification-manifest.json --verification-expected-sha256 <DETACHED_D39_VERIFICATION_MANIFEST_SHA256> --verifier-tool-attestation ../release-evidence/missing/verifier-tool-attestation.json --verifier-tool-attestation-expected-sha256 <DETACHED_D39_VERIFIER_TOOL_ATTESTATION_SHA256> --human ../release-evidence/missing/human-operation.json --independent ../release-evidence/missing/independent-review.json --limitations ../release-evidence/missing/non-safety-limitations.json --output ../release-evidence/d40-missing
```

Expected: exit code 2 and valid Not ready output naming all seven missing mandatory evidence groups. The six placeholder digests represent separately supplied detached values; tests also cover omitted/malformed digest arguments as distinct blockers. On PowerShell, run the command without `rm -rf` after removing the ignored directory through `Remove-Item -Recurse -Force release-evidence/d40-missing`.

- [ ] **Step 3: Run the actual decision without external side effects**

The D40 source aggregate, three D38 digests, and two D39 digest variables below must be supplied through the approved detached channel; do not compute them from the files being decided or read them from sibling evidence.

```bash
cd backend
python -m uv run python -m evaluation.scripts.attest_release_decision --repo-root . --output ../release-evidence/d40/decision-tool-attestation.json --expected-sha256 "$D40_DECISION_TOOL_AGGREGATE_SHA256"
python -m uv run python -m scripts.decide_release_readiness --decision-tool-attestation ../release-evidence/d40/decision-tool-attestation.json --decision-tool-expected-sha256 "$D40_DECISION_TOOL_AGGREGATE_SHA256" --freeze "$(find ../release-evidence/d36 -mindepth 2 -maxdepth 2 -name freeze-manifest.json -print -quit)" --aggregate ../release-evidence/d38/accepted-result.json --aggregate-expected-sha256 "$D38_ACCEPTED_RESULT_SHA256" --import-validation ../release-evidence/d38/validation.json --import-validation-expected-sha256 "$D38_VALIDATION_SHA256" --d38-tool-attestation ../release-evidence/d38/d38-tool-attestation.json --d38-tool-attestation-expected-sha256 "$D38_TOOL_ATTESTATION_SHA256" --verification ../release-evidence/d39/verification-manifest.json --verification-expected-sha256 "$D39_VERIFICATION_MANIFEST_SHA256" --verifier-tool-attestation ../release-evidence/d39/verifier-tool-attestation.json --verifier-tool-attestation-expected-sha256 "$D39_VERIFIER_TOOL_ATTESTATION_SHA256" --human ../release-evidence/reviews/human-operation.json --independent ../release-evidence/reviews/independent-review.json --limitations ../release-evidence/reviews/non-safety-limitations.json --output ../release-evidence/d40
```

If any mandatory file is absent, preserve the emitted Not ready result. Do not create synthetic completion evidence to change it.

- [ ] **Step 4: Inspect and write the final work report**

```bash
git status --short
git diff --check
git ls-files .env storage release-evidence
```

Record candidate ID, the generated/validated D40 decision attestation aggregate and
artifact hash, D37-D40 tool hashes, detached and observed hashes for each D38 accepted/validation/tool-attestation input and both D39 verification/verifier-attestation inputs, every cross-binding gate, every quality/safety gate for both modes, selected mode, blockers, accepted limitation identifiers/hashes, and actual outcome. Distinguish automated evidence from human operation and independent review.

- [ ] **Step 5: Commit and push tooling/documentation only**

```bash
git add backend docs/plan-c/work-report-40.md docs/plan-c/handoff.md specification.md docs/DTD.md
git commit -m "[DONE] Mission 40 Emit evidence-based readiness decision"
git push
```

This repository delivery commit/push is permitted as workflow delivery but is not a release approval and is not performed by the decision CLI. Do not tag, publish, deploy, create a GitHub release, or modify the D35 candidate checkout regardless of outcome.
