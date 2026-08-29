---
name: ingest-data
description: >-
  Ingest data from external sources (IBGE SIDRA, BCB SGS), add new products or
  series, debug ingestion failures, or understand the Bronze pipeline. Use when
  asked to ingest data, add a new product, add a new BCB series, troubleshoot
  a pipeline failure, or run the data pipeline.
---

# Data Ingestion — Embrapa Produtos Agrícolas

## Quick Commands

```powershell
# Ingest everything (IBGE + BCB inflation + BCB currency + COMEX)
make ingest-all
uv run embrapa ingest all               # COMTRADE is key-gated → excluded from `all`

# Individual pipelines
uv run embrapa ingest ibge              # IBGE PEVS
uv run embrapa ingest ibge-pam          # IBGE PAM (delta by default; --full to force)
uv run embrapa ingest bcb-inflation     # BCB inflation (IPCA, IGP-M, IGP-DI)
uv run embrapa ingest bcb-currency      # BCB FX rates (USD, EUR)
uv run embrapa ingest comex             # MDIC Comex Stat flows (export + import)
uv run embrapa ingest comtrade          # UN Comtrade global flows (needs COMTRADE_API_KEY)

# Catch upstream revisions of OLD data (operator-triggered full re-ingest)
uv run embrapa ingest reconcile         # full re-download of every scheduled source

# IBGE large historical windows (auto-chunked)
make ingest-ibge-historical             # uses --chunk-years 5
uv run embrapa ingest ibge-batch --chunk-years 5

# Force full refetch (after schema changes or to backfill)
uv run embrapa ingest bcb-inflation --full
uv run embrapa ingest bcb-currency --full
```

## Architecture

```
IBGE SIDRA API ──┐   (IBGE/BCB shown; COMEX (MDIC) + COMTRADE follow the same Bronze path)
BCB SGS API    ──┼──► Python (src/embrapa_dashboard/) → GCS Parquet (raw/)
                 ┘                                               │
                                                                 ▼
                                             BigQuery Bronze (WRITE_APPEND)
```

- **Bronze is append-only.** Every Silver model dedupes on the natural key ordered by `ingestion_timestamp desc`.
- All Bronze columns are `STRING` except `ingestion_timestamp`.
- Datasets auto-create on first run (`gcp/bigquery.py` + `gcp/storage.py`).

## Delta Mode (Default)

IBGE and BCB pipelines are delta by default — they query the max reference
already in Bronze and re-fetch only a small recent window, so a routine
`ingest all` (the WEEKLY Cloud Run batch since 2026-08-28; BCB câmbio has its own
daily trigger) stays small and reliable:

- **BCB:** fetch from `max(reference_date_str) - overlap` — 12 months (inflation)
  / 30 days (currency), absorbing BCB revisions of preliminary readings.
- **IBGE:** fetch from `latest_bronze_year - IBGE_DELTA_OVERLAP_YEARS` (default 1),
  absorbing PEVS revisions of recent years and a newly published year — instead of
  re-pulling 1986→today (a huge SIDRA request that can blow the slow-byte
  deadline). A cold Bronze table falls back to full.

Use `--full` to force the complete window (IBGE: `IBGE_START_YEAR→END`; BCB: from
`BCB_START_YEAR`). For a first IBGE historical backfill, `ingest ibge-batch`
chunks the window to stay under SIDRA's per-request limit.

## Adding a New IBGE Product

Just update `.env`:
```
IBGE_PRODUCT_CODES=3405,3406,3407,...,<new_code>
```

The product code flows straight through from SIDRA's `tipo_de_produto_extrativo_codigo` — no mapping seed is required.

**Note:** IBGE SIDRA has a per-request cell limit. Routine `ingest ibge` is delta (recent years only), so it stays under the limit; for a **first historical backfill** of a large window use `ingest ibge-batch` (chunk size auto-scales with product count — `recommended_chunk_years` in `ibge/client.py`).

## Adding a New BCB Series

