# D31 Work Report — Adversarial language and error boundaries

## Result

D31 is complete at the automated verification gate. D32 has not started. The implementation adds a shared host-side negative-intent veto, strict development-only adversarial execution through the ordinary language/core path, and fixed unexpected-error responses/log metadata.

This result separates two claims:

- **Deterministic safety:** verified. The host guard, strict proposal parsing, registered-callable dispatch, target/reference binding, confirmation, current-state validation, and persisted-effect comparison prevent the tested unauthorized effects independently of model quality.
- **Model proposal quality:** not measured in this gate. The bounded real local-model probe was skipped because the loaded configuration had no `LANGUAGE_MODEL` and no stateful retrieval index. No fake output was substituted for real inference.

No human operation or independent acceptance review was performed by this task. This delivery is not a release-readiness decision.

## Changed contracts

- Explicit negative intent is normalized with NFKC/case folding/whitespace and apostrophe normalization, then vetoed for the matching mutating operation family. Global negative phrases veto every mutating operation.
- A veto returns `dismissed`, retains the untrusted interpretation for audit, records `guard_code="negative_intent"`, and creates no prepared request or confirmation token.
- Model output remains proposal-only. It cannot select a callable, target, revision, confirmation, or execution mode.
- The D31 corpus loader performs one bounded binary read (2 MiB plus one detection byte), strict UTF-8 decoding, strict bounded nested fixture validation, and duplicate-ID rejection.
- Effects are compared by persisted content: settings and revision, jobs keyed by ID, cancellation flags, and canonical receipt/artifact/external-call-journal multisets. Every case requires zero external-call-journal changes. Allowed status alone cannot pass a positive control.
- The single-target harness accepts `target_project_id=None` or the exact seeded `initial.project_id`; cross-project targets fail validation before execution.
- A clean-process import blocker rejects worker, media-pipeline, and provider imports while loading the D31 runner and registered operation service. Process-local liveness and sanitized provider errors now sit in neutral modules so the operation path does not reverse that dependency.
- Unexpected API failures return only fixed `internal_error` detail plus a generated correlation ID. Logs retain only exception class, the matched framework route template, and correlation ID; request/model bodies, exception text, prompts, raw request paths, filesystem/private paths, and credentials are excluded.

`specification.md` required no correction. Review round 1 clarified `docs/DTD.md` so the log contract distinguishes excluded raw request/filesystem/private paths from the retained matched route template.

## Verification evidence

Run on Windows 11, Python 3.12.12, pytest 9.1.1, pnpm 10.18.3/Vitest 2.1.9/Vite 5.4.21.

