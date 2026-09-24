# D36 — Frozen release candidate

## Goal

Create a content-addressed candidate whose behavior and evaluation inputs cannot
change unnoticed.

## Scope

- Record Git commit and dirty status; operation/search-scope, prompt, response
  schema, guard, model, embedding, index, database-schema, evaluation-protocol,
  runtime, and relevant non-secret configuration fingerprints.
- Refuse a freeze with uncommitted behavior changes, missing assets, unknown schema,
  or inconsistent manifests.
- Classify documentation-only amendments separately; any executable-input change
  creates a new candidate and invalidates affected results.
- Derive `created_at` only from the frozen candidate commit's integer committer
  timestamp normalized to `YYYY-MM-DDTHH:MM:SSZ`; wall-clock time is forbidden.
- Keep secrets, absolute private paths, corpus text, and model response bodies out
  of the public manifest.

## Non-goals

No tag, publication, deployment, or final readiness claim.

## Acceptance

The same checkout and inputs reproduce byte-identical canonical manifest bytes,
including deterministic `created_at`. Any relevant byte change is detected. The frozen candidate can be reconstructed using documented commands.
