# Plan C Handoff — D31 verified; D32 has not started

## D31 current result (2026-09-24 JST)

Read `work-unit-31.md`, `work-report-31.md`, the D31 section of `docs/DTD.md`,
and `docs/modules/operation-core.md` first. D31 adds the shared host-side
negative-intent veto, strict development adversarial runner, exact persisted-effect
comparison, and fixed unexpected-error response/log boundary. Model proposals remain
untrusted and dispatch remains limited to registered callables after target, revision,
confirmation, reference, dialogue-currency, and current-state checks.

Focused backend: 208 passed with one existing Starlette/httpx warning. Full backend:
1108 passed, 7 ONNX asset/runtime tests skipped, one existing warning. Frontend:
123 passed across 16 files; Ruff, TypeScript/Vite build, ESLint, and whitespace checks
passed. The 26-case deterministic corpus passed 13/13 in All Tools and 13/13 in
stateful mode with zero forbidden setting, job, cancellation, receipt, or artifact
effects; positive controls produced their exact required effects.

Keep deterministic safety separate from model proposal quality. A bounded real local-
model run was not performed because read-only configuration had no `LANGUAGE_MODEL`
and no stateful retrieval index. No cloud or fake substitute was used. Human operation
and independent acceptance were not performed. D32 has not started. No release,
tag, publication, or deployment occurred.

## Historical D30 result (2026-09-21 JST)

Read work-unit-30.md, work-report-30.md and functional-demo.md first.
The user selected an isolated startup menu for All Tools/stateful retrieval and
started LM Studio. Normal product route -> semantic runtime -> common core ->
FFmpeg was exercised from the UI. No D29 ComparisonInterpreter injection.
14 real chat calls (5/9), 10 new language requests, 4 retained MP4s, 40 media/state
checks; backend1061/frontend123, Ruff/build/lint/diff-check passed.
Recovery killed only our synthetic host before render, resumed the same job4,
and preserved input snapshots. User LM Studio remains running and unmodified.

Evidence: task outputs/d30-verification (demo, startup script, reproduction,
verification, source hashes, raw calls, DB snapshots, media, screenshots, review prompt).
Direct history-MP4 browser navigation was blocked by Chrome; retained HTTP bytes
and embedded A/B playback passed. Fake split/image/voice, real local language/
embedding and real FFmpeg; do not claim real speech synthesis.

G5 technical criteria demonstrated, final G5 pending human operation, independent
review, D29 corrected-diff re-review, and approved-commit integration tests.
User submits prompts to another AI: do not spawn reviewers. Negation-to-cancel
and experimental B2 substitution remain known D29 issues. D24 pending20+32 and
D25 human acceptance remain inherited, not approved here. No D31/commit/push.

The earlier handoff below is historical.

## D29 independent review follow-up (2026-09-21)

The user supplied Claude's D29 review: comparison mechanism acceptable, reporting
and aggregation need correction. The original work-report and verification were
written after the review cutoff; their original absence is no longer a blocker.
Original evidence and review files remain immutable. New evidence is in task
outputs/d29-review-followup; read its report and verification for current checks.

Changed only evaluation/comparison.py (outer deadline diagnosis),
evaluation/comparison_scoring.py (project status/full history checks),
scripts/compare_modes.py (called-only metrics, timing caveat and partial reports),
tests and docs. No app/frontend code, model prompt, catalog, guard or .env change.
Offline rescoring of400 verified original records changes0 classifications and
makes0 real model calls. B2/P1 candidate pools differ only on D025;71 of72 model
pairs have identical payload sequences. Four hundred trials cannot establish
their relative merit. Timing remains incomparable because of cache/order effects.

Keep busy9/10 and all-mode D079 negation-to-cancel visible. No product policy was
changed, no pending case approved, no held-out content read. Pilot is a distinct
source version. Original1026/121 regression and90 reviewer-focused tests are
historical; follow-up results are recorded separately. Corrected diff has not had
an independent rereview; do not spawn one (user will send the prompt themselves).
No D30/G5, commit, push or publication. D24/D25 outstanding decisions remain.

The original D29 handoff below is retained as historical context; its review
pending status describes the initial evidence cutoff, before this follow-up.

