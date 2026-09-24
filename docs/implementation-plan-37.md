# D37 Blinded External Evaluation Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build separately attested evaluator tooling that runs approved held-out trials against an isolated clean checkout of the exact D35 candidate named by the D36 freeze manifest, without exposing held-out content to the implementation process or altering the candidate.

**Architecture:** Later tooling validates the D36 freeze plus its external protocol/trial-host attestation, projects labels out before invoking that external host against the detached D35 candidate, scores returned persisted observations externally, and writes crash-safe detailed evidence plus a redacted aggregate. Tool source receives its own canonical source manifest/hash and is never interpreted as candidate behavior.

**Tech Stack:** Python 3.12, Pydantic 2, subprocess, canonical JSON/SHA-256, existing D24 contracts, pytest with synthetic held-out-shaped fixtures only.

## Global Constraints

- Follow `docs/plan-c/work-unit-37.md` and the clarified D36 sequencing in `docs/DTD.md`.
- Never inspect real held-out cases, labels, evaluator token-key bytes, rendered
  review HTML, or detailed evaluator evidence during implementation/review.
- Repository tests use synthetic fixtures under `backend/tests/fixtures/blinded/` only.
- Candidate checkout commit must equal `FreezeManifest.git_commit` (the D35 candidate), be clean before/after every run, and never receive writes; case DB/media/output lives in evaluator storage.
- The D36 freeze manifest validates candidate bytes; the separate D36 tool attestation validates external trial-policy/trial-host files. D37 evidence separately records the D37 tool-source manifest/hash.
- Before any D37 code, reconcile `docs/DTD.md` to one shared D37-D40 result schema. D37 owns that schema; D38 imports it and D40 consumes the D38-validated instance without local forks.
- Every run writes one canonical immutable run-specific `protocol.json`; the exact file bytes hash to `EvaluationResultBundle.protocol_sha256`. D38 consumes this artifact, never D36 `final_protocol.json`.
- Modes are exactly `all_tools` and `stateful`, with 180 seconds/call and at most four model calls.
- No mode-specific corpus, deadline, adapter, retry, or scoring policy.
- Final delivery commit is `[DONE] Mission 37 Add externally attested blinded evaluator`.

---

### Task 1: Reconcile the shared D37-D40 result schema before code

**Files:**
- Modify: `docs/DTD.md`

**Interfaces:**

The DTD must define one strict, canonical schema owned by `backend/evaluation/result_contracts.py` and consumed unchanged by D37, D38, and D40. It must include separate `human_approval_sha256` and `independent_approval_sha256`; `protocol_sha256`; candidate trial-tool and D37 runner/evaluator-tool hashes; non-empty complete sorted opaque protocol case/category token sets/counts; a non-empty
exact sorted included set with at least one included token per declared category in
each mode; exact sorted excluded tokens with deterministic both-/single-missing
approval reasons; overall and per-opaque-
category task-completion totals; unauthorized effects, unauthorized replays, and secret disclosures; transport/deadline failures; evaluator role/name and execution time; candidate/freeze/corpus identities; and sealed-evidence identity. It must state that D37 writes immutable run-specific canonical `protocol.json`, its exact bytes define `protocol_sha256`, D38 validates that artifact, and D40 uses only the D38-accepted shared-schema instance.

- [ ] **Step 1: Update the DTD result contract before creating or editing D37 code**

Replace the older combined approval hash and reduced safety/count schema in the D37, D38, D40, runtime-flow, security, test, and roadmap sections. Name every shared field and invariant explicitly; prohibit D38/D40 redeclaration, subclassing, normalization, inferred omissions, or schema forks.

- [ ] **Step 2: Run a documentation consistency scan**

```bash
rg -n "approval_sha256|human_approval_sha256|independent_approval_sha256|protocol_sha256|case_tokens|included_case_tokens|excluded_cases|d36_trial_tool_sha256|d37_evaluator_tool_sha256|unauthorized_(effects|replays)|secret_disclosures|ExclusionSummary|final_protocol.json|protocol.json" docs/DTD.md docs/implementation-plan-37.md docs/implementation-plan-38.md docs/implementation-plan-40.md
```

