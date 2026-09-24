# D38 Independent Evaluation Result Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate and import only a non-sensitive aggregate from the independent evaluator, bound to the exact D35 candidate named by the D36 freeze manifest and to D37 protocol/tool evidence, without opening detailed held-out evidence.

**Architecture:** Strict result models validate canonical counts and identities; an out-of-band SHA-256 authenticates transfer integrity. The importer runs as later external tooling, records its own source attestation separately from candidate behavior, and atomically stores a canonical accepted bundle plus validation record.

**Tech Stack:** Python 3.12, Pydantic 2, canonical JSON/SHA-256, pytest.

## Global Constraints

- Follow `docs/plan-c/work-unit-38.md`, the D37 Task 1 shared D37-D40 result schema in `docs/DTD.md`, and the clarified D36-D40 external-tool boundary.
- Import D37's shared result models unchanged; do not redeclare, subclass, normalize, or fork the DTD schema.
- Consume the exact immutable run-specific D37 `<run-output>/protocol.json`; its raw canonical bytes must hash to `EvaluationResultBundle.protocol_sha256`. Never use D36 `final_protocol.json` as the result protocol.
- Never open, enumerate, or reconstruct sealed detailed evidence; consume its SHA-256 string only.
- `--expected-sha256` is supplied out-of-band, not read from the bundle or a sibling bundle file.
- Missing/failed trials remain failures; no skip conversion or selective filtering.
- Protocol/bundle case and category identities are lowercase 64-hex opaque tokens only;
  raw IDs, text, category names, and labels are forbidden.
- Candidate identity comes only from D36. D37 and D38 tool source hashes are separate evidence and are not candidate behavior.
- Tests use synthetic bundles only.
- Final delivery commit is `[DONE] Mission 38 Validate independent aggregate import`.

---

### Task 1: Import the D37 aggregate contract and enforce accounting invariants

**Files:**
- Modify only if D37 implementation is inconsistent: `backend/evaluation/result_contracts.py`
- Create: `backend/tests/test_d38_result_import.py`
- Create: `backend/tests/fixtures/blinded/synthetic-result-bundle.json`

**Interfaces:**

D38 imports `CategoryResult`, `ModeResult`, `ExcludedCaseToken`, and `EvaluationResultBundle` from D37's `evaluation.result_contracts`. It must not redeclare, subclass, copy, normalize, or version-skew the D37 Task 1 DTD schema. The imported schema has separate `human_approval_sha256` and `independent_approval_sha256` fields plus exact corpus, run-specific protocol, freeze, D36 candidate trial-tool, and D37 runner/evaluator-tool hashes; a non-empty complete sorted protocol case/category token set/count; a non-empty exact
sorted included set with at least one included token per declared category/mode; exact sorted
excluded tokens with deterministic `both_not_approved` or sole-missing-approval reasons; unauthorized effects/replays/
disclosures overall and by opaque category; evaluator identity/time; and the same canonical category set for both modes. All imported models are strict and use `extra="forbid"`.

- [ ] **Step 1: Write RED valid/invalid bundle tests**

Assert one result for each exact mode, identical mode included counts and exact opaque
category-token sets/order, category included/completed/task/safety sums, nonnegative
bounded integers, `task_complete <= completed <= included`, `completed +
transport_failures + deadline_failures == included`, and zero omitted trials. Require non-empty protocol case/category sets, a non-empty
included set, and at least one included token in every declared category/mode. Assert
protocol case tokens and bundle included tokens are unique and sorted; excluded entries
are unique and sorted by token; included/excluded sets are disjoint; their exact union
equals the protocol set; and lengths equal protocol/included/excluded counts. Derive
included/excluded totals and reason-by-category totals from protocol bindings and
require exact agreement with every mode/category count. Permit only the three typed approval reasons. D37 owns deterministic selection from
the private ledgers; D38 validates the strict reason value and accounting without
reconstructing private approval decisions. Reject duplicate, unsorted,
overlapping, missing, or extra tokens; bad token syntax; duplicate categories/modes;
empty evaluator name; altered candidate/corpus/approval/freeze/protocol/tool identities;
and any raw ID/text/category-name/label/path field.