## Current D29 result (2026-09-21 JST)

Read work-unit-29.md, work-report-29.md and comparison-modes.md. The user approved
B0/B1/B2/P1/B0+, shared conditions and approved-development-only use. They will
give the review prompt to another AI themselves; do not spawn/send a review agent.
The prompt is outputs/d29-independent-review-instructions.md in the task workspace.

Experiment-only CLI scripts.compare_modes uses the same language service/core;
app has only a structural selector interface and all-tools trace compatibility.
No ordinary default/.env change. Hard Filter remains experiment-only. B2 excludes
known blocked/unsupported but retains unknown arguments, including all fallbacks.
Same raw state, 180s/four-call cap, one full-pool JSON/output repair, parser/guards/
current core checks. Fresh DB/media for each trial; no bulk media dispatcher.

48 new tests; backend1026/frontend121/Ruff/build/lint pass. Real local model:
80 approved development cases × five modes =400 trials,434 real chat calls;
submit-effect matches B0=73,B1=72,B2=73,P1=73,B0+=73 out of80. Not full task
accuracy. No unexpected setting/new-job mutation on mismatched cases. All400
replays no inference/effect;2602 saved-evidence invariants pass. Raw B1/P1 ranks
and first candidates equal on72 actually interpreted cases. Source hashes fixed.

CRITICAL TO KEEP VISIBLE: busy-edit integration is9/10. B2 chose status.get for
the requested speed edit while busy, adding a read-only receipt. No setting/job
mutation, but NOT successful non-execution. Do not erase the failure or strengthen
only B2. Independent review must distinguish selector defect from model choice.
Other real-model mismatches, including all-mode D048 invalid arguments, remain.

B0+ browser journey:3 real model calls;64px save/explicit generation doubleclick,
56px save/stale old video/normal generate;2 real MP4s,30 media/state checks passed,
latest browser playback ended. Split/image/voice fake; no real VOICEVOX audition.
Old media direct URL blocked by Chrome; old MP4 HTTP/decode passed. Initial media
verifier read cursor blocked a replay writer; fetchall fixed only the verifier.

Evidence: task outputs/d29-verification. Owned8000/5173 servers/tabs stopped;
LMStudio1234 PID28096 unchanged and running. No commit/push. Independent review,
approved-commit integration and D30/G5 not passed. D24 pending20+32 and D25 human
acceptance unchanged. Held-out text/labels/HTML never read. Do not infer performance
superiority: cyclic-order cache effects and warm asset setup are not controlled.

The following D28 section is retained as historical context.

## Current D28 result (2026-09-21 JST)

Read work-unit-28.md, work-report-28.md and candidate-readiness.md. The user chose
the speech-speed1.2-during-generation case: keep the candidate, refuse the edit,
never cancel/queue it automatically, require a fresh request after completion.
D28 is complete; D29 has not started and G5 is not passed. AI operated the UI;
do not record the user as having personally operated the finished D28 screen.

Exact-version provisional DTOs use the existing core target/busy predicate. Unknown
arguments say needs_input/arguments_unchecked, never final-ready. Language supplies
a fresh read-only callback per semantic stage; ranking/membership stay unchanged.
Final core checks/confirmation/receipts are unchanged. The explicit read-only
candidate-state refresh returns current reasons separately from immutable history.
Readiness annotations default on only for an explicitly configured semantic index;
LANGUAGE_RETRIEVAL_READINESS=false preserves the D27 baseline. All Tools remains
the ordinary default. Hard Filter is only evaluation.readiness_filter, with no
product import/config/route; D29 owns the shared comparison runner.

Focused112 / backend978 / frontend121 / Ruff/build/lint/diff-check passed.
Real E5/Ternary synthetic paired-state probe8/8 (four identical-text pairs), with
unchanged raw ranks and no busy-case effects. This is not D24/general accuracy.
UI used a test-only fake voice delay to hold a genuine running job. Actual busy
refusal, read-only reason refresh after completion, new request save, explicit
generation and two retained MP4s passed34 checks. Browser played the latest MP4.
Fake voice ignores speed, so the two videos have identical bytes; the generation
snapshots correctly record1.0/1.2 and only audio/render rerun. No real-speech claim.
UI cold E5 load47.553s triggered the30s notice; next query9ms. Chat calls10 total.

