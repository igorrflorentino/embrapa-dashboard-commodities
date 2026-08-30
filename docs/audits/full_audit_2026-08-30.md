# Full codebase audit — 2026-08-30 (v1.44.1)

> **STATUS — HISTORICAL record of the state at v1.44.1.** All four 🟡 findings below were
> fixed in v1.45.0, immediately after this report was written; the fixes are named under
> each item. Read this as the measurement that motivated them, not as a work queue.


Run with the `code-audit` skill, extended past its Python scope to cover the React
frontend, the deployed service and the project's own health gate. Measurement commands and
their raw output are named inline so any figure here can be re-derived.

**Verdict: healthy.** No 🔴 Critical finding exists by the skill's definition (`cc ≥ C` **and**
`mi = C`) — all 64 Python modules are maintainability grade **A**, and there are **zero**
circular imports. What follows are 🟡 and 🟢 items, plus the one structural risk that has
concrete evidence behind it rather than a metric alone.

---

## Health summary

| Module | MI | Max CC | Coverage | |
|---|---|---|---|---|
| `serving/curation.py` | A33 | **E(38)** | 97.15% | ⚠ |
| `serving/agrupamentos.py` | A54 | **D(24)** | 97.87% | ⚠ |
| `webapi/seam_curation.py` | A50 | C(17) | 100.00% | · |
| `comtrade/client.py` | A57 | C(16) | 98.33% | · |
| `serving/catalog_lifecycle.py` | A52 | C(16) | 100.00% | · |
| `webapi/routes.py` | A24 | C(16) | 99.64% | · |
| `cli.py` | A29 | C(14) | 97.35% | · |
| `doctor.py` | A25 | C(14) | 99.42% | · |
| `reconcile_check.py` | A57 | C(14) | 100.00% | · |
| `webapi/seam.py` | A27 | C(11) | 100.00% | · |
| `webapi/serializers.py` | A32 | C(11) | 100.00% | · |
| `serving/attribute_engineering.py` | A51 | C(11) | 86.93% | · |
| `bcb/series.py` | A69 | B(10) | 100.00% | |
| `config.py` | A36 | B(9) | 100.00% | |
| `comtrade/pipeline.py` | A59 | B(9) | 100.00% | |
| `ibge/client.py` | A54 | B(8) | 99.35% | |
| `serving/gateway.py` | A37 | B(8) | 100.00% | |
| `ingestion_heartbeat.py` | A79 | B(8) | 83.33% | |
| `ibge/pipeline.py` | A66 | B(6) | 100.00% | |
| `comex/pipeline.py` | A62 | B(6) | 99.17% | |
| `backup.py` | A75 | B(6) | 100.00% | |

**Totals** — Python: 1776 tests, **99.06%** coverage (gate 98%). Frontend: 1097 tests,
87.13% lines / 83.88% statements / 70.31% branches. `ruff` clean; `eslint` clean;
`uv lock --check` clean; `npm audit --omit=dev` → 0 vulnerabilities.
`embrapa doctor` → **27/27 green**. CI on the merge commit: 5/5 green.

---

## 🔴 Critical Architecture

**None.** The category requires `cc ≥ C` *and* `mi = C`. Maintainability across all 64
modules is grade A (lowest: `webapi/routes.py` at A23.58), so no module qualifies. Circular
imports: none (AST scan over `src/`).

---

## 🟡 Code smells

### 1. `serving/curation.py::record_produto_catalog` — CC **E(38)**, 224 lines

The worst complexity figure in the codebase, and the only one graded E. Composition:
**15 branches, 5 `raise`, 0 loops** — it is a write gate, and nearly all of its complexity
is input validation (agrupamento required, length caps, group must exist, the multi-table
`sidra_tabela` rule, ingestão/visibilidade defaults, `change_id` idempotency).

Validation complexity is *essential*, not tangled control flow, so the raw number overstates
the danger. What does not overstate it is the evidence: during the v1.39.0 key change this
function held a **verbatim second copy** of the `sidra_tabela` rule, so generalising the
shared validator left every PEVS write refused with a stale message. A gate this long is
where a duplicated rule hides.

