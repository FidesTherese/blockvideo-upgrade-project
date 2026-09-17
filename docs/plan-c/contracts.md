# Operation Core Contracts

- Request: operation ID/version, one project target, strict argument object, optional observed state token.
- Readiness: `ready`, `needs_input`, `blocked`, or `unsupported`, with reason code, missing fields, resolved project, and state token.
- Result: operation ID, project ID, changed flag, latest state token, and non-secret data.
- Candidate/retrieval output is not an executable request type.
- Every execution repeats catalog argument checks, target resolution, current job/readiness checks, and optional stale-token comparison.
- Settings mutation and status read are synchronous within the caller-owned SQLAlchemy session.
- The handler registry is the only dispatch mechanism. Catalog text is not imported or evaluated.

See `docs/DTD.md` for exact signatures and API examples.
