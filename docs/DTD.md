# BlockVideo Plan C — Detailed Technical Design

## D41–D46 Extensibility redesign (2026-10-06)

Design source: `plan-c/extensibility-proposal.md`. The skeleton is unchanged in
spirit and made explicit: a large operation catalog is searched by retrieval, a
small model chooses among a few retrieved candidates and fills typed arguments
(a proposal, never code), and only registered handlers execute.

### Catalog-side knowledge (single source)

`app/operations/` holds every operation fact: `definitions.json` (arguments; its bytes
bind retrieval indexes and stay unchanged), `operation_policies.json` (mutating,
requires_confirmation, negative phrases, reference kinds, settings layouts per
version, follow-up generation), `operation_annotations.json` (Japanese utterances,
synonyms, scenarios, distinctions), `search_scope.json` (capabilities), and
`app/interpretation/prompt_rules.json` (rules tagged by operation and mode). Guards,
confirmation, references, generate_after_save, follow-up generation and the
settings-update grammar read policies instead of naming operation IDs. Startup
refuses an operation without a policy or an annotation naming an unknown operation;
an unknown operation defaults to mutating and confirmed. `catalog_compiler`
(`scripts/check_catalog.py`) validates all files together.

### Limits

`app/operations/limits.py`: catalog/scope/ranking/diagnostics up to 4,096 operation
versions, index up to 16,384 documents and 256 MB (JSON vectors; beyond needs a
binary format), and one model call sees at most 32 candidates (`too_many_candidates`
instead of failing every request). With every operation offered in normal mode the
assembled system prompt is byte-identical to D35.

### Retrieval

Index documents gain kind `annotation` (utterances, synonyms, scenarios, one document
each). The manifest binds `annotations_sha256` (`extraction_version`
`public-metadata-annotations-v2`); a changed annotation file marks old indexes stale; a
catalog directory without the file keeps the v1 format (e.g. pinned D35). Ranking with
query text mixes `(1 - 0.35) * cosine + 0.35 * character-bigram Dice` (schema documents
contribute no lexical part). Candidate payloads stay public metadata only: on 30
development requests with the bonsai model, adding annotation notes or example
requests to the payload lowered request-class agreement (21 -> 19/30 at product
level) without improving operation choice, so annotations only shape retrieval.
Development recall@5:
68.1% (English metadata, vector only) to 100% (annotations + hybrid), optimistic
because some annotation phrasings overlap development requests.

### Negation-only requests

`negative_control_reason` also returns `explicit_negative_intent` for any mutating
proposal when the request consists only of negated instructions: removing every
`negated_clause_pattern` match leaves only text that fully matches
`negation_residue_pattern` (punctuation, polite endings; both regexes live in
`operation_policies.json`). "ジョブ7は止めないで" blocks a proposed cancel or
retry; "字幕は変えないで動画だけ作り直して" still allows generation. The rule applies in
normal mode, YOLO mode and to every plan step.

### Unattended (YOLO) mode

`LanguageInput.mode = "yolo"` (server switch `LANGUAGE_YOLO_ENABLED`, default true; UI
toggle default off, remembered per browser). Interpretation appends YOLO-only prompt
rules (guess instead of asking; run the supported part; never act against an explicit
negation). Clarifying guards (reference, subtitle_value, settings_value,
pending_settings, reading, empty_settings) are recorded in `yolo_report.bypassed_guards`
instead of asking; the negative-intent guard, schemas, readiness and the server-wide
`LANGUAGE_REVIEW_ALL` still apply. `submit` confirms on the user's behalf including the
follow-up generation after a save and records `auto_confirmed`. One generation at most
per request; no automatic retries or re-planning yet (proposal section 4-3 I).

### Release decision

D40 always selects stateful as the default. Stateful must pass every gate; All Tools
keeps completion and safety gates while its quality gates are recorded as reference
only. D38/D40 source inventories include `app/operations/limits.py`.

### Not yet implemented (proposal phases)

Plans/recipes for multi-step requests (phase 4), hierarchical retrieval and a
reranker, state retrieval and candidate state lists, per-argument guess rules in the
catalog (YOLO guesses are prompt rules today), cost/attempt budgets and automatic
retries for YOLO, restoring a previous artifact (the YOLO report points to settings
history), catalog-driven frontend and evaluator contracts, and binary vector storage.

## D31–D40 Implementation Contract

### Document control

- **Status:** D38 tooling independently approved; D39 implemented with two review-correction rounds; D40 tooling implemented, independent review pending
- **Delivery mode:** High-Risk for D31 security, D32 concurrency, D34 migration,
  and D37–D40 tooling integrity, privacy, and resource ownership
- **Specification:** `specification.md`, `docs/plan-c/work-unit-31.md` through
  `docs/plan-c/work-unit-40.md`
- **DTD:** `docs/DTD.md`
- **Updated:** 2026-10-03 (D39 second review corrections; D40 implementation)
- **Scope:** sequential hardening, blinded evaluation, and release-readiness decision.
  D38 aggregate import and D39 verification/smoke tooling are implemented with
  synthetic verification; D40 decision tooling is implemented with synthetic verification only. No real aggregate acceptance or readiness approval is inferred.
- **Blocked facts:** D39 clean extras installation and its native launcher/browser
  roundtrip remain unverified. D37 already proved pinned-D35 synthetic stateful/worker
  behavior; that historical proof is not D39 fresh-sandbox or 4 GiB acceptance.
  Independent model-weight provenance, real aggregate, and human/independent acceptance
  remain evaluator/operator inputs, not facts inferred by implementation. Pinned
  D35 README advertises Python 3.13+ / Node 20+; this does not describe the audited
  3.12.12 / Node-24 lane and is a known documentation-gate blocker, not an install
  success or permission to edit the candidate.

### Technical scope and fixed decisions

D31–D35 modify production behavior. The clean D35 delivery commit is the immutable
release candidate. D36 is a later, external tooling commit: it pins that D35 parent
through a strict canonical candidate-control file and detached expected SHA-256,
then freezes an isolated detached checkout of the parent. D37–D40 tooling is also
post-candidate and externally attested; none of it is candidate behavior. D37 runs
only through a separate evaluator against approved, separately mounted held-out
material. D38 imports a non-sensitive aggregate. D39 verifies the exact D35
candidate from isolated temporary environments. D40 emits a decision and never
tags, publishes, or deploys.

The following choices resolve implementation ambiguities:

1. D31 uses a conservative host-side negative-control guard in addition to the
   model prompt. A veto is a safe non-effect and never rewrites one operation into
   another.
2. D32 and D33 first extend tests around existing transaction, receipt, journal,
   checkpoint, and publication seams. Production hooks are added only if a failing
   invariant cannot be exercised by dependency replacement or process termination.
   Public request data can never select a failpoint.
3. D34 uses SQLite `PRAGMA user_version`; unversioned supported databases are
   version 0 and the first explicit current schema is version 1. Compatibility is
   exact at SQLite-affinity level for every existing known column against a scratch
   current-schema database built from registered metadata. Known table/column matching
   follows SQLite case-insensitivity and rejects duplicate known identifiers that collide
   by case before DDL. Python's `sqlite3` backup API creates the pre-migration copy. One non-blocking exclusive database lease is
   acquired before migration and held for the full application lifespan. Offline
   restore acquires the same lease and fails immediately while an app is live. No
   Alembic dependency is added.
4. Migration failure enters a degraded API state: `/api/health` and `/api/startup`
   remain readable, database-dependent endpoints return a fixed 503, and the job
   dispatcher does not start.
5. D37's `stateful` mode is the D30 production semantic configuration with
   readiness annotations and bounded all-tools fallback. D29 B1/B2/P1/B0+ are not
   final-evaluation modes.
6. Detailed held-out evidence remains in evaluator-controlled storage. “Sealed”
   means content-addressed and not imported into this repository; it does not imply
   encryption. Public protocol/result evidence identifies cases and categories only
   with domain-separated evaluator-keyed HMAC-SHA-256 tokens; raw case IDs, text, and
   labels never cross the evaluator boundary. D38 requires an out-of-band expected
   SHA-256 for transfer-integrity validation. Reviewer identity is recorded but not
   cryptographically proven.
7. A source-request group owns one output directory; each case receives a fresh
   database/media child initialized from that case's declared state. Cases do not
   leak mutable state to sibling paraphrases.
8. Human-operation, independent-review, and accepted non-safety limitation evidence
   use strict content-bound JSON records. D40 treats absent records as blockers, not
   as negative results or inferred passes. Completed review evidence requires an
   exact lowercase 64-hex artifact SHA-256; pending/not-performed evidence cannot
   carry an artifact and always blocks.
9. Candidate behavior fixes create a new D35 successor and restart D36. A
   post-candidate tooling-only fix changes that tool's separate source hash and
   reruns every evidence artifact produced by that tool without changing the
   candidate identity.
10. Final evaluation coverage is never vacuous. The D37 protocol and result bundle
    carry the same complete bounded case/category topology; the included set is
    non-empty; and every protocol category has at least one included token in each
    mode. D37 fails before publishing a result when this is false, D38 proves bundle/
    protocol topology identity, and D40 independently reconstructs the topology from
    the accepted bundle and emits Not ready on any mismatch.
11. When approval ledgers exclude a case, the reason is deterministic:
    `both_not_approved` when both approvals are absent, otherwise
    `human_not_approved` or `independent_not_approved` for the sole absent approval.
12. D40 source attestation is a separate, Git-using operation on clean committed
    tooling. The decision operation rehashes its fixed source closure using bounded
    local reads only; it invokes no Git, network, or subprocess. Its source aggregate,
    attestation-file hash, and upstream detached input hashes are distinct.
13. D38 accepts exactly the twenty named checks below with raw booleans `true`.
    Model/index identity is committed through the bundle's exact `protocol_sha256`,
    not through nonexistent direct bundle fields. Neither D38 nor D40 forks D37 models.
14. Actual D37 evaluation waits until D38–D40 source and host prerequisites are
    committed and the final tooling checkout is pinned. Refresh D36 freeze/trial-tool
    attestation at that boundary. A later evaluation-source change alters D37's
    conservative aggregate; a docs-only commit can still alter tool Git identity and
    attestation bytes. Any mismatch requires a new run/evidence ID, never in-place
    regeneration, normalization, or relabeling of published evidence.

Application metadata remains Python `>=3.12`, Windows 11, local SQLite, and the
existing single-server worker. The verification lane is Python 3.12.12, uv 0.12.15,
Node 24.11.1 (24.x, `>=24`), and pnpm exactly 10.18.3. Generic Node `>=20` is not
sufficient for these locks. No Node-26-only runtime API is assumed from `@types/node`.
No cloud call, weights download, new candidate dependency, or private held-out file
is required by implementation tests.

### Architecture and dependency direction

```mermaid
flowchart LR
    UI[React recovery UI] --> API[FastAPI]
    API --> Lang[language_operations]
    Lang --> Guard[intent_guard]
    Lang --> Core[OperationService]
    Core --> DB[(SQLite schema v1)]
    Core --> Live[Process-local job liveness]
    Worker --> Live
    Worker --> Journal[External-call journal]
    Worker --> Artifacts[Immutable artifacts]

    Startup[Startup lifecycle] --> Lease[application-lifetime DB lease]
    Lease --> Migration[migrations]
    Migration --> DB
    Restore[offline restore] --> Lease
    Startup --> Status[startup_status]
    API --> Status

    Adv[evaluation.adversarial] --> Lang

    Control[Detached candidate control + expected hash] --> Freeze[External D36 freezer]
    Freeze --> Manifest[Freeze manifest: D35 parent]
    Manifest --> Blind[External D37 evaluator]
    Blind --> Host[External unlabeled trial host]
    Host -->|subprocess only| Candidate[Detached D35 candidate]
    Blind --> Protocol[Immutable run protocol.json]
    Blind --> Aggregate[Shared result bundle]
    Aggregate --> Import[External D38 importer]
    Protocol --> Import
    Import --> Accepted[D38 accepted triplet]
    Manifest --> Materialize[External D39 runtime materializer]
    Materialize --> Runtime[Read-only verified runtime + materialization evidence]
    Runtime --> Verify[External D39 verifier]
    Verify --> Verification[D39 verification + verifier attestation]
    Accepted --> Decision[External D40 decision]
    Verification --> Decision
    Manifest --> Decision
```

Allowed directions:

```text
contracts/models <- services <- API/main
interpretation <- language_operations <- API
operations core <- language_operations
DB/model metadata <- migrations <- main
D35 app public interfaces <- external evaluation trial-host subprocesses
D36 contracts/fingerprints <- D36 freeze script
D24 contracts + D36 unlabeled wire contracts <- D37 evaluator
D37 shared result contracts <- D38 importer <- D40 decision
D36 freeze + D39 verifier contracts <- D40 decision
```

Prohibited directions:

- `app` packages must not import `evaluation`; no D36–D40 tool is copied into or
  imported by the detached D35 candidate.
- `migrations` must not import API routes, operations, workers, evaluation, or UI.
- model interpretation must not import handlers, DB models, or workers.
- the browser must not decide retryability, migration safety, or remote-call status.
- final-evaluation code must not import D29 experiment selectors.

### Technology and research record

No new runtime package is selected. D35 adds one pinned dev-only test dependency,
`@testing-library/user-event` 14.6.7, to exercise realistic keyboard interactions.
Direct in-scope dependencies are:

| Dependency | Version/constraint | Symbols and role |
|---|---|---|
| Python standard library | Python 3.12.12 verified | `unicodedata.normalize`, `re`, `hashlib.sha256`, `hmac.new`, `json`, `sqlite3.connect`, `sqlite3.Connection.backup`, `os.open`, `os.close`, `os.fstat`, `os.fsync`, `os.link`, `os.replace`, `os.scandir`, `os.killpg`, `stat.S_ISREG`, `secrets.token_hex`, `shutil.disk_usage`, `subprocess.run`, `subprocess.CREATE_NEW_PROCESS_GROUP`, `asyncio.create_subprocess_exec`, `pathlib.Path` |
| SQLAlchemy | 2.0.51 in exact D35 lock; project `>=2.0.36` | existing `Session`, `select`, `inspect`, `text`; ORM and writer transactions |
| Pydantic | 2.13.4 in exact D35 lock; project `>=2.9.0` | `BaseModel`, `ConfigDict`, `Field`, validators; strict manifests and API DTOs |
| FastAPI | 0.139.2 in exact D35 lock; project `>=0.115.0` | `APIRouter`, `Depends`, `HTTPException`; startup status transport |
| pytest / Ruff | 9.1.1 / 0.15.22 in D35 lock; optional `dev` extra | monkeypatch, temporary directories, process/race matrices |
| React | 18.3.1 | recovery/status components |
| TypeScript | locked 5.9.3; project `^5.6.3` | exact frontend mirrors of backend enums |
| Vitest/Testing Library | Vitest 2.1.9; existing component-test packages | component tests |
| `@testing-library/user-event` | exactly 14.6.7; dev-only | realistic tab and keyboard interaction tests; not shipped at runtime |

Official sources previously recorded as checked 2026-09-23:

- Python `sqlite3.Connection.backup`: <https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup>
- SQLite `PRAGMA user_version` and `PRAGMA integrity_check`:
  <https://www.sqlite.org/pragma.html#pragma_user_version> and
  <https://www.sqlite.org/pragma.html#pragma_integrity_check>
- SQLite Online Backup API: <https://www.sqlite.org/backup.html>
- SQLAlchemy SQLite dialect/transaction behavior:
  <https://docs.sqlalchemy.org/en/20/dialects/sqlite.html>

Additional authoritative contract reference added for this amendment; live network
verification was not rerun in this documentation-only session:

- SQLite declared-type affinity rules:
  <https://www.sqlite.org/datatype3.html#determination_of_column_affinity>

The backup connection is synchronous and owned/closed by the migration runner.
The application lifespan owns the database lease and the cached SQLAlchemy engine,
pool, and sessionmaker from pre-migration startup until all database users stop at
shutdown. After dispatcher and registry drain, lifespan marks startup non-ready,
disposes and clears the database caches, and only then releases the lease. Migration
and application startup are single-threaded. Offline restore owns a separate lease
for only its stopped-app operation. Existing async model/provider clients retain
their present ownership and deadlines.

#### Stack audit evidence and implementation consequences

The read-only/synthetic probes in the 2026-09-30–2026-10-01 host session verified
Python 3.12.12, Windows build
26200, SQLite 3.51.1, the versions above, Node 24.11.1, Git 2.50.0.windows.1, and
cached pnpm 10.18.3 help. Current `backend/pyproject.toml`, `backend/uv.lock`,
`frontend/package.json`, and `frontend/pnpm-lock.yaml` equal the exact D35 Git blobs
byte-for-byte. This is manifest evidence, not proof of a fresh install. NumPy,
ONNXRuntime, tokenizers, and uv are absent from the existing backend venv; outer
Python provides uv 0.12.15. Retrieval locks are NumPy 2.5.3, ONNXRuntime 1.30.0,
and tokenizers 0.23.2. The native Node installation probed here has npm 11.6.2;
other installed npm copies must not be mistaken for the selected launcher.

| Primary reference | Version / verification in the 2026-09-30–2026-10-01 session | Consequence |
|---|---|---|
| <https://docs.python.org/3.12/library/subprocess.html> | Python 3.12 docs, captured in audit `primary-sources/python-subprocess.txt` | Native absolute executables, bounded pipe draining; Windows batch files can invoke a shell even with `shell=False` |
| <https://docs.pydantic.dev/latest/concepts/strict_mode/> | Captured strict-mode docs; installed 2.13.4 behavior separately probed | Strict JSON arrays become tuples; strict Python lists do not. `Literal[True]` accepts `1`, and `Literal[1]` accepts `true`; raw/model canonical equality is mandatory |
| <https://docs.astral.sh/uv/concepts/projects/sync/> and <https://docs.astral.sh/uv/concepts/projects/dependencies/> | Captured official docs and installed uv 0.12.15 help | Optional extras are not default dev groups; select both extras, use `--locked`, then direct sandbox Python (no resync) |
| <https://pnpm.io/10.x/cli/install> and <https://pnpm.io/10.x/settings> | Version-10 pages retrieved live; cached 10.18.3 CLI help probed | Frozen dev install with ignored lifecycle scripts; v10 `onlyBuiltDependencies`, not later `allowBuilds` / `--allow-build` policy |
| <https://nodejs.org/docs/latest-v24.x/api/cli.html> | Version-24 page retrieved live; installed 24.11.1 probed | Use APIs/options available in 24.11.1, not the supplied latest-v26 capture |
| <https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew> and <https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects> | Official captures read; Windows stdlib has no `os.open(dir_fd=...)` | Retain existing directory handles and trusted stdin-gated Job Object bootstrap; no new suspended native launcher |

The supplied latest pnpm page contains v11/v12 flags and the Node capture describes
v26. Neither is authority for those newer options on the selected lane. The locked
`eslint-visitor-keys` 5.0.1 requires `^20.19.0 || ^22.13.0 || >=24`, and jest-dom
6.10.0 requires Node `>=22`; Node 24.11.1 satisfies both. `frontend/pnpm-workspace.yaml`
uses `allowBuilds`, while `.pnpm-allow.json` contains `onlyBuiltDependencies`; do not
assume either grants scripts under 10.18.3. Candidate bytes stay unchanged. D39's
explicit `--ignore-scripts` bypasses dependency lifecycle authorization and checks the
locked native esbuild binary before build. Missing native support fails the lane;
there is no automatic rebuild, v12 flag, lock repair, or candidate-config rewrite.
A future narrow v10 authorization needs a new documented, version-probed tooling
contract and new run; it is not part of the current nine-command inventory.

#### Shared evidence parsing and resource contract (D37 prerequisites implemented)

`backend/evaluation/evidence_json.py` is implemented as a pure parser, importing only stdlib,
Pydantic, and `canonical_json_bytes` from `tool_attestation`. It imports no runner,
application, filesystem executor, or result/protocol model. `blinded_io` remains
filesystem-only; callers supply the model and explicit cap. Dependencies stay
`tool_attestation -> evidence_json -> boundary callers` and
`blinded_io -> boundary callers`; these arrows mean provider to consumer.
The external D36 host imports these two helpers only inside host-side functions;
its standalone candidate-worker bootstrap MUST NOT import them from the candidate's
older evaluation package. The D36 freezer and D37 verifier fixed trial-tool inventories
include `backend/evaluation/blinded_io.py` and `backend/evaluation/evidence_json.py`
in lexical order. This dependency-closure update requires a fresh D36 attestation;
existing publications are never rewritten. D37's conservative tracked-source inventory
also binds these helpers and the operator validator's tooling-side retrieval contracts.

```python
TModel = TypeVar("TModel", bound=BaseModel)

def parse_canonical_model(
    raw: bytes, model_type: type[TModel], *, maximum: int,
) -> TModel: ...
```

1. Read regular no-follow bytes through `blinded_io.read_regular(path, maximum=cap)`
   with `cap + 1` detection and descriptor/path identity checks. For detached inputs,
   validate the exact lowercase 64-hex expected digest and actual bytes before parse.
2. Before JSON construction, a bounded string-aware lexical scan rejects depth over
   32, more than 8,000,000 tokens, and string tokens over 8,192 encoded bytes. Each
   scalar/string (including object keys), delimiter, colon and comma counts as one token.
   Then `json.loads` uses a duplicate-rejecting
   `object_pairs_hook` and a rejecting `parse_constant` (NaN/Infinity/-Infinity).
   Reject malformed UTF-8, BOM, surrogate strings, and nonfinite/overflowing numbers.
3. Require `canonical_json_bytes(decoded) + b"\n" == raw`; no whitespace, key order,
   duplicate, spelling, escape, or newline normalization is accepted. Durable files
   have exactly one LF; hash it. In-memory configuration and fingerprint-list
   aggregates use `canonical_json_bytes(value)` without LF. This is project
   canonicalization, not RFC 8785.
4. Invoke `model_type.model_validate_json(raw, strict=True)`, not strict Python
   validation of JSON lists. Compare the model's canonical durable bytes to the same
   raw bytes again: coercible `Literal` primitive values must fail, never become a
   normalized accepted artifact. New Python-facing models additionally check raw
   `type(value) is bool/int/str` before literal validation. Existing D37 result and
   protocol classes are imported unchanged; strict direct-call entry points must
   reject primitive coercions before constructing models.
5. Enforce schema-specific array/map/string limits and all topology/accounting
   invariants. Protocol/result arrays retain 65,535 maxima, candidate/evaluator
   names 128 characters, UTC seconds 20 characters. New file inventories cap at
   8,192 entries with lexical paths <=512 characters; command argv <=64 arguments
   of <=1,024 characters; version strings <=256; gate details <=256; reviews and
   limitations <=256 entries with identifiers <=128. Never log rejected input.

| Artifact | Pre-parse maximum (including LF) |
|---|---|
| D37 `protocol.json`, every D38 protocol reader | 64 MiB (`MAX_PROTOCOL_BYTES`) |
| D37 bundle / D38 accepted bundle / D40 accepted reader | 128 MiB (`MAX_RESULT_BUNDLE_BYTES`) |
| Freeze, source attestation, materialization, validation, verification | 16 MiB |
| One smoke stage receipt | 64 KiB |
| Complete smoke manifest / D40 decision JSON | 1 MiB |
| One review / complete limitation array | 64 KiB / 1 MiB |
| Ownership marker | 4 KiB |

Large blobs are not JSON inputs. Hash source, media, and index files in 1 MiB chunks
with pre/open/post identity/size checks, finite inventory counts and total bytes;
never apply the 16 MiB JSON default to an index blob. Candidate index limits are
64,000 bytes for `manifest.json` and 64,000,000 bytes for a bundle (decimal, not MiB).
D37 `_fingerprint_directory` streams blobs through `blinded_io.fingerprint_regular`
in 1 MiB chunks, checks pre/open/post path and descriptor identities, and sorts the
complete fingerprint inventory lexically. Manifest and blob caps are applied before
reading; index bytes and protocol/result field inventories remain unchanged. On
Windows Python 3.12, path and descriptor `st_ctime_ns` can have different meanings;
compare ctime within each path/descriptor pair, not across APIs. Device/inode/size
and mtime must agree across all four observations. Tool-source fingerprints reject files above 8 MiB before opening, reject growth
while streaming, and compare pre/open/post regular-file identity/size. Source
attestation tallies those bounded fingerprints and rejects inventories above
512 MiB before producing an attestation. Index inventory caps are 4,096 files /
512 MiB total. Parse large artifacts sequentially and
release raw/decoded duplicates once hashes and validated models are retained.
Maximum-topology byte arithmetic is proven. The audited 4,000,000-token scanner
contradicted the unchanged result schema: a directly validated maximum topology has
4,980,838 tokens and 50,794,203 canonical bytes including LF. The maximum protocol
has 917,571 tokens and 19,663,039 bytes. Independent test tokenization counts strings
as indivisible tokens and counts all structural punctuation; it does not use the
production scanner or derive expectations from its constants.

For `N` cases, `C` categories, `I` included cases and `E` exclusions, a binding has
9 tokens and a seven-field category result has 29. Protocol token count is `14N + 81`.
The two ten-field modes contribute `85 + 60C` tokens together. Bundle count is
`177 + 14N + 2I + 10E + 60C` for `E > 0`, or
`178 + 14N + 2I + 60C` for `E = 0`. Since `I + E = N`, `I >= C`, and
`1 <= C <= N <= 65,535`, the maximum is `76 * 65,535 + 178 = 4,980,838`:
one included case per unique category, no exclusions, both full category arrays.
The finite 8,000,000-token cap gives headroom above that proven maximum without
changing depth/string/64-MiB/128-MiB caps, field maxima, strict types, accounting,
canonical ASCII/LF, or sanitized rejection behavior. No dependency or parser API changes.

Implementation order for this bounded completion: reproduce rejection with the actual
maximum fixtures before editing this contract; update this contract; change only
`evidence_json._MAX_TOKENS`; replace the existing actual-overflow test with an
8,000,003-token input whose JSON constructor is forbidden; prove both maximum models
roundtrip through `parse_canonical_model` with unchanged canonical bytes. Fixtures
use literal sorted synthetic 64-hex tokens, not case loading, HMAC keys, or real evidence.
Run parser/D36/D37/D22 coverage and Ruff sequentially, commit before the full backend
clean-root CLI gate. Application, candidate, locks, later-unit source and public schemas
remain unchanged. The isolated two-fixture GREEN probe passed in 17.35 seconds:
observed owned-Python peak-working-set sum 0.680 GiB, sampled owned resident peak
0.628 GiB, conservative controller/worker workload peak 1.824 GiB. These Windows
measurements are one local experiment, not a universal maximum-size performance or
operational acceptance claim; tests impose no parse-time performance cutoff.

The runner and result validator now tally included category denominators once with
`Counter`, then project the declared category order. A 4,096-case/2,048-category
regression bounds actual equality operations without a wall-clock threshold; names,
fields, equations, and thresholds stay unchanged. Maximum-size model parsing is not
yet an operational acceptance claim.

At this historical D37 checkpoint the budget was aggregate RAM <=4 GiB, with a
3 GiB target and 3.5 GiB no-start threshold. The user's 2026-10-02 instruction
supersedes that project/D39 budget with 16 GiB / 12 GiB / 14 GiB respectively; it does
not alter D37 public APIs or recertify historical results. Include the
agent/controller runtime and every owned descendant; measure working sets
before and during execution. Run one command/smoke group, pytest/Vitest worker or
compiler child at a time, with NumPy/ONNX thread limits of one. Bound input/output
and stop only owned jobs before the hard cap; every child has an owner and teardown
deadline. Earlier 16 GiB verification is historical, not evidence that the
current run meets these accounting and ownership requirements. Do not reload a whole tree or repeat maximum-size probes
when a targeted check suffices.

#### Executable-probe blueprint and acceptance checklist (D37 orders 1–2 and 5 implemented)

| Order / owner | Action | Exact acceptance / failure |
|---|---|---|
| 1 / shared tooling | Add parser; exercise duplicate keys, NaN, float/boolean literals, BOM, LF, cap+1, depth/string/count limits; strict JSON tuple roundtrip | Rejection before output for each negative; unchanged shared field inventory and exact canonical positive bytes |
| 2 / D37 host prerequisite | Stream index hash; supply a synthetic loopback profile through explicit host/runner settings described below; pin complete committed tooling and refresh D36 | No candidate writes, no weights download; differing source/protocol/index aborts with fixed reason and new run ID |
| 3 / D39 bootstrap | Fresh external backend sync with both extras; prove executable/base interpreter, uv, lock hashes, module origins; fresh native pnpm frozen dev install | Python 3.12.12 / uv 0.12.15 / Node 24.11.1 / pnpm 10.18.3, all declared modules group-local, no skips caused by missing NumPy, no resync/global fallback; failure stops and cleans |
| 4 / process owner | Native node+npx launcher under the existing gated Windows Job Object; harmless synthetic child/grandchild with parent early exit and inherited pipe | No child work before assignment; terminate descendants on normal exit, timeout, flood and cancellation; 1 s drain grace, 10 s confirmed teardown. Assignment failure never releases gate |
| 5 / D37 integration harness | Exact committed D35 bytes in a verified external sandbox, genuine catalog/profile-bound synthetic index, fake loopback chat+embeddings; both modes and restart resend | Real candidate imports only in candidate-rooted workers, not stub candidate/host or dummy index. Exact expected response/effects, <=4 actual model calls, same source/index hashes before/after, fresh case storage; no default fallback accepted as stateful success |
| 6 / D39–D40 | Six typed receipts, exact command/native-binding inventory, failure-prefix and cleanup tests, all detached inputs, Not-ready baseline | Rehash every receipt's complete canonical bytes/size and artifact hash/size; reject arbitrary six hashes, wrong bindings, stale attestation, missing inputs, and unconfirmed cleanup; no inferred human review |

Orders 3–4 and 6 remain deferred to later units. Fresh-install/native build availability
and browser provenance/automation are still **Blocked facts**. Order 5 is covered by
`test_pinned_d35_genuine_stateful_index_crossprocess_and_original_target` and
`test_pinned_d35_invalid_index_never_executes_or_falls_back`, using the verified exact
D35 Git archive and pinned candidate APIs through `tests/d37_pinned_support.py`.
Both modes, restart resend, original-target reread, actual embeddings/narrowed
retrieval grammar, unchanged complete source/index hashes, and stale catalog/scope/
profile/missing-bundle negatives are checked. Existing stub/current-tree tests remain
unit/regression coverage, not pinned integration proof. Do not repeat broad debug loops: fail the first unmet
prerequisite, record its fixed reason, update this contract only if evidence disproves
it, and resume from that dependency boundary.

### Intended repository structure

