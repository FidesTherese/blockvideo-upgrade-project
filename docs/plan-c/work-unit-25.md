# D25 — Local-model usability and bounded diagnostics

The user requested D25 after the D24 corrections and selected a 30-second slow
interpretation notice. A notice never aborts or automatically resubmits a request.
D24 human approval carries to 80 development cases; 20 corrected development and 32
held-out cases remain pending. D25 authorization does not approve those labels.

## Scope

- Separate interpretation/result-delivery waiting from video-generation progress.
  Show elapsed time, a30-second notice, and useful failure/recovery instructions.
  Preserve exact-ID resend, GET-only recovery, project fencing and confirmation.
- Persist additive diagnostic metadata in language response JSON: server start,
  candidate IDs/versions, bounded interpretation/execution timings, guard reason.
  Old records still load. Receipt-recovered effects remain authoritative and
  missing timing after a crash is reported as unknown, never fabricated.
- Emit allowlisted pseudonymous operation events. No utterance, title, script,
  pronunciation text, raw model response, path, token, confirmation token, or
  raw client-controlled request ID is logged. Numeric configuration values are
  limited to known fields/ranges; IDs correlate through a process-local HMAC.
  Exact request/revision/job and extracted/resolved fields remain in the existing
  local response/receipt inspector, not a new bulk diagnostic export.
- Run an explicit loopback-only development interpreter probe through D24's human
  and independent approval gate. Report skipped pre-model cases separately;
  proposal accuracy is not application safety or end-to-end task completion.
  Record prompt/catalog/corpus hashes, candidates, attempts and latency. Synthetic
  development evidence may contain synthetic proposals; production logs may not.
- Tune only after recording a baseline on the same eligible development data.
  Validate real representative operations through an isolated application DB.
  Model-facing settings schemas may offer equivalent property orders; this never
  changes the canonical validation or weakens its constraints. Preserve rejected
  tuning variants and fingerprint the exact output schema/order for reproduction.

## Boundaries and verification

No held-out content is read. No retrieval/index or D26–D29 comparison framework is
introduced. Keep guards, core transactions and generation confirmation unchanged
unless a reproducible development defect requires a separately documented fix.
No cloud/model fallback. The user starts LM Studio because a previous automatic
approval review rejected agent-controlled startup in this environment.

Focused tests cover delays, reload, lost response, double-submit/confirmation,
metadata persistence/replay and secret-shaped values at log boundaries. Run the
AGENTS.md backend/frontend checks and record real-model and browser verification
separately. G4 needs real representative operations and traceable failures;
human judgments about speed and clarity are not inferred from automated tests.