**Proposed fix:** extract the validation block into named, individually testable predicates,
leaving `record_produto_catalog` as sequencing + persistence. Effort: **medium**.

> **FIXED in v1.45.0** — extracted `_validate_agrupamento`, `_validate_group_registered` and
> `_preserve_omitted_fields` (the last names the preserve-on-omit policy the docstring
> already described as one rule). **E(38) → C(18)**; the `ruff C901` violation is gone.
> The gate that REFUSES (`_validate_sidra_tabela`) deliberately stayed in the main flow: a
> refusal has to be readable where the write happens.

### 2. `serving/agrupamentos.py::record_group` — CC **D(24)**

Same shape, same cause (a write gate with many validation branches), one grade lower.
Worth the same treatment. Effort: **small** once item 1 sets the pattern.

> **FIXED in v1.45.0** — extracted `_validate_group_name` and `_validate_group_uniqueness`.
> **D(24) → C(15)**. The plan said "reusing item 1's predicates"; on inspection that would
> have been wrong. `curation._validate_agrupamento` guards a catalog ENTRY's fields; this
> guards the group REGISTRY's identity. They share only `MAX_NOTE_LEN` — already the same
> constant. Forcing reuse would couple two gates that have neither the same rule nor the
> same message.

### 3. The idempotency read-back is stubbed in every test that touches it

