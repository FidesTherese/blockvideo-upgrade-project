# D38 — Independent evaluation result import

## Goal

Validate and import a separate evaluator's aggregate result without reading held-out
text or labels.

## Scope

- Define an attested bundle containing freeze/corpus/protocol fingerprints,
  included/excluded counts, mode/category aggregates, safety outcomes,
  unauthorized effects, transport/deadline failures, integrity checks, evaluator
  role, and execution time.
- Reject mismatched, incomplete, internally inconsistent, altered, or selectively
  filtered bundles.
- Preserve failures and exclusions explicitly; never convert missing trials to skips
  or successful non-effects.
- Store the accepted aggregate alongside its content hash and validation report.

## Non-goals

No self-review by the implementation process and no reconstruction of private cases
from aggregates.

## Acceptance

Synthetic valid bundles import deterministically; tampering and every manifest/count
mismatch fail closed. The accepted bundle is sufficient for D40's declared gates
without revealing held-out content.
