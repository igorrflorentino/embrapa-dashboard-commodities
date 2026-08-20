# IAM Setup Guide

Step-by-step instructions for administrators to set up Google Cloud IAM roles and Service Accounts for the enterprise architecture.

## Prerequisites

- **Google Cloud Project:** `embrapa-dashboard-commodities`
- **gcloud CLI installed:** https://cloud.google.com/sdk/docs/install
- **Admin access** to the GCP project

## Overview

This guide creates:

1. **Four service accounts** with distinct responsibilities
2. **IAM role bindings** for developers and automation

No JSON keyfiles are generated, stored, or distributed. All access flows
through OAuth + service account impersonation.

**Estimated time:** 10-15 minutes

## CI service accounts (keyless, via Workload Identity Federation)

Separate from the human/pipeline identities below: GitHub Actions authenticates with
**no service-account keys**, through a WIF pool (`github`) that maps this repository to a
dedicated identity **per purpose**. There is one SA per workflow rather than a shared
"CI" SA, so a compromised workflow cannot do another one's job.

| Service account | Used by | Can do |
|---|---|---|
| `sa-dbt-build-ci` | `ci.yml`, `dbt-build-prod.yml`, `dbt-source-freshness.yml` | build prod Silver/Gold in BigQuery |
| `sa-release-ci` | `release.yml` | push the release image |
| `sa-ingest-deploy-ci` | `ingestion-job-deploy.yml` | push + update the ingestion **Job** |
| `sa-webapi-deploy-ci` | `webapi-deploy.yml` | push + update the webapi **Service** image |
| `sa-dashboard-smoke-ci` | ⚠️ **nothing, currently** | invoke the Service |

> ⚠️ `sa-dashboard-smoke-ci` is a **leftover**: it still exists, still has its
> `GCP_SMOKE_SERVICE_ACCOUNT` repo variable and its WIF binding, but **no workflow
> references it** — verified 2026-08-20. It belonged to the smoke test that was removed
> along with the Dash UI. Standing keyless access that nothing uses is access worth
> removing; delete the SA and the variable, or wire up the smoke check it was meant for.

**The exact `gcloud` commands for each live in the header comment of the workflow that
uses it** — deliberately, so the grant and the thing it enables never drift apart. This
table is the index; the workflow header is the source of truth.

Two recurring gotchas, both already documented in those headers:

- Bindings are scoped to the **resource** (this Artifact Registry repo, this Cloud Run
  service, this runtime SA), never project-wide. Deploying a service that *runs as*
  another SA additionally needs `roles/iam.serviceAccountUser` **on that runtime SA**.
- A fresh `workloadIdentityUser` binding takes **~2 minutes to propagate**. A workflow run
  started immediately fails with a 403 on `iam.serviceAccounts.getAccessToken`; just re-run
  it — no config change is needed.

---

## Step 1: Authenticate as Admin

```bash
gcloud auth login igorlopesc@gmail.com
gcloud config set project embrapa-dashboard-commodities
```

Verify:
```bash
gcloud config list
# Output:
# [core]
# project = embrapa-dashboard-commodities
```

## Step 2: Create Service Accounts

### 2.1 Developer Impersonation Target SA

```bash
gcloud iam service-accounts create sa-secret-reader-prod \
  --display-name="Developer Workflow (Prod)" \
  --description="Impersonation target for developer workflows (dbt + ad-hoc queries)."
```

Grant developer-workflow permissions:
```bash
# Read/write to BigQuery (dbt builds, ad-hoc queries)
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member=serviceAccount:sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --role=roles/bigquery.dataEditor

# Run BigQuery jobs + create own datasets (dbt builds the dbt_dev_* schemas)
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member=serviceAccount:sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --role=roles/bigquery.user

# Read GCS landing data
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member=serviceAccount:sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --role=roles/storage.objectViewer

# Allow the SA to make API calls to GCP services (storage.objectViewer does not include this)
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member=serviceAccount:sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --role=roles/serviceusage.serviceUsageConsumer
```