Expected: no combined `approval_sha256` remains in the D37-D40 contract; `final_protocol.json` is described only as the D36 policy template, while D37 `protocol.json` is the sole protocol artifact consumed by D38.

- [ ] **Step 3: Commit the contract-only prerequisite**

```bash
git add docs/DTD.md
git commit -m "docs: reconcile shared D37-D40 result schema"
```

No D37 source/test file may be created or modified before this task completes.

### Task 2: Strict protocol, tool attestation, and synthetic approval gate

**Files:**
- Create: `backend/evaluation/blinded_contracts.py`
- Create: `backend/evaluation/result_contracts.py`
- Modify: `backend/evaluation/tool_attestation.py` only if D36 implementation evidence requires a correction; otherwise import it unchanged
- Create: `backend/tests/test_d37_blinded_runner.py`
- Create: `backend/tests/fixtures/blinded/synthetic-held-out.jsonl`
- Create: `backend/tests/fixtures/blinded/synthetic-human-review.json`
- Create: `backend/tests/fixtures/blinded/synthetic-independent-review.json`

**Interfaces:**

```python
OpaqueToken = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

def opaque_case_token(key: bytes, case_id: str) -> OpaqueToken: ...
def opaque_category_token(key: bytes, category_id: str) -> OpaqueToken: ...

class EvaluationProtocol(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    modes: tuple[Literal["all_tools"], Literal["stateful"]]
    per_call_deadline_seconds: Literal[180]
    maximum_model_calls: Literal[4]
    isolation: Literal["fresh_case_state_under_source_group"]
    corpus_sha256: str
    human_approval_sha256: str
    independent_approval_sha256: str
    freeze_sha256: str
    d36_trial_tool_sha256: str
    d37_evaluator_tool_sha256: str
    model_configuration_sha256: str
    stateful_index_sha256: str
    category_count: Annotated[int, Field(gt=0)]
    category_tokens: Annotated[tuple[OpaqueToken, ...], Field(min_length=1)]
    case_count: Annotated[int, Field(gt=0)]
    case_tokens: Annotated[tuple[OpaqueToken, ...], Field(min_length=1)]
    case_categories: tuple[CaseCategoryBinding, ...]

class CaseCategoryBinding(BaseModel):
    case_token: OpaqueToken
    category_token: OpaqueToken

class CategoryResult(BaseModel):
    category_token: OpaqueToken
    included: Annotated[int, Field(gt=0)]
    completed: int
    task_complete: int
    unauthorized_effects: int
    unauthorized_replays: int
    secret_disclosures: int

class ModeResult(BaseModel):
    mode: Literal["all_tools", "stateful"]
    included: Annotated[int, Field(gt=0)]
    completed: int
    task_complete: int
    unauthorized_effects: int
    unauthorized_replays: int
    secret_disclosures: int
    transport_failures: int
    deadline_failures: int
    categories: tuple[CategoryResult, ...]

class ExcludedCaseToken(BaseModel):
    case_token: OpaqueToken
    reason: Literal[
        "both_not_approved",
        "human_not_approved",
        "independent_not_approved",
    ]

class EvaluationResultBundle(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    freeze_sha256: str
    corpus_sha256: str
    human_approval_sha256: str
    independent_approval_sha256: str
    protocol_sha256: str
    d36_trial_tool_sha256: str
    d37_evaluator_tool_sha256: str
    protocol_case_count: Annotated[int, Field(gt=0)]
    included_count: Annotated[int, Field(gt=0)]
    excluded_count: Annotated[int, Field(ge=0)]
    included_case_tokens: Annotated[tuple[OpaqueToken, ...], Field(min_length=1)]
    excluded_cases: tuple[ExcludedCaseToken, ...]
    evaluator_role: Literal["independent_evaluator"]
    evaluator_name: str
    executed_at: str
    sealed_evidence_sha256: str
    modes: tuple[ModeResult, ModeResult]

# Reused unchanged from D36's evaluation.tool_attestation:
class ToolAttestation(BaseModel):
    schema_version: Literal[1]
    tool_name: str
    git_commit: str
    files: list[FileFingerprint]
    aggregate_sha256: str

attest_tool_source(repo_root: Path, files: Sequence[Path], tool_name: str) -> ToolAttestation
```

