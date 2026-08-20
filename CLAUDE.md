# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and other AI assistants when working with code in this repository.

## Project Overview

**Embrapa Produtos Agrícolas Dashboard** — Medallion pipeline (Bronze → Silver → Gold) for historical analysis of Brazilian extractive vegetable production (IBGE PEVS), enriched with FX rates (USD, EUR) and inflation indices (IPCA, IGP-M, IGP-DI) from Brazil's Central Bank.

Built for **Embrapa researchers** — the purpose is historical/scientific exploration of time series, **not** business metrics or real-time analytics (data is ingested and transformed in batch).

- **Language**: Python 3.12 · **Package manager**: uv · **Build**: hatchling
- **Data transforms**: dbt-core + dbt-bigquery
- **Infrastructure**: GCS + BigQuery + GitHub Actions
- **Consumption (two parallel paths)**: Looker Studio (no-code, direct on Gold) · a custom **React SPA + Flask REST API + Plotly.js** dashboard deployed to Cloud Run (behind IAP). Both read the same Gold/serving tables; neither is exclusive.
- **License**: Apache 2.0

> ✅ **Custom dashboard = React SPA + Flask REST + Plotly.js (live on Cloud Run, behind IAP).** Built in the 2026-06 Dash→React migration, which **replaced the Dash UI entirely** (the Dash package was removed after the cutover — don't look for `dashboard/`). It is **one of two first-class consumption paths**; the other is Looker Studio, direct on Gold. Architecture (**Pushdown Computing** — no Gold held in memory):
> - **Data-access / serving layer**: `dbt/models/serving/` (pre-aggregated marts at the chart grains), `dbt/models/core/` (conformed dims + the SCD2 curation view), and `src/embrapa_dashboard/serving/` (the UI-agnostic BFF: parameterized BigQuery queries, `flask-caching`, the append-only curation writer with IAP author capture).
> - **REST API + SPA host**: `src/embrapa_dashboard/webapi/` (Flask app factory; serves the built SPA **and** `/api` from one origin/IAP; `seam` composes the gateway readers, `serializers` shapes them to the UI's `contracts.js`; `format`/`registries` are the pt-BR formatting + banco/metric/view registries — these moved here from the deleted Dash package). gunicorn entrypoint `embrapa_dashboard.webapi.app:app`; extra `webapi` (flask + flask-caching + gunicorn, **no dash/plotly**).
> - **Frontend**: `frontend/` — the Design System's React/Vite UI (`frontend/src/ui/`, adopted verbatim from the handoff and now the live production UI — **not** a prototype), with the synthetic data layer + SVG charts replaced by API-backed `src/data/` + Plotly.js `src/charts/` (analytical charts get zoom/hover/pan). `npm run dev` (Vite :5173, proxies `/api`→Flask :8000) · `npm run build`→`dist`.
> - **Deploy**: `deploy/webapi/` (3-stage node-build→python image, private + IAP, runtime SA `sa-web-dashboard-prod`). **A code change needs NO manual deploy** — merging to `main` triggers `.github/workflows/webapi-deploy.yml`, which does a surgical `gcloud run services update --image` (env, secrets and the IAP annotations all persist). `make webapi-deploy` (`deploy.sh`) is only for an **env change**: it uses `--env-vars-file`, which REPLACES the whole env block, so it must run from a machine that has `deploy/webapi/.env.prod`. Spec/history: **`PLANS/react_migration_contract_map.md`**.
> - **Curadoria** (the catalog — *what enters/exits the dashboard*) is **LIVE**: a researcher-editable commodity catalog in `research_inputs` (the editable successor to the retired `commodity_crosswalk` seed → `core/dim_produto_catalog` → `gold_produto_agrupamento`), edited via the **"Cadastro de produtos agrícolas"** admin view and consulted (read-only calibration seeds) via **"Referências"**; with an **orphan→Descontinuado** lifecycle (auto-detected on the dbt-build boundary, NON-destructive) and a **human-gated purge** (`embrapa purge-orphan` — backup-first, prints the DELETEs for a human; never auto-deletes). Backend: `serving/{curation,catalog_lifecycle,research_inputs}.py` + `webapi/seam_curation.py`; per-catalog allowlist `research_inputs.catalog_editors`. Spec: **`PLANS/curadoria_catalogo.md`**.
> - **Engenharia de Atributos** (derived columns from researcher input — per-code industrialization + customs×flow market-nature) is built but **FROZEN** (deferred to *Versão Futura*, hidden from the UI; PRs #168/#169) — do NOT treat it as activatable. `serving/attribute_engineering.py` + `webapi/seam_attribute_engineering.py` + the gated SCD2 view (`enable_curation`, default false) stay as tested scaffold; stale deep links route to a neutral notice. Revive: un-freeze the UI entry points + `dbt build --vars 'enable_curation: true'`. The shared append-log + IAP-author + idempotency infra both features reuse is `serving/research_inputs.py`. **Data-blocked** (honest in-product placeholders): `cross_chain`/`cross_lag` + the *regime×flow market-nature* axis need sources this repo lacks (SEFAZ inter-UF flows; monthly PEVS — PEVS is annual; the customs-procedure dimension, summed away in Silver). (Note: the *ingestion* Cloud Run **Job** under `deploy/ingestion/` is a separate batch, no-UI artifact — don't confuse it with the dashboard Service.)

## Documentation Map

| File | Purpose |
|------|---------|
| `README.md` | Human entry point, quickstart, CLI reference |
| `ARCHITECTURE.md` | Technical deep-dive: folder structure, data flow, stack decisions |
| `CONTRIBUTING.md` | Commit conventions, branch flow, PR process |
| `CHANGELOG.md` | Version history (Keep a Changelog format) |
| Roadmap (Google Drive) | Project vision & evolution tracking for business leadership — kept **outside the repo** (replaces the former `ROADMAP.md` + `TODO.md`): [Roadmap — Google Drive](https://docs.google.com/document/d/1UByZ_THIJcqtYizZWrOSDsMpM_XCptj0f29VcymcPXE/edit?usp=sharing). `PLANS/` (engineering specs) and `CHANGELOG.md` (per-version record) stay in-repo. |
| `SECURITY.md` | Vulnerability reporting policy |
| `PLANS/` | Detailed feature plans (one .md per feature) |
| `docs/` | Deep-dive docs (setup, IAM, testing, cost safety, etc.) |
| `docs/operations_runbook.md` | Occasional prod ops: managing curators (BQ allowlist), backing up prod Gold locally, the destructive-command safety hooks |
| `docs/comtrade_world_backfill.md` | Runbook for the UN Comtrade all-reporters (world) full-history backfill — the last gap to max granularity; measured volume/time/cost, local + Cloud Run Job paths, cost guard |

## Code Style

- **Formatter/Linter**: Ruff (line-length=100, target=py312)
- **Rules**: E, F, I, B, UP, SIM, RUF (ignoring RUF001-003 for the pt-BR Unicode that remains in UI/i18n data values)
- **Language** (project rule — the **end user is the deciding reader**):
    - Read **exclusively by the development team** → **English**: identifiers, docstrings, comments, log/error and operator/CLI messages, dbt comments + YAML descriptions, and all technical docs (README, ARCHITECTURE, docs/, PLANS/, …).
    - Read by **anyone *including* the end user**, or **any string the end user could read — no matter where it lives** → **Portuguese**: dashboard display strings, chart/axis labels, and i18n data values (e.g. `month_name_pt` → `'Janeiro'`, Brazilian region/state names).
    - When unsure whether the end user could ever see a string, **default to Portuguese**. (External-API literals the code must match — e.g. SIDRA's Portuguese error text — stay verbatim as data.)
- **SQL**: SQLFluff for dbt models
- **Pre-commit**: gitleaks + ruff + file-hygiene hooks (install with `make precommit-install`)

## Commands

Setup (once per machine):
```bash
pyenv local 3.12.11 && uv sync
gcloud auth application-default login
cp .env.example .env                          # then edit GCP_PROJECT_ID etc.
cp dbt/profiles.yml.example ~/.dbt/profiles.yml
make precommit-install                        # optional: ruff + file-hygiene on every commit
```

Ingestion (Python → GCS Parquet → BigQuery Bronze):
```bash
make ingest-all                               # IBGE + both BCB series + COMEX (IBGE + BCB = delta; COMTRADE is key-gated, excluded)
make ingest-ibge-historical                   # auto-chunked for large year windows
uv run embrapa ingest {ibge|bcb-inflation|bcb-currency|all}
uv run embrapa ingest bcb-inflation --full    # force refetch from BCB_START_YEAR
uv run embrapa ingest ibge-batch --chunk-years 5
```

**IBGE and BCB pipelines are delta by default.** Each queries the max reference
already in Bronze and re-fetches only a small recent window. BCB rewinds a
**year-granular** overlap (it rewinds to the start of a calendar year, not a
precise month/day window — so inflation re-fetches up to ~24 months and FX up to
a full year of daily PTAX; strictly an over-fetch, never under-covering). **IBGE**
re-fetches from
`latest_bronze_year - IBGE_DELTA_OVERLAP_YEARS` forward — absorbing PEVS revisions
of recent years and a newly published year — instead of the whole 1986→today
window, a huge SIDRA request that can blow the slow-byte deadline on an
unattended Cloud Run job. A cold Bronze table falls back to the full window.
Use `--full` to force the complete window (or `ingest ibge-batch` to chunk a
first historical backfill). **COMEX is the exception** — its per-file ETag check
re-detects a revision to *any* year every run, so the delta limitation below is
IBGE/BCB-only.

**Catching upstream revisions of OLD data — `reconcile`.** Because IBGE/BCB are
delta, a correction the source publishes to an *old* year (e.g. IBGE revising a
1999 value) is **never re-queried** by the nightly run. `embrapa ingest reconcile`
(`make reconcile`) is the escape hatch: a full re-download of every nightly
source (IBGE year-chunked for deadline-safety, BCB + COMEX `--full`), ignoring
the delta/ETag short-circuit. It stays **operator-triggered** because the
re-ingest itself is expensive and rarely warranted — but the question of WHETHER
it is warranted is now answerable: **`embrapa reconcile-check`** compares what the
sources serve today against Bronze for data older than the delta window (IBGE PEVS
cell-by-cell at the n6 grain we store; every BCB point older than the rewind), and
exits 1 if anything diverged. It is read-only. The earlier claim that no cheap
pre-check was feasible held for the whole history but not for a well-chosen sample
(~20k points in ~2 min), and for BCB not at all — one SGS request returns the whole
series, so that half is exhaustive. COMEX stays out of scope: its per-file ETag
check already catches old-year revisions nightly. The **monthly reminder issue**
(`.github/workflows/reconcile-reminder.yml`) now leads with `reconcile-check`
instead of asking for a guess. (Re-enable a monthly Cloud Run trigger any time with
`make ingest-job-reconcile-schedule` — the same Job with args overridden to
`reconcile`.) `reconcile` refreshes only **Bronze**; the **daily scheduled
`dbt build`** (`.github/workflows/dbt-build-prod.yml`) propagates it to
Silver/Gold. No `--full-refresh` is needed: `silver_ibge_pevs` is incremental but
**year-agnostic** (it re-scans whatever Bronze years got a newer
`ingestion_timestamp`), so a revised old year flows all the way to Gold on a
plain build.

Cold-storage backup of the prod Gold tables. **The recommended prod path
bundles build + snapshot in one target — reach for this instead of bare
`dbt-build-prod` whenever the run is preservation-worthy:**

```bash
make dbt-build-prod-with-backup   # build prod, then snapshot Gold to GCS
make backup-gold                  # snapshot only (after an existing prod build)
uv run embrapa backup-gold        # same as above, direct CLI form
```

Each snapshot lands at `gs://${GCS_BUCKET}/backups/run=<ts>/...`. Plain
`make dbt-build-prod` is intentionally left un-chained so throwaway prod
experiments don't accumulate snapshots. **Operator responsibility:** run
`dbt-build-prod-with-backup` at least once per release boundary (after
schema changes, new product codes, or anything you'd want to roll back
to). `embrapa doctor` warns if the latest snapshot is more than
`BACKUP_STALENESS_DAYS` (default 14) old, and fails clearly if no
snapshot exists.

dbt transforms (run from repo root via Makefile, or `cd dbt` to call dbt directly):
```bash
make dbt-build           # dev target — writes to dbt_dev_silver, dbt_dev_gold
make dbt-build-prod      # prod target — writes to silver, gold (full-refresh)
make dbt-test
cd dbt && uv run dbt run --select silver_ibge_pevs+    # single model + downstream
cd dbt && uv run dbt test --select gold_pevs_production
cd dbt && uv run dbt build --full-refresh              # force rebuild incremental models
```

**`silver_ibge_pevs` is incremental** (insert_overwrite by `reference_year`).
Each `dbt build` scans only Bronze partitions for years with new ingestions —
the dedup `qualify` no longer pulls the whole Bronze history. Use
`--full-refresh` after schema changes, after dropping the table, or when
re-anchoring to a different `ingestion_timestamp` baseline. `silver_bcb_*`
remain `materialized=table` (small tables; the IPCA chain index requires a
full-series window).

Discovery helpers (auxiliary — for filling in `.env`, not part of the pipeline):
```bash
uv run embrapa discover ibge-periods   --table-id 289
uv run embrapa discover ibge-products  --keywords castanha,madeira
uv run embrapa discover bcb-series     433
```

Lint / test:
```bash
make lint                                # ruff check + ruff format --check
make test                                # pytest
uv run pytest tests/test_ibge_client.py::test_name   # single test
```

## Architecture

Medallion pipeline: data sources (today IBGE PEVS + BCB SGS; see `cli.INGESTS` registry — extensible) → Python (Bronze) → dbt (Silver → Gold) → consumed in parallel by **Looker Studio** (direct) and the **custom React SPA + Flask REST (`webapi`) dashboard on Cloud Run**.

For the full technical deep-dive (folder structure, data flow diagrams, stack decisions, Bronze/Silver/Gold details, configuration model, dev/prod separation), see [`ARCHITECTURE.md`](ARCHITECTURE.md).

Key facts for AI context:
- **⚠ The GCP project id `embrapa-dashboard-commodities` is a FROZEN, IMMUTABLE legacy label — treat it as an opaque string with NO domain meaning.** It predates the "produtos agrícolas" rename; GCP project ids cannot be renamed (only the display name, which is already "Embrapa Produtos Agrícolas Dashboard"). Do **not** read "commodity trading" semantics into it, do **not** propose migrating/recreating the project to change it, and **never** find/replace it in bulk (a bulk rename once corrupted it into an invalid form with a space and an accent, breaking every IAM/bq command; see the v1.10.8 incident). The GitHub repo (`embrapa-dashboard-produtos-agricolas`) and the domain are "produtos agrícolas"; only this one infra identifier keeps the old token, on purpose. In the terminology model **commodity** is a narrow, specific word (an *undifferentiated* produto) — it is not a synonym for the subject.
- **Bronze is append-only**; Silver dedupes on natural key by `ingestion_timestamp desc`.
- All Bronze columns are `STRING` except `ingestion_timestamp`.
- The seed `historical_currency_factors` absorbs currency reforms; without it, pre-1994 values are 10⁶–10⁹× too large.
- `val_real_{ipca,igpm,igpdi}_*` columns are for cross-year comparison; `val_yearfx_*` are nominal.
- Config flows through `src/embrapa_dashboard/config.py` (pydantic-settings + `.env`). `BCB_INFLATION_SERIES` uses `CODE:LABEL,CODE:LABEL` format — keep `BCB_INFLATION_SERIES_IPCA_CODE` / `BCB_INFLATION_SERIES_IGPM_CODE` / `BCB_INFLATION_SERIES_IGPDI_CODE` in sync (dbt reads each via `env_var()` to wire the right series into the Gold pivot).
- `target=dev` → `dbt_dev_silver` / `dbt_dev_gold` (auto-expire 7 days). `target=prod` → `silver` / `gold`.
- **F7 Ciclo de Vida visibility gate**: `core/dim_produto_visibility` (a view of `(source, code)` — the EXACT commodity code, no prefixes — for produtos agrícolas a researcher marked *indisponível*) + the `hidden_code_predicate` macro + `serving/sql.visibility_clause` (the Python builder) exclude those produtos agrícolas from **every** researcher-facing Gold read (the 6 serving marts, `serving_quality_by_source`, the cross-source picker, and the gateway direct readers — município cube, quality timeseries, quality-by-product); kept SEPARATE from `dim_produto_catalog` so the admin editor + crosswalk still see hidden rows. NO-OP until something is hidden. Spec: `PLANS/quality_outliers_and_visibility_gate.md`.
- **Q1 `data_quality_flag` is an 11-value taxonomy** — 9 emitted (OUTLIER = high-magnitude-but-price-consistent vs PROBLEMATIC = implied price `value/quantity` >`quality_price_k`× or <1/k× the product median ⇒ likely typo) **plus 2 RESERVED auto-fill tiers** (`INFERRED_QUANTITY`/`INFERRED_VALUE`, accepted-but-absent, always 0 today — no Gold CASE emits them; reserved for a future auto-fill pipeline, v1.10.2), gated by `enable_quality_outliers` (TRUE in prod; false ⇒ legacy 4-value flag, compiled byte-identical), with vars `quality_price_k`(=100)/`quality_outlier_k`(=4.0)/`quality_min_obs`(=100)/`quality_value_floor`(=100000, a magnitude floor skipping tiny-municipality rounding noise). IBGE is scored on **deflated** `val_real_ipca_brl` (nominal would fake a pre-1995 hyperinflation tail); trade on nominal USD value / `net_weight_kg`. Activating in prod requires a Gold rebuild.
- **Adding a new data source**: follow [`docs/adding_a_data_source.md`](docs/adding_a_data_source.md). The registries that need new entries: `cli.INGESTS`, `doctor.SOURCE_CHECKS`, `doctor.BRONZE_TARGETS`. Shared primitives live in `src/embrapa_dashboard/core/`. **Gold is per-source, ONE comprehensive table per source** named `gold_<source>_<form>` (`<form>` = `production` for output measurement like PEVS, or `flows` for origin→destination trade like COMEX/COMTRADE/NFe). Ad-hoc aggregations (Looker, exploration) come from `GROUP BY` at query time on Gold; **for the dashboard's Pushdown Computing, the `serving/` layer materializes pre-aggregated marts** at the exact chart grains (fed by the conformed dims `dim_date`/`dim_geo_br`/`dim_geo_municipio` in `core/`) — they derive from Gold, not replace it (see `ARCHITECTURE.md` § Camada Serving). `gold_pevs_production` is the PEVS table. **The sub-UF geography cascade** (classic mesorregião/microrregião + 2017 região intermediária/imediata + live município, for the IBGE bancos `ibge_pevs`/`ibge_pam`/`ibge_ppm`) is the exception to the mart pattern — too fine to pre-aggregate: it reads `gold_<source>_production` directly via `POST /api/municipio-yearly` (city-scoped + `maximum_bytes_billed`-guarded), with the static IBGE municipal mesh universe served once from `dim_geo_municipio` via `GET /api/geo-mesh`.

## Skills available

Each skill in `.claude/skills/` provides deep context for a specific workflow. Claude Code loads them on demand by matching the task description.

| Skill | When to use |
|-------|------------|
| `dbt-workflow` | Create/modify dbt models, run transforms, understand Silver/Gold patterns |
| `lint-and-test` | Run ruff, pytest, sqlfluff, or pre-commit hooks |
| `ingest-data` | Ingest from IBGE/BCB, add products or series, debug pipelines |
| `bigquery-debug` | Debug BQ errors (404/403/400), inspect data, diagnostic queries |
| `code-audit` | Strategic health audit: complexity, maintainability, coverage (run periodically, not on every change) |

> The frontend-specific skills (`run-dashboard`, `dash-page-scaffold`, `new-chart-component`, `deploy-cloud-run`) were removed alongside the old Dash UI. New UI-related skills will be (re)introduced as part of the Claude Design System handoff.

## Migration history

One-time migration notes (Bronze re-partitioning, Gold schema changes, column renames) are archived in `docs/migration_history.md`.
