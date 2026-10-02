# Mission 39 — D39 review corrections (2026-10-02)

Readiness: **Not ready**. This is tooling delivery, not approval of D35 or an
operational evidence publication. Independent review remains pending.

## Scope and authorized resource change

Base: `70251db`; branch: `codex/d39-review-fixes`. The frozen D35 commit remains
`522775516c0797abdb313e3432339a3a444b7ae2`. No application, frontend, operation
definition, dependency manifest or lockfile is changed. D37 public APIs are
unchanged. All operational CLI work uses synthetic fixtures only; no real candidate
or evidence CLI is run without the absent D36 control publication.

The user first authorized an 8 GiB development budget and then explicitly requested
**8 GiB for D39 operations too**, because the old 4 GiB envelope was impractical.
The user subsequently raised the shared ceiling to **16 GiB**, explicitly including
Codex and the test controller. The implementation, AGENTS, DTD, specification and
handoff now use 16 GiB aggregate, 14 GiB no-start/owned-stop and 12 GiB target
thresholds. The per-group committed-memory cap stays at 1536 MiB, minimum admission at 768 MiB, unknown-agent reserve at 1 GiB
and group safety reserve at 512 MiB. The formula is
`min(1536 MiB, 14336 MiB - outside_owned_memory - 512 MiB)`.
This authorization supersedes the original request to retain 4 GiB. It does not
turn earlier failed measurements into passes or waive other acceptance gates.

## Findings and regression coverage

Test names below are in `backend/tests/`; `review_*` means `test_d39_review_*.py`.
The complete backend run includes every D39 regression below. Final command
results and explicit platform/prerequisite limitations are recorded separately.

