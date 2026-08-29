# Migration History

These are one-time migration notes from past schema changes. They are kept for historical reference only and are not part of the active development workflow.

## 2026-08-29 — A identidade de um produto ganhou a tabela SIDRA

**O quê.** A chave que identifica um produto na curadoria passou de `(banco, código)` para
`(banco, tabela, código)`, nos três registros: catálogo, gate de visibilidade e nível de
industrialização.

**Por quê.** PEVS e PPM unem DUAS tabelas SIDRA sob um token de banco só (extração t289 ×
silvicultura t291; rebanho 3939 × produção animal 74). Com a chave antiga, um código
presente nas duas metades seria um produto só: um agrupamento, uma visibilidade e um nível
cobrindo ambas, a tag da tela mostrando uma delas arbitrariamente, e a ingestão dirigida
pelo catálogo perdendo a metade não marcada em silêncio. O Gold já barrava o conflito de
dados (teste de unicidade `error` + `dbt build` pula downstream); era a curadoria que não
conseguia representá-lo.

**A armadilha da migração.** O log é append-only, e as linhas escritas antes de a coluna
`sidra_tabela` existir a têm NULL. Promover a coluna para dentro da chave transformaria
**supersessão em coexistência**: medido antes, a chave de 3 colunas dava **258** entradas
ativas onde a de 2 dava **234** — 24 fantasmas, 10 de `pevs` e 14 de `ppm`.

**O que foi feito** (`scripts/migrate_catalog_key_add_table.py`, ensaio por padrão):
1. `UPDATE` em **51** linhas históricas do catálogo, preenchendo `sidra_tabela` com o valor
   que a própria entrada já carrega. Completa uma coluna que era NULL *porque não existia
   quando a linha foi escrita* — nenhum valor decidido por um pesquisador mudou.
2. Coluna `sidra_tabela` adicionada aos logs de **nível** e de **ciclo de vida** (e às
   constantes de esquema, senão uma instalação nova criaria a tabela sem ela — furo que um
   teste pegou), com backfill derivado do catálogo: 24 classificações marcadas.
3. Depois: **234** com qualquer das duas chaves — migração neutra.

**Efeito colateral deliberado.** A tag passou a ser **obrigatória** em entrada nova nos dois
bancos multi-tabela. Sem ela a entrada não cai em nenhuma das metades: cai na sentinela
`sql.SEM_TABELA`, uma terceira identidade que não corresponde a dado nenhum.

**Bancos de uma tabela** (comex, comtrade, pam) não foram tocados: para eles a coluna não
carrega informação e o `ifnull` a colapsa na sentinela, então a chave nova é equivalente à
antiga.

---

## Bronze re-partitioning

Bronze tables are now partitioned by `DATE(ingestion_timestamp)` and clustered (IBGE: `municipio_codigo, ano, variavel_codigo`; BCB: `series_code, reference_date_str`). BigQuery cannot retrofit partitioning on existing tables — if you have pre-existing Bronze tables from before this change, drop them before the next `embrapa ingest *` run, otherwise the load job fails with a partition mismatch:

```bash
bq rm -f -t "${GCP_PROJECT_ID}:bronze_ibge.sidra_t289_raw"
bq rm -f -t "${GCP_PROJECT_ID}:bronze_bcb.inflation_series_raw"
bq rm -f -t "${GCP_PROJECT_ID}:bronze_bcb.currency_series_raw"
```

## Gold materialization

Changed from `incremental` to `table`. No action required — `dbt build` will recreate it cleanly. The Gold model now also has new columns (`reference_date`, `state_name`, `region`, `city_code`, `last_refresh`) and renamed columns (snake_case throughout). Looker Studio reports must rebind any deleted column names (`valnominalbrl` → `val_nominal_brl`, etc.).

## GCS bucket protections

Versioning and lifecycle rules are now applied idempotently on `ensure_bucket` — existing buckets are upgraded on the next run.

## `val_nominal_*` → `val_yearfx_*`

The 4 BRL/USD/EUR/CNY columns were renamed because "nominal" was misleading (Silver already converts everything to current BRL numerary via the currency reform seed). Looker Studio reports need to rebind the 4 metrics — see `docs/looker_studio_setup.md`.

