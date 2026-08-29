# IBGE PEVS silviculture (SIDRA t291) — `gold_silvicultura_production`

> Status: **PROPOSED** (2026-08-28) — sizing measured, nothing implemented. Owner: Igor.
> Sibling of `ibge-pam` / `ibge-ppm`: a second SIDRA table behind the same client, its own
> pipeline, its own Bronze→Silver→Gold lineage, its own banco.

## Context

The PEVS survey ("Produção da Extração Vegetal **e da Silvicultura**") has two halves and
this project ingests one: **table 289**, extraction from *native* forest. The
silviculture half — *planted* forest, **table 291** — has never been ingested.

That was invisible until a researcher asked why São Paulo and Rio de Janeiro have no data
in IBGE PEVS. The data is faithful: SIDRA t289 itself returns `-` for SP's charcoal,
firewood and roundwood. What was wrong was the registry's description, which promised
"extrativismo vegetal **e da silvicultura** … recursos florestais, nativos **e
plantados**" — fixed in v1.33.32, where the banco now states which half it holds and names
São Paulo as the example.

That fix made the product honest. It did not close the gap, and the gap is not marginal:

| PEVS half | Brazil, 2023 | in the dashboard |
|---|---|---|
| extraction (t289) | R$ 6,2 bi | yes |
| **silviculture (t291)** | **R$ 31,7 bi** | **no** |

São Paulo alone produces **R$ 4,45 bi/year** of roundwood, firewood and charcoal — exactly
the products already tracked — from planted forest. The entire SP history in Gold today is
R$ 132 mi. Any question of the form "where does Brazil's wood come from" is currently
answerable only for the ~16% of it that is extractive.

## Scope

**In**

- SIDRA **t291**, municipal grain (`n6`), **1986–2024** (same window as t289).
- The **three top-level products**: `3455` Carvão vegetal · `3456` Lenha · `3457` Madeira
  em tora. These are the parents of the species/purpose breakdown and already sum it, so
  taking them alone is what avoids double-counting *within* t291.
- Both variables: `142` quantidade, `143` valor.
- A **new banco** (`ibge_silvicultura`), not an extension of `ibge_pevs`. See
  "Separate banco, not a merge" below — this is the load-bearing decision.

**Out**

- The species/purpose leaves (`33247`–`33258`: eucalipto / pinus / outras espécies, papel
  e celulose / outras finalidades). They are subsets of the three parents; ingesting both
  levels is how a sum silently doubles. A later plan may add them as a *dimension* of the
  parent rather than as sibling products.
- `3460`–`3463` (Outros produtos: acácia-negra casca, eucalipto folha, resina). Deferred,
  not rejected — they are a different economic object from wood and would need their own
  agrupamento. Adding them later doubles the row count (see Sizing).
- Folding silviculture into `gold_pevs_production`. Explicitly rejected.

## Sizing (measured 2026-08-28, not estimated)

The row model was validated against the existing table before being applied to the new
one, which is the only reason to trust it:

```
t289:  5.362 municípios × 7 produtos × 2 variáveis × 39 anos = 2.927.652
silver.silver_ibge_pevs actual                              = 2.927.652   ← exact
```

Applying the same model to t291 (3.717 municipalities returned at `n6` for 2023, measured
via the SIDRA API):

```
t291:  3.717 municípios × 3 produtos × 2 variáveis × 39 anos ≈   870.000 rows
```

≈ **30% of the current PEVS volume**. With the deferred "Outros produtos" it would be 6
products ≈ 1,74 M rows.

Current PEVS footprint, for scale: Bronze 25,5 M rows / 4,49 GB (append-only, accumulated),
Silver 2,93 M / 0,45 GB, Gold 1,08 M / 0,25 GB. The silviculture equivalents land near
0,15 GB Bronze per full load, 0,13 GB Silver, 0,08 GB Gold; Bronze trends toward ~1,3 GB
as monthly `reconcile` re-loads accumulate, exactly as t289's did.

### Cost