```text
backend/app/
├── core/
│   ├── provider_errors.py             # provider-neutral sanitized error contract
│   └── startup_status.py              # process-local bounded startup state
├── migrations/
│   ├── __init__.py
│   ├── backup.py                      # consistent verified SQLite backup
│   ├── contracts.py                   # MigrationResult/Error
│   ├── lease.py                       # non-blocking application-lifetime DB lease
│   ├── runner.py                      # classify, migrate, verify under caller lease
│   └── schema.py                      # v0 -> v1 additive schema operation
├── language_operations/
│   └── intent_guard.py                # deterministic negative-control veto
├── services/
│   └── job_liveness.py                # worker-free process-local liveness view
└── api/
    └── routes_startup.py              # GET /api/startup
backend/evaluation/
├── adversarial.py
├── final_protocol.json                # D36 candidate policy template only
├── unlabeled_contracts.py             # strict label-free host wire model
├── tool_attestation.py                # D36-owned, reused external-tool manifests
├── release_candidate/
│   ├── __init__.py
│   ├── contracts.py                   # candidate control/freeze contracts
│   ├── fingerprints.py                # canonical hashes
│   └── freeze.py                      # clean detached-candidate freeze
├── scripts/
│   ├── evaluation_trial_host.py       # external one-case candidate host
│   ├── freeze_candidate.py            # D36 external CLI
│   ├── materialize_candidate_runtime.py # D39 materialize/cleanup CLI
│   ├── d39_smoke.py                   # external candidate smoke orchestration
│   ├── d39_candidate_smoke.py         # planned internal candidate-rooted bootstrap
│   ├── verify_release_candidate.py    # D39 final external verifier CLI
│   └── attest_release_decision.py     # D40 source-attestation generate/validate CLI
├── evidence_json.py                   # pure bounded strict canonical parser
├── smoke_contracts.py                 # planned six typed smoke receipts; no execution
├── blinded_contracts.py
├── blinded_io.py                    # bounded no-follow reads and crash-safe publication
├── blinded_runtime.py               # candidate anchors and process-tree supervision
├── blinded_runner.py                # D37 orchestration and unchanged public entry points
├── blinded_scoring.py
├── sealed_evidence.py
├── result_contracts.py                # one D37-owned D37–D40 bundle schema
├── result_import.py
├── runtime_materialization.py         # read-only runtime copy/evidence/cleanup
├── browser_smoke.py                   # planned owned CDP browser helper, smoke only
├── release_verification.py
└── release_decision.py
backend/scripts/
├── run_adversarial.py
├── run_blinded_evaluation.py
├── import_evaluation_result.py
└── decide_release_readiness.py
frontend/src/components/
├── RecoveryStatus.tsx
└── StartupStatus.tsx
backend/tests/
├── test_d31_adversarial_safety.py
├── test_d32_concurrency_matrix.py
├── test_d33_recovery_matrix.py
├── test_d34_migrations.py
├── test_d35_startup_recovery_api.py
├── test_d36_freeze.py
├── test_d37_blinded_runner.py
├── test_d38_result_import.py
├── test_d39_release_verification.py
└── test_d40_readiness_decision.py
```

`release-evidence/` is ignored and stores generated candidate/evaluation evidence.
Migration and blinded synthetic fixtures live under `backend/tests/fixtures/`.

### D31 module, function, and contract design

`app/language_operations/intent_guard.py` owns only deterministic safe vetoes.
It imports `re`, `unicodedata.normalize`, and interpretation proposal contracts.

```python
MUTATING_OPERATIONS: frozenset[str]

def normalized_intent(text: str) -> str: ...

def negative_control_reason(text: str, operation_id: str) -> str | None: ...
```

`normalized_intent` applies NFKC, `casefold()`, translates U+2018/U+2019/U+FF07
apostrophes to ASCII `'`, converts all Unicode whitespace to one ASCII space, and
trims. It does not otherwise remove punctuation or identifiers.
`negative_control_reason` returns `"explicit_negative_intent"` only for a mutating
proposal and these normalized phrase families:

- global: `何もしない`, `実行しない`, `変更しない`, `do nothing`,
  `do not execute`, `don't execute`;
- retry: `再試行しない`, `再実行しない`, `やり直さない`, `do not retry`,
  `don't retry`;
- cancellation: `キャンセルしない`, `取り消さない`, `停止しない`,
  `do not cancel`, `don't cancel`;
- generation: `生成しない`, `開始しない`, `作り直さない`, `do not generate`,
  `don't generate`.

Operation-specific phrases veto only the matching operation family. A global phrase
vetoes every mutating operation. No positive operation is inferred from text.
`LanguageOperationService.prepare()` runs the guard after schema-valid proposal
parsing and before `OperationRequest` construction. A veto preserves the original
interpretation for audit, returns `status="dismissed"`, creates no prepared request
or confirmation token, and records diagnostic `guard_code="negative_intent"`.
`LanguageDiagnostics.guard_code` adds that literal.

`evaluation/adversarial.py` defines strict `AdversarialCase` and `AdversarialResult`
records and loads only `evaluation/d31/development.jsonl`. The loader opens the
corpus once in binary mode, reads at most `MAX_CORPUS_BYTES + 1`, rejects excess
bytes, and only then decodes UTF-8 with optional BOM; it must not use a separate
metadata size check. The harness is single-target: `target_project_id` may be
`None`, otherwise it must exactly equal `initial.project_id`. Cases contain synthetic
text, mode, expected status class, explicit forbidden effects, and exact required
effects for settings, revision, jobs, cancellation, receipts, artifacts, and the
external-call journal. Every D31 case fixes the required external-call-journal
change count at zero and marks any journal change forbidden. Initial jobs (maximum
32), settings
history rows (maximum 32), and prior turns (maximum 8) use dedicated frozen
Pydantic records with `extra="forbid"`; their strings and child collections are
bounded to the existing interpretation/fixture limits. The runner converts the
validated initial state to the existing comparison fixture contract, uses isolated
temporary DB/media roots, and executes the ordinary language/core path.

Effect comparison is content-based. Jobs remain keyed by ID; receipts, artifacts,
and external-call journal records are canonicalized and compared as multisets so an
in-place mutation or same-count replacement is an observed effect. Journal response
bytes are represented only by SHA-256 in the in-memory observation. A result passes
only when its status is allowed, no forbidden effect occurred, and every observed
effect count exactly equals the case's `required_effects`. Result JSON contains
only IDs, status, booleans, and counts; it never contains corpus/model text.

The executable D31 dependency-boundary test imports `evaluation.adversarial`,
`scripts.run_adversarial`, and the registered operation service in a clean Python
process whose import finder rejects `app.workers`, `app.services.pipeline`, and
`app.providers`. Operation readiness therefore reads process-local liveness through
`app.services.job_liveness`; workers publish and clear markers without reversing the
dependency. The sanitized `ProviderError` contract lives in
`app.core.provider_errors`, so schema/settings validation does not import provider
modules. This boundary prevents the tested runner/handler import graph from loading
or starting worker/media-provider execution. It does not prove that arbitrary future
dynamic or unjournaled network code is absent.

`app/main.py` changes the catch-all handler to log only
`error_class`, route, and a generated correlation ID; the JSON response is fixed:

```json
{"detail":{"reason_code":"internal_error","message":"処理に失敗しました。再読み込み後も続く場合は記録番号を確認してください。","correlation_id":"..."}}
```

Raw exception strings, request bodies, model bodies, prompts, raw request paths,
filesystem/private paths, and credentials must not appear in application logs or this
response. Logs may retain the matched framework route template as bounded metadata.
Existing narrow domain errors retain fixed user messages but must not forward
arbitrary provider exception text.

### D32 concurrency design

No new lock service is introduced. `services.transactions.begin_write()` remains
the cross-process serialization boundary using `BEGIN IMMEDIATE`. Tests create
independent SQLAlchemy sessions and, for process cases, spawned Python processes
pointing at one temporary SQLite file.

The matrix covers receipt identity, concurrent settings, dialogue supersession,
generation confirmation/revision change, cancel/publication, retry/recovery,
delete/active-or-unknown work, and startup pending-job claims. Assertions inspect
receipts, settings history, language records, jobs, external calls, artifacts,
current-artifact pointers, and project revision after reopening the database. One
transaction may win. All other effects resolve as exact replay, `stale_state`,
`project_busy`, `dialogue_superseded`, request-content conflict, or bounded
`database_busy`. A `WriteBusyError` response keeps `Retry-After: 1` and tells clients
to retry the same request ID. Process-local locks may reduce duplicate work but
never establish correctness.

A continuation claim calls `dialogue.require_not_superseded()` inside its writer
transaction before project revision resolution. This makes the already committed
parent successor the stable loser reason across answer, correction, and dismissal
races. `dialogue.attach()` reuses the same check before writing the successor link.

Project deletion alone composes the existing active-work guard with persisted
`unknown` jobs and remote-side-effect calls in `in_flight`/`unknown`. Once those are
explicitly resolved, `delete_project_external_calls()` removes target-job journal
rows in the same writer transaction as settings-history, artifact, project, and
cascaded job deletion. Immutable operation receipts survive for exact replay. The
route commits before dropping process-local secrets and before best-effort project-
directory removal; commit failure therefore preserves database state, secrets, and
files.

`dispatch_pending_operation_jobs(*, registry: JobRegistry | None = None) -> int`
uses the process singleton only when `registry is None`. Injection is internal and
adds no HTTP or environment selector. Scans may both submit a stale pending ID; the
worker's database pending-to-running claim remains authoritative and permits one
callback execution. D32 makes no multi-server or capacity claim.

### D33 recovery design

Tests inject failures with monkeypatches at existing callable seams:
`repository.claim`, `receipts.save_receipt`, `httpx.AsyncClient.post`,
`external_calls._finish`, `generation_snapshots.capture_inputs`,
`artifact_store.publish_artifact`, and job-control transitions. Process-kill tests
terminate an isolated app/worker only after an observed durable marker.

`recovery_snapshot()['project']` records `id`, `revision`, settings, `status`,
`progress`, `current_stage`, `current_artifact_id`, `output_video_path`,
`output_subtitle_path`, and `error_message` so restart comparisons include the full
project recovery surface.

The shutdown case runs the actual FastAPI lifespan and polling dispatcher in a child
process. `JobRegistry` owns an explicit `_accepting` lifecycle flag, exposed read-only
as `accepting`. A new instance accepts by default for direct worker/test use.
`start() -> None` reopens admission only when both task and cancellation registries
are empty; otherwise it raises `RuntimeError`. `close() -> None` synchronously sets
`_accepting = False`. `shutdown() -> None` invokes `close()` before taking its task
snapshot, calls `task.cancel()` on every accepted task, and awaits all of them with `asyncio.gather(...,
return_exceptions=True)`; it does not set cooperative cancellation flags or write a
terminal outcome. `submit()` checks admission before duplicate lookup or creation and
raises `RuntimeError` while closing, without creating a task, cancellation event, or
liveness marker. Because submission and close/snapshot contain no await and run on the
owning event loop, a concurrent submit either enters the snapshot or is rejected.
`main.lifespan()` calls `start()` before creating the polling dispatcher, then on
shutdown calls `close()` before cancelling/awaiting that dispatcher and finally awaits
the process singleton's `shutdown()` before returning. A deterministic local generation callback observes
and persists the worker's `running` claim, then remains active until registry shutdown
cancellation. Fixed test markers prove `registry_shutdown_started`, callback
`task_cancelled`, and `registry_shutdown_finished` all occur before `lifespan_exit`.
A controlled test enters the same application lifespan twice and proves registry
admission is reopened before dispatcher execution each time. Reopened durable state
must be running before reconciliation, become pending on the first reconciliation,
remain unchanged on the second, retain prior history, and contain no external-call
row for that job.

The resumed-completion case starts from a fingerprint-valid persisted checkpoint,
reconciles it to pending, and submits it exactly once through a real `JobRegistry`.
The injected local callback verifies job input snapshot/fingerprint, checkpoint
snapshot/fingerprint, project revision, and current captured input before publishing.
Invalid or stale checkpoints become failed and cannot reach registry submission.

`artifact_store.publish_artifact()` retains committed-artifact replay as its first
branch because that path performs no filesystem mutation. It may validate a new
candidate before opening the writer transaction, but both an initial rename and an
orphan replacement occur only inside the same `atomic_write` transaction that
publishes the artifact. Before either filesystem operation, the transaction requires:
(1) the job exists, is exactly `running`, and is neither durably nor cooperatively
cancelled; (2) no unresolved external call exists; (3) the project exists; (4)
`project.revision == job.input_revision`; (5) `job.input_fingerprint ==
fingerprint_inputs(settled_inputs)`; (6) the current project fingerprint equals that
settled fingerprint; and (7) materials and the candidate still match their verified
identities. Pipeline checkpoint acceptance writes the newly accepted generated
snapshot to both `job.input_snapshot` and `job.input_fingerprint` together with the
resume snapshot/fingerprint so these equalities remain explicit at publication.

The destination must resolve exactly to
`projects/<project>/history/job-<zero-padded-job-id>/video.mp4`, and the candidate
must be in that same directory. The transaction performs destination reference
queries whenever the final path exists, including when candidate and destination
bytes have the same SHA-256; implementation performs the query unconditionally as a
fail-closed simplification. A `GenerationArtifact.video_path` reference, an artifact
already owned by the same job, a `Project.output_video_path` reference, or a project's
current-artifact reference to that path blocks all rename/replacement and publication.
There is no identical-byte shortcut. Only an exact unreferenced same-job history path
may be created or replaced with the still-verified candidate. When a subtitle is
supplied, its initial path/size/SHA-256 identity is checked again inside the writer
transaction before video rename and again immediately before `GenerationArtifact`
construction. Missing or unequal subtitle identity raises `StaleGenerationInput`.
After rename, the final video size/SHA-256 is checked before constructing the
`GenerationArtifact` and its complete `manifest_json`, current-pointer, and completion
writes. `GenerationArtifact.manifest_json` is the sole authoritative artifact
manifest; artifact publication never writes a per-job `manifest.json` file. The
retrieval index's separately owned `manifest.json` contract is unchanged. A crash,
subtitle rejection, ORM flush failure, or database commit failure after rename can
leave only that exact unreferenced same-job video orphan recoverable by the same rule;
it creates no artifact row or manifest file and leaves job/project/reference state
unchanged. Referenced/current files and prior successful history are never deleted or
replaced.

No generic production failpoint registry is added. Environment variables and HTTP
payloads cannot enable a failpoint. Unknown remote calls remain terminal for
automatic replay. Local calls may be retried only under the fingerprint rules above.
Publication validates file identity before changing current-artifact pointers.

### D34 migration and startup design

#### Persistent version and supported ancestry

- `PRAGMA user_version = 0`: empty DB, upstream/pre-Plan-C DB, or current D30 DB
  created before explicit versioning.
- `PRAGMA user_version = 1`: D34 schema after all current ORM tables and additive
  columns are present.
- Values greater than 1 are rejected as `schema_too_new`.

Version 0 classification is structural. The critical known tables are exactly
`projects`, `blocks`, `generation_jobs`, `operation_requests`, `external_calls`,
`generation_artifacts`, `settings_revisions`, `language_requests`, and
`language_turns`. Unknown extra tables and unknown extra columns are preserved.
Before accepting any non-empty supported v0 or v1 database, registered
`Base.metadata` creates a scratch current-schema SQLite database. `PRAGMA table_info` is read from both files.
Table and column names are indexed by SQLite-compatible canonical keys that map only
ASCII `A`--`Z` to `a`--`z`; every non-ASCII character remains unchanged. Classification,
missing detection, and semantic-reference presence checks use those keys, while SQL
quotes each observed identifier's actual spelling. A pair of known metadata table names,
or known columns within one metadata table, that collide under this normalization fails
`unsupported_legacy_schema` before scratch creation or legacy DDL. Distinct unknown
Unicode identifiers remain distinct and are preserved. One reusable version-aware compatibility validator enforces this structure before DDL,
during migration verification, and for a copied restore candidate before any target
sidecar deletion or database replacement. Version 1 must contain every registered
current table and column. Version 0 may omit whole tables and additive columns that are
nullable or have a server default; if a known table exists, omission of a non-null
column without a server default is unsupported. For every existing column whose table
and column name are known to current metadata, the observed SQLite affinity must equal
the scratch column's affinity. Affinity is
derived from the declared type using SQLite's ordered rules: `INT` -> `INTEGER`;
`CHAR`/`CLOB`/`TEXT` -> `TEXT`; `BLOB` or an empty declaration -> `BLOB`;
`REAL`/`FLOA`/`DOUB` -> `REAL`; otherwise `NUMERIC`. A known-column name collision
with any unequal affinity fails `unsupported_legacy_schema`; aliases, coercible
runtime values, and SQLAlchemy type-family similarity do not relax the comparison.
Missing tables are created from current metadata. Missing columns are added only
when nullable or when a server default can preserve existing rows. After all columns
exist, required ordinary and unique exact column sets are derived from
`Table.indexes`, `UniqueConstraint`, and column `unique` metadata. Existing sets are
read through quoted `PRAGMA index_list` and `PRAGMA index_info`; table, column, and
index-column comparison uses the same ASCII-only folding. Partial/expression indexes
do not satisfy a full metadata requirement. A unique index satisfies an ordinary
requirement for the same exact set, while an ordinary index never satisfies a unique
requirement. Missing sets receive deterministic, quoted, collision-safe names and are
created without dropping, renaming, or replacing any existing index. Version 1 must
contain every required ordinary and unique set. No column is dropped, renamed, or
retyped. The upstream and D30 fixtures are frozen explicit SQL
files; they do not call current metadata and do not derive ancestry by dropping current
columns or tables.

Before backup or DDL, the runner captures for every critical table that exists:
(1) exact row count and (2) a canonical primary-key identity digest. The caller passes
registered current metadata explicitly. The snapshot builds the scratch schema, derives
its exact PK order, and requires the observed table to expose those same PK columns in
that order. A missing expected PK column, unreadable PK query, absent current PK, or
altered legacy PK declaration fails `unsupported_legacy_schema`; the legacy declaration
never selects digest columns. The digest is SHA-256 over compact, sorted-key, UTF-8 JSON containing the table name, ordered PK
column names from the scratch schema, and every PK tuple encoded as typed values
(`integer` with canonical decimal text or `text` with the exact string), sorted by
the canonical encoded tuple bytes. There are no locale-dependent conversions. After
migration, every pre-existing critical table must have the same count and digest;
newly created critical tables must be empty. Backup verification computes and
compares the same values against the source snapshot. These are identity-preservation
checks, not full-row content hashes.

The runner also executes `PRAGMA foreign_key_check` and explicit ID-reference checks
before backup and after migration. Required ownership references are:
`blocks.project_id -> projects.id`, `generation_jobs.project_id -> projects.id`,
non-null `generation_jobs.parent_job_id -> generation_jobs.id` with equal project
ownership, `external_calls.job_id -> generation_jobs.id`,
`generation_artifacts.project_id -> projects.id`, non-null
`generation_artifacts.job_id -> generation_jobs.id` with equal project ownership,
`settings_revisions.project_id -> projects.id`, non-null
`settings_revisions.restored_from_revision` to the same project's revision,
non-null `projects.current_artifact_id -> generation_artifacts.id` with equal project
ownership, `language_turns.request_id -> language_requests.request_id`, and non-null
`language_turns.parent_request_id`/`successor_request_id` to existing request and
turn IDs with reciprocal predecessor/successor consistency. The
`operation_requests.project_id` and nullable `operation_requests.job_id` columns are
intentional non-FKs: immutable receipts survive project/job deletion and reserve
those IDs against reuse, so existence is not required; when a referenced job still exists, its project ID
must equal the receipt project ID. `language_requests.project_id` and
`core_request_id` are likewise durable correlation references. A missing project row
is valid after deletion. If the core receipt exists, however, the language
`project_id` must be non-null and exactly equal `operation_requests.project_id`; a
request that never committed a receipt may retain a null project. Parent/successor turn
checks explicitly test reciprocal columns for `IS NULL` before inequality so SQL
three-valued logic cannot admit a missing reciprocal link. No relationship is validated
by row order, display text, title, or other mutable content.

#### Migration interfaces

```python
@dataclass(frozen=True)
class MigrationResult:
    status: Literal["created", "current", "migrated"]
    from_version: int
    to_version: int
    backup_created: bool
    backup_sha256: str | None

class MigrationError(RuntimeError):
    reason_code: Literal[
        "database_lease_unavailable", "schema_too_new", "unsupported_database",
        "unsupported_legacy_schema", "backup_failed", "backup_invalid",
        "migration_failed", "migration_verification_failed"
    ]
    backup_available: bool

class BackupMetadata:
    target_database_path_sha256: str
    source_schema_version: int
    source_critical_identities: dict[str, TableIdentity]
    backup_sha256: str
    def canonical_bytes(self) -> bytes: ...

class DatabaseLease:
    database_path: Path
    lock_path: Path
    def assert_held_for(self, database_url: str) -> None: ...
    def release(self) -> None: ...

def acquire_database_lease(database_url: str) -> DatabaseLease: ...

def create_verified_backup(
    database_path: Path,
    source: sqlite3.Connection,
    metadata: MetaData,
    expected_identities: dict[str, TableIdentity],
    source_schema_version: int,
    *,
    before_publish: Callable[[], None],
) -> VerifiedBackup: ...

def validate_schema_compatibility(
    connection: sqlite3.Connection, metadata: MetaData, *, version: int
) -> None: ...

def critical_identity_snapshot(
    connection: sqlite3.Connection, metadata: MetaData
) -> dict[str, TableIdentity]: ...

def migrate_database(
    database_url: str, metadata: MetaData, *, lease: DatabaseLease
) -> MigrationResult: ...

def restore_database_backup(
    database_url: str,
    backup_path: Path,
    expected_sha256: str,
    metadata: MetaData,
) -> None: ...
```

Only file-backed `sqlite:///` URLs are migrated. In-memory test databases are
created directly and assigned version 1. Any other dialect fails
`unsupported_database`; D34 does not claim cross-database support.

`acquire_database_lease()` resolves the configured file-backed database, creates its
parent with `Path.mkdir(parents=True, exist_ok=True)`, and only then attempts one sibling
`<database>.migration.lock` creation with `os.open(...,
O_CREAT|O_EXCL|O_WRONLY)`. Parent/lock creation failure maps to lease unavailability.
Acquisition never polls, sleeps, retries, or removes an
existing file; contention raises `database_lease_unavailable` before the database is
opened. The file contains PID and UTC time but those values are never returned
through HTTP. The returned `DatabaseLease` retains ownership until `release()` and stores the
open-file identity plus the exact canonical PID/UTC/random-token payload bytes written
at acquisition. `assert_held_for()` and `release()` each read both the retained
descriptor and the current lock path and require the descriptor identity, path
identity, and both byte sequences to equal the acquired identity/payload. In-place
content mutation therefore invalidates ownership and release never treats freshly
self-read mutated bytes as its token. Release closes the Windows descriptor only after
this validation, atomically renames the current lock path to a unique owner tombstone,
and deletes the tombstone only when its identity and bytes still match the acquisition
record. If a replacement lock was moved by the race, release
atomically hard-links it back only when the lock path is still absent, then removes
the tombstone; a restore collision fails without deleting either other-owner file.
Release is idempotent and occurs after all database users stop. A stale lease is not
removed automatically; explicit operator removal is allowed only after confirming no
application or restore process is running.

For a non-empty version-0 DB, free space must exceed database size plus 16 MiB.
`sqlite3.Connection.backup()` writes to a temporary sibling in
`<db-parent>/.backups/`. Immediately after `mkdir`, the root is checked with `lstat`:
symlinks, Windows reparse points, and non-directories fail, and its strict resolved
path must equal `database_path.parent.resolve() / ".backups"` before any temporary
backup is opened. `PRAGMA integrity_check` must return exactly `ok`; critical source
identities must match. The temporary file is fsynced and hashed before publication.
`create_verified_backup()` requires a `before_publish` callback; the runner supplies
`lambda: lease.assert_held_for(database_url)`, and the backup module invokes it
immediately before both the backup and metadata `os.replace` calls. The published
backup is directory-fsynced where the platform permits, then rehashed; unequal
pre/post hashes fail and remove the incomplete publication. A canonical JSON `<backup>.metadata.json` sidecar binds
metadata schema version 1, SHA-256 of the normalized canonical target path, source
`user_version`, complete source critical-identity snapshot, and backup SHA-256. Its
temporary bytes are fsynced, lease-revalidated, atomically published,
directory-fsynced, and read back exactly. Lease loss before either publication removes
temporary files and any already published backup so no incomplete pair remains. The
migration then uses one SQLite transaction for additive table/column DDL, exact
metadata index-set reconciliation, and `PRAGMA user_version=1`. Index reconciliation
runs only after columns exist; conflicting data that prevents a required unique index
causes migration failure and rollback. Post-verification checks integrity, required
tables, columns, ordinary/unique index sets, preserved pre-migration identities, and
references. Failure rolls back where
SQLite permits and retains only a complete verified backup/metadata pair.
`migrate_database()` re-raises every later DDL or post-verification failure with
`backup_available=True` only after `create_verified_backup()` returned a complete,
verified, published backup/metadata pair. Classification, compatibility, identity,
reference, capacity, backup-creation, and backup-publication failures retain
`backup_available=False`. The exception exposes no path or hash. Lifespan copies this
boolean directly into `StartupStatus.backup_available`, so UI restore guidance is
shown only for a migration failure with an already published verified backup. Every
migration entry point requires a live caller-owned `DatabaseLease` bound to the same
canonical database path and rejects a missing, released, or mismatched lease before
database I/O; it reasserts ownership immediately before backup publication and DDL,
and migration never releases the application lease.

Operational rollback is offline only. `restore_database_backup()` first acquires the
same database lease non-blocking. It accepts only a regular, non-symlink backup and
regular metadata sidecar directly inside the canonical target sibling `.backups`
directory. Canonical metadata, target-path binding, caller hash, source schema,
critical identity, SQLite integrity, version-aware schema compatibility, declared
foreign keys, and semantic references must all validate against the copied/fsynced
temporary file. Version-1 restore candidates missing any known table or column are
invalid even when their hash and canonical metadata are valid. Only after every
validation passes does restore reassert lease ownership before removing each stale
target `-wal`, `-shm`, and `-journal` sidecar and before atomically
replacing the main database. It fsyncs the final file and parent directory where
supported, then reopens the target and rechecks exact hash, integrity, schema,
identity, and references. It releases the lease in `finally`. If an application
(including degraded startup) is live, restore fails `database_lease_unavailable`
before reading the backup or opening/replacing the target. Reverse SQL is prohibited.

`db.register_models()` is registration-only and `db.init_db()` is
`Base.metadata.create_all()` only for a migration-approved/current database.
`db.shutdown_db() -> None` disposes the cached engine/pool and clears both engine and
sessionmaker globals without calling metadata DDL. It is production lifecycle code,
not a test reset, and runs while the application still owns the database lease.
Reflective mutation moves to `migrations/schema.py`. Task 1 temporarily retains the
deprecated `_add_missing_columns(engine)` solely so pre-D34 tests collect: it opens the
engine's DBAPI connection and delegates to `apply_v0_to_v1(connection, Base.metadata)`.
Neither `init_db()` nor startup calls it. Tasks 2/3 migrate those legacy tests to the
runner and remove the wrapper. `main.lifespan()` wiring is intentionally Task 3, not a
Task 1 acceptance condition. In Task 3 it registers models, acquires the lease, calls
migration before `init_db()` and interrupted-job recovery, retains the lease while
ready or degraded, stops dispatcher/database users at shutdown, sets a bounded
`starting` shutdown snapshot, calls `shutdown_db()`, and releases the lease as its
final database-lifecycle action. This order also applies when migration degraded or a
post-acquisition startup error aborts lifespan. `get_db()` therefore rejects between
lifespans, and a later lifespan always creates a fresh pool after an offline restore
has atomically replaced the SQLite file.

#### Degraded startup contract

`core/startup_status.py` owns one process-local immutable snapshot:

```python
class StartupStatus(BaseModel):
    status: Literal["starting", "ready", "migration_failed"]
    reason_code: str | None
    message: str
    schema_version: int | None
    backup_available: bool
```

`GET /api/startup` returns 200 with that value. `/api/health` returns
`status="degraded"` when migration failed. `get_db()` raises a fixed
`StartupUnavailableError` before creating a session unless status is ready; the
exception maps to HTTP 503 with `Retry-After: 5`. The dispatcher and recovery
reconciliation do not run in degraded state.

#### D34 implementation evidence and limits

D34 is implemented and its final-review migration/startup gate collects 121 tests:
107 for schema, backup, restore, and lease behavior plus 14 for startup lifecycle/API
behavior. The gate covers the frozen upstream/D30 fixtures, three partial-v0 unique-
column fixtures, exact metadata ordinary/unique index-set reconciliation, duplicate
insert rejection, malformed-v1 missing-index rejection, preservation of existing
indexes, scratch affinity, and ordered-PK
contracts, the complete nine-table identity set, declared and semantic references,
intentional receipt non-FKs, canonical target-bound metadata/hash, failure injection,
non-blocking app/app and app/restore exclusion, stopped-app restore, fresh-pool restart,
and all eight migration reason codes in degraded startup. `work-report-34.md` records
the exact synthetic identity/hash evidence and repository verification history without
temporary paths. D34 makes no real-user migration, online restore, downgrade,
cross-database, distributed-lock, capacity, or complete row-content-hash claim. D35
is implemented and its evidence is recorded separately in `work-report-35.md`.

### D35 recovery UI and API design

`ProjectDetail` adds one authoritative project-level generation contract:

```python
class ProjectGenerationRecovery(BaseModel):
    code: Literal["busy", "external_outcome_unknown", "ready"]
    recommended_action: Literal["wait", "check_provider", "generate"]

class ProjectDetail(ProjectSummary):
    generation_recovery: ProjectGenerationRecovery
```

`build_recovery_contexts()` derives this contract and job retry context in one
aggregate query over every persisted job and every joined external call for the
requested projects; history response limits never constrain that query. Pending or
running jobs map to `busy/wait`. With no active job, any unknown job or unresolved
remote-side-effect call maps to
`external_outcome_unknown/check_provider`. Otherwise the project maps to
`ready/generate`. The response contains only these bounded enum values and no job,
provider, endpoint, path, or call detail. Pending-job creation enforces the same
active/unknown/unresolved blockers under its writer transaction.

`JobSummary` adds required fields:

```python
recovery_code: Literal[
    "wait", "safe_retry", "external_outcome_unknown", "refresh_required",
    "cancelled", "completed", "failed"
]
recommended_action: Literal[
    "wait", "retry_current", "check_provider", "refresh", "none"
]
```

`job_views.job_summary()` derives both from persisted status and an explicit typed
`RecoveryContext`. `build_recovery_contexts()` computes project-wide unknown-job and
unresolved-remote-side-effect facts in one aggregate query for any job collection;
list and history routes reuse that context for every summary. The unresolved-call
predicate is shared with `create_pending_job()` and matches only
`remote_side_effect IS TRUE` with `in_flight` or `unknown`; local unknown calls do
not block retry. A summary without context never queries implicitly and reports
`refresh_required` for failed or cancelled jobs.

Status mapping is ordered by durable state. Pending or running jobs report `wait`,
including cancellation requests. Unknown always reports
`external_outcome_unknown`/`check_provider`, and completed reports `completed`/`none`.
A failed or cancelled job reports `wait`/`wait` with `retryable=false` while any sibling
job is pending or running; otherwise it reports `safe_retry`/`retry_current` only when
the supplied project context proves that the full `create_pending_job()` path has no
project-wide active or unknown job and no unresolved remote side effect. Uncertain work
reports `external_outcome_unknown`/`check_provider`. Existing prose fields remain
compatibility display text, but button state uses only `retryable` and
`recommended_action`. Frontend cancellation controls identify active rows from typed
`pending`/`running` status rather than treating every `wait` recommendation as a
cancellable target.

Frontend mirrors these exact unions. `RecoveryStatus.tsx` renders one status region
and optional action description; it does not execute an action itself. Project-level
generation, rerender, and block controls require
`generation_recovery=ready/generate`; project guidance renders `busy/wait` or
`external_outcome_unknown/check_provider` even when the blocking row is older than
the 100-row history window. Immediate retry revalidation requires the refreshed
project contract to remain `ready/generate` in addition to the target job's retry
contract. Immediate cancellation revalidation requires the refreshed project contract
to remain `busy/wait` in addition to the target job's cancellation contract.
`StartupStatus.tsx` performs only `GET /api/startup` while status is `starting`, with
one request in flight, a fixed two-second interval, and an `AbortController` plus
timer cleanup on effect replacement or unmount. Polling stops on `ready`,
`migration_failed`, or network failure and never calls an operation endpoint. A
network failure displays fixed text without exception details and a native button
that starts a fresh status request. Migration-failure guidance names documented
backup restoration only when `backup_available` is true; the false branch instead
directs the operator to stop, restart, and contact support. `GenerationHistory` uses
the new fields for labels and control visibility. Project and history fetches, including
refetches, disable recovery controls. Immediately before retry or cancellation,
`ProjectDetailPage` refetches both resources, locates the same job, and requires the
current typed status, `recommended_action`, `retryable`, cancellation flag, and equal
project/history revisions to authorize that exact action. A failed check executes no
operation and displays refresh guidance. A synchronous revalidation lock preserves
duplicate-action exclusion before React state updates. All buttons remain native
buttons, status text uses `role="status"` or `role="alert"`, and focus order follows DOM
order. Vitest proves structural narrow-layout containment; Task 4 supplies local
real-browser evidence at 390x844 and 1440x900 against synthetic API state.