Evidence: `C:\Users\Danir\Documents\Codex\2026-09-19\c-users-danir-downloads-blockvideo-upgrade\outputs\d28-verification`.
Read verification.json, REPRODUCE.md and cleanup.json. Test servers/tab closed,
user LM Studio1234 left running. No .env/user DB/held-out/approval changes or
commit/push. D24 pending52, D25 separate UI acceptance and D27 general9 mismatches
are not cleared by this D28 result. Earlier sections below are historical.

## Historical D27 result (2026-09-21 JST)

Read work-unit-27.md, work-report-27.md and semantic-retrieval.md. The user explicitly
approved the 5 -> 8 -> all-scoped-operations policy and UI wording, including the
statement that similarity is not a probability. D27 is complete. D28 has not
started; G5 is not passed. This does not approve outstanding D24/D25 items below.

Optional hash-pinned multilingual-e5-small ONNX CPU encoder: 384 dimensions,
9 exact operation versions / 90 public documents. Read-only ranking and bounded
semantic composition use the existing guarded operation core. Replay precedes
index/inference. Maximum 1 query embedding / 4 chat calls / 180 seconds. No readiness
filtering, scope broadening or execution of intermediate proposals. All Tools
remains the default; set LANGUAGE_RETRIEVAL_INDEX explicitly to enable retrieval.
The actual .env was not edited. D29 shared comparison modes are separate.

Approved development80 -> model73 (7 prechecks skipped) -> positive operation52.
Recall@5: Nomic40/52, E5 52/52. Adopted real-model proposal agreement64/73, not
full-effect success or general accuracy. D25 historical All Tools was65/73;
do not claim an overall improvement. Three probes are preserved (60/73,58/73,64/73).
Read-only audit of the final9 mismatches finds existing guard veto/parser rejection;
that audit is not9 fresh effect tests and those cases remain task failures.

Backend962 / frontend117 / Ruff/build/lint/diff-check passed. Real UI10 requests,
12 chat calls, isolated receipt/media checks30/30, two fake-provider MP4s64/68px
retained and fully decoded. The latest video played to completion in Chrome.
390px checked. The attempted live busy rejection raced with generation completion;
only the automated common-core test supplies busy-rejection evidence.

Evidence: `C:\Users\Danir\Documents\Codex\2026-09-19\c-users-danir-downloads-blockvideo-upgrade\outputs\d27-verification`.
Read verification.json, REPRODUCE.md and cleanup.json. E5 assets are under backend
storage/embedding-models/multilingual-e5-small; the verified index is evidence/index-e5.
Dedicated servers8000/5173 and test tab are closed; user LM Studio1234 was left
running. No model unload, user DB/.env edit, held-out reading, commit/push or release.

Historical sections below describe their own completion time, not current progress.

## Historical D26 result (2026-09-20)

Read work-unit-26.md, work-report-26.md and operation-index.md. The user selected
existing Nomic for lifecycle verification; Japanese semantic retrieval/model
selection remains D27. Local JSON bundles plus an atomic manifest, no new dependency
or download. Nine exact versioned definitions -> 90 documents -> 768-dimensional
normalized vectors. Canonical descriptions/examples/input schema remain in
operations/definitions.json; search_scope.json adds only app/capability bindings.

Real embeddings: connection probe plus three full builds, 37 HTTP calls total.
Two canonical builds are byte-identical; the third uses a synthetic changed
definition/version copy (91 documents). Fourteen real lifecycle checks passed.
Reader rejects stale hashes/versions, wrong model profiles, unknown IDs and
self-consistently forged document metadata. Capability filtering has no live
readiness input. Only the developer CLI writes indexes. No product UI connection,
ranking or retrieval-accuracy claim in D26. D27 has not started; G5 is not passed.

Focused89 / backend922 / frontend116 / Ruff/build/lint/diff-check passed. Initial
focused88+2 errors were oversized pytest parameter IDs exceeding the Windows
32767-character environment-variable limit; short explicit IDs fixed the test
issue. Preserve the original failed log.
No new browser/MP4 run, user DB/.env edit, held-out reading or approval changes.
D24 pending52 and D25 human UI acceptance remain outstanding.

