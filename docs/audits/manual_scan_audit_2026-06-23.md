# Manual-scan audit — 2026-06-23

> ⚠️ **HISTÓRICO — relatório pontual, não é uma lista de pendências.** Auditoria de 2026-06-23, sobre o PR #157 (geografia sub-UF), muito anterior ao estado atual do repositório. Seus achados foram tratados na época (veja o `CHANGELOG`); trate caminhos, contagens e estrutura aqui como o retrato daquela data, **não** como o código de hoje. Mantido por proveniência — em especial os achados refutados, que não existem em nenhum outro lugar.

A targeted **manual code-scan** audit (not a metrics sweep) of the freshly-shipped IBGE
sub-UF geography feature (PR #157) + a documentation-coherence pass. Method: deep reads of
the changed code, with every finding adversarially re-verified against the actual source.

> ⚠️ **Process note.** An initial multi-agent run was *invalidated* by an environment
> fault: the git **worktree's working directory was corrupted** (a post-merge
> `gh … --delete-branch` switched it to a stale local `main` and left an inconsistent file
> tree with ReadOnly/permission issues, so `git reset`/`checkout -f` couldn't materialize
> the `dbt/` files). Agents read stale code and refuted real findings as "code doesn't
> exist." The shipped code in `origin/main` (`239f945`) is **complete and correct** (40
> files / 7230 insertions, verified via git objects). The audit was redone by hand against
> a clean checkout (the **parent repo**). Recommend recreating the worktree before reuse.

## Confirmed findings (all fixed in this PR)

| # | Sev | Finding | Fix |
|---|-----|---------|-----|
| A | Medium | **`cityCodes` → HTTP 414.** A broad sub-UF narrowing (e.g. deselecting one of 138 mesorregiões → ~5,500 cities) joined into a GET query string overflows gunicorn's default `limit_request_line` (~4 KB) → the município-cube fetch fails. | `/api/municipio-yearly` is now **POST** (cityCodes in the JSON body); `resource.ensure` accepts a `[url, init]` factory. |
| B | Medium | **Empty cube → permanent "loading".** A legitimately-empty result (`municipioYearly → []`) was conflated with not-loaded (`null`): `muniCube && muniCube.length` falsy → `subUfCube=null` → `subUfPending=true` forever, and the view fell back to the all-UF grid. | dataFilters distinguishes `null` (pending) from `[]` (loaded-empty); an empty sub-UF selection now reads as honest zero/empty, never the all-UF fallback. |
| C | Low-Med | **`NotFound` → 500.** `seam.geo_mesh`/`geo_municipio_yearly` didn't catch a missing `dim_geo_municipio`/Gold table, contradicting the documented `{municipios:[]}` — a fresh/dev/PEVS-only env 500s the whole geography menu. | Both readers now `except NotFound: return None` (mirroring `banco_metadata_overrides`). |
| D | Low | **Full-grid scan if `cityCodes` absent.** The route didn't require `cityCodes`; a direct call could scan the full ~146k-row município grid. | The route requires a non-empty `cityCodes` (400 otherwise); the gateway returns `None` for an empty city set (defense-in-depth). |
| B2-3 | Low | `/geo-yearly` + `/municipio-yearly` kept blank `codes` from a raw `split(",")` (inconsistent with `_csv_param`). | Blank-strip both. |
| B7-1 | Low | `dim_geo_municipio` carries UF→região independently of `dim_geo_br` with no drift guard. | New singular test `assert_municipio_mesh_uf_consistent`. |

## Documentation coherence (the feature shipped undocumented)
The sub-UF geography feature existed **only** in `PLANS/geo_subregions.md`. Now documented
in: `CHANGELOG.md` (`### Added` + the fixes), `ARCHITECTURE.md` (core dim + serving
narrative + folder tree), `docs/gold_data_model.md` (ER diagram + `dim_geo_municipio`
entity), `docs/frontend_data_contract.md` (§3.6 — the `/geo-mesh` + `/municipio-yearly`
contracts), `CLAUDE.md` (serving overview), `scripts/README.md` (the mesh-refresh script).

## Refuted (false positives — left as-is)
- **B6-1** (`fetch_banco_metadata` TTL not rebound): `_bind_classification_ttl` *does* rebind it (cache.py:136).
- **B6-3** (reconcile skips PAM/PPM): `_reconcile_full_sources` *does* cover them (the L8/M1 fixes landed).
- **B3-1** (banco switch collapses município selection): `main.jsx` keys `FilterMenu` on the banco → remounts + re-seeds; `changeDatabase` resets the summary. Not reachable.
- **B4-3 / B7-2** (rollup silent-drops un-meshed cities / no coverage test): the cube is scoped to `narrowedCities ⊆ mesh`, so it can't return a non-mesh city; a relationships test would also be noisy from legitimately-extinct historical municípios.

## Outcome
No critical/high. Three real edge-case robustness bugs (A/B/C) + low items, all fixed and
verified: **884 pytest · 241 vitest · ruff · ESLint · SQLFluff · vite build** green.
