# Plan C Decisions — Work Units 01–10

| ID | Decision |
|---|---|
| DEC-01 | Completion is gate-based. This phase ends at G1, not a fixed date. |
| DEC-02 | External provider cost is zero; local tools and fake providers only. |
| DEC-03 | Only repository code and synthetic data may leave process boundaries; no secrets or user projects. |
| DEC-04 | Existing behavior remains: setting writes during a live generation job are blocked. |
| DEC-05 | Later language interpretation maps “slightly” to 2 px. G1 accepts only the final absolute integer, 16–120. |
| DEC-06 | Explicit and selected project IDs must agree. Missing target needs input; conflict is invalid. |
| DEC-07 | G1 executes one operation per request. Multi-operation atomicity is deferred. |
| DEC-08 | Setting changes never start generation. Generation requires an explicit separate request. |
| DEC-09 | Clear reversible writes need no confirmation. Missing, ambiguous, blocked, stale, or unsupported requests do not execute. |
| DEC-10 | Candidate information is provisional. The core performs final argument, target, state, and readiness checks immediately before registered dispatch. |
| DEC-11 | Small-LLM integration is deferred. No silent cloud fallback is allowed. |
| DEC-12 | G1 is deterministic tests plus a fake-provider sample; final comparative release thresholds remain deferred. |
| DEC-13 | Operation definitions use JSON and version 1 IDs. |
| DEC-14 | The thin G1 entry is an internal/public structured FastAPI route, not a new CLI. |