### Focused backend

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py tests/test_language_operations.py tests/test_language_dialogue.py tests/test_semantic_interpretation.py tests/test_comparison_modes.py tests/test_security.py tests/test_api.py -q
```

Result: **208 passed, 0 skipped, 0 failed, 1 warning** in 35.66s. The warning is the existing Starlette `TestClient`/`httpx` deprecation warning.

### Full repository

```bash
cd backend && python -m uv run pytest
```

Result: **1108 passed, 7 skipped, 0 failed, 1 warning** in 113.25s. The seven skips are the ONNX embedding runtime/asset-dependent tests in `tests/test_onnx_embeddings.py`; they are not counted as passes. The warning is the same existing Starlette `TestClient`/`httpx` deprecation warning.

```bash
cd backend && python -m uv run ruff check .
```

Result: exit 0, `All checks passed!`.

```bash
cd frontend && npx -y pnpm@10.18.3 test
```

Result: **16 test files, 123 tests passed, 0 skipped, 0 failed, 0 warnings**.

```bash
cd frontend && npx -y pnpm@10.18.3 build
```

Result: exit 0; TypeScript and Vite production build succeeded, 188 modules transformed, **0 build warnings**.

```bash
cd frontend && npx -y pnpm@10.18.3 lint
```

Result: exit 0; ESLint reported **0 errors and 0 warnings**.

### Deterministic adversarial corpus

The committed corpus contains **26 synthetic cases**: 13 All Tools and 13 stateful, covering 12 adversarial categories plus one positive control in each mode.

```bash
cd backend
python -m uv run python -m scripts.run_adversarial --cases ../evaluation/d31/development.jsonl --mode all_tools --fake-model --output <temporary>/all-tools.json
python -m uv run python -m scripts.run_adversarial --cases ../evaluation/d31/development.jsonl --mode stateful --fake-model --output <temporary>/stateful.json
```

Results:

- All Tools: **13/13 passed**, 0 failed.
- Stateful: **13/13 passed**, 0 failed.
- The runner's six forbidden-effect counters were: settings 0, jobs 0, cancellations 0, receipts 0, artifacts 0, external-call-journal changes 0.
- Positive controls completed with their exact required job/receipt effects; they did not pass on response status alone.
- The temporary reports and isolated databases/media were removed and were never staged.

These are deterministic host/core assertions using synthetic proposals. They do not establish natural-language proposal accuracy for a real model.

### Bounded real local-model probe

Configuration was loaded read-only through `Settings`; `.env` was not edited. The configured URLs were loopback (`http://127.0.0.1:1234/v1`), but `language_model` was unset and `language_retrieval_index` was unset. Therefore the required production All Tools/stateful real-inference construction was unavailable and the probe was **skipped**, not passed. No cloud API was called and no fixed/fake proposal was reported as real inference.

### Sensitive/generated-content inspection

Executed before documentation and repeated on the final staged diff:

```bash
git status --short
git diff --check
git diff --cached --check
git grep -n -I -E "(sk-[A-Za-z0-9]|api[_-]?key[[:space:]]*[:=][[:space:]]*[^N])" -- . ':!backend/uv.lock'
```

Whitespace checks passed. The grep returned only credential field names, provider plumbing, redaction regex/tests, synthetic test values, and historical prose; manual review found no real credential. No private database/media, model weight, `.env`, build output, or generated adversarial evidence is included.

## Original failures and corrections

- The inherited D29 observation was that a phrase equivalent to “do not retry job 7” could be proposed as cancellation. D31 corrects this with the shared operation-family negative-intent veto in both All Tools and stateful paths.
- Task 4 review found that status-only success and length-only effect comparison were too weak, and that corpus/nested fixture loading needed stricter bounds. The reconciled implementation now requires exact persisted effects, compares canonical collection contents, and uses a single bounded corpus read with strict nested records.
- One Task 5 support command initially used `evaluation/d31/development.jsonl` while already inside `backend/` and failed with `unable to read adversarial corpus`; rerunning with `../evaluation/d31/development.jsonl` succeeded with 26 cases. This was a command-path error, not a product defect.
- No focused, full-suite, lint, build, deterministic-corpus, diff, or staging verification failed.

## Acceptance review

