# Frontend data contract — Gold → snapshot mapping

**Audience:** anyone maintaining the dashboard's data-access layer (the Flask BFF
in `src/embrapa_dashboard/serving/` + `webapi/`). **Purpose:** spell out, field
by field, how the frontend's in-memory snapshot shapes (defined in
`dataStore.js` / `contracts.js`) are produced from the
**Gold** tables — so the BFF is a thin mapping and the UI lights up without rework.

> This is a **data contract**. **Update (2026-06 Dash→React migration):** both
> halves now EXIST — the BFF / data-access layer (`src/embrapa_dashboard/serving/`
> queries the pre-aggregated `serving` marts in `dbt/models/serving/` instead of
> loading Gold in memory) **and** the React SPA + Flask REST UI (`frontend/` +
> `src/embrapa_dashboard/webapi/`), live on Cloud Run behind IAP. What the
> backend guarantees is below: column names, **magnitudes**, units, and the few
> transforms (family vocab, region code, `world_exp`) the BFF must apply.

The single seam is `dataset_for(banco_id)` + the generic adapters + the
cross-source layer. Everything here feeds those; no view/chart/router changes.

---

## 1. Gold tables (the only things the BFF reads)

| Table | Grain | Backs |
|---|---|---|
| `gold.gold_pevs_production` | year × UF × city × product | IBGE PEVS (production) |
| `gold.gold_pam_production` | year × UF × city × product | IBGE PAM (production), with area/yield columns `area_planted_ha`, `area_harvested_ha`, `yield_kg_ha`, served via the `/api/productivity` seam |
| `gold.gold_comex_flows` | flow × year × **month** × NCM × country × UF × **via** | MDIC COMEX (Brazil trade) |
| `gold.gold_comtrade_flows` | flow × year × reporter × partner × cmd(HS6) | UN Comtrade (global trade) |
| `gold.gold_produto_agrupamento` | (source, code) → agrupamento_id | cross-source product bridge |
| `gold.gold_source_metadata` | one row per source | provenance for `dataStore.meta(id)` (§9) |

