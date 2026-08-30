{{
    config(
        materialized='table',
        partition_by={
            'field': 'reference_year',
            'data_type': 'int64',
            'range': {'start': 1960, 'end': 2050, 'interval': 1}
        },
        cluster_by=['flow', 'customs_code', 'cmd_code', 'reporter_code']
    )
}}

-- ────────────────────────────────────────────────────────────────────────────
-- gold_comtrade_flows — the single comprehensive `flows` table for UN Comtrade
-- (naming: gold_<source>_<form>; `flows` = origin→destination trade). The global
-- complement to gold_comex_flows (Brazil-only).
--
-- Grain: one row per (flow, customs_code, reference_year, reporter_code,
-- partner_code, cmd_code) — customs_code (regime aduaneiro) IS part of the grain
-- (C00 and its per-regime breakdowns are mutually exclusive per key, so SUM over
-- customs_code stays a clean total). The Silver source grain (which also splits by
-- partner2 / mode-of-supply / mode-of-transport / qty-unit) is summed up to this grain.
-- Coarser cuts (by region, by chapter, reporter totals) are derived at query
-- time via GROUP BY — ONE comprehensive table per source. The World partner
-- (partner_code='0') is already dropped in Silver, so SUM over partner_code is
-- a true bilateral total with no double counting.
--
-- Geography is bilateral: for exports reporter=origin, partner=destination;
-- for imports reporter=destination, partner=origin. Both resolve to name + ISO3
-- via comtrade_country.
--
-- Monetary conventions (mirror gold_comex_flows — source value is nominal US$,
-- but annual, so FX is the year average and inflation the year-end index like
-- gold_pevs_production):
--   • val_yearfx_*   = primary_value_usd converted at THAT year's avg FX. usd is
--                      the source value; brl/eur triangulate through BRL.
--                      Nominal — no inflation correction.
--   • val_real_{ipca,igpm,igpdi}_* = USD → BRL at the year FX → projected to today
--                      via the BCB chain index → optionally reconverted to
--                      USD/EUR at TODAY's FX. Use these for cross-year comparison.
--
-- NULL semantics: missing year FX (EUR pre-1999) → NULL that
-- currency's columns; missing year inflation index → NULL the real_* columns;
-- reference_year < 1994 → NULL val_yearfx_{brl,eur} and all val_real_* (the
-- PTAX series of those years is in old currencies — same guard as the PEVS/PAM
-- golds; val_yearfx_usd, the source value, is always kept);
-- chapter-44 rows with no reported quantity → NULL qty_native/qty_base/weight.
-- ────────────────────────────────────────────────────────────────────────────

with with_dominant as (

    -- Pick each group's DOMINANT quantity unit (the unit of the largest-quantity
    -- row) so the qty sums below stay UNIT-SAFE. A (reporter, partner, cmd) whose
    -- reported HS codes were succession-merged into one cmd_code can span >1
    -- statistical unit, and summing qty_native/qty_base across units would add
    -- incompatible quantities under a single label. Mirrors gold_comex_flows'
    -- dominant_stat_unit_code guard. Today every merged code shares one unit
    -- ('massa'), so this changes NO numbers — it just makes the latent mixed-unit
    -- case fail safe (non-dominant-unit qty excluded, not mis-summed). The ORDER BY
    -- matches the array_agg label picks below, so the summed unit == the labelled unit.
    select
        *,
        first_value(qty_unit_code) over (
            partition by flow, customs_code, reference_year, reporter_code, partner_code, cmd_code
            order by qty_native desc nulls last, qty_unit_code
        ) as dominant_qty_unit_code
    from {{ ref('silver_comtrade_flows') }}

),