- [ ] **Step 2: Run RED tests**

```bash
cd backend
python -m uv run pytest tests/test_d38_result_import.py -k contracts -q
```

Expected: FAIL because result contracts do not exist.

- [ ] **Step 3: Verify and, only if needed, correct the D37 validators**

Import the D37 models directly. Normalize no category token and infer no missing row. Category tokens must be exact non-empty lowercase 64-hex identities from the D37 protocol; duplicate/missing tokens and zero included category coverage fail closed. Any necessary schema correction belongs to D37's shared `result_contracts.py` and requires rerunning D37 tests/evidence, not a D38-local model.

- [ ] **Step 4: Run contract tests and lint**

```bash
cd backend
python -m uv run pytest tests/test_d38_result_import.py -k contracts -q
python -m uv run ruff check evaluation/result_contracts.py tests/test_d38_result_import.py
```

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/evaluation/result_contracts.py backend/tests/test_d38_result_import.py backend/tests/fixtures/blinded/synthetic-result-bundle.json
git commit -m "test: validate the shared D37 result bundle"
```

### Task 2: Detached-hash importer and tool attestation

**Files:**
- Create: `backend/evaluation/result_import.py`
- Create: `backend/scripts/import_evaluation_result.py`
- Modify: `backend/tests/test_d38_result_import.py`

**Interfaces:**

```python
class ImportValidation(BaseModel):
    schema_version: Literal[1]
    status: Literal["accepted"]
    candidate_id: str
    source_bundle_sha256: str
    accepted_bundle_sha256: str
    corpus_sha256: str
    human_approval_sha256: str
    independent_approval_sha256: str
    protocol_sha256: str
    freeze_sha256: str
    d36_trial_tool_sha256: str
    d37_evaluator_tool_sha256: str
    d38_import_tool_sha256: str
    checks: dict[str, Literal[True]]