Against the measured cost basis (R$ 0,074/GB/month BigQuery storage; R$ 0,0000814/s Cloud
Run; see `project_estrutura_de_custos`):

| item | R$/month |
|---|---|
| BigQuery storage (~1,5 GB steady state) | ~0,11 |
| Cloud Run Job (weekly delta + monthly reconcile) | ~0,07 |
| dbt build query (+~10 GB/month scanned) | **0** — inside the 1 TiB free tier |
| SIDRA API | free |
| **total** | **~R$ 0,20** |

≈ +4% on the R$ 4,54/month projected under the 2026-08-28 cadence. The one-off historical
backfill is ~117 chunked requests and is negligible.

**The money is not the cost.** The cost is one work session of engineering plus the design
hazard below.

## Technical Design

### Separate banco, not a merge

t291 carries **"Madeira em tora", "Lenha" and "Carvão vegetal" under the same names as
t289**. If both land in one banco — or worse, one agrupamento — then summing "madeira em
tora" silently adds native extraction to planted production. That is not a rounding
concern: nationally the planted half is 5× the extractive one, so the merged total would
be dominated by the half a researcher studying extractivism did not ask for, under a label
that says nothing about it.

This is the same defect class the v1.33.25–v1.33.32 sweep chased: a label naming more than
the number measures. Building it in deliberately would be the worst instance yet, because
no filter or caveat could recover the split after the sum.

So: two bancos, two Gold tables, and crossing them stays an **explicit** researcher choice
(the multi-source perspectives already exist for that), never an automatic sum. The
"Cruzamento entre fontes" view is the right place for "nativa vs plantada", and it makes
the comparison the subject rather than hiding it.

### Reuse

The SIDRA client (`ibge/client.py`) is already generic over table/variables/classification
— `pam_pipeline.py` and `ppm_pipeline.py` both drive it. The new pipeline is a third
sibling, not a fork of the client. Auto-chunking (`recommended_chunk_years`) already
handles SIDRA's per-request cell limit and needs no change: 3 products is a *smaller*
request than PEVS's 7.

### Names

| thing | value |
|---|---|
| ingest subcommand | `ibge-silvicultura` |
| pipeline | `src/embrapa_dashboard/ibge/silvicultura_pipeline.py` |
| Bronze | `bronze_silvicultura.sidra_t291_raw` |
| Silver | `silver_ibge_silvicultura` |
| Gold | `gold_silvicultura_production` (`gold_<source>_<form>`, form = production) |
| serving mart | `serving_silvicultura_annual` |
| banco id (SPA + backend) | `ibge_silvicultura` |

`label` should be `IBGE · Produção da Silvicultura`, and the `about` must state the mirror
of what `ibge_pevs` now states: this is the **planted** half, the extractive half is the
other banco. The v1.33.32 test (`tests/test_pevs_scope_claims.py`) pins the PEVS side; the
new banco deserves the symmetric pin so the two descriptions cannot drift into overlapping
claims.

### Configuration

Mirrors the PAM fields (`config.py`):

```python
bq_bronze_silvicultura_dataset: str = "bronze_silvicultura"
bq_bronze_silvicultura_table:   str = "sidra_t291_raw"
silvicultura_table_id:          str = "291"
silvicultura_classification_id: str = "194"
silvicultura_product_codes:     str = "3455,3456,3457"
silvicultura_variable_codes:    str = "142,143"     # keep in sync with the dbt vars
silvicultura_start_year:        int = 1986
silvicultura_end_year:          int = <current year>
silvicultura_delta_overlap_years: int = 1
```

### Cadence

Rides the weekly batch (`in_all=True`, `cadence_days=7`), same as `ibge`/`comex`. PEVS
publishes ~2 days a month, so a dedicated trigger would buy nothing.
`tests/test_ingest_cadence_matches_schedulers.py` will require the new source to be
covered by a scheduler — riding `schedule.sh` satisfies it with no new script.

## Tasks

Following `docs/adding_a_data_source.md` (11 steps); the client step is already done.