`attribute_engineering._code_row_for_change_id` and `._flow_market_row_for_change_id`
(lines 397-409, 423-435 — the bulk of that module's 20 uncovered lines) are replaced by
`monkeypatch` stubs in `tests/test_serving.py` at every call site. Their bodies — **the SQL
that reads a row back by `change_id`** — therefore execute in zero tests.

That SQL is what makes a retried write idempotent instead of duplicating a row. A wrong
column name in it would pass the whole suite and fail in production. `agrupamentos` has the
same pattern (`_group_row_for_change_id`, stubbed in `test_cov_agrupamentos.py`).

**Proposed fix:** one test per helper that drives the real body against a fake BQ client.
Effort: **small**.

> **FIXED in v1.45.0** — `tests/test_change_id_readback.py`, 12 tests over all **four**
> helpers (the finding said three; `agrupamentos._group_row_for_change_id` is the fourth,
> and `curation`'s was covered except its `if not rows` branch — the same branch missing in
> all four). `attribute_engineering` went **86.93% → 96.08%**, the repo total 99.06% →
> 99.31%.
>
> The first version of that test could not catch the defect it existed for: a fake row with
> the right keys answers correctly no matter what the SELECT asks for, so renaming a
> selected column passed green. The fix is a row that RECORDS which columns the code read,
> checked against the SELECT the function itself emitted — the actual coupling between the
> query and the mapping under it.

### 4. "Faixa de valor" is inert scaffolding spread across five files, and the citation
would state it

`summary.valueMin` / `valueMax` are initialised to `null` in `main.jsx:141-142` and **never
written** — no UI control sets them (`FilterMenu` has no reference) and no deep link decodes
them (`urlState.js` has no reference). The consumer, `dataFilters.valueShareForRange`,
returns `1.00` for `(null, null)`, i.e. no filtering.

`FilterTriggerBar` deliberately omits the chip, with a comment saying why ("no backed filter
path, so it is hidden rather than shown inert"). The **ABNT citation does not have that
guard**: `AppShell.jsx:310` pushes `Faixa de valor: …` whenever either bound is non-null.

Today nothing can set them, so nothing misreports — this is **latent, not live**. The risk
is that the scaffolding invites someone to wire a control and get an immediate
inconsistency: unfiltered data beside a citation claiming a restriction. That is this
project's documented recurring defect (a label naming a narrower slice than the number).

**Proposed fix:** either delete the dimension end-to-end, or gate the citation. Deleting is
cleaner and is what the chip row's own comment implies. Effort: **small**.

> **FIXED in v1.45.0 — with a correction to this finding.** The write-up above understates
> what was already in place: the FilterMenu control had been removed earlier, and
> `main.jsx` **already forced `valueMin`/`valueMax` to null on URL decode**, with a comment
> naming the ABNT citation as the exact hazard. The guard existed; it sat at the decoder
> rather than at the citation.
>
> What remained was a closed dead loop — `VALUE_PRESETS` fed only `valueShareForRange`, which
> fed only a row counter that always read 1.00 from it; `chipFmt.valueRange` formatted a
> field nothing wrote; the citation branch could not fire. All of it deleted end-to-end,
> along with four tests that asserted a constant was 1.00 (they guarded dead code, not
> behaviour). The dimension stays DOCUMENTED in `filtersSchema` with `backed: false`, which
> is where "the source has it, the dashboard does not filter on it" is honest.

---

## 🟢 Conventions

- **`ingestion_heartbeat.py` at 83.33%** — the 6 uncovered lines (62-67) are `ensure_table`
  (dataset + table bootstrap). Infrastructure setup, low regression risk; worth a test only
  when convenient.
- **`charts/LagBars.jsx` at 0% coverage** — imported by `main.jsx` and stubbed in
  `ViewsChain.cov.test.jsx`, so the real component never executes. It backs `cross_lag`,
  which CLAUDE.md records as **data-blocked** (no source in this repo). Expected, not a gap.
- **`main.jsx` at 0% coverage** — boot wiring. Mostly defensible, with one note: the
  `dataView={isDataView}` prop added in v1.43.0 gates the "Exportar CSV" button, so an
  untested file feeds a tested component's most user-visible condition. The receiving side
  *is* tested (`AppShell.cov.test.jsx`), which is where it matters most.
- **`ViewDados.jsx` at 50.68%** and **`data/producers.js` at 63.07%** — the two frontend
  files furthest below the 80% line.
- **Long files**: `FilterMenu.jsx` (1744 lines) and `ViewCadastroProdutos.jsx` (1165) are
  the two beyond a comfortable size. Both are cohesive single-screen components; splitting
  is optional and carries its own risk of scattering one screen's logic.
- **Zero pending markers.** A `TODO|FIXME|XXX|HACK` sweep over `src/`, `frontend/src/` and
  `dbt/models/` returns 7 hits, all false positives: Portuguese "TODO/TODOS" (meaning *all*)
  and a placeholder filename in a CLI help string.

---

## What was verified and found clean

| Area | Instrument | Result |
|---|---|---|
| Maintainability | `radon mi src/` | 64/64 grade A |
| Circular imports | AST scan over `src/` | 0 |
| Python complexity gate | `ruff --select C90` | 5 over threshold, all listed above |
| Python tests | `make test` | 1776 pass · 99.06% (gate 98%) |
| Frontend tests | `vitest run --coverage` | 1097 pass · 87.13% lines |
| Python lint/format | `make lint` | clean |
| Frontend lint/build | `npm run lint` / `build` | clean |
| Lockfile drift | `uv lock --check` | clean |
| JS dependency advisories | `npm audit --omit=dev` | 0 vulnerabilities |
| Data + pipeline health | `embrapa doctor` | 27/27 green |
| dbt SQL | CI (out of skill scope) | sqlfluff + dbt unit tests green |
| Deployed revision | `gcloud run revisions describe` | `00196-dfr`, created 81s after the merge |

---

## Prioritised plan

| # | Item | Risk addressed | Effort |
|---|---|---|---|
| 1 | Extract the validation predicates out of `record_produto_catalog` (E38) | The one place a duplicated rule has already hidden once | Medium |
| 2 | Same for `record_group` (D24), reusing item 1's predicates | The twin gate, and the chance to share rather than duplicate | Small |
| 3 | Test the three `_*_row_for_change_id` bodies against a fake BQ client | Idempotency SQL that no test executes | Small |
| 4 | Resolve "Faixa de valor" — delete it, or gate the citation like the chip row | A latent label/number disagreement | Small |

Items 3 and 4 are small and independent; item 1 is the only one that touches a hot write
path and should carry its own PR.
