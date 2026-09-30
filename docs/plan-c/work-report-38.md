# D38 work report — synthetic aggregate importer; review pending

## Outcome and boundary

Tasks 1–3 implement the external D38 importer and its fixed redacted CLI. D37's
`EvaluationProtocol`, `CategoryResult`, `ModeResult`, `ExcludedCaseToken` and
`EvaluationResultBundle` are unchanged. No app/frontend, dependency, lock, immutable
candidate, private input or later-unit source changed. No push or approval occurred.

The importer verifies the separately supplied SHA-256 before parsing the bundle,
requires canonical bounded public artifacts and the complete D36 publication, binds
all upstream identities and exact opaque topology/accounting, and preserves accepted
bundle bytes including their LF. Exactly twenty raw bool-true checks are recorded;
model/index identities come from the verified protocol, not invented bundle fields.
Safety and transport/deadline failures remain failures, not skipped or normalized.

D36's exact eleven-path inventory and D37's historical evaluation/app Python tree
plus four required paths are verified against recorded Git blobs. Missing objects,
nonregular blobs, forged fingerprints/inventories and Git replacement-object aliases
fail closed. Limits are 16 MiB selected metadata, 8 MiB per source and 512 MiB total.
D38 separately attests its exact 25-path AST-closed inventory from clean current HEAD
and normal index. Historical verification requires neither live-byte nor HEAD equality.

`blinded_io.publish_accepted_triplet` retains native directory/file identities,
exclusively writes/fsyncs/readbacks exactly three files, and publishes by native
no-replace directory rename. Existing finals are refused, including empty directories.
Failed stages may remain non-evidentiary; after-rename failures preserve complete
finals. No fourth marker, resume, recursive cleanup or replacement deletion exists.
Windows retains the parent anchor across stage release but provides no claimed
directory-fsync or power-loss guarantee. Relative CLI paths are checked component by
component before collapsing `..`; links/reparses cannot be hidden by normalization.

## TDD and commits

- `8e56000`: Task 1, synthetic shared-contract fixture and 84 existing-model regressions;
  new import-boundary assertion genuinely failed because D38 was absent.
- `577b9de`: Task 2, importer/CLI, additive historical verifier/native triplet publisher,
  and 225 D38 tests. Missing historical/publication/import/CLI boundaries were observed
  RED before production code. A real Linux probe exposed an alias regression; a clean
  CLI probe exposed the documented relative-path regression. Both gained GREEN proof.
- Task 3 is the documentation/gate commit. Independent controller review remains
  pending; this is not a `[DONE]` approval/delivery commit.

The unpublished initial Task 2 commit was amended after the relative-path regression;
final source/gates below refer to `577b9defe7d1d14bf0ccde53a8a332a8dda1ce95`.

## Verification

Checks ran sequentially with the existing Python 3.12.12/Pydantic 2.13.4 environment,
not implicit `uv run` resync, and Node 24.11.1/pnpm 10.18.3. No weights were loaded.

| Check | Observed result |
|---|---|
| D38 tests in final full suite | 223 passed, 2 POSIX-only skips |
| Final full backend `python -m pytest -ra` | 2018 passed, 13 skipped, 1 existing Starlette/httpx warning |
| Full backend Ruff | Passed |
| Frontend tests, one worker/no file parallelism | 17 files, 157 tests passed |
| Frontend build/typecheck | Passed, 190 modules transformed |
| Frontend ESLint | Passed |
| Named synthetic detached-hash import test after gates | 1 passed |
| Native Windows anchor/no-replace/readback/fault/process-crash cases | Passed |
| WSL/Debian production filesystem/native-primitives probe | 4 passed; Python 3.13.5, not a Linux full-suite qualification |
| Clean committed-tooling CLI with synthetic D36/run artifacts | Exit 0, exact triplet, unchanged bundle, all 20 checks |

Thirteen full-suite skips comprise six platform-specific checks and seven missing
optional NumPy/ONNX checks; none counted as passed. Frontend npm warned about the
existing `allow-scripts` user config. No user config or dependency was changed.

Focused history is not hidden: the pre-commit combined gate had 681 passes, six skips
and the expected D36 clean-tooling CLI refusal. A clean rerun before the relative-path
correction passed 682 with six skips. Final combined focus had 683 passes, six skips
and one failure in the unchanged D37 same-size streamed-mutation test; isolation also
failed, while a timestamp-observing diagnostic rejected the mutation. The complete
final backend rerun included that same test and passed without waiver or skip. This
Windows timestamp-sensitive prior-unit regression remains an independent-review item.

All Python/Node/shell/Git working sets were sampled during gates, with an additional
4 GiB reserve for runtime/WSL and unobserved spikes. Maximum conservative observed
estimate was 5817.5 MiB; no parallel heavy gates, installs, browser or model runs.

## Source attestation and pending acceptance

Clean source commit `577b9de` produced the 25-path D38 aggregate
`c7153f45e5c6deed40f1edb66bcded52a852aeda5fe0ccfc95d7e57cd36f7f5b`.
The clean CLI probe verified historical source at `6293035`; its fake candidate,
protocol and result data are synthetic, not a D35 freeze or real evaluation.
Generated artifacts remain ignored/untracked; no sealed directory was read/enumerated.

A newly trusted digest can authenticate a changed evaluator identity/time, typed
exclusion reason or sealed hash without proving those private claims. Source integrity
is not evaluator/provider truth; model identifiers are not immutable weight provenance.

Real aggregate transfer, independent review and readiness remain pending. Preserve all
historical evidence; new real runs require final clean tooling and fresh evidence roots.
Historical recorded source remains verifiable after later tooling changes. D39/D40,
private-ledger reconstruction, candidate mutation and release approval remain out of scope.
