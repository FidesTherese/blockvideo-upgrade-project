# Plan C Handoff

## Completed boundary

Work units 01–10 establish G1: versioned definitions, typed contracts, strict catalog validation, target/readiness checks, explicit registered handlers, shared subtitle persistence, status inspection, and structured HTTP entry. No retrieval or LLM is involved.

## Start here

1. Read `specification.md`, then `docs/DTD.md`.
2. Read `docs/modules/operation-core.md` and the three operation test files.
3. Run the commands in `docs/plan-c/commands.md`.
4. Begin work unit 11 by replacing the observation-only `updated_at` token with the approved durable request ID/revision/idempotency design. Update the DTD before changing that contract.

## Preserve

- Catalog JSON cannot execute code.
- All entry points call the same operation service and settings mutation.
- Retrieval/model output never grants execution permission.
- State is checked immediately before handler dispatch.
- Imports remain acyclic.

## Known limits

- No durable operation request row, monotonic revision column, or replay result exists.
- No cross-process project lock exists; the current worker is single-process.
- Generation/cancel/retry are not operation-catalog handlers yet.
- There is no natural-language UI, LLM adapter, or retrieval index.
- Real VOICEVOX and paid providers were not needed for G1 acceptance.
