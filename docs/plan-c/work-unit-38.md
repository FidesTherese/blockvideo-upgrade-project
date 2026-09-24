# D38 — Independent evaluation result import

## Goal

Validate and import a separate evaluator's aggregate result without reading held-out
text or labels.

## Scope

- Define an attested bundle containing freeze/corpus/protocol fingerprints,
  included/excluded counts, mode/category aggregates, safety outcomes,
  unauthorized effects, transport/deadline failures, integrity checks, evaluator
  role, and execution time.
- Require the protocol's complete sorted opaque case-token set/count and bundle's
  a non-empty exact sorted included set plus exact sorted excluded tokens with one
  approved deterministic reason per exclusion; require at least one included token in
  every declared category/mode and accept no raw IDs, text, category names, or labels.
- Reject mismatched, incomplete, internally inconsistent, altered, or selectively
  filtered bundles by checking token uniqueness/sorting, included/excluded
  disjointness, exact union equality, non-empty protocol/included/category coverage,
  declared counts, typed `both_not_approved`/single-missing exclusion reasons,
  opaque-category accounting, and every bound hash.
- Preserve failures and exclusions explicitly; never convert missing trials to skips
  or successful non-effects.
- Store the accepted aggregate alongside its content hash and validation report.

## Non-goals

No self-review by the implementation process and no reconstruction of private cases
from aggregates.

## Acceptance

Synthetic valid bundles import deterministically; tampering, duplicate/overlapping/
missing/extra tokens, zero overall/category inclusion, category/reason/count drift,
unknown exclusion reasons, raw identifiers/labels, and every manifest/hash mismatch
fail closed. The accepted bundle is sufficient for D40's declared gates
without revealing held-out content.
