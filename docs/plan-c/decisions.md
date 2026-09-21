# Plan C Decisions — Work Units 01–10

## D28 retained blocked candidates (2026-09-21)

The user chose 「この場面と方針で進める（推奨・現在の仕様どおり）」 for the
representative case: ask for speech speed1.2 while generating. Keep the matching
candidate and show that generation blocks changes. Do not cancel generation or
reserve the edit; after completion the user sends a new request. Candidate-state
refresh is observational and does not change the immutable old refusal. This
choice is not a report that the user personally operated the completed D28 UI.

## D24 evaluation preparation (2026-09-20)

The user approved 「別のAI担当に分けて進める」: independently author/review held-out
cases while the implementation agent prepares development material and tooling
without reading held-out content. Synthetic origins substitute for asking one
person to define all users' wording; they are not recorded as user-authored data.
This approval authorizes the preparation method, not all individual expected
labels. Human case decisions remain pending until explicitly reviewed. No final
comparative thresholds under DEC-12 are chosen and no inference score is claimed.

## D23 amendment (2026-09-20)

DEC-11 is fixed for this PC development run: the previously user-selected Ternary
Bonsai 27B Heretic Ja Q2_g64 through LM Studio, loopback only, context 8192,
reasoning none. The user manually loaded it and confirmed server/API values.
See `local-model-setup.md` for exact ID/runtime, measured resources and publisher
scope. This is not a public-release model selection or a small-parameter comparison.
No purchase/download/cloud fallback is introduced. The user chose
「今回、誤保存を防ぐ修正まで行う（推奨）」 after observing an invented subtitle delta.
DEC-09 therefore keeps immediate saves but adds conservative value/pending-intent
checks; ambiguous cases ask, and generation remains separately confirmed.

## D22 amendment (2026-09-20)

The historical table below remains the G1 record. D22 extends DEC-07 with atomic
multi-setting validation/save in one revision. The user explicitly chose:
「設定をまとめて保存し、生成だけ確認する（推奨・従来どおり）」.
DEC-08 therefore continues to require an explicit separate generation permission;
one compound utterance can save settings and leave generation pending. No general
batch of destructive/job-control operations is added. Interpretation repair is
one extra call within a shared 120-second deadline. See `work-unit-22.md`.

| ID | Decision |
|---|---|
| DEC-01 | Completion is gate-based. This phase ends at G1, not a fixed date. |
| DEC-02 | External provider cost is zero; local tools and fake providers only. |
| DEC-03 | Only repository code and synthetic data may leave process boundaries; no secrets or user projects. |
| DEC-04 | Existing behavior remains: setting writes during a live generation job are blocked. |
| DEC-05 | Later language interpretation maps “slightly” to 2 px. G1 accepts only the final absolute integer, 16–120. |
| DEC-06 | Explicit and selected project IDs must agree. Missing target needs input; conflict is invalid. |
| DEC-07 | G1 executes one operation per request. Multi-operation atomicity is deferred. |
| DEC-08 | Setting changes never start generation. Generation requires an explicit separate request. |
| DEC-09 | Clear reversible writes need no confirmation. Missing, ambiguous, blocked, stale, or unsupported requests do not execute. |
| DEC-10 | Candidate information is provisional. The core performs final argument, target, state, and readiness checks immediately before registered dispatch. |
| DEC-11 | Small-LLM integration is deferred. No silent cloud fallback is allowed. |
| DEC-12 | G1 is deterministic tests plus a fake-provider sample; final comparative release thresholds remain deferred. |
| DEC-13 | Operation definitions use JSON and version 1 IDs. |
| DEC-14 | The thin G1 entry is an internal/public structured FastAPI route, not a new CLI. |
