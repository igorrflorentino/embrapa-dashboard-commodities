{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partition_by={
            'field': 'reference_year',
            'data_type': 'int64',
            'range': {'start': 1970, 'end': 2050, 'interval': 1}
        },
        cluster_by=['state_acronym', 'product_code', 'variable_code'],
        on_schema_change='append_new_columns'
    )
}}

{#-
    Silver for IBGE PAM (Produção Agrícola Municipal, SIDRA 5457).

    Same incremental + dedupe shape as silver_ibge_pevs (insert_overwrite by
    reference_year; keep the latest ingestion per natural key), but for PAM's five
    measures (área plantada, área colhida, quantidade, rendimento, valor). It also
    shares the MEASURED SCOPE caveat documented in silver_ibge_pevs's header: this does not
    behave incrementally today — billed bytes are flat at ~3.1 GB/build, the signature of a
    full rebuild, because the `>=` boundary keeps re-including a whole-history ingestion
    batch (the monthly `reconcile`) until something newer displaces it. Not fixed on
    purpose: the `>=` is what prevents a same-second append from being skipped forever, and
    the project sits at ~15% of BigQuery's free tier, so this costs nothing today. LONG
    format — one row per (year, city, product, variable); gold_pam_production
    pivots it into measure columns.

    CURRENCY REFORM: the monetary variable (215) is converted to nominal Reais by
    the date-aware historical_currency_factors join (same as silver_ibge_pevs) — the
    factor embeds the "Mil" multiplier AND the cumulative reform divisions, so the
    full PAM history (back to 1974: Mil Cruzeiros/Cruzados/Cruzados Novos/Cruzeiros
    Reais → R$) lands correct. PAM_START_YEAR can therefore go to 1974 without the
    10^6–10^9× pre-1994 blow-up that the old ×1000 hardcode would have caused.
-#}

{% set var_quantity = var("pam_variable_quantity") %}
{% set var_value = var("pam_variable_value") %}
{% set kept_variables = [
    var("pam_variable_area_planted"),
    var("pam_variable_area_harvested"),
    var_quantity,
    var("pam_variable_yield"),
    var_value,
] %}

{% if is_incremental() %}
with affected_years as (

    -- `>=` (not `>`): re-scan the boundary year so a clock-identical double load
    -- isn't skipped forever; insert_overwrite makes re-processing a year idempotent.
    select distinct ano
    from {{ source('bronze_pam', 'sidra_raw') }}
    where ingestion_timestamp >= (select coalesce(max(ingestion_timestamp), timestamp '1970-01-01') from {{ this }})

),

deduplicated as (

    select b.*
    from {{ source('bronze_pam', 'sidra_raw') }} b
    inner join affected_years ay on b.ano = ay.ano
    where b.variavel_codigo in ({{ "'" ~ kept_variables | join("','") ~ "'" }})
      and b.nivel_territorial = 'Município'
    qualify row_number() over (
        partition by b.ano, b.municipio_codigo, b.produto_das_lavouras_temporarias_e_permanentes_codigo, b.variavel_codigo, lower(trim(b.unidade_de_medida))
        order by b.ingestion_timestamp desc
    ) = 1

),
{% else %}
with deduplicated as (

    -- Bronze is append-only; keep only the latest ingestion per natural key.
    select *
    from {{ source('bronze_pam', 'sidra_raw') }}
    where variavel_codigo in ({{ "'" ~ kept_variables | join("','") ~ "'" }})
      and nivel_territorial = 'Município'
    qualify row_number() over (
        partition by ano, municipio_codigo, produto_das_lavouras_temporarias_e_permanentes_codigo, variavel_codigo, lower(trim(unidade_de_medida))
        order by ingestion_timestamp desc
    ) = 1

),
{% endif %}

parsed as (

    select
        cast(ano as int64)                                                          as reference_year,
        municipio_codigo                                                            as city_code,
        regexp_replace(municipio, r'\s-\s[A-Z]{2}$', '')                            as city_name,
        regexp_extract(municipio, r'\s-\s([A-Z]{2})$')                              as state_acronym,
        produto_das_lavouras_temporarias_e_permanentes_codigo                       as product_code,
        trim(produto_das_lavouras_temporarias_e_permanentes)                        as product_description,
        variavel_codigo                                                             as variable_code,
        variavel                                                                    as variable_name,
        unidade_de_medida                                                           as unit_of_measure,
        {{ safe_numeric('valor', dash_is_zero=true) }}                              as raw_numeric_value,
        ingestion_timestamp
    from deduplicated

)

select
    p.reference_year,
    p.city_code,
    p.city_name,
    p.state_acronym,
    p.product_code,
    p.product_description,
    p.variable_code,
    p.variable_name,
    p.unit_of_measure,

    -- Monetary value (var 215): apply the date-aware currency seed factor (same as
    -- silver_ibge_pevs). The factor embeds BOTH the "Mil" multiplier AND the
    -- cumulative reform divisions (Cz$→…→R$), so a backfill below 1994 (Mil
    -- Cruzeiros/Cruzados/etc.) lands in nominal R$ instead of 10^6–10^9× too large.
    -- The year range disambiguates the reused "Mil Cruzeiros" label. Every other
    -- variable (area ha, quantity t, yield kg/ha) passes through unscaled.
    case
        when p.variable_code = '{{ var_value }}'
            -- ×1000 reform-boundary SOURCE correction (ibge_1985_cruzado_correction): IBGE's 1985
            -- "Mil Cruzeiros" value is magnitude-Cruzados; realigns it with 1984/1986. No-op else.
            then p.raw_numeric_value * fx.brl_factor
                 * {{ ibge_1985_cruzado_correction('p.reference_year', 'p.unit_of_measure') }}
        else p.raw_numeric_value
    end as numeric_value,

    case when p.variable_code = '{{ var_value }}' then true else false end as is_monetary_value,

    -- ── Physical-unit family (quantity rows only, var 214) ───────────────────
    -- Mirrors silver_ibge_pevs: unit_native is the source label; family/base_unit
    -- /to_base come from the generic unit-family seed (PAM has no per-product unit
    -- overrides). For the lean crop set the unit is always 'Toneladas' → massa/t.
    case when p.variable_code = '{{ var_quantity }}'
        then p.unit_of_measure end                          as unit_native,
    case when p.variable_code = '{{ var_quantity }}'
        then coalesce(ufp.family, ufc.family, 'desconhecida') end as family,
    case when p.variable_code = '{{ var_quantity }}'
        then coalesce(ufp.base_unit, ufc.base_unit) end     as base_unit,
    case when p.variable_code = '{{ var_quantity }}'
        then p.raw_numeric_value end                        as qty_native,
    case when p.variable_code = '{{ var_quantity }}'
        then p.raw_numeric_value * coalesce(ufp.to_base, ufc.to_base) end as qty_base,

    p.ingestion_timestamp
from parsed p
left join {{ ref('historical_currency_factors') }} fx
    on lower(trim(p.unit_of_measure)) = lower(trim(fx.unit_of_measure))
    and p.reference_year between fx.year_from and fx.year_to
left join {{ ref('unit_family_conversions') }} ufc
    on lower(trim(p.unit_of_measure)) = ufc.unit_raw
-- Per-product unit override, wired identically to silver_ibge_pevs so all three IBGE
-- silvers behave uniformly (DBT-4). Staged/inert today: product_unit_factors ships only
-- source='_reference' sentinel rows, so no 'pam' unit is overridden yet — but a future
-- per-product PAM factor now takes effect (matching PEVS) instead of silently no-op-ing.
left join {{ ref('product_unit_factors') }} ufp
    on ufp.source = 'pam'
    and ufp.product_code = p.product_code
    and lower(trim(p.unit_of_measure)) = ufp.unit_raw