### D36 frozen D35 candidate and external trial boundary

The candidate is exactly the clean `[DONE] Mission 35 Add recovery-oriented
operational UI` commit `522775516c0797abdb313e3432339a3a444b7ae2`. Its canonical
external control is `../blockvideo-d36-control/d35-candidate.json`, whose separately
communicated SHA-256 is
`dda5f8b5e1ca95ca0b709122d1fa2826ba647e05d720d829b9e06b4b3f88e833`.
D36 tooling is committed later and freezes an isolated, detached checkout of that D35
parent. Before any D36 output, the operator supplies that canonical
`CandidateControl` plus its expected SHA-256 through the separate channel:

```python
class CandidateControl(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    git_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    git_commit_subject: Literal[
        "[DONE] Mission 35 Add recovery-oriented operational UI",
        "[DONE] Mission 35.1 Fix release-candidate verification blockers",
    ]
    git_tree_clean: Literal[True]

class FileFingerprint(BaseModel):
    path: str
    sha256: str
    size: int

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

class CompletionMarker(BaseModel):
    schema_version: Literal[1]
    files: list[FileFingerprint]  # exact sorted canonical artifact fingerprints
```

#### D36 successor candidate amendment (2026-10-03)

The frozen D35 commit cannot pass D39 (credential-shaped test literals, a
build-time rewrite of tracked `frontend/vite.config.js`, README prerequisites and
README links to documents outside the inventory), and D35 bytes are never edited. An
authorized successor candidate is therefore allowed: a commit on top of D35 whose
subject is exactly `[DONE] Mission 35.1 Fix release-candidate verification blockers`
and which changes only those blockers. `CANDIDATE_COMMIT_SUBJECTS` lists the two
authorized subjects; the strict `CandidateControl` literal, the freezer and the
runtime materializer (which now reconstructs the control from the candidate
commit's own subject) accept only them. Any other subject is refused.

The inventory also includes tracked documentation under `docs/` with `.md`, `.png`,
`.jpg`, `.jpeg`, `.gif` or `.svg` suffixes, so README links resolve inside the
materialized runtime. This changes the inventory and aggregate of any re-freeze
(including D35), so earlier D36 evidence stays valid only for the tooling that
produced it. No gate, threshold or pin changes.

#### D37 projection parity amendment (2026-10-04)

D37's first held-out run stopped before any trial because `case_to_unlabeled` was
stricter than the D24 case format. The D24 development seed is the reference reading
of a case's initial state, so the projection now matches it: partial job
`input_settings` complete from the owning project's settings, partial history
settings complete from the selected project's current settings, a job of another
project seeds that project in `additional_projects` (product defaults plus the job
snapshot, revision from the job, `generating` when active and `failed` otherwise), a
missing job `kind` is `full`, and prior turns without `project_id`, `base_revision`
or `settings_saved` take the selected project, a revision derived from
`result_revision` (minus one when the turn saved settings) or the current revision,
and `false`. Event details, prior-turn statuses and proposal kinds outside the wire
contract still fail closed; the frozen D36 trial host and wire contract are unchanged.

A content-free check of the held-out corpus at `b9ac596` then reported 22 of 200
cases still unprojectable, in seven structural patterns. Case reading now lives in
`evaluation/case_normalization.py`, used by both projection and scoring so the trial
input and the expected state cannot diverge: author spellings of event details
(`competing_revision`/`competing_settings`, `switched_project_id`, `changed_request`)
map to the wire names, `switch_target` defaults its only action, prior turns take
`project_id` from `target_project_id`, a null `base_revision` is derived like a missing
one, and an explicit successor link to the case's own request is dropped because the
host links the continuation itself. The D36 wire contract and trial host also change:
`voicevox_pitch_scale`, a catalog setting of `project.settings.update`, joins the wire
settings, patches, v1 arguments and history fields, and prior turns may carry
`unsupported` and `no_operation` proposals, seeded with the matching outcome status.
Because these are D36 trial sources, the successor must be re-frozen and D39 rerun
against the new freeze; earlier D36/D39 evidence stays valid only for its tooling.

A third check (at `4c34ae6`, against the r2 freeze) left 7 of 200 cases in four
patterns, all handled in the D37 reading without touching D36 sources: a competing
full-project snapshot reduces to the modeled settings it changes (all modeled keys when
none change); a successor link to a request not seeded in the case is dropped; and a
project named only by a prior turn or by a changed request is seeded with product
defaults (`completed`, revision at least the turn's base/result revision, else 1).
Changes to unmodeled settings stay outside the wire state, as before.

A fourth check (at `39e7144`) left 4 cases. Three describe a race after the request's
own save: the request saves (initial+1) and awaits generation confirmation, an external
save lands (initial+2), and the original confirmation is then attempted. The wire race
event gains `timing` (`before_execution` default, or `after_submit_before_confirmation`,
read from the author's `phase`/`when` label and requiring `external_revision` =
initial+2); the host applies such a race after submit and then posts the original
confirmation, and scoring treats it as a confirmation event with the request's save
persisted before the race. The fourth answers a clarification about another project;
the product rejects that at runtime (`dialogue_target_mismatch`), so the wire no longer
pre-rejects a continuation whose parent belongs to another project.

Testing the race end to end against the real product exposed scorer assumptions that
had only been checked against canned observations. Each is now covered by a
real-product scoring test whose labels were written from RULES.md before running it,
across none, resend, restart resend, concurrent, same-id/different-body, confirm,
confirm-twice, generation start, clarification, unsupported, no-operation and both
race timings:

- The product records the pre-change revision as a history row before the first save
  or job when none exists; expected history now includes it.
- `executed` is true once the request's own settings save ran, including while
  generation awaits confirmation or after that confirmation is refused.
- Queuing a job may change the primary project's `current_stage` and `progress`.
- The host's cancellation effect also registers a queued or removed job.
- Saving and then confirming generation adds two receipts.
- Concurrent identical submissions: the host now settles an in-flight duplicate by
  reading its stored response (bounded polling) before comparing, and scoring relies on
  the persisted checks rather than a before/after state comparison that spans the one
  execution.

Host and wire changes are D36 sources, so the successor is re-frozen (r3) and D39 rerun.

A sixth check (at `91bae4b`) left one after-submit race whose request only prepared a
generation (original confirmation revision = initial), so the external save is
initial+1. After-submit races now accept initial+1 or initial+2; scoring expects +2 only
when the request's own save persisted, and the host never reuses a revision the request
just recorded. A real-product test covers this prepare-only race. Re-frozen as r4.

The runner now projects every included case before writing the protocol, so an
unprojectable corpus stops before any trial. `scripts/check_blinded_projection.py`
reports failures by case ID, field location, key name and identifier-shaped labels
only, so an evaluator can share the report without revealing held-out text or labels.

`evaluation/release_candidate/freeze.py` reads bounded control bytes once, validates
the detached lowercase 64-hex digest before parsing, requires byte-for-byte canonical
JSON and the exact fields above, and then matches commit, subject, and cleanliness to
the detached candidate. Candidate validation rejects any cached index entry whose
`git ls-files -v` tag is not normal `H`, any non-stage-zero entry, and any index mode
other than regular `100644` or `100755`; this rejects assume-unchanged,
skip-worktree, sparse-index directories, symlinks, submodules, and other special
entries. For every allowlisted path, `fingerprint_committed_file()` reads the working
regular file through its descriptor, reads `git show HEAD:<path>`, requires equal size
and SHA-256, and places the committed blob size/hash in the manifest. Porcelain status
is therefore not the provenance boundary. `backend/.env.example` is explicitly
required and allowed before the broad `.env` exclusion; other environment files remain
excluded.

`_detect_schema_version()` parses only the committed
`backend/app/migrations/schema.py` blob with Python `ast`. Exactly one
`apply_v0_to_v1` definition and exactly one `connection.execute()` call with the
exact constant text `PRAGMA user_version=<decimal>` must exist; malformed AST/text, absence, or ambiguity
fails. The detected decimal must equal the sole supported version 1 and is recorded as
`FreezeManifest.schema_version_number`; it is never supplied by the caller or
hardcoded into the manifest independently of source.

`FreezeManifest.created_at` is not wall-clock time: it is the candidate commit's
integer committer timestamp (`git show -s --format=%ct`) rendered in UTC exactly as
`YYYY-MM-DDTHH:MM:SSZ`. Git timestamps are second precision, so no fraction is
emitted. The freezer rechecks commit and cleanliness immediately before publication.
Given identical candidate-control bytes, committed allowlisted blobs, and
runtime/version strings, canonical manifest bytes are byte-identical; generation time,
host locale, timezone, temp paths, and directory enumeration order cannot affect them.
The fingerprint allowlist contains D35 behavior and its manifests, lockfiles, frontend
source, profiles, tests, and design contracts as they existed in D35; it explicitly
excludes all later D36–D40 tooling plus secret `.env` files, databases, media, weights,
caches, `node_modules`, and held-out material. Paths are lexical relative POSIX paths.
`candidate_id` is `aggregate_sha256[:16] + "-" + git_commit[:12]`.

D36 also creates the shared strict `evaluation/tool_attestation.py` contract.
`validate_git_repository()` resolves `git rev-parse --show-toplevel` and requires it
to equal the declared tooling root, requires declared `git_commit == HEAD`, a fully
clean tracked/untracked status, and the same normal index-entry constraints used for
the candidate. `attest_tool()` fingerprints every source from the declared HEAD blob
only after exact working-byte comparison, repeats repository and per-file validation,
and therefore refuses real generation until all attested tooling bytes are committed.
The separate canonical D36 source attestation identifies the post-candidate
freezer/protocol/unlabeled-contract/host allowlist and never replaces
`FreezeManifest.git_commit` or `aggregate_sha256`; D37–D40 reuse the attestation model
and canonical hashing unchanged.

`_validate_output_root()` permits any resolved external root but, when the root is
inside the identified tooling repository, permits only resolved
`<tool-repo>/release-evidence/**`; `storage`, cache directories, and every other
ignored or tracked in-repository location fail. The freezer never creates or opens the
final candidate path while constructing evidence. It creates one hidden staging
directory named from a cryptographically random token directly under the validated
output root and immediately acquires a directory anchor.

On POSIX the anchor is an `os.open()` descriptor with
`O_RDONLY|O_DIRECTORY|O_NOFOLLOW`; its directory type and `(st_dev, st_ino)` identity
come from `os.fstat()`. Every fixed child is created with `os.open(name, ..., dir_fd=
anchor_fd)`, and all truncate/write/fsync/readback operations use retained child
descriptors. On Windows the existing D36 anchor is a `CreateFileW` directory handle opened with
`GENERIC_READ`, `FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT`, and sharing
`FILE_SHARE_READ|FILE_SHARE_WRITE` but not `FILE_SHARE_DELETE`.
`GetFileInformationByHandle` supplies the volume/file-index
identity and directory/reparse attributes. The no-delete share prevents cooperative
rename, deletion, or directory replacement while the handle is live; fixed child paths
are opened only while that handle is retained. Any anchor type or identity mismatch
fails closed.

The freezer creates exactly `.d36-publication-state`, `freeze-manifest.json`, and
`d36-tool-attestation.json` in the anchored staging directory. It writes and fsyncs a
random 32-byte token through the retained state descriptor, writes and reads back the
canonical artifact bytes through retained descriptors, validates their strict models
and aggregates, then writes and reads back the canonical newline-terminated
`CompletionMarker` last. The strict version-1 marker contains exactly two sorted
`FileFingerprint` entries whose sizes and SHA-256 values bind the canonical artifacts.
The staging directory is fsynced on POSIX before publication.

Publication atomically renames the whole completed staging directory to
`<root>/<candidate_id>` with true no-replace semantics. Linux uses `renameat2(...,
RENAME_NOREPLACE)`; unsupported POSIX platforms fail closed. Windows revalidates the
anchor, closes retained child descriptors while the no-delete directory anchor remains
live, rechecks each fixed child identity, closes the directory anchor immediately before
publication, then calls `MoveFileExW(staging, final, 0)` without
`MOVEFILE_REPLACE_EXISTING`. POSIX retains the anchor and child descriptors across the
rename. A concurrently created final destination wins unchanged; the random staging
directory remains and is not evidence. After a successful rename, remaining retained
descriptors are closed, the output root is
fsynced where supported, and only the independent `read_frozen_candidate()` reader
opens the final path. The publisher performs no final-path file write or readback.

There is no recursive cleanup, final-path cleanup, or identity-blind move. On any
failure, ownership loss, or post-publication reader rejection, the freezer closes its
handles and never deletes or moves a path whose anchored identity is unavailable or no
longer matches. Random staging directories may therefore remain. Their names cannot
match the content-derived candidate ID, and `read_frozen_candidate()` rejects them as
evidence.

The threat model covers cooperative concurrent processes and path replacement after
anchor acquisition: retained descriptors/handles keep construction bound to the
anchored staging object, and no-replace publication preserves a concurrent final
winner. A malicious same-user principal is outside the trust boundary. In particular,
mutation in the unavoidable `mkdir` to anchor-acquisition syscall gap is not claimed to
be prevented; such a principal can also tamper with process memory or handles. The
Windows design does not claim an unavailable atomic `mkdir` plus `CreateFileW`
operation.

`read_frozen_candidate()` and every downstream reader MUST require exactly
`freeze-manifest.json`, `d36-tool-attestation.json`, and the regular
`.d36-publication-state`; require its bytes to parse as the canonical completion record
and match the exact two-file fingerprint list; reject a token-valued/incomplete state
and every extra entry; parse bounded artifact bytes through strict models; reject
duplicate or unsorted manifest paths; recompute
`aggregate_fingerprints(manifest.files)` and require exact `aggregate_sha256` equality;
derive `candidate_id` exactly as the aggregate's first 16 hex characters, a hyphen, and
the commit's first 12 hex characters; and recompute the tool-attestation aggregate. The
completion record's size/hash pairs must equal the exact canonical artifact bytes. The
reader captures all three file identities, rereads all bytes, and rechecks identities
and the exact entry set before returning.

`evaluation/final_protocol.json` is the canonical D36 policy template only. The
external `evaluation_trial_host` accepts exactly one strict independent wire object:

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

Neither this model nor any nested model may inherit from, import, embed, deserialize
through, or expose D24's label-bearing `Case`; no field graph may contain `expected`,
accepted operations/answers, scoring labels, review state, generic extras, or generic
action/when/then payloads. D37 projects each approved `Case` through an explicit
allowlist before serialization. Event variants are a discriminated union: normal,
identical resend, fresh-process restart resend, same-ID changed body, concurrent
identical submission, revision race, one/two confirmation attempts, and target switch
accept only their consumed fields. `UnlabeledSettingsPatch.not_empty()` requires a
non-empty `model_fields_set` and rejects the whole patch when `getattr(self, field)`
is `None` for any supplied field. Thus omitted fields remain omitted, at least one
non-null consumed field is required, and explicit JSON `null` is invalid even beside
a valid supplied field. This validation occurs during host parsing before candidate
path setup or `_run_candidate()`. Confirmation uses
`POST /api/language/requests/{request_id}/execute`. Numeric and string bounds equal
the candidate contracts. `UnlabeledPronunciation` enables Pydantic whitespace
stripping before its 1--80 surface and 1--160 reading bounds, then rejects the
candidate delimiters `。！？\n\r`, readings beginning with
`ァィゥェォャュョヮー`, and accents above the reading's mora count, where
`ァィゥェォャュョヮ` do not add a mora. One `AfterValidator` on the shared tuple
alias rejects surfaces that duplicate after trimming, so initial projects, job
snapshots, history, revision-race patches, and seeded proposals share one rule. The
100-entry maximum and a 160-mora reading with accent 160 are valid. The host recomputes `case_sha256` from compact sorted-key
ASCII JSON of the case without `case_sha256`; all canonical hashes use the same
no-newline bytes, while durable JSON files append one newline.

Initial state explicitly permits the primary project, bounded additional projects,
full settings/history, jobs, artifact identities, operation receipts, external-call
records, and prior language turns. A prior clarification proposal mirrors production
`ClarificationProposal`: `missing_fields` has one to three entries and each entry is
`target`, `arguments`, or `intent`. Production does not require entry uniqueness, so
the unlabeled contract does not add it. The host rejects `revision`, `job_id`, empty
lists, and lists longer than three before worker launch; a real-worker test seeds all
three valid values through `InterpretationOutcome` validation. Strict seed maxima are 16 additional projects,
32 history rows, 32 jobs, 32 explicit artifacts, 32 revision-derived artifacts,
32 receipts, 32 external calls, and 8 prior turns. `RedactedState` bounds each count
by its complete seed maximum plus the protocol-wide maximum of four event/model
effects: `project_count <= 17`, `history_count <= 36`, `job_count <= 36`,
`artifact_count <= 68`, `receipt_count <= 36`, `external_call_count <= 36`,
`language_request_count <= 12`, and `language_turn_count <= 12`. Projects receive no
event allowance because events cannot create projects. These are finite acceptance
bounds rather than expected-effect assertions; actual effects remain separately
reported. To make persisted-effect scoring verifiable without exposing case text or
labels, `RedactedState` also carries four required sorted bounded tuples. Project
entries contain `id`, `revision`, `status`, a canonical settings hash, hashes of title,
source script, global visual style, and error content, bounded progress/stage values,
current artifact ID, and path-free output file identities. A non-null stored output
path projects `path_sha256 = SHA-256(UTF-8(canonical stored relative path))`; this is
never derived from the storage root or a resolved absolute path. `path_sha256` remains
required when the referenced file is missing. Existing files require non-null size and
content hash; missing files require both values to be null; a null database pointer is
represented by a null file identity. Project entries are ordered by `id`.
History entries contain only `project_id`, `revision`, `settings_sha256`, sorted
`changed_fields`, and `restored_from_revision`, ordered by `(project_id, revision)`.
Job entries contain only `id`, `project_id`, `status`, bounded `current_stage`,
bounded numeric `progress` and `stage_progress`, `input_revision`,
`cancel_requested`, `kind`, `block_index`, `parent_job_id`, nullable lowercase
SHA-256 `input_fingerprint`, and required lowercase SHA-256 identities for the
canonical input snapshot, plan, recovery message, and error message, ordered by
`id`. The four required identities hash canonical values even when the underlying
value is null; only `input_fingerprint` projects null directly. Artifact entries contain only `id`, `project_id`, `job_id`,
`revision`, `input_fingerprint`, `video_path_sha256`, optional `video_size`, optional
`video_sha256`, optional `subtitle_path_sha256`, optional `subtitle_size`, optional
`subtitle_sha256`, and `manifest_sha256`, ordered by `id`. The video path hash is
required because an artifact always stores a video path. Size and content hash are
both non-null exactly when the referenced file exists. A subtitle size or content hash
requires a subtitle path hash; a non-null path hash with null size and content hash
represents a missing referenced file. No entry contains raw or resolved paths,
source/model text, messages, labels, or settings values. Tuple
lengths MUST equal their corresponding
counts, identities MUST be unique, and ordering MUST be canonical. The input validator accepts `artifact_revisions` only as strict integers from 1 through
`10**12`, requires each to be no newer than the primary project, and requires the
largest explicit artifact ID plus the revision-derived artifact count to fit
`2**63 - 1`. Before worker launch it builds the complete seeded graph and rejects:
unknown project, job, artifact, receipt, external-call, history, dialogue-parent, or
dialogue-successor references; a revision newer than its owning project; cross-project
job-parent, artifact-job, receipt-job, continuation-parent, or current-artifact links;
job or dialogue cycles; non-reciprocal dialogue links; missing restore-source revisions;
and database uniqueness collisions for artifact jobs, receipt jobs, or external-call
job/fingerprint pairs. A revision-race event is accepted only when its external revision
is in the global revision range, is absent from that project's seeded settings history,
and equals the primary project's exact next revision. Repository-owned development and
synthetic race cases are contract-tested against this `initial + 1` rule. A mounted
held-out case that violates it fails strict host parsing before candidate execution;
the evaluator and scorer never normalize a revision gap into different semantics.
Explicit and revision-derived artifact IDs are checked as one set. Receipt request/result hashes must equal the exact values reconstructed by the
worker. `current_artifact_id`, `parent_request_id`, and `successor_request_id` are
optional for compatibility. An explicit non-null `current_artifact_id` is validated
against the complete artifact graph and seeded exactly; only that value sets the
project's `current_artifact_id` and output video path. A null or omitted pointer remains
null even when the project owns artifacts. Omitted prior-turn links retain the
deterministic list-order chain. The worker derives complete
generation snapshots and fingerprints with candidate
`capture_inputs`/`fingerprint_inputs` and creates synthetic artifact bytes whose
size/hash must match the wire identity. Stored media paths MUST be canonical relative
POSIX paths: empty, absolute, drive/colon (including Windows ADS), backslash, NUL,
dot, dot-dot, and empty components are rejected. The canonical storage root and every
existing component are checked with `lstat` as non-link/non-reparse; parents are
directories and an existing final is regular. The final is opened with no-follow where
available, pre/open/post descriptor identity and size are compared, and SHA-256 is
streamed in fixed 1 MiB chunks. Missing files preserve only the valid stored-path hash.
External, symlink, reparse, and special paths fail closed without reading external
bytes; raw/resolved paths are never projected. This protects against cooperative path
replacement, not a hostile same-user principal that can alter process memory or race
platform calls outside available handle guarantees. No label model or D24 contract is
imported. Before and after each event, the worker canonicalizes sorted
records for every project and settings revision; complete job snapshot/fingerprint
state; receipt request/result values; artifact manifest and file identities; external
call response hashes; and language request/turn values. `_logical_state()` recursively
removes `created_at`, `updated_at`, `started_at`, `finished_at`, `lease_until`,
`owner_token`, and every `*_ms` field. It discovers generated `core_request_id` and
`confirmation_token` values, assigns deterministic ordinal placeholders ordered by
field and stable caller request ID, and replaces those values wherever they occur, including inside
request references. Stable caller IDs and database IDs are retained. Collection
hashes, counts, fixed enums/flags, and effect counts therefore detect replacement or
in-place mutation without changing across fresh equivalent runs. `RedactedState`
projects sorted bounded SHA-256 identities for receipts, external calls, language
requests, and language turns. Each identity hashes the canonical complete record after
replacing generated opaque ordinals with one stable opaque marker; no raw request ID,
turn text, or held-out value is emitted. `ObservedEffects` records exact additions for
these collections and strict booleans stating whether every pre-event canonical
identity remains in the post-event set. The worker computes those booleans by identity
subset, never by count comparison. Response hashing uses
an allowlisted projection that excludes diagnostics, messages, questions, model prose,
paths, and private content. `RedactedResponse` includes the actual bounded HTTP status,
strict language status/mode/operation/reason enums, execution/confirmation flags, the
strict operation version, canonical arguments SHA-256, separate `generate_after_save`
and prepared-request `generation_requested` flags, and the sorted unique tuple of
`target`/`arguments`/`intent` clarification fields when status is `needs_input`.
Operation-detail fields are all present or all null; clarification fields are present
only for `needs_input`. The response hash covers the remaining allowlisted
revision/job projection. Primary, replay,
confirmation, and duplicate-confirmation requests each retain their own actual
projection; no secondary event is projected with an assumed HTTP 200.

The host rejects label/review/scoring fields, multiple cases, explicit-null settings
patch fields, wrong mode/index combinations, or non-empty output before candidate
invocation. The D36 contract test parametrizes all six patch fields, pairs each null
with a valid non-null field, and proves `_run_candidate()` is not called. It performs `lstat`
before resolution and rejects symlink/reparse/non-regular candidate, backend, index,
storage, input, output, and temporary-file surfaces as applicable; every resolved
path is containment-checked again before publication. `_candidate_snapshot()` walks
candidate files in sorted relative-path order, excludes only repository/runtime cache
and generated-output directories, rejects special/symlink/reparse entries, hashes each
regular file with a descriptor identity/size check, and hashes the canonical entry
list. The host records this snapshot before worker launch, requires exact equality
after the final worker, and publishes the hash in `TrialObservation`. Candidate Python
starts with both `-B` and `PYTHONDONTWRITEBYTECODE=1`; user-site imports remain disabled.
Temporary files use exclusive unpredictable names, no-follow flags where available,
and file fsync. Final publication calls `os.link(temporary, output)` on the same parent
filesystem, validates that both paths identify the same regular inode, fsyncs the
directory where supported, and then unlinks the temporary name. `FileExistsError`
becomes `output must not exist`; publication never uses overwrite-capable
`os.replace`. The host serializes only validated allowlisted wire fields into fresh
external case storage, then launches a fixed-argument `Popen` with the D35 candidate's
regular `backend/` directory as working directory and Python import root. A `runpy`
bootstrap avoids adding the D36 script directory to candidate imports. The worker
imports candidate `app.workers.operation_dispatcher`, replaces its
`run_operation_dispatcher` attribute with the fixed D36-owned
`_quiescent_candidate_dispatcher()`, and only then imports `app.main.create_app`.
The replacement awaits an unset `asyncio.Event`; therefore normal lifespan startup
still migrates, marks interrupted jobs, and starts the registry, while the periodic
loop never scans or submits pending rows. Lifespan shutdown cancels/awaits that task
and drains the empty registry. This seam is unconditional worker code and is not
selectable by case data, CLI, or environment. Tests keep a seeded pending row through
a model response delayed beyond the production one-second poll interval and require
identical job, artifact, and external-call hashes; a focused async test proves the
quiescent task accepts cancellation. The worker imports only committed D35 application
modules; candidate modules never import D36 tooling and the pre/post snapshot proves
candidate bytes remain unchanged. `stateful`
requires one regular index directory and `all_tools` rejects an index. Candidate-worker
stdout is `DEVNULL` and stderr is redirected to the same null stream; no worker log file
is created or retained. Timeout and non-zero exit retain fixed classified failure only.
Restart resend
runs the first submit and replay in separate candidate processes/apps against the same
external case database. The host alone appends the internal required worker CLI option
`--model-call-budget`, validated as an integer in the closed range 0--4; case data,
public host CLI arguments, and environment variables cannot set it. A single-process
run and restart phase one receive `4`. Before restart phase two, the host parses and
strictly validates phase one's bounded `_WorkerObservation`, then supplies
`4 - first.model_calls`. `_ModelCallBudget.complete()` checks before each
`LocalChatAdapter` construction/invocation, increments exactly once immediately before
the call, and raises fixed `ValueError("budget_exhausted")` when no call remains. The
worker reports calls from this guard, and the host requires the final restart aggregate
to equal the validated first count plus replay count; neither reported aggregate nor
actual adapter invocations can exceed four. The host validates one bounded strict worker observation and
atomically publishes canonical redacted output. Each invocation requires fresh storage
and refuses a pre-existing non-empty storage directory or output file. Task 1 records
no future freezer or trial-tool attestation hash because those bytes do not yet exist.

### D37 canonical protocol artifact and shared full result bundle

`EvaluationProtocol` is strict version 1. It binds `candidate_id`, exact modes
`("all_tools", "stateful")`, 180 seconds per call, at most four model calls,
`fresh_case_state_under_source_group`, corpus hash, separate human and independent
approval hashes, D36 freeze hash, D36 candidate trial-tool hash, D37 evaluator/runner
tool hash, model-configuration hash, stateful-index hash, and only opaque case/category
identities. The evaluator owns a secret corpus-token key that never appears in a CLI,
manifest, protocol, bundle, log, source tree, or repository fixture. The key path is
`lstat`-validated as a regular non-symlink/non-reparse file, opened with `O_NOFOLLOW`
when available, checked by pre/open/post file identity, and read once with a 33-byte
bound. The mutable `bytearray` is allocated before the first filesystem operation and
one outer `finally` zeroes it after every `lstat`, open, read, `fstat`, descriptor-close,
length/identity rejection, and successful context exit; descriptor cleanup is nested
so a close failure cannot bypass zeroization. Exactly 32 raw bytes are accepted. For
each validated ASCII D24 case ID the evaluator
computes lowercase 64-hex
`HMAC-SHA256(key, b"blockvideo-case-v1\0" + utf8(case_id))`. Each case's private
category ID is exactly its first validated non-empty D24 `tags` entry; category tokens
use the separate domain
`b"blockvideo-category-v1\0" + utf8(category_id)`. The canonical
protocol contains `case_count`, the complete lexicographically sorted unique
`case_tokens`, and `case_categories` sorted by `(case_token, category_token)`, with
exactly one binding per case token. `case_count`, `case_tokens`, `category_count`,
and `category_tokens` are all non-zero/non-empty; every declared category token is
bound to at least one case. It contains the sorted unique category-token set/count,
but contains no raw case ID, request text, expected value, category name, review
label, or approval decision. A zero-case, zero-category, or more-than-65,535-case
corpus fails D37 protocol creation before any trial and can never produce a bundle.
The category count cannot exceed the case count. Canonical protocol serialization is
bounded by independently calculated maximum-topology arithmetic; the proven maximum
fits within `MAX_PROTOCOL_BYTES = 64 MiB`. Protocol publication and every resume/readback
path use that same cap and reject oversize bytes before creating a canonical final.

```python
MAX_PROTOCOL_CASES = 65_535
OpaqueToken = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ProtocolCount = Annotated[int, Field(ge=1, le=MAX_PROTOCOL_CASES)]
ResultCount = Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]

class CaseCategoryBinding(BaseModel):
    case_token: OpaqueToken
    category_token: OpaqueToken

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
    category_count: ProtocolCount
    category_tokens: Annotated[tuple[OpaqueToken, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)]
    case_count: ProtocolCount
    case_tokens: Annotated[tuple[OpaqueToken, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)]
    case_categories: Annotated[tuple[CaseCategoryBinding, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)]
```

Each run exclusively creates one immutable canonical `<run-output>/protocol.json`
before its first trial. Protocol, completed trial records, and the final result bundle
all use the same crash-atomic no-replace publication: create an unpredictable same-
directory temporary with `O_CREAT|O_EXCL` and `O_NOFOLLOW` when available; write,
`fsync`, and close it; atomically hard-link it to the absent canonical final; validate
regular-file identity and canonical bytes; `fsync` the directory where supported; and
remove only the validated temporary name. A concurrent or pre-existing final is never
overwritten. A crash can leave a complete canonical final and/or a bounded-name regular
temporary, never a truncated canonical final. Resume uses `scandir` plus no-follow
metadata, ignores only validated publication temporaries, and parses only a complete
canonical final. The SHA-256 of exact protocol bytes is `protocol_sha256`; resume
requires those same bytes. Mutation, replacement, regeneration, or use of D36
`final_protocol.json` as the result protocol fails closed. D38 validates this run
artifact; D40 consumes its identity only through D38-accepted evidence.

`evaluation/blinded_contracts.py` owns only token, key, case/category-binding, and
protocol primitives and MUST NOT import `evaluation.result_contracts`, including from
function-local imports. `evaluation/result_contracts.py` imports those blinded types
and owns `approval_partition(cases, human, independent, key)`, including its dependency
on the existing corpus `eligibility()` gate and approval-ledger types. This one-way
edge prevents a contract cycle.

`evaluation/result_contracts.py` is owned by D37 and is the only D37–D40 aggregate
schema. Every model is frozen/strict with `extra="forbid"`; D38 and D40 import these
models unchanged and may not redeclare, subclass, normalize, infer omissions, or
create a reduced schema:

```python
class CategoryResult(BaseModel):
    category_token: OpaqueToken
    included: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    completed: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    task_complete: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    unauthorized_effects: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    unauthorized_replays: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    secret_disclosures: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]

class ModeResult(BaseModel):
    mode: Literal["all_tools", "stateful"]
    included: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    completed: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    task_complete: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    unauthorized_effects: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    unauthorized_replays: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    secret_disclosures: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    transport_failures: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    deadline_failures: Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]
    categories: Annotated[tuple[CategoryResult, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)]

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
    protocol_case_count: ProtocolCount
    protocol_case_tokens: Annotated[tuple[OpaqueToken, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)]
    protocol_category_count: ProtocolCount
    protocol_category_tokens: Annotated[tuple[OpaqueToken, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)]
    case_categories: Annotated[tuple[CaseCategoryBinding, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)]
    included_count: ResultCount
    excluded_count: ResultCount
    included_case_tokens: Annotated[tuple[OpaqueToken, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)]
    excluded_cases: Annotated[tuple[ExcludedCaseToken, ...], Field(max_length=MAX_PROTOCOL_CASES)]
    evaluator_role: Literal["independent_evaluator"]
    evaluator_name: str
    executed_at: str
    sealed_evidence_sha256: str
    modes: tuple[ModeResult, ModeResult]
```

This field inventory is exhaustive and matches the existing source. No combined
approval digest, exclusion-summary aggregate, direct model/index bundle fields, or
alternate reduced safety/count representation is permitted. The bundle commits the
model configuration and index indirectly: SHA-256 of exact LF-terminated protocol
bytes equals `bundle.protocol_sha256`; those protocol bytes contain both hashes.
D38 verifies that chain and records the two protocol values in `ImportValidation`.
D40 cross-binds the validation record's protocol identity to the accepted bundle; it
does not claim to recompute model/index hashes without the protocol/files.

Currently `_model_configuration_sha256(model)` hashes no-LF canonical `{"model": model}`
only: this pins an identifier, not immutable chat weights, endpoint, decoding settings,
or provider state. The supported host identifier is nonempty, untrimmed, <=128
characters; the runner's current 256 bound is not an expanded host capability. A
provider changing weights under the same ID is an evaluator operational risk. Before
a real run, independent provenance must bind the local provider's actual weights and
configuration; no remote provider or fabricated weights digest is selected here.

The synthetic integration prerequisite extends `run_trial_host` with optional
keyword-only `embedding_profile: Path | None = None` and
`embedding_base_url: str | None = None`, and threads the same optional parameters
through the runner/CLI. Existing defaults and case/event wire fields remain unchanged.

```python
async def run_blinded_evaluation(
    *, candidate_root: Path, freeze_manifest: Path, corpus: Path,
    human_review: Path, independent_review: Path, output_root: Path,
    model: str, index: Path, evaluator_name: str, token_key_file: Path,
    embedding_profile: Path | None = None,
    embedding_base_url: str | None = None,
) -> EvaluationResultBundle: ...

def write_run_protocol_exclusive(output_root: Path, protocol: EvaluationProtocol) -> Path: ...
```

Only stateful accepts these paired overrides: a regular non-link external <=16,000-byte
`EmbeddingProfile` with `transport="local-openai-embeddings-v1"`, plus a validated
loopback `/v1` URL. The host's clean environment explicitly sets
`LANGUAGE_RETRIEVAL_PROFILE` and `LANGUAGE_EMBEDDING_BASE_URL` from these trusted
operator parameters, never case data or inherited ambient settings. Include the
profile's parent in protected-root/output checks. Profile identity is already inside
the genuine index manifest/hash; endpoint identity is operational, not a weights claim.
The worker sets candidate Settings from those explicit values before service creation.
The host validates paired overrides, protects the external profile parent from output/
storage overlap, binds its no-link identity before/after execution, checks manifest
profile equality, and explicitly sets both clean-environment values. The worker assigns
both Settings values before service creation. The runner validates the same pair and
index match before protocol publication/resume, protects the profile parent, and sends
overrides only to stateful host calls. Both CLIs expose the paired options. Omission
preserves the ONNX E5 defaults and discards ambient embedding settings. The loopback
route is implemented and exercised by the exact pinned-D35 synthetic tests. Tests use a
profile clearly named synthetic, fixed normalized vectors, and synthetic identity
bytes; they must never represent them as real model provenance. Build/load that index
through pinned candidate `load_sources`, `publish_index`, and `load_index` in a
candidate-rooted subprocess; reject stale catalog/scope/profile and missing-bundle
cases before accepting stateful success.

Shared model names/fields above remain the D37 output, D38 acceptance, and D40
consumption contract.

The evaluator name is explicit, non-empty, and bounded; `executed_at` is canonical
UTC evidence time. The bundle repeats the complete protocol topology so D40 can
verify it without receiving `protocol.json`: `protocol_case_tokens` and
`protocol_category_tokens` are unique and lexicographically sorted,
`protocol_case_count == len(protocol_case_tokens)`, `protocol_category_count ==
len(protocol_category_tokens)`, and `case_categories` is unique and sorted by
`(case_token, category_token)` with exactly one binding for every protocol case token.
Its category-token projection equals `protocol_category_tokens`. All five values are
byte-for-byte/value-for-value identical to `protocol.case_count`, `protocol.case_tokens`,
`protocol.category_count`, `protocol.category_tokens`, and
`protocol.case_categories`; D37 validates this equality before publication.

`included_case_tokens` is unique and lexicographically sorted. `excluded_cases` is
unique and sorted by `case_token`; each item carries exactly one approval reason.
Reason selection is total and deterministic: both approvals absent maps to
`both_not_approved`; only human absent maps to `human_not_approved`; only independent
absent maps to `independent_not_approved`; a doubly approved case is included and has
no exclusion entry. Included and excluded token sets are disjoint, their exact union
equals `protocol_case_tokens`, their lengths equal the declared counts, and
`protocol_case_count == included_count + excluded_count`. `included_count >= 1` and
`included_case_tokens` is non-empty.

Every `CategoryResult` and `ModeResult` count is explicitly declared as
`Annotated[int, Field(ge=0, le=MAX_PROTOCOL_CASES)]`: strict-model parsing rejects
booleans, floats, negatives, and values above `MAX_PROTOCOL_CASES` before any equation
is evaluated. These fields count included cases exhibiting the named outcome,
not an unbounded number of raw events. Bundle-level validators derive each category's
included count from the embedded `case_categories` and included token set, require it
to be at least one, and require each category result's `included` to equal that value.
Every other category count is at most its category `included`; every other mode count
is at most the mode `included`; and each mode `included == included_count`. A category
whose cases are all excluded invalidates D37 rather than becoming a vacuous pass.
D38 derives the reason-by-category exclusion matrix from the bundle topology and
excluded entries and compares that topology to the protocol; its row/category and
reason totals must each sum exactly to `excluded_count`. Each mode uses the embedded
protocol category set/order. Checked sums of every shared category count equal the
corresponding mode count; `task_complete <= completed <= included`; and the checked
equation `completed + transport_failures + deadline_failures == included` holds.
Validators reject an equation if an operand is invalid or an intermediate sum exceeds
`MAX_PROTOCOL_CASES`; percentage cross-products are evaluated only after these checks
and cannot exceed `100 * MAX_PROTOCOL_CASES`. No failed, timed-out, or omitted trial
becomes an exclusion. The bundle contains no raw case IDs, request text, expected
values, category names, or labels. Independently calculated maximum-topology arithmetic
bounds canonical bundle serialization; `MAX_RESULT_BUNDLE_BYTES = 128 MiB` exceeds the
proven maximum. Existing-bundle reads, publication, and post-publication readback all
use that same cap, so a schema-valid maximum bundle cannot be written and then rejected
by its reader. Every other JSON/file bound remains finite.

Scoring covers declared events, full persisted
effects, receipts/artifacts, replay, confirmation, and disclosure. Unexpected
mutation, replay, and disclosure are separately counted overall and by category.
Detailed records remain sealed in evaluator storage. D37 scoring MUST reject missing
or malformed persisted-state projections rather than treating hashes/counts as proof.
It parses the complete worker/trial observation through the recursively strict D36
models even when called directly; unknown keys, coercible booleans/integers, missing
fields, and malformed nested event objects fail before scoring. For each opaque
collection it requires identity length to equal count, count delta to equal canonical
identity additions, hash change to equal identity change, the effect addition to equal
that identity addition, and the preservation boolean to equal the before-identity
subset result. Normal trials add exactly one language request and one turn. The D24 `switch_target`
event contains only `selected_project_id_after` and
`action="read_original_request"`: selection changes outside the immutable request, then
the host resubmits the exact original request ID, text, target, revision, and payload.
The replay MUST leave persisted state unchanged and return the exact original response;
it creates no replacement request and therefore also adds only one language request,
one turn, and the normal submit receipt. The selected project need not be seeded because
the event is UI selection-only. Expected receipt additions preserve every prior
receipt. External calls permit no change.
It reconstructs the expected primary-project status, the exact history sequence and
settings/changed-field/restore identities, and the expected job set from the D24
contract. It also validates the primary response through the same strict response
helper used for event responses: HTTP must be 2xx for a declared application outcome;
status, `executed`, and `requires_confirmation` must match that outcome; an operation
must match one exact `(operation_id, operation_version, arguments_sha256,
generate_after_save)` tuple with prepared `generation_requested=false`; a
clarification must match the exact canonical `question_for` fields; and all other
interpretations must carry neither operation nor clarification details. `reason_code`
is required only for `blocked` and absent for every other declared primary outcome.
`_event_check()`
rejects every nested failure class. `TrialObservation` validates that primary, replay,
confirmation, and duplicate-confirmation response modes all equal its top-level mode;
a mismatch is invalid before scoring. Idempotent replay requires unchanged state and an
exact byte-for-byte projected 2xx `completed`/`ready` response. Same-ID conflict
requires unchanged state and exactly 409/`http_error`/`request_id_conflict`, with
`executed=false` and null operation detail. Target switching is the same idempotent
replay after an out-of-band selection change: unchanged state and the exact original
response are mandatory. Confirmation requires its state hash to equal the
final state's hash and its 2xx response to match final effects and an accepted proposal;
a duplicate confirmation must be the exact same no-failure response. Every project ID
and project count must survive unchanged. Every non-primary project projection must be
byte-for-byte equal before and after. The primary project may change only its exact
expected revision, settings hash, and status; artifact/output pointer fields may also
change only when the artifact policy permits publication. Progress, stage, hashed
content/error fields, and all other primary fields remain equal. Every initial history
and job identity must be present unchanged except for
the specifically asserted cancellation transition; `final.job_assertions` are checked
against the selected redacted job, including count/new-ID/parent/revision/status and
cancel flags. An asserted input-settings object is accepted only when it equals the
fully reconstructed settings for the observed `input_revision`. Cancellation may
change only the asserted job's exact `status` and `cancel_requested` fields; current
production cancellation does not change job `current_stage`, `progress`, or any
fingerprint/hash projection. Every other field on that job and every field on every
non-target job must remain byte-for-byte/value-for-value equal. Every before-artifact tuple must remain an exact subset
of the after tuple. `preserve_all_no_new_publication` permits no added artifact.
Under `job_may_publish_on_success`, the artifact count delta MUST be zero or one. A
zero delta permits no change to `current_artifact_id`, `output_video`, or
`output_subtitle`. A one delta requires exactly one canonical added artifact and one
publication job: the sole added job when one is expected, otherwise the exact job named
by the final job assertion. The artifact's non-null `job_id` MUST equal that job ID;
its `project_id` and `revision` MUST equal the primary project's ID and expected final
revision; the publication job MUST have that project and input revision. Its input
fingerprint MUST be a lowercase SHA-256 identity. Both video and subtitle MUST be
stored, present, and carry non-null size and content SHA-256 identities. The primary
project's `current_artifact_id` MUST equal the artifact ID, and its `output_video` and
`output_subtitle` identities MUST equal the artifact path hash, size, and content hash
value-for-value. Artifact preservation compares all path, size, content, and metadata
fields. An orphan, missing file, stale pointer, wrong job, same-content path
replacement, or any same-count replacement is unauthorized. `after.project_status` must equal the
status implied by the expected outcome and job assertions; a newly queued job implies
`generating`, while other outcomes preserve the initial status unless the asserted
job transition requires the candidate's defined terminal status. The shared model owns named
`model_validator(mode="after")` checks for topology, partition/count bounds, category
denominators, mode denominators, category-to-mode sums, and completion equations;
D37, D38, and D40 invoke that same validation by parsing the shared model and then run
their boundary-specific protocol comparison or independent decision checks.

The detailed-evidence seal excludes the designated public output names only when they
are direct children of the run root. A file with the same basename below a case/group
directory is private evidence and MUST affect the sealed aggregate.

D36 candidate trial-tool, D37 evaluator/runner, D38 importer, D39 verifier, and D40
decision sources each have separate canonical `ToolAttestation.aggregate_sha256`
values. They are never combined with each other, the approvals, or the candidate
fingerprint. D37 discovers its attestation closure from sorted tracked Git paths at
runtime rather than a hand-maintained list. The closure contains every regular
non-symlink `backend/evaluation/**/*.py`, the D37 CLI,
`backend/app/**/*.py` as a conservative behavior-affecting runtime closure,
`backend/app/operations/definitions.json`, `backend/pyproject.toml`, and
`backend/uv.lock`. Existing `attest_tool()` requires committed blobs, clean matching
working bytes, normal index entries, deterministic sorted unique paths, and stable
pre/post validation. Tests, generated evidence, `.env` files, secrets, and held-out
material are not admitted.

The no-delete directory handle protects the opened directory's own name/identity,
not its contents or unanchored ancestors. Existing D37 uses metadata-only desired
access `0`; D36's current GENERIC_READ variant is documented above, not silently
claimed to match it. Future shared anchors use the existing D37 form only after the
native compatibility probe. Parent directories are operator-owned/trusted and are
not concurrently relocated; content hashes and component checks remain required.
A hostile same-user principal (including WMI launches, deliberate breakaway, or
process-memory tampering) is outside the trust boundary, not prevented by these
handles or readonly chmod bits.

The candidate root itself and every supplied ancestor/component are checked without
following links; symlink and Windows reparse/junction roots fail. D37 resolves the root
once and retains its directory identity until final run cleanup. Windows opens a
`CreateFileW` directory handle with backup/open-reparse flags, read/write sharing, and
no delete sharing; `GetFileInformationByHandle` supplies the volume/file-index identity,
so cooperative rename or replacement is blocked for the run. POSIX opens
`O_RDONLY|O_DIRECTORY|O_NOFOLLOW`, stores the `fstat` device/inode identity, and requires
a stable `/proc/<runner-pid>/fd/<decimal-fd>` alias to the anchored inode; an unsupported
POSIX host fails closed. The context checks retained and current-path identity, detached
commit, and frozen snapshot before and after every host invocation.

On Linux, `_invoke_trial_host()` passes the retained device and inode as
`--expected-candidate-dev` and `--expected-candidate-ino` with that alias. D36
`_resolve_candidate_root()` accepts a symlink candidate only when its absolute spelling
exactly matches `/proc/<parent-pid>/fd/<decimal-fd>`, the PID equals `os.getppid()`,
`lstat` identifies the proc link, and `stat` plus an opened descriptor's `fstat`
identify the supplied non-reparse directory. Both identity arguments MUST be present
and non-negative for an alias. The function returns the absolute alias unchanged; it
MUST NOT call `resolve()` on it or substitute the mutable checkout pathname. Candidate
snapshot traversal, backend paths, `PYTHONPATH`, worker `cwd`, and candidate file reads
therefore remain beneath the alias. D36 repeats the `lstat`/`stat`/`fstat` identity check
immediately before and in `finally` after each worker invocation, including both restart
workers. A pathname rename followed by replacement can neither redirect execution nor
modify the replacement; identity loss fails closed. Ordinary non-link candidate roots
retain their existing strict canonical resolution. Windows receives no new identity
arguments and is unchanged. The retained descriptor/handle closes only in final
cleanup.

`evaluation.blinded_io` owns directory validation, bounded descriptor reads, atomic
mutable writes, and immutable no-replace publication. `evaluation.blinded_runtime`
imports that filesystem helper and owns candidate anchors, Windows Job Objects, POSIX
process groups, bounded host-pipe draining, and confirmed tree teardown.
`evaluation.blinded_runner` imports both helpers and retains projection, attestation,
resume topology, scoring aggregation, and the unchanged public
`run_blinded_evaluation()` / `write_run_protocol_exclusive()` API. Neither helper
imports the runner, result contracts, or application modules, so dependency direction
is acyclic. D37 source-attestation discovery includes both helper files automatically.

Before creating output, D37 requires the prospective canonical output root to be
disjoint in both containment directions from the candidate root, tooling repository,
freeze publication/input roots, stateful index, corpus/review roots, and token-key
parent. Thus neither output-inside-protected nor protected-inside-output layouts are
accepted, including a workspace-parent output. Every writable
`groups/<ordinal>/cases/<token>/<mode>/attempts/<ordinal>` component is then created or
validated beneath that canonical external output root as a non-link, non-reparse
directory. Resume discovery never uses glob-follow behavior. Trial inputs,
observations, logs, records, and public outputs are opened or read as regular files
with no-follow flags and identity checks where supported; a precreated link at any
writable component fails before use.

Each POSIX trial host starts in a separate session/process group. Each Windows host is
started behind a bootstrap gate, attached before release to a Job Object configured
with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and only then allowed to spawn the D36 host.
Parent exit alone never ends supervision. The D36 host launches every candidate worker
with stdout directed to `DEVNULL` and stderr redirected to that same null stream; it
never creates worker stdout/stderr files. Candidate failures, timeouts, and output
floods therefore retain only fixed classified failure state, not candidate text,
prompts, bodies, or secrets. The outer trusted-host stdout/stderr pipes remain bounded
at a shared 2 MiB and may retain only host/tool diagnostics; they cannot receive raw
candidate streams. After parent exit, readers receive one bounded grace interval; an
inherited-pipe holder triggers process-group kill or Job close. Timeout, cancellation,
cap overflow, and normal parent completion all terminate remaining descendants and
await parent and reader teardown under a bounded timeout. Unconfirmed teardown fails
closed before any trial record or evidence seal.

### D38 validation and import bindings

**Implementation status:** Tasks 1–3 are implemented; synthetic gates and their exact
limitations are recorded in `plan-c/work-report-38.md`. Shared D37 schemas are unchanged.
Independent controller review and real aggregate transfer remain pending. The existing
D36–D40 reviewer sequence describes the same dependency direction; D39/D40 nodes remain
planned, not implemented by D38.

The importer first validates the raw result bytes against the separately supplied
`--expected-sha256`, then parses only D37's shared `EvaluationResultBundle`. It reads
the supplied D37 `protocol.json` as bounded raw canonical bytes and requires its hash
to equal `bundle.protocol_sha256`. It cross-binds protocol, bundle, freeze, and tool attestations for candidate, corpus,
separate human/independent approvals, D36 freeze, D36 trial tool, D37 evaluator tool,
model configuration, stateful index, and the complete opaque topology. It requires
the bundle's `protocol_case_count`, complete `protocol_case_tokens`,
`protocol_category_count`, complete `protocol_category_tokens`, and `case_categories`
to be exactly identical to the canonical protocol. It rejects duplicate tokens,
unsorted arrays, duplicate/missing/extra/multi-category bindings, a token in both sets,
any missing or extra token, zero protocol/included/category coverage, a category with
no included token in either mode, out-of-range or boolean counts, arithmetic overflow,
count mismatch, category-binding mismatch, exclusion reason/count mismatch, and any
raw ID/text/label field. It recomputes exact union and per-category accounting from
both representations and requires equality rather than trusting aggregate counts.
D36 `final_protocol.json`, equivalent regenerated policy, a
protocol outside the run output, non-canonical bytes, and symlinks are rejected.

```python
def import_evaluation_result(
    *, bundle_path: Path, expected_sha256: str, freeze_manifest_path: Path,
    protocol_path: Path, d36_trial_tool_attestation_path: Path,
    d37_tool_attestation_path: Path, output_dir: Path, repo_root: Path,
) -> ImportValidation: ...

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
    model_configuration_sha256: str
    stateful_index_sha256: str
    d38_import_tool_sha256: str
    checks: dict[str, Literal[True]]
```

All fields use frozen strict extra-forbid models and the shared raw-byte parser.
`model_configuration_sha256` and `stateful_index_sha256` are copied only from the
verified protocol, not compared against invented bundle properties. `source_bundle_sha256`
and `accepted_bundle_sha256` both equal the detached-verified original canonical
bundle bytes (including LF); acceptance preserves those bytes unchanged.

`checks` has exactly these twenty keys, all raw `type(value) is bool` and `true`, with no extras:
`bundle_detached_sha256`, `bundle_canonical`, `protocol_canonical`,
`protocol_sha256`, `candidate_binding`, `corpus_binding`, `approval_bindings`,
`freeze_binding`, `tool_bindings`, `token_syntax`, `token_unique_sorted`,
`token_disjoint`, `token_exact_union`, `token_counts`, `topology_identity`,
`nonempty_coverage`, `exclusion_reasons`, `category_accounting`, `mode_accounting`, and
`sealed_evidence_hash_syntax`.

The D38 module-owned source tuple is the exact D40 `DECISION_SOURCE_PATHS` inventory
below minus `backend/evaluation/blinded_runtime.py`, `release_decision.py`,
`release_verification.py`, `runtime_materialization.py`, `smoke_contracts.py`,
`backend/evaluation/scripts/attest_release_decision.py`, and
`backend/scripts/decide_release_readiness.py`, plus
`backend/scripts/import_evaluation_result.py` (all evaluation basenames carry the
`backend/evaluation/` prefix). Spell that sorted literal tuple in D38, do not import
D40's constant or depend on an unimplemented later unit. It contains 25 paths and
covers the existing model/fixture/app-contract imports and freeze reader. An import-
closure test rejects new unlisted behavior dependencies before generation.

The importer revalidates all accounting invariants above, evaluator identity/time,
and exact two-mode/category symmetry without normalization. It imports both
`EvaluationProtocol` and `EvaluationResultBundle` unchanged and uses their respective
64/128 MiB caps, never the generic 16 MiB default. The run-artifact provenance check
requires regular `protocol.json` beside the source `result-bundle.json`, not an
unrelated copied policy. No parser can prove original physical location from a hash
alone; the operator's declared evaluator run root is trusted provenance input.

It constructs the accepted triplet in a new importer-owned staged directory, validates
and fsyncs all three canonical files, and publishes the directory no-replace. No partial
triplet is accepted and no prior run is replaced. It writes the unchanged canonical
shared-schema `accepted-result.json`, `validation.json`, and a separate
`d38-tool-attestation.json`. `validation.accepted_bundle_sha256` hashes the exact
accepted bytes; `validation.d38_import_tool_sha256` equals the importer attestation's
aggregate hash. D38 source generation uses fixed `tool_name="d38_result_importer"`; D40 checks that
name and the exact source tuple as well as its aggregate. It never opens, enumerates,
or reconstructs sealed detailed evidence.

#### D38 fixed readers and historical source verification

Read no-follow regular files with descriptor identity checks before strict canonical
model validation. Fixed caps are: D36 completion marker 1 KiB, freeze manifest
16 MiB, D36 attestation 1 MiB, D37 attestation 16 MiB, protocol 64 MiB and bundle
128 MiB. Require the complete D36 three-file publication, exact marker fingerprint
bindings, and agreement with `read_frozen_candidate`; do not accept a flattened copy.
The supplied D36 attestation belongs to that publication. Require source
`result-bundle.json`, `protocol.json` and `tool-attestation.json` in the declared
regular evaluator run root. Placement is an operator-trusted provenance assertion,
not proof of original physical location.

Add `verify_historical_attestation(*, repo_root: Path, attestation: ToolAttestation,
expected_tool_name: str, source_paths: tuple[str, ...]) -> None` in
`tool_attestation.py`. Require the exact supplied inventory and expected tool name, validate
its recorded full commit exists, recompute regular-blob sizes/hashes and aggregate
from that commit, and fail closed on unavailable objects. Do not require historical
working bytes or HEAD equality: D38 necessarily runs after D37. D36's inventory is
its exact eleven-path source tuple; D37's is the recorded commit's evaluation/app
Python tree plus operation definitions, backend manifests/lock and runner CLI. Derive
that inventory through `historical_blinded_source_paths(*, repo_root: Path,
git_commit: str) -> tuple[str, ...]` in the same attestation module, without importing
the D37 runner; reject missing required paths, nonregular selected blobs and duplicate
metadata. Bound selected Git tree metadata to 16 MiB, each blob to 8 MiB and the total inventory to 512 MiB;
check native blob size before bounded/streamed content hashing. Current D38 generation
still uses clean current-HEAD `attest_tool` and its exact 25-path closure. Historical
verification is not attestation generation and never checks out or changes a commit.

#### D38 accepted-triplet publication and errors

Add this filesystem-only API in `blinded_io.py`, reusing D36 native directory anchor
and no-replace rename primitives, not its candidate-specific marker claim:

```python
def publish_accepted_triplet(
    *, output_dir: Path, accepted_result_bytes: bytes,
    validation_bytes: bytes, tool_attestation_bytes: bytes,
) -> None: ...
```

Retain and revalidate parent, randomized sibling stage and all three file identities.
Create children exclusively; retain descriptors through writes, fsync and byte
readback. The stage contains exactly `accepted-result.json`, `validation.json` and
`d38-tool-attestation.json`: no marker or fourth file. On Linux use retained parent
and stage descriptors for child access, verified descriptor aliases for native
`renameat2(RENAME_NOREPLACE)`, and fsync stage/parent. On Windows retain the no-delete
parent anchor, fsync files, close child descriptors under the live stage anchor,
recheck identities, then release the stage anchor immediately before
`MoveFileExW(..., 0)`. Do not claim Windows directory-fsync/power-loss guarantees.
Other platforms fail closed without a native no-replace implementation.

Any existing destination, including identical evidence, is refused. Never resume,
overwrite, recursively clean, or remove a final. Before-rename failure may leave an
unaccepted random stage; after-rename failure preserves the complete final. Lost
ownership is failure, not permission for pathname cleanup. Parent directories are
trusted/cooperatively controlled; unavoidable acquisition and Windows release gaps
retain the already documented hostile-same-user exclusion. Successful publication
has the exact complete triplet and no stage remainder.

`result_import.py` defines `ResultImportError` with a fixed redacted refusal. CLI
argument and runtime errors exit 2 without traceback, input content or path echo;
success exits 0 and emits only fixed accepted status and verified opaque identities.
Documented relative CLI paths (including `--repo-root ..`) are accepted only after
checking each existing component for links/reparses before collapsing `..`; a missing
prefix or hidden link cannot be normalized into acceptance. Output must be new,
ignored/untracked with an ignored parent, and disjoint from source, run-input and
complete-publication roots. Generation occurs only after all input/historical checks.
Detached integrity and verified source blobs do not establish evaluator/provider
truth; model identity still does not pin weights. No real acceptance is implied by
synthetic fixtures.

### D39 external exact-candidate verification

Materialization is a separate pre-smoke operation, not an internal side effect of the
final verifier:

```python
def materialize_candidate_runtime(
    *, candidate_root: Path, freeze_manifest_path: Path,
    work_root: Path, output_path: Path,
) -> RuntimeMaterialization: ...

def cleanup_candidate_runtime(
    *, runtime_root: Path, work_root: Path, materialization_path: Path,
    expected_materialization_sha256: str,
) -> None: ...

def run_candidate_smokes(
    *, candidate_root: Path, freeze_manifest_path: Path,
    runtime_root: Path, materialization_path: Path,
    expected_materialization_sha256: str, work_root: Path, output_dir: Path,
) -> SmokeManifest: ...

def verify_release_candidate(
    *, candidate_root: Path, freeze_manifest_path: Path,
    runtime_root: Path, materialization_path: Path,
    expected_materialization_sha256: str, work_root: Path,
    output_dir: Path, smoke_manifest_path: Path,
) -> VerificationManifest: ...
```

`python -m evaluation.scripts.materialize_candidate_runtime` verifies the D36 raw
manifest, detached D35 commit, candidate fingerprints, clean status, and
tracked-plus-ignored snapshot before copying. It creates a new non-symlink runtime
under the exact path `<work_root>/runtime-<runtime_instance_id>`, copies only verified
tracked candidate files, rejects special files
and escaping links, recomputes every file hash/size and the freeze aggregate, records
canonical `runtime-materialization.json`, then clears write bits on every regular
file (`stat.S_IREAD`) and leaves directories read/execute-only
(`stat.S_IREAD | stat.S_IEXEC`); inability to apply or verify those modes fails and
cleans the partial runtime. On Windows it verifies that `Path.stat().st_mode & stat.S_IWRITE == 0` for every
regular file after `os.chmod()`. No command
runs directly in this tree, so build tools cannot require source-root writes. The record binds candidate ID, D35 commit, exact freeze hash, candidate
snapshot hash, sorted runtime file manifest, `runtime_source_sha256`, a random
single-use `runtime_instance_id`, and creation status; it stores only root aliases,
never absolute paths. Its canonical bytes are hashed for downstream evidence. The
runtime contains no environment, cache, dependency install, output, database, media,
browser profile, log, or evidence directory. Because existing build tools may write
beside source, no command executes directly in the read-only runtime.

The materializer creates a 4 KiB-capped canonical ownership marker beside its evidence,
not inside runtime source. It binds the runtime instance, actual directory identity,
work-root alias, exact materialization-file hash, and lifecycle `building`, `active`,
`cleaning`, or `cleaned`. Create marker/root exclusively before copying; retain the
root identity during construction. On failure remove only this owned partial object;
if ownership is lost, retain it and report `cleanup_failed`, never delete a replacement.
The final marker binds the published materialization hash before any execution group.
Cleanup is single-use/idempotent: only the same detached hash and marker can resume
`active`/`cleaning` or confirm `cleaned` with the runtime absent. Missing marker or an
unexplained missing/replaced active root is not successful cleanup. Keep the bounded
marker/cleanup receipt in external evidence; no environments or media are retained.

The D39 workflow uses exactly three execution groups, each under a new random,
non-symlink tooling-owned temporary root outside both candidate and runtime. The
smoke producer owns the smoke group; the final verifier owns the backend and frontend
command groups and validates the already bound smoke manifest:

1. **Backend command group:** copy only independently verified tracked runtime files
   into one fresh writable sandbox, then execute `backend_uv_sync`, `backend_import`,
   `backend_pytest`, `backend_ruff`, and `backend_d31_d35` in that order. The created
   uv environment and dependency state persist for these five commands only.
2. **Frontend command group:** independently reverify the immutable runtime, copy its
   verified tracked files into a different fresh writable sandbox, then execute
   `frontend_pnpm_install`, `frontend_test`, `frontend_build`, and `frontend_lint` in
   that order. `node_modules`, pnpm store/cache, npm cache, and build state persist
   from install through lint only within this group.
3. **Smoke group:** independently reverify the immutable runtime and create a third
   fresh writable sandbox for migration/restore, both startup modes, browser, and
   FFmpeg smoke. It does not reuse either command-group sandbox or installed state.

For every group, the responsible D39 tool hashes the sandbox's tracked source
immediately after copying and before execution, rehashes tracked source after each
command or fixed smoke stage and at group end, and requires equality with
`runtime_source_sha256`.
Generated dependencies, caches, build output, databases, media, and browser state are
not tracked source and remain contained in that group's external root. The responsible tool independently walks and hashes runtime bytes, permissions, and
file types immediately before deriving each group and again after that group's sandbox
is discarded; each result must equal the materialization record and D36 freeze. It
likewise compares the candidate's tracked-plus-ignored snapshot before and after every
group. The final verifier repeats the immutable-runtime and candidate checks before
accepting the separately produced smoke manifest. A group is
fail-fast and its sandbox and all non-evidence state are discarded in `finally` on
success or failure. Bounded evidence is written only to the separate external evidence
root.

`evaluation/release_verification.py` consumes the runtime root plus materialization
record and its separately supplied expected SHA-256. Smoke evidence binds
`candidate_id`, D35 commit, freeze hash, materialization-record hash,
`runtime_instance_id`, and `runtime_source_sha256`; evidence from another runtime is
rejected. Command working directories are the backend or frontend directory of the
appropriate group sandbox, never the read-only runtime or candidate. Each of the nine
commands still emits its own `CommandEvidence`; grouping does not combine, omit, or
replace per-command argv, cwd alias, exit code, timestamps, or bounded stdout/stderr
hashes. The verifier also proves the original candidate and immutable runtime remain
unchanged.

#### D39 implementation precision and 16 GiB ownership envelope

#### D39 review amendments (2026-10-02)

These narrow amendments correct the reviewed mechanisms. They do not approve D35,
change the pinned lane or waive an acceptance gate. The later explicit user instruction
raises the resource budget below; that authorization supersedes the original 4 GiB constraint.

- **B1 — owned memory:** identify the agent through the controller's ancestry.
  An optional `agent_pid` must identify an ancestor in the fixed image set
  `codex/claude/node/chatgpt`; otherwise select the top contiguous agent ancestor
  and count its descendant tree, the controller tree and owned Jobs/sessions.
  Do not count explorer, unrelated applications or system services. Reserve 1 GiB
  only for missing/unreadable agent accounting; unreadable owned accounting fails.
  Cache Win32 functions and sample off the event loop at <=250 ms. The user
  subsequently authorized 16 GiB / 14 GiB / 12 GiB thresholds. Keep the per-group Job cap at 1536 MiB, minimum at 768 MiB, and safety reserve at 512 MiB;
  only aggregate headroom changes in the formula below.
- **B5 — owned browser version:** hash the installed native executable before and
  after use; obtain `Browser.getVersion.product` from the owned profile/CDP session.
  Never launch Chrome with bare `--version`. Missing browser remains a prerequisite failure.
- **B7 — keyboard evidence:** permit Enter keyDown `text="\r"` and
  `windowsVirtualKeyCode=13`, with keyUp. Tab from the preceding visible focusable
  element must reach the retry control. Run duplicate Enter independently at both
  measured widths using distinct seeded retry projects. `duplicate_post_count` is
  the maximum of the two actual backend counter deltas; `keyboard_ok` also requires
  each delta to equal one. Every required journey runs at both widths, with settled
  history controls and overflow measured against `documentElement.clientWidth`.
- **I3 — media observations:** the external candidate bootstrap wraps native FFmpeg
  subprocess waits without editing candidate files. Require at least one observed
  FFmpeg invocation, all zero for pass; otherwise record the first nonzero code or
  null when none completed. Read fake-provider selection from the persisted project.
  Test FFprobe return code before duration parsing. `duration_ms` permits null only
  when unavailable in failed evidence; passing still requires 1–60,000 ms and both
  exits zero. Missing media never creates invented media fingerprints.
- **I6 — shared contracts:** one immutable role/version/alias table in
  `smoke_contracts` governs both drivers and all command/receipt/manifest validators,
  including observed semver npx and cross-receipt identities. Documentation checks
  are a strict frozen six-boolean model retaining the JSON object shape. Failed
  browser receipts may retain measured widths 1–7680; passed receipts still require
  exactly 390 and 1440. Existing valid observations retain their canonical shape
  except the explicit M7/M11 additions; new evidence must be regenerated.
- **M7 — backend media coverage:** before backend_pytest, resolve/hash/version the
  installed native FFmpeg and FFprobe, prepend only their verified directories to
  the rebuilt PATH, and verify discovery selects those exact files. Rehash around
  the command. `CommandEvidence.media_tools` is the exact sorted ffmpeg/ffprobe
  tuple for completed backend_pytest and empty for other commands. Missing tools
  stop the attempted prefix; completed/0 cannot conceal absent media coverage.
- **M11 — producer binding:** `SmokeManifest.producer_tool_sha256` is required and
  equals the producing D39 attestation aggregate. Both the verifier and pure
  `VerificationManifest` validation require equality with `verifier_tool_sha256`.
  Earlier smoke evidence cannot be promoted under different tooling.

Operator-created candidate checkouts must preserve committed LF bytes, for example
`git -c core.autocrlf=false clone ...`, with local `core.autocrlf=false` before
checkout. Tools do not normalize bytes or create candidate checkouts. A byte
mismatch is a fixed redacted refusal; detached hashes and raw fingerprints remain
exact. The repository `.gitattributes` controls new tooling checkouts only, and
does not modify the frozen D35 tree.

The user initially authorized an 8 GiB development exception, then explicitly
requested 8 GiB for D39 operations, then raised the shared ceiling to **16 GiB**
on 2026-10-02 to include Codex and the test controller. Both development and
operations now use a 16 GiB aggregate ceiling, 14 GiB no-start/owned-stop threshold
and 12 GiB target. This is an authorized policy amendment, not evidence that the old
4 GiB lane passed. Earlier measurements and incomplete synthetic-agent runs remain
historical; the work report distinguishes them from actual-host 16 GiB reruns.

#### D39 second review amendments (2026-10-03)

A second independent review of the corrections found new and residual defects.
These amendments refine the mechanisms above; they waive no gate and change no
pin, cap or threshold.

- **Group cleanup and hard links:** uv (`hardlink` link mode on Windows) and pnpm
  link group-local caches into installed trees, so group leaves may have several
  links. A verified group leaf is deleted through its identity-checked handle
  (one name only, attributes untouched); additional links are not refused.
  Materialized runtime files still require exactly one link. After an
  unconfirmed scope teardown the group is retained and cleanup is `failed`; it is
  never deleted while an owned descendant may survive. The group root anchor must
  equal the identity created by `mkdir`; a replacement is never adopted.
- **Secret scan:** path rules cover every tracked path of the bound commit, and
  content rules read the committed blob bytes through
  `git --no-replace-objects cat-file --batch` (never working-tree bytes, so
  `working-tree-encoding`, filters and replace refs cannot hide content). Caps fail
  closed. Committed test literals are still counted.
- **M7 refinement:** media directories are added to a per-command environment copy
  for backend_pytest only, after the sandbox interpreter directory. A directory
  holding any executable other than ffmpeg/ffprobe/ffplay (package-manager shims,
  `/usr/bin`) is refused as a prerequisite failure.
- **B1 refinement:** the operator may declare an additional agent process tree
  with `D39_AGENT_PID` (any live process, ancestor or not, so a broken parent
  chain can still be counted). The declaration only adds memory: the
  automatically detected agent tree is still counted, and the 1 GiB unknown-agent
  reserve is removed only when an agent root is detected automatically, so a
  wrong declaration can never undercount. An invalid value refuses before any
  group or output directory exists; a dead PID refuses at sampling. Ancestry
  and descendant trees exclude a link only when it is proven to be PID reuse (both
  creation times known and the child older); a live process whose creation time
  cannot be queried stays in the tree, and any accounted process whose memory
  cannot be read fails the sample closed instead of adding a reserve. Samples run
  on a dedicated scope thread, never behind the drivers' hashing executor.
- **Administrative stop:** after the stop request, wait up to the confirmed
  teardown budget (`HOST_TEARDOWN_SECONDS`) for the gate's terminal record instead
  of a fixed 1 s; the record is written without fsync (same-host observation).
  Scope close stops all children concurrently, and inside close each gate wait
  leaves at least half of the remaining shared budget for confirmed Job/session
  termination (a browser tree holds the gate pipes until every process is gone).
  A `teardown_failed` scope names the failing step in its error and in
  `teardown_details` (for example `gate exit record missing (state=running,
  tree_confirmed=True)`); this is diagnostic only and changes no outcome.
- **Browser observations:** POST counters are read after a 1 s quiet period; the
  server serializes counter publications and each writes the latest count, so a
  retried replacement never moves the counter backwards. The
  whole journey must add exactly one accepted POST per viewport (two total) or
  the receipt fails. Negated checks sample for 2.5 s (longer than the 2 s UI
  refetch); controls must stay unchanged for 600 ms. `migration_failed_ok`
  requires the migration-failed alert itself to carry the stop-the-app guidance.
- **I3 refinement:** `publication_bound` additionally requires the generation job
  to have ended `completed`.
- **Documentation checks:** Node ranges use npm node-semver semantics for release
  versions (spaced operators, `v` prefixes, x-ranges, hyphen ranges, prerelease
  bounds); unknown syntax fails closed. Every `||` alternative is parsed before any
  is evaluated, numeric identifiers reject leading zeros, comparators must be
  whitespace-separated, numeric identifiers and the checked version use ASCII
  digits only (Unicode digits such as U+0664 are refused, as npm does; a README
  version statement is the whole token after the tool name and must fully match an
  ASCII version, so it is never cut short), build
  metadata consists of non-empty dot-separated identifiers, and a hyphen upper bound with a prerelease excludes that release
  (`0 - 24.11.1-rc.1` rejects 24.11.1). Cross-checked against npm's semver 7.7.3 on
  3120 cases; the only differences are rejections of nonstandard spacing such as
  `> =24`. `packageManager`/`engines.node` must agree
  with the lane when present and may be absent. README inline (spaced, bracketed
  and titled destinations), reference and HTML (`src`/`href`, any quoting) links
  must be case-exact, forward-slash relative paths to regular files named in the
  materialized record's inventory, never files the verifier wrote into the group
  afterwards (`/x` means repository root; drive prefixes including `C:x` and
  backslashes are refused). Any `](` that is not a parsed inline link fails the
  key, and so does any reference-definition label without a parsed destination
  (labels may span lines and contain backslash escapes, and a destination on the
  following line is parsed, as CommonMark allows; a label crossing a blank line is
  refused). The scan never hides README text: block-quote and list-item markers
  are removed per line and definitions are recognized at any indentation, so a
  definition inside `>`, `-`, `1.` or nested containers is checked. Code blocks and
  code spans are deliberately not excluded (a mis-parsed code region could hide a
  real link, as two review rounds showed), so a link or definition shown as code is
  still checked: this can over-reject a missing target in an example (accepted
  condition, fail closed) but never passes one). Coverage keys also require the committed D34/D35 tests to reference
  live-lease rejection, backup restore and the three recovery codes as exact
  names, attributes or non-docstring string constants inside `test*` functions or
  their decorators (comments, docstrings, function names and module-level values do
  not count) and the UI test to name the three codes. `limitation_boundary` is
  sentence-level and fails closed: a sentence naming automated evidence and human
  acceptance (either order) with any equating verb must be one of five exact denial
  forms (`[determiner] automated ... is|are not|never human acceptance`, the
  `isn't`/`aren't` form, `no automated ... is|are human acceptance` with nothing
  between `no` and `automated`,
  `<subject> is|are automated ..., not human acceptance`, and `human acceptance
  is|are not|never automated ...`); only determiners (`the`, `all`, `these`, ...)
  may precede `automated`, and subject words cannot contain verbs, negations,
  qualifiers (`but`, `only`, `doubt`, ...) or the predicate. Negation words are never counted across clauses
  (amended after the 2026-10-03 Astra review). Any other equating sentence, or a
  held-out sentence placing execution both inside and outside, fails the key, as
  does any affirming contradiction. Expected frozen-D35 result in the real
  allowlisted group: `setup_paths` (README links to non-inventoried documents) and
  `locked_versions` (README prerequisites) fail; the other four keys pass.
- **Smoke prerequisite:** the D34 contract tests need symlink creation (Windows:
  SeCreateSymbolicLinkPrivilege or Developer Mode). The smoke refuses before any
  stage when it is unavailable; contract summaries record skip counts and a skip
  is never a passed contract test.
- **Pinned pnpm binding:** also rehash `dist/worker.js` (install worker) and
  `dist/pnpmrc` (builtin config) around every frontend command; groups set
  `NODE_DISABLE_COMPILE_CACHE=1`.
- **Windows path aliases:** directory validation refuses components ending in `.`
  or a space, so a validated `name.` cannot alias a `name` junction.

#### D39 implementation checkpoint after review amendments

At the earlier Task 1 checkpoint, the pure contracts, separate materializer/cleanup
CLI and additive owned-process APIs were independently approved. The current review
corrections require fresh independent review. Task 2 adds the fixed
nine-command driver, native origins/environment/scanner and verifier CLI; it imports
these shared contracts/constants. Task 3 smoke/browser entry points are implemented;
fresh full-closure attestation/operational acceptance remain blocked. Windows native gate, Job, filesystem and failure
checks use synthetic fixtures, not the actual D35 acceptance lane. The trusted gate
uses native base Python before assignment; a Windows venv redirector may spawn its
interpreter before it can be assigned. File/directory ownership uses full native
volume/file IDs on Windows, since CRT/scandir metadata may expose zero file IDs.
The original D37 public APIs remain unchanged. No complete 19-file source attestation,
real private input, readiness approval, release or D40 execution is claimed here.

`smoke_contracts` owns the pure serialized schemas below; runtime/materialization
modules re-export their own records but models import no executor. Hashes are exact
lowercase 64-hex, commits 40-hex, timestamps exact UTC seconds
`YYYY-MM-DDTHH:MM:SSZ`. Every primitive is raw-type checked; models are frozen,
strict and extra-forbid. Integer counts/identities are nonnegative (inodes positive),
strings bounded to 512 bytes except fixed enums, lists unique/sorted and <=8192.

`RuntimeMaterialization` fields are `schema_version=1`, `candidate_id`, `git_commit`,
`freeze_sha256`, `candidate_snapshot_sha256`, `runtime_instance_id` (64-hex),
`files` (sorted FileFingerprint tuple), `owned_paths` (sorted OwnedPathIdentity tuple),
`runtime_source_sha256`, `runtime_device`, `runtime_inode`, `marker_device`,
`marker_inode`, `root_aliases=("candidate","runtime","work")`, and
`status="materialized"`. `OwnedPathIdentity` has lexical `path`,
`kind="file"|"directory"`, `device`, `inode`; it records every runtime child identity,
not merely equal content, so cleanup cannot delete a same-byte replacement. File
paths exactly equal the freeze inventory; directories are exactly its required
parents. Materialization metadata cap is 16 MiB.

The marker filename is `<materialization-filename>.ownership.json`, beside that
record, cap 4 KiB. `RuntimeOwnership` fields: `schema_version=1`,
`runtime_instance_id`, `runtime_device`, `runtime_inode`, `marker_device`,
`marker_inode`, `work_root_alias="work"`, `runtime_root_alias="runtime"`,
`materialization_sha256` (nullable only while building), and
`state="building"|"active"|"cleaning"|"cleaned"`. Create root/marker exclusively;
retain physical identities and lock the marker (Windows byte-range lock / POSIX
flock) while validating/updating it. State updates use the retained descriptor,
truncate/write/fsync in place, preserving the marker inode. A crash-truncated marker
fails closed. Publish immutable materialization before setting active with its exact
LF-byte digest. Cleanup resumes only active/cleaning with that binding; missing paths
are permitted only as an already-cleaning subset of the recorded owned paths.
Verify each remaining identity/type/content before chmod/unlink, never a replacement.
A published active-runtime failure transitions to cleaning before destructive cleanup,
so an interrupted remaining subset is resumable under the same detached binding.
A cleaned marker with absent runtime proves idempotence. Building failure may clean
only this invocation's retained owned objects; unexplained partial roots survive.
`<materialization-filename>.cleanup.json` records schema_version, instance,
materialization_sha256 and status=`completed`|`failed`, never absolute paths.

Extend `blinded_runtime` with async `OwnedProcessScope` and
`start_owned_process(*, scope, argv, cwd, env, stdout_path, stderr_path,
deadline_seconds) -> OwnedProcess`. The scope owns one group, long-lived server/browser
and command children alike. Each child uses the native base Python supervisor with `-I -S -B` (isolated startup,
no sitecustomize/user-site/cwd import hooks) and is stdin-gated until group Job
assignment or POSIX session registration; no breakaway. After assignment the fixed
supervisor launches the intended target with its explicitly validated environment;
supervisor isolation must not erase target sandbox semantics. `OwnedProcess` exposes pid, async wait,
stop and terminal outcome; closing the scope stops and confirms all descendants and
readers. `run_owned_command` accepts an optional scope, otherwise owns a temporary
one, and returns `OwnedCommandOutcome`: outcome, exit_code, started_at, finished_at,
stdout_size, stderr_size, stdout_sha256, stderr_sha256, using exactly the existing
CommandEvidence outcome vocabulary. No raw output enters a serialized model.
On Windows query retained Job active-process count after termination before closing
its handle; parent exit alone is not teardown proof. On POSIX confirm registered
session/group absence. Keep existing D37 host API behavior compatible.

Include the agent/controller and all out-of-group owned resident memory B. Reserve
1 GiB if agent runtime cannot be sampled. Group committed-memory limit is
`min(1536 MiB, 14336 MiB - B - 512 MiB)`; refuse a full execution group below
768 MiB or projected aggregate above 14 GiB. Measure group and outside resident memory
at intervals <=250 ms; lost owned accounting or aggregate >=14 GiB stops owned work.
Never start at >=14 GiB, and never exceed the user's 16 GiB ceiling. Windows Job
memory is a committed-memory cap, not a resident-memory proof: both are required.
Pure focused unit checks may use smaller externally supervised groups with known
peaks. Native browser flags bound caches/renderers and disable background networking;
only owned loopback URLs/profile/CDP targets are allowed. No browser/weights download.

Command role/alias mapping is fixed: backend sync binds `python_bootstrap` 3.12.12
(`tools/python_bootstrap`, no launcher) and `uv` 0.12.15 (same executable,
`tools/uv_module`); commands 2--5 bind `python` 3.12.12 (`tools/python_sandbox`).
Frontend binds `node` 24.11.1 (`tools/node`), `npx` to its actually verified bundled
npm version with launcher `tools/npx_cli`, and `pnpm` 10.18.3 with launcher
`tools/pnpm_cjs`. Resolved argv substitutes these aliases only; logical argv stays
unchanged. Smoke additionally binds installed `chrome`, `ffmpeg`, `ffprobe` and
`websockets` 16.1.1 as used; versions are actual verified values, not guessed pins.
Native tool aliases/hashes are compared before/after use. Summary integer fields:
versions 0/1, widths exact 390/1440, calls 0--4, duplicate_post_count 0--4,
backup_size <=32 MiB, duration_ms 0--60000. Other observation fields are raw booleans;
index/profile/backup hashes and ffmpeg/ffprobe exit codes may be null only on failure.
Passed stages require every documented observation, exact zero exits, nonnull hashes
and stateful embedding calls >=1. A failed stage emits only actual observations and
its bounded summary artifact; an unattempted stage emits no receipt. A missing/failed
smoke produces failed verification with nullable smoke and confirmed cleanup, never
fabricated complete receipts. D40 tooling may follow even when D35 acceptance fails.

Secret scan uses four fixed rule IDs: `tracked_private_state` (tracked .env except
.env.example, private corpus/review/key/evidence or storage paths),
`tracked_generated_state` (venv/node_modules/cache/dist/bytecode/media outputs),
`credential_token` (OpenAI/Anthropic sk-, GitHub token and AWS access-key shapes),
`private_key_block` (PEM private-key headers). Match byte patterns in bounded streamed
candidate tracked files and D39 public metadata, with 4 KiB chunk overlap; exclude
only exact placeholder/example tokens, not all tests. Report rule/counts only.
Passing means no matches under these bounded rules, not proof of every possible
secret absence. Define/test literal pattern constants before scanning.

Task 2 precision: `release_verification` owns the fixed scanner and native resolver,
without extending the 19-path source closure. Path matching is case-insensitive on
POSIX lexical components: private components `private`, `corpus`, `keys`, `secrets`,
`reviews`, `evidence`, `storage`; filenames `.env`/`.env.*` except exact `.env.example`,
`held-out.jsonl`, `human-review.json`, `independent-review.json`. Only the four exact
committed synthetic blinded fixture paths with these purposes are approved path
exceptions; content is still scanned. Generated components are `.venv`, `venv`,
`node_modules`, `dist`, `__pycache__`, `.cache`, `.pytest_cache`, `.ruff_cache`,
`media`, `generated`; suffixes `.pyc`, `.pyo`, `.mp4`, `.webm`, `.wav` also match.
Credential byte shapes are bounded alphanumeric/underscore/hyphen OpenAI/Anthropic
`sk-` (20--200), GitHub `gh[pousr]_` (20--200) or `github_pat_` (20--200), and AWS
`AKIA`/`ASIA` plus 16 uppercase alphanumeric characters; PEM headers cover PRIVATE,
RSA PRIVATE, EC PRIVATE and OPENSSH PRIVATE KEY. Exact full example tokens made
only from `x` or `X` (and AWS example `AKIAIOSFODNN7EXAMPLE`) are excluded; there is
no test-directory exemption. Scan 64 KiB chunks with 4 KiB overlap, count each
absolute match offset once, cap each rule count at 8192, and fail on byte/inventory
caps. Emit only the four rule IDs/counts, never matched paths or bytes.

Native probes use fixed source strings through `run_owned_command` within the same
scope, bounded output and a 30-second deadline, not extra inventory entries. Their
noncanonical tool/package JSON is capped at 64 KiB and reuses evidence_json's lexical,
duplicate-key, nonfinite and value guards; durable evidence remains canonical. Python
probes check real sys.executable/base prefix/base executable and every declared
runtime/dev/retrieval import origin beneath the group's exact site-packages directory; bootstrap uv must be within the native base
installation, not user-site, and its module launcher and discovered native binary
are rehashed around use. Commands 2--5 require a group-local site-packages origin,
include-system-site-packages=false, and the verified bootstrap base. Frontend first
primes only group-local npm cache using fixed pinned pnpm `--version`, then locates
one matching npm `_npx` pnpm package, verifies its exact package version and cjs
launcher, and rehashes it around every command. Installed npx belongs to the resolved
native Node installation. Esbuild preflight runs a fixed JS require/transform against
the locked installed esbuild (no scripts/rebuild/download); failure stops before
build. The environment is constructed from scratch: only validated Windows system
root/windir and fixed system/native executable PATH directories survive; all writable
homes/config/cache/temp and application storage paths are group-local. Python safe
path is enabled only for bootstrap uv/probes, not candidate-rooted application/tests.

Writable group source is copied using retained native anchors. After confirmed scope
teardown, generated entries are inventoried under the retained group anchor and
removed bottom-up; links are unlinked as leaves, never traversed. A lost/replaced
root, or a component replaced after teardown inventory, fails cleanup, never removes
a replacement. Publication cleanup uses only retained staged-file identities and
known byte prefixes; an unknown entry/replacement survives refusal. Runtime cleanup is
attempted in finally even if attestation, smoke or command preflight fails. Invalid
materialization binding refuses output rather than fabricating initial hashes.
Atomic verification publication uses a new disjoint, Git-ignored directory beneath
the trusted current tool repository, staging exactly `verification-manifest.json`
and `d39-verifier-attestation.json` with retained native parent/stage/file identities
and a native no-replace directory rename. It does not call the D38-specialized triplet
publisher, create a fourth marker, or replace previous evidence. Missing Task 3
source prevents attestation/publication; cleanup still runs, and no smaller closure
or substitute attestation is permitted. Native command bindings are schema-validated
before any target instruction; unavailable prerequisites add no command entry. A
failed or unconfirmed group teardown sets overall cleanup failed even if the runtime
cleanup itself completes. Recheck the exact raw freeze digest at every group boundary
and final check, not only equal candidate files. Convert Git subprocess failures to
redacted verifier failure without bypassing runtime cleanup. Offload blocking source,
Git and tool hashing to one executor thread while a scope is active, keeping the
resident monitor runnable; never overlap two execution groups. Every smoke receipt carries the six bootstrap roles
`node`, `npx`, `pnpm`, `python`, `python_bootstrap`, `uv`; browser additionally requires
`chrome` and `websockets`, and FFmpeg additionally requires `ffmpeg` and `ffprobe`.
Use the same role aliases/pins as commands, `tools/chrome`, `tools/ffmpeg`,
`tools/ffprobe`, and `tools/websockets_module` for the added launcher. Identical aliases
must have identical complete fingerprints throughout the smoke manifest; reject
wrong/missing roles, versions, launchers, oversized tools and conflicting identities.

`ToolExecutionBinding` is owned by `smoke_contracts`; `release_verification` imports it.

```python
class ToolExecutionBinding(BaseModel):
    role: str
    version: str
    executable: FileFingerprint  # lexical alias, complete streamed size/SHA-256
    launcher: FileFingerprint | None

class CommandEvidence(BaseModel):
    name: str
    argv: tuple[str, ...]  # canonical logical inventory, not a claim of native argv
    resolved_argv: tuple[str, ...]  # actual native argv with owned path aliases
    tool_bindings: tuple[ToolExecutionBinding, ...]
    media_tools: tuple[ToolExecutionBinding, ...]  # backend_pytest: bound ffmpeg/ffprobe; otherwise empty
    cwd: str
    deadline_seconds: int
    outcome: Literal["completed", "launch_failed", "timeout", "output_limit", "memory_limit", "teardown_failed"]
    exit_code: int | None
    started_at: str
    finished_at: str
    stdout_size: int
    stderr_size: int
    stdout_sha256: str
    stderr_sha256: str

class SmokeManifest(BaseModel):
    schema_version: Literal[1]
    producer_tool_sha256: str  # exact producer source attestation aggregate
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
    stage_receipts: tuple[SmokeStageReceipt, ...]  # exactly six, in fixed order

class VerificationManifest(BaseModel):
    schema_version: Literal[1]
    candidate_id: str
    git_commit: str
    freeze_sha256: str
    verifier_tool_sha256: str
    status: Literal["passed", "failed"]
    commands: tuple[CommandEvidence, ...]  # full inventory on pass; attempted prefix on failure
    smoke_manifest_sha256: str | None
    smoke_manifest: SmokeManifest | None
    secret_scan_passed: bool
    candidate_clean_before: bool
    candidate_clean_after: bool
    candidate_snapshot_before_sha256: str
    candidate_snapshot_after_sha256: str | None
    materialization_sha256: str
    runtime_instance_id: str
    runtime_source_sha256: str
    runtime_snapshot_after_sha256: str | None
    cleanup_status: Literal["completed", "failed"]
```

The fixed `shell=False` command inventory contains exactly these nine `(name, argv)`
entries, in this order, each exactly once:

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

`evaluation.release_verification.D39_REQUIRED_COMMANDS` is this immutable ordered
nine-tuple. Models/validators above are frozen, strict, extra-forbid, with the shared
pre-parse/canonical/literal contracts. A failed manifest may contain only an attempted
ordered prefix and nullable absent smoke/final snapshots; it must never fabricate
unexecuted commands, smoke success, clean flags, or final hashes to satisfy a schema.

| Command | Hard deadline (seconds) |
|---|---:|
| backend_uv_sync | 600 |
| backend_import | 30 |
| backend_pytest | 1,800 |
| backend_ruff | 120 |
| backend_d31_d35 | 600 |
| frontend_pnpm_install | 600 |
| frontend_test | 600 |
| frontend_build | 300 |
| frontend_lint | 180 |

Before command 1, resolve a regular native bootstrap Python 3.12.12, prove its uv
0.12.15 module/binary origin, and bind executable/launcher versions, sizes, and
streamed hashes. The backend venv itself need not contain uv. Set `UV_PYTHON` to that
verified absolute Python, `UV_PROJECT_ENVIRONMENT` to `<group>/env`, `UV_CACHE_DIR`
to `<group>/uv-cache`, and `UV_CONCURRENT_DOWNLOADS=2`, `UV_CONCURRENT_BUILDS=1`,
`UV_CONCURRENT_INSTALLS=1`. Validate the resulting venv's `sys.executable`,
`sys.base_prefix`/base executable and installed package origins before command 2.
Commands 2–5 resolve `python` only to that group's `env/Scripts/python.exe` (POSIX
`env/bin/python`); use `-m pytest`/`-m ruff` from it, never global executables or
implicit `uv run` resync. A missing extra/module/origin fails before the next command.
The optional retrieval wheels eliminate NumPy-based ONNX pooling-test skips; the
loopback embeddings smoke itself needs HTTPX, not NumPy/ONNXRuntime/tokenizers and
never loads weights. Successful fake-ONNX tests do not prove real ONNX asset inference.

