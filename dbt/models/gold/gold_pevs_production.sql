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
-- Conventions
--
--  Silver already converts every historical-currency value to present BRL via
--  the `historical_currency_factors` seed (so val_raw is in R$ regardless of
--  the year). Gold only applies FX and inflation deflation on top.
--
--  • val_yearfx_*  = val_raw (BRL) converted to USD/EUR at the FX rate
--                     of THAT year. Use this for historical auditing — note
--                     pre-1994 BRL is purchasing-power-equivalent today, but
--                     the FX rate of the year is in the currency of the year
--                     (Cz$/USD, Cr$/USD, etc.), giving a USD value at the
--                     time the transaction happened.
--
--  • val_real_ipca_* = val_raw projected to today via the IPCA chain (real
--                     inflation only — currency reforms already absorbed in
--                     Silver), then optionally converted to foreign currency
--                     at TODAY's FX rates. This is the column for cross-year
--                     economic comparison.
--
--  • val_real_igpm_* = identical logic to IPCA, using IGP-M.
--
--  • val_real_igpdi_* = identical logic to IPCA, using IGP-DI (BCB SGS 190 —
--                     general price index, broader basket than IGP-M, includes
--                     wholesale + consumer + construction).
--
--  NULL semantics:
--    - "no data" sentinels (..., .., *, X) in the source → NULL in the Silver layer;
--      SIDRA '-' is NOT one of them — it is an EXACT MEASURED ZERO (0.0), kept distinct
--      from "não disponível" so a municipality-year-product that went to (or stayed at)
--      zero production is retained here as 0, not dropped/hidden as missing;
--    - missing currency factor for unit_of_measure → NULL val_raw → NULL all monetary;
--    - missing IPCA / IGP-M / IGP-DI index for that year → NULL real_* columns;
--    - missing FX rate for that year (e.g. EUR pre-1999) → NULL val_yearfx_FX.
-- ────────────────────────────────────────────────────────────────────────────

-- ── The two halves of PEVS ──────────────────────────────────────────────────
--
--  The survey is "Produção da Extração Vegetal E DA Silvicultura" and this table
--  carries both, told apart by `sidra_tabela` — the SIDRA table each row came from:
--    t289 — NATIVE forest, extração vegetal (the original contents of this table)
--    t291 — PLANTED forest, silvicultura
--
--  The table id, not a word derived from it. A produto's identity is
--  (banco, tabela, código) — the same key the curation catalog has used since v1.39.0
--  — so the table has to BE a column. Until v1.46.0 Gold stamped prose instead
--  (`origem` = 'extrativa' | 'silvicultura'), which left the identity component
--  reachable only as a Bronze table NAME (`sidra_t289_raw`) and as a label: a chart
--  that had to tell two halves apart could not reach it, and merged two legitimate
--  produtos (same name, different tables) into one bar with both labels on top of
--  each other. The human name of each half is now DERIVED from the id wherever it is
--  displayed, so there is one stored fact instead of two that can disagree.
--
--  They are one banco on purpose. The codes never collide (3433-3435 vs 3455-3457),
--  the units match, and the sum is a real quantity IBGE itself publishes as one
--  survey. What must never happen is a total that mixes them WITHOUT saying so, which
--  is why the table is a first-class filter axis all the way to the chip, the ABNT
--  citation and the CSV — see PLANS/silvicultura_source.md.
--
--  `union all` by position: both Silvers are column-identical by construction (one is
--  a mirror of the other) and a dbt test asserts it, because a silent column drift
--  here would shuffle values between fields rather than fail.
with silver_union as (

    select '{{ var("ibge_table_id") }}'         as sidra_tabela, * from {{ ref('silver_ibge_pevs') }}
    union all
    select '{{ var("silvicultura_table_id") }}' as sidra_tabela, * from {{ ref('silver_ibge_silvicultura') }}

),

