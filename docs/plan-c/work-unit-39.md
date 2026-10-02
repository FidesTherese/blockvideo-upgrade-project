# D39 — Release-candidate verification

## Goal

Verify immutable D35 named by D36 as a clean, reproducible local release candidate.
The tooling and review corrections are implemented. Operational acceptance remains
pending; see `work-report-39.md` for measured results and prerequisites.

## Scope

- Provide a separate external `materialize_candidate_runtime` command/function that
  verifies and copies exact candidate bytes into a read-only external runtime and
  emits canonical materialization evidence before any browser/media smoke.
- Derive exactly three fresh external writable sandboxes from independently reverified
  immutable runtime bytes: one backend sandbox for ordered install/import/test/lint/
  D31–D35 commands, one frontend sandbox for ordered pnpm install/test/build/lint, and
  one separate smoke sandbox. Backend dependency state persists only through its group;
  frontend `node_modules` persists only from install through lint in its group.
- Test fresh installation with Python 3.12.12 / uv 0.12.15, explicit optional dev and
  retrieval extras under --locked, then direct sandbox Python without resync/global
  fallback. Node 24.11.1 (24.x >=24) and pnpm exactly 10.18.3 use native node+npx-cli
  with frozen dev install and ignored dependency scripts, not .cmd or newer flags.
  Record canonical vs native argv and actual executable/launcher hashes+versions.
- Test supported legacy migration/backup/restore with foreign_keys enabled/read back
  on every new synchronous SQLite test connection before transactions.
- Reproduce All Tools and stateful modes from documented commands.
- Run bounded browser journeys and real FFmpeg with synthetic/fake content providers.
- Check committed files and generated evidence for secrets, private data, and
  accidental large/runtime artifacts.
- Record exactly nine fixed command name/argv entries once each, in the DTD-defined
  order, and require every exit code to be zero.
- Bind a canonical smoke manifest to candidate/freeze/materialization/runtime. Keep
  exactly six named stage hashes, each binding complete LF-terminated canonical bytes
  of an embedded typed receipt: migration, restore, All Tools, stateful, browser,
  FFmpeg in DTD order. Require actual outcomes, versions and artifact hashes/sizes;
  six arbitrary strings are not evidence. Stateful uses a genuine candidate-format
  synthetic index and fake loopback profile/adapters, not dummy index/fallback proof.
  Embed complete smoke content/hash for D40; automated docs checks are not human review.
  Pinned demo profile/endpoints are hardcoded: use the DTD external candidate-rooted
  bootstrap/public seams, not environment-only overrides or current-demo substitution.
  Pinned README stack claims are a known documentation-gate blocker; no silent waiver
  or candidate modification is authorized by this audit.
- Require the responsible D39 tool to rehash immutable runtime bytes before deriving
  and after discarding each group, rehash every sandbox's tracked source before/after
  each command or smoke stage, and prove candidate/runtime remain read-only and
  unchanged. The final verifier repeats those checks before accepting smoke evidence.
- Bind physical single-use ownership markers and cleanup state; remove only owned
  partial/runtime/temp objects in finally, clear Windows readonly bits only after
  identity checks, never traverse links/junctions or delete a replacement. Preserve
  bounded evidence; unknown ownership/teardown/cleanup fails. Failed manifests retain
  attempted prefixes and null absent observations, not manufactured passed fields.
- Enforce DTD per-command/stage deadlines, shared 2 MiB child output cap, gated Job
  Objects/confirmed descendant teardown, group-local caches/env/temp and one worker.
  Sequential aggregate project RAM <=16 GiB, target <=12; include agent runtime and
  all owned descendants, sample memory, and start no nontrivial job at >=14 GiB.
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