For frontend commands, resolve native `node.exe` 24.11.1 and its installed npm
`npx-cli.js`; execute `(node_exe, npx_cli, *logical_argv[1:])` with `shell=False`.
Never spawn `.cmd`/`.bat` or pass a caller-selected command. Pin pnpm 10.18.3 and bind
its resolved `pnpm.cjs` hash/version before accepting install/test/build evidence.
`argv` retains the canonical inventory; `resolved_argv` records this native expansion
with exact role-to-path aliases, and `tool_bindings` records the real executable and
JS/module launcher identities. The trusted Python stdin-gate supervisor is separately
source-attested; its fixed wrapper is not mislabeled as the target command's argv.
Rehash bindings around commands. Node/npx/pnpm hashes are not candidate source hashes.
Native tool blobs cap at 256 MiB each / 1 GiB total and are stream-hashed.

Set group-local npm cache/config, pnpm store/cache/state, `HOME`, `USERPROFILE`,
`APPDATA`, `LOCALAPPDATA`, `XDG_*`, `TEMP`, `TMP`, and `TMPDIR`. A generated untracked
`.npmrc` in the writable sandbox supplies group-local `store-dir` and
`cache-dir`, `child-concurrency=1`, `network-concurrency=2`, and engine-strict checking;
it is not a candidate tracked-file modification. Set `NODE_OPTIONS=--max-old-space-size=512`,
`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`,
`NUMEXPR_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1`,
`RUFF_CACHE_DIR`, and `PYTEST_ADDOPTS` with the cache path inside the group. No inherited
`NODE_ENV=production`, Python path, provider credentials, pytest plugins, Node options,
or package-manager config is admitted. Build outputs remain in the writable sandbox;
external application storage/database/browser profile roots belong to that group.
Pinned package `test`/`build`/`lint` scripts are intentionally trusted and may internally
use a shell (`tsc -b && vite build`); this is not a promise of shell-free npm internals.
Arguments and synthetic inputs never supply shell fragments. Native esbuild availability
is a fixed post-install preflight, not a tenth command or implicit script authorization.

