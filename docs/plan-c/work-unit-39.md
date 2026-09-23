# D39 — Release-candidate verification

## Goal

Verify the exact D36 candidate as a clean, reproducible local release candidate.

## Scope

- Run full backend/frontend checks and D31–D35 safety/recovery suites.
- Test clean installation plus supported legacy migration, backup, and restoration.
- Reproduce All Tools and stateful modes from documented commands.
- Run bounded browser journeys and real FFmpeg with synthetic/fake content providers.
- Check committed files and generated evidence for secrets, private data, and
  accidental large/runtime artifacts.
- Reconcile setup, operations, recovery, migration, limitations, and evaluation
  documentation with the frozen implementation.

## Non-goals

No post-freeze behavior fix inside the same candidate, real cloud-provider spend,
publication, deployment, tag, or GitHub release.

## Acceptance

Every mandatory command passes on the frozen commit and produces content-bound
evidence. Any behavior fix requires a new D36 candidate and rerunning affected
independent evaluation rather than editing the result record.
