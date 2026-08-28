# ui/ — the dashboard's React UI layer

This directory is the **live production UI** of the dashboard: the app shell, every
view/perspective, the FilterMenu, the client-side registries (`bancos.js`,
`views.js`, `filtersSchema.js`), and the view-model utilities (`dataFilters.js`,
`urlState.js`, `chipFmt.js`, `csvExport.js`, …). `src/main.jsx` imports these
modules at boot; Vite bundles them into `dist/`, which the Flask service serves on
Cloud Run. **This is not a prototype** — it ships to users.

## Origin

The code was originally delivered as the **Claude Design System handoff prototype**
("Embrapa Commodities Design System") and adopted into the repo verbatim, so the
build no longer depends on an external bundle. It has since diverged substantially —
the synthetic data layer became API calls, `proto/` became `ui/`, and new views were
added — and it runs in production like any other source.

It **is** linted, with the same correctness ruleset as `src/data/` and `src/charts/`:
`npm run lint` is `eslint src/data src/charts src/ui`, and `frontend/eslint.config.js`
lists `src/ui/**/*.{js,jsx}` explicitly (106 files today). This README said the opposite
until 2026-08-28 — "intentionally out of ESLint scope", citing the very config that
includes it. The exemption was real once and lapsed when the directory became maintained
production code; per that config's own note, the gap "was hiding real dead-code +
hook-deps findings".

## What it does NOT contain

The two trees we author and maintain live OUTSIDE this directory:

| Concern | Lives in | Replaced this directory's… |
|---|---|---|
| Data access (API-backed) | `src/data/` (`dataStore`, `producers`, `enrichment`, `decorate`, `resource`) | …synthetic data layer (the old `dataStore.js`, `demoFixture.js`, `crossSource.js`, … — deleted) |
| Analytical charts | `src/charts/` (Plotly.js + SVG ports) | …hand-rolled SVG charts (`Charts*.jsx` — deleted) |

The synthetic mock series the prototype shipped with (`OVERVIEW_TS`, `PRODUCT_TS`,
the `QUALITY_*`/`TOP_*` tables) were removed once the views moved to the API-backed
snapshot. `data.js` here now holds only the live client-side **registries** (the UF
tile grid, region + quality-flag taxonomies, the unit-family conversion table) and
the pt-BR **formatters** — the metadata the `/api` deliberately omits, joined onto
the API rows in `src/data/decorate.js`.

## Contract

The boundary between this UI and the data layer is the `window.*` global interface
(`window.applyFilters`, `window.dataStore`, the producers, the registries). The
snapshot/contract shapes are documented in `contracts.js` and
`PLANS/react_migration_contract_map.md` (the historical migration spec).
