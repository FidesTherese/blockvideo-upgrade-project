# D37 Work Report — Externally Attested Blinded Evaluator

## Result

D37 supplies external post-candidate tooling for a separately controlled blinded
evaluation. The immutable release candidate remains the clean D35 commit
`522775516c0797abdb313e3432339a3a444b7ae2`, candidate ID
`26933fe07103c402-522775516c07`. D37 does not change candidate behavior.

Independent review through `ad0529933e1db063530296e16d372c5a28cf20a7` passed
both specification and quality/security checks. This approves the tooling within its
stated trust model, not real evaluation or release readiness.

The complete D37 source closure contains tracked `backend/evaluation/**/*.py` and
`backend/app/**/*.py` plus operation definitions, backend manifests/lock, and the runner
CLI. Official attestation from that clean commit covered **167 files**, aggregate
`f0377a0b3757f4ad9b84566fac0998b066c8c3cec418e3761f0d4da72dc1ad04`.
This documentation is outside the closure. Later source additions invalidate that
aggregate; the evaluator MUST attest the final clean committed tooling before a real
run, using a new run directory rather than changing existing evidence.

## Final-review correction

The correction restores the D24 D029 target-switch contract: selection changes outside
the immutable request, and the exact original request/response replays with one request,
one turn, and the normal submit receipt. It hardens media identity to canonical relative
POSIX paths and streamed descriptor hashing; rejects links, reparses, special files,
Windows ADS/colon, traversal, and identity races; sends candidate-worker stdout/stderr
to the null device; binds every response mode to the trial mode; and aligns protocol
and result reader/writer caps with independently calculated maximum topologies.
Filesystem/publication and platform runtime responsibilities now live in
`blinded_io.py` and `blinded_runtime.py`; `blinded_runner.py` retains orchestration and
its public API. The D37 attestation closure discovers both helpers automatically.

The audited prerequisites add a pure canonical evidence parser, bounded streamed
index/source fingerprints, linear category accounting, and paired operator-only
loopback embedding configuration. Pydantic literal coercion is rejected without
normalizing bytes. The maximum valid bundle needs **4,980,838 tokens**; the proven
8,000,000-token limit now admits it within the 64/128 MiB protocol/result byte caps.
No candidate, production app, frontend, held-out input, real token key, or private
real evaluator evidence changed.

## Synthetic verification

Only repository-owned synthetic material and fake loopback providers were used:

- final full backend: **1795 passed, 11 skipped**;
- controller rerun of parser, maximum topology, D22 repair and pinned-D35 integration:
  **51 passed**; full Ruff passed;
- frontend verification: **157 tests**, build/typecheck and lint passed; subsequent
  changes affected tooling and tests only;
- genuine pinned-D35 integration: **7 passed**, covering both modes, restart replay,
  original-target replay and stale/missing index refusal.

The integration harness verifies all 433 exact D35 tracked blobs in an external
archive, builds/loads a real source/profile-bound synthetic index in candidate-rooted
subprocesses, proves actual stateful retrieval rather than fallback, and checks source,
index, budget and persisted effects. Earlier stub tests remain unit coverage only.
The flaky D22 wall-clock assumption was replaced by deterministic control of the real
shared timeout; a per-attempt-timer mutation fails. Production and pinned test bytes
were not edited.

Checks ran sequentially; sampled task workload stayed below 2.4 GiB against the
16 GiB hard aggregate limit. Four platform-specific and seven optional NumPy/ONNX
checks were skipped, not counted as passes. The existing Starlette/httpx warning
remains. Fresh-install/browser/ONNX lanes are D39 work, not claimed here.

## Evaluator-controlled command

The independent evaluator runs the following from an exact clean pushed D37 tooling
checkout. Every angle-bracket value is supplied by the evaluator; none is a repository
secret or a committed path:

```text
cd backend
python -m uv run python -m scripts.run_blinded_evaluation \
  --candidate-root <detached-d35-candidate-root> \
  --freeze-manifest <validated-d36-freeze-manifest.json> \
  --corpus <separately-mounted-held-out-corpus.jsonl> \
  --human-review <separately-mounted-human-approval-ledger.json> \
  --independent-review <separately-mounted-independent-approval-ledger.json> \
  --output <new-empty-evaluator-output-directory> \
  --model <evaluator-controlled-model-id> \
  --index <evaluator-controlled-stateful-index-directory> \
  --evaluator-name <independent-evaluator-identity> \
  --token-key-file <evaluator-controlled-token-key-file>
```

The real run is evaluator-controlled and deferred. The evaluator MUST keep mounted
inputs, the token-key parent, tooling, candidate, and output mutually disjoint as
required by the runner. The implementation process MUST NOT receive the key, corpus,
review ledgers, private trial evidence, or D37 output.

## D38 handoff boundary

The sole D38 protocol artifact is the immutable canonical
`<output>/protocol.json` produced before the first trial, together with the SHA-256 of
those exact bytes reported as `protocol_sha256` in the canonical
`<output>/result-bundle.json`. D36 `final_protocol.json` is only an input policy
template and MUST NOT be imported, substituted, or accepted as the D38 run protocol.
D38 remains unstarted.

## D36 evidence consequence

D36 trial-host and projection tooling was revised during D37. The ignored D36 freeze
evidence generated against the earlier tooling attestation is stale even though the
D35 candidate commit and candidate ID are unchanged. After the final D37 delivery is
pushed, fresh D36 evidence is generated in a new ignored output root from that clean
tooling `HEAD`, against the detached candidate/control, and validated with the official
reader. Historical publications are preserved; no completed evidence is overwritten.
A valid publication contains exactly `freeze-manifest.json`,
`d36-tool-attestation.json`, and `.d36-publication-state`, with no staging remainder.

## Limits

D37 synthetic verification proves contracts, isolation, privacy-preserving public
shape, bounded execution, teardown, resume, immutable publication, and source
attestation behavior. It is not a held-out quality result, human-operation approval,
independent evaluator result, release-readiness decision, tag, publication or deployment.
The frozen README prerequisite mismatch remains an explicit D39 documentation blocker;
no candidate correction or gate waiver is implied. D38 implementation may follow this
approved tooling gate, using synthetic aggregates only.
