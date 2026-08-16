# Ingestion — Cloud Run Job + Cloud Scheduler

Packages `embrapa ingest all` as a **Cloud Run Job** (batch) triggered by
**Cloud Scheduler** in the early morning. This automates the Bronze refresh that
feeds Silver → Gold → the `serving` marts.

> **Job, not Service.** This is the *batch ingestion* image — it runs the CLI to
> completion and exits, with no HTTP port. It is **not** the dashboard, which is
> a long-running Cloud Run *Service* (the React SPA + Flask REST app, live on
> Cloud Run — `deploy/webapi/`). Don't confuse this `Dockerfile` with the
> dashboard one.

| | **Job** (this dir) | **Service** (dashboard, `deploy/webapi/`) |
|---|---|---|
| Nature | batch, ephemeral | request-driven — scales to zero (min-instances=0) |
| HTTP port | none | yes (Gunicorn) |
| Trigger | Cloud Scheduler (cron) | user request (behind IAP) |
| Runtime SA | `sa-data-pipeline-prod` (write GCS+BQ) | `sa-web-dashboard-prod` (read serving) |

## Why this is safe to run unattended

`ingest all` is built for a blind cron:

- **`tenacity` retries** (`core.http.http_retry_policy`: `stop_after_attempt(5)` +
  exponential backoff + a wall-clock slow-byte drain) reabsorb transient upstream
  failures (HTTP 5xx, timeouts, stalled reads).
- **Delta by default** — IBGE re-fetches only recent years (from
  `latest_bronze_year - IBGE_DELTA_OVERLAP_YEARS`), BCB pulls a small overlap
  window, COMEX re-downloads only on ETag change. No leg re-pulls its whole
  history, so re-running is cheap and idempotent enough for cron.
- **COMTRADE is excluded** from `all` (key-gated), so the job needs **no secret** —
  only the runtime SA's GCP credentials.

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | The job image (`uv sync --no-dev`, runs `embrapa ingest all`). |
| `cloudbuild.yaml` | Builds the image from the repo root via Cloud Build. |
| `deploy.sh` | Build + create/update the Cloud Run Job. Reads `.env`. |
| `schedule.sh` | Create/update the nightly (delta) Cloud Scheduler trigger. |
| `schedule_reconcile.sh` | Create/update the MONTHLY deep-refresh trigger (same Job, args overridden to `reconcile`). |
| `schedule_comtrade.sh` | Per-source UN Comtrade world-backfill scheduler (see `docs/comtrade_world_backfill.md`). |
| `schedule_pam.sh` | IBGE PAM manual scheduler. |
| `schedule_ppm.sh` | IBGE PPM (livestock) monthly scheduler (same Job, args overridden to `ibge-ppm`). |
| `alert.sh` | Create the Cloud Monitoring alert (email channel + policy) for job failures. |
| `alert_policy.json` | The alert-policy template `alert.sh` applies (`__JOB_NAME__` substituted in). |

## One-time prerequisites

```bash
# Enable APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com cloudscheduler.googleapis.com

# The runtime SA (write GCS + BQ) — see docs/iam_setup.md. Typically:
#   roles/storage.objectAdmin, roles/bigquery.dataEditor, roles/bigquery.jobUser
```

## Deploy

From the repo root (config is read from `.env` — the same single source of truth
the CLI uses):

```bash
make ingest-job-deploy        # build image + create/update the job
# then run it once to validate (use the job's region — INGEST_JOB_REGION, default
# us-central1; NOT BQ_LOCATION, which may be a multi-region Cloud Run can't use):
gcloud run jobs execute embrapa-ingest-all --region <INGEST_JOB_REGION> --project <GCP_PROJECT_ID>
```

`deploy.sh` forwards config to the job via an **explicit allowlist** — only the
keys `embrapa ingest all` actually reads: `GCP_PROJECT_ID`, `GCS_*`,
`BQ_LOCATION`, the `BQ_BRONZE_*` dataset/table names, and the per-source scope
vars `IBGE_*` / `PAM_*` / `PPM_*` / `BCB_*` / `COMEX_*` (PAM/PPM are forwarded
even though they are out of `ingest all` — their monthly schedulers override the
args to `ibge-pam`/`ibge-ppm` and rely on the same allowlist). Everything else in
`.env` is **not** shipped
to the Job: the secret `COMTRADE_API_KEY` and `GCP_IMPERSONATION_SA`, all other
`COMTRADE_*` (COMTRADE is key-gated and excluded from `all`), the serving/cache
vars (`BQ_SERVING_DATASET`, `BQ_RESEARCH_INPUTS_DATASET`,
`BQ_CODE_INDUSTRIALIZATION_LOG_TABLE`,
`CACHE_*`), the dbt-only `BQ_SILVER_DATASET` / `BQ_GOLD_DATASET`, the `BACKUP_*`
knobs, and the deploy-time `INGEST_*` / `INGEST_SCHEDULE_*` vars (read by these
scripts, never by the app). The job runs **as** the ingestion SA, so it
authenticates via the runtime identity — no keyfile, no impersonation.

