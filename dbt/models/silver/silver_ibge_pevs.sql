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
    Incremental strategy:
      1. Find which years got new Bronze rows since the last Silver build.
      2. Pull every Bronze row for those years (not just the new ones — the
         dedupe `qualify` needs the full natural-key partition to pick the
         latest ingestion_timestamp).
      3. insert_overwrite replaces only the affected reference_year partitions.

    MEASURED SCOPE (2026-08-28) — this does NOT behave incrementally today, and the
    `>=` note below explains why. `affected_years` currently returns ALL 39 years
    (1986-2024) on every build, so step 2 re-reads the whole of Bronze and step 3
    overwrites every partition. Billed bytes for this model are flat at 3.22 GB/build
    (3.88 GB after 2026-08-19), identical every day — the signature of a full rebuild,
    not an incremental one.

    Why: the boundary is `ingestion_timestamp >= max(Silver)`, and the batch sitting AT
    that boundary keeps qualifying until a NEWER Bronze ingestion arrives. Two things make
    that batch huge and long-lived here: the monthly `reconcile` re-ingests the entire
    history by design, and PEVS itself only writes to Bronze ~2 days a month. So a
    full-history batch stays on the boundary for weeks, and every build in between redoes
    it.

    NOT fixed, deliberately. The `>=` is what stops a same-second append from being
    skipped forever (see the note in the CTE), so tightening it needs a different
    correctness argument, not just a different operator — a per-year comparison of Bronze
    vs Silver (max ingestion_timestamp AND row count, so the same-second case is still
    caught) would do it. It is not worth the risk today: the whole project sits at ~15% of
    BigQuery's free 1 TiB/month, so this costs nothing. Revisit if that changes — these
    two models are ~36% of the build's bytes and would drop to near zero.

    AND THE BRONZE THEY SCAN IS MOSTLY DEAD WEIGHT. Measured 2026-08-28 with each model's
    own natural key: **82.8%** of bronze_ibge.sidra_t289_raw is superseded (21.1M rows vs
    4.4M live) and **69.9%** of bronze_pam.sidra_t5457_raw (39.1M vs 16.9M). Bronze is
    append-only by design and the monthly `reconcile` re-ingests the whole history, so
    copies accumulate; Silver's dedupe `qualify` then discards ~5 of every 6 rows it read.
    Pruning superseded rows would cut this model's scan ~5× WITHOUT touching the `>=`
    contract above — a bigger and safer lever than tightening the boundary. It is a
    human-gated, backup-first operation (Bronze is the queryable landing; the GCS raw zone
    keeps the provenance copy), and it buys ~US$0.16/month today, which is why it has not
    been done.
    On `--full-refresh` (or first build), the {% if is_incremental() %} block
    is skipped and we scan all of Bronze.

    SEED CHANGES DON'T PROPAGATE INCREMENTALLY: this model ref()s the
    historical_currency_factors, unit_family_conversions and product_unit_factors
    seeds, but the incremental gate keys off NEW Bronze ingestion_timestamps — a
    seed edit bumps none, so it never reaches already-built reference_year
    partitions. After editing any of those seeds, rebuild with
    `dbt build --select silver_ibge_pevs+ --full-refresh`.
-#}

{% if is_incremental() %}
with affected_years as (

    -- `>=` (not `>`) on purpose: a Bronze row appended with an
    -- ingestion_timestamp EQUAL to the current Silver max (a same-second /
    -- clock-identical double load) is `> max` = false and would be skipped
    -- forever. Re-scanning the boundary year is safe — insert_overwrite is
    -- idempotent, so reprocessing a year replaces its whole partition (no
    -- double-counting) — and bounded: only the year(s) tied at the max
    -- timestamp re-run, not the full history.
    select distinct ano
    from {{ source('bronze_ibge', 'sidra_raw') }}
    where ingestion_timestamp >= (select coalesce(max(ingestion_timestamp), timestamp '1970-01-01') from {{ this }})

),