Expose the reusable `blinded_runtime.run_owned_command(*, argv: tuple[str, ...],
cwd: Path, env: dict[str, str], stdout_path: Path, stderr_path: Path,
deadline_seconds: int) -> Awaitable[OwnedCommandOutcome]` for D39 bootstrap/commands/
smoke. `OwnedCommandOutcome` contains outcome, nullable exit code, timestamps and
actual bounded output sizes/hashes, not raw text; `release_verification` adds canonical
inventory and prevalidated tool bindings. This helper imports neither verification nor
smoke/result models. Reconcile latched memory/output/timeout/stop failures after final
reader and process settlement, with teardown failure taking precedence; parent exit
zero never clears a later observed failure. An explicit administrative `stop()` of a
still-running owned server/browser before its deadline permits later commands only
after confirmed tree/reader teardown; its real nonzero termination code remains
recorded and is never a passed command. This exception does not clear an already
exited nonzero child, any prior scope failure, timeout, output/memory latch or teardown
failure. Ordinary command completion still requires zero. Failed CommandEvidence validates every
populated native alias/version/hash binding too; only genuinely unavailable launch
observations may be empty. It reuses D37 gate/tree/drain primitives and extends no candidate
contract. D40 may import contracts but never invokes this helper.

All commands use the existing trusted stdin gate before Windows Job Object assignment,
with kill-on-close and no breakaway. Deadlines use monotonic time, not evidence wall
clock; record canonical UTC-second start/finish times separately. If process creation
returns after its deadline, do not release its gate and tear it down. Python cannot
promise interruption of the initial native process-creation call; this OS limitation
is not hidden as an exact kill-at-deadline guarantee. Output has a shared stdout+stderr 2 MiB cap per
command, drained incrementally, with 1 s parent-exit grace and 10 s confirmed tree/
reader teardown. One command runs at a time. Deadline, cap, memory pressure, nonzero
exit, source drift, or launch/assignment/teardown failure stops the group; remaining
commands do not run. Output is never captured unboundedly in RAM. Cleanup completes
before bounded failed evidence is published; unknown teardown is a failed result,
not a successful command. The group-local package fetches are the only installation
network allowance; smoke providers are loopback only, and decision has none. Entries 1–5 execute in the single backend group sandbox and entries 6–9
execute in the single frontend group sandbox; the separate smoke group adds no entry
to this inventory. Partial/failed smoke has only actual receipt files and a fixed
redacted failure; `run_candidate_smokes` raises without a complete SmokeManifest.
The verifier can consume the intended absent/failed smoke path to emit truthful failed
verification and perform bound runtime cleanup. The verifier uses the tuple to execute, and D40 independently
compares the parsed manifest's full `(name, argv)` sequence to it and checks every
exit code; D40 never trusts `VerificationManifest.status` as a substitute. Every entry in a passed manifest must have
`outcome == "completed"` and `exit_code == 0`, the specified deadline, bounded output
sizes, and validated native/tool bindings; duplicate, missing, additional, reordered,
or argv/name-mismatched entries invalidate passed verification. Legacy migration/backup,
restore, both-mode startup, recovery browser journey, and real FFmpeg with fake
providers are mandatory smoke evidence, not caller-extensible commands. The exact
canonical `SmokeManifest` is embedded in `VerificationManifest`; its LF-terminated
canonical bytes hash to `smoke_manifest_sha256`. Six arbitrary hash strings are not
proof: the `smoke_contracts.py` schema below embeds exactly six typed stage receipts,
and each named stage hash hashes that receipt's complete LF-terminated bytes.
A secret/private/generated-file scan records rule IDs/counts only. Candidate/runtime drift or any command/smoke failure stops subsequent work and yields
failed evidence. A partial materialization is removed by the materializer before it
returns failure. After the final independent runtime recheck, the verifier calls
`cleanup_candidate_runtime()` in `finally`; cleanup verifies the detached expected
materialization hash before parse, the physical ownership marker/root identity, and
containment beneath `work_root`. Stop/confirm every owned descendant first. Walk only
owned non-link/non-reparse components; on Windows clear read-only with `os.chmod`
only on validated owned regular files before unlinking, then remove owned directories
bottom-up. Never traverse a junction, chmod a replacement or ancestor, or terminate a
user-owned process. Close no-delete handles only immediately before removing their
validated objects. Clean group caches/temp/browser/database/media and runtime source,
preserve only bounded canonical evidence/ownership receipts, and record `cleaned`.
Idempotence is marker-bound, not an identity-blind `rmtree(ignore_errors=True)`. A cleanup failure sets
`status="failed"` and `cleanup_status="failed"` and reports only a root alias. If the
verifier is never started after successful materialization, the operator runs the
same dedicated cleanup CLI with the record; it refuses an unbound or out-of-root
path. D39 atomically emits
`verification-manifest.json` plus a distinct canonical D39 verifier source
attestation whose aggregate hash equals `VerificationManifest.verifier_tool_sha256`.
Use fixed `tool_name="d39_release_verifier"` and the exact sorted 19-path tuple below,
validated against committed project-root bytes by existing `attest_tool`. No D39
controller imports D37/D38/corpus/app; the internal bootstrap's app modules come only
from independently frozen candidate bytes. An import-closure test distinguishes this
candidate process boundary and fails any new unlisted tooling dependency.

