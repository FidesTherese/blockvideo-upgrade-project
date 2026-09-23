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
- Save sealed detailed evidence and a non-sensitive aggregate result without logging
  request text or labels.
- Test runner behavior only with repository-owned synthetic fixtures.

## Non-goals

The implementation agent does not inspect held-out cases, labels, rendered review
HTML, or detailed evaluator evidence. D37 does not report final quality itself.

## Acceptance

Synthetic tests prove isolation, complete accounting, crash-safe partial reporting,
mode symmetry, scoring correctness, and rejection of unapproved or mismatched input.
