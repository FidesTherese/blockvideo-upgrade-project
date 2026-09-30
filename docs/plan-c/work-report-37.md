# D37 Work Report — Externally Attested Blinded Evaluator

## Result

D37 supplies external post-candidate tooling for a separately controlled blinded
evaluation. The immutable release candidate remains the clean D35 commit
`522775516c0797abdb313e3432339a3a444b7ae2`, candidate ID
`26933fe07103c402-522775516c07`. D37 does not change candidate behavior.

The source hash and test totals below are historical evidence from the original D37
delivery and are superseded for the final-review fix wave until its final sequential
gates complete. The final fix keeps the exact D35 candidate unchanged.

The historical complete D37 source closure contains every tracked
`backend/evaluation/**/*.py` and `backend/app/**/*.py` file plus
`backend/app/operations/definitions.json`, `backend/pyproject.toml`,
`backend/uv.lock`, and `backend/scripts/run_blinded_evaluation.py`. Computed from
clean committed source at `77ce86d7d16e2a31cd14f98fc88a469d64c99ec4`, its 164-file aggregate is
`54e3f5f21836ca1959855c0e2f8fa016831c576f766d24a8b6cce4ec2679ea51`.
This report and handoff are outside that source closure, so the aggregate is unchanged
by the documentation-only D37 delivery commit. The real evaluator MUST recompute and
validate the attestation from the exact clean pushed tooling `HEAD`.

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

Final correction verification is recorded in the task's
`.superpowers/sdd/implementation-plan-37/final-fix-report.md`. No candidate, production
app, frontend, held-out input, real token key, or evaluator evidence changed.

## Historical synthetic verification

Only repository-owned synthetic tests were executed. No real held-out corpus, review
ledger, token key, private detailed evidence, or real D37 evaluation output was read or
created.

The first full backend attempt ran after creating this report and therefore correctly
failed the D36 CLI clean-tooling precondition: **1696 passed, 11 skipped, 1 failed**.
The failure was `test_cli_writes_completed_publication_contract`; the CLI rejected the
intentionally dirty documentation checkout. The two documentation files were stashed
without touching ignored evidence, making the tooling checkout clean, and a fresh full
sequential gate then produced:

- backend full suite: **1697 passed, 11 skipped**, one existing Starlette/httpx
  deprecation warning, in 682.48 s;
- Ruff: passed;
- frontend tests: **17 files, 157 tests** passed;
- frontend build: passed, **190 modules transformed**;
- frontend lint: passed;
- explicit synthetic external-runner isolation: **1 passed** in 37.92 s.

The implementation-plan test selector had been renamed during Task 4, so its stale
name collected zero tests. The executed current equivalent was
`test_external_runner_uses_attested_host_detached_candidate_and_redacted_aggregate`;
it exercises the external host, detached synthetic candidate, redacted aggregate, and
candidate non-mutation in one test.

The detached real D35 checkout had empty tracked and ignored status before the full
gate, immediately before the explicit isolation test, and after that test. The explicit
test uses only temporary synthetic corpus, approvals, candidate-host stub,
stateful-index stub, and output.

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
pushed, only that stale candidate evidence and D36 staging created by this task are
removed; D36 freeze evidence is then regenerated from the exact clean pushed tooling
`HEAD` against the detached candidate/control and validated with the official reader.
A valid publication contains exactly `freeze-manifest.json`,
`d36-tool-attestation.json`, and `.d36-publication-state`, with no staging remainder.

## Limits

D37 synthetic verification proves contracts, isolation, privacy-preserving public
shape, bounded execution, teardown, resume, immutable publication, and source
attestation behavior. It is not a held-out quality result, human approval, independent
review result, release-readiness decision, tag, publication, deployment, or D38 start.
