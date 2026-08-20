# deploy/webapi — React SPA + Flask REST Cloud Run Service

The Dash→React migration's deploy target. Serves the built React SPA **and** the
`/api` JSON endpoints from one origin (one service, one IAP, no CORS) via
gunicorn → `embrapa_dashboard.webapi.app:app`.

Replaces the Dash image (`deploy/dashboard/`) **in place** at cutover: the
`deploy.sh` defaults to the same service (`embrapa-dashboard`), the same runtime
SA (`sa-web-dashboard-prod`), and the same PRIVATE + IAP posture. The service URL
and IAP grants are unchanged — only the served app changes.

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | 3-stage build: node (build `frontend/dist`) → uv (`--extra webapi`) → runtime (gunicorn + `SPA_DIST_DIR`) |
| `cloudbuild.yaml` | Cloud Build config (explicit Dockerfile path, repo-root context) |
| `deploy.sh` | Build via Cloud Build + `gcloud run deploy` (private), env allowlist, prod datasets forced. `WEBAPI_SKIP_BUILD=1` deploys a pre-built image instead of rebuilding |

## Deploy

```bash
make webapi-deploy          # or: bash deploy/webapi/deploy.sh
```

Builds from source (Cloud Build) and deploys. Prereqs: gcloud authenticated;
`run`/`cloudbuild`/`artifactregistry` APIs enabled; the runtime SA provisioned
(`make iam-grant`). The build needs `frontend/package-lock.json` (committed) for `npm ci`.

## Releases — build once (CI), deploy later (no rebuild)

`.github/workflows/release.yml` decouples **build** from **deploy**: it bakes a
versioned, immutable image into Artifact Registry on every release, so a later
deploy is just pointing Cloud Run at that tag — no rebuild.

**Cut a release** (builds + pushes `…/embrapa-dashboard:vX.Y.Z` + `:latest`, then
creates the GitHub Release whose body is the curated `CHANGELOG.md` `## [vX.Y.Z]`
section + the deployable-image ref + an auto-generated PR appendix — so add the
version's CHANGELOG entry before tagging):

```bash
git tag v1.2.3 && git push origin v1.2.3      # or publish a Release in the GitHub UI
```

(`workflow_dispatch` on the "Release image" workflow builds an ad-hoc tag too —
no `:latest`, no Release.)

**Deploy that pre-built image** (skips the build, verifies the tag exists, deploys):

```bash
WEBAPI_SKIP_BUILD=1 WEBAPI_TAG=v1.2.3 bash deploy/webapi/deploy.sh
```

One-time GCP setup (a least-privilege release SA with Artifact Registry write,
bound to the existing WIF pool) is documented in the header of `release.yml`.
It reuses the `GCP_PROJECT_ID` / `GCP_WIF_PROVIDER` repo vars from
`dbt-build-prod.yml` and adds `GCP_RELEASE_SERVICE_ACCOUNT`.

## Keeping the deployed image current (CI auto-deploy)

`make webapi-deploy` is the **operator** path — run it when the Service's **env**
must change. Nothing about it is automatic, and that asymmetry caused a real outage
on 2026-08-20: dbt changes reach production the moment a build runs, Service changes
only on a manual deploy. A single PR touched both — it added `pam`/`ppm` rows to
`gold_produto_agrupamento` *and* taught `seam_base.produto_catalog` to handle them —
but only the dbt half landed. The Service, still on the previous image, indexed a
hardcoded `pevs/comex/comtrade` bucket dict as `c[r.source]`, so the first `pam` row
raised `KeyError` and every cross-source view 500'd. The fix was in the same PR that
broke it.

`.github/workflows/webapi-deploy.yml` closes that window: on every merge to `main`
touching `src/embrapa_dashboard/**`, `frontend/**`, `pyproject.toml`, `uv.lock` or
`deploy/webapi/**`, CI rebuilds the image and points the Service at it with a
**surgical `gcloud run services update --image`** — only the image changes, so env,
the `FEEDBACK_GITHUB_TOKEN` secret ref, the runtime SA, scaling and the IAP
annotations all persist. It then reads the Service back and fails if the image, any
critical env var, or `iap-enabled` did not survive.

The image is tagged with the commit's short SHA, so "which commit is prod serving?"
is answerable from the console — the drift above was invisible precisely because it
was not.

Requires the one-time GCP setup in that workflow's header (a dedicated
`sa-webapi-deploy-ci` identity + the `GCP_WEBAPI_DEPLOY_SERVICE_ACCOUNT` repo
variable). **Until that variable is set the workflow skips**, so merging it changes
nothing; it activates by itself once the variable exists.

## Notes

- **No dash/plotly** in the image: the `webapi` extra is flask + flask-caching +
  gunicorn. The analytical charts are client-side Plotly.js in the SPA.
- **`SPA_DIST_DIR=/app/frontend/dist`** is baked into the image; Flask serves the
  SPA for non-`/api` routes (client-side deep-links resolve to `index.html`).
- Same Pushdown model: parameterized BigQuery via the serving BFF, memoized by
  flask-caching; `WEB_CONCURRENCY=1` keeps the per-instance SimpleCache coherent.
- The old Dash deploy (`deploy/dashboard/`) was removed at cutover.
