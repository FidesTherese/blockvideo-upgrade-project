# D38 — Independent evaluation result import

## Goal

Validate and import a separate evaluator's aggregate result without reading held-out
text or labels.

## Scope

- Import D37's existing EvaluationResultBundle and EvaluationProtocol unchanged;
  never define a D38-local bundle. Verify freeze/corpus/protocol and separate approval/
  tool fingerprints, complete topology, counts, safety/failure outcomes, evaluator
  identity/time, and exact canonical bytes.
- Require the protocol's complete sorted opaque case/category token sets/counts and
  exact one-case/one-category bindings repeated in the bundle, plus a non-empty exact sorted included set plus exact sorted excluded tokens with one
  approved deterministic reason per exclusion; require at least one included token in
  every declared category/mode and accept no raw IDs, text, category names, or labels.
- Reject mismatched, incomplete, internally inconsistent, altered, or selectively
  filtered bundles by checking token uniqueness/sorting, included/excluded
  disjointness, exact union equality, non-empty protocol/included/category coverage,
  declared counts, typed `both_not_approved`/single-missing exclusion reasons,
  opaque-category accounting, and every bound hash.
- Preserve failures and exclusions explicitly; never convert missing trials to skips
  or successful non-effects.
- Preserve accepted bytes unchanged in a complete no-replace accepted triplet. Require
  the DTD's exact twenty raw bool-true validation checks, including
  sealed_evidence_hash_syntax; no extras or omissions.
- Bind model_configuration_sha256/stateful_index_sha256 through the exact protocol
  hash and copy those verified values into ImportValidation, never invented bundle
  fields. Use 64/128 MiB protocol/result pre-parse caps, duplicate/nonfinite/Literal
  primitive rejection and explicit strict JSON tuple parsing. File hashes include LF;
  source aggregate does not. Do not open sealed evidence.

## Non-goals

No self-review by the implementation process and no reconstruction of private cases
from aggregates.

## Acceptance

Synthetic valid bundles import deterministically; tampering, duplicate/overlapping/
missing/extra tokens, zero overall/category inclusion, category/reason/count drift,
unknown exclusion reasons, raw identifiers/labels, and every manifest/hash mismatch
fail closed. The accepted bundle is sufficient for D40's declared gates
without revealing held-out content.
