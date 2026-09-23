# D33 — Crash and recovery matrix

## Goal

Demonstrate safe behavior at every durable boundary without blindly replaying an
external side effect or losing a previously successful artifact.

## Scope

- Add test-owned failpoints before/after request claim and core commit; around
  provider transmission and response persistence; during checkpoint creation,
  artifact publication, cancellation, and shutdown.
- Resume local idempotent work only from verified frozen snapshots.
- Keep potentially completed remote work `unknown`; never automatically resend it.
- Preserve prior successful artifacts and expose a specific safe next action.
- Verify restart reconciliation of project, job, receipt, call-journal, checkpoint,
  and artifact state.

## Non-goals

No provider-specific reconciliation API unless an existing adapter already supplies
a verifiable lookup contract. No destructive fault injection against user storage.

## Acceptance

The recovery matrix has no duplicate remote attempt, no publication of incomplete
artifacts, no adoption of changed inputs, and no silent loss of successful history.
Each terminal or recoverable state is stable after another restart.
