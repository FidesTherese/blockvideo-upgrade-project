# D31 Adversarial Input Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent explicit negative control requests, hostile input, malformed model output, and unexpected exceptions from producing unauthorized effects or disclosing sensitive content.

**Architecture:** Add a deterministic proposal veto between strict model parsing and `OperationRequest` construction, retain the operation core as the only execution authority, and verify both interpretation modes through a development-only adversarial runner. Replace the global raw-exception response/log path with fixed reason codes and correlation IDs.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, pytest/pytest-asyncio, existing local structured-model adapter, existing React/Vitest regression suite.

## Global Constraints

- Follow `docs/plan-c/work-unit-31.md` and the D31 section of `docs/DTD.md`.
- No new runtime or development dependency.
- Production `app` code must not import `evaluation`.
- Model output remains proposal-only; registered operations, target binding, revision, confirmation, dialogue currency, and final readiness remain mandatory.
- Public requests and environment variables must not enable test failpoints.
- Never log or return raw utterances, prompts, model bodies, source scripts, secrets, credentials, provider headers, or absolute private paths.
- Use fake adapters and synthetic content for deterministic tests; held-out material remains unread.
- Commit the completed unit as `[DONE] Mission 31 <DETAIL>` only after required verification passes.

---

### Task 1: Deterministic negative-control guard

**Files:**
- Create: `backend/app/language_operations/intent_guard.py`
- Create: `backend/tests/test_d31_adversarial_safety.py`

**Interfaces:**
- Consumes: plain request `text: str` and parsed `operation_id: str`.
- Produces: `normalized_intent(text: str) -> str` and `negative_control_reason(text: str, operation_id: str) -> str | None`.

- [ ] **Step 1: Add table-driven failing normalization tests**

```python
@pytest.mark.parametrize(("raw", "expected"), [
    ("  ジョブ７を\u3000再試行しないで  ", "ジョブ7を 再試行しないで"),
    ("DON’T   RETRY job 7", "don't retry job 7"),
])
def test_normalized_intent(raw: str, expected: str) -> None:
    assert normalized_intent(raw) == expected
```

- [ ] **Step 2: Run the normalization test and confirm the missing-module failure**

Run:

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py::test_normalized_intent -q
```

Expected: collection fails because `app.language_operations.intent_guard` does not exist.

- [ ] **Step 3: Implement exact normalization**

Use `unicodedata.normalize("NFKC", text).casefold()`, translate U+2018/U+2019/U+FF07 apostrophes to ASCII `'`, replace every run matched by `r"\s+"` with one space, and strip the result. Do not otherwise remove punctuation, IDs, or letters.

- [ ] **Step 4: Add failing operation-family veto tests**

```python
@pytest.mark.parametrize(("text", "operation_id", "expected"), [
    ("ジョブ7は再試行しないで", "project.generation.retry", "explicit_negative_intent"),
    ("ジョブ7は再試行しないで", "project.generation.cancel", None),
    ("キャンセルしないで", "project.generation.cancel", "explicit_negative_intent"),
    ("動画を生成しないで", "project.generation.start", "explicit_negative_intent"),
    ("何もしないで", "project.settings.update", "explicit_negative_intent"),
    ("字幕を56pxにして", "project.settings.update", None),
])
def test_negative_control_reason(text: str, operation_id: str, expected: str | None) -> None:
    assert negative_control_reason(text, operation_id) == expected
```

Also include English `do not`/`don't` forms and positive words such as `再試行して` that must not be vetoed.

- [ ] **Step 5: Run veto tests and verify they fail**

Run:

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py -q
```

Expected: veto assertions fail because the function is not implemented.

- [ ] **Step 6: Implement the minimal immutable phrase tables**

Define `MUTATING_OPERATIONS`, operation-family sets, global negative phrases, and family-specific phrases exactly as specified in `docs/DTD.md`. Return only `explicit_negative_intent` or `None`; never return a replacement operation.

- [ ] **Step 7: Run focused guard tests**

Run:

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py -q
```

Expected: normalization and pure-guard tests pass.

- [ ] **Step 8: Commit the isolated guard**

```bash
git add backend/app/language_operations/intent_guard.py backend/tests/test_d31_adversarial_safety.py
git commit -m "test: define D31 negative intent guard"
```

### Task 2: Integrate the veto into both language modes

**Files:**
- Modify: `backend/app/language_operations/contracts.py`
- Modify: `backend/app/language_operations/service.py`
- Modify: `backend/tests/test_d31_adversarial_safety.py`
- Modify: `backend/tests/test_language_operations.py`
- Modify: `backend/tests/test_semantic_interpretation.py`

**Interfaces:**
- Consumes: schema-valid `OperationProposal` from All Tools or semantic interpretation.
- Produces: `LanguageResponse(status="dismissed", diagnostics.guard_code="negative_intent")` with no prepared request, confirmation, or effect.

- [ ] **Step 1: Write a failing All Tools integration test**

