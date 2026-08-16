# Testing Guide

Comprehensive testing for the development environment setup.

> ℹ️ **Scope.** This guide covers the backend (ingest + dbt + CLI). The React SPA (`frontend/`) shipped in the 2026-06 Dash→React migration and brings its own test suite: Vitest, run by the `frontend` job in `.github/workflows/ci.yml` (`cd frontend && npm test`). The old Dash UI tests (Dash smoke test, Playwright visual check) were removed on 2026-05-29 alongside the Dash layer.
>
> ⚠️ **Run the frontend suite on the node version in `/.nvmrc` (22).** It is the single source of truth CI and `deploy/webapi/Dockerfile` also use. On a newer node the suite fails in ways that have nothing to do with your change — node 25, for example, fails all 36 `AppShell` tests with `localStorage.removeItem is not a function`, a jsdom interaction, while CI stays green. With `nvm`/`fnm`, `nvm use` in the repo root picks it up. Without a version manager on macOS: `brew install node@22` (keg-only — it does NOT touch your global node) and prefix the run with `export PATH="/opt/homebrew/opt/node@22/bin:$PATH"`.

## Quick Test

Run all environment validation tests in one command:

### macOS / Linux
```bash
./test.sh
```

### Windows
```cmd
test.bat
```

### Or directly with Python
```bash
python3 scripts/test_setup.py
```

## What Gets Tested

The test suite validates critical components across 9 categories. The exact
count varies by auth mode (~27 in enterprise / impersonation mode, ~31 in
legacy keyfile mode):

### 1️⃣ File Existence (8 checks)
- ✅ `.env` file exists
- ✅ `~/.dbt/profiles.yml` exists
- ✅ Bootstrap scripts present: `setup.sh`, `setup.bat`, `setup.ps1`, `scripts/setup_dev_env.py`
- ✅ `docs/setup.md` present
- ✅ `.gcp-credentials.json` — required in legacy mode, optional in enterprise mode

### 2️⃣ Environment Configuration (7 checks)
- ✅ `.env` file is readable
- ✅ Required config keys present:
  - `GCP_PROJECT_ID`
  - `GCS_BUCKET`
  - `BQ_LOCATION`
  - `BQ_BRONZE_IBGE_DATASET`
  - `BCB_INFLATION_SERIES`
  - `IBGE_PRODUCT_CODES`

### 3️⃣ GCP Credentials (1–5 checks)
- **Legacy:** Credentials file is valid JSON + required fields (`project_id`, `private_key`, `client_email`, `type`)
- **Enterprise:** Application Default Credentials (ADC) reachable via `gcloud auth application-default print-access-token`

### 4️⃣ dbt Configuration (6 checks)
- ✅ `profiles.yml` is readable
- ✅ Required sections present:
  - `embrapa_dashboard:`
  - `dev:` and `prod:` targets
  - `type: bigquery`
  - `method: service-account` (legacy) **or** `method: oauth` (enterprise)

### 5️⃣ Python & Dependencies (1 test)
- ✅ Python >= 3.8 available

### 6️⃣ Build Tools (1 test)
- ✅ `uv` command available and working

### 7️⃣ dbt (1 test)
- ✅ `dbt` accessible via `uv run`

### 8️⃣ Embrapa Pipeline (1 test)
- ✅ `embrapa doctor` passes all checks:
  - `.env` parsed ✓
  - GCP credentials accessible ✓
  - BigQuery reachable ✓
  - GCS bucket accessible ✓
  - IBGE SIDRA API reachable ✓
  - IBGE PAM SIDRA (5457) reachable ✓
  - PAM variable codes ✓
  - IBGE PPM SIDRA (3939+74) reachable ✓
  - BCB SGS API reachable ✓
  - COMEX Stat (MDIC) reachable ✓
  - UN Comtrade API reachable ✓
  - Bronze tables present ✓

### 9️⃣ BigQuery Connection (1 test)
- ✅ `dbt debug` succeeds:
  - Service account authentication ✓
  - BigQuery connection OK ✓
  - Schema and dataset accessible ✓

