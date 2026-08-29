.PHONY: coverage-diff help setup sync auth ingest-all ingest-ibge ingest-bcb-inflation ingest-bcb-currency \
        ingest-ibge-historical reconcile ingest-job-deploy ingest-job-schedule \
        ingest-job-reconcile-schedule ingest-job-comtrade-schedule ingest-job-currency-schedule ingest-job-pam-schedule \
        ingest-job-ppm-schedule ingest-job-alert iam-grant \
        webapi-run webapi-deploy \
        dbt-deps dbt-build dbt-build-prod dbt-build-prod-with-backup backup-gold \
        nomenclature-audit nomenclature-check \
        dbt-build-curation serving-sync ensure-curation ensure-flow-market \
        dbt-test dbt-source-freshness dbt-clean lint sqlfluff test clean \
        refresh-geo precommit-install precommit-run

PY := uv run

# Base to diff against for patch coverage (`make coverage-diff`). Override on a
# stacked branch: make coverage-diff COMPARE_BRANCH=origin/feat/x
COMPARE_BRANCH ?= origin/main
DBT_DIR := dbt
# Every dbt invocation goes through this wrapper so the repo-root .env is exported
# first — dbt_project.yml reads its datasets + BCB series codes via env_var(), which
# only sees the process environment. A bare `dbt build` would silently use the
# baked-in env_var() defaults and ignore .env (see scripts/dbt-with-env.sh).
DBT := bash scripts/dbt-with-env.sh

# A bare `make` lists the annotated targets rather than running the first one — so
# it never silently mutates the environment (the old default ran `setup`, which
# pins Python + syncs the venv). Run `make setup` explicitly for that.
.DEFAULT_GOAL := help

