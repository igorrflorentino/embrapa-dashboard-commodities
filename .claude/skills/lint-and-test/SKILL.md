---
name: lint-and-test
description: >-
  Run lint, format, or test the codebase. Use when asked to lint, format,
  check code style, run tests, fix ruff errors, run pytest, validate code,
  or when you need to verify code changes before committing.
---

# Lint & Test — Embrapa Produtos Agrícolas

## Quick Commands

```powershell
# Lint (check only, no fixes)
make lint                    # ruff check + ruff format --check
uv run ruff check .          # lint only
uv run ruff format --check . # format check only

# Auto-fix
uv run ruff check --fix .    # fix auto-fixable lint issues
uv run ruff format .         # auto-format

# Test
make test                    # all tests
uv run pytest                # same thing
uv run pytest tests/test_ibge_client.py::test_name   # single test
uv run pytest -k "test_pattern"                      # pattern match

# dbt SQL lint
uv run sqlfluff lint dbt/models/ --dialect bigquery
uv run sqlfluff fix dbt/models/ --dialect bigquery
```

## Ruff Configuration (from `pyproject.toml`)

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]
ignore = ["RUF001", "RUF002", "RUF003"]  # Unicode pt-BR intentional
```

The `RUF001/2/3` ignores are intentional: the project uses Unicode characters like `×`, en-dash, and NBSP for pt-BR typography per the design system. Do NOT add these to the code.

## Test Patterns

Tests use the `responses` library to mock HTTP clients. Pattern:

```python
import responses
import pytest

@responses.activate
def test_something():
    responses.add(
        responses.GET,
        "https://api.example.com/endpoint",
        json={"key": "value"},
        status=200,
    )
    # ... call the function under test ...
```

Key test files (a representative subset — the suite is much larger; `make test` runs all of
them, and `ls tests/test_*.py` is the only count that will not rot):

| File | Tests |
|------|-------|
| `tests/test_ibge_client.py` | IBGE SIDRA API client |
| `tests/test_bcb_client.py` | BCB SGS API client |
| `tests/test_bcb_pipeline.py` | BCB pipeline integration |
| `tests/test_gcp_bigquery.py` | BigQuery operations |
| `tests/test_gcp_storage.py` | GCS operations |
| `tests/test_backup.py` | Gold table backup |
| `tests/test_doctor.py` | Doctor/diagnostics |
| `tests/test_monitor.py` | Monitoring module |
| `tests/test_observability.py` | Observability/logging |

The post-migration `webapi`/serving/source suites (e.g. `tests/test_webapi_routes.py`, `tests/test_webapi_seam.py`, `tests/test_webapi_serializers.py`, `tests/test_webapi_format.py`, `tests/test_webapi_registries.py`, `tests/test_webapi_cache_resilience.py`, `tests/test_cov_seam.py`, `tests/test_cov_serializers.py`, `tests/test_serving.py`, `tests/test_comex_*.py`, `tests/test_comtrade_*.py`, `tests/test_pam_pipeline.py`, `tests/test_cli.py`, `tests/test_config.py`, `tests/test_core_*.py`) are not listed above but are part of the same `make test` run. (The webapi files carried no prefix until they were renamed; this list said `test_seam.py` / `test_serializers.py` / `test_format.py` / `test_registries.py` / `test_cache_resilience.py` until 2026-08-28, so following it gave "file not found". `tests/test_doc_file_references.py` now holds every test path named in a doc or skill to the files that exist.)

The frontend has its own Vitest suite: run `npm test` in `frontend/` (test files are `*.test.jsx` / `*.test.js`).

## Pytest Configuration (from `pyproject.toml`)

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
```

## Pre-commit Hooks

The `.pre-commit-config.yaml` sets up:
1. `ruff check --fix` — auto-fix on staged files
2. `ruff format` — auto-format on staged files
3. File hygiene checks

Install: `make precommit-install`
Run manually: `make precommit-run`

## Common Lint Errors and Fixes

| Error | Fix |
|-------|-----|
| `E501` line too long | Break at 100 chars. Use parenthesized continuation. |
| `I001` unsorted imports | `ruff check --fix` auto-sorts. |
| `F401` unused import | Remove the import. |
| `B006` mutable default arg | Use `None` default + `if arg is None: arg = []`. |
| `UP035` deprecated typing | `from __future__ import annotations` + use `list` not `List`. |
| `SIM108` ternary | Use `x = a if cond else b` instead of if/else block. |
