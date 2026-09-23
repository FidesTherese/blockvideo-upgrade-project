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
