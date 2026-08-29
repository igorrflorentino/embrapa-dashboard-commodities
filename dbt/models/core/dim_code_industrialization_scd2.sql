{{
    config(
        materialized='view',
        schema=env_var('BQ_SERVING_DATASET', 'serving'),
        enabled=var('enable_curation', false)
    )
}}

-- Researcher-editable per-code industrialization (bruta/processada). This model
-- self-disables via the `enable_curation` flag in the config above, so a prod build must
-- pass `--vars 'enable_curation: true'` to materialize it (and thus the value-added analysis
-- + the industrialization editor's reads). The SAME var gates dim_flow_market_scd2 (the
-- (customs procedure × flow) market-nature) — both derived attributes are edit-driven again.

-- ────────────────────────────────────────────────────────────────────────────
-- dim_code_industrialization_scd2 — Type-2 SCD over the researchers' append-only
-- per-CODE industrialization log. Classifies each raw Gold CODE (NCM / PEVS
-- product / HS6) on an open-vocabulary 8-level ordinal scale from a raw commodity
-- (Commodity Pura) to a specialized manufactured good (Manufaturado Especializado)
-- — the level the value-added analysis needs to split COMEX exports.
--
-- Each "Aplicar" in the Curadoria panel appends ONE immutable row to
-- research_inputs.code_industrialization_log (written by the Python data-access
-- layer, never by dbt) — the Gold tables are NEVER overwritten. This view derives
-- the timeline per (source, code):
--   valid_from = edited_at of this version
--   valid_to   = LEAD(edited_at) — when the next edit superseded it (NULL = open)
--   is_current = valid_to IS NULL
--
-- Materialized as a VIEW on purpose: the log is small, and a view means a fresh
-- INSERT from the curation panel is visible to the UI immediately, with no dbt
-- rebuild. The dashboard LEFT JOINs the Gold code universe (DISTINCT codes) to
-- this live dim on (source, code) filtered to is_current — an unclassified code
-- surfaces as "a classificar" (the dynamic worklist).
--
-- Grain: one row per (source, code, version).
-- ────────────────────────────────────────────────────────────────────────────

with log as (

    select
        source,
        code,
        industrialization_level,
        note,
        edited_by,
        edited_at,
        change_id,
        -- Parte da identidade do produto (banco/source + TABELA + código): PPM e PEVS
        -- unem duas tabelas SIDRA sob um token só. Precisa vir até aqui porque a window
        -- de versionamento particiona por ela.
        sidra_tabela
    from {{ source('research_inputs', 'code_industrialization_log') }}

),

versioned as (

    select
        source,
        code,
        industrialization_level,
        note,
        edited_by,
        edited_at,
        sidra_tabela,
        -- Order by edit time, breaking ties on the surrogate change_id so two
        -- edits in the same instant still get a deterministic version sequence.
        row_number() over w     as version,
        lead(edited_at) over w  as valid_to
    from log
    window w as (partition by {{ chave_produto('code', 'source') }} order by edited_at, change_id)

)

select
    source,
    code,
    version,
    industrialization_level,
    note,
    edited_by,
    edited_at        as valid_from,
    valid_to,
    valid_to is null as is_current
from versioned