## Test Output Example

```
============================================================
  1️⃣  File Existence Tests
============================================================

  ➜ File exists: .env... ✅
  ➜ File exists: .gcp-credentials.json... ✅
  ...

============================================================
  📊 Test Summary
============================================================

Total: 27 tests
Passed: 27 ✅
Failed: 0 ❌

🎉 All tests passed! Environment is ready.
```

## Exit Codes

- **0** — All tests passed ✅
- **1** — One or more tests failed ❌

## Troubleshooting

### Test Fails: "File exists: .env"
Run setup again:
```bash
./setup.sh
```

### Test Fails: "Config key present: GCP_PROJECT_ID"
Edit `.env` and ensure all required keys are present. See CLAUDE.md for defaults.

### Test Fails: "GCP Credentials"
The credentials file is invalid JSON. Verify:
1. File is valid JSON (use https://jsonlint.com/)
2. All required fields are present
3. No special characters in file path

### Test Fails: "dbt debug (BigQuery connection)"
This usually means:
1. Service account doesn't have BigQuery permissions
2. Credentials file path is wrong in `profiles.yml`
3. Network connectivity issue

Check permissions in Google Cloud Console:
- IAM & Admin → IAM
- Find service account
- Verify roles: `BigQuery Data Editor` and `Storage Object Creator`

### Test Fails: "embrapa doctor"
Run manually to see detailed output:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/.gcp-credentials.json
uv run embrapa doctor
```

## Python unit tests

The backend unit suite (in `tests/`) runs credential-free against mocked
HTTP/GCP clients and is the gate that `make test` enforces:

```bash
make test                                # all tests (pytest)
uv run pytest tests/test_ibge_client.py  # single test file
uv run pytest -k "config"                # tests matching a keyword
```

GitHub Actions runs the same `make test` step on every PR (see
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).

## Manual Testing

Beyond automated tests, you can verify functionality manually:

### Test dbt
```bash
# Validate dbt configuration
make dbt-test

# Build dev models
make dbt-build

# Or run specific dbt command
uv run dbt run --select silver_ibge_pevs
```

### Test ingestion
```bash
# Simulate ingestion (dry-run)
uv run embrapa ingest ibge --help

# Test IBGE discovery
uv run embrapa discover ibge-periods --table-id 289

# Test BCB discovery
uv run embrapa discover bcb-series 433
```

### Test database connectivity
```bash
# Test BigQuery directly (connection + auth)
cd dbt && uv run dbt debug
```

## CI/CD Integration

These tests can be integrated into CI/CD pipelines:

```bash
#!/bin/bash
# GitHub Actions example
- name: Test environment setup
  run: python3 scripts/test_setup.py
```

## Test Coverage

| Component | Type | Status |
|-----------|------|--------|
| File structure | Static | ✅ Automated |
| Configuration | Static | ✅ Automated |
| Credentials | Static + Dynamic | ✅ Automated |
| Python/uv | Environment | ✅ Automated |
| dbt | Tool | ✅ Automated |
| BigQuery | Network | ✅ Automated |
| GCS | Network | ✅ Automated (via embrapa doctor) |
| Ingestion | Integration | ⚠️ Manual only |
| dbt models | Integration | ⚠️ Manual only |

## Next Steps After Testing

If all tests pass, you're ready to:

1. **Run the pipeline:** `make dbt-build`
2. **Test ingestion:** `uv run embrapa ingest ibge`
3. **Monitor pipeline:** `uv run embrapa monitor`
4. **Start development:** Create your feature branch

## Additional Resources

- **setup.md** — Environment setup documentation
- **CLAUDE.md** — Project architecture and commands
- **scripts/setup_dev_env.py** — Setup script (see for test implementation)
- **scripts/test_setup.py** — Test script source code

## Support

For test failures or questions:
1. Check testing.md troubleshooting section
2. Review setup.md for setup issues
3. Check CLAUDE.md for architecture details
4. Open GitHub issue if problem persists
