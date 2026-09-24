# D36 Frozen Release Candidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the exact clean D35 delivery commit as the release candidate, while keeping D36 freeze/trial tooling and all candidate identifiers outside that candidate commit.

**Architecture:** The D35 delivery commit is immutable candidate behavior. D36 adds external freeze and unlabeled-trial tooling in a later tooling commit, then generates ignored evidence whose manifest names the exact D35 parent commit; D37-D40 tools execute externally against an isolated detached checkout/worktree of that parent and are never interpreted as candidate behavior.

**Tech Stack:** Python 3.12 standard library, Pydantic 2, Git CLI, pytest, canonical JSON/SHA-256.

## Global Constraints

- Follow `docs/plan-c/work-unit-36.md`; reconcile `docs/DTD.md` and `specification.md` in the post-candidate D36 tooling commit because tracked pre-freeze documents cannot contain or predict their own commit identifier.
- The candidate is exactly the clean `[DONE] Mission 35 ...` commit. The D36 tooling/delivery commit is its descendant and is external to the candidate.
- `FreezeManifest.git_commit` must equal the exact D35 candidate commit (the D36 tooling commit's parent at the start of D36), never the D36 tooling/report commit.
- Freeze accepts the D35 identity only through a canonical strict candidate-control JSON file plus a separately supplied expected SHA-256. It verifies the detached hash before parsing, rejects non-canonical or extra/missing fields, and requires the control's commit and clean-tree claim to match the detached candidate checkout before any freeze output.
- Candidate identifiers may be recorded only after the D35 commit exists: in the later D36 tooling/report commit and in generated ignored evidence. No tracked document may claim its own not-yet-created commit hash.
- D36-D40 freeze/runner/import/verifier/decision source runs outside the isolated D35 checkout and is separately attested; it is not candidate behavior.
- A D39 behavior fix creates a new D36 freeze. A tooling-only fix changes the tool hash and requires its evidence rerun, not a candidate mutation.
- `FreezeManifest.created_at` is exactly the D35 candidate commit's integer committer
  timestamp normalized to UTC `YYYY-MM-DDTHH:MM:SSZ`; never read wall-clock time.
- No held-out corpus, labels, detailed evidence, secret, absolute private path, DB, media, model weight, cache, or `.env` enters the manifest.
- D36 does not tag, publish, deploy, or decide readiness.
- Final D36 delivery commit is a tooling/documentation commit named `[DONE] Mission 36 Freeze exact D35 release candidate`; it is not the release candidate and must not replace the D35 commit in the manifest.

---

### Task 1: Pin the D35 parent and define the external unlabeled-trial boundary

**Files:**
- Modify in the later tooling commit: `docs/DTD.md`
- Modify in the later tooling commit: `specification.md`
- Create: `backend/evaluation/final_protocol.json`
- Create: `backend/evaluation/unlabeled_contracts.py`
- Create: `backend/evaluation/scripts/evaluation_trial_host.py`
- Create: `backend/tests/test_d36_candidate_protocol.py`

**Interfaces:**

`backend/evaluation/final_protocol.json` is the canonical D36 candidate trial-policy template with:

```json
{"schema_version":1,"modes":["all_tools","stateful"],"per_call_deadline_seconds":180,"maximum_model_calls":4,"isolation":"fresh_case_state_under_source_group","scoring_owner":"external_evaluator"}
```

External trial-host CLI:

```text
python -m evaluation.scripts.evaluation_trial_host --candidate-root ../../blockvideo-d35-candidate --mode all_tools|stateful --input request.json --output observation.json --storage case-storage --model ternary-bonsai-27b-heretic-ja --index stateful-index
```

```python
class UnlabeledTrialCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    case_id: str
    group_id: str
    category: str
    split: Literal["held_out"]
    event: UnlabeledEvent
    initial: UnlabeledInitialState
    case_sha256: str
```

`UnlabeledTrialCase` is an independent wire model. It must not inherit from, import, embed, deserialize through, or expose D24's label-bearing `Case`; neither it nor any nested input model may define `expected`, accepted answers/operations, scoring labels, review status, or a generic extras dictionary. D37 explicitly projects an approved `Case` into this allowlisted structure before serialization, and tests inspect the complete model field graph to prove no label-bearing field can deserialize.

- The external host accepts exactly one `UnlabeledTrialCase`, rejects `expected`, review ledgers, labels, and multiple cases before invoking the candidate, and uses only committed D35 public/application interfaces through a subprocess rooted at `--candidate-root`.
- Output contains observed response/persisted state, call counts/failure classes, replay/confirmation observations, and SHA-256 identifiers; it contains no source text, model bodies, labels, or expected values.
- `stateful` requires an index; `all_tools` rejects `--index`.

- [ ] **Step 1: Update the design contract before code**

Before making any D36 change or commit, capture `git rev-parse HEAD`, the D35 delivery subject, and `git status --porcelain` into canonical UTF-8 `../blockvideo-d36-control/d35-candidate.json` with exactly `schema_version`, `git_commit`, `git_commit_subject`, and `git_tree_clean`; require the subject to be the reviewed D35 delivery and the status to be empty before writing `git_tree_clean: true`. Compute its SHA-256 separately and store/communicate that digest out of band, never inside or beside the control JSON as an authority. Record the already-existing candidate hash and candidate-control SHA-256 in later design/report changes. State explicitly that D36 contains external protocol/freeze/trial tooling only; D36-D40 tools are later than and external to the D35 candidate, with separate source manifests. Replace any diagram/import statement implying tool code executes from, imports into, or mutates the candidate checkout. Record the behavior-fix/new-D35-successor-freeze rule and tooling-fix/new-tool-hash/evidence-rerun rule.

- [ ] **Step 2: Write RED protocol/host tests with synthetic cases**

Assert exact protocol bytes/hash, mode symmetry, output redaction, fresh storage, replay behavior, and refusal of an input containing `expected`, held-out ledger data, duplicate case IDs, or an existing non-empty output directory. Assert recursively that `UnlabeledTrialCase` has no inheritance/import/deserialization dependency on label-bearing `Case` and that unknown nested fields fail closed.

- [ ] **Step 3: Run RED tests**

```bash
cd backend
python -m uv run pytest tests/test_d36_candidate_protocol.py -q
```

Expected: FAIL because the protocol and host do not exist.

- [ ] **Step 4: Implement the minimal external trial host**

Implement the external host as tooling that launches the D35 candidate's committed application interfaces in a candidate-rooted subprocess; do not add or copy a host module into the candidate. Reuse only public D30 all-tools/stateful behavior, external fixture setup, and observation contracts. Do not import future blinded scoring/import/decision modules. Write output atomically under external evaluator storage with `os.replace()` and fixed redacted errors.

- [ ] **Step 5: Run host tests and regressions**

```bash
cd backend
python -m uv run pytest tests/test_d36_candidate_protocol.py tests/test_d30_functional_candidate.py tests/test_comparison_runner.py -q
python -m uv run ruff check evaluation/unlabeled_contracts.py evaluation/scripts/evaluation_trial_host.py tests/test_d36_candidate_protocol.py
```

- [ ] **Step 6: Commit Task 1**

```bash
git add docs/DTD.md specification.md backend/evaluation/final_protocol.json backend/evaluation/unlabeled_contracts.py backend/evaluation/scripts/evaluation_trial_host.py backend/tests/test_d36_candidate_protocol.py
git commit -m "feat: define frozen candidate evaluation boundary"
```

### Task 2: Deterministic manifest and freezer

**Files:**
- Create: `backend/evaluation/tool_attestation.py`
- Create: `backend/evaluation/release_candidate/__init__.py`
- Create: `backend/evaluation/release_candidate/contracts.py`
- Create: `backend/evaluation/release_candidate/fingerprints.py`
- Create: `backend/evaluation/release_candidate/freeze.py`
- Create: `backend/evaluation/scripts/freeze_candidate.py`
- Create: `backend/tests/test_d36_freeze.py`
- Modify: `.gitignore`

**Interfaces:**

```python
class FileFingerprint(BaseModel):
    path: str
    sha256: str
    size: int

class CandidateControl(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    git_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    git_commit_subject: Literal["[DONE] Mission 35 Add recovery-oriented operational UI"]
    git_tree_clean: Literal[True]

class ToolAttestation(BaseModel):
    schema_version: Literal[1]
    tool_name: str
    git_commit: str
    files: list[FileFingerprint]
    aggregate_sha256: str

class FreezeManifest(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    git_commit: str
    git_tree_clean: Literal[True]
    candidate_control_sha256: str
    created_at: str
    runtime: dict[str, str]
    schema_version_number: int
    mode_configuration: dict[str, object]
    files: list[FileFingerprint]
    aggregate_sha256: str

canonical_json_bytes(value: object) -> bytes
fingerprint_files(repo_root: Path) -> list[FileFingerprint]
freeze_candidate(
    *, candidate_root: Path, candidate_control_path: Path,
    expected_candidate_control_sha256: str, output_root: Path,
) -> FreezeManifest
```

CLI:

```text
python -m evaluation.scripts.freeze_candidate --candidate-root ../../blockvideo-d35-candidate --candidate-control ../blockvideo-d36-control/d35-candidate.json --expected-candidate-control-sha256 <DETACHED_64_HEX_SHA256> --output-root ../release-evidence/d36
```

The API/CLI reads the bounded raw candidate-control bytes once, verifies the separately supplied 64-hex SHA-256 before parsing, requires byte-for-byte canonical JSON and the exact strict fields above, then verifies the claimed commit/subject and `git_tree_clean: true` against the detached checkout's `HEAD` and empty porcelain status. Missing, malformed, non-canonical, stale, dirty, extra-field, hash-mismatched, commit-mismatched, subject-mismatched, or false-clean controls fail before fingerprinting or output creation. Its own D36 tooling commit is recorded only in a separate tool attestation and is never assigned to `FreezeManifest.git_commit`.

- [ ] **Step 1: Write RED manifest tests**

Freeze the same detached candidate twice into separate empty output roots while
monkeypatching wall clock, locale, timezone, temp paths, and directory enumeration
order. Assert `created_at` equals `datetime.fromtimestamp(int(git show -s
--format=%ct), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")`, both canonical
`freeze-manifest.json` byte strings are identical, and their SHA-256 values match.
Assert changing only the candidate commit timestamp changes `created_at` and manifest
hash; no fractional seconds or numeric timezone offset is accepted.

Create temporary Git repositories and assert clean/dirty behavior, lexical POSIX paths, deterministic file list/aggregate, changed allowlisted-byte detection, excluded `.env`/DB/media/model/cache/node_modules paths, and missing candidate mode/index/profile inputs. Cover valid canonical candidate control plus detached SHA-256, then independently reject altered bytes, a digest copied from the JSON/sibling file instead of the required argument, malformed/non-64-hex expected digest, non-canonical JSON, unknown/missing fields, false clean claim, dirty checkout, commit/subject mismatch, and stale control. Assert `candidate_control_sha256` is retained and `candidate_id == aggregate_sha256[:16] + "-" + git_commit[:12]`.

- [ ] **Step 2: Implement canonical fingerprinting**

Allowlist backend/frontend manifests/lockfiles, candidate `app`, only evaluation/scripts files already present in D35, frontend `src`, operation/search/retrieval profiles, DTD/spec/work-unit contracts as they exist at D35, and test command metadata. Explicitly exclude later D36-D40 tooling files from candidate fingerprints. Record external model weights only through the configured profile fingerprint. Use UTF-8, sorted keys, compact separators, and `allow_nan=False`.

- [ ] **Step 3: Implement clean-tree freeze output**

Validate the candidate-control detached hash, canonical strict schema, commit subject,
`git_tree_clean: true`, `git rev-parse HEAD == control.git_commit`, and empty
`git status --porcelain` before fingerprinting. Read the commit's integer committer
timestamp with fixed Git argv, parse it as an integer, and render UTC at second
precision; do not call `datetime.now()` or read host timezone for manifest fields. Recheck commit/cleanliness immediately before publication. Under the supplied external output root, write only `{FreezeManifest.candidate_id}/freeze-manifest.json` plus a separate canonical D36 tool attestation with atomic replace. `evaluation/tool_attestation.py` owns the reusable strict `ToolAttestation` and canonical source-file hashing used unchanged by D37-D40; the D36 attestation covers the explicit freezer, protocol, unlabeled-contract, and trial-host source allowlist; add `/release-evidence/` to `.gitignore`. Verify the manifest after writing, refuse tracked output roots, and assert the candidate tree—including ignored-path inventory—did not change. Any mismatch produces no freeze artifact.

- [ ] **Step 4: Run freeze tests**

```bash
cd backend
python -m uv run pytest tests/test_d36_freeze.py tests/test_d36_candidate_protocol.py -q
python -m uv run ruff check evaluation/tool_attestation.py evaluation/release_candidate evaluation/scripts/freeze_candidate.py tests/test_d36_freeze.py
```

- [ ] **Step 5: Commit Task 2**

```bash
git add .gitignore backend/evaluation/tool_attestation.py backend/evaluation/release_candidate backend/evaluation/scripts/freeze_candidate.py backend/tests/test_d36_freeze.py
git commit -m "feat: add deterministic D36 candidate freeze"
```

### Task 3: Candidate gate, post-candidate tooling commit, and reconstruction evidence

**Files:**
- Create: `docs/plan-c/work-report-36.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `docs/modules/operation-core.md` only if documenting the external tool boundary is necessary; do not imply candidate code changed

**Interfaces:**
- `release-evidence/d36/{FreezeManifest.candidate_id}/freeze-manifest.json` is generated after the D36 tooling commit and is not tracked; its `git_commit` is still the exact D35 parent.
- The tracked D36 report may record the already-existing D35 candidate commit, but cannot claim the D36 tooling commit's own hash. The generated ignored manifest/tool attestation records candidate and tooling identifiers without circular self-reference.

- [ ] **Step 1: Pin and reconstruct the already-committed D35 candidate**

```bash
CONTROL=../blockvideo-d36-control/d35-candidate.json
CONTROL_SHA256="<detached digest communicated out of band>"
D35_COMMIT="$(python -c 'import json; print(json.load(open("../blockvideo-d36-control/d35-candidate.json"))["git_commit"])')"
git show -s --format=%s "$D35_COMMIT"
git worktree add --detach ../blockvideo-d35-candidate "$D35_COMMIT"
git -C ../blockvideo-d35-candidate status --porcelain
```

Require the subject to be the D35 delivery commit expected by the handoff and the status output to be empty. Persist the exact D35 hash in the D36 report/tool configuration; never substitute the current D36 tooling commit.

- [ ] **Step 2: Verify the detached D35 candidate and inspect tooling changes**

```bash
git -C ../blockvideo-d35-candidate status --porcelain
git status --short
git diff --check
git ls-files .env storage release-evidence
```

Run the full backend/frontend command set against the detached D35 worktree using external environment/cache directories. Document that D36-D40 tooling is absent from candidate behavior and that the candidate's tracked bytes match the D35 commit.

- [ ] **Step 3: Create and push the post-candidate tooling/documentation commit**

```bash
git add .gitignore backend docs/plan-c/work-report-36.md docs/plan-c/handoff.md docs/modules/operation-core.md specification.md docs/DTD.md
git commit -m "[DONE] Mission 36 Freeze exact D35 release candidate"
git push
```

This commit delivers freeze tooling and documentation only. It is not the candidate. The report may contain the known D35 hash but must not contain or predict this commit's own hash.

- [ ] **Step 4: Generate ignored manifest and tooling attestation**

```bash
D35_COMMIT="$(git -C ../blockvideo-d35-candidate rev-parse HEAD)"
CONTROL_SHA256="<detached digest communicated out of band>"
cd backend
python -m uv run python -m evaluation.scripts.freeze_candidate --candidate-root ../../blockvideo-d35-candidate --candidate-control ../../blockvideo-d36-control/d35-candidate.json --expected-candidate-control-sha256 "$CONTROL_SHA256" --output-root ../release-evidence/d36
python -m uv run pytest tests/test_d36_freeze.py tests/test_d36_candidate_protocol.py -q
cd ..
git -C ../blockvideo-d35-candidate status --porcelain
git status --porcelain
```

The candidate status must be empty and its tracked-plus-ignored snapshot unchanged. The tooling checkout may differ from HEAD only by generated ignored `release-evidence/`. If any candidate byte changes, create a new behavior commit and restart from a new freeze; never edit the detached candidate in place.

- [ ] **Step 5: Validate parent identity from generated evidence**

```bash
python -c "import hashlib,json,pathlib,subprocess; p=next(pathlib.Path('release-evidence/d36').glob('*/freeze-manifest.json')); m=json.loads(p.read_text()); c=pathlib.Path('../blockvideo-d36-control/d35-candidate.json').read_bytes(); h=hashlib.sha256(c).hexdigest(); assert h=='<detached digest communicated out of band>'; assert m['candidate_control_sha256']==h; assert m['git_commit']==subprocess.check_output(['git','-C','../blockvideo-d35-candidate','rev-parse','HEAD'],text=True).strip(); assert m['created_at']==__import__('datetime').datetime.fromtimestamp(int(subprocess.check_output(['git','-C','../blockvideo-d35-candidate','show','-s','--format=%ct'],text=True).strip()),__import__('datetime').timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'); assert m['git_commit']!=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()"
```

The manifest must identify the D35 parent candidate and contain the detached-verified `candidate_control_sha256`, while the separate D36 tool attestation identifies the later tooling source. Recompute the candidate-control bytes' SHA-256 and assert it equals both the supplied detached digest and the manifest field. Do not tag, publish, deploy, or run held-out evaluation in D36.
