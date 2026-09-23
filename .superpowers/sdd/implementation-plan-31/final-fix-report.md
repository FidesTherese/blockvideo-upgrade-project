# D31 Final Whole-Plan Fix Report

## Status

PASS for the requested automated final fix wave. Implementation commit:
`6d65dc7` (`fix: enforce D31 target and provider boundaries`). This report is added
by the final `[DONE] Mission 31 ...` delivery commit. D32 has not started.

## Contract changes

- `AdversarialCase.target_project_id` is optional, but an explicit value must equal
  `initial.project_id`. The D31 harness remains intentionally single-target.
- Every D31 case must set `forbidden.external_calls=true` and require exactly zero
  `required_effects.external_calls`.
- Reopened observations compare complete external-call journal records by canonical
  content; response bytes are represented by SHA-256. Same-count mutation or
  replacement is an observed change.
- Results and canonical CLI summaries expose the external-call change count. Any
  journal change fails a case.
- Operation readiness now reads process-local liveness through
  `app.services.job_liveness`; workers publish and clear markers in the allowed
  direction. The sanitized `ProviderError` contract moved to
  `app.core.provider_errors` so schema/settings validation does not import provider
  modules.
- A clean subprocess blocks imports of `app.workers`, `app.services.pipeline`, and
  `app.providers` while importing both D31 runner modules and building all registered
  operation handlers.

These controls establish zero changes to the reopened `external_calls` journal and
an import dependency boundary for the tested D31 runner/operation graph. They do not
prove that arbitrary future unjournaled network code cannot be introduced.

## TDD evidence

### RED

Command:

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py -k "target_other or omitted_target or same_count_collection or no_worker_pipeline" -q
```

Result: **4 failed, 2 passed**. Expected failures showed:

1. no cross-project target validator;
2. `None` was rejected as a target;
3. `ObservedEffects` had no external-call counter;
4. the clean import blocker caught `app.providers` and, after that dependency,
   the existing operation-to-worker path.

Additional contract pressure made the new external-call fields fail as forbidden
unknown properties before implementation. The failures were caused by the missing
contracts, not test syntax or fixture errors.

### GREEN

- Final D31 focused file: **61 passed**, 0 failed, 1 existing Starlette/httpx
  deprecation warning.
- A synthetic journal-writing service creates one journal row and is mechanically
  rejected with one forbidden effect and a required-effect mismatch.
- The clean-process dependency test imports the runner and builds the registered
  service while all worker, pipeline, and provider module imports are blocked.
- The strict target tests accept `None`, accept the existing seeded target through
  the corpus, and reject a different explicit target.

## Positive controls and corpus

The committed corpus remains **26 synthetic cases**: 13 All Tools and 13 stateful.
All cases now contain the mandatory zero external-call expectation.

- All Tools fake CLI: **13/13 passed**, 0 failed.
- Stateful fake CLI: **13/13 passed**, 0 failed.
- Both positive controls completed while creating exactly **one job and one receipt**
  each.
- Each positive control created zero setting, revision, cancellation, artifact, and
  external-call-journal changes.
- All six forbidden totals were zero in both reports. Generated reports were removed
  before staging.

## Verification

```bash
cd backend && python -m uv run pytest tests/test_d31_adversarial_safety.py -q
```

**61 passed**, 0 failed, 1 existing warning.

```bash
cd backend && python -m uv run pytest \
  tests/test_d31_adversarial_safety.py tests/test_operation_catalog.py \
  tests/test_operation_service.py tests/test_operations_api.py \
  tests/test_operation_durability.py tests/test_operation_storage.py \
  tests/test_operation_dispatcher.py tests/test_interpretation_isolation.py -q
```

**152 passed**, 0 failed, 1 existing warning; this is 61 D31 plus **91 relevant
operation/isolation tests**.

```bash
cd backend && python -m uv run pytest
```

**1115 passed, 7 skipped, 0 failed, 1 existing warning**. The seven skipped tests
remain the ONNX runtime/asset-dependent cases and are not counted as passes.

```bash
cd backend && python -m uv run ruff check .
```

Exit 0, `All checks passed!`.

```bash
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

- Test: **16 files / 123 tests passed**.
- Build: exit 0, **188 modules transformed**.
- Lint: exit 0.

Both fake CLI commands exited 0 with the counts above. `git diff --check` and staged
diff checks passed. The credential-pattern scan returned only known field names,
provider plumbing, redaction tests, synthetic values, and historical prose; manual
review found no credential, private data, generated media, database, `.env`, or
model asset in the change.

## Documentation reconciliation

Updated:

- `specification.md`
- `docs/DTD.md`
- `docs/modules/operation-core.md`
- `docs/plan-c/work-report-31.md`
- `docs/plan-c/handoff.md`
- `evaluation/d31/development.jsonl`

The documents state the single-target validator, mandatory zero journal changes,
neutral liveness/error modules, executable import boundary, and the exact claim
limit. No D32 behavior is described as implemented.

## Self-review

- Confirmed the validator runs after both target and initial state validation.
- Confirmed `forbidden.external_calls` cannot be disabled and a nonzero required
  external-call effect is rejected.
- Confirmed observations reopen the database and compare journal contents rather
  than counts only.
- Confirmed response bodies are not copied into result JSON or logs.
- Confirmed the runner and registered service load with worker, pipeline, and provider
  modules blocked.
- Confirmed worker liveness behavior remains covered by dispatcher and operation
  regressions.
- Confirmed both positive controls retain only their expected receipt/job effects.
- Confirmed generated fake-CLI evidence was removed before staging.

## Concerns and deferrals

- This is not a general network sandbox and does not prove absence of arbitrary
  future unjournaled network code.
- Real local-model proposal quality remains unmeasured because the prior read-only
  configuration had no model/index; no cloud or fake substitute is reported as real.
- The reviewer MINOR on nested JSON limits remains deferred under the strict 2 MiB
  single-read corpus cap; this wave did not expand that scope.
- Seven ONNX runtime/asset tests remain skipped, and the existing Starlette/httpx
  deprecation warning remains.
- Human operation and independent acceptance were not performed.