## Gold table rename: `gold_commodity_matrix` → `gold_pevs_production` (2026-05-29)

Adopted the `gold_<source>_<form>` naming convention. The single PEVS Gold table
was renamed from `gold_commodity_matrix` to `gold_pevs_production` (`production` =
output-measurement grain). The dbt model file, `_gold.yml`, and the
`assert_gold_has_rows` test were updated; `dbt build` recreates the table under
the new name automatically.

Two manual cleanups outside this repo (dbt does NOT do these for you):

1. **Looker Studio** — repoint the report's data source from
   `gold.gold_commodity_matrix` to `gold.gold_pevs_production`. Column names are
   unchanged, so metric/dimension bindings survive once the table is rebound.

2. **Orphaned prod table** — after the next `make dbt-build-prod`, the new
   `gold.gold_pevs_production` exists but the old `gold.gold_commodity_matrix`
   lingers (dbt only manages models it knows about; a renamed model leaves the
   old physical table behind). Drop it once the new table is verified:

   ```bash
   bq rm -f -t "${GCP_PROJECT_ID}:gold.gold_commodity_matrix"
   ```

   Do this only AFTER confirming `gold_pevs_production` built and Looker is
   repointed — the drop is irreversible.

## CNY currency removal (2026-06)

The `val_*_cny` columns were dropped from all four Gold facts and the external-FX
seed path (`extfx_cny_brl` → `silver_extfx_currency` → `silver_currency` UNION) was
removed. The Gold tables physically shed the columns only after
`dbt build --full-refresh`; until then the dropped columns linger harmlessly
(nothing reads them). The currency selector now offers BRL/USD/EUR only.

## Rename cutover: `commodities` → `produtos agrícolas` (2026-07-03, v1.10.8)

The v1.10.8 release renamed the project's domain vocabulary and its BigQuery
schema. The objects were migrated non-destructively
(`CREATE TABLE new AS SELECT … FROM old`) and then a prod `dbt build` rebuilt the
graph under the new names:

| Old | New |
|-----|-----|
| `gold.gold_commodity_crosswalk` (table) | `gold.gold_produto_agrupamento` |
| `gold.dim_commodity_catalog` (view) | `gold.dim_produto_catalog` |
| `gold.dim_commodity_visibility` (view) | `gold.dim_produto_visibility` |
| `research_inputs.commodity_catalog_log` (table) | `research_inputs.produto_catalog_log` |
| `research_inputs.commodity_group_log` (table) | `research_inputs.agrupamento_log` |

Column renames: `commodity_id` → `agrupamento_id`, `codigo_commodity` →
`codigo_produto`; the `code_prefix` column was **removed** (products are now
registered by their exact code — see the v1.10.0 cadastro change). The Python
package was renamed `embrapa_commodities` → `embrapa_dashboard`, the gunicorn
entrypoint became `embrapa_dashboard.webapi.app:app`, and the GitHub repo became
`embrapa-dashboard-produtos-agricolas` (CI Workload Identity Federation
re-pointed). The **GCP project id stays `embrapa-dashboard-commodities`**
(immutable — only the GCP display name changed).

The 5 old BigQuery objects were **dropped** on 2026-07-03, after a pre-drop
safety audit (no live reader in code/dbt; no scheduled queries; and an
`INFORMATION_SCHEMA.JOBS_BY_PROJECT` 30-day scan found no Looker/external reader)
and a post-drop functional check (`/api/catalog`, the cross-source views, and
`/api/snapshot` all returned 200 against the migrated tables). No rollback net
remains.

Two manual cleanups outside this repo:

1. **Looker Studio** — repoint any report bound to `gold.gold_commodity_crosswalk`
   or the `dim_commodity_*` views to the `*_produto_*` names. (The job-history
   audit found no Looker reader of these internal tables, but verify.)

2. **Local dbt profile** — rename the `~/.dbt/profiles.yml` top-level key
   `embrapa_commodities:` → `embrapa_dashboard:` to match `dbt_project.yml`'s
   `profile:` (CI is already updated).
