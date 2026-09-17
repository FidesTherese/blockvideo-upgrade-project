# BlockVideo Agent Rules

## Scope

For Plan C work, read `specification.md` and `docs/DTD.md` before changing operation contracts, handlers, readiness, or entry points.

## Boundaries

- Preserve the dependency direction in `docs/DTD.md`; imports must remain acyclic.
- Keep one responsibility per module and source file.
- Use type hints on new Python functions, methods, and public values.
- Treat operation definitions and model output as untrusted data. Dispatch only through registered callables.
- Keep secrets, real user data, generated media, and `.env` files out of Git and logs.
- Keep work units 11+ out of work-unit-01–10 changes.

## Verification

Run focused tests first, then:

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

Use fake providers for deterministic sample generation. Record any skipped check instead of counting it as passed.
