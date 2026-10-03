# Mission 40 — D40 release-readiness decision tooling (2026-10-03)

Readiness: **Not ready**. This delivers the D40 decision *tooling* and its synthetic
verification. No real decision, evidence, tag, release, publication or deployment is
created. Real D37 aggregate evidence, the D36 control publication, fresh D39
verification and human/independent review do not exist, so the actual decision for
the frozen candidate remains Not ready.

## Scope

Base: `main` at `daad99e` (D39 rounds 1–2 merged); branch
`claude/d40-readiness-decision`. The frozen D35 commit
`522775516c0797abdb313e3432339a3a444b7ae2` is unchanged. No application, frontend,
operation definition, dependency manifest or lockfile changes. D37 result contracts,
D38 `ImportValidation` and D39 `VerificationManifest` are imported unchanged.

| File | Responsibility |
|---|---|
| `backend/evaluation/evidence_json.py` | Adds `parse_canonical_typed`; `parse_canonical_model` shares the same raw canonical checks and error messages. |
| `backend/evaluation/release_decision.py` | Models, detached-digest loaders, running-closure check, fixed 27-gate engine, Markdown rendering and no-replace publication. |
| `backend/evaluation/scripts/attest_release_decision.py` | Separate Git-using source attestation; publishes only on exact detached aggregate equality. |
| `backend/scripts/decide_release_readiness.py` | Decision CLI: local reads/hashes and output writes only; exit 0 only for Ready/Conditionally ready. |
| `backend/tests/test_d40_readiness_decision.py` | Synthetic gate arithmetic, transfer provenance, CLIs, side-effect, path and import-closure regressions. |

Contract details that the DTD left open are recorded under `D40 implementation
amendments (2026-10-03)` in `docs/DTD.md` (loader failure reasons, the D36 tool
keyword, freeze refusal, 27-row gate order, output-directory rule, running-closure
check, shared-parser consequence for D38/D39 aggregates).

## Mandatory gates and evidence

| Work-unit gate | Implementation | Regression |
|---|---|---|
| 1–2 Safety | `<mode>_safety` per mode and category | `test_any_unauthorized_effect_blocks` |
| 3 Integrity / detached digests | Loaders verify exact lowercase 64-hex detached digests before parsing and name every refused input; engine recomputes model hashes; D38 identity binds the publication's D36 tool | `test_d38_loader_names_each_failed_transfer`, `test_d39_loader_rejects_verifier_tool_swap`, `test_loader_hash_maps_must_match_model_bytes`, `test_aggregate_d36_tool_must_be_the_publications_tool` |
| 4 Independent D39 validation | Exact ordered nine commands, deadlines, caps, native bindings; six receipts rehashed; integrity flags; runtime source equals the freeze aggregate | `test_failed_d39_prefix_and_flags_are_independent_blockers`, `test_verified_runtime_must_be_built_from_the_frozen_bytes` |
| 5 Decision source attestation | Fixed 31-path inventory rehashed before and after the decision; running modules must be the attested files; shared D38/D39 sources must be current | `test_decision_tool_attestation_is_rehashed_without_git`, `test_decision_cli_refuses_unattested_source_and_tracked_output`, `test_decision_cli_refuses_a_root_that_is_not_the_running_code`, `test_upstream_tools_must_share_the_current_sources`, `test_attestation_cli_uses_committed_root_and_detached_aggregate` |
| 6 Non-vacuous coverage | Topology, partition, derived denominators and count bounds re-derived | `test_empty_category_coverage_is_never_a_vacuous_pass` |
| 7 Thresholds | Integer cross-products, 90% overall / 80% category | `test_overall_quality_uses_exact_integer_threshold` (18/20 vs 17/20), `test_category_quality_requires_eighty_percent` (20/25 vs 19/24) |
| 8 Default selection | Stateful only if it passes every gate with ratio >= All Tools | `test_stateful_is_default_only_when_it_passes_with_equal_or_better_ratio`, `test_one_mode_completion_failure_blocks_even_if_other_mode_passes` |
| 9 Reviews | Exact `ReviewEvidence`; pending/not-performed/failed block; wrong slot or candidate blocks | `test_review_evidence_is_exact`, `test_completed_review_must_match_its_slot_and_candidate` |
| Limitations | Canonical typed array, candidate-bound, non-safety only | `test_limitations_make_conditionally_ready_only_when_candidate_bound`, `test_limitation_records_are_strict`, `test_limitations_parse_as_one_canonical_typed_array` |
| No side effects / outputs | Decision CLI runs with subprocess and socket APIs patched to fail; no write into tracked source, input publications or through links; no lone `decision.json` | `test_decision_cli_*`, `test_output_location_never_creates_through_a_link_into_tracked_source`, `test_decision_never_writes_into_an_input_publication`, `test_failed_summary_never_leaves_a_lone_decision` |
| Import closure | Fresh interpreter and static (function-local included) closure inside `DECISION_SOURCE_PATHS` | `test_decision_import_closure_stays_inside_the_attested_allowlist`, `test_decision_static_import_closure_includes_function_local_imports` |

