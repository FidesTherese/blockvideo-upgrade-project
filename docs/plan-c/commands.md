# Verified Commands

Verified on 2026-09-17 from repository root.

```bash
python -m uv sync --project backend --extra dev --frozen
cd frontend && npx -y pnpm@10.18.3 install --frozen-lockfile
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
cd backend && python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Baseline results before Plan C changes: backend 326 passed, 2 skipped, 1 third-party deprecation warning; frontend 23 passed; build and ESLint passed. FFmpeg tests were skipped before FFmpeg installation and are rerun at final verification.