| ID | Implementation status | Regression coverage / qualification |
|---|---|---|
| Step 0 | Fixed | `.gitattributes` committed separately as `22ee940`; `test_step0_archive_ignores_local_eol_config`; raw-byte attestation remains exact. |
| B1 | Fixed; budget explicitly revised | `test_b1_only_controller_agent_and_owned_memory`, `test_user_authorized_16gib_scope_admits_4gib_agent_and_keeps_job_cap`, `test_16gib_scope_still_refuses_14gib_aggregate`; actual-host results are recorded below. |
| B2 | Fixed | `test_b2_real_uv_version_formats`, `test_b2_uv_version_is_strict`: bounded target triples, optional hash/date, underscore support. |
| B3 | Fixed | `test_b3_isolated_vite_resolves_sibling_esbuild` plus existing missing-native-esbuild test; resolve from Vite's package location. |
| B4 | Fixed | `test_b4_origin_probe_does_not_execute_packages`, existing sandbox-origin tests; `find_spec` and distribution metadata without importing CairoSVG. |
| B5 | Fixed | `test_browser_main_binds_version_from_owned_cdp`, `test_browser_stage_never_probes_chrome_without_owned_flags`, native owned Chrome test. |
| B6 | Fixed | `test_pinned_candidate_owned_serve_and_seed_register_all_models`; install demo settings before importing the DB module, then register all models before ORM access. |
| B7 | Fixed | `test_every_browser_journey_uses_measured_width_keyboard_and_client_width`, `test_real_owned_chrome_tab_enter_and_version`. |
| B8 | Fixed in D39 filesystem paths | `test_b8_copy_and_cleanup_use_extended_paths`; extended paths at filesystem boundaries and `core.longpaths=true` in new Git inventory/blob operations. |
| I1 | Fixed | `test_i1_stream_preserves_left_boundary`, `test_i1_scan_includes_tracked_excluded_paths`, `test_pinned_d35_tracked_credential_literals_still_fail_secret_scan`. |
| I2 | Fixed | `test_i2_nonzero_exit_before_stop_cannot_be_forgiven` at 4/6/20 ms; gate uses native Popen exit/kill observation. |
| I3 | Fixed | `test_ffmpeg_observer_captures_actual_nonzero_and_restores_subprocess`, `test_failed_ffprobe_keeps_real_code_without_parsing_duration`, pinned real-media test. Failed duration is null. |
| I4 | Fixed | `test_d39_review_documentation.py`: six individual checks, contradictory Python/Node/React metadata, missing links, AST seams and negation; actual backend/UI contract results. |
| I5 | Fixed | `test_startup_requires_http_listener_instead_of_inprocess_fallback`, pinned both-mode HTTP startup test, owned nonce-health tests; mode-specific server and teardown. |
| I6 | Fixed | `test_i6_shared_receipt_rejects_incomplete_tools`, `test_i6_documentation_is_immutable_and_hashable`, existing role/alias/hash negative matrices. |
| I7 | Fixed | Both measured widths execute history, retry/duplicate Enter, playback and migration; `test_every_browser_journey_uses_measured_width_keyboard_and_client_width`. |
| M1 | Fixed | `test_m1_sandbox_binds_config_and_native_base` tests both files; bind pyvenv.cfg/base before probe and rehash around commands. |
| M2 | Fixed | `test_m2_constructor_cleanup_loss_has_distinct_status`, `test_m2_anchor_open_failure_removes_owned_empty_root`, existing late cleanup failure tests. |
| M3 | Fixed | `test_m3_cleaned_runtime_cannot_hide_dangling_junction`. |
| M4 | Fixed | `test_m4_group_never_changes_attributes_of_hardlinked_leaf`, `test_m4_replacement_after_identity_check_survives`, existing replacement tests. Windows deletes through an identity-checked handle; POSIX uses retained parent fd and immediate identity check. |
| M5 | Fixed | `test_m5_cli_redacts_git_errors` for both materializer and smoke; subprocess errors become fixed redacted refusals. |
| M6 | Fixed; native POSIX verification pending | `test_m6_descendant_new_process_group_cannot_survive` is a Windows platform skip. Session-wide kill/absence checks replace gate-only process-group teardown. |
| M7 | Fixed | `test_m7_backend_pytest_cannot_hide_unbound_media_coverage`, `test_m7_backend_path_selects_real_bound_media`; bound media visible in CommandEvidence. |
| M8 | Fixed | `test_m8_missing_target_has_no_fabricated_exit_or_gate_traceback`; launch_failed always has null target exit. |
| M9 | Fixed | `test_m9_shared_frontend_preflight_refuses_local_pnpm`; both drivers use shared frontend guard and group teardown. |
| M10 | Fixed | `test_m10_pnpm_implementation_is_rehashed`; stub, implementation and metadata are bound. |
| M11 | Fixed | `test_m11_smoke_requires_producer_attestation`, `test_m11_shared_verification_rejects_different_smoke_producer`. |
| L1 (gate release) | Fixed | `test_l1_failed_scope_during_spawn_never_releases_gate`. |
| L2 (cancellation) | Fixed | `test_l2_cancellation_never_confirms_teardown`. |
| L3 (latched reason) | Fixed | `test_l3_latch_preserves_already_exited_child`, late-failure and administrative-stop tests. |
| L4 (Job peak) | Fixed | `test_l4_settlement_checks_job_peak_after_quiet_monitor`; final Job peak sampled at settlement and close. |
| L5 (clean flag) | Fixed | Existing `test_freeze_metadata_changed_after_commands_cannot_pass`; candidate binding precedes setting clean-after. |
| L6 (clock) | Fixed | `test_l6_backwards_clock_does_not_discard_observation`, `test_l6_command_evidence_survives_backwards_clock`; native result and command evidence clamp wall-clock completion. |
| L7 (Japanese cache path) | Fixed | `test_l7_pytest_cache_path_preserves_japanese`. |
| L8 (UTF-8 parser) | Fixed | `test_l8_probe_requires_utf8` for UTF-16/32; public canonical parser used before normalization. |
| L9 (browser ancestors) | Fixed | `test_l9_browser_ancestor_junction_is_rejected`. |
| L10 (screenshot ancestors) | Fixed | `test_l10_screenshot_fingerprint_rejects_ancestor_junction`; screenshot fingerprints use the same checked parent-directory boundary as media/tool fingerprints. |
| L11 (initial marker write) | Fixed | `test_l11_first_marker_write_failure_cleans_owned_root`. |
| L12 (file descriptors) | Fixed | `test_l12_copy_uses_bounded_file_descriptors`: 32 files with an 8-descriptor budget. |
| L13 (public constant typing) | Fixed | Typed MAX constants, METHODS, ACTIONS and DOC_KEYS; Ruff. |
| L14 (health-test flake) | Fixed | Nonce test allows two seconds for async client initialization instead of a 0.3-second startup-sensitive deadline; no health trusted before nonce/live target. |
| Step 5 (efficiency) | Fixed | `test_step5_candidate_boundaries_batch_blobs_and_still_reject_drift`; retained per-command/stage source hashes, group/final runtime/candidate checks, single batched blob verification, media hashes around use, shared cleanup identities, browser/server teardown before contract tests. |

