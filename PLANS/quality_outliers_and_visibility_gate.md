# PLANS — Q1 Outlier/Problemático quality flags + F7 Ciclo-de-Vida visibility gate

> Status: **F7 + Q1 IMPLEMENTED + Q1 ENABLED (2026-06-27).** The MAGNITUDE FLOOR
> (`quality_value_floor`, default 100000 deflated BRL/USD) made a single global threshold work for
> ALL 5 sources — it removes the tiny-municipality rounding noise that over-flagged PAM/PPM at ~2%,
> leaving only genuine typos. Materialized problemático rates (of **all rows**, from
> `serving.serving_quality_by_source`): PEVS 0.0009% / COMEX 0.0057% / PAM 0.020% / PPM 0.0003% /
> COMTRADE 0.15% (the last all `weight=1` placeholders, spot-checked). So `enable_quality_outliers`
> is now **true** for all 5 sources (revert to legacy 4-value by setting it false — still compiles
> byte-identical). The
> F7 direct-Gold readers (município / quality timeseries+by-product) now thread the visibility gate
> too (`serving/sql.visibility_clause`). All layers wired + tested: dbt compile + sqlfluff (ON) clean,
> 950 pytest / 275 vitest green.
> Designed data-grounded (adversarial workflow validated on live BigQuery, 2026-06-26/27).
> Origin: the "Contrato de Dados" sheet verification (`docs/audits/curadoria_pr_audit_2026-06-26.md`
> is the catalog audit; this doc is the spreadsheet-vs-code integration follow-up).

## The decisive data finding (magnitude alone fails; the implied-price test + magnitude floor wins)

Every **magnitude-only** statistical fence tested on live Gold false-accuses legitimate records:
- PEVS quantity max log-z = **4.51** (z>6 unreachable); robust log-Tukey k>4 flags **722** rows,
  all legitimate recurring Amazon timber (Paragominas/Carauari 1989–1996).
- COMEX value z>6 = **2 rows**, both ~US$281k banana→Uruguay (trivial, not typos), while
  billion-dollar rows clear. Within-series ratio over-flags (4.8% at ≥10×); ≥1000× spikes are real
  regime shifts.

**Conclusion:** no magnitude threshold separates "typo" from "legitimate giant" on this data — a real
big number and a placeholder both read as "high." The working signal is the **implied price**
(`value ÷ quantity`, scale-invariant): a typo breaks it, a legit giant does not (detector below).
Paired with the **magnitude floor** (`quality_value_floor`), which drops the tiny-municipality rounding
noise that had over-flagged PAM/PPM, a **single global** `quality_price_k` now isolates typos cleanly
across all 5 sources. The detector is still gated behind `var('enable_quality_outliers', true)`: when
set OFF the gold models compile **byte-identical** to the legacy 4-value flag (the revert path); in prod
it is **true for all 5 sources**, validated on a live build (rates above).

## FEATURE A — F7 visibility gate (DONE)

`ciclo_de_vida = 'Fazer Ingestão mas deixar indisponível'` hides a commodity everywhere a researcher
sees it, but NEVER from the Curadoria admin editor / orphan / crosswalk. Today: 46 active prefixes, all
visible → the gate era um **data no-op**. NÃO é mais: 3 códigos comex estão escondidos em
prod (6.688 linhas de Gold filtradas, medido 2026-08-30). Leia as afirmações de "no-op" abaixo
como histórico da entrega original.

**Single source of truth:** `dbt/models/core/dim_produto_visibility.sql` (view) emits only HIDDEN
`(source, code, sidra_tabela)` rows — the EXACT commodity code (latest-wins, active, indisponível;
`code_prefix` was eliminated in v1.10.0, so this is now `codigo_produto`). Gate predicate =
`NOT EXISTS … <code_column> = v.code` over it (was `LIKE code_prefix||'%'`; behavior-preserving since
every entry's prefix already equalled its exact leaf code). A code with no row stays visible (handles
PPM=0, partial coverage).

**A TABELA entra no predicado (v1.46.5).** A identidade de um produto é `(banco, tabela, código)`, e
nos bancos multi-tabela (pevs 289×291, ppm 3939×74) o predicado casa também a tabela: esconder a
metade extração deixa a silvicultura visível. Antes casava só `(source, code)` e as duas metades
sumiam juntas — latente, porque os códigos das duas tabelas são disjuntos e o caso nunca ocorreu.
Uma linha do gate SEM tabela é **coringa** (esconde as duas), preservando as entradas sem tag. Os
dois lados — a macro `hidden_code_predicate` e o espelho `serving/sql.visibility_clause` — renomeiam
a coluna do gate para `_vis_sidra_tabela`: sem isso, `sidra_tabela` sem qualificação resolve para o
escopo interno do `NOT EXISTS` e a comparação vira tautologia (medido contra o BigQuery). Guardado
pelos testes unitários dbt em `_gold.yml` sobre `gold_source_metadata`.
`dim_produto_catalog` is untouched (admin/crosswalk still see hidden-but-active rows).