> Note: the `sa-secret-reader-prod` name is historical — it pre-dates the
> decision to drop Secret Manager. The account is now purely an impersonation
> target. Feel free to rename it in your IAM console if you prefer.

### 2.2 Data Pipeline SA

```bash
gcloud iam service-accounts create sa-data-pipeline-prod \
  --display-name="Data Pipeline (Prod)" \
  --description="Runs IBGE and BCB ingestion pipelines. No human access."
```

Grant data pipeline permissions:
```bash
# Read + write GCS raw/ — the ingestion is TWO-PHASE: Phase 1 writes the raw
# archive, Phase 2 reads it back to derive Bronze (and `--from-raw` re-reads it).
# objectCreator alone (write-only) is therefore INSUFFICIENT — the pipeline SA
# must also read. objectAdmin grants both; or pair objectCreator + objectViewer.
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member=serviceAccount:sa-data-pipeline-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin

# Write to BigQuery (Bronze)
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member=serviceAccount:sa-data-pipeline-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --role=roles/bigquery.dataEditor

# Run BigQuery jobs
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member=serviceAccount:sa-data-pipeline-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --role=roles/bigquery.jobUser
```

### 2.3 Web Dashboard SA

> **One-command path:** §2.3 + §2.4 are codified idempotently in
> [`deploy/iam/grant_least_privilege.sh`](../deploy/iam/grant_least_privilege.sh) —
> run `make iam-grant` (or `DRY_RUN=1 make iam-grant` to preview). It reads
> `GCP_PROJECT_ID` / dataset names from `.env`, creates the SAs if missing, and
> re-asserts the grants without appending duplicate ACL entries. Run it **after**
> the `serving` / `research_inputs` datasets exist (first prod dbt build / first
> curation write). The manual steps below document exactly what it does.

```bash
gcloud iam service-accounts create sa-web-dashboard-prod \
  --display-name="Web Dashboard (Prod)" \
  --description="Stateless Cloud Run dashboard: read 'serving', append to 'research_inputs'."
```

**Least privilege — dataset-scoped, NOT project-wide.** The dashboard only ever
reads the pre-aggregated `serving` marts and appends curation rows to
`research_inputs`. It must **not** be able to read the whole Gold dataset, nor
write anywhere except the curation log. So grant:

- `roles/bigquery.dataViewer` **scoped to the `serving` dataset** (read marts + `dim_code_industrialization_scd2`),
- `roles/bigquery.dataEditor` **scoped to the `research_inputs` dataset** (the append-only `INSERT`),
- `roles/bigquery.jobUser` **at project level** (required to *run* a query job — this role grants no data access on its own).

BigQuery dataset-level roles are granted on the dataset resource (not via
`gcloud projects add-iam-policy-binding`, which is project-wide). The portable
way is to merge an access entry into the dataset with `bq`:

```bash
SA="sa-web-dashboard-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com"

# READ on the serving dataset only.
bq show --format=prettyjson embrapa-dashboard-commodities:serving > /tmp/serving.json
jq --arg sa "$SA" \
  '.access += [{"role":"READER","userByEmail":$sa}]' /tmp/serving.json > /tmp/serving.patched.json
bq update --source /tmp/serving.patched.json embrapa-dashboard-commodities:serving

# WRITE (append) on the research_inputs dataset only.
bq show --format=prettyjson embrapa-dashboard-commodities:research_inputs > /tmp/research.json
jq --arg sa "$SA" \
  '.access += [{"role":"WRITER","userByEmail":$sa}]' /tmp/research.json > /tmp/research.patched.json
bq update --source /tmp/research.patched.json embrapa-dashboard-commodities:research_inputs

# jobUser is the ONLY project-level role — needed to execute query jobs, grants no data access.
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member="serviceAccount:${SA}" \
  --role=roles/bigquery.jobUser
```

> BigQuery's legacy dataset roles `READER`/`WRITER`/`OWNER` map to
> `dataViewer`/`dataEditor`/`dataOwner`. The `serving` and `research_inputs`
> datasets are auto-created on first prod build / first curation write — run
> these grants **after** those datasets exist. Looker Studio does **not** use
> this SA (it reads Gold via end-user OAuth), so scoping the SA to `serving`
> does not affect the no-code path.

