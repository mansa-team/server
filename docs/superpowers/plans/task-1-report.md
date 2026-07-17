# Task 1 Report: PrometheusSandbox Model & Migration

**Status:** DONE

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `main/models/sandbox.py` | Created | `PrometheusSandbox` ORM model with id, userId, sandboxId, workspacePath, timestamps |
| `main/models/__init__.py` | Modified | Added `PrometheusSandbox` import and `__all__` entry |
| `migrations/env.py` | Modified | Added `import main.models.sandbox` for autogenerate discovery |
| `migrations/versions/d3e4f5a6b7c8_add_prometheus_sandboxes.py` | Created | Manual Alembic migration (MySQL unavailable locally for autogenerate) |
| `tests/test_sandbox_persistence.py` | Created | 3 tests: CRUD, timestamps, one-per-user query |

## Test Results

```
tests/test_sandbox_persistence.py::TestPrometheusSandboxModel::test_create_sandbox_mapping PASSED [ 33%]
tests/test_sandbox_persistence.py::TestPrometheusSandboxModel::test_sandbox_has_timestamps PASSED [ 66%]
tests/test_sandbox_persistence.py::TestPrometheusSandboxModel::test_one_sandbox_per_user PASSED [100%]

============================== 3 passed in 1.63s ==============================
```

## Commits

```
7fe4c6d feat: add PrometheusSandbox model for per-user sandbox persistence
```

## Concerns

1. **Migration written manually** — `alembic revision --autogenerate` requires a live MySQL connection (not available in this env). Migration was hand-written following existing conventions. Should be validated against a real MySQL instance before production deploy.
2. **Unique constraint on userId** — The model uses `unique=True` on the `userId` column, enforced at DB level. The test only verifies application-level "one per user" query logic. A test asserting `IntegrityError` on duplicate userId would strengthen this — skipped to match the spec exactly.
