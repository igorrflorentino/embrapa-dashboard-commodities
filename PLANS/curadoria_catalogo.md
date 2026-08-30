# PLANS — Curadoria (catalog) + Engenharia de Atributos split, editable catalog, orphan lifecycle, seed consultation

> **⚠ SUPERSEDED IN PART (v1.10.0, 2026-07): `code_prefix` was ELIMINATED.** Every commodity is now
> registered by its **EXACT source code** (`codigo_produto`), one at a time. This was
> behavior-preserving: after the v1.9.5 catalog import every entry's `code_prefix` already equalled
> its exact leaf code, so the `LIKE code_prefix||'%'` bridge and the exact `= code` join produce the
> same rows. Consequently, wherever this doc says "keep `code_prefix`", "prefix-disjointness", or
> "`LIKE code_prefix||'%'`", read **exact-code equality (`= code`)** instead. The physical
> `research_inputs.produto_catalog_log.code_prefix` column is dropped (operator DDL). The add form
> now hard-blocks a code that doesn't exist in the source's Gold, and the catalog shows each
> commodity's Gold state (linhas / período / tem-dados). Rationale below is otherwise unchanged.

> Status: **COMPLETE** (2026-06) — P0–P5 all implemented, tested, and live-verified on prod
> BigQuery (941 pytest / 273 vitest). Owner: Igor. Supersedes the rejected Google-Sheets
> "Contrato de Dados" source-of-truth proposal — the editing surface is an **in-dashboard admin UI
> writing to BigQuery `research_inputs`**, NOT a Sheet.
>
> **Manual operator follow-ups** (the agent deliberately did NOT do these — they touch prod
> destructively or are deploy-time): (1) drop the now-unreferenced `silver.commodity_crosswalk`
> table (the retired seed — kept inert; `DROP TABLE` is an operator call); (2) deploy the webapi
> so the new "Cadastro de produtos agrícolas" / "Referências" views go live; (3) populate
> `research_inputs.catalog_editors` (resource `produto_catalog`) with the authorized researcher
> emails (empty = open to any IAP user); (4) set the `DBT_BUILD` repo vars so the workflow's new
> `mark-orphans` step runs. The deferred BQ-table renames (#5) were evaluated and **declined** —
> the table names (`code_industrialization_log`, `flow_market_log`, `curators`, `banco_metadata`,
> `produto_catalog_log`, `catalog_editors`, `catalog_lifecycle_log`) are already accurate, and
> cross-dataset renames of append-only audit tables are pure churn/risk.

## Guiding decisions (from the project lead)

1. **In-dashboard admin UI → `research_inputs`** (not a Google Sheet). Reuses the existing
   operator-editable patterns (`banco_metadata` read path; the append-only writer + IAP author
   capture; the per-resource allowlist).
2. **No automatic deletion.** The dashboard auto-detects orphans and auto-marks them
   **`Descontinuado` with a deletion warning**, but the physical delete waits for a **human**
   (operator CLI, backup-first). Auto-detect + auto-mark + warn = automatic; delete = human-gated.
3. **Orphan definition (lead's words):** an element (banco or commodity) **available for
   consultation in the dashboard** (present in Gold) but **absent from the cadastro seed**
   (`cadastro_bancos` / `cadastro_produtos`). Each cadastro seed has its **own authorization
   list**. Authorized editors of a cadastro define what enters/exits. → orphan = `Gold − catalog`.
4. **Not all seeds are editable.** High-precision **calibration** seeds stay version-controlled and
   engineer-only. Read-only seeds are **displayed in the dashboard** so researchers can consult +
   confirm values and **report errors** via the existing feedback channel (no edit rights).
5. **`commodity_crosswalk` redundancy: CONFIRMED.** It is derivable from the catalog
   (`agrupamento_nome ≡ Agrupamento`, `source ≡ Banco`, `code_prefix` is a prefix of the code).
   It becomes the editable catalog, **prioritizing the "Cadastro de Commodities" column structure**.
6. **No backward-compat / no fallback to the old way.** Project is beta, no users. Prefer maximum
   cleanliness. A clean cutover: if the new path errors it must **fail loud**, never silently fall
   back to the old behaviour (that would make the project deceptive). BQ **table renames are
   deferred to a final cleanup phase** (after everything is built + tested).

## The 3-way conceptual split (nomenclature)

| Concern | English id | pt-BR (UI) | What it is |
|---|---|---|---|
| **A. Curadoria (catalog)** | `curation` | Curadoria | *what enters/exits* — bancos + produtos agrícolas membership, lifecycle (Beta→…→Descontinuado), orphan flow. **Net-new.** |
| **B. Engenharia de Atributos** | `attribute_engineering` | Engenharia de atributos | *new derived columns from researcher input* — per-code industrialization (`code_industrialization_log`) + (customs×flow)→market-nature (`flow_market_log`). **= today's frozen "Curadoria" code.** |
| **C. Shared infra** | `research_inputs` | (none — infra) | append-only writer + IAP author capture + per-resource allowlist + `ensure_*_table` + `change_id` idempotency + cache invalidation. Common to A and B. |

**BQ tables keep their current names during the build** (`code_industrialization_log`,
`flow_market_log`, `curators`, `banco_metadata`, dataset `research_inputs`); renames happen in the
final cleanup phase. The reorg is otherwise **code-only, zero data migration**.

## commodity_crosswalk → editable catalog

- Target: `research_inputs.produto_catalog`, key `(codigo_produto, banco, tabela)` — a tabela SIDRA entra na chave desde 2026-08-29 (v1.39.0), porque PEVS e PPM unem duas tabelas sob um token de banco só; ver `docs/migration_history.md`, columns prioritizing
  Cadastro: `codigo_produto, banco, agrupamento, descricao_produto, industrializacao,
  ciclo_de_vida` + stored `agrupamento_id` slug + explicit **`code_prefix`** (kept — coarse prefixes
  are deliberate auto-absorb, NOT lossy). Edit grain for the in/out flag = **per Agrupamento**
  (store rows per `(banco, code)` underneath).
- **Two correctness properties to preserve:** keep `code_prefix` (don't switch the join to `=`);
  **validate prefix-disjointness on write** (overlapping prefixes silently double sums — today only
  `unique_combination_of_columns(source, code)` catches it at build).
- `gold_produto_agrupamento.sql` rebuilt to read the catalog (filtered to the "available" Ciclo de
  Vida) keeping the `LIKE code_prefix||'%'` expansion. The PAM/PPM inline path in
  `serving_{pam,ppm}_annual.sql` migrates **together**. 3 consumers traced: gold_produto_agrupamento;
  serving_pam/ppm_annual inline; `seam_base.produto_catalog()`→`/api/catalog` + `seam_cross._codes`.

## Orphan / Descontinuado lifecycle

- **Orphan = `Gold − catalog`** (D3). `Gold − catalog` (data exists, not in cadastro) → **Descontinuado**
  + deletion warning. `catalog − Gold` (registered, no data) → a *distinct* "Sem dados / aguardando
  ingestão", **never** Descontinuado.
- Detection on the **`dbt-build-prod` boundary** (status only changes when Gold or catalog change —
  no new scheduler) + a soft-warn `doctor` check. Append-only `research_inputs.catalog_lifecycle_log`.
  Auto-mark author = reserved `system:orphan-detector`.
- **Hide-not-delete** at the catalog/seam boundary; data stays in Gold, visible in the admin/orphan view.
- Human purge = `embrapa purge-orphan` CLI: backup-freshness-gated, prints the scoped parameterized
  `DELETE` (the hooks block `bq rm` for the agent), appends a terminal `purged` audit row.

## Seed editability + read-only viewer

- **Editable (authorized researcher):** the catalog (`produto_catalog`, `cadastro_bancos`),
  `banco_metadata`. **Read-only (engineer-only):** `historical_currency_factors`,
  `unit_family_conversions`, `product_unit_factors`, `comex_*`/`comtrade_*` dims + succession maps,
  `ibge_municipio_mesh` (calibration / source-faithful / script-regenerated).
- Read-only viewer = a new **"Referências"** view. NOT via the `Dados` `_INSPECT_TABLES` path
  (banco-scoped + billed): a new `_SEED_CATALOG` registry + `GET /api/seeds` (free metadata) +
  `GET /api/seed?id=` via `client.list_rows()` (zero bytes billed; seeds ≤5570 rows), reusing the
  `Dados` grid read-only + a `_seeds.yml`-description panel.
- Error reporting reuses the shipped feedback channel (`POST /api/feedback`) with a prefilled
  `[Seed: …] Linha: … Valor suspeito: …` — no edit rights granted.

## Phased plan

- **P0 — Nomenclature reorg** (code-only, no behaviour change). Split `serving/curation.py` →
  `serving/research_inputs.py` (C) + `serving/attribute_engineering.py` (B); rename
  `webapi/seam_curation.py` → `webapi/seam_attribute_engineering.py`; update `seam.py`, `routes.py`,
  tests. Free `curation`/"Curadoria"/`/api/curation/*` for the catalog. **No re-export shim** (clean
  cutover, #6). Verify: ruff + pytest + vitest.
- **P1 — Read-only seed viewer + feedback prefill** (MVP, zero write risk). `_SEED_CATALOG` + 2
  endpoints + "Referências" view + per-row "Reportar valor incorreto".
- **P2 — Editable commodity catalog** (core). `research_inputs.produto_catalog` (+ log) via
  `ensure_*_table`; backfill + diff-gated cutover; rebuild `gold_produto_agrupamento`; migrate
  PAM/PPM; admin write endpoints + per-catalog allowlist + on-write prefix-disjointness validation.
- **P3 — Orphan / Descontinuado lifecycle** (builds on P2 catalog). `catalog_lifecycle_log` +
  `fetch_orphans()` + `auto_mark_orphans()` on the build boundary + `doctor` check + orphan API +
  source-meta overlay + hide-not-delete.
- **P4 — Human-gated purge CLI** (last; the only destructive surface). `embrapa purge-orphan`,
  backup-gated, prints scoped DELETE, appends audit row.
- **P5 — Final cleanup renames** (BQ tables, `enable_curation` var, lazy `/api/attributes/*`).

## Sandbox verification matrix

- Runnable here: `ruff`, `pytest`, `vitest`, `eslint`, `sqlfluff`, `vite build`, `dbt parse`.
- **Operator-only** (no `*.googleapis.com` from the sandbox): `dbt build` / `dbt test` against
  BigQuery, deploy, live preview. These steps are flagged in the per-phase notes for Igor to run.
- Windows: prefix dbt with `PYTHONUTF8=1`.
