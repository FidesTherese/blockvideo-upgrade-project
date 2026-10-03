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

## Independent review corrections (GPT-6 Astra, 2026-10-03)

An independent review of `daad99e..7dab375` (and of D39 round 2) returned
**Request changes**. The D40 findings and fixes:

| ID | Finding | Status | Regression |
|---|---|---|---|
| B-01 (High) | Output in a not-yet-existing child of the D36 publication was accepted; the publication then failed to load | Fixed: every input file's directory is protected; the output may not equal or lie inside one (child, grandchild or through a link) | `test_decision_never_writes_into_an_input_publication` (self, child, grandchild, junction, D38/D39 evidence child) |
| B-02 (High) | `\\?\C:\...\repo\backend\new` bypassed the tracked-source containment check and wrote files | Fixed: root, output and protected paths are normalized to Win32 form before every comparison; other device namespaces are refused; the normalized path is what gets created | `test_windows_path_spellings_cannot_reach_tracked_source` (extended, device, trailing dot, trailing space, case, extended root), `test_windows_extended_output_outside_the_repository_is_normalized`, extended-path case in the CLI tracked-output test |

The reviewer found no additional false-Ready path through the canonical CLI in
the integer thresholds, two-mode evaluation, coverage, review matching or D39
command/smoke consistency, and judged the freeze refusal not to weaken a gate.
The D39 findings A-01 to A-04 are recorded in `work-report-39.md`.

### Review-correction verification

All runs sequential, official Node 24.11.1 first on PATH.

| Run | Result |
|---|---|
| D39 documentation + review-fix files + frozen-D35 documentation test | 117 passed |
| D40 file | 64 passed |
| Reversion check: each Astra fix undone in place, its regression rerun | 7 of 7 detected |
| D40 mutation suite rerun (15 injected defects) | 14 detected; the surviving one disables the non-empty-directory rule, whose publication scenario is now also blocked by the B-01 guard (the rule itself is still detected by its CLI test) |
| npm semver 7.7.3 cross-check | 2900 cases, 2 differences, both fail-closed rejections of `> =24` |
| D37 runner + all D39 files + D40 file | 674 passed, 14 skipped (symlink-permission and POSIX-only) in 525 s |
| Backend Ruff | All checks passed |
| Frontend test / build / lint | 157 passed / passed / passed; no tracked frontend change |

The complete backend suite was not rerun for these corrections; the changed
modules (`blinded_runtime`, `d39_smoke`, `release_decision`, the decision CLI) are
imported only by the D37 runner, D39 and D40 test files, which were all rerun.

### Follow-up review of the corrections (Astra, 2026-10-03)

The follow-up review of `1a1cd40` judged B-02 resolved and B-01 partially resolved
(PR #2: Request changes), and added R-01 and R-05 for D40. All six follow-up items
(R-01 to R-06; D39 items in `work-report-39.md`) are fixed:

| ID | Remaining gap | Fix | Regression |
|---|---|---|---|
| R-01 (High) | `publish_decision` defaulted to no protected inputs, so a direct API call could still write into a publication | `protected` is a required keyword and must be a non-empty tuple of paths | `test_publication_api_always_protects_its_inputs` |
| R-05 (Medium) | A `\\?\`-spelled `--repo-root` was refused by the running-closure check | The closure and attestation loaders compare normalized paths | `test_extended_repo_root_gives_the_same_decision` (byte-identical Ready decisions) |

Verification:

| Run | Result |
|---|---|
| Reversion check: each R-01 to R-06 fix undone in place (R-05 with both normalization points), its regression rerun | 6 of 6 detected |
| D40 mutation suite (15) | 14 detected; the survivor is the known redundancy with the B-01 guard |
| npm semver 7.7.3 cross-check | 3120 cases, 2 fail-closed differences (`> =24`) |
| Focused D39 documentation/review-fix, D40 and frozen-D35 documentation tests | all passed |
| All D39 files + D40 file | 470 passed, 3 skipped (POSIX-only) in 462 s |
| Backend Ruff / frontend test, build, lint | All checks passed / 157 passed, passed, passed |

The D37 runner was not rerun: `blinded_runtime.py` did not change in this round
(only its test file did, and that file is part of the D39 run).

### Third review round (Astra, 2026-10-03)

The confirmation review of `c03eadb` judged R-01, R-02, R-05 and R-06 resolved and
R-03/R-04 partial because of R-07 and R-08 (both D39 documentation checks, recorded
in `work-report-39.md`). No new D40 finding was raised.

| Run | Result |
|---|---|
| Reversion check: R-07 (container stripping, indentation) and R-08 (range digits, version digits) undone in place | 4 of 4 detected |
| npm semver 7.7.3 on the non-ASCII digit cases | all `validRange=null`, `satisfies=false`, matching the implementation |
| Documentation file + frozen-D35 test + stop-race test | 103 passed |
| All D39 files + D40 file | 489 passed, 1 failed, 3 skipped (POSIX-only) in 479 s. The failure is the native `test_real_owned_chrome_tab_enter_and_version`: a cold Chrome start exceeded its 15 s discovery deadline and teardown was then reported unconfirmed (fail-closed). The file passed 3 of 3 reruns (7 tests each); closing a scope during Chrome startup was confirmed cleanly in 7 of 7 forced cases; the slow-start teardown has not been reproduced and remains an open environment-dependent item |
| Backend Ruff / frontend test, build, lint | All checks passed / 157 passed, passed, passed |

### Fourth review round (Astra, 2026-10-03)

The confirmation of `ec23739` raised R-09 and R-10 (D39 documentation checks,
recorded in `work-report-39.md`) and no D40 finding; the stop-race test change was
judged not to weaken its intent.

| Run | Result |
|---|---|
| Reversion check: R-09 token check, R-10 indented code / fences / code spans / list continuation, teardown diagnostic | 6 of 6 detected |
| Documentation file + frozen-D35 test | 115 passed (before the inline-in-indented-code case was added) |
| Frozen D35 README | still 32 links parsed; full-tree result unchanged (only `locked_versions` fails) |
| D37 runner + all D39 files + D40 file | 727 passed, 14 skipped (symlink-permission and POSIX-only) in 706 s, including the native Chrome tests |
| Backend Ruff / frontend test, build, lint | All checks passed / 157 passed, passed, passed |