Windows deletion uses [FileDispositionInformationEx](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-_file_disposition_information_ex)
DELETE, POSIX_SEMANTICS and IGNORE_READONLY_ATTRIBUTE flags; it never clears
attributes by an unchecked pathname. The regression preserves a raced replacement
and an external hardlink's attributes.

## Verification record

Every check is sequential, with a 1536 MiB native Job cap and 200 ms aggregate
resident sampling by the development supervisor. Only owned work is stopped.
Native tests with synthetic agent tables are labeled separately; their targets,
Jobs, pipe readers and teardown remain real OS operations.

| Run | Result | Measured aggregate peak |
|---|---|---|
| Independent review baseline from request | 193 passed, 40 failed, 2 skipped, 4 errors | Historical host run; not reclassified |
| Local baseline after separate LF commit, before fixes | 198 passed, 39 failed, 2 skipped | 5992.2 MiB; old 4 GiB operational scope refused |
| Initial review regressions before corrections | 25 failed, 2 passed | Logged synthetic regressions |
| Initial review regressions after corrections | 27 passed, then 32 passed with binding tests | Up to 4165.1 MiB for binding run |
| Native lifecycle regressions after corrections | 8 passed, 1 POSIX platform skip | 4708.7 MiB; synthetic agent inventory |
| Filesystem regressions after corrections | 8 passed | 6259.3 MiB |
| Browser/startup/media observation regressions | 5 failed before, 5 passed after | 6153.7 MiB after |
| Pinned D35 startup/seed/media and nonce checks | 6 passed | 5822.3 MiB |
| Documentation regressions | 8 failed/4 passed before, 12 passed after | 4827.9 MiB after |
| Shared group/media regressions | 2 failed before, 2 passed after | 5135.6 MiB after |
| Batched boundary regression | 1 failed before, 1 passed after | 5230.7 MiB after |
| 8 GiB admission/boundary regression | 1 failed/1 passed before policy update, 2 passed after | 5399.8 MiB after |
| 16 GiB admission/boundary regression | 1 failed/2 passed before policy update; all 3 passed in the next 32-case run | 4191.6 MiB before; 5138.1 MiB next run |
| New native/FS/observation seams before final two fixes | 29 passed, 2 failed, 1 POSIX skip | 5138.1 MiB; FFmpeg PATH case and missing screenshot helper corrected |
| Intermediate synthetic-agent integration | Interrupted by development supervisor at its 7 GiB stop boundary | Not a pass; no complete suite count |
| First complete 16 GiB focused rerun | 313 passed, 5 failed, 3 platform skips | 4900.5 MiB; one Node pin mismatch and four stale fixture assumptions |
| Targeted fixture / clean-after / clock checks | 8 passed, 1 new clock fixture setup failure; corrected clock fixture then passed | 4245.2 / 4363.5 MiB |
| Final D39 subset within the full backend run | 318 passed, 1 failed, 3 skipped (322 total) | Included in the full-run peak below; failure is installed Node 24.13.0 vs required 24.11.1 |
| Full backend before implementation commit | 2326 passed, 2 failed, 26 skipped, 1 dependency deprecation warning; 1732.59 seconds | 7748.6 MiB, within the revised budget |
| Backend Ruff | All checks passed | 3676.3 MiB |
| Initial frontend test | 138 passed; 1 of 17 suites failed collection because locked user-event was absent | 6584.7 MiB |
| Frontend frozen dev dependency install | Passed with pnpm 10.18.3, frozen lock, ignored scripts and CI mode; 350 packages reused, 1 downloaded | 4801.5 MiB; first non-TTY attempt refused before removal (3949.8 MiB) |
| Final frontend test, one worker | 157 passed across 17 files; no skips | 3965.8 MiB |
| Frontend build | Passed (TypeScript and Vite; 190 modules) | 3979.2 MiB |
| Frontend lint | Passed | 3844.8 MiB |
| D36 CLI on clean implementation commit `d8944c4` | 1 passed; the dirty-tree attestation failure is resolved | 3500.2 MiB |

