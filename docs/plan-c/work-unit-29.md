# D29 — Controlled comparison modes and common development runner

Scope: section 8 B0/B1/B2/P1/B0+, approved development material only. P2, held-out
evaluation, D30/G5 and D36 freezing are separate. Existing D24 pending decisions
and the unreported D25 human UI acceptance remain separate from this implementation.

## Conditions

- B0: all operation versions; B1: semantic 5→8→full scope; B2: remove known
  blocked/unsupported versions before the same semantic search, add readiness;
  P1: same search as B1 with retained blocked versions and readiness;
  B0+: all versions with readiness. Unknown arguments alone never cause exclusion.
- Same catalog, model/transport parameters, schema builder/parser, canonical branch
  ordering, initial database state, user input and raw state snapshot. Readiness is
  additional provisional presentation, not a changed executor or ranking function.
- Common 180-second total interpretation deadline, four-chat-call upper bound,
  and at most one schema repair at the full allowed pool. B0/B0+ need at most two
  calls; semantic modes may spend two more on candidate expansion. Actual counts
  and bytes are reported; equal upper bounds do not imply equal compute consumed.
- Reset DB and output directory for each case/mode/repeat; rotate mode order by
  case/repeat. No dispatcher/provider is started by the bulk runner. Queuing a real
  durable job and rendering a video are different measurements.
- Same language guards and transactional core for every mode, including generation
  confirmation, replay, revision checks and non-execution. Initial candidate state
  is frozen within a trial; authoritative current state is rechecked by the core.
- Filtered candidates cannot reappear on embedding failure, candidate expansion,
  full-pool fallback or compound generation. Zero candidates produces a question.
- Content-bound human + independent-AI approval is required. Pending and held-out
  cases cannot become scored trials. Record exclusions, incomplete runs, fixture
  limitations, machine checks and proposal/effect agreement separately.
- Retain manifests, exact per-call synthetic payload/schema hashes, candidate
  membership/ranks/hints, source/index hashes, raw model outcomes and actual DB
  deltas. Never call a refused correct task a success solely because it was safe.

## Verification

Check mode difference matrix and unchanged common state/schema parts; blocked
retention/exclusion, unknown arguments, all fallbacks, no-op/question, empty pools,
shared repair/deadline limits, real receipt replay and generation confirmations,
current-state races, exact fixture restoration, corpus approval gate and dependency
direction. Run representative real local-model comparisons, required regression
checks, and report bulk execution separately from an actual UI/video journey.
