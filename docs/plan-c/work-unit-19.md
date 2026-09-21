# D19 — Linked clarification, correction and project-scoped pending requests

The user requested D19 after the verified D18 UI. They selected corrections relative
to the currently saved value: 56px followed by slightly smaller becomes a new 54px
save. Existing receipts are immutable. The project-switch question was not answered;
the stated implementation assumption is to retain each project's pending intent,
restore it by GET on return, and validate state again before any effect. This is not
recorded as an explicit user decision. Intents never transfer to another project.

Add a separate durable dialogue-turn ledger with bounded local utterances, parent
request IDs, continuation kind and a single successor. Each answer/correction uses
a new language/core ID. Existing same-ID replay precedes dialogue state checks.
The interpreter receives bounded, explicitly labelled prior utterances/questions/
structured proposals; no raw project content, secrets or media. It remains read-only.
No-operation/negation is a distinct non-executing proposal. Missing values are asked,
not guessed. Language-supplied pronunciation surfaces/readings must occur in the
linked user utterances (kana normalization is allowed); guessed accents ask again.
Nonempty pronunciation updates merge by surface with saved entries outside the
model, under the same frozen revision checks, so an addition cannot erase others.
Generation always retains its separate explicit confirmation.

Validate parent status, project binding, latest revision and successor under the
claim writer transaction. A stale answer never silently rebases or changes another
project. Blocked/unsupported/error turns cannot be silently substituted with another
operation; users may start a separate intent. Completed settings can be corrected
from their committed current revision. Missing-target roots may acquire a selected
target on answer, but bound targets cannot change.

The core accepts an optional internal pre-dispatch guard executed inside its writer
transaction after replay lookup. Language execution uses it to reject a pending
request superseded by a correction/dismissal, atomically with core effects. This is
not an HTTP/model-editable field and adds no reverse import into language orchestration.
It closes the race between old confirmation and continuation; only one wins.

The UI distinguishes new intent, answer and correction, shows the parent prompt and
question, retains project-scoped sessions, and never confirms or continues on reload.
Explicit dismiss invalidates a pending request without undoing completed operations
or cancelling a running video. Target selection is explicit navigation. D26–D27
retrieval stays deferred. Test old answers, concurrent successors, denial, missing
values/readings, stale settings, target switches and no blocked-operation fallback;
run full repository checks and synthetic real-model/browser/video verification.

Completed implementation and evidence: `work-report-19.md`. The original plan's
human acceptance checkbox remains unchanged; D20 acceptance is separate work.
