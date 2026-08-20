# Contributing — Embrapa Produtos Agrícolas Dashboard

Thank you for considering contributing to this project! This guide explains how to collaborate efficiently and consistently.

---

## 📋 Prerequisites

Before you begin, make sure you have:

- **Python 3.12.11** (via `pyenv`)
- **uv** (package manager)
- **Git** with hook support
- **gcloud CLI** (for GCP authentication)

Quick setup:
```bash
# macOS / Linux
./setup.sh

# Windows
setup.bat
```

---

## 🌿 Branch Flow

We follow a simplified **GitHub Flow** model:

```
main (protected)
 └── feature/feature-name
 └── fix/bug-description
 └── docs/change-description
 └── refactor/description
 └── chore/description
```

### Rules

1. **`main` is the production branch** — it must always be in a deployable state.
2. **Never push directly to `main`** — always via Pull Request.
3. **Name branches with a semantic prefix**: `feature/`, `fix/`, `docs/`, `refactor/`, `chore/`.
4. **Keep branches short** — smaller PRs are reviewed faster.

---

## 📝 Commit Convention (Conventional Commits)

We use [Conventional Commits](https://www.conventionalcommits.org/) for standardized messages:

```
<type>[optional scope]: <description>

[optional body]

[optional footer]
```

### Allowed types

| Type | When to use |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting (no logic change) |
| `refactor` | Refactoring (no behavior change) |
| `perf` | Performance improvement |
| `test` | Adding/fixing tests |
| `build` | Build changes (pyproject.toml, Dockerfile, etc.) |
| `ci` | CI/CD changes (GitHub Actions) |
| `chore` | Auxiliary tasks (deps, configs) |

### Examples

```bash
feat(ibge): add silviculture data ingestion
fix(bcb): fix date parsing in the SGS API
docs: update README with deploy instructions
refactor(core): extract SourceTransientError into shared module
test(pipeline): add tests for delta ingestion
ci: add SQLFluff step to the workflow
chore(deps): bump dbt-core to 1.9
```

### Common scopes

`ibge`, `ppm`, `bcb`, `comex`, `comtrade`, `core`, `gcp`, `dbt`, `cli`, `doctor`, `backup`, `monitor`, `config`, `ci`, `deps`, `docs`

This list is open-ended — add new scopes when you create a new module or source (e.g. `nfe`).

---

## 🔄 Pull Request Flow

### 1. Create the branch

```bash
git checkout main
git pull origin main
git checkout -b feature/my-feature
```

### 2. Develop

```bash
# Install pre-commit hooks (once)
make precommit-install

# Run lint and tests before committing
make lint
make test

# For dbt changes
make dbt-build    # always dev first!
make dbt-test
```

### 3. Open the PR

- **Title**: follow the Conventional Commits convention (e.g. `feat(ibge): add new PEVS time series`)
- **Description**: explain WHAT changed and WHY
- **Checklist**:
  - [ ] `make lint` passes without errors
  - [ ] `make test` passes without errors (runs the **absolute** coverage floor, 98%)
  - [ ] `make coverage-diff` passes — **patch coverage**: ≥90% of the lines *this branch
        changed* must be covered. This is a separate CI check from `make test` and it is
        the one that usually catches a missing test, because the absolute floor barely
        moves when you add a handful of untested lines. Needs `make test` first (it writes
        `coverage.xml`). See [`docs/testing.md`](docs/testing.md#the-two-coverage-layers-and-why-one-number-was-not-enough).
  - [ ] New tests were added (if applicable)
  - [ ] Documentation was updated (if applicable)
  - [ ] dbt changes were validated with `make dbt-build` (dev)
  - [ ] **Monetary-model changes** (deflation / year-FX in `gold_*` — `val_real_*`, `val_yearfx_*`) ran `make dbt-test`: the deflation+FX **golden unit_test** (`test_pevs_deflation_and_fx_arithmetic`) pins the scientific core and is **dbt-only** (needs a warehouse), so the always-run pytest gate can't catch a regression in that SQL on its own.

### 4. Code Review

- CI (GitHub Actions) must pass — **five** status checks: **`Lint, test, dbt parse`** (Python lint + pytest + the 98% coverage floor + **patch coverage** + dbt parse), **`Frontend tests (Vitest)`** (ESLint + Vitest), **`SQLFluff (dbt templater, BigQuery)`** (dbt SQL style), **`dbt unit tests (BigQuery)`**, and **`gitleaks`** (secret scan).
- The branch must be **up to date with `main`** before merging (branch protection requires this).
- Review approvals are recommended but not required by the current branch protection.
- Use **Squash and Merge** to keep the history clean.

---

## 🛠️ Local Development

### Most-used commands

Full reference in [`CLAUDE.md` → Commands](CLAUDE.md#commands). The most frequent ones:

```bash
make lint               # Ruff check + format
make test               # pytest (no GCP credentials)
make dbt-build          # dev transforms
make ingest-all         # Bronze ingestion of all sources in cli.INGESTS
```

### Code quality

Style rules (Ruff, SQLFluff, pre-commit) are documented in [`CLAUDE.md` → Code Style](CLAUDE.md#code-style).

### Tests

Full reference of test commands in [`CLAUDE.md` → Commands](CLAUDE.md#commands). Summary:

```bash
make test                                            # whole suite (no GCP)
uv run pytest tests/test_ibge_client.py::test_name   # specific test
```

### dbt changes

1. **Always iterate in dev**: `make dbt-build` (writes to `dbt_dev_silver`, `dbt_dev_gold`)
2. **Validate with tests**: `make dbt-test`
3. **Only run prod after validation**: `make dbt-build-prod-with-backup`
4. Use `--full-refresh` after schema changes

---

## 📁 Where to put each thing

| Type of change | Location |
|---|---|
| **Adding a new data source** | Follow the checklist in [`docs/adding_a_data_source.md`](docs/adding_a_data_source.md) |
| New ingestion pipeline | `src/embrapa_dashboard/<source>/` |
| Primitives shared across sources | `src/embrapa_dashboard/core/` |
| New dbt model | `dbt/models/<layer>/` (Gold is per-source: `gold_<source>_*`) |
| New dbt macro | `dbt/macros/` |
| Python tests | `tests/` |
| Auxiliary scripts | `scripts/` |
| Technical documentation | `docs/` |
| Detailed feature plans | `PLANS/` |

---

## ⚠️ Important Rules

1. **Never commit credentials** — `.gitignore` covers `.env`, `sa-*.json`, `sa-*.b64`.
2. **Never commit `dbt/profiles.yml`** — use the `profiles.yml.example` template.
3. **No hardcoding** — everything via `.env` and `config.py`.
4. **Always add tests** for new business logic.
5. **Language rule** ([CLAUDE.md → Code Style](CLAUDE.md#code-style)): anything read only by developers — identifiers, docstrings, comments, log/CLI messages, technical docs — is written in **English**; any string the end user could see (dashboard labels, chart/axis captions, i18n data values) is written in **Portuguese (pt-BR)**. When unsure whether a string is user-visible, default to Portuguese.

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
