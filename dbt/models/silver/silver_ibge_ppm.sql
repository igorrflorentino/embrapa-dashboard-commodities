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
    Silver for IBGE PPM (Pesquisa da Pecuária Municipal, SIDRA).

    PPM is MULTI-TABLE: this model UNIONs two Bronze tables that PEVS/PAM never had to —
      • bronze_ppm.herd_raw   (table 3939) — efetivo dos rebanhos (herd HEADCOUNT,
        variable 105, unit Cabeças). A STOCK with NO monetary value → measure_kind
        'stock'. Product dimension column: `tipo_de_rebanho[_codigo]`.
      • bronze_ppm.animal_raw (table 74)   — produção de origem animal (milk/eggs/
        honey/wool, variable 106 quantity + 215 value). A FLOW with value →
        measure_kind 'flow'. Product dimension column:
        `tipo_de_produto_de_origem_animal[_codigo]`.

    The two tables have DIFFERENT product-dimension columns and natural keys, so each is
    deduped on its OWN key (insert_overwrite + qualify by ingestion_timestamp desc, like
    silver_ibge_pevs/pam) and then unioned into one LONG shape — one row per (year, city,
    product, variable) plus a `measure_kind` discriminator.

    UNIT FAMILIES: unlike PAM (always Toneladas/massa), PPM emits MULTIPLE families in the
    same model — Cabeças→contagem, Mil litros→volume, Mil dúzias→contagem, Quilogramas→
    massa — resolved by the generic unit_family_conversions seed (the 'mil litros'/'mil
    dúzias' rows fold the SIDRA ×1000 "Mil" scale into to_base). qty_base is only summable
    WITHIN a family AND product_code (the serving layer keeps both in the grain).

    CURRENCY REFORM: the value variable (215, animal_raw only) rides the same date-aware
    historical_currency_factors join as PEVS/PAM — the factor embeds the "Mil" multiplier
    + the cumulative reform divisions, so the full history (Mil Cruzeiros/Cruzados/… → R$)
    lands correct. Herd (stock) rows have NO value → numeric_value passes through and
    is_monetary_value is false.
-#}

{% set var_herd = var("ppm_variable_herd") %}
{% set var_animal_qty = var("ppm_variable_animal_qty") %}
{% set var_value = var("ppm_variable_value") %}

{% set this_max %}(select coalesce(max(ingestion_timestamp), timestamp '1970-01-01') from {{ this }}){% endset %}

{% if is_incremental() %}
with affected_years as (

    -- Years touched by a newer ingestion in EITHER Bronze table (both are loaded
    -- together by `ingest ibge-ppm`). `>=` re-scans the boundary year; insert_overwrite
    -- makes re-processing a year idempotent.
    select distinct ano from {{ source('bronze_ppm', 'herd_raw') }}
    where ingestion_timestamp >= {{ this_max }}
    union distinct
    select distinct ano from {{ source('bronze_ppm', 'animal_raw') }}
    where ingestion_timestamp >= {{ this_max }}

),

herd_dedup as (

    select b.*
    from {{ source('bronze_ppm', 'herd_raw') }} b
    inner join affected_years ay on b.ano = ay.ano
    where b.variavel_codigo = '{{ var_herd }}'
      and b.nivel_territorial = 'Município'
    qualify row_number() over (
        partition by b.ano, b.municipio_codigo, b.tipo_de_rebanho_codigo, b.variavel_codigo, lower(trim(b.unidade_de_medida))
        order by b.ingestion_timestamp desc
    ) = 1

),

animal_dedup as (

    select b.*
    from {{ source('bronze_ppm', 'animal_raw') }} b
    inner join affected_years ay on b.ano = ay.ano
    where b.variavel_codigo in ('{{ var_animal_qty }}', '{{ var_value }}')
      and b.nivel_territorial = 'Município'
    qualify row_number() over (
        partition by b.ano, b.municipio_codigo, b.tipo_de_produto_de_origem_animal_codigo, b.variavel_codigo, lower(trim(b.unidade_de_medida))
        order by b.ingestion_timestamp desc
    ) = 1

),
{% else %}
with herd_dedup as (

    select *
    from {{ source('bronze_ppm', 'herd_raw') }}
    where variavel_codigo = '{{ var_herd }}'
      and nivel_territorial = 'Município'
    qualify row_number() over (
        partition by ano, municipio_codigo, tipo_de_rebanho_codigo, variavel_codigo, lower(trim(unidade_de_medida))
        order by ingestion_timestamp desc
    ) = 1

),

animal_dedup as (

    select *
    from {{ source('bronze_ppm', 'animal_raw') }}
    where variavel_codigo in ('{{ var_animal_qty }}', '{{ var_value }}')
      and nivel_territorial = 'Município'
    qualify row_number() over (
        partition by ano, municipio_codigo, tipo_de_produto_de_origem_animal_codigo, variavel_codigo, lower(trim(unidade_de_medida))
        order by ingestion_timestamp desc
    ) = 1

),
{% endif %}

parsed as (

    -- Herd (3939): a STOCK headcount; product dim = tipo_de_rebanho.
    --
    -- `sidra_tabela` é o FATO guardado — a identidade de um produto é
    -- (banco, tabela, código) — e `measure_kind` passa a ser DERIVADA dele lá na Gold.
    -- Antes só a prosa era guardada, e o id da tabela existia apenas como nome de
    -- tabela no Bronze. `measure_kind` NÃO foi aposentada junto com a `origem` do PEVS
    -- porque ela não é um apelido da tabela: cinco telas perguntam
    -- `measure_kind === 'stock'` para saber se a linha TEM PREÇO, e trocar isso por
    -- `sidra_tabela === '3939'` poria um número mágico no lugar de uma pergunta legível.
    select
        '{{ var("ppm_herd_table_id") }}'                        as sidra_tabela,
        cast(ano as int64)                                      as reference_year,
        municipio_codigo                                        as city_code,
        regexp_replace(municipio, r'\s-\s[A-Z]{2}$', '')        as city_name,
        regexp_extract(municipio, r'\s-\s([A-Z]{2})$')          as state_acronym,
        tipo_de_rebanho_codigo                                  as product_code,
        trim(tipo_de_rebanho)                                   as product_description,
        variavel_codigo                                         as variable_code,
        variavel                                                as variable_name,
        unidade_de_medida                                       as unit_of_measure,
        {{ safe_numeric('valor', dash_is_zero=true) }}          as raw_numeric_value,
        ingestion_timestamp
    from herd_dedup

    union all

    -- Animal production (74): a FLOW (quantity + value); product dim = tipo_de_produto_de_origem_animal.
    select
        '{{ var("ppm_animal_table_id") }}'                      as sidra_tabela,
        cast(ano as int64)                                      as reference_year,
        municipio_codigo                                        as city_code,
        regexp_replace(municipio, r'\s-\s[A-Z]{2}$', '')        as city_name,
        regexp_extract(municipio, r'\s-\s([A-Z]{2})$')          as state_acronym,
        tipo_de_produto_de_origem_animal_codigo                 as product_code,
        trim(tipo_de_produto_de_origem_animal)                  as product_description,
        variavel_codigo                                         as variable_code,
        variavel                                                as variable_name,
        unidade_de_medida                                       as unit_of_measure,
        {{ safe_numeric('valor', dash_is_zero=true) }}          as raw_numeric_value,
        ingestion_timestamp
    from animal_dedup

)

select
    p.sidra_tabela,
    -- DERIVADA da tabela, não guardada em paralelo: um fato só. 'stock' = efetivo do
    -- rebanho (contagem, sem preço) · 'flow' = produção animal (quantidade + valor).
    -- Continua existindo porque responde "esta linha tem preço?", que é a pergunta que
    -- cinco telas fazem — o id da tabela responde "de onde veio", que é outra coisa.
    case when p.sidra_tabela = '{{ var("ppm_herd_table_id") }}' then 'stock' else 'flow' end
        as measure_kind,
    p.reference_year,
    p.city_code,
    p.city_name,
    p.state_acronym,
    p.product_code,
    p.product_description,
    p.variable_code,
    p.variable_name,
    p.unit_of_measure,

    -- Monetary value (var 215, animal only): date-aware reform-correct factor (same as
    -- silver_ibge_pevs/pam). Every other variable passes through unscaled.
    case
        when p.variable_code = '{{ var_value }}'
            -- ×1000 reform-boundary SOURCE correction (ibge_1985_cruzado_correction): IBGE's 1985
            -- "Mil Cruzeiros" value is magnitude-Cruzados; realigns it with 1984/1986. No-op else.
            then p.raw_numeric_value * fx.brl_factor
                 * {{ ibge_1985_cruzado_correction('p.reference_year', 'p.unit_of_measure') }}
        else p.raw_numeric_value
    end as numeric_value,

    case when p.variable_code = '{{ var_value }}' then true else false end as is_monetary_value,

    -- ── Physical-unit family (quantity rows: herd 105 OR animal 106) ─────────────
    -- Multiple families coexist (contagem/volume/massa); the seed's 'mil litros' /
    -- 'mil dúzias' rows fold the SIDRA ×1000 "Mil" scale into to_base.
    case when p.variable_code in ('{{ var_herd }}', '{{ var_animal_qty }}')
        then p.unit_of_measure end                          as unit_native,
    case when p.variable_code in ('{{ var_herd }}', '{{ var_animal_qty }}')
        then coalesce(ufp.family, ufc.family, 'desconhecida') end as family,
    case when p.variable_code in ('{{ var_herd }}', '{{ var_animal_qty }}')
        then coalesce(ufp.base_unit, ufc.base_unit) end     as base_unit,
    case when p.variable_code in ('{{ var_herd }}', '{{ var_animal_qty }}')
        then p.raw_numeric_value end                        as qty_native,
    case when p.variable_code in ('{{ var_herd }}', '{{ var_animal_qty }}')
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
-- source='_reference' sentinel rows, so no 'ppm' unit is overridden yet — but a future
-- per-product PPM factor now takes effect (matching PEVS) instead of silently no-op-ing.
left join {{ ref('product_unit_factors') }} ufp
    on ufp.source = 'ppm'
    and ufp.product_code = p.product_code
    and lower(trim(p.unit_of_measure)) = ufp.unit_raw