Skipped platform/optional checks are never counted as passed. Intermediate schema
fixture failures and pre-policy memory refusals are diagnostic runs, not final
verification. The full-run skips are 17 unavailable symlink-permission cases,
7 POSIX/Linux-only cases and 2 directory replacement cases prevented by Windows
no-delete anchors. All 81 tests in the five added review files are included:
80 passed and the POSIX session-teardown case was skipped. The dependency warning
concerns Starlette/httpx; no dependency change is made. The full-run failures are
the Node pin prerequisite and the D36 CLI
clean-tooling check. The latter passed on clean implementation commit `d8944c4`;
the installed Node pin mismatch is the only unresolved executed-test failure.
The complete backend suite was not repeated after the documentation-only finalization
and trailing-blank-line cleanup in one test; all implementation bytes are unchanged.
The frontend missing-dependency failure was resolved with the existing frozen lock;
no manifest or lockfile changed. Build regenerated one explanatory comment in the
tracked Vite JavaScript config; that generated-only difference was restored.

The required commands were run sequentially: backend `python -m uv run pytest -q
-rs -p no:cacheprovider` and `python -m uv run ruff check .`; frontend pnpm 10.18.3
`test --maxWorkers=1 --minWorkers=1 --no-file-parallelism`, `build`, and `lint`.
Frontend commands used installed native Node plus its bundled npx CLI. Logs remain
outside Git in the Codex task workspace. No real D36/D39 evidence was published.

## Contract amendments and operational blockers

The dated DTD section records B1 ownership and the later explicit 16 GiB policy,
B5 owned CDP version, B7 keyboard parameters/per-viewport counter semantics, I3
actual media exits/null duration, I6 shared immutable contracts, M7 bound backend
media inventory and M11 producer attestation. Existing valid receipt JSON shape
is preserved where possible; the new CommandEvidence media inventory and required
smoke producer digest require fresh evidence after final tooling attestation.

Operational acceptance still requires Python **3.12.12**, uv **0.12.15**, Node
**24.11.1**, pnpm **10.18.3**, an installed compatible Chrome and a complete D36
control publication. This host has Python 3.13.13, uv 0.11.31 and Node 24.13.0
rather than those pins; `../blockvideo-d36-control` is absent. No package/lock repair or candidate
replacement is performed to manufacture a pass.

D35's README prerequisite mismatch remains failed. Its tracked credential-shaped
test literals remain counted with no test exemption. README links must refer to
inventoried regular files; missing source references also fail the corresponding
documentation subcheck. Operator-created candidate checkouts must use exact LF
bytes (`git -c core.autocrlf=false`, configured before checkout); attestation never
normalizes them. Independent review and fresh final-commit evidence remain pending.
No tag, release, deployment, held-out execution or human acceptance is claimed.

The current frontend tree exactly matches D35 (verified with `git diff
522775516c0797abdb313e3432339a3a444b7ae2 HEAD -- frontend`). The local TypeScript
build emitted one explanatory comment into tracked
`frontend/vite.config.js`. This was restored after the required build/lint checks.
A corresponding mutation during D39 would correctly fail the tracked-source gate;
the pinned operational lane has not been run, so this is a candidate-side build
reproducibility issue to investigate, not a waived check or a claimed operational
failure. Fixing frozen candidate behavior requires a separately authorized successor.
