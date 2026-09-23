# D32 — Concurrency and race correctness

## Goal

Verify that database-backed receipts, revisions, confirmations, and job claims—not
process-local timing—decide concurrent effects.

## Scope

- Exercise independent sessions and processes against one isolated SQLite database.
- Cover duplicate IDs, changed-content reuse, simultaneous settings writes,
  answer/correction/dismiss races, confirmation versus revision change,
  cancellation versus completion/publication, retry versus recovery, deletion
  versus active/unknown work, and startup with multiple pending jobs.
- Preserve replay of the winning committed result. Losing requests return an
  existing replay, stale-state, busy, or conflict result without partial effects.
- Keep SQLite contention bounded and expose retry guidance without bypassing checks.

## Non-goals

No multi-server deployment claim, distributed lock, queue service, or performance
capacity claim.

## Acceptance

Every scenario has at most one permitted effect, consistent project/job/artifact
state, no orphan receipt or artifact, and deterministic post-race recovery. Repeated
runs and process-level tests preserve the same invariants.