### 2.4 AI Agent Admin SA

```bash
gcloud iam service-accounts create sa-ai-agent-admin-prod \
  --display-name="AI Agent Admin (Prod)" \
  --description="AI agents: read-only analysis; writes confined to one report sandbox."
```

**Least privilege — read-only on data, writes confined to a sandbox.** An AI
agent analyzes the warehouse and emits reports. It must be able to *read* and
*run queries*, but it must **never** hold project-wide `dataEditor` — that would
let it overwrite Gold prod tables or, worse, tamper with the append-only
curation log in `research_inputs` (which would destroy the `edited_by` audit
trail). So grant read-only data access project-wide, `jobUser` to run queries,
and confine all *write* to a single dedicated report/sandbox dataset.

```bash
SA="sa-ai-agent-admin-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com"
AGENT_SANDBOX_DATASET=ai_reports   # one dedicated dataset for agent output; create it first.

# Create the sandbox dataset the agent is allowed to write to.
bq mk --dataset --location=us-central1 embrapa-dashboard-commodities:${AGENT_SANDBOX_DATASET}

# Read-only on data (project-wide) — analysis across Bronze/Silver/Gold.
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member="serviceAccount:${SA}" \
  --role=roles/bigquery.dataViewer

# Run query jobs (no data access on its own).
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member="serviceAccount:${SA}" \
  --role=roles/bigquery.jobUser

# WRITE confined to the sandbox dataset ONLY (never project-wide, never on gold/research_inputs).
bq show --format=prettyjson embrapa-dashboard-commodities:${AGENT_SANDBOX_DATASET} > /tmp/agent.json
jq --arg sa "$SA" \
  '.access += [{"role":"WRITER","userByEmail":$sa}]' /tmp/agent.json > /tmp/agent.patched.json
bq update --source /tmp/agent.patched.json embrapa-dashboard-commodities:${AGENT_SANDBOX_DATASET}

# Read from GCS + write reports to GCS.
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member="serviceAccount:${SA}" \
  --role=roles/storage.objectViewer
gcloud projects add-iam-policy-binding embrapa-dashboard-commodities \
  --member="serviceAccount:${SA}" \
  --role=roles/storage.objectCreator
```

> The previous version granted project-wide `roles/bigquery.dataEditor`, which
> let this SA write **any** dataset — including `gold` prod and the
> `research_inputs` curation log. Read-only + a write-scoped sandbox closes that
> gap while still letting the agent materialize its own report tables.

### 2.5 Verify Service Accounts Created

```bash
gcloud iam service-accounts list --filter="displayName:*Prod"

# Output:
# NAME                                             EMAIL
# sa-secret-reader-prod                           sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com
# sa-data-pipeline-prod                           sa-data-pipeline-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com
# sa-web-dashboard-prod                           sa-web-dashboard-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com
# sa-ai-agent-admin-prod                          sa-ai-agent-admin-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com
```

## Step 3: Grant Developer Impersonation Access

Developers need permission to impersonate `sa-secret-reader-prod` so dbt and
ad-hoc queries can run as that service account.

### 3.1 For Individual Developer

```bash
# Replace with actual email
DEVELOPER_EMAIL="florenciaitalo@gmail.com"

gcloud iam service-accounts add-iam-policy-binding \
  sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --member=user:${DEVELOPER_EMAIL} \
  --role=roles/iam.serviceAccountTokenCreator
```

### 3.2 For Development Team (Batch)

```bash
# Create batch_developers.txt with one email per line
cat > batch_developers.txt << 'EOF'
florenciaitalo@gmail.com
dev2@gmail.com
dev3@gmail.com
EOF

# Grant all at once
while read email; do
  gcloud iam service-accounts add-iam-policy-binding \
    sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
    --member=user:${email} \
    --role=roles/iam.serviceAccountTokenCreator
done < batch_developers.txt
```

### 3.3 Verify Developer Permissions

