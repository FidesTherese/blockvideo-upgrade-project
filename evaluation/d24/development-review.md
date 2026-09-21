# D24 development independent AI review

## Current corrected review (2026-09-20)

The latest independent reviewer is `d24_correction_review`. Current corpus:
`636bf76424480bb6f6bfb71b2971edfed729a90781eaf55105174d71c3f148ae`.
All100 current cases have independent AI approval. Human confirmation from the
original presented corpus carries to80 unchanged cases;20 modified cases remain
pending. The current ledger is `development.independent-ai-review.json`.
The detailed current report and original ledger archive are in this task's
`outputs/d24-corrections/`. See README.md for the exact paths and current pages.

The earlier review below is historical. Its original corpus and ledger were
preserved; subsequent independent review found additional fixture/label defects.

## Original pre-correction review

Reviewer: `d24_label_reviewer` (`independent_ai`). This is not human approval.
Original timestamp/hashes are in the archived
`development-independent-ai-before-corrections.json`, not the current ledger.

All 100 development cases in 10 intact origin groups were read semantically against
`specification.md`, the decisions and operation catalog, D12–D15/D17/D19/D22
contracts, `RULES.md`, and `FORMAT.md`. The final ledger contains one separately
written rationale per case, 100 AI approvals, and no unresolved rejected case.
No model call, application execution, application-code edit, or accuracy result was
part of this review. Human review remains pending.

## Corrections made before approval

- D017 explicitly identifies subtitle **text size**; the old wording could describe
  vertical position. The intended size reduction and label remain unchanged.
- All initial-state narratives now state the actual settings and relevant jobs.
  Failed/pending status examples contain the corresponding job, and active local
  jobs agree with the project state.
- Linked answers, corrections, and dismissal include the relevant prior proposal
  or clarification. This makes the pending meaning available without inventing
  an absent turn.
- Saved pronunciation values include the schema default `accent: null`; accepted
  proposals still allow both omitted accent and explicit null. Settings v2 requires
  its nullable delta key under the operation catalog, so that key is not omitted.
- Terminal/idempotent cancellations explicitly assert the retained job state.
  Confirmed retries assert a new parent-linked job using every supplied current
  setting, and double confirmation asserts one job.
- D037 explicitly records the competing writer and distinguishes the request's
  attributable revision-6 save from the later revision-7 current state. The
  confirmation remains blocked and must not overwrite the later save.

The generator and JSONL agree. Every case validates through `load_cases`; content
hashes bind the complete origin, state, request, event, and expected result.
Corpus SHA-256: `e095e460bd5d969d25caf1a679581441297f100a81ecece363fbce96b969830c`.

## Receipt vocabulary clarification for FORMAT.md

`first_result` means the original language/core result, including a pending
confirmation. `same_id_conflict` rejects changed request content under an existing
identity. `none` means no executable operation receipt is required. `new_request`
means a fresh language request identity; an operation receipt exists only if the
core commits. It does not assert that every new request commits or mutates state.
The field is request-identity behavior, not a count of database receipt rows.

## Development provenance and split-review method

Development intentionally contains D16–D23 requests, failures, and paraphrases.
That provenance is correctly marked `prior_development` for all development cases.
The reviewer inspected the six prior probe scripts, related product contracts and
reports, and extracted 94 distinct text strings from local D16–D23 synthetic
evidence/scripts. The development-only extraction is in the task's
`outputs/d24-verification/prior-development-texts.json`.

This extraction includes surrounding dialogue and some non-request text; it is a
search aid, not a corpus or an accuracy sample. The private split review must assess
origins and meaning as well as normalized strings. Shared product operations alone
are expected; a reworded prior request/failure with substituted numbers is not an
independent held-out origin. All case-level held-out review stays in the sealed
evaluation directory, outside this repository and its output reports.
