# Quality Audit — 2026-06-22

> ⚠️ **HISTÓRICO — relatório pontual, não é uma lista de pendências.** Auditoria de 2026-06-22, muito anterior ao estado atual do repositório. Seus achados foram tratados na época (veja o `CHANGELOG`); trate caminhos, contagens e estrutura aqui como o retrato daquela data, **não** como o código de hoje. Mantido por proveniência — em especial os achados refutados, que não existem em nenhum outro lugar.

**Scope:** repository hygiene · codebase quality · cloud infrastructure (infrastructure-as-code).
**Question asked:** *are the repo, the codebase, and the cloud infra following high quality standards?*
**Verdict:** **Yes, across all three.** 0 critical / 0 high. 2 MEDIUM (both narrow, both with a clean minimal fix), 9 LOW (mostly docs/ops/supply-chain hardening). The security core was re-confirmed clean for the Nth audit running.

> **Remediation (2026-06-22):** all 11 findings were fixed in branch `claude/sweet-fermi-1948aa` — see CHANGELOG `[Unreleased]`. Verified green locally: **872 pytest + 231 vitest + ESLint + `ruff`/`ruff format`/C90 + `npm run build`** all pass; the behavior-pinning tests (3 `reconcile`, 1 comtrade-quota) were updated and an M2 regression test added (`test_geo_yearly_*flow*`).

## Method

- **Static baseline (measured, not estimated):** `ruff check` + `ruff format` clean; `ruff C90` (max-complexity 10) clean — no function over CC 10; `radon cc` average **A (3.15)** over 502 blocks; `radon mi` grade **A** for every module; no secrets/keys/parquet/large binaries tracked; conventional-commit history (230 commits); GitHub Actions SHA-pinned with Dependabot.
- **Adversarial fan-out:** a 13-dimension multi-agent audit (47 agents) read the actual source / dbt SQL / IaC, then **every consequential finding was re-verified against the cited code** before inclusion. Two false positives were caught and discarded (see *Refuted* below).
- **Environment limits (honest):** the audit sandbox cannot execute `pytest`/`npm`/`gcloud`/`dbt build` (Application Control + no `*.googleapis.com` network), so test-suite execution and live-cloud calls are out of scope — this is a **static + IaC** audit. Test *quality* was assessed by reading all 33 pytest files + a representative set of the 35 vitest files; prior runs (827 pytest / 193 vitest green, ~94% backend coverage) are unchanged on this branch.

## Dimension scorecard

| # | Dimension | Verdict |
|---|-----------|---------|
| R1 | Repo — git hygiene & structure | 🟢 good |
| R2 | Repo — CI/CD & supply chain | 🟢 excellent |
| R3 | Repo — docs accuracy & freshness | 🟢 good |
| R4 | Repo — dependency management | 🟢 excellent |
| C1 | Code — backend architecture | 🟢 excellent |
| C2 | Code — ingestion pipelines | 🟢 good |
| C3 | Code — application security | 🟢 excellent |
| C4 | Code — test suite | 🟢 excellent |
| C5 | Code — frontend (React SPA) | 🟢 good |
| C6 | Code — dbt medallion transforms | 🟢 excellent |
| I1 | Infra — Cloud Run deploy & container | 🟢 good |
| I2 | Infra — IAM / WIF / secrets | 🟢 good |
| I3 | Infra — cost safety & ops resilience | 🟢 excellent |

**Bucket rollup:** Repository **strong** · Codebase **excellent** · Cloud infra **strong**.

---

## Findings (verified)

### MEDIUM

