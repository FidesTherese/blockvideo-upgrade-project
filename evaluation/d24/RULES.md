# D24 normative rubric (product decisions through D23)

Use these with specification.md, docs/plan-c/decisions.md and operation-catalog.md.
Existing implementation failures are development observations, not new correct labels.
No final release thresholds or general-language accuracy claims are decided here.

| ID | Expected behavior |
|---|---|
| R01 | Bind to explicitly selected project; absent target asks; text naming a different project blocks. Never silently switch or resolve a project by name. |
| R02 | Explicit valid reversible settings save immediately; no automatic generation. One actual setting change transaction creates one revision; saving identical values creates none. |
| R03 | Subtitle font size integer 16–120. Relative delta resolves from CURRENT saved size. 「少し」 is 2px with direction; unspecified amount asks. Never infer amounts from examples. |
| R04 | Compound settings are atomic. Missing/invalid one means save none. Supplied readings may merge by surface; readings must not be invented. Speech speed is 0.5–2.0. |
| R05 | Generation and retry need a separate user confirmation. Compound settings can save first, then offer generation for that saved revision. Before confirmation no new job; double confirmation creates one job. |
| R06 | Active pending/running generation blocks setting changes and new generation. Status is still readable. Unsupported is distinct from supported-but-blocked. |
| R07 | Same request ID and same content replays its original result, including after restart/state change, before relative recalculation. Same ID with changed content rejects. Concurrent identical requests cause one effect. |
| R08 | Stale revision / state race is rechecked before mutation. Never overwrite a later save or generate a newer revision using an old confirmation. |
| R09 | Explicit job ID required to cancel/retry; selected-project ownership checked. Pending/running cancel is cooperative, stops subsequent work/publication and preserves earlier successful videos. Cancel of an already completed job does not undo its video. |
| R10 | Retry only failed/cancelled jobs, uses CURRENT inputs/settings and creates a NEW job with parent link after confirmation. Unknown external outcome blocks automatic repetition. |
| R11 | Restore requires an explicitly chosen saved revision of this project. A successful restore records a NEW revision even when values already match (D12–D15 contract and test_noop_restore_is_recorded_as_a_new_revision). No generation/cancel. All successful videos remain history. Missing revision asks; absent historical revision blocks. |
| R12 | An answer may complete the same unsaved request, preserving other explicit pending settings and generation intent. Correction after save uses CURRENT values and is a NEW save. Dismissal of an unsaved request has no setting/job side effect. |
| R13 | Status query changes no settings, revision or jobs; saved configuration and current/stale video state are distinguished. |
| R14 | Unsupported operations (mail, arbitrary file deletion, direct script editing through language tools etc.) must not be substituted with supported ones. Pure negative/withdrawn intent is no_operation, not an inverse change. |
| R15 | Compare useful completion and safety separately. A guard asking on an unambiguous executable request prevents damage but is NOT successful completion. Record model proposal correctness separately from application effects. |

Source-request provenance must remain honest. D16–D23 probes, observed failures,
and their paraphrases belong only to development. Synthetic held-out examples
measure this collection under fixed conditions, not every user's language.