```text
backend/evaluation/__init__.py
backend/evaluation/blinded_io.py
backend/evaluation/blinded_runtime.py
backend/evaluation/browser_smoke.py
backend/evaluation/evidence_json.py
backend/evaluation/release_candidate/__init__.py
backend/evaluation/release_candidate/contracts.py
backend/evaluation/release_candidate/fingerprints.py
backend/evaluation/release_candidate/freeze.py
backend/evaluation/release_verification.py
backend/evaluation/runtime_materialization.py
backend/evaluation/scripts/d39_candidate_smoke.py
backend/evaluation/scripts/d39_smoke.py
backend/evaluation/scripts/materialize_candidate_runtime.py
backend/evaluation/scripts/verify_release_candidate.py
backend/evaluation/smoke_contracts.py
backend/evaluation/tool_attestation.py
backend/pyproject.toml
backend/uv.lock
```
A candidate failure restarts at D36; a verifier-only change gets a new verifier hash
and a complete D39 rerun in a new evidence directory. A passed manifest additionally
requires a complete passed six-receipt smoke manifest, `secret_scan_passed is True`,
both clean flags raw booleans true,
`candidate_snapshot_before_sha256 == candidate_snapshot_after_sha256`,
`runtime_snapshot_after_sha256 == runtime_source_sha256`, and
`cleanup_status == "completed"`.

#### Six-stage smoke contract

`backend/evaluation/smoke_contracts.py` owns strict `SmokeStageReceipt`, its six
summary variants, and `SmokeManifest`; it imports `FileFingerprint`/canonical hashing
and the pure JSON parser, not executors/browser/app. D39 and D40 import it unchanged.

```python
class SmokeStageReceipt(BaseModel):
    schema_version: Literal[1]
    stage: Literal["legacy_migration", "restore", "all_tools_startup", "stateful_startup", "browser", "ffmpeg"]
    candidate_id: str
    git_commit: str
    freeze_sha256: str
    materialization_sha256: str
    runtime_instance_id: str
    runtime_source_sha256: str
    outcome: Literal["passed", "failed"]
    tools: tuple[ToolExecutionBinding, ...]
    artifacts: tuple[FileFingerprint, ...]
    summary: Annotated[
        MigrationSummary | RestoreSummary | AllToolsStartupSummary | StatefulStartupSummary | BrowserSummary | FFmpegSummary,
        Field(discriminator="stage"),
    ]
```

Summary is discriminated by `stage`, not a free-form dictionary; fields below are
required, extra-forbid and bounded. Each summary's `stage` is the matching single
Literal; separate AllToolsStartupSummary and StatefulStartupSummary preserve exact
mode-specific fields without optional omissions.
`tools` is unique/sorted by role (<=16 entries); `artifacts` unique/sorted lexical
aliases (1–64 entries). Every artifact has actual complete byte size and streamed
SHA-256, verified before cleanup; no caller-supplied digest stands for a performed
stage. Receipts <=64 KiB and smoke manifest <=1 MiB; retained summary JSON files
<=64 KiB each, screenshots <=4 MiB, transient synthetic media <=32 MiB. The smoke
producer hashes transient artifacts before disposal; D40 validates the attested typed
summaries/bindings, not retained raw media or a human-review claim.

| Fixed order / summary fields | Required observation / stage deadline |
|---|---|
| `legacy_migration`: `stage`, `from_version`, `to_version`, `integrity_ok`, `foreign_keys_enabled`, `rows_preserved`, `identities_preserved`, `backup_size`, `backup_sha256` | Copy committed synthetic upstream_v0 SQL, new synchronous SQLite connections explicitly execute/read back `PRAGMA foreign_keys=ON` before transactions, actual leased migration 0->1, backup verification and exact logical row/identity preservation; 120 s |
| `restore`: `stage`, `restored_version`, `integrity_ok`, `foreign_keys_enabled`, `rows_equal`, `identities_equal`, `lease_exclusion_passed` | Actual stopped-app restore and rejected live-app restore, re-open with FK enabled and check exact expected logical state, never require nondeterministic SQLite file bytes to be equal; 120 s |
| `all_tools_startup`: `stage`, `mode`, `startup_ready`, `health_ok`, `request_completed`, `model_calls`, `index_sha256` | Startup+health 200/ready, one synthetic exact operation via fake loopback chat, mode all_tools, `index_sha256=None`; 180 s |
| `stateful_startup`: same startup fields plus `profile_sha256`, `embedding_calls`, `retrieval_verified` | Genuine source/profile-bound index, loopback embeddings/chat, explicit readiness and bounded fallback. Require actual verified retrieval/embedding call, not index presence or fallback-only success; complete exact operation; 180 s |
| `browser`: `stage`, `narrow_width`, `wide_width`, `waiting_ok`, `safe_retry_ok`, `unknown_remote_blocked`, `migration_failed_ok`, `keyboard_ok`, `duplicate_post_count`, `horizontal_overflow`, `playback_ok`, `documentation_checks` | Actual 390/1440 px journeys, Tab/Enter and duplicate action (one POST), no overflow and playback. Fixed automated documentation checks below; 300 s |
| `ffmpeg`: `stage`, `providers_fake`, `ffmpeg_exit_code`, `ffprobe_exit_code`, `video_present`, `subtitle_present`, `publication_bound`, `duration_ms` | Real FFmpeg/ffprobe through candidate fake-provider generation, present video/subtitle and exact current artifact pointer/size/hash; duration 1–60,000 ms, both exits zero; 300 s |

`SmokeManifest.stage_receipts` follows that exact order. It retains exactly the six
named hash fields already shown; do not add alternate stage-hash arrays or omit stages.
For a passed smoke all outcomes/required booleans are true, counts are exact strict
integers (model calls 0–4; embedding calls 1–4 in stateful), versions/executable hashes
are present, summary stage/mode agrees, and every candidate/runtime binding equals
materialization. The producer independently hashes/reopens six receipt files; the
verifier independently validates the embedded receipts, hashes, schemas, versions,
and bindings. Missing/malformed/failed receipt fails smoke; a partial failed smoke
retains only actually completed/failed receipt files, never a fabricated complete
`SmokeManifest`.

Smoke has its own clean backend extras sync and frontend frozen dev install using
the same native launch/environment policy; these bootstrap operations are bounded
600 s each but add no entries to the nine-command final verifier inventory. Stage
hashes bind the verified bootstrap tool versions too. The immutable runtime and
original candidate remain untouched throughout. Index generation runs candidate
`publish_index`/`load_index` in that group's candidate-rooted subprocess, against
external synthetic assets; no `.env`/tracked source mutation or cloud/weights
acquisition is permitted. It is a real candidate index format, not a placeholder file.

The exact D35 `scripts/plan_c_demo.py` hardcodes chat/embedding endpoints and the ONNX
E5 profile in `demo_settings`; environment variables alone cannot override them.
Current demo/test source is not byte-identical to D35, so do not import current tooling
copies as candidate proof. Add external internal-entrypoint
`evaluation/scripts/d39_candidate_smoke.py`, launched by owned sandbox Python `-B`
through a fixed runpy bootstrap with candidate backend as cwd/import root and no
external-tool directory on sys.path. It imports candidate modules only in this child.
Load committed candidate demo functions with `runpy.run_path` from the verified copy;
call its exact `prepare_storage(directory)`, `exclusive_demo(directory)`,
`demo_settings(directory, mode, model, index)`, and
`create_demo_app(settings, frontend)` seams. Before create_demo_app, assign the Settings
object's explicit synthetic `language_base_url`, `language_retrieval_profile`,
`language_embedding_base_url`, and `language_retrieval_index`; bind `voicevox_url` on
settings and every synthetic project to the owned fake provider's bounded
GET `/v1/speakers`, so UI discovery never queries an unrelated local VOICEVOX service;
use a 5 s fake-provider connection timeout; keep readiness/all-tools
fallback/reasoning flags as defined by D35. No source-file or `.env` write occurs.
Use `uvicorn.run(app, host="127.0.0.1", port=owned_port, workers=1, reload=False)`.
The external controller supplies only fixed mode plus validated owned storage/frontend/
index/profile paths, loopback URLs and bounded model ID/port, never an arbitrary
expression, Python import, shell command or case-selected hook. Reject incomplete
stateful configuration before serving. Build frontend in the smoke group's writable
copy first, then serve that group's dist path. This bootstrapping seam is synthetic
configuration evidence, not a claim that the unmodified interactive demo CLI accepts
new flags or that production ONNX weights were exercised. Media smoke additionally
sets synthetic output to 320x240 at 12 fps with a 48 px subtitle band before app
creation, keeping the owned 16 GiB lane bounded; it verifies publication/playback,
not full-HD throughput. Import modules that capture settings only after this demo
configuration is bound. The browser's fake-provider playback media uses the same
bounded configuration, and the later FFmpeg stage remains separately performed.

Official browser protocol research: <https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json>
and <https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/js_protocol.json>
were retrieved with a 2 MiB cap each in the 2026-09-30–2026-10-01 session (schema 1.3).
Exact HTTP retrieval timestamps were not separately recorded. Browser/Runtime/Input/
Page documentation pages were also inspected. Attempted official websockets reference
<https://websockets.readthedocs.io/en/stable/reference/sync/client.html> returned
HTTPError; installed 16.1.1 signature is the available API evidence, not a fabricated
successful documentation lookup.

Browser implementation is an external `backend/evaluation/browser_smoke.py` helper
called only by `evaluation/scripts/d39_smoke.py`, never by the decision process.
Use already locked/installed `websockets` 16.1.1 (via Uvicorn standard) and
`websockets.sync.client.connect(uri, proxy=None, compression=None, open_timeout=5,
close_timeout=5, max_size=2*1024*1024, max_queue=4)` with one connection/reader.
The controller launches this standalone helper using the verified sandbox Python;
its actual transport import/version/hash belongs to that sandbox, not a different
controller installation. The helper imports no candidate app or current evaluation
package. It reads bounded ephemeral CDP JSON (duplicate/nonfinite/depth refusal),
not the canonical evidence string limit: screenshot/base64 and generated protocol
fields can legitimately exceed 8 KiB. Durable typed receipts continue through the
shared canonical evidence parser.
The installed signature was probed; live websockets documentation retrieval failed,
so behavior is checked by the later local roundtrip. Launch a user-supplied installed
native Chrome/Chromium executable under the owned Job Object, bind version/hash.
The smoke CLI accepts optional `--browser-executable` and the Python smoke API optional
`browser_executable: Path | None = None`; omission checks only fixed native installed
Chrome/Chromium locations (Windows Program Files Chrome and Linux chrome/chromium
PATH entries), never a running profile/account. Reject script launchers/links/reparses;
missing installed native browser is a failed prerequisite, never a download or skip.
Use a new group-local profile, loopback debugging address and ephemeral port, and
poll the bounded `DevToolsActivePort`/`/json/version` and `/json/list` only for this
owned process (5 s request / 30 s startup). Never attach to a user's browser.
Recheck its installed `/json/protocol` before driving it. Official CDP master
browser/js JSON schemas were retrieved in that audit session; they describe required fields,
not proof of the installed browser version. Use only `Browser.getVersion`,
`Page.navigate(url)`, `Runtime.evaluate(expression, returnByValue=True,
awaitPromise=True, timeout=5000)`, `Input.dispatchKeyEvent(type,key,code,text,windowsVirtualKeyCode)`,
`Emulation.setDeviceMetricsOverride(width,height,deviceScaleFactor=1,mobile=False)`,
and `Page.captureScreenshot(format="png",captureBeyondViewport=False)`. Reject CDP
errors, `exceptionDetails`, unexpected IDs, oversized frames/screenshots, and missing
methods. Fixed repository-owned expressions inspect role/status text, focus, scroll
width and media readiness; synthetic values are JSON-encoded data, never JS fragments.
Provider/backend/network counters prove exactly one action POST. Each server receives
a fresh 64-hex synthetic `owner_token` in its bounded fixed configuration. A fixed
bootstrap-only middleware GET `/__d39-owned` returns that token; readiness requires
its exact match and a still-active owned process before health/status are trusted,
so an accidentally reused loopback port cannot adopt an unrelated server. This
synthetic ownership token is not an application credential. The same middleware
atomically records actual operation POST counts from an initially observed zero. The Chrome protocol
roundtrip is still a **Blocked fact**; it cannot be counted as browser acceptance yet.

Documentation checks in `BrowserSummary.documentation_checks` have exactly keys
`setup_paths`, `locked_versions`, `mode_commands`, `recovery_codes`,
`migration_restore`, `limitation_boundary`, all exact booleans true. Fixed inputs are
pinned `README.md`, `Makefile`, `backend/.env.example`, package manifests/locks,
`backend/scripts/plan_c_demo.py`, D34/D35 test sources and candidate specification.
Check those paths/links resolve to inventoried regular files; package versions and
Python/Node prerequisites agree with locked metadata; both demo-mode choices and
public seams exist and the external bootstrap produces tested startup; the committed
D35 API/UI reason/action fixtures pass; committed D34 migration/restore tests pass
including live-lease rejection; and specification states automated evidence is not
human acceptance and real held-out execution is external. Record explicit per-key
pass/fail in the summary. The mode check does not claim environment overrides work
with demo.main. Each machine check is bounded file/AST/fixture or command evidence,
not an unstructured prose-review checkbox. Missing/stale claims fail this automated
gate; no semantic prose review, human operation, or independent review is inferred.
The pinned D35 README currently says Python 3.13+ and Node 20+, whereas its manifest
permits Python >=3.12 and locked packages require a stronger Node floor. Thus the
frozen setup claims are a known failed documentation subcheck for the selected lane.
Do not silently ignore it, install a different stack to manufacture a pass, or edit
D35. A fingerprinted candidate-doc correction requires an explicitly authorized
successor candidate/D36 restart; changing this mandatory gate requires an explicit
policy/DTD revision, not a coding-agent waiver. Neither action is authorized by this
audit. Six receipt hashes and automation never supply D40 human/independent review.

### D40 exact readiness decision

D40 requires D36 freeze; all three D38 artifacts; D39
`verification-manifest.json`; the D39 verifier source attestation; human operation;
and independent review. Raw bytes of the D38 triplet, D39 verification manifest, and
D39 verifier attestation each require a separately supplied detached expected
lowercase 64-hex SHA-256 before parsing. A missing file, missing/malformed detached
digest, digest mismatch, non-canonical file, or schema error becomes its own named
Not-ready blocker.

Before deciding, the separate `python -m evaluation.scripts.attest_release_decision`
operation validates the actual Git repository root (project root, not `backend/`),
clean normal index, declared HEAD, and exact committed working bytes, then calls the
existing keyword-only API unchanged:

```python
attest_tool(
    repo_root=repo_root, tool_name="d40_release_decision", git_commit=verified_head,
    source_paths=DECISION_SOURCE_PATHS,
)
```

There is no `attest_tool_source` API. Running from `backend/`, both CLIs use
`--repo-root ..`. `DECISION_SOURCE_PATHS` is the exact sorted module-owned tuple below;
paths are project-root-relative and include the existing result/protocol import
closure (including corpus/fixture and app contract imports), planned IO/parser/runtime
helpers, pure smoke contracts, and dependency manifests. This is conservative source
coverage, not a permission to call imported executor/Git/provider functions.

```text
backend/app/__init__.py
backend/app/interpretation/__init__.py
backend/app/interpretation/contracts.py
backend/app/operations/__init__.py
backend/app/operations/catalog.py
backend/app/operations/contracts.py
backend/app/operations/definitions.json
backend/app/operations/schema_validation.py
backend/evaluation/__init__.py
backend/evaluation/blinded_contracts.py
backend/evaluation/blinded_io.py
backend/evaluation/blinded_runtime.py
backend/evaluation/contracts.py
backend/evaluation/corpus.py
backend/evaluation/evidence_json.py
backend/evaluation/fixtures.py
backend/evaluation/release_candidate/__init__.py
backend/evaluation/release_candidate/contracts.py
backend/evaluation/release_candidate/fingerprints.py
backend/evaluation/release_candidate/freeze.py
backend/evaluation/release_decision.py
backend/evaluation/release_verification.py
backend/evaluation/result_contracts.py
backend/evaluation/result_import.py
backend/evaluation/runtime_materialization.py
backend/evaluation/scripts/attest_release_decision.py
backend/evaluation/smoke_contracts.py
backend/evaluation/tool_attestation.py
backend/pyproject.toml
backend/scripts/decide_release_readiness.py
backend/uv.lock
```

Planned D38/D39 imports must stay inside that stated graph: import model/hash/reader
APIs, not the smoke/browser orchestration CLI or runner. The import-closure check
includes function-local imports and package initializers. If implementation adds a
behavior-affecting imported helper, update this tuple and DTD before continuing;
a new unlisted import fails the test. No stale seven-file subset is accepted.
D39 has the distinct exact 19-path verifier tuple above (including its bootstrap/
browser/CLIs); D38 has the distinct exact 25-path importer tuple. Neither inherits
D40's larger closure at runtime or uses an unattested dependency-hash appendix.
D40 checks fixed upstream tool names `d38_result_importer` and
`d39_release_verifier`, source inventories and recomputed aggregates before gates.

No glob, directory walk, caller-added path, omission, duplicate, or alternate file is
permitted in decision-source selection. `load_decision_tool_attestation` performs only
bounded regular-file reads, streaming fixed-path hashes, and shared aggregate
recomputation. It MUST NOT call `attest_tool`, `validate_git_repository`, or any
subprocess; committed-root/HEAD cleanliness was proved by the separate attestation
operation. The declared immutable tooling checkout and trusted parents remain an
operator assumption at decision time, not a fresh Git assertion. Fixed-source pre/post
hash equality and detached expected aggregate protect decision bytes, not hostile
same-user mutation. The attestation uses the shared canonical `ToolAttestation` model, sorted
POSIX paths, per-file size/SHA-256, and canonical aggregate hash. The attestation CLI
requires an out-of-band `--expected-sha256` and rejects a malformed or unequal
expected aggregate before atomically publishing the artifact. The decision CLI then
requires `--decision-tool-attestation` and the same detached
`--decision-tool-expected-sha256`, rehashes the exact allowlist before evaluating any
gate, and rejects any artifact/current-source/expected-aggregate mismatch without
creating `decision.json` or `decision.md`. It passes the validated `ToolAttestation` object to the decision engine; there is no
`decision_tool_sha256` CLI option or free-form API parameter. The decision records the
attestation file's actual canonical-byte hash under
`input_sha256["decision_tool_attestation"]` and its validated source aggregate under
`decision_tool_sha256`; these two hashes have distinct meanings.

D40 imports D37's `EvaluationResultBundle`, D38's `ImportValidation`, and D39's
`VerificationManifest`; it does not fork them. D40 consumes only the shared-schema
`EvaluationResultBundle` instance whose exact canonical bytes D38 accepted; it never
parses a separately supplied D37 bundle or reconstructs omitted fields. It cross-binds:

- actual D38 accepted bytes to `validation.accepted_bundle_sha256` and all candidate,
  freeze, corpus, separate approval, run-protocol, D36 trial-tool, and D37 evaluator
  identities;
- actual D38 tool attestation to `validation.d38_import_tool_sha256`;
- actual D39 verification-manifest hash to its detached expected hash and decision
  input map;
- D39 candidate ID, D35 Git commit, and freeze hash to D36;
- `VerificationManifest.verifier_tool_sha256` to the separately detached and parsed
  D39 verifier source attestation aggregate hash;
- the D39 command inventory to the exact nine ordered name/argv pairs exactly once,
  with completed outcome, zero exit, exact deadlines/output caps, and honest native
  executable/launcher hash+version bindings;
- the embedded D39 smoke manifest's LF-terminated canonical hash, complete six typed
  receipt bytes/hashes/sizes, summary outcomes/version evidence, and all candidate/
  commit/freeze/materialization/runtime bindings;
- D39 secret scan, candidate cleanliness, candidate snapshot equality, runtime
  snapshot equality, and completed cleanup; and
- every review and limitation candidate ID to D36.

```python
class ReviewEvidence(BaseModel):
    kind: Literal["human_operation", "independent_review"]
    candidate_id: str
    status: Literal["completed", "failed", "pending", "not_performed"]
    reviewer: str
    recorded_at: str
    artifact_sha256: str | None

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

# In evaluation.release_decision; the fixed allowlist is module-owned.
def attest_and_validate_decision_tool(
    *, repo_root: Path, output_path: Path, expected_sha256: str,
) -> ToolAttestation: ...

def load_decision_tool_attestation(
    *, repo_root: Path, attestation_path: Path, expected_sha256: str,
) -> tuple[ToolAttestation, str]: ...

def load_d38_accepted_evidence(
    *, accepted_result_path: Path, accepted_result_expected_sha256: str,
    validation_path: Path, validation_expected_sha256: str,
    d38_tool_attestation_path: Path, d38_tool_attestation_expected_sha256: str,
    freeze: FreezeManifest,
) -> tuple[EvaluationResultBundle, ImportValidation, ToolAttestation, dict[str, str]]: ...

def load_d39_verification_evidence(
    *, verification_path: Path, verification_expected_sha256: str,
    verifier_tool_attestation_path: Path,
    verifier_tool_attestation_expected_sha256: str,
    freeze: FreezeManifest,
) -> tuple[VerificationManifest, ToolAttestation, dict[str, str]]: ...

def decide_readiness(
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
) -> ReadinessDecision: ...
```

#### D40 shared array parsing and bounded gate output

Add `parse_canonical_typed(raw: bytes, adapter: TypeAdapter[T], *, maximum: int) -> T`
to `evidence_json`, sharing the existing lexical/duplicate/nonfinite/raw canonical
checks and sanitized errors. Validate JSON strictly, then require
`canonical_json_bytes(adapter.dump_python(value, mode="json")) + b"\\n" == raw`.
`parse_canonical_model` remains compatible and delegates without a second parser.
This API parses the limitations tuple; no strict Python list-to-tuple conversion.

Evaluate every category, but emit a fixed bounded gate family rather than one row
per category: two-mode completion, overall quality, category completion, category
quality and safety, plus each existing integrity/review/limitation family. At most
64 gate rows/blockers, name <=128 characters, detail <=1024; failed category detail
contains only total failure count and the first eight sorted opaque tokens. All
categories still affect the outcome. This keeps decision.json <=1 MiB even for the
maximum topology and reveals no category names/text. Use an explicitly supplied
complete refreshed D36 publication; never auto-select the first historical manifest.

The optional limitations input is one canonical JSON array, parsed explicitly with
`TypeAdapter(tuple[AcceptedNonSafetyLimitation, ...]).validate_json(..., strict=True)`
after the shared duplicate/nonfinite/canonical checks; its API value is a Python tuple
(maximum 256 unique limitation IDs). Strict Python list-to-tuple coercion is not used.
`ReadinessDecision.gates`, `blockers`, and `accepted_limitations` are output JSON
arrays and Python `list` values; those output fields are never tuple-typed or
serialized from sets. Their deterministic ordering is
fixed by the decision engine: gate-definition order, blocker gate order, and
`limitation_id` order respectively.

The evidence loaders derive returned input hash maps only from detached-verified
actual canonical bytes, never sibling hashes or caller claims. The engine compares
canonical serialization hashes of the supplied models to those maps and the bound
validation/attestation identities; it accepts successful integrity gates only from
these loader-produced inputs. Direct synthetic model construction exercises gate
arithmetic, not real transfer provenance. Likewise decision source identity comes
only from independently fixed-file rehash plus detached aggregate validation before
calling the engine, not an arbitrary ToolAttestation/hash argument.

No hash is trimmed or case-normalized. Every content/artifact hash is exact lowercase
64-hex. Completed review evidence requires an artifact; pending/not-performed must
carry `None`; failed always blocks. Limitation evidence is optional, canonical,
candidate-bound, uniquely identified, content-hashed, and separately approval-hashed;
free text, safety limitations, pending/unaccepted records, malformed hashes, or
candidate mismatch cannot support conditional readiness.

The two-mode semantics are exact and independent. Before ratio evaluation, D40
independently validates the bundle's complete embedded topology: bounded non-empty
unique sorted protocol case/category token arrays, matching declared counts, one exact
sorted case/category binding per protocol case, no undeclared token, the exact
included/excluded partition, a non-empty included set, `included_count >= 1`, and at
least one included token in every embedded protocol category in each mode. D40 derives
category denominators from `case_categories`; it does not trust category result
`included` values and does not need `protocol.json`. It also re-runs every bounded-count,
checked-sum, and mode/category equation enforced by D37/D38. Empty overall/category
coverage or invalid/overflowing arithmetic is a named Not-ready blocker
and is never accepted as a vacuous completion or percentage pass. For **each** of
`all_tools` and `stateful`, overall and every protocol category must satisfy
`completed == included`; overall quality must satisfy
`task_complete * 100 >= completed * 90`; every category must satisfy
`task_complete * 100 >= completed * 80`; and unauthorized effects, unauthorized
replays, and secret disclosures must all equal zero.
Integer cross-products or `Fraction` are mandatory—no float rounding. Both modes must
pass every completion, quality, and safety gate; one passing mode never masks the
other. Only approval-attested exclusions are outside `included`, and all remaining
transport/deadline failures stay in the denominator and therefore fail completion.

The selected default is `all_tools` unless stateful independently passes every gate
and its exact overall quality ratio is at least the passing All Tools ratio; because
both safety gates require zero, this also enforces no worse safety. `Ready` requires
all integrity, regression, scoring, safety, and review gates and no accepted
limitations. `Conditionally ready` requires those same gates plus one or more valid
accepted non-safety limitations. Every other state is `Not ready`. Canonical JSON and concise Markdown record named gates, blockers, selected mode,
limitation IDs/content/approval hashes, and decision-tool hash. `input_sha256` uses
only these exact keys for successfully loaded inputs: `freeze_manifest`,
`d38_accepted_result`, `d38_validation`, `d38_tool_attestation`,
`d39_verification_manifest`, `d39_verifier_tool_attestation`,
`decision_tool_attestation`, `human_operation`, `independent_review`, and optional
`non_safety_limitations`; a missing input omits its key and creates its named blocker.
`ReadinessDecision.decision_tool_sha256` equals only the independently regenerated
and detached-expected-validated decision attestation aggregate. Output contains no held-out text,
private paths, Git/network/publication/deployment side effects.

#### D40 implementation amendments (2026-10-03)

These amendments make the D40 contract above executable; they waive no gate and
change no threshold, pin or source inventory.

- **Loader failures reach the engine as fixed reasons only.** `decide_readiness`
  takes one additional keyword, `input_failures: dict[str, str] | None = None`,
  whose keys are `INPUT_KEYS` and whose values are the fixed reasons `missing`,
  `digest_missing`, `digest_malformed`, `digest_mismatch`, `invalid` and `binding`.
  Loaders raise `DecisionInputError(failures)` (a `ValueError`) naming every refused
  sibling at once; the CLI collects them so each mandatory input is still its own
  named blocker. No path, content or exception text enters the decision. A second
  keyword, `d36_tool_attestation: ToolAttestation | None = None`, carries the freeze
  publication's own D36 tool attestation from `load_freeze`, which now returns
  `(FreezeManifest, freeze_sha256, ToolAttestation)`.
- **Freeze refusal.** A missing or invalid D36 publication refuses without output
  (exit 2) instead of becoming a named blocker: without it no decision can name a
  candidate, and `freeze_manifest` is therefore always a passing row when present.
- **Fixed gate order (27 rows).** `decision_tool_attestation`, `freeze_manifest`,
  `d38_accepted_result`, `d38_validation`, `d38_tool_attestation`,
  `d38_upstream_identity`, `d39_verification_manifest`,
  `d39_verifier_tool_attestation`, `d39_candidate_binding`, `d39_command_inventory`,
  `d39_smoke_receipts`, `d39_integrity`, `upstream_tool_sources`, `protocol_coverage`,
  then for `all_tools` and
  `stateful` in that order `_completion`, `_quality`, `_category_completion`,
  `_category_quality`, `_safety`, then `human_operation`, `independent_review` and
  `non_safety_limitations`. `blockers` are exactly the failed rows in this order.
  `ReadinessDecision` itself rejects an outcome inconsistent with its gates and
  limitations.
- **Additional bindings.** `d38_upstream_identity` also requires
  `bundle.d36_trial_tool_sha256` to equal the publication's
  `d36_candidate_freezer_and_trial_host` attestation aggregate.
  `d39_candidate_binding` also requires `runtime_source_sha256` to equal the freeze
  `aggregate_sha256` (the verified runtime was materialized from exactly the frozen
  bytes). `upstream_tool_sources` requires every D38 importer and D39 verifier
  attested file that is also in `DECISION_SOURCE_PATHS` to equal the rehashed
  current decision-source fingerprint, so evidence produced by stale shared tooling
  (for example a pre-change `evidence_json.py`) cannot pass.
- **Coverage is re-derived, not trusted.** `protocol_coverage` re-checks token order,
  counts, bindings, the partition, derived category denominators, mode/category
  sums and per-row bounds (`task_complete <= completed <= included`, every safety
  count `<= included`). If it fails, every mode gate fails as "protocol coverage or
  accounting invalid"; no ratio is evaluated on an unusable topology.