base_flows as (

    select
        flow,
        customs_code,
        reference_year,
        reporter_code,
        partner_code,
        cmd_code,
        -- A TABELA no grão da CTE base, vinda do Silver — o trio atravessa o Gold
        -- inteiro em vez de ser reconstituído no select final.
        tabela,
        any_value(hs_chapter)                     as hs_chapter,
        -- The unit fields are picked together from the group's dominant-quantity
        -- row (same ORDER BY for all five) so family/base_unit/unit stay COHERENT
        -- even when a (reporter, partner, cmd) reported under mixed qty units; a
        -- group with no quantity falls to the '-1' row → desconhecida / NULL base.
        array_agg(qty_unit_code order by qty_native desc nulls last, qty_unit_code limit 1)[offset(0)]      as qty_unit_code,
        array_agg(unit_native order by qty_native desc nulls last, qty_unit_code limit 1)[offset(0)]        as unit_native,
        array_agg(unit_native_symbol order by qty_native desc nulls last, qty_unit_code limit 1)[offset(0)] as unit_native_symbol,
        array_agg(family order by qty_native desc nulls last, qty_unit_code limit 1)[offset(0)]             as family,
        array_agg(base_unit order by qty_native desc nulls last, qty_unit_code limit 1)[offset(0)]          as base_unit,
        -- UNIT-SAFE: sum quantity ONLY for rows in the dominant statistical unit
        -- (see with_dominant). Weights/values are unit-independent (kg / USD) → full sum.
        sum(case when qty_unit_code = dominant_qty_unit_code then qty_native end) as qty_native,
        sum(case when qty_unit_code = dominant_qty_unit_code then qty_base end)   as qty_base,
        sum(net_weight_kg)                        as net_weight_kg,
        sum(gross_weight_kg)                      as gross_weight_kg,
        sum(primary_value_usd)                    as primary_value_usd,
        sum(cif_value_usd)                        as cif_value_usd,
        sum(fob_value_usd)                        as fob_value_usd,
        count(*)                                  as source_rows,
        max(ingestion_timestamp)                  as last_refresh
    from with_dominant
    group by flow, customs_code, reference_year, reporter_code, partner_code, cmd_code, tabela

),

{{ annual_deflation_ctes() }},

enriched as (

    select
        b.*,
        fy.brl_per_usd_avg,
        fy.brl_per_eur_avg,
        fxl.brl_per_usd_current,
        fxl.brl_per_eur_current,

        -- Nominal BRL at the year-average FX (US$ → R$ of that year). Pre-1994
        -- the PTAX series is denominated in the old currencies (Cz$/NCz$/Cr$/CR$),
        -- so a "BRL" product would be off by 10^3-10^9 — NULL it (and the real_*
        -- columns built on it), mirroring gold_pevs_production's year-FX guard.
        case when b.reference_year >= 1994
            then b.primary_value_usd * fy.brl_per_usd_avg end                                 as val_nominal_brl,
        -- Real BRL today: nominal BRL projected forward via each inflation chain.
        case when b.reference_year >= 1994
            then (b.primary_value_usd * fy.brl_per_usd_avg)
                * safe_divide(il.ipca_current, iy.ipca_year_end) end                          as val_real_ipca_brl,
        case when b.reference_year >= 1994
            then (b.primary_value_usd * fy.brl_per_usd_avg)
                * safe_divide(il.igpm_current, iy.igpm_year_end) end                          as val_real_igpm_brl,
        case when b.reference_year >= 1994
            then (b.primary_value_usd * fy.brl_per_usd_avg)
                * safe_divide(il.igpdi_current, iy.igpdi_year_end) end                        as val_real_igpdi_brl

    from base_flows b
    left join fx_year            fy  on b.reference_year = fy.reference_year
    left join inflation_year_end iy  on b.reference_year = iy.reference_year
    cross join inflation_latest  il
    cross join fx_latest         fxl

)

