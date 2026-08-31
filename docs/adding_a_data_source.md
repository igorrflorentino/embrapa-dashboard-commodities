# Adding a new data source

Step-by-step guide for integrating a new source into the pipeline (Bronze → Silver → Gold) without having to reverse-engineer the existing patterns.

**When to use:** when adding MDIC COMEX, UN COMTRADE, SEFAZ NFe, or any other future source. The project is already prepared — the structural frictions were resolved in the prep PR that introduced the [`core/`](../src/embrapa_dashboard/core/) package, the `cli.INGESTS` registry, the `doctor.SOURCE_CHECKS` registry, and the introspection in `backup.py`.

**Architectural premise (important):** **Gold is per-source — ONE comprehensive table per source**, named `gold_<source>_<form>`. The `<form>` is the semantic grain: `production` (output measurement, no origin→destination; PEVS/PAM → `gold_pevs_production` / `gold_pam_production`) or `flows` (origin→destination flow; trade databases → `gold_comex_flows`, `gold_comtrade_flows`, `gold_nfe_flows`). Ad-hoc aggregations come out of Gold at query time via `GROUP BY`; pre-aggregated marts (for the dashboard's Pushdown Computing) live in the `serving/` layer, deriving from Gold — do not create pre-aggregated siblings in the Gold dataset. And do not try to force COMEX (monthly × country × HS code) or NFe (event × UF) into `gold_pevs_production` — the grains are incompatible. The deflation and FX Silver models (`silver_bcb_inflation`, `silver_bcb_currency`) are shared via `ref()`.

---

## Checklist (11 steps)

### 1. HTTP client

Location: `src/embrapa_dashboard/<source>/client.py`

Minimal pattern:

```python
from embrapa_dashboard.core import SourceTransientError


class <Source>RequestError(Exception):
    """Non-200 response from the <Source> API (base class)."""


class <Source>TransientError(<Source>RequestError, SourceTransientError):
    """Retryable error (5xx, 408, 429, …)."""
```

The mixin with `SourceTransientError` lets the shared decorator in [`core/http.py`](../src/embrapa_dashboard/core/http.py) (`http_retry_policy`) catch all transients without listing each class by name.

**Default retry + slow-byte drain** (5 attempts, exponential 2-30s, timeout `(10, 30)`, `Connection: close`, slow-byte defense via `iter_content` under a wall-clock deadline): use the shared primitives from `core/http.py`:

```python
from embrapa_dashboard.core import http as core_http

@core_http.http_retry_policy(
    transient_exc=<Source>TransientError,
    deadline_s=PER_REQUEST_DEADLINE_S,   # source-specific (180s for IBGE, 120s for BCB)
    before_sleep=_emit_retry,            # optional — for observability (see IBGE)
)
def _http_get(url: str) -> requests.Response:
    response = core_http.get_drained(
        url,
        total_deadline_s=REQUEST_TOTAL_DEADLINE_S,  # source-specific (75s IBGE, 60s BCB)
        transient_exc=<Source>TransientError,
        context=...,                                 # string for the error message
    )
    try:
        # status-code handling source-specific
        ...
    except BaseException:
        response.close()
        raise
```

`http_retry_policy` accepts `transient_exc`, `deadline_s`, `max_attempts=5`, and `before_sleep=None`. `get_drained` returns the `Response` with its body already in `_content` — it preserves `.json()` / `.text`. See [`ibge/client.py:_http_get`](../src/embrapa_dashboard/ibge/client.py) and [`bcb/client.py:_fetch_window`](../src/embrapa_dashboard/bcb/client.py) for the two reference call-sites. Deadline constants live in the client (they are source-specific).

**Logic that should NOT go into `core/`** (in case the API has it): recursive period-halving (like `SidraLimitExceeded` in IBGE), chunking by year (like the BCB's `MAX_YEARS_PER_REQUEST`), per-entity parallelism — hard-won code that deserves to stay in the source's client.

### 2. Pipeline (two-phase: extract→raw→bronze)

Location: `src/embrapa_dashboard/<source>/pipeline.py`

**Two-phase model (mandatory, all sources).** The pipeline has two phases:

1. **Phase 1 — extract→raw:** fetch the *verbatim* extract and archive it in GCS via
   [`core.land_raw(df, ...)`](../src/embrapa_dashboard/core/raw.py) (or
   `land_raw_file(path, ...)` for extracts too large for memory). Pass
   `provenance` (URL, ETag/Last-Modified, query params) — it becomes object
   metadata and the basis of the freshness check.
2. **Phase 2 — raw→bronze:** read the raw back (`read_raw` / `download_raw +
   iter_batches`), filter/shape it, **stamp `ingestion_timestamp`**, and load
   Bronze via [`gcp/bigquery.load_dataframe()`](../src/embrapa_dashboard/gcp/bigquery.py)
   (explicit schema + `clustering_fields`).

```python
def run(settings: Settings, *, full: bool = False, from_raw: bool = False) -> str:
    """Extract→raw (Phase 1) then raw→Bronze (Phase 2). Returns destination, or ''.

    from_raw skips Phase 1 and rebuilds Bronze from the already-archived raw
    (re-filter without re-hitting the source). See PLANS/raw_zone_architecture.md
    and the 3 examples: comex/pipeline.py, ibge/pipeline.py, bcb/series.py.
    """
```

`ensure_dataset` is on you, *before* the extract (the delta lookup queries
Bronze). Short-circuit the empty fetch (by returning `""`). Expose `--from-raw` on
the CLI command. **Freshness** is source-specific in Phase 1: ETag (COMEX, via
`raw_provenance` vs HEAD), `max(reference_date)` (BCB), or re-extraction per run
(IBGE). To re-derive from the complete trail, use
[`core.list_raw()`](../src/embrapa_dashboard/core/raw.py).

**Delta-aware?** Reuse [`latest_reference_date()`](../src/embrapa_dashboard/gcp/bigquery.py) to compute the re-fetch start in Phase 1.

- **If the source is a BCB SGS series** (shape `data`/`valor`, natural key `reference_date_str`, delta lookup per series), you don't write a pipeline: define a [`BcbSeriesSpec`](../src/embrapa_dashboard/bcb/series.py) and delegate to `bcb.series.run`. The inflation/currency variants are exactly this — they differ only in the `label_column`, the schema, and a single `overlap_start_year(last) -> int` function (monthly always rewinds 1 year; daily only in January). See [`bcb/inflation.py`](../src/embrapa_dashboard/bcb/inflation.py) and [`bcb/currency.py`](../src/embrapa_dashboard/bcb/currency.py).
- **If the source has a genuinely different shape** (non-SGS API, event/timestamp granularity like NFe, a different natural key), write your own `run()` instead of forcing a spec onto `bcb.series` — use `latest_reference_date` with a custom `date_format` and the appropriate overlap window (it can be hours). Don't try to generalize `bcb.series` to cover heterogeneous shapes; the readability cost isn't worth it.

**Explicit schema.** The loader [`gcp/bigquery.load_dataframe()`](../src/embrapa_dashboard/gcp/bigquery.py) requires `list[SchemaField]` — do not use autodetect.

**Landing.** Phase 1 writes the raw with `core.land_raw`/`land_raw_file`; Phase 2
loads Bronze with `gcp/bigquery.load_dataframe` (there is no longer a single
land+load primitive — GCS keeps the verbatim raw, BQ keeps the derived
Bronze). `ensure_bucket` is called inside `land_raw`; `ensure_dataset` is on
you before the extract.

### 3. Configuration

Location: [`.env.example`](../.env.example) and [`src/embrapa_dashboard/config.py`](../src/embrapa_dashboard/config.py).

Pattern (mirror `IBGE_*` / `BCB_*`):

```bash
# ─── <Source> ──────────────────────────────────────────────────────────────────
BQ_BRONZE_<SOURCE>_DATASET=bronze_<source>
BQ_BRONZE_<SOURCE>_<TABLE>_TABLE=<table>_raw

<SOURCE>_API_BASE_URL=https://...
<SOURCE>_START_DATE=2010-01
<SOURCE>_END_DATE=2026-12
# ... source-specific series / codes
```

In `Settings`:

```python
bq_bronze_<source>_dataset: str = Field(default="bronze_<source>")
bq_bronze_<source>_<table>_table: str = Field(default="<table>_raw")
<source>_api_base_url: str = Field(default="https://...")
# ...
```

### 4. Give the banco a TABLE ID — the product identity is `(banco, tabela, código)`

**Do this before anything else touches a product code.** Since v1.47.0 the triple holds in
**all five bancos**, including the ones with a single table — so a new source needs a table
id even when it has only one. That is the point, not an oversight: with the triple holding
everywhere, every identity function has ONE shape, and no consumer has to ask *"does this
banco have a table?"* before reading an identity. That branch is what let the rule go
unpropagated three times in one week (v1.46.1, v1.46.3, v1.46.5).

Use the source's **real** table id if it has one (PEVS 289/291, PPM 3939/74, PAM 5457 are
SIDRA ids). If the source has no such concept — COMEX and COMTRADE don't — pick a stable,
readable **project-chosen** name — SHORT, because the banco already sits beside it in
the key and on screen (`ncm`, `hs`; not `comex_ncm`, which repeated its neighbour and
overflowed the Cadastro's Tabela column).

| Where | What to add |
|---|---|
| `config.py` | `<source>_table_id: str = Field(default="…")` |
| `dbt/dbt_project.yml` (`vars:`) | `<source>_table_id: "{{ env_var('<SOURCE>_TABLE_ID', '…') }}"` — parity with `config.py`, guarded by `embrapa doctor` |
| `silver_<source>*.sql` | stamp `'{{ var("<source>_table_id") }}' as tabela` in the final select. **Silver**, not Gold: each Silver model knows which table it reads, so the value is born where it is known and Gold just carries it |
| `gold_<source>_*.sql` | carry `tabela` through every CTE that aggregates, and project it in the final select — a `group by` alone is not enough |
| `serving_<source>_*.sql` | `tabela` in the grain (`group by`) **and** projected |
| `serving/sql.BANCO_TO_SOURCE` | the banco↔source pair (the inverse map derives from it) |
| `tabela_com_padrao` (macro **and** `serving/sql.py`) | only if the banco has ONE table: the append-only curation logs predate the column, so the default is filled at the log→dim boundary. Multi-table bancos get **no** default — guessing a half would invent data |
| `tests/test_trio_identidade_produto.py` | add the Gold model and the marts to `_GOLD_PRODUTO` / `_MARTS` |

**Every one of these is test-guarded**, so a forgotten entry fails loudly rather than
silently — but the failure message points at the test, not at this list, so work through it
in order. Background: `docs/audits/chave_produto_audit_2026-08-30.md`.

### 5. Register in the three registries (CLI + Doctor)

| Registry | File | What to add |
|---|---|---|
| `cli.INGESTS` | [`cli.py`](../src/embrapa_dashboard/cli.py) (right after the `discover_app` declaration) | `IngestSpec("<source>", <source>_pipeline, accepts_full=True/False, label="…", cadence_days=<N>)` — `cadence_days` is how often a scheduler is expected to run it (1 daily, 7 weekly, 31 monthly). `doctor`'s Ingest heartbeat check reads it to decide when silence stops being normal, and `tests/test_ingest_cadence_matches_schedulers.py` holds it to the cron in `deploy/ingestion/schedule*.sh` — so set both together. |
| `doctor.SOURCE_CHECKS` | [`doctor.py`](../src/embrapa_dashboard/doctor.py) (end of file) | `("<source>", _check_<source>)` |
| `doctor.BRONZE_TARGETS` | [`doctor.py`](../src/embrapa_dashboard/doctor.py) | `("bq_bronze_<source>_dataset", "bq_bronze_<source>_<table>_table")` |

And write the hand-maintained `@ingest_app.command("<source>")` in `cli.py` — `ingest all` uses the registry, but each individual command is hand-written (its own messages). For **visibility in `embrapa monitor`**, wrap the work in the `pipeline_run` context manager from [`core/observability_helpers.py`](../src/embrapa_dashboard/core/observability_helpers.py):

```python
from embrapa_dashboard.core import pipeline_run

@ingest_app.command("<source>")
def ingest_<source>(full: bool = typer.Option(False, "--full")) -> None:
    settings = get_settings()
    with pipeline_run("<source>", params={"full": full}) as (_run_id, log_path):
        console.print(f"[dim]event log:[/dim] {log_path}")
        destination = <source>_pipeline.run(settings, full=full)
    if destination:
        console.print(f"[green]✓[/green] <Source> bronze loaded → {destination}")
    else:
        console.print("[dim]<source>: nothing new since last ingest.[/dim]")
```

- **Single-shot** (one sweep, like IBGE/BCB): use `pipeline_run` as above. It emits the sequence `pipeline_start → chunk_start → chunk_end/chunk_error → pipeline_end` and the source shows up in the monitor.
- **Multi-chunk** (progress per state/series/month, like `ingest ibge-batch`): do NOT use `pipeline_run`; copy the hand-maintained structure of `ingest_ibge_batch` in [`cli.py`](../src/embrapa_dashboard/cli.py), which emits `chunk_start`/`chunk_end`/`chunk_error` per chunk and `state_*` per unit.

For sources without a public API (NFe via batch XML), `_check_<source>` can be a stub: `return CheckResult("<source>", True, "no public probe (batch ingestion)")`.

### 6. dbt Bronze source

Location: [`dbt/models/_sources.yml`](../dbt/models/_sources.yml).

Add a `bronze_<source>` block mirroring the existing ones (lines 4-29):

```yaml
- name: bronze_<source>
  description: "Raw <Source> payloads ingested by `embrapa ingest <source>`."
  database: "{{ target.project }}"
  schema: "{{ env_var('BQ_BRONZE_<SOURCE>_DATASET', 'bronze_<source>') }}"
  tables:
    - name: <table>_raw
      identifier: "{{ env_var('BQ_BRONZE_<SOURCE>_<TABLE>_TABLE', '<table>_raw') }}"
      description: "..."
      config:
        loaded_at_field: ingestion_timestamp
```

### 7. dbt Silver

Location: `dbt/models/silver/silver_<source>_<table>.sql`.

Copy [`silver_ibge_pevs.sql`](../dbt/models/silver/silver_ibge_pevs.sql) as the template. Pattern:

1. **Dedup** via `qualify row_number() over (partition by <natural_key> order by ingestion_timestamp desc) = 1`.
2. **Typing** with [`safe_numeric()`](../dbt/macros/safe_numeric.sql) for STRING → NUMERIC columns: the "no-data" placeholders (`...`, `..`, `*`, `X`) → NULL. For IBGE `valor` pass `dash_is_zero=true` so SIDRA's exact-zero `-` maps to `0` (kept distinct from missing); other sources leave the default (`-` → NULL).
3. **Enrichment** with source-specific seeds and CTEs.

Add tests in `dbt/models/silver/_silver.yml` following the same pattern as the existing ones — `unique_combination_of_columns`, `not_null`, `accepted_values` for closed domains.

### 8. dbt Gold (its own lineage, ONE table per source)

Location: `dbt/models/gold/gold_<source>_<form>.sql` — e.g. `gold_comex_flows.sql`, `gold_comtrade_flows.sql`, `gold_nfe_flows.sql`. `<form>` = `production` (output measurement, like PEVS) or `flows` (origin→destination flow, trade databases).

**One comprehensive table per source** — ad-hoc aggregation at query time via `GROUP BY`; pre-aggregated marts (the dashboard's Pushdown) live in the `serving/` layer, not in the Gold dataset. And **do not** join the source into `gold_pevs_production`: incompatible grains and geographies.

For monetary deflation: reuse the shared Silver models via `ref()`:

```sql
inflation_year_end as (
  -- see the deflation CTEs in gold_pevs_production.sql
  select ... from {{ ref('silver_bcb_inflation') }} ...
),

fx_year as (
  -- see the FX CTEs in gold_pevs_production.sql
  select ... from {{ ref('silver_bcb_currency') }} ...
)
```

Apply the project's four monetary conventions (`val_yearfx_*`, `val_real_ipca_*`, `val_real_igpm_*`, `val_real_igpdi_*`) if the source has monetary values.

**Important:** after the `dbt build` in prod, the table shows up automatically in `make backup-gold` (introspection via `list_tables` + the `gold_` prefix). No manual list maintenance.

### 9. Reference seeds (if applicable)

Location: `dbt/seeds/`.

Typical mapping tables:
- **HS codes** (COMEX, COMTRADE): `hs_code_<ano>.csv` with columns `code`, `name`, `parent_code`.
- **ISO countries** (COMTRADE): `country_iso.csv` with `iso2`, `iso3`, `name`, `region`.
- **NCM** (NFe): `ncm_to_hs.csv` to harmonize with COMEX.

YAML pattern in [`dbt/seeds/_seeds.yml`](../dbt/seeds/_seeds.yml) — declare explicit `column_types` and tests (`not_null`, `unique`).

### 10. Python tests

Locations: `tests/test_<source>_client.py` + `tests/test_<source>_pipeline.py`.

Templates:
- Mocked HTTP client: copy [`tests/test_bcb_client.py`](../tests/test_bcb_client.py) (uses `responses`).
- Pipeline with delta + GCP mocks: copy [`tests/test_bcb_inflation_pipeline.py`](../tests/test_bcb_inflation_pipeline.py). **Patch `latest_reference_date`** in your source's namespace, not `_effective_start_year`.

Minimum coverage:
- Correct schema in Bronze (assertion on `load_dataframe` kwargs).
- Delta computes correctly for the cases: (a) empty Bronze → `configured_start`; (b) Bronze with data → overlap applied; (c) `--full` ignores delta.
- HTTP transient (5xx) is returned as `<Source>TransientError`.

### 11. Secret (per-source decision)

- **Public API without auth** (COMEX, today): nothing to do. Mirrors IBGE/BCB.
- **Non-sensitive API key** (COMTRADE, today): use an env var in `.env` (`COMTRADE_API_KEY=...`) + a GitHub Actions secret in CI. Add it to [`.gitignore`](../.gitignore) if it was never committed.
- **Sensitive credential** (SEFAZ NFe A1/A3 cert; long-lived OAuth): **reopen the Secret Manager decision**. The project dropped Secret Manager in [`docs/iam_setup.md:70-73`](iam_setup.md) — for these cases it's worth consciously revisiting. Document the decision and the path here afterward.

### 12. Light documentation

- Add the source to the pipeline diagram in [`README.md`](../README.md) and [`ARCHITECTURE.md`](../ARCHITECTURE.md) (update the Bronze and Consumption boxes).
- Add the source's scope (`comex`, `comtrade`, `nfe`) to the list in [`CONTRIBUTING.md`](../CONTRIBUTING.md) → Common scopes (line 90).
- Add an entry to `CHANGELOG.md` under `[Unreleased] / Added`.

---

## End-to-end verification

Before declaring the source ready for PR:

```powershell
# 1. Test suite (include the new test_<source>_*.py)
uv run pytest

# 2. Lint
uv run ruff check .
uv run ruff format --check .

# 3. CLI smoke — new source shows up in help and in the registries
uv run python -m embrapa_dashboard.cli ingest --help        # should list <source>
uv run python -m embrapa_dashboard.cli doctor                # should include check <source>

# 4. Dev ingestion (needs ADC + valid .env)
uv run python -m embrapa_dashboard.cli ingest <source>

# 5. dbt parse + build in dev
Set-Location dbt
uv run python -m dbt.cli.main deps
uv run python -m dbt.cli.main parse
uv run python -m dbt.cli.main build --select silver_<source>_+ gold_<source>_+
Set-Location ..

# 6. Introspective backup-gold includes it automatically
uv run python -m embrapa_dashboard.cli backup-gold           # new table shows up
```

If every step comes back green and the new `gold_<source>_*` is cited in the `backup-gold` log, the source is integrated.

---

## Anti-patterns to avoid

- ❌ **Forcing the source into `gold_pevs_production`.** Creates an impossible join or lumps incompatible grains together. Create its own `gold_<source>_<form>` lineage.
- ❌ **Creating pre-aggregated tables in the Gold dataset.** Gold is ONE comprehensive table per source (ad-hoc aggregation at query time). Pre-aggregated marts do exist — but in the `serving/` layer (the dashboard's Pushdown), deriving from Gold, not as siblings in the Gold dataset.
- ❌ **Hardcoding lists that should be registries.** If you edit `backup.py` or `doctor.py` instead of just adding a registry entry, you're off-pattern.
- ❌ **Skipping `SourceTransientError`.** Without the mixin, a future shared retry won't work.
- ❌ **Rewriting slow-byte / period-halving copy-pasted from IBGE to another source.** That code is expensive to maintain; only replicate it if your API truly exhibits the same pathology.
- ❌ **Committing credentials in `.env`.** Use `.env.example` as the template; the real `.env` is in `.gitignore`.
- ❌ **Forgetting to add the Bronze TABLE config to `BRONZE_TARGETS`.** `embrapa doctor` won't check it and the operator only finds out when the table doesn't materialize.