- **Review records** are canonical JSON (`ReviewEvidence`, at most 64 KiB) without a
  detached digest; their canonical hash is recorded under `human_operation` /
  `independent_review`. A review of the wrong kind or candidate fails its gate.
- **Output location.** Attestation and decision outputs must be outside the
  repository root or strictly below its Git-ignored `release-evidence/` directory,
  decided lexically and again after resolving the deepest existing ancestor and the
  parent, without Git; no directory is created through a link into tracked source.
  Paths are first normalized to Win32 form (`\\?\C:\x` and `\\.\C:\x` to `C:\x`,
  `\\?\UNC\s\x` to `\\s\x`, trailing dots/spaces removed); other device
  namespaces are refused. The decision CLI passes every input file's directory as
  protected: the output may not equal or lie inside one (child, grandchild or via a
  link), so no D36/D38/D39 publication or review directory gains entries. The public
  `publish_decision(..., *, protected, attestation_path=None)` requires a non-empty
  tuple of protected paths, and the running-closure check compares normalized
  paths, so a `\\?\`-spelled `--repo-root` decides exactly like the plain one.
  Files are published with the shared no-replace `publish_immutable`. The decision
  output directory must be new or contain only this run's decision-tool attestation,
  so a decision can never be added to (and thereby invalidate) an input publication
  or replace prior evidence. If `decision.md` cannot be published, the
  `decision.json` written by the same call is removed.
- **Pre/post source binding.** The decision CLI rehashes the fixed source inventory
  before loading any evidence and again after deciding, and both times requires every
  loaded closure module (including the CLI itself) to be the attested file under
  `--repo-root`; a byte-identical decoy tree cannot lend its aggregate to other
  running code. Any failure refuses without output. Exit status is 0 only for `Ready` / `Conditionally ready`; `Not ready` and
  every refusal exit 2.
- **Import closure.** The engine, both CLIs and their transitive imports load only
  files in `DECISION_SOURCE_PATHS` (namespace packages `evaluation.scripts` and
  `scripts` have no initializer). Regression tests enforce this in a fresh
  interpreter and statically over every import statement, including function-local
  imports and package initializers.
- **Shared parser change.** `parse_canonical_typed` lives in
  `evaluation/evidence_json.py`, which is also in the D38 and D39 source
  inventories. Their attestation aggregates therefore change with this commit;
  D38/D39 evidence must be produced by the final committed tooling, never by an
  earlier attested aggregate.

### Internal HTTP APIs

#### Startup status

```text
Name: startup status
Endpoint: GET /api/startup
Authentication/authorization: unchanged local application boundary
Request body: none
Success: 200 StartupStatus
Errors: none for migration failure; route itself remains available
Side effects: none
```

`GET /api/health` retains existing fields and changes `status` to `"ok"` or
`"degraded"`. Database-backed routes return 503 `startup_unavailable` while degraded.
No other new public HTTP endpoint is introduced by D31–D40.

### Critical runtime flows

```mermaid
sequenceDiagram
    participant Main
    participant Mig as Migration runner
    participant DB as SQLite
    participant Status as Startup status
    participant Dispatcher
    Main->>Status: starting
    Main->>Mig: acquire_database_lease(url) non-blocking
    Mig->>DB: create exclusive lease file
    Main->>Mig: migrate_database(url, metadata, lease)
    Mig->>DB: classify version under lease
    alt legacy non-empty
        Mig->>DB: verified online backup
        Mig->>DB: additive migration + user_version=1
        Mig->>DB: integrity/schema/row verification
    end
    alt success
        Main->>Status: ready
        Main->>Dispatcher: reconcile and start
    else migration failure
        Main->>Status: migration_failed (fixed reason)
        Main-->>Dispatcher: do not start; retain lease while degraded
    else lease unavailable
        Main-->>DB: abort startup with database_lease_unavailable; no DB open/mutation
    end
    Note over Main,DB: An acquired lease remains held until database users stop at shutdown
    Main->>Dispatcher: close admission, cancel dispatcher, drain registry
    Main->>Status: starting (bounded shutdown message)
    Main->>DB: dispose pool and clear engine/sessionmaker
    Main->>Mig: release lease as final DB lifecycle action
```

```mermaid
sequenceDiagram
    participant Eval as Independent evaluator
    participant Freeze as D36 freeze + trial-tool attestation
    participant Runner as External D37 runner
    participant Protocol as Immutable protocol.json
    participant Host as External unlabeled host
    participant Candidate as Detached D35 candidate
    participant Import as External D38 importer
    participant Materialize as D39 runtime materializer
    participant Runtime as Verified read-only runtime
    participant Smoke as External D39 smoke producer
    participant Verify as External D39 verifier
    participant Decide as External D40 decision
    Eval->>Runner: corpus + separate approvals + freeze/tool hashes
    Runner->>Protocol: write complete opaque token set/bindings before trials
    loop doubly approved group/case/mode
        Runner->>Host: strict UnlabeledTrialCase
        Host->>Candidate: candidate-rooted subprocess
        Candidate-->>Host: observed persisted effects
        Host-->>Runner: redacted observation
    end
    Runner-->>Eval: sealed-evidence hash + bundle with complete protocol topology
    Eval->>Import: bundle + immutable protocol.json + attestations + detached digest
    Import->>Import: prove bundle topology identical to protocol
    Import-->>Decide: accepted triplet carrying self-contained topology
    Decide->>Decide: independently recompute topology and bounded equations
    Materialize->>Candidate: verify frozen bytes and clean snapshot
    Materialize->>Runtime: read-only copy + canonical evidence
    Smoke->>Runtime: independent bytes/permission recheck
    Smoke->>Smoke: separate smoke sandbox, then discard
    Smoke-->>Verify: bound canonical smoke manifest
    Verify->>Runtime: independent bytes/permission recheck
    Verify->>Verify: backend sandbox (commands 1-5), then discard
    Verify->>Verify: frontend sandbox (commands 6-9), then discard
    Verify-->>Decide: detached manifest + detached verifier attestation
    Decide-->>Eval: canonical decision; no release side effect
```

### Error handling and observability

- Negative-intent veto is a normal dismissed response, not an exception.
- Validation failures remain 422 with fixed payloads; state conflicts remain 409;
  database busy remains 503/`Retry-After: 1`; degraded startup is
  503/`Retry-After: 5`.
- Migration/lease errors carry internal cause chaining but only fixed reason/message
  over HTTP. Lease contention is non-blocking and never retries. Backup and lease
  paths are logged only as repository-relative/storage-relative aliases, never raw
  user paths.
- No automatic retry occurs for migration, unknown remote work, held-out trials, or
  evaluation import. The evaluator explicitly resumes an incomplete D37 run with the
  same manifest.
- Logs may contain correlation ID, operation ID/version, pseudonymous project/request
  aliases, reason code, candidate ID, counts, durations, and exception class. They
  must not contain free text, model request/response bodies, prompts, source scripts,
  secrets, provider headers, held-out labels, or absolute private paths.
- D37 immutable protocol/trial/bundle files use same-directory fsynced temporary files
  plus atomic no-replace hard-link publication; D37 mutable partial status and existing
  D39 contracts retain their separately documented replacement behavior. Partial D37
  evidence remains inspectable after interruption.

### Security design

Trust boundaries are browser input, local-model output, separately mounted held-out
material, imported evaluator aggregates, filesystem databases/backups, and external
providers. Existing loopback validation and registered-callable dispatch remain.
D31 adds defense-in-depth but does not make model text trusted. Confirmation tokens,
request IDs, revisions, target binding, and current readiness remain mandatory.

Migration accepts only configured file-backed SQLite URLs and never a path supplied
by an HTTP request. The application-lifetime lease excludes a second application,
migration, or offline restore process; all migration operations validate that lease
before database I/O. Backup names are generated, resolved under the DB parent, opened
without shell invocation, and atomically replaced. Offline restore acquires the same
lease non-blocking and cannot run while a ready or degraded application is live.
Freeze/tool paths are lexical repository-relative paths and cannot escape their
roots. Strict bounded canonical JSON loading validates detached hashes before parsing:
small manifests retain their existing finite limits, D37 protocol/result artifacts use
their proven 64/128 MiB structural caps, and corpora retain the existing case-loader
limits. The D37 host boundary accepts only the recursive strict unlabeled model and evaluation output
never includes source request text or labels. D39 executes from isolated verifier-owned
temporary roots and proves the detached candidate snapshot unchanged. D31 additionally
requires zero content-level changes in the reopened `external_calls` journal and an
import-blocked runner/operation graph with no worker, pipeline, or provider modules;
these are precise journal/dependency guarantees, not a general network sandbox.
Detached hashes detect transfer modification but do not cryptographically authenticate
evaluator/reviewer identity; explicit evaluator identity and content-bound human and
independent review gates supply the recorded trust decisions. D38 and D40 treat the
D37-owned strict shared models as untrusted input but MUST validate them without
redeclaration, subclassing, normalization, inferred omissions, or alternate
approval, exclusion, completion, safety, transport, identity, or sealed-evidence
fields. The accepted bundle carries the complete opaque protocol topology, not merely
included/excluded subsets, so D40 can detect selective topology removal independently
of D38. Strict finite count bounds, bool rejection, denominator-derived upper bounds,
and checked sums/products prevent negative, oversized, or arithmetic-confusion inputs
from reaching readiness equations.

### Test design

- **D31:** table-driven host-guard unit tests; strict single-target validation; API
  validation/log redaction; reopened content comparison including mandatory zero
  external-call-journal changes; clean-process import blocking for worker, pipeline,
  and provider dependencies; paired All Tools/stateful positive controls; bounded
  real-model probe reported separately.
- **D32:** thread/session and spawned-process barriers; assert one winner and complete
  persisted invariants after reopening the DB.
- **D33:** crash matrix at each durable boundary; full project recovery fields;
  actual FastAPI lifespan/dispatcher shutdown cancellation; concurrent submit versus
  close with no post-close task/liveness marker; repeated lifespan reopen before
  dispatcher; restart twice to prove state stability; remote POST counter must remain
  one; valid-checkpoint submit-once/completion through `JobRegistry`; invalid-
  checkpoint non-dispatch; subtitle mutation/deletion at the post-rename artifact
  boundary with transactional rollback; ORM flush/commit failure proving no artifact
  row or per-job manifest file and only the permitted video orphan; complete DB
  `manifest_json` on success; no artifact `manifest.json` on success; and
  rename-before-commit orphan replacement restricted to the exact unreferenced job
  history path with referenced/current artifact protection and stable replay. The
  retrieval-index manifest tests remain unchanged and continue to cover that separate
  subsystem.
- **D34:** empty/current/upstream/D30/partial/newer/corrupt fixtures; frozen explicit
  upstream/D30 SQL independent of current metadata; SQLite-compatible ASCII-only
  identifier folding for classification, missing detection, and semantic-reference
  presence checks; actual-spelling quoted SQL; preservation of distinct unknown Unicode
  identifiers; pre-DDL rejection of ASCII-case-colliding duplicate known identifiers;
  scratch-metadata affinity equality for every existing known column and rejection of each affinity
  mismatch/name collision; exact metadata-derived ordinary/unique index sets through
  case-insensitive `index_list/index_info`; additive restoration after each of the three
  unique columns; duplicate enforcement; malformed-v1 missing ordinary/unique rejection;
  preservation of weaker and unrelated existing indexes; preservation of unknown extra tables/columns; nested-path
  parent creation before lease; exact scratch-PK order and malformed/missing legacy PK
  rejection; language receipt ownership and explicit-null reciprocal turn checks;
  pre/post-publication backup hash equality, integrity, exact critical-table row counts,
  canonical pre/post PK identity digests, canonical target-bound metadata, declared FK
  checks, every enumerated ID-reference check, and intentional receipt non-FK survival;
  missing/released/mismatched lease rejection; wrong-target, escaping, symlink, special,
  noncanonical, schema/identity/reference-incompatible restore rejection; stale
  WAL/SHM/journal removal only after validation; final reopen verification; spawned-process
  app-vs-app and app-vs-restore exclusion; non-blocking contention with unchanged DB
  bytes; degraded-state lease retention; forced lease replacement/release races;
  descriptor/path exact-payload checks and in-place tamper rejection; lease loss
  immediately before each backup publication with no retained partial;
  redirected/symlink/reparse/non-directory backup-root rejection before writes;
  graceful release/reacquisition; stale-lease refusal; successful stopped-app restore;
  non-ready `get_db()` rejection between lifespans; pool disposal before lease release
  on ready and degraded shutdown; offline restore between lifespans followed by a
  second lifespan reading restored bytes/state instead of the old pooled inode; and
  repeated lifespan startup with a fresh pool.
- **D35:** API contract tests and Vitest interactions cover every job and project-level
  code/action, blockers older than the 100-row history window, unresolved old remote
  calls, immediate action revalidation, migration backup availability propagation,
  stale refresh, duplicate click, DOM-order tab/Enter behavior,
  role/status text, and structural narrow-layout containment. The final gate passed
  1300 backend tests and 150 frontend tests plus Ruff/build/lint. Installed Chrome
  passed 18 synthetic-state checks at 390x844 and 1440x900, including real Tab/Enter,
  one POST from duplicate activation, and no horizontal overflow. This is automated
  technical evidence, not human acceptance.
- **D36:** strict canonical candidate control plus detached digest; exact D35
  parent/subject/cleanliness; commit-timestamp-derived UTC `created_at`; byte-identical
  manifest generation on repeated identical inputs; changed allowlisted byte;
  excluded later tooling, secret/cache paths; separate source attestation; recursively
  strict `UnlabeledTrialCase`; nested label/extra rejection; candidate non-mutation;
  anchored hidden staging with retained child descriptors; mocked and native Windows
  no-delete handle behavior; POSIX `dir_fd` and Linux `renameat2(RENAME_NOREPLACE)`
  coverage where available; concurrent final-winner preservation; no final-path writes;
  no identity-blind cleanup; retained random staging on failure; token-valued state
  rejected as incomplete; canonical completion bytes/hashes required; no token bytes in
  successful state; and exact two-artifact/one-state successful layout.
- **D37:** synthetic cases only; domain-separated opaque case/category token generation
  with no raw IDs/text/labels in protocol or bundle; non-empty bounded complete sorted
  protocol case/category sets and exact one-case/one-category bindings repeated
  identically in the bundle; non-empty included set, at least one included token per
  declared category in each mode, and exact included/excluded token lists with deterministic
  `both_not_approved`/single-missing-approval reasons;
  immutable run `protocol.json`; D36/D37 tool-hash binding; group/case isolation;
  exact mode and opaque-category symmetry; overall and per-category task-completion,
  unauthorized-effect, unauthorized-replay, and secret-disclosure totals; overall
  transport/deadline failures; evaluator role/name/time; candidate/freeze/corpus,
  protocol, D36 trial-tool, D37 evaluator-tool, and sealed-evidence identities;
  explicit non-negative finite bounds for every category/mode count; bool, negative,
  oversized, denominator-exceeding, sum-overflow, and equation rejection; canonical
  opaque receipt/request/turn preservation under additions; same-count replacement and
  prior-receipt mutation rejection; strict direct-call event parsing; primary
  500-with-completed, false-executed, and stray-reason rejection; nested failure,
  wrong replay/conflict/confirmation status, execution and proposal rejection; full
  bounded job progress/fingerprint/snapshot/plan/recovery/error projection and
  cancellation-only mutation enforcement;
  switch-target response binding; confirmation state-hash and duplicate-response
  binding; partial resume; mismatch rejection; bidirectional output/protected-root
  rejection including a workspace-parent output; retained Windows/POSIX candidate
  identity, equivalent checkout replacement, and swap/restore execution through only
  the anchored inode; token-key final-`fstat` and descriptor-close fault zeroization;
  early parent exit with a pipe-holding descendant, cancellation, bounded drain/
  teardown, and no hang; and output redaction.
- **D38:** raw detached bundle hash before parse; exact protocol bytes; shared-schema
  import without forks; exact equality between protocol and bundle case count/tokens,
  category count/tokens, and case/category bindings; uniqueness, sorting, disjointness,
  exact token-union equality, non-empty overall/per-category coverage, typed bounded
  reason/count/category accounting, and all hashes; all upstream identity/tool bindings; mode/safety
  accounting; evaluator identity/time; atomic accepted triplet;
  and proof that sealed evidence is never opened.
- **Shared boundary prerequisites:** canonical JSON duplicate/nonfinite/Literal primitive
  rejection, LF/no-LF hash distinction, strict JSON array/Python tuple behavior,
  artifact-specific cap+1 rejection before parse, streaming index/blob identity checks,
  and single-pass finite topology accounting. Blueprint rows are acceptance tests,
  not claims that this audit ran them.
- **D39:** separate materialization command/function; read-only verified runtime and
  external writable environments; materialization/smoke candidate-runtime binding;
  exactly one fresh backend sandbox for commands 1–5 with persistent uv state, one
  fresh frontend sandbox for commands 6–9 with group-local persistent `node_modules`,
  and one separate fresh smoke sandbox; independent runtime rechecks around each group
  and sandbox tracked-source rehashes before/after every command or smoke stage; exact
  nine ordered name/argv entries once each with separate evidence and zero exit codes;
  embedded canonical smoke content/hash with all six mandatory hashes; external
  cwd/root enforcement; tracked and ignored candidate drift around every group;
  cleanup on success/failure/interruption; command failure propagation; smoke/secret scan;
  canonical verification manifest; separate verifier source attestation; and real
  FFmpeg/browser smoke with fake providers when the environment permits.
- **D40:** generated/validated exact-file decision source attestation with detached
  expected aggregate; detached hashes for every D38 artifact and both D39 artifacts;
  independent exact-nine D39 command/exit inventory, smoke hash/content, and all
  candidate/materialization/verifier bindings; cross-binding verification-manifest
  hash, verifier-tool hash, D35 commit/freeze/candidate, and all upstream D37/D38
  identities; independent reconstruction of the complete bundle-carried topology,
  included/excluded partition, category denominators, finite bounds, checked equations,
  and non-vacuous overall/category coverage without `protocol.json`; exact 89.99/90 and
  79.99/80 boundaries for both modes; per-mode/category completion; zero effect/replay/
  disclosure; one-mode failure; JSON-array/Python-list decision collections with
  deterministic ordering; exact content-bound review and limitation evidence; mode selection; conditional
  restrictions; missing-input Not-ready output; and no external side effects.

Unit tests use fake providers and synthetic text. Held-out files are never test
fixtures in this repository. Full verification remains:

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

### Configuration and secrets

No application/runtime secret is added. D37 alone receives an evaluator-owned corpus
token key file outside every repository. The key contains exactly 32 raw random bytes; only the external file path may appear
in CLI process arguments, while key bytes and
their digest never enter protocol/result/evidence/log output. Tests use an explicit
synthetic key. D34 derives backup/lease locations from `DATABASE_URL`; no HTTP
or environment override is added. The application lifespan owns the lease; offline
restore has no wait/force override and operators may remove a stale file only after
confirming no application or restore process is live. Release/evaluation scripts
require explicit CLI paths and refuse outputs inside tracked source except ignored
`release-evidence/`.
D37 receives model/index settings already documented for D30 and records only
allowlisted non-secret values. The explicitly paired external synthetic embedding
profile/base-URL override described above is not an inherited setting or case field;
missing/invalid pairing fails before a worker. Model configuration currently binds
only the identifier; independent actual-provider provenance is required before real
execution. D39 uses the fixed group-local clean environment, version lane and worker
limits above; missing optional extras, native launcher/build support, or browser
protocol methods fail instead of falling back. The evaluator supplies corpus, ledgers,
and output paths directly; `.env` is not modified.

### Dependency-safe implementation roadmap

#### Step 1 — D31 adversarial safety

Create `intent_guard.py`, adversarial contracts/corpus/runner, and focused tests;
integrate the veto and fixed exception redaction; run D31 focused, language,
comparison, API, Ruff, and frontend regression checks. Produce
`work-report-31.md`. Do not begin D32 until D31 behavior is reviewed.

#### Step 2 — D32 race matrix

Add process/session race tests around existing durable boundaries. Change production
code only for demonstrated invariant failures. Run focused tests repeatedly plus the
full backend suite and record winners/losers and SQLite limitations.

#### Step 3 — D33 recovery matrix

Add deterministic dependency failures and isolated process termination. Repair only
demonstrated crash gaps while retaining unknown-remote conservatism. Verify a second
restart is a no-op and prior artifacts remain.

#### Step 4 — D34 explicit migration (implemented and verified)

Create migration contracts, application-lifetime lease, backup, schema, runner,
startup state, and startup API. Build a scratch current-schema DB from registered
metadata; classify and detect missing known identifiers with SQLite-compatible ASCII-only
folding, retain actual spellings for quoted SQL, reject ASCII-case-colliding duplicate
known metadata before DDL, and require exact affinity for every existing known column. Pass metadata into every critical snapshot, derive exact ordered
PKs only from scratch current metadata, reject altered/missing legacy PKs, capture and compare
critical-table row counts and canonical PK identity digests; validate every enumerated
ownership/reference ID; and reconcile exact metadata-defined ordinary/unique index
sets only after additive columns exist, preserving all existing indexes and rejecting
incomplete v1 schemas. Preserve intentional receipt non-FKs and unknown extras. Move reflective schema mutation from `db.py`; acquire the lease before
migration, require it for migration operations, retain it through ready/degraded
lifespan, and after dispatcher/registry drain mark non-ready, dispose and clear the
engine/sessionmaker without DDL, then release through an identity/token-validated
atomic tombstone as the final database lifecycle action. Publish a canonical metadata sidecar only after temp backup
integrity/identity/hash/fsync validation and verify both atomic publications. Make
offline restore acquire the same lease non-blocking, require registered metadata and an
exact target-bound backup under `.backups`, validate hash/schema/identity/references,
remove stale SQLite journals under repeated ownership assertions, and fsync/reopen
verify the final target. Add historical fixtures, spawned-process exclusion and forced
lease-replacement tests, path/wrong-target/WAL/journal restore tests, backup/restore
instructions, and degraded-startup tests.

#### Step 5 — D35 recovery UI

Extend job/startup DTOs, add RecoveryStatus/StartupStatus, update controls and client
types, then run component/browser tests against real API states. Update the operation
module note because public recovery contracts change.

#### Step 6 — D36 freeze the D35 parent with external tooling

After the clean D35 delivery commit exists, create its strict canonical candidate
control and communicate the expected hash separately. Derive manifest `created_at`
only from the D35 integer commit timestamp normalized to UTC and prove repeated
freezes with identical inputs produce byte-identical manifest bytes. In a later
tooling commit add
`evaluation/final_protocol.json`, recursive strict unlabeled contracts, the external
single-case host, and `evaluation/release_candidate` freezer. Test label exclusion and
candidate non-mutation. The freezer MUST create a random hidden staging directory under
the validated output root, acquire its POSIX or Windows directory anchor immediately,
create and retain all fixed children through that anchor, and transition the fsynced
random state token to canonical completion bytes last. It MUST atomically publish the
whole directory with platform true no-replace, perform no final-path write/readback,
and perform no identity-blind cleanup deletion or move. Freeze only an isolated detached
D35 checkout; emit the ignored
manifest and separate D36 tool attestation. Never name the D36 tooling commit as
candidate behavior.

#### Step 7 — D37 canonical protocol, shared schema, and blinded evaluator

The single strict D37-owned D37–D40 result/protocol schemas already exist. Do not
repeat an obsolete RED premise or recreate them. Before D38 implementation, execute
blueprint orders 1–2: pure canonical parser, streamed index hashing, exact literal
rejection and single-pass topology accounting, paired external loopback-profile host
configuration, and new synthetic boundary tests. `evidence_json`/runtime helpers cannot
import result/protocol/runner/app. Extend only documented optional host/runner parameters,
keep D24 event meanings and shared model inventories unchanged, and rerun focused D36/D37
verification after source corrections. These prerequisites and exact pinned-worker
synthetic integration are now implemented; later units and independent review remain
pending. Direct schema/clean-flag guards also cover the reused freeze/control/marker,
unlabeled-case, observation, trial-record, protocol and result boundaries without adding
fields. Exact pinned integration is separate evidence, never implied by stub tests. Commit tooling before source attestation; refresh
D36 and pin the final tooling boundary before any real run. The original D37 construction
scope below is retained as context, not an instruction to overwrite existing files.

Establish the single strict D37-owned D37–D40 result schema. Add separate human
and independent approval hashes, run-protocol hash, D36 trial-tool and D37 evaluator
hashes, domain-separated opaque case/category tokens, non-empty bounded complete sorted
protocol case/category sets and exact bindings repeated identically in the bundle, a
non-empty included set with at least one included case per declared category/mode,
exact sorted included and excluded token collections, and deterministic both-/single-
missing approval reasons, plus explicitly bounded non-negative overall/category
completion and effect/replay/disclosure counts, bounded transport/deadline failures,
checked equations, evaluator identity/time, and sealed
evidence identity. Prove maximum protocol/result topology byte bounds and apply the
same 64/128 MiB caps to writer, readback, and resume paths. Implement filesystem and
publication in `blinded_io`, process/anchor behavior in `blinded_runtime`, and keep
projection/attestation/aggregation in `blinded_runner`. Exclusively write immutable run
`protocol.json` before trials, project approved cases to `UnlabeledTrialCase`, preserve
the D24 selection-only original-request replay, suppress candidate-worker output, then
implement scoring, partial resume, source attestation, and sealed evidence using
synthetic fixtures only. The implementation process never accesses real held-out material.

#### Step 8 — D38 bound aggregate import

Prerequisites: shared parsing/host corrections and committed D37 schemas; genuine
synthetic pinned-worker proof remains required before claiming integration acceptance.
Create `result_import.py`, import CLI and focused synthetic tests; do not modify app,
candidate or locks. Verify focused D38/D37 tests and Ruff with the existing environment
without resync. Acceptance: unchanged canonical accepted bytes, exact twenty bool-true
checks, a no-replace complete accepted triplet and no sealed-data access. Import D37
models unchanged. Validate detached bundle hash before parsing, validate exact D37
protocol bytes, bind candidate/freeze/corpus/separate approvals/
D36 trial tool/D37 evaluator tool and protocol model/index/category/case identities,
require exact protocol/bundle identity for complete case count/tokens, category
count/tokens, and case/category bindings, and enforce uniqueness, sortedness,
disjointness, exact protocol-token union equality, finite count bounds, checked
arithmetic, non-empty overall/per-category included coverage, all declared counts/
typed-reason/opaque-category accounting, all bound hashes, and complete
two-mode accounting. Atomically emit the canonical accepted
bundle, validation record, and separately attested D38 importer; never open detailed
evidence.

#### Step 9 — D39 isolated exact-candidate verification

Prerequisites: fixed shared parser/models and versioned native-launch/environment
blueprint. Create `smoke_contracts.py`, `runtime_materialization.py`,
`release_verification.py`, `browser_smoke.py`, internal `d39_candidate_smoke.py`,
three public D39 CLIs and focused tests in
that dependency order (pure contracts -> ownership -> owned execution -> smoke ->
final verifier). Verify focused D39 tests/Ruff first, then blueprint orders 3–6 in
fresh groups; do not count absent extras, browser or FFmpeg as a pass. Acceptance:
exact canonical/native nine-command inventory, six fully bound typed receipts,
tracked-source/candidate invariance, and ownership-verified cleanup. Implement the
fixed verifier under `evaluation`, never `app`. First expose the
separate `materialize_candidate_runtime` command/function to create a verified
read-only tracked-byte copy plus canonical materialization evidence. Put every
writable environment/cache/output outside it. Bind browser/media smoke to that exact
candidate/runtime instance. Have the final verifier consume the materialization
record and detached hash, then independently rehash runtime bytes around exactly
three fresh external groups: one backend sandbox for ordered commands 1–5, one
frontend sandbox for ordered commands 6–9 with `node_modules` retained only through
that group, and one separate smoke sandbox. Rehash each sandbox's tracked source
before/after every command or smoke stage, preserve separate evidence for every one of
the exact nine commands, validate and embed the canonical smoke manifest, and run
migration/restore, both-mode startup, browser/recovery, real FFmpeg fake-provider,
documentation, and secret scans. Prove tracked and ignored candidate snapshots unchanged and clean all
runtime/temp roots in `finally`, failing closed on cleanup failure. Emit
`VerificationManifest` and a separate verifier
source attestation. Candidate failure returns to Step 6 and reruns affected D37–D39;
verifier-only changes require a new verifier hash and complete D39 rerun.

#### Step 10 — D40 detached, cross-bound readiness decision

Prerequisites: implemented D38 and pure D39 contracts, fixed import closure and a
committed tooling checkout. Create `release_decision.py`, attestation CLI, decision
CLI and focused synthetic tests. Verify focused D40/D38/D39 tests and Ruff; ban
subprocess/network during decision tests. Separate source attestation may use Git;
the decision operation may not. Acceptance: exact thresholds/bindings, tuple input /
list outputs, and valid named Not-ready results for all missing mandatory evidence.
Actual baseline remains Not ready without real independent aggregate and review;
synthetic success is not release acceptance. Require D36; the three D38 artifacts;
D39 verification manifest; D39 verifier source attestation; generated/validated D40
decision source attestation; human operation;
and independent review. Require detached expected hashes for each D38 and D39 file
and the detached expected D40 source aggregate before parse/decision, then cross-bind their actual hashes,
verifier/importer/runner/trial tool hashes, D35 commit/freeze/candidate, protocol,
corpus, and approval identities. Independently reconstruct and validate the complete
bundle-carried opaque topology, partitions, category denominators, and bounded
arithmetic without loading `protocol.json`. Emit deterministic JSON-array/Python-list
gates, blockers, and accepted limitations. Apply the exact completion/90% overall/80%
per-category/zero-safety gates independently to both modes. Select stateful only when
it passes and its exact overall ratio is at least passing All Tools. Accept
conditional status only from candidate-bound, content-hashed, artifact-approved
non-safety limitations. Emit canonical JSON/Markdown and named Not-ready blockers
without Git, network, publication, or deployment side effects.

### Implementation Instructions for Coding Agent

1. Implement roadmap steps sequentially unless the DTD explicitly permits a test-only
   parallel activity.
2. Do not skip prerequisites or start D32 before D31's report and review gate.
3. Treat this DTD as the implementation contract for D31–D40.
4. Do not replace dependencies, APIs, schemas, boundaries, thresholds, or algorithms
   silently.
5. Do not invent a material architecture absent from this DTD.
6. Run focused verification after each step and full checks at each work-unit gate.
7. Update tests with implementation and preserve unrelated repository changes.
8. Preserve the documented import direction; production `app` never imports final
   evaluation or release tooling.
9. Report incompatible APIs, versions, contradictions, or failed acceptance criteria
   rather than weakening a gate.
10. If implementation evidence invalidates this contract, update the DTD before
    continuing with the conflicting design.
11. Keep held-out access, publication, deployment, tags, and cloud calls deferred.
12. Do not claim human or independent acceptance without content-bound evidence.

## D30 functional candidate boundary

Connection metadata reports the host-configured all_tools/semantic/stateful mode
without loading an index or exposing paths. The UI displays configuration rather
than asserting successful search. An isolated demo startup script selects ordinary
configuration before importing the application, then serves the built frontend
on loopback. It never imports the D29 comparison selector or injects experiment
state into product prompts. Search, parser, guards and execution remain separate.
See `plan-c/work-unit-30.md` for acceptance and outstanding decision boundaries.

## D29 comparison boundary

`evaluation.comparison` composes the existing Interpreter/SemanticInterpreter;
`evaluation.comparison_runner` supplies isolated databases to the unchanged
LanguageOperationService and registered OperationService. A structural candidate
interpreter protocol keeps application imports independent of evaluation code.
All modes share a frozen, allowlisted raw state snapshot, parser, value/reference
guards, final readiness, confirmations and transactions. Only candidate membership,
readiness presentation and the documented search stages differ. Experiment-only
CLI configuration enables Hard Filter; ordinary application configuration does not.
Review follow-up reporting excludes host-only/unmeasured trials from model timing,
separates deadline from transport failures, and retains partial reports after a
started experiment fails. Submit scoring additionally checks project status and
the full settings-history sequence. Reanalysis of immutable evidence is labelled
as offline rescoring, not new inference or a new acceptance run.
See `plan-c/work-unit-29.md` and `plan-c/comparison-modes.md`.


## D28 provisional candidate-state boundary

`operations.candidate_readiness` uses the existing target/busy check without
constructing an executable request. Immutable candidate DTOs belong to operation
contracts. Language orchestration supplies a read-only snapshot callback to the
semantic interpreter; the latter still cannot import DB/execution modules. Each
stage includes exact-version annotations without changing rank/membership. The
interpreter accepts only annotations for its offered candidates and selected target.
The language read-only refresh endpoint reads current state for recorded candidate
IDs, never runs a model/index/executor and never overwrites the old response.
`evaluation.readiness_filter` is an experiment-only consumer of these snapshots,
not imported by product modules. See `plan-c/work-unit-28.md`.

## D27 semantic interpretation boundary

`app.retrieval.ranking` adds read-only exact cosine ranking. The optional
`onnx_embeddings` adapter loads hash-pinned E5 data locally and uses masked mean
pooling with no silent truncation. `app.semantic_interpretation` composes retrieval
and the existing read-only interpreter; it cannot import a DB or an executor.
Language orchestration may inject this component after the durable claim and
before the unchanged guards/core. Source freshness is checked before and after
inference; fallback never widens static scope. See `plan-c/work-unit-27.md` for
the bounded5→8→full-scope policy, deadline and diagnostic contract. Index path
configuration is opt-in; no `.env`, default flow or comparison-mode UI changes.

## D26 index boundary

`app.retrieval` reads operation contracts/catalog only. `sources` extracts public
description/example/input documents and exact app/capability bindings from
`operations/search_scope.json`. `embeddings` returns normalized finite vectors
through a bounded loopback HTTP adapter. `builder` writes a content-addressed
bundle and atomically replaces its manifest; only `scripts.operation_index`
invokes it. `reader` checks current source hashes, model profile and regenerated
documents, then filters exact scope without inspecting live readiness. No package
imports execution, handlers, DB, evaluation corpora or language orchestration.
Existing application entry points do not import retrieval in D26.

This is index lifecycle infrastructure. D27 supplies cosine ranking and candidate
fallback; D28 adds state/readiness presentation; D29 connects comparison modes.
The developer CLI validates local weight bytes against the profile fingerprint;
the HTTP response must match the model ID and dimension. The local serving process
is trusted to use those weights: an API model name alone cannot attest its bytes.
No new dependency, migration or runtime configuration default is introduced.

## D25 diagnostic and development-probe boundary

See `plan-c/work-unit-25.md`. Language orchestration records additive timing and
candidate metadata in its existing response JSON; receipts still own effects.
Its observability helper emits a fixed allowlist, with process-local HMAC aliases
for identifiers, and never logs free text or exceptions. The interpreter remains
read-only. The frontend retains the frozen request while showing elapsed waiting
and the user-selected30-second notice separately from video progress.

The new development probe is an explicitly invoked script with loopback transport,
not a product dependency. It reads only approved development cases through the
D24 gate and records synthetic proposal accuracy separately from core effect tests.
The existing offline `scripts.evaluation_cases` still has no inference/network path.

D25 also changes model-facing argument property presentation. Settings output
uses three equivalent schema alternatives (alphabetical, common settings first,
and canonical order) because local constrained decoding can depend on key order.
Every alternative has exactly the catalog's fields and constraints. No candidate
is removed; the core schema, validation, transactions and generation permission
are unchanged. Probe manifests fingerprint the ordered payload and response
schema as well as the prompt/catalog/corpus. This is output compatibility, not
retrieval or final-evaluation scoring. See the D25 report for measured tradeoffs.

## D24 offline evaluation tooling

`backend/evaluation` owns data validation, content fingerprints, review ledgers
and offline review rendering. It reads operation metadata for label-schema checks;
the application never imports it. `scripts.evaluation_cases` has no interpreter,
database, provider or network execution path. Development examples remain in
`evaluation/d24`; held-out text/labels live outside the implementation workspace.
Only group/count/hash and review-status metadata returns to the implementation
agent. Approved subset manifests require separate, matching human and independent
AI ledgers. Later runners must use that eligibility gate; old development probes
do not become approved final evaluators automatically.

## D23 connection observability

See `plan-c/work-unit-23.md`. A separate read-only language connection route uses
the interpreter's transport URL validation and a bounded model-list reader. It
does not receive project input, invoke inference, select models or access the
operation executor. The UI shows only an allowlist of connection settings and
fixed status messages. Development probes own metrics and synthetic evidence;
production request/model bodies are not added to application logs.

The user authorized fixes for observed real-model accidental saves. Language
orchestration now checks supplied subtitle quantities, other numeric settings,
explicit speech-speed presence and known pending compound fields before creating
an executable request. Untrusted prior proposals may veto a partial save but
never provide executable arguments. Uncertain values ask; no automatic rewriting
or additional semantic repair call is added. LocalChatAdapter also rejects a
missing/mismatched response model ID before returning content to the interpreter.

## D22 compound intent and repair

See `plan-c/work-unit-22.md`. The interpreter still has no execution capability.
Version 2 of settings.update normalizes relative arguments in the core writer
transaction, then uses the existing settings handler. Language orchestration
persists generation intent and reconstructs a separate revision-bound generation
request from the settings receipt. Both receipts remain authoritative; no model
call or provider call runs inside a database writer transaction.

## D21 connection audit

See `plan-c/work-unit-21.md`. The settings editor already submits
`project.settings.update` through the durable core, as does language orchestration.
The legacy PATCH also uses `validate_settings` and `apply_project_settings`.
Verify specialized pronunciation validation and stage invalidation through these
entry points without adding a second settings writer or duplicate field handlers.

## D20 acceptance boundary

See `plan-c/work-unit-20.md`. Exercise existing production APIs, dialogue/core and
the managed generation pipeline in isolated synthetic storage. Fault injection
belongs only to the test runner. Acceptance fixes must preserve the dependency
direction and the immutable request/revision/confirmation contracts below.

## D19 dialogue boundary

See `plan-c/work-unit-19.md`. A dialogue ledger and orchestration helper retain
bounded context separately from immutable operation receipts. Models store data;
only orchestration reads it into a read-only interpretation context. An optional
server-injected core guard checks dialogue invalidation inside the same writer
transaction as effects, after replay lookup. No reverse import or model-defined
callable is permitted. Frontend continuation mode always creates a new request ID.
The language pronunciation helper binds proposed readings to supplied utterances
and merges additions into stored entries without exposing the existing glossary
to the model. Core revision/readiness validation still authorizes the final save.
`plan-c/work-report-19.md` records the final tests and actual model/browser/video
evidence. The additive `language_turns` table contains local utterance text; old
language records without a turn keep their replay behavior but cannot be continued.

## D18 UI boundary

See `plan-c/work-unit-18.md`. Frontend language contracts/client, durable session
storage, a request lifecycle hook and result presentation are separate modules.
The project page composes the panel with existing controls/history. No new model
interpreter, executor, retrieval or automatic generation path is introduced.
Server receipts and revision history own displayed effects; model prose does not.
Unknown HTTP delivery refreshes observed project/history state but never implies a
successful request. Explicit resend retains the exact input; reload only looks up.
`plan-c/work-report-18.md` records implementation and executed verification.

## D17 orchestration

See `plan-c/work-unit-17.md`. `language_operations` depends on interpretation,
operation metadata/core and the new language-request ledger. API routes compose
these parts; no reverse import into orchestration from operations or shared
services is permitted. The interpreter continues to have no execution capability.
Interpretation runs outside writer transactions. Core receipts own committed
effects and recover the gap between core commit and orchestration acknowledgement.
The reference-binding check rejects model-guessed job/history IDs before preparing
an executable request. It retains the model's parsed proposal and returns a separate
application clarification. Generation proposals always need a confirmation bound
to the stored request. See `plan-c/work-report-17.md` for verification and API use.

## D16 model boundary

The current requested addition is specified in `plan-c/work-unit-16.md`.
The new `app.interpretation` package depends only on operation metadata/schema,
its own contracts, and an injected transport. It must never depend on operation
execution/bootstrap/handlers, database/models, or workers. A synthetic CLI probe
owns HTTP transport lifetime. D17 separately adds orchestration/API routes, while
this interpreter has no execution capability. D18 adds the product UI above.
Local HTTP structured output support is checked against official LM Studio docs
and an actual synthetic probe; new SDK assumptions are not introduced.
The verified local configuration explicitly disables thinking for the bounded
768-token output (`reasoning_effort: "none"`). This setting is opt-in at the
transport boundary and does not weaken schema validation or add retries.
Actual test outcomes and limits are in `plan-c/work-report-16.md`.

## Current implementation contract: D12–D15

The user's D15 request and answered initial product questions authorize the work in
`plan-c/work-unit-12-15.md`. It supersedes D11's full-pipeline-only dispatch,
interrupted-job failure policy and deferred history/control statements below.
D11 replay/transaction guarantees and dependency direction remain mandatory.
Executed verification and G2 judgment are in `plan-c/work-report-12-15.md`.
`generation_plan` declares dependencies, `generation_snapshots` freezes inputs,
`artifact_store` verifies/publicizes immutable outputs, and `external_calls` journals
provider effects. API/history and operation handlers use these services; services
never import API/operations. Project/job ID reservations prevent reference reuse.

## Historical amendment: D11 (2026-09-19)

Read `plan-c/work-unit-11.md` for the approved-by-task D11 implementation contract.
It extends the G1 design below with durable receipts, integer project revisions,
transaction-owned commits, relative subtitle changes and a transactional pending
generation job. It supersedes G1's timestamp token and deferred-request sections.
The existing dependency direction remains: models and shared services never import
operations; the dispatcher depends on persisted models and the existing worker.
The user request authorizes this separate D11 change; units 01–10 records remain
historical evidence. No claim of a separate human design-review meeting is made.

## 1. Document Control

- **Project:** BlockVideo state-aware common operation foundation
- **Status:** Implementation-ready
- **Delivery mode:** Standard
- **Specification:** `specification.md`
- **DTD:** `docs/DTD.md`
- **Updated:** 2026-09-17
- **Baseline:** `main` at `00ae7cb3333d226bee97c742c7aa1db1dd81203c`
- **Scope:** Work units 01–10 only
- **Open blockers:** None for the typed core. Real VOICEVOX generation remains optional because the fake provider is the approved deterministic sample path.

## 2. Technical Scope

### In scope

1. Record the verified environment, baseline, code map, product decisions, commands, and unit evidence.
2. Add a synthetic, non-sensitive sample project payload and script that run with fake providers.
3. Add a typed operation core for two representative operations:
   - `project.subtitle-font-size.set`
   - `project.status.get`
4. Keep versioned operation definitions in Git-managed JSON.
5. Reject malformed definitions, duplicate IDs, unknown handlers, invalid targets, invalid values, stale state observations, and execution while a project has a live generation job.
6. Expose a thin structured HTTP entry that lists definitions, checks readiness, and executes requests.
7. Route normal `PATCH /api/projects/{id}` subtitle-size writes and operation-core subtitle-size writes through one settings mutation function.
8. Verify persistence after database reload without retrieval or LLM use.

### Deferred

Request ID persistence, durable revision columns, idempotent replay, regeneration planning, artifact revision binding, recovery, natural-language input, model integration, semantic retrieval, and comparison experiments are work units 11+.

### Runtime constraints

- Windows 11 target; repository remains cross-platform.
- Python `>=3.12`; local verified Python is 3.12.12.
- Node `>=20`; local verified Node is 24.11.1.
- Existing lockfiles remain authoritative.
- No new runtime or development dependency.
- SQLite and the process-local worker remain unchanged.
- All new Python public functions and methods use type hints.

### Acceptance criteria

- Existing baseline suites remain green.
- The fake-provider sample can create and generate a project when FFmpeg is available.
- Catalog loading fails for duplicate IDs, malformed schemas, or missing registered handlers.
- A candidate/provisional result cannot be executed.
- Execution always resolves the target and validates arguments/readiness again.
- Subtitle size accepts only integer values from 16 through 120.
- Missing/nonexistent targets and stale observations do not write.
- Status inspection never writes.
- Subtitle size persists and survives a new SQLAlchemy session.
- Existing PATCH and operation HTTP paths share the same settings mutation function.

## 3. Architecture and Dependency Direction

```mermaid
flowchart LR
    ExistingUI[Existing React UI] --> ProjectAPI[Project API]
    StructuredClient[Structured client] --> OperationAPI[Operation API]
    ProjectAPI --> Settings[Project settings service]
    OperationAPI --> Bootstrap[Operation bootstrap]
    Bootstrap --> Core[Operation service]
    Core --> Catalog[JSON catalog]
    Core --> Readiness[Target and readiness]
    Core --> Registry[Handler registry]
    Registry --> Handlers[BlockVideo handlers]
    Handlers --> Settings
    Readiness --> ORM[Existing ORM and jobs]
    Settings --> ORM
    ORM --> SQLite[(SQLite)]
