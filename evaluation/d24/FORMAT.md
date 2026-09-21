# D24 case format, version 1

Synthetic Japanese cases; data only. This directory is development material.
Never copy held-out requests, labels, screenshots, or examples into this tree.
The held-out author and independent reviewer may read the specification but must
not run the model or change application code. The implementation agent must not
read the held-out corpus. Isolation is procedural, not an OS access restriction.

Each UTF-8 JSONL row has the following fields (all required unless marked optional):

- `schema_version`: 1
- `case_id`: `D24-D001` etc for development; `D24-H001` etc for held-out
- `group_id`: `D24-DG01` etc / `D24-HG01` etc. All variants of one original
  request, including changed state, remain together. Never split by individual row.
- `split`: `development` or `held_out`
- `source_request`: the original Japanese request for this group, identical across
  all its rows. Development: 10 groups x 10 cases. Held-out: 20 groups x 10 cases.
  These 30 origins are AI-authored synthetic examples, NOT user-authored samples.
- `provenance`: object with `kind` (`new_synthetic` or `prior_development`) and
  `reference` (nonempty source description; prior development is never held-out).
- `tags`: nonempty list from `paraphrase`, `negation`, `omission`, `correction`,
  `compound`, `blocked`, `unsupported`, `resend`, `race`, `boundary`, `target`,
  `confirmation`, `history`, `failure`, `status`.
- `situation`: Japanese explanation of the initial state/event for a human reviewer.
- `initial`: object with `project_id` (positive integer), `revision` (positive),
  `settings` (object, include subtitle_font_size, voicevox_speed_scale and any
  other relevant values), `project_status`, `jobs` (list of objects with id,
  project_id, status, input_revision, cancel_requested, kind), `history` (list of
  objects with revision/settings), `artifact_revisions` (list of positive ints),
  `prior_turns` (list of synthetic dialogue objects; include request_id, text,
  status, settings_saved, and question/proposal when relevant).
  Job status: pending/running/completed/failed/cancelled/unknown.
  Normal managed pending/running jobs of the selected project use its current
  revision and include the full current `input_settings` snapshot: settings cannot
  advance while such a job is live. Terminal jobs and jobs of other projects are
  not forced to match. Corrupted-state fault injection needs a distinct future
  fixture contract; do not pass unreachable normal states as ordinary cases.
  An owned unknown job needs a positive recorded input_revision. It blocks later
  successful generation, so artifact_revisions cannot exceed that input revision.
  Later ordinary settings saves can advance the current revision without a later
  successful artifact; do not force unknown jobs to use the current settings.
- `request`: object with `request_id`, `text`, `target_project_id` (positive or
  null), `base_revision` (positive or null), `continuation` (null or object with
  parent_request_id and relation answer/correction/dismiss).
- `event`: object with `kind` (none/resend_identical/restart_resend/
  same_id_different_body/concurrent_identical/revision_race/confirm_generation/
  confirm_twice/switch_target) and `details` (object; exact changed request,
  competing revision/settings, or switched project ID when relevant).
- `expected`: object:
  - `interpretation`: operation/clarification/unsupported/no_operation/not_called.
    not_called is reserved for pre-model rejection (e.g. missing target or stale
    initial revision). Valid intent can remain operation when execution is blocked.
  - `operations`: list of acceptable EXACT proposal objects containing
    operation_id, operation_version, arguments, generate_after_save. Empty for a
    non-operation label. Include semantically equivalent settings v1/v2 encodings
    where appropriate; do not require a particular arbitrary encoding for success.
  - `target_project_id`: positive or null; model never chooses another project.
  - `submit`: effects object (defined below) after initial submit, before event.
  - `after_event`: null if event none, otherwise effects object. Deltas are TOTAL
    effects from this request across submit+event, excluding an external writer's
    own changes. Explain externally changed state explicitly in situation/details.
  - `rationale`: Japanese normative justification, NOT observed model behavior.
  - `rule_ids`: nonempty list of IDs from RULES.md.
- `known_limitation`: optional string; observed development failure/reference only.

