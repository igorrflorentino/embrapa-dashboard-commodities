# IBGE PEVS silviculture (SIDRA t291) — an `origem` axis on `gold_pevs_production`

> Status: **IMPLEMENTED** (2026-08-29). Owner: Igor.
>
> Two numbers in the acceptance criteria below were WRONG when written and are corrected
> in place: São Paulo 2023 is **R$ 4,15 bi**, not 4,45, and Brazil 2023 is **R$ 31,16 bi**,
> not 31,7. Both originals were the whole-table SIDRA totals, which include the "outros
> produtos" (acácia-negra, resina) this plan deliberately excludes. The ingest is what
> surfaced the slip — the criterion did its job by being checked against the source
> instead of against our own output.
>
> The row model was right to the row: predicted ≈ 870.000, landed **869.778**.
>
> **Design revised 2026-08-28, before any code.** The first draft proposed a *separate
> banco*. The project lead pushed back: the survey is named "Extração Vegetal **e da**
> Silvicultura", so the faithful model is one banco with a column saying which half a row
> belongs to. That is right, and the objection that had motivated the split does not
> survive contact with the repository — see "Why one banco, not two".

## Context

The PEVS survey has two halves and this project ingests one: **table 289**, extraction
from *native* forest. The silviculture half — *planted* forest, **table 291** — has never
been ingested.

That was invisible until a researcher asked why São Paulo and Rio de Janeiro have no data
in IBGE PEVS. The data is faithful: SIDRA t289 itself returns `-` for SP's charcoal,
firewood and roundwood. What was wrong was the registry's description, which promised
"extrativismo vegetal **e da silvicultura** … recursos florestais, nativos **e
plantados**" — narrowed in v1.33.32 to describe only the half we hold.

That made the product honest by shrinking the claim. This plan makes it honest the other
way: by delivering what the survey's name already promises.

| PEVS half | Brazil, 2023 | in the dashboard |
|---|---|---|
| extraction (t289) | R$ 6,2 bi | yes |
| **silviculture (t291)** | **R$ 31,7 bi** | **no** |

São Paulo alone produces **R$ 4,45 bi/year** of roundwood, firewood and charcoal — exactly
the products already tracked — from planted forest. The entire SP history in Gold today is
R$ 132 mi. "Where does Brazil's wood come from" is currently answerable for ~16% of it.

## Why one banco, not two

The first draft argued for a separate banco because t291 repeats the product *names*
"Madeira em tora", "Lenha" and "Carvão vegetal", and a merged sum would silently add
native to planted. Three facts measured in the repository dissolve that:

1. **The project already does exactly this.** COMEX and COMTRADE carry `flow`
   (export/import) as a discriminator inside **one** banco, with `'all'` summing the
   directions — `FLOW_OPTIONS` in `filtersSchema.js` says so in as many words. A
   categorical axis whose "todos" is a meaningful total is the established pattern here,
   not a new risk.
2. **The codes do not collide.** Extraction uses `3433` carvão · `3434` lenha · `3435`
   madeira em tora; silviculture uses `3455` · `3456` · `3457`. Same names, distinct
   codes, and the Curadoria catalog registers by **exact code** — so the two can share a
   table with no ambiguity in the key.
3. **The unifying layer already exists and is already used this way.**
   `gold_produto_agrupamento` maps many codes across many sources to one agrupamento:
   `madeira` today spans **136 codes across 3 bancos** (comex, comtrade, pevs). Adding
   three silviculture codes to it is what that layer is for. A separate banco would have
   rebuilt, worse, machinery that is already in production.

And the sum is not nonsense: native + planted wood production is a real quantity that IBGE
itself publishes as one survey. Splitting it would make the *legitimate* total the hard
question and the partial one the default — the opposite of what a researcher wants.

The double-counting risk is real but it is a **presentation** problem, not a modelling
one: a discriminator column *preserves* the split, so nothing is unrecoverable. The
earlier draft's claim that "no filter recovers the separation after the sum" was simply
wrong — the column is the filter. What the risk demands is that `origem` be stated
wherever the number travels, which is the v1.33.25–v1.33.32 lesson applied from day one
rather than retrofitted.

## Scope

**In**

- SIDRA **t291**, municipal grain (`n6`), **1986–2024** (same window as t289).
- The **three top-level products**: `3455` Carvão vegetal · `3456` Lenha · `3457` Madeira
  em tora — the parents of the species/purpose breakdown, which already sum it.
- Both variables: `142` quantidade, `143` valor.
- A new **`origem`** column on `gold_pevs_production` (`extrativa` | `silvicultura`),
  backfilled `extrativa` for every existing row.