```

Allowed imports are monotonic:

```text
contracts
  <- catalog
  <- registry
  <- readiness
  <- handlers
catalog + registry + readiness + handlers
  <- service
service
  <- bootstrap
bootstrap
  <- operation API
project settings service
  <- project API and subtitle handler
```

Prohibited directions:

- `contracts`, `catalog`, `registry`, `readiness`, and `service` must not import API routes.
- Existing models and settings services must not import the operation package.
- The catalog must not import handlers or evaluate names as Python expressions.
- Frontend code must not be imported by backend code.

## 4. Technology Stack and Research Record

| Technology | Version/constraint | Role | Decision |
|---|---|---|---|
| Python | `>=3.12`; verified 3.12.12 | Backend/core/tests | Existing stack |
| FastAPI | locked 0.139.2 | Structured HTTP entry | Reuse existing router pattern |
| Pydantic | locked 2.13.4 | Strict contracts and catalog models | Reuse; no JSON-schema package added |
| SQLAlchemy | locked 2.0.51 | Target/status/settings persistence | Reuse synchronous session ownership |
| SQLite | Python/SQLAlchemy driver | Local durable project state | No schema change in units 01–10 |
| pytest | locked 9.1.1 | Contract/API/integration tests | Existing test framework |
| React/TypeScript | React 18.3.1; TS 5.9.3 | Existing UI regression only | No Plan C UI in this phase |
| Vitest | locked 2.1.9 | Frontend regression | Existing framework |
| FFmpeg | installed 9.0.1 | Sample MP4 generation | Official repository requirement |
| JSON | standard library | Operation source of truth | Chosen over YAML for strict, unambiguous machine data |

Primary sources verified 2026-09-17:

- Repository: <https://github.com/Rimcat-JA/blockvideo>
- FastAPI response/model behavior: <https://fastapi.tiangolo.com/>
- Pydantic models and JSON Schema: <https://docs.pydantic.dev/latest/concepts/models/> and <https://docs.pydantic.dev/latest/concepts/json_schema/>
- SQLAlchemy sessions: <https://docs.sqlalchemy.org/en/20/orm/session_basics.html>
- uv project synchronization: <https://docs.astral.sh/uv/concepts/projects/sync/>
- FFmpeg: <https://ffmpeg.org/documentation.html>

Repository manifests and lockfiles determine exact compatible versions. No LlamaIndex, Rasa, Outlines, retrieval library, or LLM SDK is introduced.

## 5. Dependency Inventory

### Python standard library

- `json`: `json.loads`; parse operation definitions. `catalog.py` owns file reads.
- `pathlib`: `Path`; locate catalog and sample files.
- `enum`: `Enum`; readiness/result labels.
- `typing`: `Any`, `Protocol`, `Callable`; typed handler boundaries.
- `datetime`: existing project `updated_at` is serialized as the observed state token.

### Pydantic

- Package: `pydantic==2.13.4`
- Symbols: `BaseModel`, `ConfigDict`, `Field`, `ValidationError`, `field_validator`, `model_validator`.
- Used by: operation contracts and catalog models.
- Ownership: immutable request/result values; no resources.
- Failures: `ValidationError` becomes catalog startup failure or HTTP 422.

### SQLAlchemy

- Package: `sqlalchemy==2.0.51`
- Symbols: `Session`, `select`.
- Used by: readiness, handlers, settings mutation, tests.
- Ownership: caller injects the request-scoped session; operation code never closes it.
- Failure: transaction errors propagate to FastAPI's bounded error handler; validation errors occur before mutation.

### FastAPI

- Package: `fastapi==0.139.2`
- Symbols: `APIRouter`, `Depends`, `HTTPException`.
- Used by: `app/api/routes_operations.py`.
- Semantics: synchronous handlers use the existing `get_db` dependency.

### Existing internal modules

- `app.models.project.Project`: target and settings state.
- `app.models.job.GenerationJob`, `JobStatus`: readiness evidence.
- `app.workers.job_runner.job_registry`: distinguish live work from historical rows.
- `app.services.invalidation.invalidate_project_settings`: preserve current downstream invalidation semantics.
- `app.db.get_db`: request session.

## 6. Repository Structure

```text
AGENTS.md
specification.md
docs/
├── DTD.md
├── plan-c/
│   ├── ai-environment.md
│   ├── commands.md
│   ├── current-system-map.md
│   ├── decisions.md
│   ├── operation-catalog.md
│   ├── contracts.md
│   ├── handoff.md
│   ├── work-report-01-10.md
│   └── tasks/work-unit-01.md ... work-unit-10.md
└── modules/operation-core.md
samples/
├── compose_multiplatform_intro.txt
├── plan_c_operation_demo.txt
└── plan_c_operation_demo.json
backend/app/
├── api/routes_operations.py
├── operations/
│   ├── __init__.py
│   ├── contracts.py
│   ├── catalog.py
│   ├── registry.py
│   ├── readiness.py
│   ├── handlers.py
│   ├── service.py
│   ├── bootstrap.py
│   └── definitions.json
└── services/project_settings.py
backend/tests/
├── test_operation_catalog.py
├── test_operation_service.py
└── test_operations_api.py
```

No broad directory migration is permitted.

## 7. Configuration and Secrets

No new environment variable or secret is introduced.

- Catalog path is package-local and fixed at `operations/definitions.json`.
- Tests may inject a temporary catalog `Path` directly.
- Sample payload sets `use_fake_providers: true` and contains no API key.
- Existing `.env` and `SecretStore` rules remain unchanged.
- External cost ceiling for this phase is zero: no paid provider is called.

## 8. Module and File Design

### `app/operations/contracts.py`

Responsibility: transport-independent typed contracts.

Public types:

```python
class Readiness(str, Enum):
    ready = "ready"
    needs_input = "needs_input"
    blocked = "blocked"
    unsupported = "unsupported"

class OperationTarget(BaseModel):
    project_id: int | None
    selected_project_id: int | None

class OperationRequest(BaseModel):
    operation_id: str
    operation_version: int = 1
    target: OperationTarget
    arguments: dict[str, Any]
    observed_state_revision: str | None = None

class ReadinessResult(BaseModel):
    operation_id: str
    readiness: Readiness
    reason_code: str | None
    missing_fields: list[str]
    project_id: int | None
    state_revision: str | None

class OperationResult(BaseModel):
    operation_id: str
    project_id: int
    changed: bool
    state_revision: str
    data: dict[str, Any]
```

All models use `extra="forbid"`. `project_id` and `selected_project_id` may not conflict. An executable request is separate from a future retrieved candidate; no candidate type is accepted by `execute`.

### `app/operations/catalog.py`

Responsibility: parse and validate versioned JSON definitions.

```python
def load_catalog(path: Path) -> OperationCatalog
def validate_arguments(definition: OperationDefinition, arguments: dict[str, Any]) -> dict[str, Any]
```

Supported schema subset is intentionally exact: object root, properties, required, additionalProperties, integer/string/boolean, minimum, maximum. Unsupported schema keywords cause catalog load failure rather than silent omission.

### `app/operations/registry.py`

Responsibility: explicit mapping from `handler_key` to callable.

```python
OperationHandler = Callable[[Session, Project, dict[str, Any]], OperationResult]
class HandlerRegistry:
    def register(self, key: str, handler: OperationHandler) -> None
    def require(self, key: str) -> OperationHandler
    def keys(self) -> frozenset[str]
```

Duplicate keys fail. `require` never imports/evaluates a catalog string.

### `app/operations/readiness.py`

Responsibility: target resolution and state checks.

```python
def resolve_project(db: Session, target: OperationTarget) -> Project | None
def project_state_revision(project: Project) -> str
def evaluate_readiness(db: Session, definition: OperationDefinition, target: OperationTarget) -> ReadinessResult
```

Rules:

1. Missing both target IDs → `needs_input`, `missing_fields=["project_id"]`.
2. Conflicting IDs → request validation error.
3. Missing row → `unsupported`, reason `target_not_found`.
4. A pending/running job that is live in `job_registry` → `blocked`, reason `project_busy`.
5. Otherwise → `ready` with current `updated_at` token.

Historical pending rows left after restart are not considered live in units 01–10; restart recovery is deferred.

### `app/services/project_settings.py`

Responsibility: one mutation path for validated project settings.

```python
def apply_project_settings(project: Project, updates: Mapping[str, Any]) -> set[str]
```

It calculates changed fields, assigns only existing project attributes, invokes `invalidate_project_settings`, and returns changed fields. It does not commit. The caller owns transaction boundaries.

### `app/operations/handlers.py`

```python
def set_subtitle_font_size(db: Session, project: Project, arguments: dict[str, Any]) -> OperationResult
def get_project_status(db: Session, project: Project, arguments: dict[str, Any]) -> OperationResult
```

- Setter receives already catalog-validated `{"value": int}`; it calls `apply_project_settings`, commits once, refreshes, and reports persisted value.
- Status handler performs no write and returns status, progress, stage, block count, output path, and error.

### `app/operations/service.py`

```python
class OperationService:
    def list_definitions(self) -> list[OperationDefinition]
    def readiness(self, db: Session, request: OperationRequest) -> ReadinessResult
    def execute(self, db: Session, request: OperationRequest) -> OperationResult
```

Execution order:

1. Resolve operation ID/version from catalog.
2. Validate argument names/types/ranges from catalog.
3. Resolve target and calculate final readiness.
4. If `observed_state_revision` is present and differs, reject with `stale_state`.
5. Reject every readiness other than `ready`.
6. Resolve the target project and repeat readiness/current-state validation.
7. Resolve the registered handler by key.
8. Invoke handler.
9. Return typed result.

### `app/operations/bootstrap.py`

Builds one immutable process-wide service from package JSON and an explicit registry. At import/startup it verifies every definition's handler exists and every registered handler is referenced. Tests may call `build_operation_service(catalog_path)`.

### `app/api/routes_operations.py`

Endpoints:

| Method | Path | Purpose | Result |
|---|---|---|---|
| GET | `/api/operations` | List source definitions | `list[OperationDefinition]` |
| POST | `/api/operations/readiness` | Final typed readiness check | `ReadinessResult` |
| POST | `/api/operations/execute` | Final validation and execution | `OperationResult` |

Mapping:

- Unknown operation/version: HTTP 404.
- Invalid arguments/target shape: HTTP 422.
- `needs_input`, `blocked`, `unsupported`, stale state: HTTP 409 with a machine-readable detail object.
- Successful status read or setting write: HTTP 200.

No shell string, retrieval result, or model output is accepted.

### `operations/definitions.json`

Contains exactly two version-1 definitions. Each has:

- `schema_version`
- `operation_id`
- `operation_version`
- `description`
- `examples`
- `input_schema`
- `handler_key`
- `affected_artifacts`
- `precondition_key`
- `postcondition_key`

Subtitle size schema requires only integer `value`, minimum 16, maximum 120, no extra keys. Status schema requires an empty object.

### Sample files

`plan_c_operation_demo.txt` is a short Japanese synthetic script with an authored slide, suitable for deterministic fake providers. `plan_c_operation_demo.json` is a complete `POST /api/projects` body referencing the same script content, title, fake-provider flag, and subtitle size 48. It contains no real identity, secret, or copyrighted user data.

## 9. Data Model Design

No database migration is made.

### Operation definition

| Field | Type | Rule |
|---|---|---|
| schema_version | int | exactly 1 |
| operation_id | str | lowercase dot/hyphen identifier, unique with version |
| operation_version | int | >=1 |
| description | str | non-empty |
| examples | list[str] | non-empty strings |
| input_schema | object | supported strict subset |
| handler_key | str | registered key |
| affected_artifacts | list[str] | descriptive only in this phase |
| precondition_key | str | known metadata, not evaluated dynamically |
| postcondition_key | str | known metadata, not evaluated dynamically |

### State revision

The phase uses `Project.updated_at.isoformat()` as an observation token. It is not claimed as the durable monotonic revision required by work unit 11. It prevents an explicitly observed stale request from proceeding in a single-process local workflow. Execution checks readiness once before target resolution and again immediately before dispatch. This narrows state drift but is not a cross-process lock; durable revision and concurrency control remain work unit 11 scope.

## 10. Internal Interfaces

- API owns `Session`; operation service borrows it synchronously.
- Service owns ordering and validation; handler owns operation-specific read/write.
- Handler never receives an unvalidated target or catalog-unknown field.
- Settings service mutates ORM state but never commits.
- Catalog data is immutable after process bootstrap.
- Exceptions are converted only at the API boundary.

## 11. External APIs

No new external API is called. Existing fake-provider sample generation uses existing internal provider interfaces and FFmpeg subprocess handling. Real OpenAI-compatible and VOICEVOX APIs are explicitly unnecessary for G1.

## 12. APIs Implemented by the Project

### Readiness request

```json
{
  "operation_id": "project.subtitle-font-size.set",
  "operation_version": 1,
  "target": {"project_id": 1},
  "arguments": {"value": 56}
}
```

Success:

```json
{
  "operation_id": "project.subtitle-font-size.set",
  "readiness": "ready",
  "reason_code": null,
  "missing_fields": [],
  "project_id": 1,
  "state_revision": "2026-09-17T12:00:00+00:00"
}
```

### Execute request

Same request, optionally adding `observed_state_revision`. Success data for setter:

```json
{
  "operation_id": "project.subtitle-font-size.set",
  "project_id": 1,
  "changed": true,
  "state_revision": "2026-09-17T12:01:00+00:00",
  "data": {"subtitle_font_size": 56}
}
```

Status execution uses `{}` arguments and returns the project state fields. Credentials and source script are excluded.

## 13. Runtime Flow

```mermaid
sequenceDiagram
    participant C as Structured client
    participant A as Operation API
    participant S as OperationService
    participant V as Catalog/readiness
    participant H as Registered handler
    participant DB as SQLite

    C->>A: execute typed JSON
    A->>S: execute(session, request)
    S->>V: definition + argument validation
    S->>DB: resolve project and live state
    alt not ready or stale
        S-->>A: typed rejection
        A-->>C: 409/422
    else ready
        S->>H: registered callable only
        alt subtitle setter
            H->>DB: shared settings mutation + commit
        else status read
            H->>DB: read only
        end
        H-->>S: OperationResult
        S-->>A: OperationResult
        A-->>C: 200 JSON
    end
```

## 14. Error Handling and Resilience

- Catalog errors are fatal during service construction.
- Validation never partially mutates state.
- Unknown operation/version and unknown handler are distinct errors.
- `needs_input`, `blocked`, `unsupported`, and `stale_state` keep distinct reason codes.
- No retries occur in the operation core.
- No operation starts generation in this phase.
- Database commit failure propagates; SQLAlchemy rolls back when request scope closes. Tests verify no mutation for all validation failures.
- Existing global logging remains in force; arguments are non-secret for the two definitions.

## 15. Observability

Use existing Loguru configuration. Log operation ID, version, project ID, readiness, reason code, and changed flag. Never log source scripts, API keys, provider secrets, or whole request bodies. No metric/tracing dependency is added.

## 16. Security Design

- Local-machine trust boundary remains unchanged.
- Catalog strings never become imports, attributes, SQL, or shell commands.
- Only registry callables can execute.
- Pydantic rejects extra request fields.
- Catalog validation rejects extra arguments and wrong runtime types; `bool` is not accepted as integer.
- Target IDs are database lookups, not paths.
- Result excludes secrets and full source text.
- No model or retrieval component can write catalog files or call handlers directly.

## 17. Testing Design

### Catalog tests

- Valid package catalog loads two definitions.
- Duplicate ID/version fails.
- Unsupported schema keyword fails.
- Missing registered handler fails bootstrap.
- Unknown/extra/wrong-type/out-of-range arguments fail.

### Service tests

- Missing target → `needs_input`.
- nonexistent target → `unsupported`.
- live job → `blocked`.
- stale observed revision rejects without write.
- valid subtitle size writes and survives a new session.
- same subtitle size reports `changed=false`.
- invalid value never writes.
- status result is read-only.

### API tests

- list exposes both definitions.
- readiness/execute use structured JSON.
- malformed requests return 422.
- not-ready state returns machine-readable 409.
- setter and existing PATCH produce the same persisted value and invalidation state.

### Regression and smoke

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

Sample MP4 smoke uses fake providers and FFmpeg 9.0.1. It must record output path and size; failure must be reported rather than counted as pass.

## 18. Build, Run, and Deployment

Install:

```bash
python -m uv sync --project backend --extra dev --frozen
cd frontend && npx -y pnpm@10.18.3 install --frozen-lockfile
```

Run backend:

```bash
cd backend && python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

No deployment topology, port, container, or database change is introduced.

## 19. Implementation Roadmap

### Step 1 — Work units 01–05 records and sample

- **Prerequisites:** cloned baseline and verified tools.
- **Create:** specification, Plan C records/tasks, sample payload/script, AGENTS instructions.
- **Tests:** validate JSON and run baseline suites/sample pipeline.
- **Acceptance:** G0 evidence is explicit; unknown human budget is resolved as zero external spend for this phase.

### Step 2 — Contracts, catalog, and registry (units 06–07)

- **Prerequisites:** Step 1.
- **Create:** contracts, JSON definitions, catalog loader, registry, bootstrap.
- **Tests:** catalog and registry negative cases first.
- **Acceptance:** malformed/unregistered definitions cannot build the service.

### Step 3 — Resolution and readiness (unit 08)

- **Prerequisites:** Step 2.
- **Create:** readiness module and service readiness path.
- **Tests:** target, busy, stale, value, and reason-code cases first.
- **Acceptance:** every execution candidate is revalidated against current state.

### Step 4 — Representative operations and shared write path (unit 09)

- **Prerequisites:** Step 3.
- **Create:** settings service and handlers; modify project PATCH route.
- **Tests:** persistence and UI/API semantic equivalence first.
- **Acceptance:** subtitle write and status read work without LLM/retrieval.

### Step 5 — Thin HTTP entry and G1 (unit 10)

- **Prerequisites:** Step 4.
- **Create:** operation router; register in app.
- **Tests:** endpoint integration and bypass-negative cases first.
- **Acceptance:** listing/readiness/execution all reach one core; complete regressions pass.

### Step 6 — Reconcile documentation and review

- **Prerequisites:** Steps 1–5.
- **Modify:** DTD if implementation evidence differs; module note; report; handoff.
- **Verification:** full commands and independent review.
- **Acceptance:** documents describe only implemented behavior and identify work unit 11 as next.

## Implementation Instructions for Coding Agent

1. Implement roadmap steps sequentially.
2. Do not skip prerequisites.
3. Treat this DTD as the implementation contract.
4. Do not silently replace dependencies, APIs, schemas, boundaries, or algorithms.
5. Do not invent material architecture absent from this DTD.
6. Run specified verification after each step when feasible.
7. Update tests with implementation using red-green-refactor.
8. Preserve the dependency direction above; circular imports are forbidden.
9. Report unavailable APIs, incompatible versions, or unsatisfied criteria rather than redesigning silently.
10. If implementation evidence disproves this DTD, update the affected DTD section before continuing.
11. Keep work units 11+ deferred.
12. Preserve unrelated repository changes.
