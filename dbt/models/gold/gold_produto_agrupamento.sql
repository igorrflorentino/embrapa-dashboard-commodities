{{ config(materialized='table') }}

-- ────────────────────────────────────────────────────────────────────────────
-- gold_produto_agrupamento — cross-source product bridge (RESOLVED to exact codes).
--
-- The same physical commodity wears a different code in each source: PEVS uses
-- an extractive-product code, COMEX an 8-digit NCM, COMTRADE a 6-digit HS. Every
-- cross-source analysis (export coefficient, world market share, price spread,
-- trade mirror, harvest→shipment lag) must join the SAME commodity across them —
-- and that link is domain knowledge, not a SELECT DISTINCT.
--
-- The editable Curadoria catalog registers each commodity by its EXACT source code
-- (`codigo_produto`; no prefixes). This model joins those codes to the codes that
-- actually appear in each Gold fact table, emitting exact (source, code) → commodity
-- rows so a consumer joins on equality. A Gold code not in the catalog is simply
-- absent here → "unlinked" (graceful degradation), never an error.
--
-- Grain: one row per (source, code). source ∈ {pevs, comex, comtrade}.
--
-- ⚠ INVARIANT (load-bearing): (codigo_produto, source) is unique in the catalog, and
-- the join below is a plain equality `code = codigo_produto`, so a Gold code resolves
-- to AT MOST one agrupamento_id — the cross-source LEFT JOIN in the serving marts cannot
-- FAN OUT and double any qty_base/val_* sum. The `dbt_utils.unique_combination_of_columns`
-- test on (source, code) in _gold.yml is the build-time guard that trips if this is ever
-- broken (e.g. the same code cataloged under two commodities).
-- ────────────────────────────────────────────────────────────────────────────

with xwalk as (

    -- The editable Curadoria catalog (dim_produto_catalog), the SOT that replaced
    -- the commodity_crosswalk seed. Each row is one exact (source, codigo_produto).
    -- A produto registered WITHOUT an agrupamento (agrupamento_id null) can't be
    -- cross-linked, so it is excluded from the crosswalk — matching the serving
    -- layer's produto_catalog() skip. Keeps agrupamento_id/_nome NOT NULL here (and
    -- those produtos still appear in single-banco views via gold_<source>_production).
    select agrupamento_id, agrupamento_nome, source, codigo_produto
    from {{ ref('dim_produto_catalog') }}
    where agrupamento_id is not null

),

source_codes as (

    -- PAM and PPM joined the bridge in 2026-08 (the coordinated change this note
    -- used to reserve: union below + accepted_values in _gold.yml + the buckets in
    -- webapi/seam_base.produto_catalog, which would KeyError on an unknown source).
    --
    -- It changes NO existing computation: every cross-source view asks for its
    -- sources BY NAME (seam_base._codes(agrupamento_id, 'pevs') for the export
    -- coefficient, 'comex'/'comtrade' for market share), so nothing sums across
    -- production sources behind the researcher's back. What it adds is CHOICE —
    -- the multi-fonte picker is series-oriented, so PAM/PPM simply become series a
    -- researcher can place on the axis next to PEVS, and decide for themselves
    -- whether extractive and cultivated output belong side by side or added up.
    -- An aggregate "extractive + cultivated" metric, if ever wanted, must be its
    -- own NAMED metric — never a silent change to an existing denominator.
    select distinct 'pevs' as source, product_code as code
    from {{ ref('gold_pevs_production') }}
    union all
    select distinct 'pam' as source, product_code as code
    from {{ ref('gold_pam_production') }}
    union all
    select distinct 'ppm' as source, product_code as code
    from {{ ref('gold_ppm_production') }}
    union all
    select distinct 'comex' as source, ncm_code as code
    from {{ ref('gold_comex_flows') }}
    union all
    select distinct 'comtrade' as source, cmd_code as code
    from {{ ref('gold_comtrade_flows') }}

)

select distinct
    x.agrupamento_id,
    x.agrupamento_nome,
    c.source,
    c.code
from source_codes c
join xwalk x
    on c.source = x.source
    and c.code = x.codigo_produto