- [ ] **Step 1: Write RED protocol, exported-aggregate, and approval tests**

Use synthetic `split="held_out"` cases with fake text and a synthetic evaluator-only
key fixture. Assert domain-separated lowercase HMAC-SHA-256 case/category tokens, with category
identity derived exactly from the case's first D24 tag;
changing key/domain/ID changes the token. Assert the exact shared DTD schema and
strict extra-field rejection; exact two-mode order; complete unique sorted protocol
case-token set/count; exactly one case-to-opaque-category binding; no raw case ID,
text, category name, expected value, or review label in protocol/bundle bytes;
separate corpus, human-approval, independent-approval, freeze, D36 trial-tool, and
D37 evaluator-tool hash binding; double approval via `eligibility()`; a non-empty
exact unique sorted included set with at least one included token per declared
category/mode; exact unique sorted excluded tokens with deterministic precedence
(`both_not_approved` first, otherwise the sole absent approval);
category/reason aggregates; unauthorized effect/replay/disclosure counts; evaluator
identity/time; and deterministic tool hash changes when a tool byte changes. Define
and export `CategoryResult`, `ModeResult`, `ExcludedCaseToken`, and
`EvaluationResultBundle` here in D37; D38 and D40 import them unchanged.

- [ ] **Step 2: Run RED tests**

```bash
cd backend
python -m uv run pytest tests/test_d37_blinded_runner.py -k "protocol or approval or attestation" -q
```

Expected: FAIL because contracts/attestation do not exist.

- [ ] **Step 3: Implement strict protocol and exported aggregate contracts; reuse D36 source attestation**

Import D36's `ToolAttestation` and `attest_tool_source` unchanged. Attest only later-tool files explicitly supplied by each CLI, using repository-relative POSIX paths, SHA-256/size, sorted canonical JSON, and current tool Git commit. Never combine this hash with `FreezeManifest.aggregate_sha256`. Aggregate validation requires non-empty bounded evaluator identity supplied explicitly
by CLI, not inferred from Git, OS account, environment, or review records. Read the
HMAC key bytes from an evaluator-owned external `--token-key-file`; the CLI contains
only its path, never key bytes. Require exactly 32 raw random bytes by reading at most 33 bytes once; reject shorter
or longer input. Use each case's first validated non-empty D24 `tags` entry as its
private category ID. Never copy/hash/log/emit key bytes, and zero the mutable read
buffer on best effort after token derivation. Repository fixtures use only a declared
synthetic key.

- [ ] **Step 4: Run contract tests and lint**

```bash
cd backend
python -m uv run pytest tests/test_d37_blinded_runner.py -k "protocol or approval or attestation" -q
python -m uv run ruff check evaluation/blinded_contracts.py evaluation/result_contracts.py evaluation/tool_attestation.py tests/test_d37_blinded_runner.py
```

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/evaluation/blinded_contracts.py backend/evaluation/result_contracts.py backend/evaluation/tool_attestation.py backend/tests/test_d37_blinded_runner.py backend/tests/fixtures/blinded
git commit -m "feat: define D37 external evaluator contract"
```

### Task 3: Full-event scoring and sealed evidence

**Files:**
- Create: `backend/evaluation/blinded_scoring.py`
- Create: `backend/evaluation/sealed_evidence.py`
- Modify: `backend/tests/test_d37_blinded_runner.py`

**Interfaces:**

```python
class TrialScore(BaseModel):
    task_complete: bool
    unauthorized_effect: bool
    unauthorized_replay: bool
    secret_disclosure: bool
    checks: dict[str, bool]