Evidence: `C:\Users\Danir\Documents\Codex\2026-09-19\c-users-danir-downloads-blockvideo-upgrade\outputs\d26-verification`.
Use index-first or rebuild with the documented CLI. Do not use the synthetic
index-updated-synthetic for production. The weight/profile must match. On each
future candidate lookup, pass a fresh load_sources() snapshot, then keep the
existing interpreter/core exact-version/current-readiness/confirmation checks.
Leave user-owned LM Studio and Ternary Bonsai running; Nomic is also loaded.
No commit/push, cloud API, publication or new test servers/tabs.

## Historical D25 result (2026-09-20)

Read work-unit-25.md and work-report-25.md. The user selected a 30-second notice.
Waiting/recovery UI, durable diagnostics, allowlisted pseudonymous logs, HTTP
failure status, approved-development probing and model output tuning are complete.
The settings model schema offers three equivalent key orders; canonical validation
and core effects/confirmation are unchanged. D26 has not started.

Real Ternary Bonsai at context8192: approved development80, model cases73,
pre-model cases7 separately skipped. Baseline52/73 -> adopted65/73. No transport
errors in six complete post-reboot probes (438 model calls). One invalid-argument
case per later run is not a connection failure. Remaining8 recorded proposals
are vetoed by existing guards or rejected by the interpreter; do not count them
as successful requests. No held-out text/labels were read. D24 pending52 remain.

Real-model HTTP journey12 requests and browser save/generation passed. Two MP4s
were generated with fake split/image/voice, decoded and subtitle/hash checked.
30-second notice, error/reload, double-submit/confirmation and390px were checked.
The in-app browser crashed once on video play; Chrome played the same video to
the end without media error. Human acceptance of the new UI is not reported.

Final regression: backend860, frontend116, Ruff/build/lint/diff-check passed.
Pre-reboot import timeouts/partial inference logs are preserved; after the user's
reboot the unchanged subprocess deadline and the full suite passed.

Evidence: `C:\Users\Danir\Documents\Codex\2026-09-19\c-users-danir-downloads-blockvideo-upgrade\outputs\d25-verification`. Read verification.json, REPRODUCE.md and cleanup.json.
Only owned test servers/tabs are stopped. Leave the user's LM Studio/model alone.
No commit/push, cloud model or publication. G4 technical pass is not a release
approval or a final-evaluation score; preserve the limitations above.

## Latest D24 corrected material (2026-09-20)

Claude's independent audit was followed by corpus/tooling corrections and a
separate independent re-review. Development20 and held-out32 cases changed;
the original source-request groups are intact. Current development corpus is
636bf76424480bb6f6bfb71b2971edfed729a90781eaf55105174d71c3f148ae.
The current held-out metadata is evaluation/d24/held-out-manifest-v2.json.
Keep v1 and the first v2 candidate as history, never as the current review target.

The explicit human report below is now transcribed against the verified original
corpora, with quote/provenance. It is not an invented HTML export or click record.
Only full-case hash matches carry: development80 and held-out168 approved;
modified20+32 remain pending. Do not ask the user to redo the unchanged248 cases
or require an export retroactively for their already explicit confirmation.
New modifications still need human confirmation. D25 has NOT started.

Current public evidence is this task's outputs/d24-corrections/report.md and
verification.json. Development review page: development-changes-review-v2.html;
current human ledger: development-human-current-v2.json. Sealed v2 review page is
human-review.changed-only.html in the location from the public manifest. It starts
with changed32 cases; the full200 ledger remains embedded. Do not inspect it as an
implementation agent. Only the separate evaluator handles private text and notes.

The same-value restore label was incorrect: successful restore records +1 revision
even when settings_delta is empty. Existing product behavior is preserved and
tested directly. Evaluation comparison aliases are narrow and preserve all effects,
receipts, interpretation, and phases. Immediate refusal is NOT the same as waiting
for confirmation and then refusing. Do not tune product behavior to these labels.

