{{
    config(
        materialized='table',
        partition_by={
            'field': 'reference_year',
            'data_type': 'int64',
            'range': {'start': 1970, 'end': 2050, 'interval': 1}
        },
        cluster_by=['state_acronym', 'product_code', 'city_name']
    )
}}

-- ────────────────────────────────────────────────────────────────────────────
-- gold_ppm_production — comprehensive IBGE PPM (livestock) fact.
--
-- Pivots silver_ibge_ppm's LONG measure rows into one row per
-- (year × UF × CITY × product) carrying qty_native (in the product's own family —
-- Cabeças/contagem for herd, Mil litros/volume + Quilogramas/massa + Mil dúzias/
-- contagem for animal production) and val_raw (nominal R$, animal production only).
-- The monetary measure gets the SAME FX + inflation deflation matrix as
-- gold_pevs_production / gold_pam_production, so PPM rides the identical currency/
-- correction toggles in the dashboard.
--
-- DIVERGES from gold_pam_production: PPM is LIVESTOCK, so it has NO área plantada/
-- colhida/rendimento (no 'yield' capability). It DOES carry a `measure_kind`
-- discriminator: 'stock' (efetivo dos rebanhos — a headcount with NO price) vs
-- 'flow' (animal production — quantity + value). A stock row's val_* are NULL by
-- design; the quality flag treats a stock as OK on quantity alone (value is N/A,
-- not "missing").
--
-- NOTE: val_raw is nominal R$ for the FULL history — silver_ibge_ppm applies the
-- date-aware historical_currency_factors join, so pre-1994 years (Mil Cruzeiros/
-- Cruzados/…) are reform-corrected. Foreign-FX columns (val_yearfx_{usd,eur}) stay
-- NULL pre-1994; val_real_* (BRL, inflation-deflated) is valid wherever the index
-- covers the year.
-- ────────────────────────────────────────────────────────────────────────────

with base_ppm as (

    select
        reference_year,
        state_acronym,
        city_code,
        any_value(city_name)            as city_name,
        product_code,
        any_value(product_description)  as product_description,
        -- Per product there is one SIDRA table (3939 herd | 74 animal production) and
        -- one physical unit → any_value/max lift them. `sidra_tabela` is part of the
        -- produto's IDENTITY (banco, tabela, código); `measure_kind` is derived from it
        -- upstream and rides along because it answers a different question — "does this
        -- row have a price?" — that five views ask directly.
        any_value(sidra_tabela)         as sidra_tabela,
        any_value(measure_kind)         as measure_kind,
        max(family)                     as family,
        max(unit_native)                as unit_native,
        max(base_unit)                  as base_unit,
        max(qty_native)                 as qty_native,
        max(qty_base)                   as qty_base,
        max(case when is_monetary_value then numeric_value end) as val_raw,
        max(ingestion_timestamp)        as last_refresh
    from {{ ref('silver_ibge_ppm') }}
    group by reference_year, state_acronym, city_code, product_code
    having qty_native is not null
        or val_raw    is not null

),

{{ annual_deflation_ctes() }},

enriched as (

    select
        b.*,
        fy.brl_per_usd_avg,
        fy.brl_per_eur_avg,
        fxl.brl_per_usd_current,
        fxl.brl_per_eur_current,

        -- Real BRL via each inflation chain (val_raw already nominal present-era R$).
        b.val_raw * safe_divide(il.ipca_current,  iy.ipca_year_end)  as val_real_ipca_brl,
        b.val_raw * safe_divide(il.igpm_current,  iy.igpm_year_end)  as val_real_igpm_brl,
        b.val_raw * safe_divide(il.igpdi_current, iy.igpdi_year_end) as val_real_igpdi_brl

    from base_ppm b
    left join fx_year            fy  on b.reference_year = fy.reference_year
    left join inflation_year_end iy  on b.reference_year = iy.reference_year
    cross join inflation_latest  il
    cross join fx_latest         fxl

)

select
    -- ── Time ─────────────────────────────────────────────────────────────────
    reference_year,
    date(reference_year, 12, 31)                             as reference_date,

    -- ── Geography ────────────────────────────────────────────────────────────
    state_acronym,
    {{ state_name('state_acronym') }}                        as state_name,
    {{ state_region('state_acronym') }}                      as region,
    city_code,
    city_name,

    -- ── Product + measure nature ─────────────────────────────────────────────
    product_code,
    product_description,
    -- 'stock' (herd headcount, no price) vs 'flow' (animal production, qty + value).
    sidra_tabela,
    measure_kind,

    -- ── Quantities (physical-unit family — contagem/volume/massa per product) ──
    family,
    unit_native,
    qty_native,
    qty_base,
    base_unit,

    -- ── Year-FX: val_raw converted via FX of THAT year ──────────────────────
    -- Foreign-FX columns are NULL pre-1994; stock rows have NULL val_raw → all NULL.
    val_raw                                                  as val_yearfx_brl,
    case when reference_year >= 1994
        then safe_divide(val_raw, brl_per_usd_avg) end       as val_yearfx_usd,
    case when reference_year >= 1994
        then safe_divide(val_raw, brl_per_eur_avg) end       as val_yearfx_eur,

    -- ── Real via IPCA ─────────────────────────────────────────────────────────
    val_real_ipca_brl                                        as val_real_ipca_brl,
    safe_divide(val_real_ipca_brl, brl_per_usd_current)      as val_real_ipca_usd,
    safe_divide(val_real_ipca_brl, brl_per_eur_current)      as val_real_ipca_eur,

    -- ── Real via IGP-M ───────────────────────────────────────────────────────
    val_real_igpm_brl                                        as val_real_igpm_brl,
    safe_divide(val_real_igpm_brl, brl_per_usd_current)      as val_real_igpm_usd,
    safe_divide(val_real_igpm_brl, brl_per_eur_current)      as val_real_igpm_eur,

    -- ── Real via IGP-DI ──────────────────────────────────────────────────────
    val_real_igpdi_brl                                       as val_real_igpdi_brl,
    safe_divide(val_real_igpdi_brl, brl_per_usd_current)     as val_real_igpdi_usd,
    safe_divide(val_real_igpdi_brl, brl_per_eur_current)     as val_real_igpdi_eur,

    -- ── Quality + provenance ─────────────────────────────────────────────────
    -- Stock rows (efetivo) have NO value by design → OK on quantity alone; flow rows use the
    -- standard qty+value rule via data_quality_flag (the full taxonomy when enable_quality_outliers
    -- is on, legacy 4-value when off). Stock rows only ever emit OK / MISSING_QUANTITY.
    case
        when measure_kind = 'stock'
            then case when qty_native is not null then 'OK' else 'MISSING_QUANTITY' end
        else {{ data_quality_flag('qty_native', 'val_raw',
                 quality_qty_level('val_real_ipca_brl', 'qty_native'),
                 quality_val_level('val_real_ipca_brl', 'qty_native')) }}
    end                                                      as data_quality_flag,
    last_refresh

from {% if var('enable_quality_outliers', false) -%}
(
    select e.*,
{{ quality_scored_bounds('val_real_ipca_brl', 'qty_native') }}
    from enriched e
    window _qw as (partition by product_code, family)
) enriched
{%- else -%}
enriched
{%- endif %}