**Capabilities** (drive the brief's view gating; match `bancos.js`):

| bank | geo (UF) | monthly | product detail | flows/partners | productivity/yield |
|---|---|---|---|---|---|
| `ibge_pevs` | ✅ (UF+city) | ❌ annual | product_code | ❌ (production, not flows) | ❌ |
| `ibge_pam` | ✅ (UF+city) | ❌ annual | product_code | ❌ (production, not flows) | ✅ |
| `mdic_comex` | ✅ (UF origin) | ✅ (`reference_month`) | NCM8 | ✅ | ❌ |
| `un_comtrade` | ❌ (country↔country) | ❌ annual | HS6 | ✅ | ❌ |

→ COMTRADE has **no** `ufData` and **no** `monthlyData` (Geografia / Concentração-
geográfica / Sazonalidade resolve to "Não se aplica"). COMEX has both.

---

## 2. Magnitude & unit rules (read this first — it's what breaks integrations)

Gold stores **raw** numbers in base units. The BFF scales to the snapshot's display
magnitude. Get this wrong and axes/KPIs break.

| Gold column | Raw unit | Snapshot field | Display magnitude | BFF transform |
|---|---|---|---|---|
| `val_real_ipca_brl` (PEVS) | R$ | `overviewTS.v` | **R$ bi** | ÷ 1e9 |
| `val_yearfx_usd` (COMEX/COMTRADE) | US$ | `overviewTS.v` | **US$ bi** | ÷ 1e9 |
| `val_*` (productTS) | R$ / US$ | `productTS.v` | **mi** | ÷ 1e6 |
| `net_weight_kg` | kg | `q_mass` | **mil t** | ÷ 1e6 |
| `qty_base` (family=massa) | t | `q_mass` (PEVS) | **mil t** | ÷ 1e3 |
| `qty_base` (family=volume) | m³ | `q_vol` (PEVS) | **mi m³** | ÷ 1e6 |
| cross `exp_value`/`imp_value`/`world_exp` | US$ | `points[].v` | **US$ bi** | ÷ 1e9 |
| cross `exp_weight` | kg | `points[].v` | **mil t** | ÷ 1e6 |

**Axis/ratio rule (brief §4):** two cross series share a Y-axis (or form a ratio)
**iff their `unit` strings are identical**. Keep display units consistent:
`'US$ bi'`, `'mil t'`, `'US$/kg'`. So `exp_value` and `world_exp` (both `'US$ bi'`)
mix; `exp_weight` (`'mil t'`) never mixes with them.

---

## 3. `dataset_for(banco_id)` → snapshot (brief §2)

### 3.1 `products` — `[{ code, tabela, name, unit, family }]`
`SELECT DISTINCT` the product key from the bank's Gold table.

| field | PEVS | COMEX | COMTRADE |
|---|---|---|---|
| `code` | `product_code` | `ncm_code` | `cmd_code` (HS6) |
| `tabela` | `289` / `291` | `comex_ncm` | `comtrade_hs` |
| `name` | `product_description` | `ncm_description` | `cmd_description` |
| `unit` | `base_unit` | `base_unit` | `base_unit` |
| `family` | `family` → **en** (see §7) | idem | idem |

> `code` MUST match the keys of `productTS`. They do — both come from the same Gold
> product column.

> **`tabela` travels for EVERY banco since v1.47.2** — including the single-table ones,
> where the value is constant (PAM `5457`, COMEX `comex_ncm`, COMTRADE `comtrade_hs`). It
> was emitted only for PEVS/PPM until then, behind a `_TABELA_SOURCES` set; that set was
> the last *"does this banco have a table?"* branch on the read path, and it is gone. A
> consumer reads the identity the same way in all five bancos — **constant is simpler than
> absent**.
>
> Why it matters even where it looks redundant: a produto's identity is
> `(banco, tabela, código)`, and in PEVS three products exist in BOTH halves under the same
> NAME with different codes (Carvão vegetal, Lenha, Madeira em tora). Without the field the
> Donut and the product comparison show two identical entries. `window.labelProductRows`
> uses it to suffix a name only when it repeats.
>
> The UI does **not** show a table filter for single-table bancos — a one-option segment
> would be noise. The symmetry is in the data and the code, not on screen.

> **Livestock (IBGE PPM) adds two things.** (1) `products` carries an extra
> **`measure_kind`** (`stock` | `flow`) — emitted ONLY for PPM (the gateway's
> `with_measure_kind` flag; the column lives only in `serving_ppm_annual`). `stock` =
> the herd (efetivo, a value-less headcount); `flow` = animal products (eggs/milk, with
> value). It lets the UI gate the **Rebanho** view and tell the two apart. (2) The
> **`count`** family (head/eggs) gets its own quantity track **`q_count`** (mi un)
> alongside `q_mass`/`q_vol` on `productTS` (as `q`), `ufData`, `ufYearly` and
> `serving.product_uf`/`products_by_uf`. Heads are **never summed across species**, so
> there is no aggregate count headline — `overviewTS` does NOT carry `q_count` (the
> Overview count series is computed client-side in `dataFilters` and suppressed for a
> stock basket).

### 3.2 `overviewTS` — annual `[{ y, v, q_mass, q_vol, q }]`
Aggregate to the year. **COMEX is monthly in Gold → SUM over months for the annual
overview** (monthly detail is served by `monthlyData`, §4.3).

| field | PEVS | COMEX | COMTRADE |
|---|---|---|---|
| `y` | `reference_year` | `reference_year` | `reference_year` |
| `v` | `SUM(val_real_ipca_brl)` ÷1e9 | `SUM(val_yearfx_usd)` ÷1e9 | `SUM(val_yearfx_usd)` ÷1e9 |
| `q_mass` | `SUM(qty_base WHERE family='massa')` ÷1e3 | `SUM(net_weight_kg)` ÷1e6 | `SUM(net_weight_kg)` ÷1e6 |
| `q_vol` | `SUM(qty_base WHERE family='volume')` ÷1e6 | — (omit) | — (omit) |
| `q` | = `q_mass` (back-compat alias) | idem | idem |

> Do **not** emit `q_vol` for COMEX/COMTRADE — those rows carry no volume family in
> the current scope. Only emit families that exist (group `qty_base` BY `family`).

### 3.3 `productTS` — `{ [code]: [{ y, v, q, family }] }`
One annual series per product, keyed by the same `code` as `products`.

- `v` = `SUM(value)` ÷ 1e6 (**mi**) — PEVS `val_real_ipca_brl`, trade `val_yearfx_usd`.
  (`overviewTS.v` in bi = Σ `productTS.v` ÷ 1000 — keep the factor.)
- `q` = `SUM(qty_native)` × 1000 (PEVS convention).
- `family` = the product's `family` (→ en).

### 3.4 `ufData` — COMEX + PEVS only (`geo` capability)
`[{ uf, name, region, col, row, value, q_mass, q_vol }]`, grouped by UF.

| field | source |
|---|---|
| `uf` | `state_acronym` |
| `name` | `state_name` |
| `region` | `region` → **abbrev** (see §7): Norte→`N`, Nordeste→`NE`, Centro-Oeste→`CO`, Sudeste→`SE`, Sul→`S` |
| `col`, `row` | **frontend's** `../data.js` `UF_DATA` tile-map — NOT in Gold; the BFF copies the grid |
| `value` | `SUM(val_yearfx_usd)` (COMEX) / `SUM(val_real_ipca_brl)` (PEVS) |
| `q_mass` | `SUM(net_weight_kg)` (COMEX) / `SUM(qty_base WHERE family='massa')` (PEVS) |
| `q_vol` | `SUM(qty_base WHERE family='volume')` |

> **COMTRADE → do not produce `ufData`** (no Brazilian UF; `geo` absent in `bancos.js`).

### 3.5 `quality` — `[{ id, label, color, count, share }]`
`GROUP BY data_quality_flag`.

- `id` = `data_quality_flag` (see §7 for the exact id set — **not** the brief's
  example `ESTIMATED`/`OUTLIER`).
- `count` = row count; `share` = count ÷ total (Σ ≈ 1).
- `label`, `color` = mapped by the React frontend from `id` (keep the palette in
  the frontend; backend ships only `id`+`count`).

### 3.6 Sub-UF geography cascade — `geo-mesh` + município cube (IBGE PEVS/PAM/PPM)
The geography filter descends BELOW UF via three dedicated endpoints (the snapshot stays
UF-grained) — the mesh, the per-(município, year) cube, and the per-product breakdown
WITHIN a município selection (`POST /api/products-by-municipio`, added v1.29.0: the cube
groups by city and sums the produtos away, so it can draw a place's trajectory but never
name what is behind it). Two PARALLEL IBGE divisions sit between UF and município and do **not** nest:
classic **mesorregião → microrregião** and 2017 **região intermediária → imediata**; a
município passes the cascade iff it clears every active facet (intersection).

- **`GET /api/geo-mesh`** → `{ municipios: [{ cityCode, cityName, uf, region, meso, micro,
  intermediaria, imediata }] }`. Each sub-UF level is a `{ code, name }` pair — blank
  `{code:'',name:''}` for a município with no grouping at that level (e.g. a post-2017
  município has no classic meso/micro). The static IBGE mesh (~5570 rows, from
  `dim_geo_municipio`), fetched once + cached; the cascade builds its level option-lists +
  the `cityCode → ancestry` map from it. `{ municipios: [] }` if the dim isn't built.
- **`POST /api/municipio-yearly`** — body `{ cityCodes: [...] }`; `banco` / `codes` /
  `currency` / `correction` in the query string → `{ municipioYearly: [{ year, cityCode,
  uf, value, q_mass, q_vol, q_count }] }`. The basket + **city-scoped** per-(município,
  year) cube, read straight from Gold (`maximum_bytes_billed`-guarded). **POST, not GET**:
  the resolved city set can be hundreds of codes — too large for a query string (gunicorn's
  ~4 KB request-line limit → 414). A **non-empty `cityCodes` is required** (so the backend
  never scans the full ~146k-row município grid). Same `/1e6`-style scaling as `ufData`
  (§3.4). The client rolls these city rows up to whichever sub-UF level is active.
  `{ municipioYearly: [] }` for a banco with no município grain (COMEX/COMTRADE) or a
  not-built table.

---

## 4. Generic adapters (brief §3)

### 4.1 `flowData` → Sankey origin→destination
- COMEX: origin = `state_acronym` (UF), dest = `country_name`. unit `'US$'`.
- COMTRADE: origin = `reporter_name`, dest = `partner_name`. unit `'US$'`.
- `node.value` = Σ of the links touching it (pre-summed). value = `SUM(val_yearfx_usd)`.

### 4.2 `partnerData` → partner ranking
`{ partners: [{ name, exp, imp, value }] }`, ordered by `value` desc.
- `name` = `country_name` (COMEX) / `partner_name` (COMTRADE).
- `exp` = `SUM(val_yearfx_usd WHERE flow='export')`, `imp` = import; `value` = exp+imp.
- COMTRADE: **World is already excluded** in Silver (no `partner_code='0'`), so the
  ranking is clean — no extra filter needed.

### 4.3 `monthlyData` → seasonality (**COMEX only**)
COMEX Gold has `reference_month`. Build `matrix[year][1..12]`, `monthlyAvg[12]`,
`series[{ym,y,m,v}]` from `SUM(val_yearfx_usd)` by (year, month).
> COMTRADE is annual → never call this for `un_comtrade` (Sazonalidade = "Não se aplica").

---

## 5. Cross-source metrics (brief §4)

`crossSeries(banco, metric, {y0,y1})` → annual `points:[{y,v}]` in the **DISPLAY_UNIT
magnitude**.

| metric.id | source | formula (per year, in scope) | DISPLAY_UNIT |
|---|---|---|---|
| `mdic_comex:exp_value` | gold_comex_flows | `SUM(val_yearfx_usd WHERE flow='export')` ÷1e9 | `US$ bi` |
| `mdic_comex:imp_value` | gold_comex_flows | import ÷1e9 | `US$ bi` |
| `mdic_comex:exp_weight` | gold_comex_flows | `SUM(net_weight_kg WHERE flow='export')` ÷1e6 | `mil t` |
| `mdic_comex:exp_price` | derived | `exp_value / exp_weight` (same window) | `US$/kg` |
| `un_comtrade:exp_value` | gold_comtrade_flows | `SUM(val_yearfx_usd WHERE flow='export')` ÷1e9 | `US$ bi` |
| `un_comtrade:imp_value` | gold_comtrade_flows | import ÷1e9 | `US$ bi` |
| `un_comtrade:world_exp` | gold_comtrade_flows | **see below** | `US$ bi` |

**`world_exp` (world total exports)** — the World partner (`W00`) is dropped in
Silver, so the world total is **derived by summing over all reporters**:
```sql
SELECT reference_year, SUM(val_yearfx_usd)/1e9 AS world_exp_usd_bi
FROM gold.gold_comtrade_flows
WHERE flow = 'export'          -- (filter cmd to the commodity for market share)
GROUP BY reference_year
```
This is the denominator for `cross_market_share` (Brazil ÷ world). `exp_price` is
derived (value ÷ weight), kept internally consistent with `exp_value`/`exp_weight`.

> `crossSeries.preview` **derives from the source banks' maturity** — true if any
> source lacks real data (`MATURITY[b.maturity].hasData` is false), not a hardcoded
> literal (see §9). Flip the real builder and the source's `maturity` together so a
> synthetic series never reads as real.

---

## 6. Product crosswalk (brief §6) — `gold_produto_agrupamento`

The keystone for every cross-source join (export coefficient, market share, price
spread, trade mirror, harvest→shipment lag). Resolved table, grain `(source, code)`:

| column | meaning |
|---|---|
| `agrupamento_id` | stable slug: `castanha_do_para`, `madeira_em_tora` |
| `agrupamento_nome` | display name |
| `source` | `pevs` \| `comex` \| `comtrade` |
| `code` | exact code in that source (PEVS code / NCM8 / HS6) |

**Usage** — join each fact's product code to get a comparable agrupamento:
```sql
SELECT x.agrupamento_id, SUM(c.val_yearfx_usd) AS comex_exp_usd
FROM gold.gold_comex_flows c
JOIN gold.gold_produto_agrupamento x ON x.source='comex' AND x.code = c.ncm_code
WHERE c.flow='export'
GROUP BY x.agrupamento_id
```
A product code matching no agrupamento is simply absent from the crosswalk →
**"não vinculado"** (graceful), never an error. Register a new produto by its exact
source code via the **"Cadastro de produtos agrícolas"** admin view (writes to `research_inputs`
→ `core/dim_produto_catalog` → `gold_produto_agrupamento`) when the product scope grows.

Verified (2023): the crosswalk links castanha and roundwood across all three
sources, so e.g. the export coefficient (COMEX exports ÷ PEVS production) and the
trade mirror (COMEX vs COMTRADE Brazil) compute on a common agrupamento.

---

## 7. Vocabulary the BFF must reconcile

### 7.1 Physical-unit `family` — Gold is Portuguese
Gold emits `family` in pt. Map to the frontend `UNIT_FAMILIES` ids (`../data.js`).
Proposed mapping (confirm the right-hand ids against the registry; if they differ
it is a one-line BFF map, never a Gold change):

| Gold `family` | base_unit | → `UNIT_FAMILIES` id |
|---|---|---|
| `massa` | t | `mass` |
| `volume` | m³ | `volume` |
| `energia` | MWh | `energy` |
| `contagem` | un | `count` |
| `area` | ha | `area` |
| `desconhecida` | (NULL) | `unknown` |

> Rule (brief §2.1): the backend **always carries** `family` — the frontend never
> guesses the dimension. `net_weight_kg` is a parallel always-massa measure; never
> `SUM(qty_base)` across families (GROUP BY `family`).

### 7.2 `data_quality_flag` — exact id set
The flags the macro emits (the frontend color map must cover **these**). The last four
(the implied-price tiers) are emitted only when the dbt var `enable_quality_outliers` is
`true` (on in prod):

| id | meaning | tables |
|---|---|---|
| `OK` | has quantity + value, plausible implied price | all |
| `MISSING_VALUE` | quantity but no monetary value | all |
| `MISSING_QUANTITY` | value but no quantity (common in COMTRADE ch.44) | PEVS, COMTRADE |
| `MISSING_WEIGHT` | value but no net weight | COMEX |
| `INCOMPLETE` | neither | all |
| `OUTLIER_VALUE` / `OUTLIER_QUANTITY` | high-magnitude but price-consistent — a valid large value | all (gated) |
| `PROBLEMATIC_VALUE` / `PROBLEMATIC_QUANTITY` | implied price >100× or <1/100× the product median ⇒ likely typo | all (gated) |
| `INFERRED_QUANTITY` / `INFERRED_VALUE` | **reserved** auto-fill tiers (accepted-but-absent) — plumbed through `contracts.js` / `_gold.yml` but always 0 today; no Gold CASE emits them yet | all (reserved) |

### 7.3 `region` — Gold is full names
Gold `region` ∈ {Norte, Nordeste, Centro-Oeste, Sudeste, Sul}. The brief's `ufData`
wants the abbreviations {N, NE, CO, SE, S} — map in the BFF.

---

## 8. Gold column reference

Both flows tables share the 4 monetary conventions (× 3 currencies): `val_yearfx_*`
(nominal at the year/month FX) and `val_real_{ipca,igpm,igpdi}_*` (deflated to today
— use for cross-year comparison). See `dbt/models/gold/_gold.yml` for per-column docs.

- **gold_pevs_production**: reference_year, reference_date, state_acronym, state_name,
  region, city_code, city_name, product_code, product_description, family, unit_native,
  qty_native, qty_base, base_unit, val_yearfx_{brl,usd,eur},
  val_real_{ipca,igpm,igpdi}_{brl,usd,eur}, data_quality_flag, last_refresh.
- **gold_comex_flows**: + reference_month, ncm_code, hs_chapter, ncm_description,
  country_code/name/iso_a3, transport_route_code, via_name, stat_unit_code,
  unit_native_symbol, net_weight_kg, val_freight_usd, val_insurance_usd, source_rows.
- **gold_comtrade_flows**: cmd_code, hs_chapter, cmd_description,
  reporter_code/name/iso_a3, partner_code/name/iso_a3, partner_is_group,
  qty_unit_code, unit_native_symbol, net_weight_kg, gross_weight_kg,
  val_cif_usd, val_fob_usd, source_rows. (annual — no reference_month.)
- **gold_produto_agrupamento**: agrupamento_id, agrupamento_nome, source, code.
- **gold_source_metadata**: source, gold_table, cadence, year_start, year_end,
  total_rows, products_total, ufs_total, last_refresh. (view; see §9.)

---

## 9. Status & provenance the BFF reports (brief CHANGELOG)

These are **runtime/BFF concerns — NOT in the Gold fact tables**. The data layer is
status-agnostic; what follows is what the BFF must report and how to derive it.

### 9.1 Status — three axes (the old `status:'live'|'soon'` is DERIVED, never set)

| Axis | What | Source |
|---|---|---|
| `maturity` | backend readiness, one of `planejado · desenvolvimento · ingestao · beta · estavel · manutencao · descontinuado` (+ optional `implNote`, `implDate`) | BFF/`bancos.js` runtime config |
| `visible` | bool — hide the bank from the whole UI when false | BFF/`bancos.js` |
| *uso* (active) | derived at runtime (the bank feeding the current view) | not a field |

Per-source `maturity` for this project (config, not data):

| source | maturity | implDate |
|---|---|---|
| `ibge_pevs` | `estavel` | — |
| `mdic_comex` | `estavel` | — |
| `un_comtrade` | `beta` | — |
| `ibge_pam` | `beta` | — |
| `sefaz_nf` | `planejado` (planned, no deadline; no Gold table yet) | none |

`status:'live'` is derived from `MATURITY[b.maturity].hasData`; `crossSeries.preview` derives
from the **source banks' maturity** — true if any source lacks real data (`MATURITY[b.maturity].hasData` is false).

### 9.2 Provenance seam — `dataStore.meta(id)` ← `gold_source_metadata`

The UI reads ALL bank provenance from the backend (never frontend literals), via
`dataStore.meta(id)` → `bancoMeta(id)`. `gold.gold_source_metadata` (one row per
source, a view → always current) supplies it, derived from the Gold tables so a
rename / new cadence / extended coverage / fresh load propagates to the whole UI:

| meta / `prov` field | gold_source_metadata column |
|---|---|
| table name (`bancoTable`) | `gold_table` |
| cadence (annual/monthly) | `cadence` |
| coverage / `yearStart`,`yearEnd` | `year_start`, `year_end` |
| `totalRows` | `total_rows` |
| `productsTotal` | `products_total` |
| `ufsTotal` | `ufs_total` (NULL for COMTRADE — no UF) |
| `lastCrop` (PEVS) | `year_end` |
| `refresh` / `goldVersion.at` / `isStale` | `last_refresh` |

`maturity` / `visible` are **not** in this table — they
are runtime config (§9.1). `source`, `granularity/scope`, and the human source name
are constants the BFF maps from `source` + this contract.