```bash
gcloud iam service-accounts get-iam-policy \
  sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --format=json | jq '.bindings[] | select(.role=="roles/iam.serviceAccountTokenCreator")'

# Output:
# {
#   "role": "roles/iam.serviceAccountTokenCreator",
#   "members": [
#     "user:florenciaitalo@gmail.com",
#     "user:dev2@gmail.com"
#   ]
# }
```

## Step 4: Authenticate Developers

Each developer runs this **once per machine** (or after gcloud is installed):

```bash
# Developer command
gcloud auth application-default login

# Or for specific account
gcloud auth login florenciaitalo@gmail.com
```

This opens a browser, developer logs in with their Google account, and an OAuth token is cached locally.

## Step 5: Developer Setup

Each developer runs the setup script:

```bash
# Developer command
cd embrapa-dashboard-commodities
python3 scripts/setup_dev_env.py
```

The script will:
1. Detect OAuth context (gcloud auth)
2. Validate impersonation permissions
3. Create `.env` with `GCP_AUTH_METHOD=impersonation`
4. Create `~/.dbt/profiles.yml` with `method: oauth` + `impersonate_service_account`

## Step 6: Verify Setup

### 6.1 Developer Verifies Setup

```bash
# Developer runs:
uv run embrapa doctor

# Output should include:
# ✅ BigQuery connection: OK (impersonating sa-secret-reader-prod)
# ✅ GCS bucket access: OK
# ✅ dbt: OK (using OAuth)
```

### 6.2 Admin Checks Audit Logs

```bash
# Admin verifies audit trail
gcloud logging read \
  "protoPayload.authenticationInfo.principalEmail=florenciaitalo@gmail.com AND
   protoPayload.request.policy.bindings.members=*sa-secret-reader-prod*" \
  --limit=10 \
  --format=table(timestamp,protoPayload.methodName,protoPayload.authenticationInfo.principalEmail)

# Output shows impersonation events:
# 2026-05-21T15:30:45.123Z  compute.instances.setServiceAccount  florenciaitalo@gmail.com
```

## Step 7 (Optional): Grant Additional Service Account Roles

### For CI/CD (Cloud Run / Cloud Scheduler)

If you want automated pipelines to run as `sa-data-pipeline-prod`:

```bash
# Service: Cloud Run Jobs
gcloud iam service-accounts add-iam-policy-binding \
  sa-data-pipeline-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --member=serviceAccount:cloud-run-service-account@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountUser
```

### For GitHub Actions Workload Identity Federation (No Secret Keys in GitHub)

```bash
# Create GitHub OIDC provider (one-time setup)
gcloud iam workload-identity-pools create "github-pool" \
  --project="embrapa-dashboard-commodities" \
  --location="global" \
  --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="embrapa-dashboard-commodities" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.aud=assertion.aud,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Bind GitHub to sa-data-pipeline-prod
gcloud iam service-accounts add-iam-policy-binding \
  sa-data-pipeline-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --project="embrapa-dashboard-commodities" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/NUMERIC_PROJECT_ID/locations/global/workloadIdentityPools/github-pool/attribute.repository/igorrflorentino/embrapa-dashboard-produtos-agricolas"
```

## Step 8: Credential Rotation

There is nothing to rotate manually. OAuth tokens are short-lived (~1 hour)
and refreshed automatically by gcloud. No static service account keys exist
in this architecture.

## Step 9: Offboarding (Revoke Developer Access)

When a developer leaves:

```bash
DEPARTING_EMAIL="departed@gmail.com"

# Remove impersonation permission
gcloud iam service-accounts remove-iam-policy-binding \
  sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --member=user:${DEPARTING_EMAIL} \
  --role=roles/iam.serviceAccountTokenCreator

# Immediate effect - no new tokens can be generated
# No need to rotate the service account key
```

Verify removal:
```bash
gcloud iam service-accounts get-iam-policy \
  sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com \
  --format=json | jq '.bindings[] | select(.role=="roles/iam.serviceAccountTokenCreator") | .members'

# Output should NOT include the departing email
```

## Troubleshooting

### "Permission denied: cannot impersonate sa-secret-reader-prod"

**Problem:** Developer's account is missing the Token Creator role.

