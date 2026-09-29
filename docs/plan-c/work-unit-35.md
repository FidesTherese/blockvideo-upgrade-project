# D35 — Recovery-oriented operational UI

## Goal

Give users accurate next actions for durable operation and generation states without
moving recovery authority into the browser.

## Scope

- Distinguish waiting, busy, stale, interrupted, unknown external outcome, failed,
  cancelled, and safely retryable states from explicit backend reason codes.
- Show whether refresh, exact resend, cancellation wait, new generation, or restore
  from backup is appropriate.
- Disable controls that would imply unknown remote work can be retried.
- Display migration/startup failures safely through a bounded status contract.
- Preserve reload, stale-tab, responsive, keyboard, and screen-reader behavior.
- Keep receipts, journals, migrations, and readiness authoritative on the backend.

## Non-goals

No browser-side recovery engine, automatic retry loop, schema administration UI,
or claim that UI status replaces persisted evidence.

## Acceptance

Component and browser tests cover every state and stale-view transition. Suggested
actions match backend permissions, duplicate clicks remain safe, and narrow-screen
and keyboard operation remain usable.

Backend retry guidance MUST use the same project-wide blockers as durable job
creation: any unknown job or any `remote_side_effect IS TRUE` call in `in_flight` or
`unknown` blocks retry, while local unknown calls do not. Only pending and running
jobs wait. Unknown jobs always require provider checking; completed jobs are final;
failed and cancelled jobs offer retry only when full retry execution can proceed.
Job lists and history MUST construct one typed project recovery context with one
aggregate query and reuse it across all returned summaries. Detached terminal jobs
without context require refresh.