Use the existing fake structured adapter to return a `project.generation.retry` proposal for `ジョブ7は再試行しないで`. Seed job 7 and snapshot settings/jobs/receipts. Assert:

```python
assert response.status == "dismissed"
assert response.prepared_request is None
assert response.confirmation_token is None
assert response.diagnostics.guard_code == "negative_intent"
assert observe_state(db) == before
```

- [ ] **Step 2: Write a failing stateful-semantic integration test**

Wrap the same proposal through the existing semantic test fixture and assert the same response and unchanged state. The test must prove candidate selection does not bypass the shared guard.

- [ ] **Step 3: Run the two integration tests and verify current unsafe behavior**

Run the exact new node IDs from `test_d31_adversarial_safety.py` with `-q`. Expected: at least one response is `ready` or prepares cancellation/retry instead of returning `dismissed`.

- [ ] **Step 4: Extend the diagnostics contract**

Add `"negative_intent"` to the `LanguageDiagnostics.guard_code` literal in `contracts.py`.

- [ ] **Step 5: Integrate the guard before `OperationRequest` construction**

In `LanguageOperationService.prepare()`, after all existing reference/value/reading guards and after confirming the proposal is an `OperationProposal`, call:

```python
negative_reason = negative_control_reason(request.text, outcome.proposal.operation_id)
```

When non-`None`, preserve `response.interpretation`, set status `dismissed`, set `guard_code="negative_intent"`, and do not construct `prepared`, confirmation, or readiness calls. Do not modify parser or operation core behavior.

- [ ] **Step 6: Run D31 and existing language tests**

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py tests/test_language_operations.py tests/test_language_dialogue.py tests/test_semantic_interpretation.py -q
```

Expected: all pass; existing positive mutations and confirmation behavior remain unchanged.

- [ ] **Step 7: Commit the orchestration integration**

```bash
git add backend/app/language_operations/contracts.py backend/app/language_operations/service.py backend/tests/test_d31_adversarial_safety.py backend/tests/test_language_operations.py backend/tests/test_semantic_interpretation.py
git commit -m "fix: veto explicit negative control proposals"
```

### Task 3: Bound unexpected errors and logs

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/routes_language.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_security.py`
- Modify: `backend/tests/test_d31_adversarial_safety.py`

**Interfaces:**
- Produces fixed HTTP 500 detail with `reason_code`, fixed Japanese message, and generated correlation ID.
- Logs only correlation ID, route, and exception class at the catch-all boundary.

- [ ] **Step 1: Add a failing catch-all response-redaction test**

Create a test-only route that raises `RuntimeError("SECRET /Users/private/source.txt")`. Assert status 500, exact `reason_code == "internal_error"`, a non-empty bounded correlation ID, and absence of `SECRET`, `private`, and the raw exception text from response bytes.

- [ ] **Step 2: Add a failing log-redaction test**

Capture Loguru output for the same request and assert it contains `RuntimeError` and the correlation ID but not the exception message, request body, or private path.

- [ ] **Step 3: Run the redaction tests and verify current leakage**

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py -k "exception or log" -q
```

Expected: current catch-all includes truncated `str(exc)` and the tests fail.

- [ ] **Step 4: Implement the fixed catch-all boundary**

Generate `uuid.uuid4().hex[:16]`. Log structured fields `correlation_id`, `path`, and `error_class=exc.__class__.__name__` without `str(exc)`. Return the fixed payload from `docs/DTD.md`.

- [ ] **Step 5: Verify language validation never echoes malformed input**

Add cases containing invalid Unicode/control characters, unknown fields, oversized text, malformed request IDs, and attempted path/secret strings. Assert HTTP 422 with only `invalid_request` and the fixed message.

- [ ] **Step 6: Run API and security regressions**

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py tests/test_api.py tests/test_security.py tests/test_operations_api.py -q
```

Expected: all pass and no captured output contains synthetic secrets.

- [ ] **Step 7: Commit redaction changes**

```bash
git add backend/app/main.py backend/app/api/routes_language.py backend/tests/test_api.py backend/tests/test_security.py backend/tests/test_d31_adversarial_safety.py
git commit -m "fix: redact unexpected API failures"
```

### Task 4: Development-only adversarial corpus and runner

**Files:**
- Create: `backend/evaluation/adversarial.py`
- Create: `backend/scripts/run_adversarial.py`
- Create: `evaluation/d31/development.jsonl`
- Modify: `backend/tests/test_d31_adversarial_safety.py`

**Interfaces:**
- `load_adversarial_cases(path: Path) -> list[AdversarialCase]`
- `run_adversarial_case(case, service_factory, directory: Path) -> AdversarialResult`
- CLI accepts `--cases`, `--mode all_tools|stateful`, `--output`, `--fake-model`, and explicit local model/index options already used by existing probe scripts. `--fake-model` selects only the committed deterministic synthetic reply map.

- [ ] **Step 1: Add failing strict-contract tests**