base_pevs as (

    select
        sidra_tabela,
        reference_year,
        state_acronym,
        -- Group by city_code (the natural geographic key from Silver), NOT
        -- city_name (a display label): two municipalities can share a name, so
        -- grouping on the name would silently fan-in their rows. city_name is
        -- lifted via any_value() — it is functionally dependent on city_code.
        city_code,
        any_value(city_name)            as city_name,
        product_code,
        any_value(product_description)  as product_description,
        -- One quantity row per (year, state, city, product) — PEVS reports a
        -- single physical unit per product — so max() simply lifts the
        -- quantity row's family/unit/qty (NULL on the monetary row).
        -- CAVEAT: max() (not sum()) assumes exactly ONE physical unit per
        -- product at this grain. If a product ever reported under TWO units in
        -- the same (year, state, city) — which PEVS does not today — max()
        -- would keep one row and DROP the other instead of summing. Were that
        -- to happen, add unit_native to the grain (group by) so each unit gets
        -- its own row, rather than switching to sum() across mixed units.
        max(family)                     as family,
        max(unit_native)                as unit_native,
        max(base_unit)                  as base_unit,
        max(qty_native)                 as qty_native,
        max(qty_base)                   as qty_base,
        max(case when is_monetary_value then numeric_value end) as val_raw,
        max(ingestion_timestamp)        as last_refresh
    from silver_union
    group by sidra_tabela, reference_year, state_acronym, city_code, product_code
    having qty_native is not null
        or val_raw    is not null

),

{{ annual_deflation_ctes() }},

enriched as (

    select
        b.*,
        fy.brl_per_usd_avg,
        fy.brl_per_eur_avg,
        iy.ipca_year_end,
        iy.igpm_year_end,
        iy.igpdi_year_end,
        il.ipca_current,
        il.igpm_current,
        il.igpdi_current,
        fxl.brl_per_usd_current,
        fxl.brl_per_eur_current,

        -- Real-IPCA BRL: val_raw is already in present-day BRL (Silver applied
        -- the historical_currency_factors seed); we now apply the IPCA chain
        -- ratio to bring the year-of-record purchasing power up to today.
        b.val_raw * safe_divide(il.ipca_current,  iy.ipca_year_end)  as val_real_ipca_brl,
        -- Real-IGPM BRL: same logic with the alternative series.
        b.val_raw * safe_divide(il.igpm_current,  iy.igpm_year_end)  as val_real_igpm_brl,
        -- Real-IGPDI BRL: same logic, broader index (wholesale + consumer + construction).
        b.val_raw * safe_divide(il.igpdi_current, iy.igpdi_year_end) as val_real_igpdi_brl

    from base_pevs b
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

    -- ── Product ──────────────────────────────────────────────────────────────
    product_code,
    product_description,

    -- ── Which SIDRA table the row came from ─────────────────────────────────
    -- t289 (native forest, extração vegetal) | t291 (planted forest, silvicultura).
    -- Never null: every row comes from exactly one of the two Silvers. Part of the
    -- produto's identity (banco, tabela, código), not a label about it — the human
    -- name of each half is derived from this id wherever it is displayed.
    sidra_tabela,

    -- ── Quantities (physical-unit family) ───────────────────────────────────
    -- The reported quantity is normalised to a per-family base unit:
    --   family       — massa | volume | energia | contagem | area | desconhecida
    --   unit_native  — the source unit label (Toneladas, Metros cúbicos, …)
    --   qty_native   — the value in unit_native
    --   qty_base     — qty_native converted to base_unit (t / m³ / MWh / un / ha)
    --   base_unit    — the family's base unit
    -- NEVER sum qty_base across families: any SUM(qty_base) must GROUP BY family
    -- to build the q_by_family map at query time. Monetary values stay
    -- family-agnostic and freely summable.
    family,
    unit_native,
    qty_native,
    qty_base,
    base_unit,

    -- ── Year-FX: val_raw converted via FX of THAT year ──────────────────────
    -- val_raw is already in current BRL numerary (Silver applied the currency
    -- reform seed), but it carries NO inflation correction — so it equals
    -- "what the value was, restated in today's R$ symbols". Foreign-FX
    -- columns are NULL pre-1994: the FX rate of the year is in the currency-
    -- of-the-year (Cz$/USD etc.), which would mix scales and confuse readers.
    -- 1994 itself is valid: fx_year averages only the R$ half (>= 1994-07-01).
    -- Use val_real_* for cross-year comparisons.
    val_raw                                                  as val_yearfx_brl,
    case when reference_year >= 1994
        then safe_divide(val_raw, brl_per_usd_avg) end       as val_yearfx_usd,
    case when reference_year >= 1994
        then safe_divide(val_raw, brl_per_eur_avg) end       as val_yearfx_eur,

    -- ── Real via IPCA: comparable across years, expressed in current units ──
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
    -- Outlier/problemático detection (off by default) reads the DEFLATED value
    -- (val_real_ipca_brl) for a stable implied price; the missing-check keeps val_raw.
    {{ data_quality_flag('qty_native', 'val_raw',
         quality_qty_level('val_real_ipca_brl', 'qty_native'),
         quality_val_level('val_real_ipca_brl', 'qty_native')) }} as data_quality_flag,
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
