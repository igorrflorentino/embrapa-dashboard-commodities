#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Create/update the DAILY BCB câmbio (PTAX) ingestion Cloud Scheduler trigger.
#
# Why this exists as its own trigger, from measurement (2026-08-28): of the four
# sources in `ingest all`, only the FX series genuinely advances every day. Over
# 30 days of daily polling, the newest reference date moved:
#
#   BCB câmbio (PTAX)  22 times  ← business days; daily polling is EARNED
#   BCB inflação        2 times  ← monthly series; 30 polls for 2 advances
#   MDIC COMEX          wrote on 3 of 30 days (its ETag short-circuits)
#   IBGE PEVS           wrote on 2 of 30 days (annual source)
#
# So the batch moved to WEEKLY (schedule.sh) and FX kept its daily cadence here.
# The saving is not the point — ingestion is ~1% of the BigQuery bill (measured:
# 1.3 GB/week against the daily dbt build's 121 GB/week). The point is to stop
# asking four APIs for data three of them only publish monthly or yearly.
#
# Runs the SAME Job (embrapa-ingest-all) with its container args overridden to
# ["bcb-currency"] → `embrapa ingest bcb-currency`. Delta-aware: it rewinds a
# year-granular overlap, so one missed day self-heals on the next run.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found"; exit 1; }
get_env() { { grep -E "^$1=" "$ENV_FILE" || true; } | head -n1 | cut -d= -f2- | tr -d '\r'; }

resolve_region() {
  local r="${INGEST_JOB_REGION:-}"
  if [ -z "$r" ]; then echo us-central1; return 0; fi
  case "$r" in
    US|us) echo us-central1 ;;
    EU|eu) echo europe-west1 ;;
    *-*)   echo "$r" ;;
    *)
      echo "ERROR: INGEST_JOB_REGION='$r' is not a Cloud Run region." >&2
      exit 1 ;;
  esac
}

PROJECT="${GCP_PROJECT_ID:-$(get_env GCP_PROJECT_ID)}"
[ -n "$PROJECT" ] || { echo "ERROR: GCP_PROJECT_ID not set"; exit 1; }
REGION="$(INGEST_JOB_REGION="${INGEST_JOB_REGION:-$(get_env INGEST_JOB_REGION)}" resolve_region)"
JOB_NAME="${INGEST_JOB_NAME:-$(get_env INGEST_JOB_NAME)}"
JOB_NAME="${JOB_NAME:-embrapa-ingest-all}"

SCHED_NAME="${CURRENCY_SCHEDULE_NAME:-$(get_env CURRENCY_SCHEDULE_NAME)}"
SCHED_NAME="${SCHED_NAME:-${JOB_NAME}-currency-daily}"
# Daily at 05:00 BRT — the slot the old nightly batch used, so nothing else moved.
CRON="${CURRENCY_SCHEDULE_CRON:-$(get_env CURRENCY_SCHEDULE_CRON)}"
CRON="${CRON:-0 5 * * *}"
SCHED_TZ="${CURRENCY_SCHEDULE_TZ:-$(get_env CURRENCY_SCHEDULE_TZ)}"
SCHED_TZ="${SCHED_TZ:-America/Sao_Paulo}"
SCHED_SA="${INGEST_SCHEDULE_SA:-$(get_env INGEST_SCHEDULE_SA)}"
SCHED_SA="${SCHED_SA:-sa-data-pipeline-prod@${PROJECT}.iam.gserviceaccount.com}"
# A delta FX run is tiny (one SGS series window); the ceiling is generous only so a
# slow BCB response never truncates it.
TASK_TIMEOUT="${CURRENCY_JOB_TASK_TIMEOUT:-$(get_env CURRENCY_JOB_TASK_TIMEOUT)}"
TASK_TIMEOUT="${TASK_TIMEOUT:-1800s}"

URI="https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/${JOB_NAME}:run"

# Override CMD ["all"] → ["bcb-currency"]; ENTRYPOINT ["embrapa","ingest"] stays, so
# the container runs `embrapa ingest bcb-currency` (delta-aware, keyless).
BODY_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE"' EXIT
cat > "$BODY_FILE" <<JSON
{"overrides":{"containerOverrides":[{"args":["bcb-currency"]}],"timeout":"${TASK_TIMEOUT}","taskCount":1}}
JSON

if gcloud scheduler jobs describe "$SCHED_NAME" \
     --location "$REGION" --project "$PROJECT" >/dev/null 2>&1; then
  ACTION=update
else
  ACTION=create
fi

echo "${ACTION^} scheduler '$SCHED_NAME': '$CRON' ($SCHED_TZ) → run '$JOB_NAME' as bcb-currency (timeout ${TASK_TIMEOUT})"
gcloud scheduler jobs "$ACTION" http "$SCHED_NAME" --project "$PROJECT" --location "$REGION" \
  --schedule "$CRON" --time-zone "$SCHED_TZ" \
  --uri "$URI" --http-method POST \
  $( [ "$ACTION" = update ] && printf -- --update-headers || printf -- --headers ) "Content-Type=application/json" \
  --message-body-from-file "$BODY_FILE" \
  --oauth-service-account-email "$SCHED_SA"

cat <<EOF

Scheduled the DAILY BCB câmbio (PTAX) ingest. Before it can succeed, ensure (one-time):
  • the Job forwards BCB_* config — it already does (the nightly batch used it)
  • the scheduler SA can override args (same as reconcile/comtrade/pam):
      gcloud run jobs add-iam-policy-binding $JOB_NAME --region $REGION --project $PROJECT \\
        --member "serviceAccount:$SCHED_SA" --role roles/run.jobsExecutorWithOverrides

Trigger a run now (delta — tiny):
  gcloud scheduler jobs run $SCHED_NAME --location $REGION --project $PROJECT
Or directly:
  gcloud run jobs execute $JOB_NAME --region $REGION --project $PROJECT --args=bcb-currency

To refetch the full PTAX history from BCB_START_YEAR (heavy, rarely needed):
  uv run embrapa ingest bcb-currency --full

NOTE: refreshes only BRONZE. Silver/Gold update on the next scheduled dbt build.
EOF