help:         ## List the annotated targets (this screen)
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-30s\033[0m %s\n", $$1, $$2}'

setup:        ## Pin Python and create the virtualenv
	pyenv local 3.12.11
	uv sync

sync:         ## Re-sync dependencies from pyproject.toml + uv.lock
	uv sync

auth:         ## Refresh Application Default Credentials for local dev
	gcloud auth application-default login

ingest-ibge:    ## Ingest IBGE PEVS (delta by default) → Bronze
	$(PY) embrapa ingest ibge

ingest-bcb-inflation:    ## Ingest BCB inflation series (IPCA/IGP-M/IGP-DI) → Bronze
	$(PY) embrapa ingest bcb-inflation

ingest-bcb-currency:    ## Ingest BCB FX series (USD/EUR) → Bronze
	$(PY) embrapa ingest bcb-currency

ingest-all:    ## Ingest every nightly source (IBGE + BCB + COMEX) → Bronze
	$(PY) embrapa ingest all

ingest-ibge-historical:    ## Ingest IBGE in safe 5-year chunks (for large historical windows)
	$(PY) embrapa ingest ibge-batch --chunk-years 5

reconcile: dbt-deps    ## Deep-refresh: full re-ingest (catches OLD-year revisions) then PROD dbt build
	@echo "[reconcile] Full re-ingest (chunked IBGE + full BCB/COMEX) via LOCAL .env, then a PROD dbt build."
	@echo "[reconcile] WARNING: this uses your LOCAL .env. Verify it matches prod (esp. BCB_CURRENCY_SERIES)"
	@echo "[reconcile]          before running — a drifted local .env will regress Bronze. The deployed Job"
	@echo "[reconcile]          path (make ingest-job-reconcile-schedule) uses the correct prod config and is unaffected."
	$(PY) embrapa ingest reconcile
	$(DBT) build --target prod
	@echo "[reconcile] Done. This may have rewritten HISTORICAL Gold — consider 'make backup-gold'."

ingest-job-deploy:    ## Build + deploy the `embrapa ingest all` Cloud Run Job (reads .env)
	bash deploy/ingestion/deploy.sh

ingest-job-schedule:    ## Create/update the nightly Cloud Scheduler trigger for the job
	bash deploy/ingestion/schedule.sh

ingest-job-reconcile-schedule:    ## Create/update the MONTHLY deep-refresh trigger (Job with --args=reconcile)
	bash deploy/ingestion/schedule_reconcile.sh

ingest-job-comtrade-schedule:    ## Create/update the MONTHLY UN Comtrade backfill trigger (Job with --args=comtrade; needs COMTRADE_API_KEY secret)
	bash deploy/ingestion/schedule_comtrade.sh

ingest-job-currency-schedule:    ## Create/update the DAILY BCB câmbio trigger (Job with --args=bcb-currency)
	bash deploy/ingestion/schedule_currency.sh

ingest-job-pam-schedule:    ## Create/update the MONTHLY IBGE PAM trigger (Job with --args=ibge-pam; needs PAM_* in the deploy allowlist → redeploy)
	bash deploy/ingestion/schedule_pam.sh

ingest-job-ppm-schedule:    ## Create/update the MONTHLY IBGE PPM trigger (Job with --args=ibge-ppm; needs PPM_* in the deploy allowlist → redeploy)
	bash deploy/ingestion/schedule_ppm.sh

ingest-job-alert:    ## Create the Cloud Monitoring alert for ingestion-job failures (needs INGEST_ALERT_EMAIL)
	bash deploy/ingestion/alert.sh

iam-grant:    ## Apply dataset-scoped least-privilege IAM grants (DRY_RUN=1 to preview)
	bash deploy/iam/grant_least_privilege.sh

webapi-run:    ## Run the REST API locally on :8000 (needs .env + ADC; serve the SPA via `cd frontend && npm run dev`)
	uv run --extra webapi python -c "from embrapa_dashboard.webapi.app import app; app.run(host='127.0.0.1', port=8000, threaded=True)"

webapi-deploy:    ## Build + deploy the React SPA + Flask REST Cloud Run Service (reads .env)
	bash deploy/webapi/deploy.sh

dbt-deps:    ## Install dbt package dependencies (dbt_utils etc.)
	$(DBT) deps

dbt-build: dbt-deps    ## Dev: silver+gold in dbt_dev_silver / dbt_dev_gold
	$(DBT) build

dbt-build-prod: dbt-deps    ## Prod: silver+gold in silver / gold (real datasets)
	$(DBT) build --target prod

backup-gold:    ## Snapshot prod Gold tables to gs://${GCS_BUCKET}/backups/run=<ts>/
	$(PY) embrapa backup-gold

nomenclature-audit:    ## Regrava docs/nomenclatura_divergencias.md a partir das tabelas do MDIC
	$(PY) python scripts/audit_nomenclature_seeds.py

nomenclature-check:    ## Falha se o registro de divergencias estiver defasado (precisa de rede)
	$(PY) python scripts/audit_nomenclature_seeds.py --check

refresh-geo:    ## Re-fetch the IBGE territorial mesh: the código->ancestry seed AND the map geometry
	@echo "[1/2] seed: city_code -> meso/micro + intermediaria/imediata"
	$(PY) python scripts/refresh_ibge_municipio_mesh.py
	@echo "[2/2] geometry: one municipal GeoJSON per UF (frontend/public/geo/municipios/)"
	$(PY) python scripts/refresh_ibge_municipio_geojson.py
	@echo "[ok] Run 'make dbt-build' to rebuild the seed's dim; the GeoJSON is served as-is."
	@echo "[!]  Both are versioned — review 'git diff --stat' before committing."


dbt-build-prod-with-backup: dbt-build-prod backup-gold    ## Recommended prod path: build then snapshot
	@echo "[ok] prod build + Gold snapshot complete"

serving-sync:    ## Install the dashboard data-access extra (flask + flask-caching)
	uv sync --extra serving

ensure-curation:    ## Create the append-only attribute-engineering log tables (research_inputs.*)
	$(PY) python -c "from embrapa_dashboard.serving.attribute_engineering import ensure_code_industrialization_log_table as c, ensure_flow_market_log_table as f; from embrapa_dashboard.serving.research_inputs import ensure_attribute_editors_table as a; print('code log ready:', c()); print('flow-market log ready:', f()); print('editors table ready:', a())"

ensure-flow-market:    ## Create + backfill the (customs×flow) market-nature log from the retired seed (cutover)
	$(PY) embrapa flow-market-seed

dbt-build-curation: dbt-deps    ## Dev build INCLUDING the gated SCD2 curation dim (needs the log table)
	$(DBT) build --vars 'enable_curation: true'

dbt-test:    ## Run dbt schema/data tests (needs a profile + warehouse)
	$(DBT) test

dbt-source-freshness: dbt-deps    ## Check Bronze source staleness vs the freshness thresholds (needs a profile + warehouse)
	$(DBT) source freshness

sqlfluff:    ## Lint dbt SQL models with SQLFluff (BigQuery dialect; needs a dbt profile)
	cd $(DBT_DIR) && $(PY) sqlfluff lint models

dbt-clean:    ## Remove dbt build artifacts (target/, dbt_packages/, logs/)
	cd $(DBT_DIR) && $(PY) dbt clean

lint:    ## Ruff lint + format check (no writes)
	$(PY) ruff check .
	$(PY) ruff format --check .

test:    ## Run the unit test suite + the ABSOLUTE coverage floor (credential-free, no live BQ)
# The floor's job is to stop SILENT DECAY, not to police individual PRs — that is what
# `coverage-diff` below does, and it does it better. 98 (not 99) because the floor is
# proportional to repo size: at ~6.8k statements, 99% left ~7 lines of headroom, so a
# single defensive `except` blocked a merge. A gate that blocks routinely gets lowered in
# a hurry, which is how it became decorative in the first place (see v1.24.27). 98 still
# catches an untested feature (~77 statements) while ignoring one-line noise.
# `precision = 2` in pyproject.toml is what makes 98 mean 98 — do not remove it.
# The xml report feeds `coverage-diff`; it is gitignored.
	$(PY) pytest --cov=src/embrapa_dashboard --cov-report=term-missing --cov-report=xml \
		--cov-fail-under=98

coverage-diff:    ## Patch coverage: are the lines THIS branch changed tested? (needs `make test` first)
# The check an absolute floor cannot express. A floor asks "is the whole repo still well
# covered?", which degrades as the repo grows — the same untested feature moves the needle
# less every month. This asks "did you test what you just wrote?", which does not degrade,
# and it never punishes you for PRE-EXISTING gaps (e.g. the 20 uncovered lines in the
# FROZEN serving/attribute_engineering.py, which no PR should have to pay for).
# COMPARE_BRANCH is overridable for a stacked branch: make coverage-diff COMPARE_BRANCH=origin/feat/x
	@test -f coverage.xml || { echo "coverage.xml missing — run 'make test' first." >&2; exit 1; }
	$(PY) diff-cover coverage.xml --compare-branch=$(COMPARE_BRANCH) --fail-under=90

precommit-install:    ## Install git hooks defined in .pre-commit-config.yaml
	$(PY) pre-commit install

precommit-run:        ## Run all hooks against every file (not just staged)
	$(PY) pre-commit run --all-files

clean:    ## Remove local caches + dbt build artifacts
	rm -rf .pytest_cache .ruff_cache $(DBT_DIR)/target $(DBT_DIR)/dbt_packages $(DBT_DIR)/logs