Define test data for prompt injection, negative retry/cancel/generate, guessed references, unknown operation/version, extra model fields, invalid arguments, oversized input, Unicode whitespace/confusables, and disclosure attempts. Assert unknown JSON properties and non-synthetic split values are rejected.

- [ ] **Step 2: Run contract tests and confirm missing symbols**

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py -k adversarial_contract -q
```

Expected: import or name failure.

- [ ] **Step 3: Implement strict Pydantic records and bounded loader**

Use `extra="forbid"`, maximum 2,000 text characters, mode literal, expected status set, and explicit booleans for forbidden settings/job/cancellation/receipt/artifact effects. Reject files larger than 2 MiB and duplicate case IDs.

- [ ] **Step 4: Add failing runner effect tests with fake adapters**

For each mode, initialize a fresh temporary DB/media root, execute through ordinary `LanguageOperationService`, reopen the DB, and compare settings, revision, jobs, cancellation flags, receipts, and artifacts. Assert each forbidden effect remains zero and supported positive controls still complete.

- [ ] **Step 5: Implement the runner using existing fixtures**

Reuse existing comparison fixture state observation and configured semantic construction without importing evaluation from `app`. Write canonical JSON atomically to the explicit output path. Do not write utterance/model bodies to logs.

- [ ] **Step 6: Add the synthetic development corpus**

Commit only synthetic D31 cases. Include the known retry negation in both modes and paired positive controls. Do not copy held-out cases or private review material.

- [ ] **Step 7: Run deterministic D31 corpus tests**

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py -q
python -m uv run python -m scripts.run_adversarial --cases ../evaluation/d31/development.jsonl --mode all_tools --fake-model --output ../release-evidence/d31-all-tools.json
python -m uv run python -m scripts.run_adversarial --cases ../evaluation/d31/development.jsonl --mode stateful --fake-model --output ../release-evidence/d31-stateful.json
```

Expected: every case is accounted for, forbidden-effect totals are zero, and outputs contain no free request text.

- [ ] **Step 8: Commit the development harness**

```bash
git add backend/evaluation/adversarial.py backend/scripts/run_adversarial.py backend/tests/test_d31_adversarial_safety.py evaluation/d31/development.jsonl
git commit -m "test: add D31 adversarial safety harness"
```

### Task 5: D31 verification and design reconciliation

**Files:**
- Modify: `specification.md` only if implementation behavior differs from its current summary.
- Modify: `docs/DTD.md` only if verified evidence requires a contract correction.
- Modify: `docs/modules/operation-core.md`
- Create: `docs/plan-c/work-report-31.md`
- Modify: `docs/plan-c/handoff.md`

**Interfaces:**
- Work report distinguishes deterministic safety, bounded real-model behavior, core effects, and unperformed human/independent acceptance.

- [ ] **Step 1: Run focused backend suites**

```bash
cd backend
python -m uv run pytest tests/test_d31_adversarial_safety.py tests/test_language_operations.py tests/test_language_dialogue.py tests/test_semantic_interpretation.py tests/test_comparison_modes.py tests/test_security.py tests/test_api.py -q
```

Expected: all pass.

- [ ] **Step 2: Run full repository verification**

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

Expected: all commands exit 0. Record exact counts and warnings; do not count skipped commands as passed.

- [ ] **Step 3: Run bounded real local-model adversarial probe when configured**

Use the same configured local model and production All Tools/stateful construction. Do not modify `.env`, use cloud APIs, or execute provider/media work. Record model proposal outcomes separately from the deterministic zero-effect assertions. If the local model is unavailable, record the exact blocker rather than substituting fixed output.

- [ ] **Step 4: Inspect tracked changes for sensitive/generated content**

```bash
git status --short
git diff --check
git diff --cached --check
git grep -n -I -E "(sk-[A-Za-z0-9]|api[_-]?key[[:space:]]*[:=][[:space:]]*[^N])" -- . ':!backend/uv.lock'
```

Expected: no credential, private database/media, model weight, or generated evidence is staged.

- [ ] **Step 5: Write and reconcile D31 documentation**

`work-report-31.md` must record changed contracts, executed commands/counts, original failures, deterministic and real-model evidence, known limits, and confirmation that D32 has not started. Update the operation-core note with the shared negative-intent veto and fixed error boundary.

- [ ] **Step 6: Review the final diff against the work-unit acceptance criteria**

Confirm zero unauthorized setting/job/cancellation/remote-call/arbitrary-dispatch effects in deterministic cases, safe positive controls, both-mode coverage, and no raw error disclosure. If any criterion is unproven, mark D31 incomplete.

- [ ] **Step 7: Create the D31 delivery commit**

```bash
git add .
git commit -m "[DONE] Mission 31 Harden adversarial language and error boundaries"
```

- [ ] **Step 8: Push the task branch according to `AGENTS.md`**

```bash
git push
```

Expected: the current branch's configured upstream accepts the D31 delivery commit. Do not tag, publish, deploy, or begin D32 before the D31 review gate.
