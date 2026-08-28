# Deep audit — v1.6.0 (post-release)

> ⚠️ **HISTÓRICO — relatório pontual, não é uma lista de pendências.** Auditoria de 2026-06-24, sobre a v1.6.0 (pós-release), muito anterior ao estado atual do repositório. Seus achados foram tratados na época (veja o `CHANGELOG`); trate caminhos, contagens e estrutura aqui como o retrato daquela data, **não** como o código de hoje. Mantido por proveniência — em especial os achados refutados, que não existem em nenhum outro lugar.

**Date:** 2026-06-24
**Scope:** full codebase at `v1.6.0` (commit `f141d0f`), with extra scrutiny on the v1.6.0
changes: the in-app **feedback channel** (+ GitHub loop), the **Curadoria freeze**, the
**dev-server fix** (classic JSX runtime), and the **roadmap docs migration**.

**Method (honest note).** A 12-dimension multi-agent adversarial workflow was run
(finders per dimension → 3 independent skeptics per finding, majority-refutation gate →
synthesis). The formal verify/synthesis stages were repeatedly throttled by **transient
API rate limits + a session-quota reset** mid-run, so the machine-verified pipeline did
not complete. What *did* land: wave-1 finders (security / feedback-feature /
correctness-backend → 16 raised findings) and the **completeness critic**, whose concrete,
v1.6.0-focused leads were then **verified by hand** against the cited code. This report is
therefore a hybrid — workflow-seeded, human-verified — and is deliberately conservative
(only findings confirmed by reading the actual code are listed).

---

> **Remediation status (2026-06-24):** all confirmed findings below were **FIXED** on branch
> `claude/audit-v1.6.0-remediation` — see CHANGELOG `[Unreleased]`. Verified: 915 pytest /
> 267 vitest green; ruff / eslint / vite-build clean; `deploy.sh` syntax OK. (DATA-1 remains
> operator-owed: a live `dbt build` grain re-check, not runnable from the sandbox.)

## Executive summary

**Health grade: A−.** The baseline remains excellent (prior audits A−/A, 0 critical, ~96%
backend coverage) and nothing here is critical or exploitable: the new `/api/feedback`
surface is IAP-gated, parameterized, and input-validated. The v1.6.0 work introduced a
small cluster of real issues — **one HIGH operational trap** (a routine redeploy silently
disables the GitHub loop) plus medium/low polish items concentrated in the feedback feature
and the curation freeze.

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 1 |
| Medium | 4 |
| Low | 3 |
| Info | 2 |

**Most important finding:** `INFRA-1` — `deploy/webapi/deploy.sh` will **wipe** the feedback
GitHub-loop activation on the next routine deploy (the env allowlist omits
`FEEDBACK_GITHUB_REPO` and the script never re-mounts the `FEEDBACK_GITHUB_TOKEN` secret).

---

## Findings

### 🔴 HIGH

#### INFRA-1 — `deploy.sh` silently disables the feedback GitHub loop on redeploy
- **Dimension:** infra-ci-deploy · **File:** `deploy/webapi/deploy.sh:120,145-148`
- **What/why:** the deploy builds the Cloud Run env from an explicit allowlist —
  `WEBAPI_ALLOWLIST='^(GCP_PROJECT_ID|BQ_LOCATION|CACHE_[A-Z0-9_]+|IAP_AUDIENCE|COMTRADE_BRAZIL_ISO|CURATION_ALLOWED_EMAILS|BQ_MAX_BYTES_BILLED)='`
  — and deploys with `--env-vars-file "$ENV_YAML"`, which **replaces** the service env.
  `FEEDBACK_GITHUB_REPO` is not in the allowlist, and the script has **no `--set-secrets`**
  for `FEEDBACK_GITHUB_TOKEN`. The loop was activated out-of-band
  (`gcloud run services update --update-secrets …`), so the next `make webapi-deploy` /
  `deploy.sh` run drops **both** the repo env var and the token secret mount → the loop
  silently degrades to BigQuery-only, with no warning.
- **Suggested fix:** add `FEEDBACK_GITHUB_REPO` to `WEBAPI_ALLOWLIST`, and append a
  conditional `--set-secrets FEEDBACK_GITHUB_TOKEN=feedback-github-token:latest` to the
  `gcloud run deploy` (only when the secret exists). Until then, document loudly in the
  runbook that `FEEDBACK_*` must be re-applied after any `deploy.sh` run.

### 🟠 MEDIUM

#### FB-1 — GitHub issue is opened *before* the durable BigQuery write (orphan risk + wrong docstring)
- **Dimension:** feedback-feature / correctness-backend · **File:** `src/embrapa_dashboard/serving/feedback.py:189-221` (docstring `:110-112`)
- **What/why:** `record_feedback` calls `_forward_to_github` at line 191, then the BigQuery
  `INSERT` at line 221. If the INSERT fails after the issue is created, you get an **orphan
  GitHub issue with no `feedback_log` row**. The `_forward_to_github` docstring claims
  "*logged, never raised — the feedback is already safe in BigQuery*", but at call time the
  write has **not** happened yet — the ordering is reversed.
- **Suggested fix:** do the BigQuery INSERT first, then forward to GitHub, then (optionally)
  a second cheap UPDATE to stamp `issue_url`; or at minimum correct the docstring and accept
  the ordering. The current order makes the misleading docstring the real bug.

#### FREEZE-1 — Curadoria freeze is incomplete (residual entry points + glossary)
- **Dimension:** curation-freeze · **Files:** `frontend/src/ui/MainScreen.jsx:40`,
  `frontend/src/ui/glossary.js:129-143`, `src/embrapa_dashboard/webapi/routes.py` (curation block)
