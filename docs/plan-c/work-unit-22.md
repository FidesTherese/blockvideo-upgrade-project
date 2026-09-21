# D22 — Compound settings and bounded interpretation repair

## Contract

The user's D22 request authorizes this extension of DEC-07. All settings in a
single proposal validate and commit together, with one revision and receipt.
There is no general batch executor: cancellation, restore, status, multiple
projects and unsupported actions cannot be mixed into a settings transaction.

The user explicitly reconfirmed this on 2026-09-20: save unambiguous settings immediately, then show a
separate generation confirmation. A compound request can therefore have saved
settings and a pending generation, and the UI must show both. With review-all,
settings require their own confirmation first. Declining generation does not undo
saved settings. A question or invalid setting prevents the entire settings save.

`project.settings.update` v1 remains compatible. Version 2 accepts `settings`
and nullable `subtitle_font_size_delta`; the core resolves the latter under its
writer lock after receipt lookup and revision validation. An absolute font size
and a delta together are rejected. Both versions use the same specialist
validation and settings writer. The model cannot calculate an absolute value for
a compound relative change.

An interpretation may request `generate_after_save` for the registered settings
operations only. This is intent, never execution permission. Persist it with the
proposal. After the settings receipt exists, derive one immutable generation
request from its resulting revision and a separate stable ID. Confirmation binds
that exact request. Settings receipt and generation receipt recover independently
after a crash. Resends/reloads never reinterpret or automatically confirm a job.
The existing generation planner unions affected stages into that single job.
Corrections and dismissal invalidate an old pending confirmation under the core
writer lock; revision changes also reject it.

## Interpretation repair

Allow at most one additional model call for malformed JSON or an invalid envelope
shape. Candidate, argument, safety, transport, refusal and incomplete-output
failures stop immediately; missing semantic information asks the user. Repair
receives the original request and fixed failure code, never raw invalid output.
One 120-second deadline covers both calls. No execution capability exists in the
interpreter. Store attempt count and repair failure codes in the outcome. The
durable language claim owns both attempts, so an identical resend cannot reset
the budget. This is distinct from external-provider retry and a new video job.

## Verification

Cover atomic rollback, relative replay, concurrent/restart confirmation, crashes
between commits and acknowledgements, union planning, missing/negated/corrected
intent, stale and superseded confirmation, repair bounds and total timeout.
Run focused suites, full backend/frontend checks, then a controlled browser and
fake-provider video journey in isolated storage. Keep fixed-provider evidence
separate from any actual model inference; record unavailable real-model checks.