Claude independently verified the old review UI (43 checks on each of2 synthetic
copies). This correction pass checks the seeded ledger/default pending filter by
unit/static checks only. Root has not bypassed the earlier local-file browser
policy rejection. No new model/provider calls or user DB edits took place.
See work-report-24.md for current regression results and the historical baseline.
Final correction checks: D24-specific45, backend841, frontend111 passed;
Ruff/frontend build/lint/review-JavaScript syntax passed. One existing
Starlette/httpx deprecation warning. Current detailed evidence is verification.json.

## Latest human report and external review handoff

After receiving both review-page links, the user reported 「人間で確認しましたが、特に問題がありませんでした。」
and requested a Markdown brief for another AI. That human report is received; do not ask them to repeat the same review.
Individual exported ledgers were not supplied in this message. Historical pending ledgers and evidence remain unchanged;
do not invent UI click/download evidence or confuse their original counts with the latest human report.
See work-report-24.md and the task output `D24-independent-review-instructions.md` for the separate AI review brief.

## D24 material baseline before the human report

Read `work-unit-24.md`, `work-report-24.md` and `evaluation/d24/README.md`.
Development100 cases/10groups include prior development failures. Held-out200
cases/20groups are independently authored outside this repository and workspace.
Do not read their text/labels when implementing or tuning. Use the manifest's
aggregate metadata; a separate evaluation reviewer handles private case changes.
The user approved separate AI preparation; no human case approvals are implied.
Approval ledgers bind all input/state/expected data hashes. D25 uses development
only. Unapproved cases are excluded from later final aggregation. There is no D24
model inference score. Product code, normal DB and .env are unchanged in D24.

Checks: D24-specific26, backend822, frontend111 pass; Ruff/build/lint/diff and review JS
syntax pass. Browser policy rejected the local review page URL; visual/interaction
QA was not completed and no workaround was attempted. Review materials are ready
for human checking, which must not be recorded as already complete.

## Current D23 state

Read `work-report-23.md` and `local-model-setup.md`. User manually started LM
Studio; real Ternary Bonsai Q2_g64 inference is verified at loopback:1234, context
8192, reasoning none. Existing `.env` is unchanged; use the documented configuration.
New readonly connection route/UI distinguishes listing from actual inference.
Missing/mismatched response model IDs are terminal errors, including observed
LM Studio server-side fallback on an absent model identifier.

The user authorized accidental-save fixes after real failures. Value/pending-field
guards ask before saving invented subtitle amounts, unrelated numeric settings,
missing explicit speed, and dropped known pending compound fields. They never
rewrite or calculate model values. Short-answer dialogue can still require a new
complete request; do not claim arbitrary-language correctness. Prompt unchanged.
Raw development probe: 15/20 exact, not held out, not 20/20 after guards.
Backend 796, frontend 111; lint/build/Ruff passed. Browser and final MP4 verified
with real language inference and fake generation providers. Next is D24; preserve
the failed synthetic examples as development evidence, not held-out evaluation.
Owned test backend/Vite/tab were stopped/closed. User-started LM Studio remains
running on 1234. Normal LANGUAGE_MODEL remains unset; documented setup is opt-in.

Historical D22 report follows.

## Current D22 state

Read `work-unit-22.md` and `work-report-22.md`. The user explicitly reconfirmed
immediate atomic settings save followed by a separate generation confirmation.
Settings.update v2 resolves a relative font delta plus other settings under the
core lock, after replay/revision checks, and reuses the v1 settings writer.
The catalog has eight IDs and nine versioned definitions; v1 remains compatible.

LanguageResponse keeps the settings `result` separate from `generation_request`
and `generation_result`. A ready response can have `executed: true` for settings
and require confirmation for generation. Never treat its original base_revision
as the generation revision: use generation_request.base_revision. Both phase
receipts recover independently. Dialogue marks settings_saved so a model does not
misread a pending generation as unsaved settings. Confirmation/dismissal races are
fenced inside core transactions.

Repair is at most one additional model call for invalid JSON/envelope only, with
a shared 120-second deadline. No transport/semantic-argument retry or model call
after committed execution. Attempts and repair codes are persisted in the outcome.
Final regression: backend 749, frontend 109; Ruff/build/lint passed.
UI/fake media: 20/20 reconciliation checks, two MP4s, lost response + resend,
double submit/confirm, reload, correction and 390px layout. Actual D22 model
inference was not run; LM Studio was stopped. Do not claim D22 wording accuracy.
Live backend stop/restart was rejected by automatic approval (`blocked by policy`);
see evidence cleanup.json for the final process state. No bypass was attempted.