### Keeping the deployed image current (CI auto-deploy)

`make ingest-job-deploy` is the **operator** path — it is what you run when the
Job's **env or config** must change. Nothing about it is automatic, and that is
how the Job silently fell a month behind `main`: it ran the `v1.17.0` image
(built 2026-07-14) until 2026-08-16, so a fix merged in v1.19.0 never reached
production and the monthly UN Comtrade run kept paging on self-healing HTTP 429s.

`.github/workflows/ingestion-job-deploy.yml` closes that gap: on every merge to
`main` touching `src/embrapa_dashboard/**`, `pyproject.toml`, `uv.lock` or
`deploy/ingestion/**`, CI rebuilds the image and points the Job at it with a
**surgical `gcloud run jobs update --image`** — only the image changes, so env,
the `COMTRADE_API_KEY` secret ref, the runtime SA, retries and timeout all
persist. It never *executes* the Job (the CI identity is deliberately not granted
`run.jobs.run`); the next scheduled run picks the image up.

The image is tagged with the commit's short SHA, so "which commit is the Job
running?" is answerable from the console — the earlier drift was invisible
precisely because it wasn't.

Requires the one-time GCP setup documented in that workflow's header (a dedicated
`sa-ingest-deploy-ci` identity + the `GCP_INGEST_DEPLOY_SERVICE_ACCOUNT` repo
variable). **Until that variable is set the workflow skips**, so merging it
changes nothing; it activates by itself once the variable exists.

## Schedule

```bash
make ingest-job-schedule      # 05:00 America/Sao_Paulo daily by default
# grant the scheduler SA permission to run the job (one-time; --region is the
# job's region = INGEST_JOB_REGION, default us-central1):
gcloud run jobs add-iam-policy-binding embrapa-ingest-all \
  --region <INGEST_JOB_REGION> --project <GCP_PROJECT_ID> \
  --member "serviceAccount:sa-data-pipeline-prod@<GCP_PROJECT_ID>.iam.gserviceaccount.com" \
  --role roles/run.invoker
```

## Monthly deep-refresh (catch revisions of old data)

The nightly run is **delta** — each source only revisits a recent window, so an
upstream **correction to an old year** (IBGE revising a 1999 PEVS value, BCB
re-publishing an old month) is never re-queried. COMEX is the exception: its
per-file ETag check already re-detects any year. To catch IBGE/BCB old-year
revisions, a **monthly** trigger runs the SAME Job with its args overridden to
`reconcile` (`embrapa ingest reconcile`) — a full re-download of every source's
configured history (the IBGE leg year-chunked so the big window survives the
unattended slow-byte deadline; BCB + COMEX with `--full`).

```bash
make ingest-job-reconcile-schedule    # 1st of month, 03:00 America/Sao_Paulo by default
```

