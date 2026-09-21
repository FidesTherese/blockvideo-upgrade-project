# D24 — Japanese cases, grouped splits and label review

Prerequisites: D04 product decisions and D23 observations. The user requested D24
and explicitly approved separate AI authors/reviewers, with final human review in
a case list. AI prepares synthetic origins rather than treating one user's wording
as representative of every user. Preserve prior development failures as development.

## Deliverables

- 100 development cases in 10 source-request groups, under `evaluation/d24/`.
- 200 held-out cases in 20 independently authored source-request groups, outside
  the implementation repository and this task's outputs.
- Exact selected target, saved state, prior dialogue, lifecycle/history fixtures,
  incoming request, resend/race/confirmation event and expected effects.
- Operation/argument alternatives only for equivalent meanings, plus expected
  settings, revision, job and artifact behavior. Missing information, unsupported
  intent and supported-but-blocked intent remain distinct.
- Independent semantic review against product decisions, content-bound case
  ledgers and an offline Japanese human-review page. Human records start pending.
- Schema/catalog validation, group and normalized-text leakage checks, manual
  origin review, and an explicit eligibility gate excluding unapproved cases.

## Boundaries

This is offline tooling and data. No application route, operation, prompt, model
connection, provider or normal user project is changed. There is no D24 inference
score or video generation. D25 tuning uses development data only; D26 retrieval
remains separate. Compare model proposal accuracy, application safety and useful
completion separately. A conservative clarification on an unambiguous request is
not counted as useful completion just because it prevented an incorrect write.

The root implementation agent must not inspect held-out text or labels. An author
without development context writes those cases; a different reviewer may read both
sets and previous probes for leakage. Only aggregate metadata returns to root.
Directory/workflow isolation is not OS-enforced secrecy. Do not claim independence
of operation families, natural population sampling, or general language coverage.

## Human gate

The plan calls for reviewing all expected labels. An AI review or a generic request
to proceed is not case approval. Opening the review page approves nothing. Human
decisions are exported per case and bound to the entire current case hash. Unknown,
duplicated, missing, stale-hash, or wrong-role review records fail validation.
Both independent review and human approval are required for final aggregation.
Approval of zero cases must not produce an empty or misleading score.

An explicit report of having reviewed the presented cases (as supplied by this
user after receiving both page links) may also be transcribed against the verified
original corpus hash. Record the exact quote and transcription provenance; never
invent browser clicks or an exported file. On correction, carry only decisions
whose entire case hash is unchanged. Modified cases need new human confirmation.

Unfinished human review is carried forward explicitly. D24 material/tooling can be
delivered while this gate remains pending; it must not be recorded as all300 labels
approved. See `work-report-24.md` and `evaluation/d24/README.md`.
