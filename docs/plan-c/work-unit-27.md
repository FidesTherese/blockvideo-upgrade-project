# D27 — Semantic candidates and bounded fallback

The user authorized D27 and additional local-model downloads. Compare approved
development cases only; held-out text and labels remain sealed. Human-pending
cases are excluded. E5 is an optional offline CPU encoder pinned by model and
tokenizer hashes. No application request downloads or rebuilds an index.

## Contract

- Rank exact operation versions by maximum document cosine, with stable ties.
  Application/capability/version scope is supplied by the host; live readiness
  never removes a candidate. Similarity is not a probability or execution permit.
  Ranking chooses membership, while the model prompt/schema use stable ID/version
  order, as in All Tools. Ranking order must not change JSON grammar branch order.
- Offer the first 5 operations. For insufficient candidates (unsupported,
  clarification, or invalid structured output), expand once to 8; then, if allowed
  and at most32 scope operations exist, offer all of that same scope. Otherwise
  ask for clarification. The user approved this behavior and its UI on 2026-09-21
  (JST): 「この表示と動作を採用する（推奨）」. Similarity is explicitly not a probability.
  Development evidence changed the initial3→6 pilot to5→8;3 candidates retained
  only43/52 explicit operation labels, whereas5 retained52/52. No held-out tuning.
- Each narrow stage has one model attempt; the full-scope stage may repair output
  once. Maximum4 chat calls,1 embedding query,1 expansion,1 all-scope fallback,
  under one180-second deadline. Transport failure is terminal, not output repair.
- Search failure, stale metadata, missing scope and scope mismatch never mean
  unsupported. Verified current scope may use All Tools on an encoder failure;
  source/index integrity failures stop without a proposal. True unsupported can
  be returned only after full-scope interpretation.
- Every model output is parsed against its offered definitions. No intermediate
  proposal executes. The final proposal uses the existing guards, readiness,
  durable receipt and generation-confirmation path unchanged. Replay precedes
  index loading and inference. Existing All Tools remains the default; explicit
  local index configuration enables D27. D29 comparison modes remain separate.
- Persist ranking, stage counts/results, embedding/chat elapsed time and payload
  bytes. Byte counts are not token estimates; no fabricated token cost. Logs use
  fixed codes and numeric counts, never request text, raw output or local paths.

## Verification

Separate raw Recall@k (explicit acceptable operation versions only), final
proposal agreement (not a full effect/clarification-quality metric), and focused
UI/core effect checks. Run focused tests, all backend/Ruff and frontend
test/build/lint. Record real embedding and local chat calls separately from fake
video providers. D28 readiness annotations and D29 shared comparison runner are
not included. Human approval of fallback presentation is recorded above; it does
not approve the pending D24 corrected labels or the separate D25 UI acceptance.