- `origem` as a first-class filter dimension, stated in the chip, the ABNT citation and
  the CSV.

**Out**

- The species/purpose leaves (`33247`–`33258`: eucalipto / pinus / outras espécies, papel
  e celulose / outras finalidades). Subsets of the three parents; ingesting both levels is
  how a sum silently doubles *within* t291. A later plan may add them as a dimension.
- `3460`–`3463` (acácia-negra casca, eucalipto folha, resina). Deferred, not rejected —
  a different economic object from wood, needing their own agrupamento.
- A separate banco. Explicitly rejected; see above.

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

≈ **30% of the current PEVS volume**. Gold grows from 1,08 M to ~1,34 M rows. Current
footprint, for scale: Bronze 25,5 M rows / 4,49 GB (append-only, accumulated), Silver
2,93 M / 0,45 GB, Gold 1,08 M / 0,25 GB.

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

**The money is not the cost.** The cost is one work session of engineering plus the
presentation discipline below.

## Technical Design

### Shape

Separate **ingestion** (a different SIDRA table needs its own request and its own Bronze),
converging in **Gold**:

| layer | extraction | silviculture |
|---|---|---|
| Bronze | `bronze_ibge.sidra_t289_raw` | `bronze_ibge.sidra_t291_raw` |
| Silver | `silver_ibge_pevs` | `silver_ibge_silvicultura` |
| Gold | **`gold_pevs_production`** — both, discriminated by `origem` | |
| serving | the existing PEVS marts, carrying `origem` | |
| banco | **`ibge_pevs`** — unchanged id | |

Keeping two Silver models (rather than one union) keeps each one's incremental contract
and its source's quirks local; the union happens once, in Gold, where the conformed grain
already lives.

### The `origem` column

`extrativa` | `silvicultura`, never null. Backfilled `extrativa` on the existing rows —
which is true by construction, since every row there came from t289.

It must behave like COMEX's `flow`:

- a filter dimension in `filtersSchema.js` + backend `FILTER_SCHEMAS`, with `todos`
  meaning the real total;
- a chip in the trigger bar, via the same resolver family as the other axes;
- a fragment in the ABNT "consulta detalhada" reference — the citation over-claimed by
  omitting exactly this kind of axis until v1.33.29, and
  `filterSummary.wiring.test.js` now fails if a call site forgets it;
- a column in the CSV export, alongside `escopo_produto` and `recorte_geografico`.

### Default, and what it breaks

Recommended default: **`todos`** — it is what the banco's name says and what the survey
is. The consequence must be stated rather than discovered: **every existing permalink and
saved citation changes meaning**, because a URL with no `origem` parameter will start
resolving to both halves. São Paulo goes from ≈ 0 to R$ 4,45 bi overnight.

That is acceptable and is what the ABNT access date exists for — but only if the chip and
the reference state `origem`, so a reader can tell which world a number came from. If the
project lead prefers continuity over faithfulness, the alternative is defaulting to
`extrativa`; then the banco under-reports by default again, and the description must keep
saying so.

### Agrupamentos

Add `3455`/`3456`/`3457` to the **existing** `carvao_vegetal` / `lenha` / `madeira`
agrupamentos rather than creating parallel ones. `madeira` already spans 136 codes and 3
bancos; this is the same operation. The product picker then keeps one "Madeira em tora",
and `origem` — not a duplicated product name — is what separates native from planted.

### Reuse

The SIDRA client (`ibge/client.py`) is already generic over table/variables/classification
— `pipeline.py`, `pam_pipeline.py` and `ppm_pipeline.py` all drive it. The new pipeline is
a fourth sibling, not a fork. Auto-chunking (`recommended_chunk_years`) needs no change:
3 products is a *smaller* request than PEVS's 7.

### The v1.33.32 test inverts

`tests/test_pevs_scope_claims.py` currently *requires* the banco description to say the
silviculture half is out, pinned to `IBGE_TABLE_ID == "289"`. Once t291 lands, that test
must be rewritten to require the opposite: that the description names **both** halves and
the `origem` axis.

This is the test doing its job. Anyone who ingests t291 without fixing the description
gets a red build, which is precisely the failure mode — a stale claim outliving the
mechanism that decided it — that the whole v1.33.25–v1.33.32 sweep was about.

## Tasks

Following `docs/adding_a_data_source.md`; step 1 (HTTP client) is already done.

