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
-- serving_ppm_annual — pre-aggregated PPM (livestock) mart for Pushdown Computing.
--
-- Rolls gold_ppm_production (year × UF × CITY × product) up to
-- (year × UF × product × family), dropping the municipality grain. Column-shaped
-- like serving_pevs_annual (NO área/yield — PPM is livestock), plus measure_kind so
-- a herd STOCK (Cabeças) is never conflated with an animal-production FLOW.
--
-- Keeping `family` IN the grain is non-negotiable for PPM: its products span
-- contagem (herd/eggs), volume (milk) and massa (honey/wool), so qty_native/qty_base
-- are only ever summed WITHIN a family — never the forbidden cross-family sum.
--
-- Backs (frontend_data_contract.md §3): overviewTS (GROUP BY year), productTS
-- (GROUP BY year, product_code), ufData (GROUP BY state_acronym).
--
-- Grain: one row per (reference_year, state_acronym, product_code, family).
-- ────────────────────────────────────────────────────────────────────────────

with ppm as (

    select
        reference_year,
        state_acronym,
        product_code,
        family,
        any_value(product_description)  as product_description,
        any_value(sidra_tabela)         as sidra_tabela,
        any_value(measure_kind)         as measure_kind,
        any_value(base_unit)            as base_unit,
        any_value(unit_native)          as unit_native,
        -- Summed WITHIN a family (family is in the grain) — never cross-family.
        sum(qty_native)                 as qty_native,
        sum(qty_base)                   as qty_base,
        sum(val_yearfx_brl)             as val_yearfx_brl,
        sum(val_yearfx_usd)             as val_yearfx_usd,
        sum(val_yearfx_eur)             as val_yearfx_eur,
        sum(val_real_ipca_brl)          as val_real_ipca_brl,
        sum(val_real_ipca_usd)          as val_real_ipca_usd,
        sum(val_real_ipca_eur)          as val_real_ipca_eur,
        -- IGP-M / IGP-DI deflation carried in BRL and EUR only (the BFF allowlist
        -- omits the USD-deflated combos, so materializing them would be dead bytes).
        sum(val_real_igpm_brl)          as val_real_igpm_brl,
        sum(val_real_igpm_eur)          as val_real_igpm_eur,
        sum(val_real_igpdi_brl)         as val_real_igpdi_brl,
        sum(val_real_igpdi_eur)         as val_real_igpdi_eur,
        count(distinct city_code)       as n_cities,
        count(*)                        as source_rows,
        max(last_refresh)               as last_refresh
    from {{ ref('gold_ppm_production') }}
    where {{ hidden_code_predicate('ppm', 'product_code') }}
    group by reference_year, state_acronym, product_code, family

),

ppm_codes as (

    -- A tabela entra no distinct porque o join abaixo passou a usá-la: sem ela a CTE
    -- colapsaria as duas metades num código só e o join perderia a chave que veio buscar.
    select distinct product_code, sidra_tabela
    from ppm

),

-- Cross-source commodity linkage. gold_produto_agrupamento can NEVER emit
-- source='ppm' rows — its source_codes CTE only scans the PEVS/COMEX/COMTRADE facts,
-- and its accepted_values tests reject 'ppm' — so the exact-code linkage is replicated
-- here against the PPM codes in this mart. Cataloguing a 'ppm' commodity (source='ppm')
-- in dim_produto_catalog is then enough to light up agrupamento_id/agrupamento_nome. With
-- no ppm commodity catalogued yet, both columns come out NULL (the dashboard handles
-- NULL commodity).
ppm_xwalk as (

    select distinct
        x.agrupamento_id,
        x.agrupamento_nome,
        c.product_code as code
    from ppm_codes c
    -- Junta pela CHAVE INTEIRA (source, código, tabela), que é o grão da dim desde
    -- v1.39.0. Até v1.46.0 este join omitia a tabela e isso era uma SUPOSIÇÃO documentada:
    -- o Gold carregava um discriminador semântico (`measure_kind`), não o id da tabela, e
    -- escrever o mapeamento `stock↔3939 / flow↔74` aqui teria sido uma quarta cópia dele.
    -- Um código presente nas duas tabelas devolveria DUAS linhas e o join duplicaria os
    -- valores do fato, em silêncio. Agora o id viaja no fato e a suposição some.
    join {{ ref('dim_produto_catalog') }} x
        on x.source = 'ppm'
        and c.product_code = x.codigo_produto
        and c.sidra_tabela = x.sidra_tabela

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
    p.product_description,
    p.sidra_tabela,
    p.measure_kind,
    p.family,
    p.base_unit,
    p.unit_native,
    p.qty_native,
    p.qty_base,
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
from ppm p
left join {{ ref('dim_geo_br') }} g
    on g.state_acronym = p.state_acronym
left join ppm_xwalk x
    on x.code = p.product_code
