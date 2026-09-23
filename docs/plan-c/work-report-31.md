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
- Effects are compared by persisted content: settings and revision, jobs keyed by ID, cancellation flags, and canonical receipt/artifact multisets. Allowed status alone cannot pass a positive control.
- Unexpected API failures return only fixed `internal_error` detail plus a generated correlation ID. Logs retain only exception class, route, and correlation ID; request/model bodies, exception text, prompts, paths, and credentials are excluded.

`specification.md` and `docs/DTD.md` already describe the Task 4-reconciled behavior and required no Task 5 correction.

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

Result: **16 test files, 123 tests passed, 0 failed**.

```bash
cd frontend && npx -y pnpm@10.18.3 build
```

Result: exit 0; TypeScript and Vite production build succeeded, 188 modules transformed.

```bash
cd frontend && npx -y pnpm@10.18.3 lint
```

Result: exit 0; ESLint reported no errors or warnings.

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
- Forbidden-effect counters in both modes: settings 0, jobs 0, cancellations 0, receipts 0, artifacts 0.
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

- Deterministic cases show zero unauthorized setting/revision, new-job, cancellation, remote/provider-call, receipt, artifact, or arbitrary-dispatch effects where forbidden.
- Both All Tools and stateful construction are covered deterministically.
- Positive retry controls in both modes prove the ordinary confirmation/core effect path remains functional.
- Unexpected errors and invalid language requests do not disclose raw exception, body, path, secret, or model text.
- Real-model proposal behavior remains unmeasured in this gate because configuration was unavailable; this does not weaken the deterministic safety result.
- Human operation and independent acceptance remain unperformed.

## Known limits

- The phrase guard covers the documented explicit families; it is not a general prompt-injection or semantic-negation classifier.
- The 26-case development corpus is synthetic and not held-out evidence.
- Seven ONNX runtime/asset-dependent tests were skipped by the full suite.
- No real local-model proposal-quality result was produced.
- D32 concurrency work has not started.