**M1 — `reconcile` does not cover the PAM/PPM SIDRA sources.** `code/ingestion`
`reconcile` is the documented escape hatch that catches an upstream *correction to an old year* (which the nightly delta never re-queries). But `_reconcile_full_sources` skips any spec where `not spec.in_all` ([cli.py:698-700](src/embrapa_dashboard/cli.py)), and both PAM and PPM are registered `in_all=False` ([cli.py:86,90](src/embrapa_dashboard/cli.py)); `_reconcile_ibge` re-runs only PEVS. So an old-year revision to **PPM (live in prod)** or PAM would never be caught by `reconcile`, and the only manual remediation is the deadline-fragile **single-shot** `ingest ibge-ppm --full` (not year-chunked like the PEVS reconcile path) — the exact slow-SIDRA failure mode that PR #148 had to fix for the PPM backfill.
*Fix:* add a chunked PAM/PPM phase to `reconcile` (mirror `_reconcile_ibge`'s `_ibge_batch_ingest` chunking), or, if intentional, document the limitation and ship a chunked `--full` path for PAM/PPM. The docstring's "full re-download of every *nightly* source" is technically accurate (PAM/PPM run on their own monthly schedulers), but those monthly runs are *also* delta — so there is currently **no** path, automated or chunked-manual, that catches an old-year PAM/PPM revision.

**M2 — Geography view shows all-flows totals for a COMEX product basket when a flow direction is active.** `code/frontend + webapi`
The single-product **snapshot** path threads the active `flow` filter end-to-end, but the **basket-scoped geo-yearly cube** path drops it:
- `window.geoYearly` omits `flow` from both its cache key and query string ([producers.js:101-120](frontend/src/data/producers.js)),
- `/geo-yearly` never reads a `flow` arg ([routes.py:262-277](src/embrapa_dashboard/webapi/routes.py)),
- `seam.geo_yearly()` doesn't extract/pass `flow`, so the gateway SUMs over every flow ([seam.py:421-433](src/embrapa_dashboard/webapi/seam.py)).

Result: with a COMEX (`mdic_comex`) **product basket** *and* a non-`all` **flow** (export/import) both active, the Geography "VALOR TOTAL" + choropleth show all-flows figures, internally inconsistent with the flow-filtered rest of the app. Narrow blast radius (COMEX is the one live geo+flow banco; default `flow='all'` and any non-basket view are unaffected), but it is a genuinely wrong displayed number.
*Fix (3 call sites, lower layers already support `flow`):* thread `flow` through `producers.js` `window.geoYearly` (cache key + querystring) → `/geo-yearly` (`request.args.get("flow")` into the summary) → `seam.geo_yearly()` (`_flow_from_summary` → `gateway.fetch_comex_by_uf_yearly(..., flow=flow)`; gateway+SQL already apply it at [sql.py:603](src/embrapa_dashboard/serving/sql.py)).

### LOW

**L1 — pre-commit ruff pin drifts from CI.** `repo/ci` — `.pre-commit-config.yaml` pins `ruff-pre-commit` to **v0.6.9** while the project/CI run the synced (current) ruff, and Dependabot has no pre-commit ecosystem entry, so the local hook can lint/format differently than CI. *Fix:* bump the `rev` to match the resolved ruff, and run `pre-commit autoupdate` periodically (or add a scheduled job — Dependabot has no native pre-commit updater).

**L2 — Container base images are tag-pinned, not digest-pinned.** `repo/deps + infra` — both Dockerfiles use floating `python:3.12-slim` / `node:22-slim` ([deploy/webapi/Dockerfile:17,26,42](deploy/webapi/Dockerfile), [deploy/ingestion/Dockerfile:13,32](deploy/ingestion/Dockerfile)) and `dependabot.yml` has no `docker` ecosystem entry, so the build is not byte-reproducible and a base-image CVE bump isn't surfaced. *Fix:* pin to `@sha256:` digests and add a `docker` Dependabot updater.

**L3 — Package version strings are stale (cosmetic).** `repo/docs` — `pyproject.toml:3` is `version = "1.0.0"` and `src/embrapa_dashboard/__init__.py:3` is `__version__ = "0.1.0"`, while releases are at **v1.5.1**. Verified harmless: nothing reads either string at runtime, the README has no version badge, and deploy/release tags come from git (`deploy.sh` uses `git rev-parse`, `release.yml` uses `GITHUB_REF_NAME`) — fully decoupled. *Fix:* bump both to `1.5.1` or wire `__version__` to `importlib.metadata.version`. (CHANGELOG is **correct** — complete and newest-first through v1.5.1.)

**L4 — PPM (v1.3.0) missing from several enumerative docs.** `repo/docs` — the user-facing docs (README, `gold_data_model.md`, `.env.example`) correctly list PPM, but these enumerate PAM and forgot PPM: `ARCHITECTURE.md` folder tree ([:121](ARCHITECTURE.md)), dbt-model tree ([:147,:156,:170](ARCHITECTURE.md)), form list ([:337](ARCHITECTURE.md)), scheduler box ([:617-622](ARCHITECTURE.md)); the `doctor` sample output in [docs/testing.md:76-78](docs/testing.md); the dataset list in [docs/ownership_transfer.md:17](docs/ownership_transfer.md) (omits `bronze_ppm`); and the `pyproject.toml:4` description string.

**L5 — `IAP_AUDIENCE` env-replace footgun on redeploy.** `infra/deploy` — `deploy/webapi/deploy.sh` deploys with `--env-vars-file` (full env *replace*) and only **warns** (doesn't fail) when `IAP_AUDIENCE` is absent ([deploy.sh:128-132](deploy/webapi/deploy.sh)). A deployer whose `.env` lacks it (e.g. a worktree `.env`) would silently drop the in-app IAP JWT double-check. Platform IAP still enforces auth, so this is defense-in-depth only, and the team already mitigates via image-only redeploys — worth promoting to a documented checklist item / optional hard-fail flag.

**L6 — Comtrade quota-exit produces a false-positive failure alert.** `infra/ops` — the UN Comtrade backfill exits non-zero on quota exhaustion on the same Job the Cloud Monitoring failure policy watches, so every monthly backfill run pages falsely. Known; self-resolves at steady state. *Fix:* treat the quota-exit code as success, or snooze the policy during backfill.

**L7 — One long-lived SA JSON key + SA-grant doc drift.** `infra/iam` — the Claude Code Web SA uses a long-lived JSON key (acknowledged; scoped read-only + a single write sandbox), the lone non-keyless credential against an otherwise all-WIF posture; plus minor documentation drift on two SA grants. *Fix:* note the key as the one accepted exception and add a rotation reminder; reconcile the grant docs with `grant_least_privilege.sh`.

**L8 — Minor dbt + backend doc/coverage gaps.** `code/dbt + backend` — an operational doc gap on incremental seed-change propagation and a curation-warn coverage gap (C6), and a single cache-TTL consistency nit in the serving layer (C1) — none corrupts a displayed number or a security boundary today; listed for completeness.

---

## Refuted (false positives caught by verification)

- **"Flow filter is URL-only, not in the FilterMenu."** It *is* a functional FilterMenu segmented control ([FilterMenu.jsx:382,502,750-774](frontend/src/ui/FilterMenu.jsx)); the `fx` URL param is just deep-link persistence. The M2 fix above is the real residue.
- **"CHANGELOG trails the git tags."** It does not — it is complete and newest-first through v1.5.1 ([CHANGELOG.md:10-16](CHANGELOG.md)).

---

## What's genuinely strong (don't regress these)

- **Security model:** systematic SQLi defense (bound params + identifier allowlists, incl. schema-as-allowlist for the raw-table inspector), **fail-closed** IAP author capture (refuses to trust the plaintext header on Cloud Run without `IAP_AUDIENCE`; verifies JWT sig/aud/iss/email), two-layer curator authorization, `maximum_bytes_billed` on every read path. Re-confirmed clean.
- **CI/CD & supply chain:** every action SHA-pinned + Dependabot-bumped, keyless WIF scoped to this repo, injection-safe release input handling, least-privilege workflow permissions, reproducibility-gated (`uv sync --frozen` / `npm ci`).
- **Deploy hardening:** `deploy.sh` asserts the *end state* — hard-fails on `invoker-iam-disabled=true` and `iap-enabled!=true`, warns on `allUsers`; non-root multi-stage images; scale-to-zero / max-instances cost caps.
- **dbt correctness:** deflation/FX pinned by a worked-number unit test plus magnitude *and* coverage guards; three-tier conservation tests catch post-`GROUP BY` fan-out; grain uniqueness on every gold/serving table; `measure_kind` stock/flow handled so quantities never sum across families.
- **Ingestion resilience:** volume-scaled SIDRA drain + full-jitter backoff that bounds correctly, period-halving only on cell-limit (never slow-byte), idempotent Bronze + two-phase raw-zone resume markers.

## Suggested order of work

1. **M2** (wrong displayed number; small, well-scoped 3-call-site fix).
2. **M1** (silent data-staleness risk on a live source).
3. **L4 + L3** (doc/version freshness — cheap, batchable).
4. **L1 + L2** (supply-chain hardening — batchable).
5. **L5–L8** (ops/IAM hardening + nits as capacity allows).
