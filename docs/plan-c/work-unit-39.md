# D39 — Release-candidate verification

## Goal

Verify the exact D36 candidate as a clean, reproducible local release candidate.

## Scope

- Provide a separate external `materialize_candidate_runtime` command/function that
  verifies and copies exact candidate bytes into a read-only external runtime and
  emits canonical materialization evidence before any browser/media smoke.
- Derive exactly three fresh external writable sandboxes from independently reverified
  immutable runtime bytes: one backend sandbox for ordered install/import/test/lint/
  D31–D35 commands, one frontend sandbox for ordered pnpm install/test/build/lint, and
  one separate smoke sandbox. Backend dependency state persists only through its group;
  frontend `node_modules` persists only from install through lint in its group.
- Test clean installation plus supported legacy migration, backup, and restoration.
- Reproduce All Tools and stateful modes from documented commands.
- Run bounded browser journeys and real FFmpeg with synthetic/fake content providers.
- Check committed files and generated evidence for secrets, private data, and
  accidental large/runtime artifacts.
- Record exactly nine fixed command name/argv entries once each, in the DTD-defined
  order, and require every exit code to be zero.
- Bind a canonical smoke manifest and its hash to candidate, freeze, materialization
  hash, runtime instance, and runtime byte hash. Require non-empty lowercase 64-hex
  hashes for legacy migration, restore, All Tools startup, stateful startup, browser,
  and FFmpeg; embed the smoke content/hash in `VerificationManifest` for D40.
- Require the responsible D39 tool to rehash immutable runtime bytes before deriving
  and after discarding each group, rehash every sandbox's tracked source before/after
  each command or smoke stage, and prove candidate/runtime remain read-only and
  unchanged. The final verifier repeats those checks before accepting smoke evidence.
- Clean partial materializations on failure and remove runtime/temp environments in
  verifier `finally`; preserve bounded evidence and fail closed on cleanup failure.
- Reconcile setup, operations, recovery, migration, limitations, and evaluation
  documentation with the frozen implementation.

## Non-goals

No post-freeze behavior fix inside the same candidate, real cloud-provider spend,
publication, deployment, tag, or GitHub release.

## Acceptance

Every mandatory command passes on the frozen commit and produces candidate/runtime-
bound evidence. The exact nine-command inventory remains ordered with separate
per-command evidence and zero exits; commands 1–5 share only the backend sandbox,
commands 6–9 share only the frontend sandbox, and smoke uses a third sandbox. Group
source hashes, secret scan, clean before/after state, equal candidate snapshots, equal
final/runtime-source snapshots, all smoke hashes/bindings, and completed sandbox/
runtime cleanup are explicit. Independent runtime-byte rechecks and cleanup complete
successfully. Any behavior fix requires a new D36 candidate and rerunning affected
independent evaluation rather than editing the result record.