- **What/why:** the freeze hid the nav/sidebar, but: (1) `MainScreen` still routes
  `infoPage === 'curation' | 'enrich_industrial' | 'enrich_market'` to the editor, so a
  stale `?ip=curation` **deep link still renders the (frozen) editor**; (2) `glossary.js`
  still ships a full `curadoria:` section (8 terms) visible to users; (3) the frozen backend
  routes (`/api/cross/value-added`, `/cross/market-nature`, `/curation/*`) remain registered
  and reachable. Decoupling at the data layer is sound (dbt gated, reads degrade), but the
  feature is not fully *hidden*.
- **Suggested fix:** route the frozen `infoPage` values to a neutral "indisponível /
  Versão Futura" screen instead of the editor; hide or remove the `curadoria` glossary
  section while frozen. (Backend routes can stay as tested scaffold — low risk.)

#### DEV-1 — dev vs prod JSX-runtime divergence is untested
- **Dimension:** dev-server-fix · **File:** `frontend/vite.config.js`
- **What/why:** the dev server now uses the **classic** JSX runtime
  (`command === 'serve' && !process.env.VITEST`) while **build + Vitest** use **automatic**.
  So tests and the production bundle exercise a different JSX-compilation path than what a
  developer sees in `npm run dev`. A regression in either path's global-`window.React`
  resolution would pass CI yet break dev (or vice-versa) with no test to catch it.
- **Suggested fix:** add one smoke test (or a CI step) that boots the **dev** server and
  asserts the app renders (non-empty `#root`), closing the dev-only gap; document the
  divergence in `vite.config.js`.

#### TEST-1 — the GitHub-forward success path has zero coverage
- **Dimension:** tests-coverage · **File:** `tests/test_webapi_feedback.py:70-83`
- **What/why:** only `test_forward_to_github_is_noop_without_config` exists. The actual
  forwarding — title/body construction, `requests.post`, `raise_for_status`, `html_url`
  parse, the `issue_url` round-trip into the row, and the exception-swallow — is **never
  tested**. The headline v1.6.0 feature's most failure-prone branch is unguarded.
- **Suggested fix:** add a test that monkeypatches `requests.post` (success + raising) and
  asserts the returned `issue_url` and the swallow-on-failure behaviour.

### 🟡 LOW

#### SEC-1 — user message is interpolated raw into the GitHub issue (markdown/mention injection)
- **File:** `src/embrapa_dashboard/serving/feedback.py:119-137`
- **What/why:** `message` flows verbatim into the issue `title` and `body` (GitHub renders
  body as Markdown), so a reporter can inject Markdown, fake the "Aberto automaticamente"
  footer, or embed `@mentions`/links. **Low** because authors are IAP-gated trusted
  researchers writing into the project's own repo. **Suggested fix:** wrap the user message
  in a fenced block / prefix lines, and strip leading `@`.

#### SEC-2 — no rate-limit / abuse guard on `/api/feedback`
- **File:** `src/embrapa_dashboard/webapi/routes.py` (the `/feedback` route)
- **What/why:** each call issues a BigQuery DML INSERT **and** an outbound GitHub API call;
  there is no per-user throttle (only `MAX_CONTENT_LENGTH` caps body size). A loop could
  create unbounded issues + DML jobs. **Low** (IAP-gated, small audience). **Suggested fix:**
  a lightweight per-author cooldown (e.g., cache-based N/min) if abuse ever appears.

#### DOC-1 — no docs entry for the feedback secret wiring / token scope
- **Files:** `.env.example:283-290`, `docs/operations_runbook.md`
- **What/why:** the runbook documents curators/backups but not the `FEEDBACK_GITHUB_*`
  Secret Manager setup; `.env.example` gives no guidance that the token should be a
  **fine-grained `issues:write`** token (not a broad PAT). **Suggested fix:** add a short
  runbook section (the Secret Manager + `--update-secrets` recipe + the token-scope note).

### ℹ️ INFO

- **DATA-1 (owed):** the CHANGELOG "Fixed" claims for `commodity_crosswalk` `'ppm'` +
  `comtrade_cpc_value` breakdown pins were validated only via `dbt compile`, not a live
  `dbt build`. A `bigquery-debug` round should confirm `gold_*` grain uniqueness on prod
  (sandbox has no `*.googleapis.com` network, so this could not be checked here).
- **DATA-2 (resolved):** `feedback_log` materialization was flagged as unverified, but the
  end-to-end prod test already created **and** queried the row (with `issue_url` populated) —
  the table + dataset materialize correctly. No action.

---

## Dimensions that came back clean (no confirmed findings)

`correctness-frontend`, `ingestion`, `architecture-maintainability`, and the
`data-dbt` grain/conservation checks surfaced no confirmed code-level defects in the
machine pass; `correctness-backend` (deflation/FX/parameterized SQL) was clean apart from
`FB-1`. (Caveat: several of these dimensions' verify stages were cut short by the rate-limit
— treat "clean" as "no issue surfaced", not "exhaustively proven".)

---

## Prioritized remediation plan

- **P0 (do first):** `INFRA-1` — make `deploy.sh` preserve/re-apply `FEEDBACK_GITHUB_REPO` +
  the token secret (a routine redeploy currently disables the loop).
- **P1:** `FB-1` (write-before-forward + fix docstring), `FREEZE-1` (route frozen deep links
  to a neutral screen; hide the curadoria glossary), `TEST-1` (cover the GitHub-forward
  success path).
- **P2:** `DEV-1` (dev-boot smoke test for the JSX-runtime divergence), `DOC-1` (runbook +
  `.env.example` secret guidance).
- **P3:** `SEC-1` (sanitize message → issue), `SEC-2` (optional rate-limit), `DATA-1` (live
  `dbt build` grain re-check by the operator).
