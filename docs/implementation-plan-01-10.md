# Plan C Work Units 01–10 Implementation Plan

> **For agentic workers:** Execute sequentially with test-first red-green-refactor.

**Goal:** Deliver G1: typed subtitle-size and status operations use one validated core without retrieval or LLMs.

**Architecture:** A package-local JSON catalog and explicit callable registry feed an operation service. The service validates arguments, resolves project state, checks final readiness, and calls BlockVideo handlers. Existing PATCH and the subtitle handler share a settings mutation service.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, SQLite, pytest; existing React/TypeScript/Vitest regression suite.

## Global Constraints

- No new dependency.
- No circular import.
- All new Python APIs are typed.
- Catalog text is never evaluated as code.
- No paid/external model call.
- Work units 11+ remain deferred.

---

### Task 1: G0 records and synthetic sample

**Files:** Create `AGENTS.md`, `docs/plan-c/*.md`, `docs/plan-c/tasks/work-unit-{01..10}.md`, `samples/plan_c_operation_demo.txt`, and `samples/plan_c_operation_demo.json`.

- [ ] Record baseline commit, verified versions, commands, test counts, known warning/skips, zero-cost boundary, and DEC-01–10.
- [ ] Write a synthetic Japanese script and complete fake-provider project JSON.
- [ ] Validate the JSON with Python's standard library.
- [ ] Run the fake-provider pipeline using a temporary storage root and record the resulting MP4.

### Task 2: Catalog and contracts

**Files:** Create `backend/app/operations/contracts.py`, `catalog.py`, `registry.py`, `definitions.json`, and `backend/tests/test_operation_catalog.py`.

**Produces:** `load_catalog(Path)`, `validate_arguments(...)`, `HandlerRegistry`, and typed request/result models.

- [ ] Write tests for valid load, duplicate IDs, malformed schema, strict integer/range/extra-key rejection, duplicate handlers, and missing handlers.
- [ ] Run tests and verify expected import/failure state.
- [ ] Implement the minimum contracts, schema subset validator, and registry.
- [ ] Run catalog tests to green and Ruff them.

### Task 3: Readiness and operation service

**Files:** Create `backend/app/operations/readiness.py`, `service.py`, and `backend/tests/test_operation_service.py`.

**Consumes:** Catalog, registry, `Project`, `GenerationJob`, and process-local job registry.

**Produces:** `OperationService.readiness` and `OperationService.execute`.

- [ ] Write tests for missing/nonexistent/conflicting targets, live-job block, stale observation, invalid values, and non-ready non-execution.
- [ ] Verify tests fail because the modules are absent.
- [ ] Implement resolution, state tokens, reason codes, validation ordering, and dispatch.
- [ ] Run focused tests to green.

### Task 4: Shared settings and representative handlers

**Files:** Create `backend/app/services/project_settings.py`, `backend/app/operations/handlers.py`, `bootstrap.py`; modify `backend/app/api/routes_projects.py`; extend service tests.

**Produces:** `apply_project_settings`, `set_subtitle_font_size`, `get_project_status`, `operation_service`.

- [ ] Write persistence/reload, read-only status, unchanged write, and shared PATCH/operation invalidation tests.
- [ ] Verify tests fail for missing implementation.
- [ ] Implement mutation without commit in the settings service; commit only in handler/route owners.
- [ ] Replace PATCH's local mutation loop with the shared function.
- [ ] Run focused API/service tests to green.

### Task 5: Thin operation HTTP entry

**Files:** Create `backend/app/api/routes_operations.py`, `backend/tests/test_operations_api.py`; modify `backend/app/main.py`.

**Produces:** `GET /api/operations`, `POST /api/operations/readiness`, `POST /api/operations/execute`.

- [ ] Write list, readiness, execution, 404, 409, and 422 tests.
- [ ] Verify route tests fail with 404 before router registration.
- [ ] Implement thin exception mapping and register the router.
- [ ] Run route tests to green.

### Task 6: Verification and handoff

**Files:** Create/update `docs/modules/operation-core.md`, `docs/plan-c/work-report-01-10.md`, and `docs/plan-c/handoff.md`; reconcile `docs/DTD.md` and `specification.md`.

- [ ] Run backend focused tests, full pytest, Ruff, frontend tests, build, and ESLint.
- [ ] Run the synthetic fake-provider MP4 smoke.
- [ ] Review the dependency graph for cycles and scan catalog/API for arbitrary dispatch paths.
- [ ] Record exact commands, results, skipped checks, limitations, and the work-unit-11 start point.