select
    -- A TABELA da fonte, carregada do Silver (que a carimba). Fecha o trio
    -- `(banco, tabela, código)` neste banco de uma tabela só — a simetria é o ponto:
    -- com o trio valendo nos cinco, nenhum consumidor ramifica por banco.
    tabela,
    -- ── Time ─────────────────────────────────────────────────────────────────
    reference_year,
    date(reference_year, 12, 31)                            as reference_date,

    -- ── Flow direction + customs regime (regime aduaneiro) ───────────────────
    flow,
    -- The UN customs procedure. 'C00' = todos os regimes / total (the only value for
    -- ~86% of trade, which reports no per-regime split); specific procedures otherwise.
    -- Preserved without double-count (see silver_comtrade_flows): SUM over customs_code
    -- equals the old C00-only total. A regime filter narrows on this; omitting it sums
    -- every regime back to the bilateral total.
    customs_code,
    -- NOTE: tipo de mercado (consumo/processamento) is NOT a Gold column. It reverted
    -- from the comtrade_market_nature seed (v1.9.0) to the researcher-editable append-log
    -- and is derived in the serving layer (serving_comtrade_annual LEFT JOINs
    -- dim_flow_market_scd2) — an editable classification is kept out of the medallion fact.

    -- ── Product (HS) ─────────────────────────────────────────────────────────
    enriched.cmd_code,
    hs_chapter,
    h.description                                           as cmd_description,

    -- ── Geography (bilateral; reporter→partner) ──────────────────────────────
    reporter_code,
    rc.country_name                                         as reporter_name,
    rc.iso_a3                                               as reporter_iso_a3,
    partner_code,
    pc.country_name                                         as partner_name,
    pc.iso_a3                                               as partner_iso_a3,
    pc.is_group                                             as partner_is_group,

    -- ── Quantities (physical-unit family) ───────────────────────────────────
    -- The reported quantity unit varies by HS code (kg, m³, items, …) and is
    -- normalised to a per-family base unit. NEVER sum qty_base across families:
    -- any SUM(qty_base) must GROUP BY family. net_weight_kg is always kilograms
    -- (massa) — a parallel, always-comparable weight. Chapter-44 rows usually
    -- report neither (→ all NULL): see data_quality_flag.
    family,
    qty_unit_code,
    unit_native,
    unit_native_symbol,
    qty_native,
    qty_base,
    base_unit,
    net_weight_kg,
    gross_weight_kg,

    -- ── Year-FX (nominal, at the year-average FX) ────────────────────────────
    primary_value_usd                                      as val_yearfx_usd,
    val_nominal_brl                                        as val_yearfx_brl,
    safe_divide(val_nominal_brl, brl_per_eur_avg)          as val_yearfx_eur,

    -- ── Real via IPCA (comparable across years, in today's units) ────────────
    val_real_ipca_brl                                      as val_real_ipca_brl,
    safe_divide(val_real_ipca_brl, brl_per_usd_current)    as val_real_ipca_usd,
    safe_divide(val_real_ipca_brl, brl_per_eur_current)    as val_real_ipca_eur,

    -- ── Real via IGP-M ───────────────────────────────────────────────────────
    val_real_igpm_brl                                      as val_real_igpm_brl,
    safe_divide(val_real_igpm_brl, brl_per_usd_current)    as val_real_igpm_usd,
    safe_divide(val_real_igpm_brl, brl_per_eur_current)    as val_real_igpm_eur,

    -- ── Real via IGP-DI ──────────────────────────────────────────────────────
    val_real_igpdi_brl                                     as val_real_igpdi_brl,
    safe_divide(val_real_igpdi_brl, brl_per_usd_current)   as val_real_igpdi_usd,
    safe_divide(val_real_igpdi_brl, brl_per_eur_current)   as val_real_igpdi_eur,

    -- ── CIF / FOB split (nominal US$, where the reporter provides it) ────────
    cif_value_usd                                          as val_cif_usd,
    fob_value_usd                                          as val_fob_usd,

    -- ── Quality + provenance ─────────────────────────────────────────────────
    -- "Has a quantity" = any of native qty / net weight present (chapter 44
    -- frequently reports neither → MISSING_QUANTITY, which is expected).
    -- Value presence is tested on primary_value_usd — the PRE-FX source value —
    -- not val_nominal_brl (post-FX). A year with no PTAX rate yields NULL
    -- val_nominal_brl while the source value is fully present; flagging that as
    -- MISSING_VALUE would be misleading. This mirrors gold_comex_flows (which
    -- tests val_fob_usd) and gold_pevs_production (val_raw, already BRL).
    -- NOTE: completeness coalesces qty_native+net_weight_kg ("has a quantity"), but Q1 SCORING
    -- uses net_weight_kg ONLY. qty_native mixes units across an HS code (kg / litres / items), so
    -- value/qty_native is not a comparable implied price, while value/net_weight_kg (USD/kg) is. A
    -- weight-null but qty-present row is therefore "complete" yet unscored (falls to OK) rather
    -- than risk a mixed-unit false PROBLEMATIC — a deliberate conservative gap (~56.5k weight-null
    -- rows stay OK, mostly chapter-44 wood in non-mass units; revisit only with a
    -- per-unit-normalised quantity).
    {{ data_quality_flag('coalesce(qty_native, net_weight_kg)', 'primary_value_usd',
         quality_qty_level('primary_value_usd', 'net_weight_kg'),
         quality_val_level('primary_value_usd', 'net_weight_kg')) }} as data_quality_flag,
    source_rows,
    last_refresh

from {% if var('enable_quality_outliers', false) -%}
(
    select e.*,
{{ quality_scored_bounds('primary_value_usd', 'net_weight_kg') }}
    from enriched e
    window _qw as (partition by flow, cmd_code)
) enriched
{%- else -%}
enriched
{%- endif %}
-- Reference dimensions → human-readable labels for Looker.
left join {{ ref('comtrade_hs') }}      h  on enriched.cmd_code      = h.cmd_code
left join {{ ref('comtrade_country') }} rc on enriched.reporter_code = rc.m49_code
left join {{ ref('comtrade_country') }} pc on enriched.partner_code  = pc.m49_code