import_evaluation_result(
    *, bundle_path: Path, expected_sha256: str, freeze_manifest_path: Path,
    protocol_path: Path, d36_trial_tool_attestation_path: Path,
    d37_tool_attestation_path: Path, output_dir: Path, repo_root: Path,
) -> ImportValidation
```

CLI:

```text
python -m scripts.import_evaluation_result --bundle D:/blockvideo-evaluator/results/result-bundle.json --expected-sha256 8f4d2c6c7b75b9f4f57432db19f92f657340f25da6ebf5f564531f7865b0b46e --freeze-manifest D:/blockvideo-evaluator/freeze-manifest.json --protocol D:/blockvideo-evaluator/results/protocol.json --d36-trial-tool-attestation D:/blockvideo-evaluator/d36-tool-attestation.json --d37-tool-attestation D:/blockvideo-evaluator/results/tool-attestation.json --output ../../blockvideo-upgrade-project/release-evidence/d38
```

`ImportValidation.checks` must contain exactly the DTD-defined 19 check names, all
`true`, with no omitted or extra key.

The hexadecimal value above is a synthetic command example used only with the fixture whose test computes/patches the matching value; real execution uses the independently communicated 64-hex digest.

- [ ] **Step 1: Write RED import tests**

Assert raw bundle bytes match detached SHA-256 before JSON parsing and parse only through D37's exported `EvaluationResultBundle`. Read the supplied D37 `protocol.json` as bounded raw bytes, require canonical decoding through `EvaluationProtocol`, and assert its exact byte SHA-256 equals `bundle.protocol_sha256`. Cross-bind its candidate, corpus, separate human/independent approval, freeze, D36 candidate trial-tool, D37 runner/evaluator-tool, model-configuration, stateful-index, opaque category-token/binding and complete case-token identities to the bundle,
attestations, exact token partition, and imported accounting. Reject D36 `final_protocol.json`, regenerated equivalent policy bytes that omit run identities, a copied/mutated protocol, non-canonical bytes, symlinks, and a protocol outside the evaluator run output. Assert canonical bundle hash stability and exact candidate, corpus, separate human/independent approval, freeze, D36 trial-tool, and D37 evaluator-tool hash matches. Assert evaluator role/name/time and shared-schema exclusions/category/safety fields are present, the output directory is ignored/untracked and new, and the importer never opens the sealed evidence path even if one exists nearby.

- [ ] **Step 2: Add tamper and accounting rejection tests**

Alter one byte, each identity hash independently, evaluator identity/time, one
exclusion reason, declared count, mode, opaque category set/binding, unauthorized
effect/replay/disclosure count, candidate, D37 run protocol, or tool attestation.
Separately test a duplicate token, unsorted token list, included/excluded overlap,
missing protocol token, extra unknown token, wrong per-category partition, zero included overall/category coverage, an unknown
exclusion reason, omitted trial, and injected raw ID/text/label field. Every case must fail before writing accepted output and return only a fixed error class/reason without bundle content/path.

- [ ] **Step 3: Implement atomic accepted evidence**

Write `accepted-result.json`, `validation.json`, and `d38-tool-attestation.json` through temporary files plus `os.replace()`. `accepted-result.json` is the canonical shared-schema bundle; `validation.json.accepted_bundle_sha256` hashes its exact bytes and records every upstream identity and the exact DTD-defined check-key set covering token
syntax/uniqueness/sorting/disjointness/exact-union/count/non-empty-coverage/typed-
reason/category and hash checks; `validation.json.d38_import_tool_sha256` equals the canonical `d38-tool-attestation.json.aggregate_sha256`. Attest `result_import.py`, `tool_attestation.py`, and `import_evaluation_result.py`; include the shared D37 `result_contracts.py` hash in dependency evidence without redefining it. Retain D36 trial, D37 evaluator, and D38 importer tool hashes as separate fields so D40 can cross-bind all three artifacts.

- [ ] **Step 4: Run import tests**

```bash
cd backend
python -m uv run pytest tests/test_d38_result_import.py -q
python -m uv run ruff check evaluation/result_contracts.py evaluation/result_import.py evaluation/tool_attestation.py scripts/import_evaluation_result.py tests/test_d38_result_import.py
```

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/evaluation/result_import.py backend/scripts/import_evaluation_result.py backend/tests/test_d38_result_import.py
git commit -m "feat: import detached-hash evaluation aggregate"
```

### Task 3: Synthetic import evidence and D38 gate

**Files:**
- Create: `docs/plan-c/work-report-38.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `docs/DTD.md` only if implementation evidence invalidates the external-tool contract

**Interfaces:**
- The implementation report records synthetic tests and tooling hashes only. Real aggregate acceptance is a separate evaluator handoff and may be pending.

- [ ] **Step 1: Run focused and full verification**

```bash
cd backend && python -m uv run pytest tests/test_d38_result_import.py tests/test_d37_blinded_runner.py -q
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

- [ ] **Step 2: Run the synthetic detached-hash import test**

```bash
cd backend
python -m uv run pytest tests/test_d38_result_import.py::test_imports_canonical_synthetic_bundle_with_detached_hash -q
```

The test computes the detached hash from the synthetic fixture, constructs matching temporary D36/protocol/D37 attestations with opaque token
partitions, imports into a temporary ignored output, asserts every selective-filtering
check, and asserts no detailed-evidence file is opened.

- [ ] **Step 3: Inspect, report, and deliver tooling**

```bash
git status --short
git diff --check
git ls-files .env storage release-evidence
```

Record whether the real aggregate is absent/pending without treating that as a pass.

- [ ] **Step 4: Commit and push the implementation task**

```bash
git add backend docs/plan-c/work-report-38.md docs/plan-c/handoff.md docs/DTD.md
git commit -m "[DONE] Mission 38 Validate independent aggregate import"
git push
```

Do not inspect detailed evidence, decide readiness, tag, publish, or deploy.