1. Update `.env`:
   ```
   BCB_INFLATION_SERIES=433:IPCA,189:IGP-M,...,<CODE>:<LABEL>
   # or for currency:
   BCB_CURRENCY_SERIES=1:USD,21619:EUR,...,<CODE>:<LABEL>
   ```

2. If the new series is an inflation index used for deflation in Gold:
   - Update `BCB_INFLATION_SERIES_IPCA_CODE`, `BCB_INFLATION_SERIES_IGPM_CODE`, or `BCB_INFLATION_SERIES_IGPDI_CODE` in `.env`
   - These are read by `dbt_project.yml` via `env_var()` and used in Gold's `val_real_*` projections.

## Configuration (`config.py`)

All configuration flows through `src/embrapa_dashboard/config.py` (pydantic-settings reading `.env`):

| Key env var | Purpose |
|-------------|---------|
| `GCP_PROJECT_ID` | BigQuery project |
| `GCS_BUCKET` | Data lake bucket |
| `IBGE_PRODUCT_CODES` | Comma-separated SIDRA codes |
| `BCB_INFLATION_SERIES` | `CODE:LABEL,CODE:LABEL` |
| `BCB_CURRENCY_SERIES` | `CODE:LABEL,CODE:LABEL` |
| `BCB_START_YEAR` | Earliest year for full-refetch |
| `BQ_BRONZE_IBGE_DATASET` | Bronze IBGE dataset name |
| `BQ_BRONZE_BCB_DATASET` | Bronze BCB dataset name |
| `BQ_LOCATION` | BigQuery dataset location |

## Discovery Helpers

For finding codes and periods before adding new products/series:

```powershell
uv run embrapa discover ibge-periods   --table-id 289
uv run embrapa discover ibge-products  --keywords castanha,madeira
uv run embrapa discover bcb-series     433
```

## Pipeline Structure

```
src/embrapa_dashboard/
├── cli.py              # Typer entry point (embrapa ingest ...)
├── config.py           # Pydantic Settings (.env reader)
├── core/               # Shared primitives (raw zone, HTTP retry, observability)
│   ├── raw.py          # Two-phase raw zone (land/read/provenance + bronze marker)
│   └── http.py         # Shared HTTP retry policy + drained GET
├── ibge/
│   ├── client.py       # SIDRA API client + auto-chunking
│   ├── pipeline.py     # PEVS: fetch → raw → Parquet → GCS → BigQuery
│   └── pam_pipeline.py # PAM: fetch → raw → Parquet → GCS → BigQuery
├── bcb/
│   ├── series.py       # Generic SGS pipeline (shared by inflation/currency)
│   ├── inflation.py    # BCB SGS inflation spec
│   └── currency.py     # BCB SGS currency spec
├── comex/
│   ├── client.py       # MDIC Comex Stat CSV downloader (stream + filter)
│   └── pipeline.py     # two-phase Bronze, delta by (flow, year)
├── comtrade/
│   ├── client.py       # UN Comtrade keyed JSON API client
│   └── pipeline.py     # chunked/resumable Bronze by (year, reporter-batch)
├── gcp/
│   ├── bigquery.py     # BigQuery load + dataset auto-create
│   └── storage.py      # GCS upload + bucket auto-create
└── backup.py           # Gold table cold backup to GCS
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `HTTP 400` from SIDRA | Too many cells in request | Use `ibge-batch --chunk-years 3` |
| `Dataset not found` on ingest | First run, dataset doesn't exist | The code auto-creates — check `GCP_PROJECT_ID` is correct |
| BCB returns empty data | Series code wrong or BCB rate-limiting | Verify with `embrapa discover bcb-series <code>` |
| `Partition mismatch` on load | Table exists without partitioning | Drop the old table first (see CLAUDE.md migration notes) |

## Cold-Storage Backup

After `make dbt-build-prod`, preserve the Gold tables:
```powershell
uv run embrapa backup-gold    # → gs://${GCS_BUCKET}/backups/run=<ts>/...
```
