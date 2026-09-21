# D28 — Provisional readiness on retained semantic candidates

The user requested D28 and selected the real product case: while generating,
ask to set speech speed to 1.2. Keep the matching settings operation, explain that
generation blocks the edit, never cancel/queue it automatically, and require a new
request after completion. D27 fallback and D24 development/held-out boundaries remain.

## Contract

- Candidate readiness is a host-computed, read-only snapshot before arguments are
  interpreted. It is not final execution readiness. Known target/busy failures
  take precedence; operations with unchecked arguments say needs_input, not ready.
  Even an argument-free candidate labelled ready still needs core validation.
- Use existing evaluate_readiness, exact registered operation versions and the
  selected target. No fake arguments, guessed job/history IDs, provider calls,
  reservations or effect receipts are used to produce a snapshot.
- Semantic ranking and membership do not change with readiness. All stages,
  including expansion and full-scope fallback, retain blocked candidates. Each
  stage obtains a fresh snapshot. Model instructions distinguish meaning from
  feasibility and forbid switching to cancellation or another available action.
- The final parsed proposal still passes the same language guards, readiness,
  revision, confirmation and transactional executor. Refreshing candidate state
  never retries an old request or grants permission to execute it.
- Persist the per-stage snapshots with the interpretation record. UI labels these
  as historical/provisional; an explicit read-only refresh shows current reasons
  without mutating the original receipt, calling a model, or loading an index.
- Semantic readiness is enabled with the already opt-in semantic path and can be
  disabled for the existing D27 baseline. All Tools is unchanged. Hard Filter is
  an evaluation-only helper: it excludes known blocked/unsupported candidates,
  keeps unchecked-argument candidates, and can return no candidates. No product
  route or ordinary environment setting enables it; D29 owns the shared runner.

## Verification

Pair identical intents in editable/busy states. Check identical raw ranks, retained
blocked IDs/reasons in the model and UI, no cancellation/settings/job side effect,
missing arguments and references, fresh reasons after job completion, and a state
change between preview/confirmation/execution. Verify immutable replay and old D27
records. Compare Hard Filter membership separately without executing operations.
Run focused tests, all backend/Ruff and frontend test/build/lint. Use real local
E5/Ternary for representative paired requests and a browser journey with synthetic
video providers. Record model failures and any test race honestly. D29 is separate.