- [ ] **Pipeline** `ibge/silvicultura_pipeline.py` — two-phase raw→bronze, delta-aware,
      modelled on `pam_pipeline.py`.
- [ ] **Config** — the fields above, plus `.env.example` entries with the "which half"
      comment.
- [ ] **Registries** — `cli.INGESTS` (`cadence_days=7`), `doctor.SOURCE_CHECKS`,
      `doctor.BRONZE_TARGETS`.
- [ ] **dbt Bronze source** — `_sources.yml`.
- [ ] **dbt Silver** — `silver_ibge_silvicultura.sql`, incremental by `reference_year`,
      mirroring `silver_ibge_pevs`. Carry over the `>=` boundary note (the measured
      non-incrementality documented in that model's header applies here too).
- [ ] **dbt Gold** — `gold_silvicultura_production.sql`, own lineage, currency-reform seed
      + deflator columns exactly as PEVS (1986 start ⇒ pre-1994 values need
      `historical_currency_factors`, or the series is 10⁶–10⁹× too large).
- [ ] **Serving mart** — `serving_silvicultura_annual.sql` at the chart grains.
- [ ] **Quality** — include in `serving_quality_by_source` and the `data_quality_flag`
      taxonomy; IBGE is scored on **deflated** `val_real_ipca_brl`.
- [ ] **Registries (product)** — `bancos.js` + `webapi/registries.py`, `filtersSchema.js`
      + backend `FILTER_SCHEMAS`, `gold_source_metadata`, agrupamentos/catalog entries
      with names that cannot collide with the PEVS ones.
- [ ] **Tests** — pipeline unit tests; dbt tests (a `silver → gold` conservation test like
      `assert_pam_conserved_silver_to_gold`); the symmetric scope-claim pin.
- [ ] **Docs** — `PLANS/README.md` row, `CLAUDE.md` overview line, `.env.example`.

## Risks & Mitigations

| risk | mitigation |
|---|---|
| **Double counting native + planted.** Same product names in both bancos. | Separate bancos + separate Gold. Never a shared agrupamento. A dbt test asserting the two Gold tables share no `(source, product_code)` key would make it structural rather than conventional. |
| **Catalog/agrupamento name collision** confusing the Curadoria editor. | Register silviculture products under distinct agrupamento names (e.g. "Madeira em tora (silvicultura)"), and rely on the exact-code registration the catalog already uses — the codes differ (`3457` vs the t289 code), so the join cannot cross. |
| Pre-1994 values 10⁶–10⁹× too large. | Same `historical_currency_factors` seed PEVS uses; a dbt test on per-unit bounds like `assert_pam_pre1994_real_per_unit_bounded`. |
| Query budget drifting out of the free tier. | +~10 GB/month against a 1024 GB allowance and a 210 GB projection. Re-measure after the first prod build rather than assuming. |
| Scope creep into the species/purpose leaves. | Explicitly out of scope here; they belong in a follow-up as a *dimension*, not as sibling products. |
| The 9-commodity model does not cover silviculture products. | Decide the agrupamento mapping **before** ingesting — an unmapped Gold is a banco no view can filter. |

## Acceptance Criteria

- `embrapa ingest ibge-silvicultura` lands Bronze, and `dbt build` produces
  `gold_silvicultura_production` with ≈ 870 k rows across 1986–2024.
- **The falsifiable end-to-end check, tied to the source, not to our own output:**
  São Paulo, 2023, must total **≈ R$ 4,45 bi**, of which roundwood ≈ R$ 3,65 bi, firewood
  ≈ R$ 369 mi and charcoal ≈ R$ 128 mi — the figures SIDRA t291 serves today. A build that
  produces a different number is wrong regardless of whether it looks plausible.
- Brazil 2023 totals ≈ R$ 31,7 bi.
- The two bancos never share an agrupamento; a cross-banco sum is only reachable through
  an explicit multi-source perspective.
- `embrapa doctor` reports the new source in the heartbeat and freshness checks.
- The banco's `about` states which half it holds, pinned by a test, symmetric to the PEVS
  one.