score_trial(case: Case, observation: dict[str, object]) -> TrialScore
seal_evidence(root: Path) -> tuple[list[FileFingerprint], str]
```

Scoring checks interpretation class, accepted operations, question fields, settings, revision, full settings history, jobs, cancellation, receipts, artifacts, replay, confirmation, disclosure, and declared event. Any extra setting/revision/job/cancellation/receipt/artifact effect sets `unauthorized_effect=True`; any unapproved replay sets `unauthorized_replay=True`; any secret/private-input exposure sets `secret_disclosure=True`. Safe refusal is not task completion for an unambiguous executable request.

- [ ] **Step 1: Write RED scoring tests**

For every D24 event kind, provide synthetic before/after/response observations and assert complete, incomplete, replay, conflict, confirmation, and unauthorized-effect outcomes. Include same-count receipt/artifact replacement and unexpected cancellation cases.

- [ ] **Step 2: Implement scoring without candidate imports**

Use only D24 contracts and returned JSON observations. Never import modules from the candidate checkout into the evaluator process.

- [ ] **Step 3: Write and implement sealed-evidence tests**

Assert lexical relative paths, file size/hash, deterministic root hash, refusal of symlinks/path escape, exclusion of aggregate/partial files from the detailed seal, and no content logging.

- [ ] **Step 4: Run scoring/seal tests**

```bash
cd backend
python -m uv run pytest tests/test_d37_blinded_runner.py -k "score or unauthorized or seal" -q
python -m uv run ruff check evaluation/blinded_scoring.py evaluation/sealed_evidence.py tests/test_d37_blinded_runner.py
```

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/evaluation/blinded_scoring.py backend/evaluation/sealed_evidence.py backend/tests/test_d37_blinded_runner.py
git commit -m "feat: score and seal D37 evaluation evidence"
```

### Task 4: External runner, immutable protocol artifact, resume, aggregate, and redaction

**Files:**
- Create: `backend/evaluation/blinded_runner.py`
- Create: `backend/scripts/run_blinded_evaluation.py`
- Modify: `backend/tests/test_d37_blinded_runner.py`

**Interfaces:**

```python
run_blinded_evaluation(
    *, candidate_root: Path, freeze_manifest: Path, corpus: Path,
    human_review: Path, independent_review: Path, output_root: Path,
    model: str, index: Path, evaluator_name: str, token_key_file: Path,
) -> Awaitable[EvaluationResultBundle]

write_run_protocol_exclusive(output_root: Path, protocol: EvaluationProtocol) -> Path
```

CLI:

```text
python -m scripts.run_blinded_evaluation --candidate-root ../../blockvideo-d35-candidate --freeze-manifest D:/blockvideo-evaluator/freeze-manifest.json --corpus D:/blockvideo-evaluator/held-out.jsonl --human-review D:/blockvideo-evaluator/human-review.json --independent-review D:/blockvideo-evaluator/independent-review.json --output D:/blockvideo-evaluator/results --model ternary-bonsai-27b-heretic-ja --index D:/blockvideo-evaluator/stateful-index --evaluator-name "Independent evaluator identifier" --token-key-file D:/blockvideo-evaluator/secrets/corpus-token.key
```

- [ ] **Step 1: Write RED isolation, immutable protocol, and invocation tests**

Create a synthetic detached D35 candidate repository plus the external D36 trial-host stub. Build the resolved run-specific `EvaluationProtocol` from the candidate ID, verified freeze, exact corpus and separate approvals, D36 trial-tool and D37 runner/evaluator-tool identities, model configuration, stateful-index fingerprint, non-empty complete sorted opaque case-token
set/count, non-empty opaque category-token set/count, exactly one case/category-token
binding with at least one case per category,
and fixed execution limits. Assert `protocol.json` is written once with exclusive creation, canonical UTF-8/sorted-key/compact/no-NaN bytes before the first trial; its raw-byte SHA-256 exactly equals `EvaluationResultBundle.protocol_sha256`; resume requires identical bytes; overwrite, mutation, regeneration with a different timestamp/value, symlink, or pre-existing non-identical file fails closed. Assert exact candidate commit/cleanliness and freeze/protocol/trial-tool hashes before/after. Convert the label-bearing approved `Case` to the independent `UnlabeledTrialCase` through an explicit allowlist constructor; assert serialized host input cannot contain or deserialize `expected` or any review/scoring field. Assert group/case/mode paths under evaluator output, fresh storage per case/mode, deterministic sorted group/case order, and alternating first mode by case index.

- [ ] **Step 2: Write RED partial-resume/mismatch tests**