This uses the Cloud Run Admin **v2** `:run` API (the only one that can override a
Job's args) with a longer task timeout for the heavier full window. Overriding
args needs **`run.jobs.runWithOverrides`**, which `roles/run.invoker` does *not*
grant (a non-empty `overrides` body with only invoker gets a 403). Grant the
scheduler SA the least-privilege role built for this — `roles/run.jobsExecutorWithOverrides`
(or the broader `roles/run.developer`). The script prints the exact command:

```bash
gcloud run jobs add-iam-policy-binding embrapa-ingest-all \
  --region <INGEST_JOB_REGION> --project <GCP_PROJECT_ID> \
  --member "serviceAccount:sa-data-pipeline-prod@<GCP_PROJECT_ID>.iam.gserviceaccount.com" \
  --role roles/run.jobsExecutorWithOverrides
```

Run it once on demand (no scheduler) — e.g. to force-unstick a frozen source:

```bash
gcloud run jobs execute embrapa-ingest-all --region <INGEST_JOB_REGION> \
  --project <GCP_PROJECT_ID> --args=reconcile
```

> **Reaches the dashboard via the scheduled dbt build.** `reconcile` refreshes
> only **Bronze**. Silver/Gold update on the next run of the scheduled
> `dbt build` (`.github/workflows/dbt-build-prod.yml`). Because the incremental
> `silver_ibge_pevs` keys its re-scan off `ingestion_timestamp` (not year), a
> plain build carries an old-year revision all the way to Gold — no
> `--full-refresh` needed. Locally, `make reconcile` chains both (but re-ingests
> via your **local** `.env` — verify it matches prod first).

## Alert on failure

A blind nightly cron is only safe if a *failure* is noticed. `alert.sh` wires a
**Cloud Monitoring** alert so a failed run emails someone instead of being
discovered only when the dashboard looks stale.

```bash
# in .env: who to notify (comma-separated for multiple recipients)
INGEST_ALERT_EMAIL=ops@example.com,lead@example.com

make ingest-job-alert         # creates the email channel(s) + the alert policy (idempotent)
```

It creates (both idempotent — safe to re-run):

1. an **email notification channel per recipient** in `INGEST_ALERT_EMAIL`
   (comma-separated), reused on re-run by its email address;
2. an **alert policy** on the metric `run.googleapis.com/job/completed_execution_count`
   filtered to `result="failed"` for this job, firing when failed executions
   `> 0` over a 1-hour window (the policy body is `alert_policy.json`).

A Cloud Run execution only counts as `failed` after a task exhausts its retries
(and the CLI itself retries upstream calls via `tenacity`), so this fires on a
**real**, non-transient failure — not a flaky night. The runner needs
`roles/monitoring.editor` (or `roles/monitoring.alertPolicyEditor` +
`roles/monitoring.notificationChannelEditor`). The channel is created via the
Monitoring REST API (the `gcloud monitoring channels` surface is beta-only and
often not installed), so the script needs `curl` + `python3` + base `gcloud`
auth — no `beta` component. Verify:

```bash
gcloud monitoring policies list --project <GCP_PROJECT_ID> \
  --filter='display_name="Embrapa ingestion job failed - embrapa-ingest-all"'
```

## Tunable knobs (optional `.env` overrides)

All have sensible defaults; set them in `.env` only to override:

| Var | Default | Meaning |
|---|---|---|
| `INGEST_JOB_REGION` | `us-central1` | Cloud Run region (a **single** region). **Decoupled from `BQ_LOCATION`** — Cloud Run rejects a BigQuery multi-region locator like `US`/`EU`, so this is its own input. If you do set it to `US` or `EU` it's mapped (→ `us-central1` / `europe-west1`); any other bare multi-region is rejected with a clear error. |
| `INGEST_JOB_NAME` | `embrapa-ingest-all` | Job name |
| `INGEST_JOB_AR_REPO` | `embrapa-jobs` | Artifact Registry repo |
| `INGEST_JOB_SA` | `sa-data-pipeline-prod@<project>…` | Runtime service account |
| `INGEST_JOB_TASK_TIMEOUT` | `3600s` | Max wall-clock per run |
| `INGEST_JOB_MEMORY` / `INGEST_JOB_CPU` | `2Gi` / `1` | Resources |
| `INGEST_SCHEDULE_CRON` | `0 5 * * *` | Nightly (delta) cron expression |
| `INGEST_SCHEDULE_TZ` | `America/Sao_Paulo` | Schedule timezone (both triggers) |
| `RECONCILE_SCHEDULE_CRON` | `0 3 1 * *` | Monthly deep-refresh cron (1st of month, 03:00) |
| `RECONCILE_SCHEDULE_NAME` | `<job>-reconcile-monthly` | Scheduler name for the deep-refresh trigger |
| `RECONCILE_JOB_TASK_TIMEOUT` | `7200s` | Task timeout for the (heavier) reconcile execution |
| `PAM_SCHEDULE_CRON` / `PAM_SCHEDULE_TZ` / `PAM_SCHEDULE_NAME` | `0 4 2 * *` / `America/Sao_Paulo` / `<job>-pam-monthly` | Monthly PAM trigger (read by `schedule_pam.sh`) |
| `PPM_SCHEDULE_CRON` / `PPM_SCHEDULE_TZ` / `PPM_SCHEDULE_NAME` | `<see schedule_ppm.sh>` / `America/Sao_Paulo` / `<job>-ppm-monthly` | Monthly PPM trigger (read by `schedule_ppm.sh`) |
| `COMTRADE_SCHEDULE_CRON` / `COMTRADE_SCHEDULE_TZ` / `COMTRADE_SCHEDULE_NAME` | `<see schedule_comtrade.sh>` | Comtrade backfill trigger (read by `schedule_comtrade.sh`) |
| `INGEST_ALERT_EMAIL` | _(required for `alert.sh`)_ | Recipient for job-failure alerts |
| `INGEST_ALERT_CHANNEL_NAME` | `Embrapa ingestion alerts` | Display name of the notification channel |

## Notes & troubleshooting

- **Single source per run:** override the command to ingest just one source, e.g.
  `gcloud run jobs execute embrapa-ingest-all --args=ibge …` (the entrypoint is
  `embrapa ingest`, so `--args ibge` runs `embrapa ingest ibge`).
- **First historical backfill:** the nightly job is **delta** (recent years
  only), so it never does the full IBGE/COMEX history. Seed the history once
  locally (`make ingest-ibge-historical` for IBGE; a `--full` COMEX run) — then
  the job keeps it current via delta.
- **Logs:** `gcloud run jobs executions list --job embrapa-ingest-all …` then
  `gcloud run jobs executions describe <execution> …`. The pipeline also emits
  structured events consumable by `embrapa monitor`.