At the end of D22 the next unit was D23; its outcome is recorded above.

## Current state: D20 progression approved, D21 connection verification complete

On 2026-09-20 the user said: 「確認動画を見ました。問題ありません。これで進めてください。」
Record the demonstrated real-VOICEVOX video as accepted and D21 progression as authorized.
Do not claim the user performed hands-on UI tests; none were reported. AI browser
evidence plus user audiovisual acceptance are the documented basis for proceeding,
rather than a claim that every original G3 human checkbox was performed.

Read `work-report-20.md`, `work-report-21.md`, `operation-catalog.md` and
`schedule-after-20.md`. Claude's D20 real-model run used no fixed replies: 16 UI
calls (15 successful, one connection failure), 45 probe calls, 60 received server
requests, seven jobs and five artifacts. C used real VOICEVOX 0.25.2; split/image
remained fake. Codex independently reconciled the saved DB and five MP4s.
Evidence: workspace `outputs/d20-claude-verification/` and `d20-claude-review.json`.
The earlier `d20-verification/` fixed-adapter run remains historical evidence only.

D19 and D20 dialogue probes are 38/39, not 39/39 (corrected from saved JSON/logs).
The implicit restore case guesses a revision; the application asks instead and
does not execute. Track the raw-model failure separately from this protection.
One unexplained LM Studio exit and cold-load stability remain open. Memory/disk
causality is unproven. The earlier Codex server-start policy rejection is historical;
do not treat another agent's run as permission to bypass this environment's controls.

D21 reused the existing eight registered operations. All ProjectPatch fields are
represented by settings.update; typed forms and language use the same core, while
legacy PATCH shares validation/save/invalidation services. Added 11 backend and five
frontend connection/validation tests. Final totals: 718 backend, 105 frontend;
Ruff/build/lint passed. No production code, catalog schema or model prompt changed.
Five new MP4s use real VOICEVOX with fake splitting/images, through typed core
requests and the managed worker. Subtitle-only changes reuse audio; speech speed,
speaker and reading rebuild audio/render; API remains API in subtitles while the
engine receives エーピーアイ. Evidence: workspace `outputs/d21-verification/`.
These typed media checks are not additional real-model wording tests or a new
human listening acceptance. The approved D20 video is a separate artifact.

At the end of D21, the next planned unit was D22; its completion is recorded above.
Retrieval remains D26–D27. Target-switch retention remains the existing
documented assumption, not an individually answered preference.

## Completed D19 dialogue

Read `work-unit-19.md` and `work-report-19.md`. Linked answers/corrections/dismissals
use new language/core IDs, a durable `language_turns` ledger and a single-successor
constraint. Replay still precedes successor/current-state checks. Pending parents
are validated under the claim writer; an internal guard checks invalidation again
inside core dispatch's writer transaction, closing the old-confirmation race.
The interpreter stays read-only. No-operation is a separate non-executing proposal.
Pronunciation values must be supplied in user text; additions merge existing entries
outside the model. Empty settings changes and echoed questions become clarification.

The user chose 56px -> slightly smaller = new 54px save. Project-switch retention
was unanswered; the stated assumption retains a pending request on its own target,
restores by GET and revalidates before continuation. It is not a confirmed preference.
The UI exposes new intent, answer, correction, explicit dismissal and target selection.
Generation keeps its separate confirmation. A dismissal never undoes saved settings
or stops a running video. Blocked/unsupported/error results cannot continue into a
different operation. Old answers, stale revisions and cross-project replies fail.

Final checks: backend 707 passed (24 D19 tests), frontend 100 passed (12 new),
zero skips; Ruff/ESLint/TypeScript/Vite/diff checks pass. The final local Ternary
Bonsai development probe passes 38/39 including 27 D17 cases (corrected from evidence); initial 36/39 and
browser misinterpretations are documented, not hidden or counted as successes.
Real browser tests used two synthetic projects. Project A ended at revision 6,
font 54, one successful generation/artifact; B stayed at revision 1/font 48.
The 1280x720 H.264/AAC MP4 decoded fully and played in the browser. Providers were
fake; the production FFmpeg pipeline was real, with no external API cost.
Model-disconnected linked replay and superseded confirmation rejection passed.
Evidence is outside Git in the task workspace `outputs/d19-verification/`.

