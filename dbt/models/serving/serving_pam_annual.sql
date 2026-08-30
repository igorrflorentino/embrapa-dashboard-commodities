{{
    config(
        materialized='table',
        partition_by={
            'field': 'reference_year',
            'data_type': 'int64',
            'range': {'start': 1970, 'end': 2050, 'interval': 1}
        },
        cluster_by=['state_acronym', 'product_code']
    )
}}

-- ────────────────────────────────────────────────────────────────────────────
-- serving_pam_annual — pre-aggregated IBGE PAM mart for Pushdown Computing.
--
-- COLUMN-IDENTICAL to serving_pevs_annual (plus area_* extras) so the generic,
-- source-parameterized gateway readers (fetch_products / fetch_product_timeseries
-- / fetch_production_overview / fetch_production_by_uf) serve PAM with no
-- per-source SQL — PAM rides the entire PEVS-shaped snapshot and the
-- currency/correction toggles for free.
--
-- Rolls gold_pam_production (year × UF × CITY × product) up to
-- (year × UF × product × family), dropping the municipality grain. Area columns
-- are summed (additive across cities); yield is intentionally NOT carried (a
-- ratio is not summable — recompute as qty/area in the future área/rendimento
-- expansion). Grain: one row per (reference_year, state_acronym, product_code, family).
-- ────────────────────────────────────────────────────────────────────────────

with pam as (

    select
        reference_year,
        state_acronym,
        product_code,
        -- A TABELA no grão, como em todos os bancos. Constante aqui (banco de UMA tabela
        -- só), e é justamente por isso que precisa estar: com o trio valendo nos cinco, a
        -- mart tem a MESMA forma em todos e o consumidor não ramifica por banco.
        tabela,
        family,
        any_value(product_description)  as product_description,
        any_value(base_unit)            as base_unit,
        any_value(unit_native)          as unit_native,
        -- qty_native / qty_base summed WITHIN a family (family is in the grain) —
        -- never the forbidden cross-family sum. Monetary values are family-agnostic.
        sum(qty_native)                 as qty_native,
        sum(qty_base)                   as qty_base,
        sum(area_planted_ha)            as area_planted_ha,
        sum(area_harvested_ha)          as area_harvested_ha,
        sum(val_yearfx_brl)             as val_yearfx_brl,
        sum(val_yearfx_usd)             as val_yearfx_usd,
        -- EUR carried alongside BRL/USD (real BCB BRL/EUR series).
        sum(val_yearfx_eur)             as val_yearfx_eur,
        sum(val_real_ipca_brl)          as val_real_ipca_brl,
        sum(val_real_ipca_usd)          as val_real_ipca_usd,
        sum(val_real_ipca_eur)          as val_real_ipca_eur,
        -- IGP-M / IGP-DI deflation is carried in BRL and EUR only. The USD-deflated
        -- combos (val_real_{igpm,igpdi}_usd) are intentionally NOT served: the BFF
        -- allowlist (serving/sql.ALLOWED_VALUE_COLUMNS) omits them, so the serving
        -- layer can never SELECT them — materializing them here would be dead bytes.
        sum(val_real_igpm_brl)          as val_real_igpm_brl,
        sum(val_real_igpm_eur)          as val_real_igpm_eur,
        sum(val_real_igpdi_brl)         as val_real_igpdi_brl,
        sum(val_real_igpdi_eur)         as val_real_igpdi_eur,
        -- city_code, not city_name: the name is a display label and two
        -- municipalities can share one (Gold groups by city_code for the same
        -- reason), so counting names could silently undercount.
        count(distinct city_code)       as n_cities,
        count(*)                        as source_rows,
        max(last_refresh)               as last_refresh
    from {{ ref('gold_pam_production') }}
    where {{ hidden_code_predicate('pam', 'product_code') }}
    group by reference_year, state_acronym, product_code, tabela, family

),

pam_codes as (

    select distinct product_code
    from pam

),

-- Cross-source commodity linkage. gold_produto_agrupamento can NEVER emit
-- source='pam' rows — its source_codes CTE only scans the PEVS/COMEX/COMTRADE
-- facts, and its accepted_values tests reject 'pam' — so the code linkage is
-- replicated here, directly against the PAM codes in this mart. Cataloguing a 'pam'
-- commodity in the editable Curadoria catalog (research_inputs.produto_catalog_log →
-- dim_produto_catalog; the retired commodity_crosswalk seed's successor) is then enough
-- to light up agrupamento_id/agrupamento_nome. With no pam commodity catalogued yet, both
-- columns come out NULL (the dashboard handles NULL commodity).
pam_xwalk as (

    select distinct
        x.agrupamento_id,
        x.agrupamento_nome,
        c.product_code as code
    from pam_codes c
    -- Junta sem a tabela SIDRA, e aqui isso NÃO é suposição: o PAM é banco de tabela
    -- única (5457), então um código nunca aparece duas vezes na dim e o join não pode
    -- fazer fan-out. Nos bancos multi-tabela (PEVS, PPM) o join usa a chave inteira desde
    -- v1.46.0, quando o id da tabela passou a viajar no fato — antes disso ele era uma
    -- suposição de verdade, presa por `tests/assert_catalog_join_cannot_fan_out.sql`.
    join {{ ref('dim_produto_catalog') }} x
        on x.source = 'pam'
        and c.product_code = x.codigo_produto

)

select
    p.reference_year,
    date(p.reference_year, 12, 31)  as reference_date,
    p.state_acronym,
    g.state_name,
    g.region,
    g.region_abbrev,
    x.agrupamento_id,
    x.agrupamento_nome,
    p.product_code,
    p.tabela,
    p.product_description,
    p.family,
    p.base_unit,
    p.unit_native,
    p.qty_native,
    p.qty_base,
    p.area_planted_ha,
    p.area_harvested_ha,
    p.val_yearfx_brl,
    p.val_yearfx_usd,
    p.val_yearfx_eur,
    p.val_real_ipca_brl,
    p.val_real_ipca_usd,
    p.val_real_ipca_eur,
    p.val_real_igpm_brl,
    p.val_real_igpm_eur,
    p.val_real_igpdi_brl,
    p.val_real_igpdi_eur,
    p.n_cities,
    p.source_rows,
    p.last_refresh
from pam p
left join {{ ref('dim_geo_br') }} g
    on g.state_acronym = p.state_acronym
left join pam_xwalk x
    on x.code = p.product_code