**Solution:** Verify developer is in `iam.serviceAccountTokenCreator` role:
```bash
gcloud iam service-accounts get-iam-policy \
  sa-secret-reader-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com
```

If missing, re-run Step 3 for that developer.

### "Failed to impersonate: Invalid Compute Credential"

**Problem:** gcloud auth not working.

**Solution:**
```bash
gcloud auth application-default login
# or
gcloud auth login florenciaitalo@gmail.com
```

### "Service account sa-secret-reader-prod does not exist"

**Problem:** Service account not created.

**Solution:** Run Step 2.1 to create it.

### "embrapa doctor: BigQuery connection failed"

**Problem:** Setup script detected impersonation, but it doesn't actually work.

**Solution:**
1. Verify `gcloud auth` is configured:
   ```bash
   gcloud config list
   ```
2. Verify developer has impersonation permission (Step 3)
3. Check audit logs for permission errors:
   ```bash
   gcloud logging read "resource.type=service_account" --limit=10
   ```

## Reference: Complete IAM Permission Matrix

| Component | Service Account | Roles | Purpose |
|---|---|---|---|
| **Developer Local** | (user email) | `roles/iam.serviceAccountTokenCreator` on `sa-secret-reader-prod` | Can impersonate developer workflow SA |
| **Developer Workflow** | `sa-secret-reader-prod` | `roles/bigquery.user`<br/>`roles/bigquery.dataEditor`<br/>`roles/storage.objectViewer`<br/>`roles/serviceusage.serviceUsageConsumer` | dbt builds + ad-hoc queries |
| **Data Pipeline** | `sa-data-pipeline-prod` | `roles/storage.objectCreator`<br/>`roles/bigquery.dataEditor`<br/>`roles/bigquery.jobUser` | IBGE/BCB ingestion |
| **Web Dashboard (Cloud Run)** | `sa-web-dashboard-prod` | `roles/bigquery.dataViewer` **on `serving`**<br/>`roles/bigquery.dataEditor` **on `research_inputs`**<br/>`roles/bigquery.jobUser` (project) | Dataset-scoped: read marts, append curation log. NOT project-wide on Gold. Looker uses end-user OAuth, not this SA. |
| **AI Agent Admin** | `sa-ai-agent-admin-prod` | `roles/bigquery.dataViewer` (project, read-only)<br/>`roles/bigquery.jobUser` (project)<br/>`roles/bigquery.dataEditor` **on `ai_reports` sandbox only**<br/>`roles/storage.objectViewer`<br/>`roles/storage.objectCreator` | Read-only analysis; writes confined to a sandbox dataset (never Gold prod / curation log) + GCS reports |

## Common Commands

### List all service accounts
```bash
gcloud iam service-accounts list
```

### View service account details
```bash
gcloud iam service-accounts describe sa-data-pipeline-prod@embrapa-dashboard-commodities.iam.gserviceaccount.com
```

### List all IAM roles on a project
```bash
gcloud projects get-iam-policy embrapa-dashboard-commodities --flatten="bindings[].members" --format=table
```

### Check specific member's roles
```bash
gcloud projects get-iam-policy embrapa-dashboard-commodities \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:florenciaitalo@gmail.com" \
  --format=table(bindings.role)
```

### View recent audit logs
```bash
gcloud logging read "resource.type=gce_instance OR resource.type=bigquery_resource" \
  --limit=20 \
  --format=table(timestamp,protoPayload.methodName,protoPayload.authenticationInfo.principalEmail)
```

## Support

- **GCP Console:** https://console.cloud.google.com/iam-admin/serviceaccounts
- **Audit Logs:** https://console.cloud.google.com/logs
- **gcloud reference:** https://cloud.google.com/sdk/gcloud/reference/iam
- **IAM Roles:** https://cloud.google.com/iam/docs/understanding-roles

## Next Steps

1. **Admin:** Complete all steps in this guide
2. **Admin:** Share `scripts/setup_dev_env.py` and `auth_architecture.md` with developers
3. **Developers:** Run `python3 scripts/setup_dev_env.py`
4. **Everyone:** Review audit logs quarterly