## Review and test-strength evidence

- **Mutation check.** Single defects were injected into the engine and CLI
  (threshold operator and constant, empty-coverage check, default selection,
  output-directory refusal, link-escape check, review and limitation candidate
  binding, verifier-tool binding, then the six review-driven bindings). The first
  suite missed three of nine; after strengthening, all fifteen are detected.
- **Read-only review (one reviewer).** Found that the runtime source was not bound
  to the freeze, the D36 tool was not bound, the attested root was not tied to the
  running code, stale shared upstream tooling passed, a decision could be written
  into an input publication, a failed summary could leave a lone `decision.json`, and
  the closure test ignored function-local imports. All are fixed with the
  regressions above. Gate arithmetic, mode handling, coverage, review and limitation
  logic, digest ordering, no-Git decision path and output-path link handling were
  reported sound.

## Verification record

All runs were sequential (one process group at a time) on Windows with official
Node 24.11.1 (zip SHA-256 verified against `SHASUMS256.txt`) first on PATH. The
aggregate peak is a conservative host-wide sum of every `claude`, `python`, `node`,
`git` and `uv` working set sampled each second.

| Run | Result | Notes |
|---|---|---|
| First D40 suite | 40 passed | Before mutation and review hardening |
| Mutation check, first pass | 6 of 9 injected defects detected | Tests strengthened (exact 79%/80% boundary, refusal output, review candidate) |
| Full backend while D40 sources were being edited | 2418 passed, 5 failed, 26 skipped, 1 warning; 2491 s | Peak 2289 MiB. Failures: D36 CLI clean-tooling check on the uncommitted tree (see below); the native Node-origin test because an external temp-folder cleanup deleted 1355 of 2174 files of the portable Node toolchain under `%TEMP%` at 11:59:34 (other sessions' temp scratchpads changed at the same second; no test touches that tree); three D40 CLI tests because the engine was edited mid-run (old module in memory, new CLI on disk) |
| Node toolchain re-extracted outside `%TEMP%` (checksum re-verified) + Node-origin test + all D40 tests after the review fixes | 54 passed | |
| Mutation check, final | 15 of 15 injected defects detected | Adds runtime-source, D36-tool, upstream-currency, running-closure, input-publication and lone-output mutations |
| `python -m scripts.decide_release_readiness` / `python -m evaluation.scripts.attest_release_decision` with refused inputs | exit 2, fixed refusal text, no output | |
| Backend Ruff | All checks passed | |
| Frontend test / build / lint (pnpm 10.18.3) | 157 passed in 17 files / passed / passed | No tracked frontend file changed |
| D36 CLI test on the committed tree | 1 passed on clean implementation commit `2593e6d` | The full-run failure was the uncommitted working tree |
| Real attestation smoke on clean `2593e6d` (output outside the repository) | Published; `load_decision_tool_attestation` rehash matched | Aggregate `0f65fc5f13231686a62e9e83fe33577b101241fcb328d52dcdb8c41287cc5be4` for that commit; a tooling check, not readiness evidence |

The complete backend suite was not repeated after the D40-only fixes: those edits
touch only D40 files (imported solely by `test_d40_readiness_decision.py`) and
documentation that no test reads, and the D40 file was rerun in full. The 26
full-run skips are symlink-permission, POSIX/Linux-only and Windows
no-delete-anchor cases; none is counted as passed.

## Pending conditions

- Independent review of this D40 tooling.
- Real D36 control publication, real D37 aggregate accepted by D38 (produced with
  the final committed tooling), fresh D39 verification on the pinned lane, and
  human-operation and independent-review records. Until then the actual readiness is
  **Not ready**.
- Known D35 failures (README prerequisites/links, tracked credential-shaped test
  literals, build-time rewrite of `frontend/vite.config.js`) would block D39 and
  therefore D40 for the frozen candidate; fixing them needs an authorized successor.
