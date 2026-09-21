# D20 — G3 acceptance of the All Tools natural-language UI

2026-09-20 update: after real-model/VOICEVOX verification and evidence review,
the user accepted the demonstrated video and instructed work to proceed. D21 is
authorized on that basis. Hands-on UI testing by the user remains unreported;
do not mark that historical checklist item performed. The progression decision
and evidence are recorded in `work-report-20.md`.

The user requested D20 after D19. Preserve the existing choices: settings save
immediately, generation requires a separate confirmation, slightly means 2px,
corrections use current saved values, live generation blocks edits, retry uses
current settings, cancellation is cooperative, all successful videos remain.
Project-switch retention remains the stated D19 assumption, not a confirmed choice.

Run one representative synthetic browser journey through explicit/missing setting
values, linked correction, status, generation confirmation, cooperative cancellation,
lost acknowledgement and identical resend, current-settings retry, successful video
history and ordinary form/history regression. Reconcile UI, persisted receipts,
revisions, job snapshots, artifacts, subtitles and decoded media. Use the selected
local Ternary Bonsai and isolated storage; never alter the real DB or .env.
Use deterministic fake generation providers and real FFmpeg, as AGENTS.md requires.
Any test-only transport/provider delay or failure must be identified in evidence.

Review the D16–D19 boundary and fix only reproduced acceptance defects. Run focused
checks when fixes are needed, then the full required backend/frontend checks.
Produce a short demo, machine-readable evidence, a pass/pending/fail matrix,
known limitations, and a conditional D21–D40 work/cost/schedule update.
The original plan's human checks are not evidence that a person has tested it.
Record human usability/real-speech review separately; do not claim G3 sign-off or
advance to retrieval while required acceptance remains pending. D21+ is not scope.