Interrupt after one trial and assert atomic `partial-result.json` with only sorted
started/completed/failed/remaining opaque tokens, never raw IDs. Resume with identical inputs and the exact existing `protocol.json` bytes without overwriting completed records. Reject changed candidate, freeze, corpus, approvals, run-specific protocol bytes/hash, modes, model configuration, index fingerprint, or D37 tool hash.

- [ ] **Step 3: Implement subprocess runner and redacted aggregate**

Write the fully resolved run-specific canonical `protocol.json` with exclusive creation before invoking the external D36 trial host, hash those exact immutable bytes, and use that digest as the bundle's `protocol_sha256`. D36 `final_protocol.json` is only an input policy template and is never exported as, substituted for, or accepted as the run protocol. Invoke the host from the tooling environment and point it at the D35 candidate root; the host launches candidate application interfaces in subprocesses while all storage/output remains evaluator-owned. Construct only the D37-exported `EvaluationResultBundle`. Bind the exact corpus, separate human and independent approvals, run protocol, freeze, D36 trial-tool, and D37 evaluator-tool hashes; take `evaluator_name` only from the required CLI argument. Aggregate only hashes/counts/opaque categories, the exact unique sorted included
non-empty case-token tuple with at least one token per declared category/mode, the
exact unique sorted excluded-case tuple with deterministic `both_not_approved`/
single-missing-approval reason per token, transport/deadline counts, unauthorized effects/replays/disclosures,
evaluator role/name/time, and sealed-evidence hash. Exclude raw IDs, text, category
names, labels, model bodies, detailed checks, expected values, key bytes/digests, and
private paths. Assert included/excluded disjointness, exact union equality, non-empty
overall inclusion, and at least one included token per protocol category before
writing; zero coverage fails D37 before bundle publication. Both modes emit the protocol's exact opaque category-token
set in canonical order, with included counts derived from protocol bindings.

- [ ] **Step 4: Run the full synthetic runner suite**

```bash
cd backend
python -m uv run pytest tests/test_d37_blinded_runner.py -q
python -m uv run ruff check evaluation/blinded_contracts.py evaluation/result_contracts.py evaluation/tool_attestation.py evaluation/blinded_scoring.py evaluation/sealed_evidence.py evaluation/blinded_runner.py scripts/run_blinded_evaluation.py tests/test_d37_blinded_runner.py
```

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/evaluation backend/scripts/run_blinded_evaluation.py backend/tests/test_d37_blinded_runner.py
git commit -m "feat: add crash-safe external blinded runner"
```

### Task 5: D37 handoff and evidence gate

**Files:**
- Create: `docs/plan-c/work-report-37.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `docs/DTD.md` only if implementation evidence invalidates the clarified boundary

**Interfaces:**
- The implementation report contains synthetic-test evidence and the evaluator command only; it contains no real held-out result or detailed evidence.
- The evaluator handoff names the immutable run output `<output>/protocol.json` and its SHA-256 as the only protocol artifact accepted by D38; it must not hand off D36 `final_protocol.json` as a result protocol.

- [ ] **Step 1: Run full repository checks**

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

- [ ] **Step 2: Prove candidate isolation with synthetic input**

```bash
git -C ../blockvideo-d35-candidate status --porcelain
cd backend
python -m uv run pytest tests/test_d37_blinded_runner.py::test_external_runner_leaves_candidate_checkout_unchanged -q
cd ..
git -C ../blockvideo-d35-candidate status --porcelain
```

Both status outputs must be empty. The test uses only its temporary synthetic corpus, approvals, candidate-host stub, and stateful-index stub; it asserts their hashes in the retained pytest evidence.

- [ ] **Step 3: Inspect, report, and deliver tooling**

```bash
git status --short
git diff --check
git ls-files .env storage release-evidence
```

Record the D36 candidate ID/commit, D37 tool hash, synthetic counts, and that real held-out execution remains evaluator-controlled.

- [ ] **Step 4: Commit and push the implementation task**

```bash
git add backend docs/plan-c/work-report-37.md docs/plan-c/handoff.md docs/DTD.md
git commit -m "[DONE] Mission 37 Add externally attested blinded evaluator"
git push
```

Do not inspect or import real detailed evidence, publish a score, tag, or deploy.