Files: `dim_produto_visibility.sql` (new), `macros/hidden_code_predicate.sql` (new); predicate added to
serving marts (pevs/pam/ppm/comex+seasonality/comtrade annual) + `serving_quality_by_source.sql`;
`serving/sql.py` `visibility_clause()` for direct-Gold readers (quality_timeseries, quality_by_product,
production_by_municipio_yearly, Dados raw on `gold_*` facts); `seam_base._crosswalk_df()` anti-joins it.
Admin readers (`fetch_produto_catalog`, orphan, lifecycle, crosswalk) are EXEMPT by design.

Tests: a `dim_produto_visibility` unit_test (disponível/indisponível/tombstone fixture, latest-wins);
pytest gate tests + admin-exemption regression + `visibility_clause` / direct-reader string tests. The
conservation test `assert_serving_conserved_gold.sql` gates BOTH the serving AND the Gold side with
`hidden_code_predicate`, so hiding a commodity can never false-fail it; no vitest (rows-only change).

## FEATURE B — Q1 outlier/problemático (detection ENABLED in prod via the magnitude floor)

**9-value emitted enum:** `OK, MISSING_VALUE, MISSING_QUANTITY, MISSING_WEIGHT, INCOMPLETE, OUTLIER_QUANTITY,
PROBLEMATIC_QUANTITY, OUTLIER_VALUE, PROBLEMATIC_VALUE`. COMEX/COMTRADE weight reuses the QUANTITY ids.
(**v1.10.2:** the accepted-value domain grew to **11** — two RESERVED tiers `INFERRED_QUANTITY`/`INFERRED_VALUE`
were added to every `_gold.yml` accepted_values list + the frontend/backend taxonomy, for a future auto-fill
pipeline. No Gold CASE emits them, so they're accepted-but-absent, 0 today; they do NOT participate in the
precedence below.)

**Precedence (donut stays a partition):** MISSING_*/INCOMPLETE > PROBLEMATIC_VALUE > PROBLEMATIC_QUANTITY
> OUTLIER_VALUE > OUTLIER_QUANTITY > OK.

