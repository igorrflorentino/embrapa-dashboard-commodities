# `scripts/` — operational tooling

Helper scripts that sit alongside the Python package. Each script is short
and single-purpose; the heavy logic lives in `src/embrapa_dashboard/`. This
README is the index — for behaviour details, open the script and read its
header comment / docstring (which is also the source for every description
below).

Three groups, distinguished by audience:

- **Local dev / setup** — run once per machine when you start contributing.
- **GCP IAM / service accounts** — one-shots run by the project owner.
- **Reporting / data export** — ad-hoc pulls from Gold for sharing (e.g. a
  produtos agrícolas inventory for a supervisor report).

> ℹ️ **Frontend tooling moved to `frontend/`.** The run / build / deploy scripts for the
> Dash dashboard (`dashboard-*.ps1`, `dashboard_smoke.py`,
> `dashboard_visual_check.py`, `check_dashboard_size.py`,
> `dashboard-setup-sa.ps1`) were removed at the 2026-05-29 cutover along with the
> Dash UI. Frontend tooling now lives in `frontend/` (Vite/npm).

The `.ps1` files are **Windows PowerShell** wrappers that exist as a
convenience for this Windows-first repo. They all delegate to the same Python
entry points (or `gcloud`) that the cross-platform paths use, so on
macOS/Linux you can ignore them and go straight to `make <target>` or
`uv run python scripts/<name>.py`.

---

## Local dev / setup

| Script | Platform | What it does | When to run | Invoked by |
|---|---|---|---|---|
| [`setup_dev_env.py`](setup_dev_env.py) | Cross-platform (Python 3) | Cross-platform development environment setup. Auto-detects auth mode (SA impersonation → `GOOGLE_APPLICATION_CREDENTIALS` → `--credentials-file` → interactive paste) and generates `.env`, `~/.dbt/profiles.yml`, and credential files for the detected mode. | Once per machine, immediately after cloning, to bootstrap the dev environment. Also re-run after switching auth modes. | `setup.sh`, `setup.ps1`, `init_dev_env.sh`; documented in [docs/setup.md](../docs/setup.md). |
| [`test_setup.py`](test_setup.py) | Cross-platform (Python 3) | Comprehensive test suite that validates the development environment after `setup_dev_env.py` ran — checks `.env`, dbt profile, ADC credentials, BigQuery connectivity, Python version, and `uv`/`dbt` availability. | After running setup (manually or via `setup_dev_env.py`) to confirm everything works before you start writing code. | `test.sh`, `test.bat`, `init_dev_env.sh`; documented in [docs/testing.md](../docs/testing.md). |
| [`refresh_comtrade_country_seed.py`](refresh_comtrade_country_seed.py) | Cross-platform (Python 3) | Refreshes the COMTRADE country seed. | As needed, when the upstream country list changes. | Standalone. |
| [`refresh_ibge_municipio_mesh.py`](refresh_ibge_municipio_mesh.py) | Cross-platform (Python 3) | Regenerates the IBGE municipal territorial-mesh seed (`dbt/seeds/ibge_municipio_mesh.csv`) from the IBGE Localidades API — every município → both sub-UF divisions (classic meso/micro + 2017 intermediária/imediata). Backs the sub-UF + live-município geography filters (`dim_geo_municipio`). | As needed, when IBGE revises the territorial mesh (rare); rebuild dbt afterward. | Standalone. |
| [`refresh_ibge_municipio_geojson.py`](refresh_ibge_municipio_geojson.py) | Cross-platform (Python 3) | Re-vendors the per-UF municipal **GeoJSON meshes** (`frontend/public/geo/municipios/<UF>.json`, 27 files) from IBGE's malhas API. The sibling `refresh_ibge_municipio_mesh.py` fetches the código→ancestry *table*; this one fetches the *shapes*, without which the choropleth cannot narrow below the UF and just shades the whole state. | Rarely — only when IBGE revises municipal boundaries (they are stable between censuses). | — |
| [`dbt-with-env.sh`](dbt-with-env.sh) | Bash (macOS / Linux / Cloud Shell) | Runs dbt with the project `.env` exported. | When invoking dbt directly and you need the project's `.env` loaded into the environment. | Standalone. |

## GCP IAM / service accounts

| Script | Platform | What it does | When to run | Invoked by |
|---|---|---|---|---|
| [`grant-sa-iam-roles.ps1`](grant-sa-iam-roles.ps1) | Windows PowerShell | Grants `roles/bigquery.user`, `bigquery.dataEditor`, `storage.objectViewer`, and `serviceusage.serviceUsageConsumer` to `sa-secret-reader-prod@…` on the project (the SA used by `setup_dev_env.py`'s impersonation path). | Once per GCP project, by the project owner, to bootstrap the impersonation target SA used during local dev. | Standalone one-shot (see [docs/iam_setup.md](../docs/iam_setup.md)). |
| [`setup-claude-code-web-sa.sh`](setup-claude-code-web-sa.sh) | Bash (macOS / Linux / Cloud Shell) | Creates `sa-claude-code-web-dev` SA + JSON keyfile, granting project read-only BigQuery `dataViewer` + job-runner (`bigquery.user`) roles — deliberately **not** `dataEditor`, so a leaked key cannot write prod data. Output keyfile (`sa-claude-code-web-dev-key.json`) is base64-encoded and pasted into Claude Code Web env vars. | Once per GCP project, only if you want a limited-scope SA for Claude Code Web sandbox (no prod access). | Standalone one-shot. |

## Reporting / data export

Read-only pulls from Gold, run with owner ADC (`GCP_IMPERSONATION_SA=`). The
output CSVs land in the repo root and are git-ignored — regenerate them rather
than committing point-in-time snapshots.

| Script | Platform | What it does | When to run | Invoked by |
|---|---|---|---|---|
| [`export_commodity_inventory.py`](export_commodity_inventory.py) | Cross-platform (Python 3) | Exports the per-banco produto inventory (`Banco \| Código \| Descrição`, one row per product code) from the five live Gold tables to `inventario_produtos_agricolas.csv`. | Ad-hoc, to produce a flat produto list for a report. | Standalone. |
| [`export_commodity_consolidated.py`](export_commodity_consolidated.py) | Cross-platform (Python 3) | Exports the inventory **consolidated by agrupamento concept** via `gold_produto_agrupamento` (`Conceito \| Banco \| Código \| Descrição`) plus a per-concept summary, into two CSVs (`inventario_produtos_agricolas_consolidado.csv` + `inventario_produtos_agricolas_por_conceito_resumo.csv`). Codes the crosswalk does not link (all PAM + PPM, deep COMTRADE wood-derivatives) are kept in a marked `(não vinculado)` bucket. | Ad-hoc, alongside the inventory export, when a concept-grouped view is needed. | Standalone. |

---

## Conventions

- **Read the header.** Every script starts with a comment block (`.ps1`) or
  module docstring (`.py`) that documents required env vars, optional env
  vars, and a usage example. If something here is out of date, that header
  is the source of truth — please update both.
- **Idempotent IAM.** Both SA scripts are safe to re-run; they detect
  existing SAs / bindings and skip them.
- **`claude-hooks/`.** Claude Code safety hooks
  (`block-dangerous-commands.js`, `protect-secrets.js`) — not part of the data
  pipeline; wired in via the repo's Claude Code settings.
