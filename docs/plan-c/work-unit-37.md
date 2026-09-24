# D37 — Blinded evaluation runner

## Goal

Run approved held-out evaluation without exposing its content to the implementation
process or allowing mode-specific test conditions.

## Scope

- Accept a separately mounted corpus and approval ledger at execution time.
- Validate corpus, approval, protocol, and D36 freeze fingerprints before running.
- Isolate database and media state per source-request group.
- Execute frozen All Tools and stateful-retrieval modes with identical limits.
- Score persisted receipts/effects and expected state, not model prose.
- Derive domain-separated evaluator-keyed HMAC-SHA-256 case/category tokens. Publish
  only a non-empty complete sorted opaque token set/count and non-empty opaque category
  bindings in the canonical protocol; never publish raw case IDs, text, category names,
  or labels.
- Require a non-empty included token set and at least one included token in every
  declared category in each mode; zero overall/category inclusion fails D37.
- Save sealed detailed evidence and a non-sensitive aggregate containing exact sorted
  included tokens and exact sorted excluded tokens with one deterministic reason per
  exclusion: `both_not_approved` when both approvals are absent, otherwise the sole
  missing approval's reason.
  without logging request text or labels.
- Test runner behavior only with repository-owned synthetic fixtures.

## Non-goals

The implementation agent does not inspect held-out cases, labels, rendered review
HTML, or detailed evaluator evidence. D37 does not report final quality itself.

## Acceptance

Synthetic tests prove isolation, opaque-token privacy, exact included/excluded union
accounting, deterministic exclusion precedence, non-empty overall/per-category
coverage, crash-safe partial reporting, mode symmetry, scoring correctness, and
rejection of unapproved, selectively filtered, duplicate, zero-coverage, or mismatched
input.