Local utterance text is now persisted in the separate additive table; no body
logging or automatic pruning is added. Context is limited to eight prior turns
and 6000 characters including current text. Old D17/D18 records without dialogue
text retain replay but require a complete new intent rather than a continuation.
The real DB and `.env` are unchanged; preview processes/model/server are stopped
after verification. Existing uncommitted D11–D18 work is preserved.

The subsequent D20 acceptance and D21 work are recorded above. The original plan's
human hands-on checkboxes remain unchanged. Retrieval is still
deferred to D26–D27; do not duplicate it in the All Tools baseline.

## Completed D18 UI

Read `work-unit-18.md` and `work-report-18.md`. The user selected the inline panel
at the top of project detail. It uses D17's API; production backend contracts are
unchanged in D18. `useLanguageRequest` owns exact request identity, sessionStorage,
explicit generation confirmation, GET-only reload/polling and late-response fencing.
Result cards use core receipts/settings history and verified jobs/artifacts.
Unknown delivery locks mutations and refreshes observed state without claiming success.
Existing forms and arbitrary settings-history restore remain usable.

Final checks: backend 683 passed, frontend 88 passed (30 D18-specific), no skips;
Ruff/build/ESLint/diff checks passed. Real local Ternary Bonsai was used in the browser
with synthetic data, fake video providers and real FFmpeg. Duplicate clicks,
lost acknowledgement, delayed submit/reload, stale confirmation, generation-time
blocking, missing-value clarification, history restore and 390px layout were verified.
Two immutable 1280x720 MP4s decoded fully. The model-disconnected error was verified
after unloading the task model. Preview processes and LM Studio HTTP server were stopped.
Evidence lives in the task workspace `outputs/d18-verification/`, outside Git.
The real `.env` and real project DB are unchanged; normal startup still needs a
configured and running local model. Existing D11–D17 uncommitted work is retained.

D19 multi-turn correction is now implemented above. The user's conditional request for vector
search was checked against the schedule: D26 covers indexing/method selection,
D27 semantic retrieval, D29 comparison modes. Do not duplicate that work in D18.
The original schedule's human acceptance checkbox remains for the user to review.

## Completed D17 boundary

Read `work-unit-17.md` and `work-report-17.md` before changing orchestration.
`app.language_operations` sends all eight approved definitions to D16's interpreter
without retrieval, fixes target/revision outside the model, and uses the existing
operation core. Four `/api/language/requests` routes prepare, submit, look up and
confirm immutable requests. Language IDs and core IDs are separate durable values.
Core receipt recovery requires canonical body equality, not only a matching ID.

The user chose immediate settings saves and separate generation confirmation;
unspecified subtitle amounts ask, with the prior "slightly" = 2 px rule preserved.
They asked us to cover varied wording instead of requiring one personal fixed phrase.
Generation/retry always needs a separate confirmation even if the model proposes it
from a settings-only request. Explicit job/history references must match the text;
the current revision is never accepted as an inferred restore target. Application
clarifications preserve the model's original parsed proposal for inspection.

Default `LANGUAGE_MODEL` is unset; no model calls are enabled until configured.
Local configuration is separate from generation providers. Ternary Bonsai was used
with `reasoning_effort: none`, 8192 context, all eight definitions and synthetic data.
The final wording check passes 27/27 development cases; earlier misclassifications
are retained as counterexamples. This is not a held-out general accuracy result.
Two actual FFmpeg MP4s from natural-language and typed requests have identical saved
settings and media hashes. See the report for counts, conditions, evidence and limits.
Final checks: D17 45 passed; backend 683 passed with zero skips; frontend 58 passed;
Ruff/build/ESLint/diff checks passed. The task-owned model was unloaded and the
local HTTP server stopped after verification. The real `.env` was not changed.

D18 normal UI and D19 multi-turn correction are now implemented above.
Do not add retrieval to this All Tools baseline. Preset/embedding matching was
not implemented as part of D17 and is reserved for the planned D26–D27 work.
Original plan human acceptance checkboxes and historical D01–D16 reports are unchanged.

