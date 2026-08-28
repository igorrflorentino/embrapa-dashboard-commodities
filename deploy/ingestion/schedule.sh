#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Create/update the Cloud Scheduler trigger that runs the ingestion Job nightly.
#
# Cloud Scheduler hits the Cloud Run Admin API `jobs:run` endpoint with an OAuth
# token from a service account that holds roles/run.invoker on the job. Defaults
# to 05:00 America/Sao_Paulo (early morning / madrugada — low contention, off the
# analysis window). Idempotent.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found"; exit 1; }
# `|| true` contains grep's no-match exit under set -euo pipefail (an optional
# key absent from .env must yield empty, not kill the script) — same helper as
# schedule_reconcile.sh / schedule_comtrade.sh.
get_env() { { grep -E "^$1=" "$ENV_FILE" || true; } | head -n1 | cut -d= -f2- | tr -d '\r'; }

# Resolve the Cloud Run region — must match deploy.sh so the scheduler targets
# the same region the Job was deployed to. INGEST_JOB_REGION is a first-class
# input DECOUPLED from BQ_LOCATION (a BigQuery multi-region like "US"/"EU" is
# NOT a valid Cloud Run region), defaulting to us-central1; an explicit
# multi-region locator is mapped, a bare/unmapped one is rejected.
resolve_region() {
  local r="${INGEST_JOB_REGION:-}"
  if [ -z "$r" ]; then
    echo us-central1
    return 0
  fi
  case "$r" in
    US|us) echo us-central1 ;;
    EU|eu) echo europe-west1 ;;
    *-*)   echo "$r" ;;
    *)
      echo "ERROR: INGEST_JOB_REGION='$r' is not a Cloud Run region (multi-region not allowed)." >&2
      echo "       Set INGEST_JOB_REGION explicitly in .env (decoupled from BQ_LOCATION)." >&2
      exit 1
      ;;
  esac
}

PROJECT="${GCP_PROJECT_ID:-$(get_env GCP_PROJECT_ID)}"
[ -n "$PROJECT" ] || { echo "ERROR: GCP_PROJECT_ID not set"; exit 1; }
REGION="$(INGEST_JOB_REGION="${INGEST_JOB_REGION:-$(get_env INGEST_JOB_REGION)}" resolve_region)"
JOB_NAME="${INGEST_JOB_NAME:-embrapa-ingest-all}"
SCHED_NAME="${INGEST_SCHEDULE_NAME:-${JOB_NAME}-weekly}"
# WEEKLY (Monday 05:00 BRT), not nightly. Measured 2026-08-28: of the four sources in
# `ingest all`, only BCB câmbio advances daily (22 of 30 days) — and it now has its own
# daily trigger (schedule_currency.sh). The other three advance monthly or yearly:
# inflação moved twice in 30 days, COMEX wrote on 3 days, PEVS on 2. A weekly batch polls
# each of them well above its real publication rate while bounding staleness at 7 days.
CRON="${INGEST_SCHEDULE_CRON:-0 5 * * 1}"
SCHED_TZ="${INGEST_SCHEDULE_TZ:-America/Sao_Paulo}"
# Same .env fallback chain as schedule_reconcile.sh / schedule_comtrade.sh.
SCHED_SA="${INGEST_SCHEDULE_SA:-$(get_env INGEST_SCHEDULE_SA)}"
SCHED_SA="${SCHED_SA:-sa-data-pipeline-prod@${PROJECT}.iam.gserviceaccount.com}"

# Cloud Run Admin API v1 "run job" endpoint.
URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run"

if gcloud scheduler jobs describe "$SCHED_NAME" \
     --location "$REGION" --project "$PROJECT" >/dev/null 2>&1; then
  ACTION=update
else
  ACTION=create
fi

echo "${ACTION^} scheduler '$SCHED_NAME': '$CRON' ($SCHED_TZ) → run '$JOB_NAME'"
gcloud scheduler jobs "$ACTION" http "$SCHED_NAME" --project "$PROJECT" --location "$REGION" \
  --schedule "$CRON" --time-zone "$SCHED_TZ" \
  --uri "$URI" --http-method POST \
  --oauth-service-account-email "$SCHED_SA"

cat <<EOF

Scheduled. The scheduler SA must hold run.invoker on the job:
  gcloud run jobs add-iam-policy-binding $JOB_NAME --region $REGION --project $PROJECT \\
    --member "serviceAccount:$SCHED_SA" --role roles/run.invoker
Trigger a test run immediately:
  gcloud scheduler jobs run $SCHED_NAME --location $REGION --project $PROJECT
EOF