**Detector (REVISED — VALIDATED on live BigQuery, 2026-06-26).** The magnitude-only fence the first
workflow proposed CANNOT split outlier from problemático (both are "high") — proven false-positives on
legit Amazon timber. The working method is an **implied-price (unit-value) consistency test**: a typo
breaks `value ÷ quantity` (scale-invariant), a legit giant does not. Confirmed on real data:
- COMEX: within a product the VALUE tail is 26.5× the median but the PRICE tail is 10.5× (P99); the
  extreme price tail is unambiguous typos (charcoal $1,440/**1 kg**; rice $13,800/**1 kg**; soybean meal
  $3 for 2,500 t) — all `weight=1` placeholders / dropped digits, NONE legit giants.
- The **deflation requirement is load-bearing**: IBGE price MUST use `val_real_ipca_brl` — nominal
  `val_yearfx_brl` manufactured a fake 20% near-zero-price tail (66,826 rows, ALL pre-1995 hyperinflation).
  With deflation, PEVS >100× rate = **0.003%**.

Rule, per group (IBGE `(product_code, family, unit_native)`; trade `(flow, code)`), sample gate `n>=MIN_OBS`:
- `price = real_value / quantity` — IBGE `val_real_ipca_brl/qty_native`; trade `val_yearfx_usd/net_weight_kg`
  (USD, post-1989, no BR-inflation issue). Compute `ln_med = median(LN(price))` per group (APPROX_QUANTILES).
- `price_dev = LN(price) - ln_med`.
- **PROBLEMATIC** iff `ABS(price_dev) >= LN(k_price)` — the implied price is economically absurd → a value
  or quantity typo. Attribute: `price_dev > 0` (value-too-high or qty-too-low) → if the value is the high
  outlier `PROBLEMATIC_VALUE` else `PROBLEMATIC_QUANTITY`; `price_dev < 0` → the opposite. (Both QUANTITY
  ids also cover trade `net_weight_kg`.) Needs a small magnitude floor to skip trivia.
- **OUTLIER_{QUANTITY,VALUE}** iff the measure is in the product's high tail (one-sided log fence,
  `(LN(measure)-p50)/(p75-p50) >= k_outlier`, `n>=MIN_OBS`, `p75>p50`) AND the row is NOT problemático
  (price consistent) → "bem acima do esperado mas válido."
- Precedence (donut partition): MISSING_*/INCOMPLETE > PROBLEMATIC_VALUE > PROBLEMATIC_QUANTITY >
  OUTLIER_VALUE > OUTLIER_QUANTITY > OK.

**dbt vars (prod):** `enable_quality_outliers=true` (false ⇒ legacy 4-value flag, compiled byte-identical),
**`quality_price_k=100`** (implied price >100× or <1/100× the product median = typo), `quality_outlier_k=4.0`
(magnitude fence for the OUTLIER tier), `quality_min_obs=100`, **`quality_value_floor=100000`** (the magnitude
floor — skip rows below this deflated BRL / USD value so tiny-municipality rounding noise can't over-flag).
PPM `measure_kind='stock'` (herd) has NO value → quantity OUTLIER only, never a price/value flag.

**Files:** `dbt_project.yml` (vars); `macros/data_quality_flag.sql` (extend signature, 2-arg back-compat,
precedence); `macros/quality_outlier_ctes.sql` (new — bounds CTE + `quality_level_expr` compile-gated by
the var → null when off); the 5 gold models (bounds CTEs + level exprs; PPM stock skips value; COMEX
migrates inline CASE keeping MISSING_WEIGHT); `_gold.yml` accepted_values += 4 ids + new unit_tests +
singular `assert_quality_flag_in_enum.sql`; `serializers.py` `_FLAG_KEY`/`_FLAG_LABEL_PT` += 4 pt-BR;
`data.js` QUALITY_FLAGS += 4; `ViewQuality.jsx` QTS_KEY += 4; `contracts.js` qualityTs keys; `glossary.js`
prose. pt-BR labels: "Quantidade/Valor atípica(o) (válida/o)" + "… problemática(o) (provável erro)".

## Per-source validation on live prod — the magnitude floor makes price_k generalize

The first pass measured the raw |ln(price)−ln(product median)| rate WITHOUT a magnitude floor and found a
single `quality_price_k` over-flagged PAM/PPM at ~2% — agricultural value-per-unit spans regions / years /
sub-crops within one `product_code`, so tiny-municipality rounding produced erratic implied prices. The fix
was NOT per-source thresholds but the **magnitude floor** (`quality_value_floor`, default 100000 deflated
BRL / USD): dropping sub-floor rows removes that rounding noise, after which a **single global**
`quality_price_k=100` isolates genuine typos across all 5 sources. Validated on the live rebuild —
problemático rate **of all rows** (from `serving.serving_quality_by_source`):

| source | rows | problemático | outlier (valid tail) |
|---|---|---|---|
| PEVS | 331,544 | **0.0009%** | 0.42% |
| COMEX | 352,157 | **0.0057%** | 0.61% |
| PAM | 1,124,058 | **0.020%** | 0.29% |
| PPM | 2,405,516 | **0.0003%** | 0.46% |
| COMTRADE | 2,294,874 | **0.15%** | 0.24% |

Spot-checked: the flagged rows are genuine typos (overwhelmingly trade `weight=1` placeholders, e.g.
US$80M for 1 kg of plywood). `enable_quality_outliers` is therefore **true for all 5 sources** in prod.
*(The earlier "per-source threshold needed / ships OFF" conclusion is SUPERSEDED — it predated the floor.)*

## Operator runbook (prod)

1. `make dbt-build-prod-with-backup` (rewrites `data_quality_flag` on every gold fact — backup-first).
2. F7 check: `SELECT * FROM gold.dim_produto_visibility` → eram **0 linhas** na entrega; hoje são
   3 (comex). Confira que o número bate com o que a curadoria escondeu, não que seja zero.
3. Q1 check: `SELECT source, data_quality_flag, COUNT(*) FROM serving_quality_by_source GROUP BY 1,2` → the
   `OUTLIER_*` / `PROBLEMATIC_*` tiers appear; sanity-check the per-source rates against the table above.
4. Revert (if ever needed): set `enable_quality_outliers: false` in `dbt_project.yml` + rebuild → the gold
   models compile byte-identical to the legacy 4-value flag. Fully reversible — `data_quality_flag` is
   recomputed from Silver on every build (no data loss). The scheduled `dbt-build-prod` picks up the
   `dbt_project.yml` setting automatically.

## Sandbox vs operator

Sandbox-verifiable: `dbt parse`/`compile` (PYTHONUTF8=1), dev-target unit_tests, pytest, vitest,
ruff/sqlfluff; **offline-compile the gold models with the flag OFF and diff `data_quality_flag` against
`main` to prove byte-identical**. Operator-only (no `*.googleapis.com` in sandbox): every prod
`dbt build`/`test`, the F7 no-op confirmation + live hide/restore smoke test, all
`enable_quality_outliers: true` validation/enable builds.