- [ ] **Pipeline** `ibge/silvicultura_pipeline.py` — two-phase raw→bronze, delta-aware,
      modelled on `pam_pipeline.py`.
- [ ] **Config** — `silvicultura_table_id=291`, `silvicultura_classification_id=194`,
      `silvicultura_product_codes=3455,3456,3457`, `silvicultura_variable_codes=142,143`,
      start/end/overlap; `bq_bronze_ibge_silvicultura_table=sidra_t291_raw` (same
      `bronze_ibge` dataset). Plus `.env.example`.
- [ ] **Registries** — `cli.INGESTS` (`in_all=True`, `cadence_days=7`, so it rides
      `schedule.sh` and satisfies `test_ingest_cadence_matches_schedulers`),
      `doctor.SOURCE_CHECKS`, `doctor.BRONZE_TARGETS`.
- [ ] **dbt Bronze source** — `_sources.yml`.
- [ ] **dbt Silver** — `silver_ibge_silvicultura.sql`, incremental by `reference_year`,
      mirroring `silver_ibge_pevs` (including the measured `>=`-boundary note in its
      header, which applies identically).
- [ ] **dbt Gold** — add `origem` to `gold_pevs_production`, union the two Silvers.
      Currency-reform seed + deflator columns apply unchanged (1986 start ⇒ pre-1994
      values need `historical_currency_factors`).
- [ ] **Serving marts** — carry `origem` through every PEVS mart and the gateway readers.
- [ ] **Quality** — `data_quality_flag` scored on **deflated** `val_real_ipca_brl`, as
      today; verify the price-consistency thresholds still hold with planted-forest
      magnitudes mixed in (a per-`origem` median may be needed).
- [ ] **Catalog** — add the three codes to the existing agrupamentos.
- [ ] **UI** — `origem` filter, chip, citation fragment, CSV column; banco description
      rewritten to name both halves.
- [ ] **Tests** — pipeline unit tests; a dbt test asserting `origem` is never null and
      that the extraction subtotal still equals the pre-change Gold; rewrite
      `test_pevs_scope_claims.py`; a wiring test for the new chip/citation axis.
- [ ] **Docs** — `PLANS/README.md`, `CLAUDE.md`, `.env.example`.

## Risks & Mitigations

| risk | mitigation |
|---|---|
| **A total silently mixing native and planted.** The legitimate sum is also the dangerous default. | `origem` in the chip, the ABNT citation and the CSV — the axis travels with the number. `filterSummary.wiring.test.js` already fails when a call site forgets an axis. |
| **Existing permalinks change meaning.** A URL with no `origem` starts including silviculture. | Deliberate and stated above; the chip and reference make the new scope visible. Decide the default explicitly, do not inherit it by accident. |
| Quality thresholds calibrated on extraction only. | `quality_price_k` compares implied price to the **product median**; with two origins in one product the median shifts. Compute the median per `(product, origem)` or verify the flags do not move before shipping. |
| Pre-1994 values 10⁶–10⁹× too large. | Same `historical_currency_factors` seed; a per-unit bound test like `assert_pam_pre1994_real_per_unit_bounded`. |
| Scope creep into the species/purpose leaves. | Explicitly out of scope; they belong in a follow-up as a dimension, not as sibling products. |
| Query budget drifting out of the free tier. | +~10 GB/month against a 1024 GB allowance and a 210 GB projection. Re-measure after the first prod build rather than assuming. |

## Acceptance Criteria

- `embrapa ingest ibge-silvicultura` lands Bronze; `dbt build` produces
  `gold_pevs_production` with ≈ 1,34 M rows, `origem` never null.
- **Falsifiable against the source, not against our own output:** São Paulo, 2023,
  `origem = silvicultura` must total **R$ 4,15 bi** — roundwood R$ 3.651,5 mi, firewood
  R$ 369,1 mi, charcoal R$ 127,9 mi — the figures SIDRA t291 serves today for the three
  products in scope. A build that produces a different number is wrong regardless of how
  plausible it looks. ✅ verified in Bronze and in Silver.
- Brazil 2023: `silvicultura` **R$ 31,16 bi** (the whole t291 is R$ 31,72 bi; the R$ 0,56 bi
  difference is the deliberately excluded "outros produtos"). ✅
- **Nothing that existed changed:** filtering `origem = extrativa` reproduces the
  pre-change Gold row-for-row.
- `origem` appears in the filter chip, the "consulta detalhada" reference and the CSV.
- The banco description names both halves, and `test_pevs_scope_claims.py` has been
  inverted to require it.
- `embrapa doctor` reports the new source in the heartbeat and freshness checks.
