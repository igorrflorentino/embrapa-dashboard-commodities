# Plan — IBGE sub-UF geography (meso/micro + intermediate/immediate) + live município

Status: **DONE** (2026-08-27, v1.26.0). Adds the IBGE territorial levels **between UF and
município** as filterable geography dimensions, and activates **município** as a live
filter (today gated). Scope: the municipality-grained IBGE bancos only — `ibge_pevs`,
`ibge_pam`, `ibge_ppm` (they ingest at SIDRA `n6` and Gold carries `city_code`). COMEX
is UF-grained and COMTRADE is international, so neither gains sub-UF geography.

## The two PARALLEL hierarchies (key design fact)

A município belongs to exactly one of EACH of two independent decompositions of its UF.
They do **not** nest into each other:

```
Brasil ─ Região (macrorregião, 5) ─ UF (27) ┬─ Mesorregião (~137) ─ Microrregião (~558) ─┐
                                            └─ Reg. Intermediária (~133) ─ Reg. Imediata (~510) ─┴─ Município (~5570)
```

So the cascade is NOT a single linear chain. Below UF there are two branches, both
converging on município. The cascade engine must support: a linear spine
(nação ▸ região ▸ UF) and, under UF, two two-level sub-hierarchies plus the município
leaf, where the eligible-município set is the **intersection** of every active geo facet.

The classic (meso/micro) and current (intermediária/imediata) divisions are kept BOTH —
classic for historical continuity, 2017 because current IBGE data uses it.

## Data source

IBGE Localidades API, one call: `GET /api/v1/localidades/municipios`. Each município
carries both hierarchies nested (`microrregiao.mesorregiao.UF.regiao` and
`regiao-imediata.regiao-intermediaria.UF.regiao`). No ingestion change needed — Gold
already has `city_code` (7-digit IBGE code) to join on.

## Layers (build order, bottom-up)

1. **Seed generator** — `scripts/refresh_ibge_municipio_mesh.py` (fetch → CSV). Idempotent,
   UTF-8, sorted by `city_code`. Mirrors `refresh_comtrade_country_seed.py`.
2. **Seed** — `dbt/seeds/ibge_municipio_mesh.csv` (~5570 rows): city_code, city_name,
   uf_code, state_acronym, state_name, region_code, region_abbrev, region_name,
   meso_code, meso_name, micro_code, micro_name, intermediaria_code, intermediaria_name,
   imediata_code, imediata_name. Declared + tested in `_seeds.yml` (unique city_code,
   not_null on every code).
3. **Conformed dim** — `dim_geo_municipio.sql` (core), one row per município, all
   codes/names. PK city_code. Tests: unique city_code, not_null, accepted ranges.
   `dim_geo_br` (UF grain) is kept unchanged.
4. **Serving** — a município-grained geo cube reader carrying every geo code, basket+banco
   scoped, joined to `dim_geo_municipio`. The client aggregates up to the selected level.
   Cost guard: basket-scoped, `maximum_bytes_billed` applies, queried only when the
   geography view is open. Plus a small `/api/geo-mesh` universe endpoint feeding the
   cascade options (the level lists + município→ancestor map), cached.
5. **Backend (webapi)** — routes + seam + serializers for the universe + the município cube
   + applying a geo-level filter (which set of municípios).
6. **Frontend** — generalize `useGeoCascade` for the dual sub-UF hierarchy + município leaf;
   FilterMenu render of the 4 new levels + município; `filtersSchema` geo dim metadata;
   `dataFilters` application (intersect municípios across active facets, aggregate);
   `decorate.js`/`contracts.js` as needed.
7. **Tests + preview** — pytest (dim/seam/serializers/routes), vitest (cascade engine +
   dataFilters), dbt tests on the seed/dim, browser preview verifying a meso/micro filter
   narrows the map.

   ✅ Closed in v1.26.0. Steps 1-6 shipped in v1.5.2; step 7's LAST clause — "a meso/micro
   filter narrows **the map**" — did not, and stayed open for over a year: the cascade
   narrowed the DATA correctly while `BrazilChoropleth` kept shading the whole UF, so the
   finest filter in the product had no visible effect. Closing it needed municipal
   *geometry*, which the repo had none of:

   - `scripts/refresh_ibge_municipio_geojson.py` vendors one mesh per UF from IBGE's
     malhas API v3 (`intrarregiao=municipio&qualidade=minima`, coordinates rounded to 3
     decimals) into `frontend/public/geo/municipios/<UF>.json` — 27 files, ~2.9 MB.
   - `MunicipioChoropleth.jsx` draws them, lazily, one UF at a time.
   - The join needed no new plumbing: IBGE's `codarea` IS the 7-digit `city_code` this
     plan already built everything else on.

   **Per UF, not for Brazil**, and that is a deliberate limit rather than a first
   increment: the whole-country municipal mesh is ~836 KB gzipped (heavier than maplibre)
   and 5570 polygons at country zoom are 2-3px smudges. The map therefore renders only
   when the selection resolves to ONE state; broader selections keep the ranking, which is
   grain-correct at any breadth.

## Notes / accessory needs
- The município universe is currently gated (`topMunis` []); activating it live is part of
  this work (Q2 = "município vivo").
- `dbt build --full-refresh` (or at least `dbt seed` + the new models) is an operator step
  for prod; the seed + dim build offline against dev.