- The persisted-state evidence covers the six counters named above plus revision comparison. The external-call counter mechanically detects content changes in the reopened `external_calls` journal, including same-count mutation/replacement; it does not detect arbitrary future network code that bypasses that journal.
- **Guarded requests do not execute:** `LanguageOperationService.prepare()` applies `negative_control_reason()` before constructing an `OperationRequest`; `submit()` returns unless the result is `ready`. The named tests `test_all_tools_vetoes_negative_retry_proposal_without_state_change` and `test_stateful_semantic_candidate_cannot_bypass_negative_retry_veto` assert `dismissed`, no prepared request, no confirmation token, and exact before/after state equality. Therefore those guarded paths cannot reach `OperationService.execute()`.
- **Unknown/unregistered proposals do not dispatch:** proposal parsing accepts only exact catalog-offered operation/version pairs (`test_only_exact_offered_version_allowed`) and rejects model-supplied `handler_key` (`test_extra_or_invalid_shape_rejected`). The route-level fallback case `test_unknown_operation_never_reaches_handler_after_fallback` returns `error` with no settings/job/receipt effect. In the core, catalog lookup precedes `HandlerRegistry.require()` and handler invocation; `test_bootstrap_rejects_definition_without_registered_handler` and `test_registry_rejects_duplicate_and_unknown_keys` cover missing, duplicate, and unknown registration constraints. No model value is evaluated or used as a callable.
- **The direct adversarial runner does not start media work:** `evaluation.adversarial.run_adversarial_case()` calls only `LanguageOperationService.submit()` and, for an explicitly confirmed ready case, `LanguageOperationService.execute()`. A clean subprocess installs an import finder that raises for `app.workers`, `app.services.pipeline`, and `app.providers`, then imports both D31 runner modules and builds the registered operation service. The operation path obtains process-local job liveness from `app.services.job_liveness`; worker code publishes markers in the allowed direction. Retry/start handlers persist only a pending job through `create_pending_job`, while dispatcher/pipeline/provider modules remain outside the import graph. This proves the tested dependency boundary; it is not a claim about arbitrary future dynamic imports or unjournaled network code.
- Both All Tools and stateful construction are covered deterministically. Positive retry controls in both modes prove the ordinary confirmation/core enqueue path remains functional.
- Unexpected errors and invalid language requests do not disclose raw exception/body/model text, secrets, raw request paths, or filesystem/private paths. The matched route template is intentionally retained as bounded log metadata.
- Real-model proposal behavior remains unmeasured in this gate because configuration was unavailable; this does not weaken the deterministic host/core safety result.
- Human operation and independent acceptance remain unperformed.

## Final whole-plan fix wave

The final D31 review wave closed two additional IMPORTANT findings with TDD.
The RED selection collected six tests and produced **4 expected failures / 2 passes**:
cross-project target validation was absent, omitted targets were rejected, the
external-call effect did not exist, and a clean-process import blocker exposed
provider and worker dependencies. After the minimal implementation, the complete
D31 file passed **61/61** with the existing Starlette/httpx warning.

The single-target validator now rejects an explicit target other than the seeded
project while retaining `None` for target-required cases. All 26 committed cases
declare `external_calls: true` as forbidden and require exactly zero journal changes.
Reopened observations compare canonical journal contents, including hashes rather
than response bytes; a synthetic journal-writing service proves one change makes a
case fail. Both positive controls still create exactly one job and one receipt, with
zero settings, revision, cancellation, artifact, or external-call-journal change.

The executable dependency check uses a clean Python subprocess and an import finder
that rejects `app.workers`, `app.services.pipeline`, and `app.providers` while
loading the runner and building the registered service. `services.job_liveness`
removes the operation-to-worker import, and `core.provider_errors` removes the
schema-validation-to-provider import. This establishes the tested journal and import
dependency boundaries only; it does not prove arbitrary future unjournaled network
code cannot be introduced.

Final verification for this wave:

- D31 focused: **61 passed**, 0 failed, 1 existing warning.
- Relevant operation catalog/service/API/durability/storage/dispatcher and
  interpretation-isolation tests, together with D31: **152 passed**; therefore
  **91 relevant non-D31 tests** passed.
- Fake CLI: All Tools **13/13**, stateful **13/13**, with all six forbidden totals
  zero and each positive control limited to one job plus one receipt.
- Full backend: **1115 passed, 7 skipped, 0 failed, 1 existing warning**.
- Ruff: exit 0.
- Frontend: **16 files / 123 tests passed**; build exit 0 with 188 modules; lint
  exit 0.

## Known limits

- The phrase guard covers the documented explicit families; it is not a general prompt-injection or semantic-negation classifier.
- The 26-case development corpus is synthetic and not held-out evidence.
- Nested JSON depth/value-size expansion remains deferred under the existing strict 2 MiB single-read file cap; this fix does not broaden that reviewer MINOR.
- Seven ONNX runtime/asset-dependent tests were skipped by the full suite.
- No real local-model proposal-quality result was produced.
- D32 concurrency work has not started.
