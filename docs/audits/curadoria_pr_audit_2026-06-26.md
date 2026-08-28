# Curadoria PR — pre-merge bug audit (2026-06-26)

> ⚠️ **HISTÓRICO — relatório pontual, não é uma lista de pendências.** Auditoria de 2026-06-26, sobre o PR da Curadoria (pré-merge), muito anterior ao estado atual do repositório. Seus achados foram tratados na época (veja o `CHANGELOG`); trate caminhos, contagens e estrutura aqui como o retrato daquela data, **não** como o código de hoje. Mantido por proveniência — em especial os achados refutados, que não existem em nenhum outro lugar.

Adversarial multi-agent audit of the Curadoria feature PR (branch
`claude/charming-brown-bc2a4d`, base `main`; 42 files, +3976/−806, commits P0–P5)
run **before merge**. Six dimension-finders (catalog writer / orphan-purge /
security / dbt / frontend / integration) read the real code, then a skeptic
adversarially verified each finding (default-refute). 15 raw findings → **14
survived verification** → 11 distinct defects after de-duplication.

## Verdict

**Healthy, well-architected feature; safe to merge after the write-contract gaps
were closed.** Zero Critical. **No security hole, no SQL-injection path, no
automatic data-loss path, no crash.** Every finding is a write-time
input-validation gap or a downstream-staleness/UX issue. One root cause dominates:
*the write contract was looser than the downstream dbt `not_null` tests and the
orphan-prefix `LIKE` assume.*

Verified **clean**: parameterized DML (no injection), the human-gated purge (never
auto-executes DELETEs), the orphan 2-step detection's efficiency + non-destructiveness,
IAP-author capture + idempotency, the 191=191 cutover, fail-loud reads (no silent
fallback to the retired seed), and the P0 3-way split.

## Findings & remediation (all fixed in this PR)

| ID | Sev | Finding | Fix |
|----|-----|---------|-----|
| H-1 | High | Blank Agrupamento → NULL `agrupamento_id`/`agrupamento_nome` → breaks the nightly prod `dbt build` (`not_null` tests). Reachable via the admin UI. | Reject empty `agrupamento_id`/`agrupamento` at the write gate (`curation.record_produto_catalog`); mirror client-side in `ViewCadastroProdutos.submitAdd`. |
| M-1 | Med | Whitespace-only `code_prefix` → `''` → `LIKE '%'` matches **every** code in the banco (silent fan-out). | Reject empty + LIKE-wildcard (`%`/`_`) `code_prefix` at the write gate. |
| M-2 | Med | `remove` hardcoded `codigo_produto` into the tombstone's `code_prefix` slot → orphan detection (which keys off that prefix) silently no-ops for coarse-prefix entries. | Look up the active entry's real `code_prefix` and carry it into the tombstone. |
| M-3 | Med | Re-orphan after a prior descontinuado/purge was never re-marked (deterministic `change_id` + status gate) and could not be re-purged. | Generation-aware re-mark: expose the tombstone's `removed_at`, compare it to the last lifecycle `flagged_at`, and key the `change_id` on the generation. |
| M-4 | Med | The prefix-overlap (and other writer) reason was masked by a generic 400 message → researcher could not self-correct. | `errorhandler(ValueError)` now surfaces `str(exc)`; catalog + attribute-engineering writer messages made pt-BR. |
| M-5 | Med | A mid-loop failure in the per-Agrupamento bulk ciclo update left a stale, partially-applied grid. | Reload the grid in `run`'s `finally` (re-sync to persisted state); report how many members applied before the failure. |
| L-1 | Low | `remove` of a never-cataloged key wrote a phantom tombstone → false orphan. | Require a currently-active entry before tombstoning (the same M-2 lookup). |
| L-2 | Low | (folds into H-1) NULL `agrupamento_id` polluted the cross-source picker. | Covered by the H-1 write-time guard. |
| L-3 | Low | `purge_plan` regex permitted `_` (a LIKE single-char wildcard) in the printed DELETE. | Drop `_` from the allowed character class. |
| L-4 | Low | `orphan_worklist` hardcoded `status='descontinuado'`, ignoring an actual `'purged'`. | Use the recorded `st.status`; fall back to the standing warning when a purged event has no note. |
| L-5 | Low | `fetch_catalog_editors` was omitted from `_bind_classification_ttl`, so its auth-gate TTL ignored `CACHE_CLASSIFICATION_TIMEOUT`. | Rebind it alongside the other classification reads. |

## Tests

New/updated: write-contract rejection tests (blank agrupamento, blank/wildcard
prefix), tombstone real-prefix + uncataloged-key rejection (M-2/L-1), generation-aware
re-mark (M-3), errorhandler reason-surfacing (M-4, + pt-BR writer messages),
purged-status worklist (L-4), catalog-editor TTL bind (L-5), and frontend coverage
for the H-1 client guard + the M-5 partial-failure reload.

Suite: **947 pytest / 275 vitest green**; ruff + ruff-format + eslint clean.