deduplicated as (

    select b.*
    from {{ source('bronze_ibge', 'sidra_raw') }} b
    inner join affected_years ay on b.ano = ay.ano
    where b.variavel_codigo in (
              '{{ var("ibge_variable_quantity") }}',
              '{{ var("ibge_variable_value") }}'
          )
      and b.nivel_territorial = 'Município'
    -- NORMALIZE the unit in the dedup key with lower(trim(...)) — the SAME normalization the
    -- unit_family_conversions / historical_currency_factors joins already apply. Without it, a
    -- cosmetic source RE-LABEL (case/whitespace) of an already-ingested cell would land the
    -- revised row in a DIFFERENT partition from the stale one, so BOTH survive latest-wins and
    -- Gold's max() pivot collapses them by magnitude, not recency. Never observed in the ingested
    -- history and guarded downstream by assert_pevs_conserved_silver_to_gold, so this is defensive.
    qualify row_number() over (
        partition by b.ano, b.municipio_codigo, b.tipo_de_produto_extrativo_codigo, b.variavel_codigo, lower(trim(b.unidade_de_medida))
        order by b.ingestion_timestamp desc
    ) = 1

),
{% else %}
with deduplicated as (

    -- Bronze is append-only; keep only the latest ingestion per natural key.
    select *
    from {{ source('bronze_ibge', 'sidra_raw') }}
    where variavel_codigo in (
              '{{ var("ibge_variable_quantity") }}',
              '{{ var("ibge_variable_value") }}'
          )
      and nivel_territorial = 'Município'
    qualify row_number() over (
        partition by ano, municipio_codigo, tipo_de_produto_extrativo_codigo, variavel_codigo, lower(trim(unidade_de_medida))
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
        -- Product code comes directly from SIDRA (the classification-193
        -- category id, e.g. "3405"). The product_description is also taken
        -- from SIDRA — the leading display ordinal (e.g. "1.3 - ") is stripped.
        --
        -- The ordinal is anchored to DIGITS AND DOTS ONLY. The earlier pattern was
        -- `^([^-]+)\s-\s`, which strips ANY prefix without a hyphen: a produto named
        -- "Açaí - fruto" would have lost "Açaí" and displayed as "fruto". No SIDRA value
        -- has ever tripped it (10 distinct, all numeric ordinals), but "it has not
        -- happened yet" is not a guarantee — and this one IS guaranteeable, because
        -- informative text can never match [0-9.]+.
        --
        -- Why strip at all: the ordinal is a POSITION IN SIDRA'S MENU, not an attribute of
        -- the produto — carvão vegetal is "7.1" in t289 and "1.1" in t291, so keeping it
        -- would show the same produto under two different numbers depending on the half.
        tipo_de_produto_extrativo_codigo                                            as product_code,
        trim(regexp_replace(tipo_de_produto_extrativo, r'^[0-9]+(?:\.[0-9]+)*\s-\s', ''))       as product_description,
        variavel_codigo                                                             as variable_code,
        variavel                                                                    as variable_name,
        unidade_de_medida                                                           as unit_of_measure,
        {{ safe_numeric('valor', dash_is_zero=true) }}                              as raw_numeric_value,
        ingestion_timestamp
    from deduplicated

)

select
    -- A TABELA da fonte, carimbada AQUI, na primeira camada tipada — cada modelo Silver
    -- sabe de qual tabela ele lê, então a informação nasce onde é conhecida em vez de ser
    -- reconstituída depois. Fecha o trio `(banco, tabela, código)` em TODOS os bancos:
    -- 289, a metade de extração vegetal do PEVS.
    -- Com isso as uniões do Gold são `select *` puro e nenhum consumidor ramifica por
    -- banco para saber se há tabela. Ver docs/audits/chave_produto_audit_2026-08-30.md.
    '{{ var("ibge_table_id") }}' as tabela,
    p.reference_year,
    p.city_code,
    p.city_name,
    p.state_acronym,
    p.product_code,
    p.product_description,
    p.variable_code,
    p.variable_name,
    p.unit_of_measure,

    -- Monetary values: apply the currency seed factor (which embeds both the
    -- "Mil" multiplier AND the cumulative reform divisions Cz$→...→R$). The
    -- seed join is date-aware because the name "Mil Cruzeiros" was used for
    -- three distinct currencies (1942 Cr$, 1970 Cr$, 1990 Cr$) with different
    -- factors; the year range disambiguates. The IPCA chain index only
    -- captures inflation, NOT currency reforms — without this factor,
    -- pre-1994 values come out 10^6 to 10^9 times too large.
    -- Quantity values are NOT scaled here: physical-unit conversion is owned by
    -- the unit-family seeds below (qty_base). The old "x1000 if mil" branch was
    -- removed — it never fired for the current units and would wrongly inflate
    -- 'milheiro' (which now converts via to_base=1000).
    case
        when p.variable_code = '{{ var("ibge_variable_value") }}' then
            p.raw_numeric_value * fx.brl_factor
        else
            p.raw_numeric_value
    end as numeric_value,

    case when p.variable_code = '{{ var("ibge_variable_value") }}' then true else false end as is_monetary_value,

    -- ── Physical-unit family (quantity rows only) ────────────────────────────
    -- unit_native is the source label, kept verbatim for display/audit.
    -- family / base_unit / to_base come from the unit-family seeds: the
    -- per-product crosswalk (ufp) overrides the generic table (ufc); an unknown
    -- unit falls to 'desconhecida' with a NULL qty_base (never an invented
    -- conversion — surfaced for curation by a dedicated test). Commodity units
    -- (saca/@/bushel/barril) carry a family but a NULL generic factor, so
    -- qty_base stays NULL until the product crosswalk supplies to_base.
    case when p.variable_code = '{{ var("ibge_variable_quantity") }}'
        then p.unit_of_measure end                          as unit_native,
    case when p.variable_code = '{{ var("ibge_variable_quantity") }}'
        then coalesce(ufp.family, ufc.family, 'desconhecida') end as family,
    case when p.variable_code = '{{ var("ibge_variable_quantity") }}'
        then coalesce(ufp.base_unit, ufc.base_unit) end     as base_unit,
    case when p.variable_code = '{{ var("ibge_variable_quantity") }}'
        then p.raw_numeric_value end                        as qty_native,
    case when p.variable_code = '{{ var("ibge_variable_quantity") }}'
        then p.raw_numeric_value * coalesce(ufp.to_base, ufc.to_base) end as qty_base,

    p.ingestion_timestamp
from parsed p
left join {{ ref('historical_currency_factors') }} fx
    on lower(trim(p.unit_of_measure)) = lower(trim(fx.unit_of_measure))
    and p.reference_year between fx.year_from and fx.year_to
left join {{ ref('unit_family_conversions') }} ufc
    on lower(trim(p.unit_of_measure)) = ufc.unit_raw
-- Per-product unit override. Staged/inert today: the seed ships only
-- source='_reference' sentinel rows (which this 'pevs' filter excludes by
-- design), so no PEVS unit is overridden yet — see seeds/_seeds.yml. The join
-- is wired and correct; it activates the moment a real 'pevs' row is added.
left join {{ ref('product_unit_factors') }} ufp
    on ufp.source = 'pevs'
    and ufp.product_code = p.product_code
    and lower(trim(p.unit_of_measure)) = ufp.unit_raw
