{{ config(materialized='view') }}

-- ────────────────────────────────────────────────────────────────────────────
-- dim_produto_catalog — the CURRENT commodity catalog (Curadoria).
--
-- The editable successor to the version-controlled `commodity_crosswalk` seed: the
-- researcher-managed catalog of which commodities are in the dashboard and their
-- agrupamento (cross-source concept). Each commodity is registered by its EXACT
-- source code (`codigo_produto`; no prefixes). Written append-only by the
-- dashboard's admin editor (the Python data-access layer, never dbt) to
-- research_inputs.produto_catalog_log; this view derives the CURRENT catalog = the
-- latest row per (codigo_produto, banco), keeping only active rows (a row with
-- active=false is a tombstone — the entry has LEFT the catalog, so its Gold data
-- becomes an orphan, handled non-destructively downstream).
--
-- Exposes (agrupamento_id, agrupamento_nome, source, codigo_produto) — the consumers
-- (gold_produto_agrupamento + serving_{pam,ppm}_annual) join on `code = codigo_produto`
-- (equality; no LIKE-prefix expansion).
--
-- Materialized as a VIEW on purpose: the log is small and a fresh admin edit is then
-- visible to the next build / request immediately, with no rebuild.
--
-- NOT gated by enable_curation (unlike dim_code_industrialization_scd2): this is the
-- LIVE catalog the gold model reads — it must exist. The source table is created on
-- the first write / the cutover backfill; a fresh project must backfill it (fail loud
-- if absent — never silently fall back to the retired seed).
--
-- ⚠ Grain: one row per (codigo_produto, banco). Because every code is exact (no
-- prefixes), a Gold code resolves to AT MOST one commodity, so the cross-source join
-- cannot fan out — guarded at build time by the unique_combination_of_columns(source,
-- code) test on gold_produto_agrupamento.
-- ────────────────────────────────────────────────────────────────────────────

with log as (

    select
        codigo_produto,
        banco,
        agrupamento,
        descricao_produto,
        ciclo_de_vida,
        {{ catalog_ingestao() }} as ingestao,
        {{ catalog_visibilidade() }} as visibilidade,
        agrupamento_id,
        active,
        edited_by,
        edited_at,
        change_id
    from {{ source('research_inputs', 'produto_catalog_log') }}

),

current_catalog as (

    select
        *,
        -- Latest-wins per key. Tie-breaker note: on a same-microsecond `edited_at` tie the
        -- random `change_id` decides — deterministic, but NOT necessarily true write-order.
        -- Unreachable in practice (the change_id idempotency guard dedups double-clicks, and a
        -- human can't submit two DIFFERENT edits to one key in one microsecond; the seed writes
        -- distinct keys). A truly monotonic tie-breaker would need cross-instance coordination
        -- this architecture lacks; the unique_combination test on this model (and on
        -- dim_produto_visibility) is the backstop that turns any real multi-active row into a
        -- red build. This ORDER BY is replicated across the serving readers — change together.
        row_number() over (
            partition by {{ chave_produto() }}
            order by edited_at desc, change_id desc
        ) as _rn
    from log

)

select
    agrupamento_id,
    agrupamento     as agrupamento_nome,
    banco           as source,
    codigo_produto,
    descricao_produto,
    -- The lifecycle, as the two EFFECTIVE coded axes (legacy prose already translated by
    -- the catalog_lifecycle macros). ciclo_de_vida is kept for history/audit only.
    ciclo_de_vida,
    ingestao,
    visibilidade,
    edited_by,
    edited_at
from current_catalog
where _rn = 1 and active