## Historical D16 boundary (D17 integration supersedes its deferred scope)

`app.interpretation` and `scripts.probe_interpretation` implement a strict,
read-only model boundary. Read `work-unit-16.md` and `work-report-16.md` first.
There are no imports of execution handlers/core/bootstrap/DB from interpretation,
no production natural-language endpoint and no product UI change. Proposals
always report `executed: false`. Local HTTP uses JSON Schema without an SDK;
no retry, schema relaxation, proxy, redirect or remote endpoint is allowed.
Final offline checks: D16-focused 118 passed; backend 638 passed with zero skips;
frontend 58 passed; Ruff/build/lint/diff checks pass. Existing Starlette warning only.

The user selected local inference and Ternary Bonsai from installed models.
They approved the five fixed synthetic requests, fictitious minimal state and
zero external API spend. Real inference is now verified: final five cases all
match expected operations/arguments, clarification, and unsupported responses.
The default thinking mode consumed the 768-token cap without producing content;
explicit `reasoning_effort: "none"` fixes this verified connection. The adapter's
generic default still omits the parameter. No automatic compatibility fallback.
The prompt now explicitly distinguishes missing arguments from unsupported
operations. Earlier failed probes are preserved separately, not counted as passes.

For reproduction, load `ternary-bonsai-27b-heretic-ja` as `blockvideo-d16` in LM
Studio (context 8192, parallel 1, TTL 3600) and start the loopback server on 1234.
Then run from backend:

```powershell
python -m uv run python -m scripts.probe_interpretation --model blockvideo-d16 --reasoning-effort none --output <absolute-evidence-path.json>
```

After verification, the task-owned model was unloaded and the local HTTP server
stopped. Evidence lives in this task's `outputs/d16-verification/`; the report
documents 17 diagnostic/probe calls using only the same five synthetic request
types, all local and zero external API cost. D17 execution and D18 UI are still
separate requests. Prior D11–D15 uncommitted changes below must be preserved.

## Completed D15 boundary

Units 01–10 establish G1. D11 adds durable receipts and revision/transaction safety.
D12–D15 now implement necessary-stage planning, input-bound successful-video history,
remote-call uncertainty and restart recovery, plus separate cancel/current-settings
retry/arbitrary recorded-settings restore handlers and project detail controls.
Read `work-report-12-15.md` for G2 evidence, including actual browser and MP4 verification.
Changes are local/uncommitted on `codex/plan-c-d12-d15`, based on `c6924d7` and prior D11 work.

## Start here

1. Read `specification.md`, `docs/DTD.md`, then `work-unit-12-15.md`.
2. Read `backend/app/operations/definitions.json`, `control_handlers.py` and
   the shared generation/history/journal services before altering contracts.
3. Run `docs/plan-c/commands.md` checks with synthetic data and fake providers.
4. D16 has now been requested and is tracked above; D15 evidence stays historical.

## Preserve

- Catalog metadata cannot execute code; only explicitly registered handlers dispatch.
- Receipt lookup precedes current-state validation and relative-value resolution.
- Settings, revision, receipt and pending generation intent commit together.
- Cancellation and publication serialize on the same DB writer boundary.
- Original input snapshots stay immutable; checkpoints may add generated style/blocks,
  but may not adopt different settings/runtime/effective provider identity.
- All successful final videos remain history. Missing/corrupt media cannot be current.
- Cancel never restores settings. Restore never auto-generates or auto-cancels.
- Retry uses current inputs and a new job; transport resend retains ID and original body.
- Unknown external outcomes remain unresolved; repeating POST is not result lookup.
- Models/shared services never import operations or API.

## Limits

One backend server per database. Process-local BYOK credentials are not restored
after restart. Unknown remote calls currently have no provider reconciliation UI.
All successful videos consume storage; there is no automatic pruning or hash cache.
Legacy create/quick-create and direct endpoints retain their old identity-less APIs;
replay guarantees require the operation API. Quick project plus job intent commit
together, and all production generation uses the managed snapshot/journal runner.

Original work-unit-01–10 and D11 reports remain historical. No paid API call,
real-data migration, commit/push or deployment was performed for this delivery.