Effects object:

- `outcome`: saved/saved_awaiting_confirmation/awaiting_confirmation/queried/
  needs_input/unsupported/dismissed/blocked/replayed/cancel_requested/cancelled/
  unchanged/generation_queued
- `reason`: nonempty stable semantic label (e.g. explicit_settings, missing_amount,
  project_busy, stale_state). It is not required to equal an API error string.
- `question_for`: list of missing field names (empty unless needs_input)
- `settings_delta`: object containing only changed settings and their FINAL values.
  All other settings must remain unchanged; `{}` means no setting mutation.
- `revision_delta`: 0 or 1; unchanged ordinary setting saves do not create another
  revision. A successful settings.restore ALWAYS records one revision, including
  when settings_delta is empty. Replaying that restore still totals one revision.
- `new_jobs`: 0 or 1; includes submit+event where after_event is specified.
- `confirmation_required`: boolean; generation/retry require separate confirmation.
- `job_assertions`: object with exact relevant lifecycle assertions (empty if none).
- `artifact_policy`: preserve_all_no_new_publication or job_may_publish_on_success.
- `receipt_rule`: new_request/first_result/same_id_conflict/none.

`first_result` means the original language/core result, including a pending
confirmation. `same_id_conflict` rejects changed content under an existing ID.
`none` requires no executable operation receipt. `new_request` means a fresh
language request identity; an operation receipt exists only when the core commits.
This is identity behavior, not a count of database receipt rows. After-event deltas
are writes attributable to this request; an intervening external save can replace
those values. Its final revision/settings must be explicit in event.details and
the rationale, and must not be overwritten by an old confirmation.

No human approvals are embedded in a case. A separate content-bound review ledger
starts pending. Independent AI review is NOT human approval. Approval hashes bind
the entire case, including original group, request, state and expected results.
Changing any of them invalidates previous approvals. Unapproved cases cannot enter
final aggregate metrics. D24 does not run inference or tune prompts.

## Comparison by phase, with narrow display-word aliases

Compare interpretation, target, accepted operation/arguments and each phase's
effects. Output words alone are not a correctness metric. `reason` represents a
semantic code, not exact Japanese explanatory text. `effect_comparison.py` provides
a narrow signature helper for future scorers; it runs no model or evaluation.

- saved / unchanged: equivalent only for a successful ordinary operation with
  settings_delta {}, revision_delta 0, no new jobs, no job lifecycle change and no
  pending confirmation. Same-value RESTORE is excluded because its revision is 1.
- dismissed / unchanged: equivalent only for interpretation no_operation with no
  state effects and no pending confirmation. Never equivalent to clarification or
  unsupported just because nothing changed.
- generation_queued / replayed: equivalent for the CUMULATIVE after_event snapshot
  of confirm_twice only, with one new job and confirmation finished. The exact
  settings, revision, receipt behavior and job assertions must still agree.
- awaiting_confirmation -> blocked and immediate blocked are NOT equivalent as
  task completion/UX. They may both avoid unsafe writes, but phase and confirmation
  are graded separately. Under the current contract, unknown external outcomes
  without a live pending/running blocker allow prepare to await confirmation, and
  execution rejects on confirmation; they create zero new jobs. Keep that timeline.

Receipt conventions are not globally interchangeable aliases. Do not erase reason,
question_for, receipt_rule, artifact policy or job assertions to make a pair match.
Equivalence must not make "refuse everything" pass useful-completion checks.

## Conversation confirmation and unchanged-case transfer

An explicit human report of having reviewed the presented material can be recorded
with the exact quoted message and the matching reviewed corpus hash. Mark it as
conversation transcription, never as a browser export or evidence of clicks.
On a revised corpus, `approval.carry_forward_review` transfers a decision ONLY when
that case's entire hash is unchanged. Modified/new cases remain pending. Preserve
the original corpus and ledger as evidence; the carried ledger has a new corpus
hash, notes its source and is checked normally by the approval gate. This does not
authorize an AI to grant human approval to its own fixes.
