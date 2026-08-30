{{
    config(
        materialized='table',
        partition_by={
            'field': 'reference_year',
            'data_type': 'int64',
            'range': {'start': 1970, 'end': 2050, 'interval': 1}
        },
        cluster_by=['flow', 'customs_code', 'cmd_code', 'reporter_code']
    )
}}

-- ────────────────────────────────────────────────────────────────────────────
-- serving_comtrade_annual — pre-aggregated COMTRADE mart (global bilateral).
--
-- gold_comtrade_flows is already at (year × flow × reporter × partner × cmd), so
-- here the win is COLUMN pruning + clustering + crosswalk conformance rather than
-- row reduction: the dashboard reads a narrow, clustered table (the handful of
-- columns the partner/flow/market-share views use) instead of the wide Gold fact.
-- The `world_exp` denominator (brief §5) is derived by summing over reporters at
-- query time — the World partner is already dropped in Silver, so SUM is clean.
--
-- Carries the same family/unit/qty AND currency set as serving_pevs_annual so the
-- BFF reads products/productTS uniformly across sources. The monetary measures span
-- {nominal, real IPCA/IGP-M/IGP-DI} × {BRL, USD, EUR} — the REAL year-FX / deflated
-- values Gold computes (triangulated through BRL, NULL pre-1994) — so a BRL/EUR
-- display serves the real column instead of cross-converting USD client-side.
--
-- Grain: one row per
-- (reference_year, flow, cmd_code, reporter_code, partner_code, family).
-- ────────────────────────────────────────────────────────────────────────────

with comtrade as (

    select
        reference_year,
        flow,
        -- Customs procedure (regime aduaneiro), carried as a server-side filter axis like
        -- `flow`. C00 = todos os regimes / total (the only value for ~86% of trade). A
        -- reader that does NOT filter or group by customs_code sums over it → the bilateral
        -- total (no double-count: C00 and breakdowns are mutually exclusive per key,
        -- guaranteed in silver_comtrade_flows). The regime filter narrows on it.
        customs_code,
        cmd_code,
        -- A TABELA no grão, como em todos os bancos. Constante aqui (banco de UMA tabela
        -- só), e é justamente por isso que precisa estar: com o trio valendo nos cinco, a
        -- mart tem a MESMA forma em todos e o consumidor não ramifica por banco.
        tabela,
        reporter_code,
        partner_code,
        -- family in the grain only mirrors the other marts' shape (uniform BFF
        -- reads); unlike COMEX, a mixed-unit HS6 split CANNOT occur here. Silver
        -- dedups to ONE row per (year, reporter, partner, cmd, flow) — the unit
        -- code is deliberately NOT in the dedup key, so the non-dominant unit
        -- variant is discarded upstream — and Gold is tested unique on that same
        -- key. Every Gold row thus carries a single family and this GROUP BY adds
        -- no rows (which is why the YAML uniqueness test omits family).
        family,
        any_value(hs_chapter)       as hs_chapter,
        any_value(cmd_description)  as cmd_description,
        any_value(reporter_name)    as reporter_name,
        any_value(reporter_iso_a3)  as reporter_iso_a3,
        any_value(partner_name)     as partner_name,
        any_value(partner_iso_a3)   as partner_iso_a3,
        any_value(unit_native)      as unit_native,
        any_value(base_unit)        as base_unit,
        sum(qty_native)             as qty_native,
        sum(qty_base)               as qty_base,
        -- Full currency matrix carried forward from Gold (same column set as
        -- serving_pevs_annual) so the dashboard can serve BRL/EUR — at the REAL
        -- year-FX / deflated values Gold already computes — instead of the
        -- frontend cross-converting USD via a frozen mock rate. The BRL/EUR (and
        -- all val_real_*) columns are NULL pre-1994 by the Gold guard; that
        -- NULL-pre-1994 semantics carries through this SUM automatically.
        sum(val_yearfx_brl)         as val_yearfx_brl,
        sum(val_yearfx_usd)         as val_yearfx_usd,
        sum(val_yearfx_eur)         as val_yearfx_eur,
        sum(val_real_ipca_brl)      as val_real_ipca_brl,
        sum(val_real_ipca_usd)      as val_real_ipca_usd,
        sum(val_real_ipca_eur)      as val_real_ipca_eur,
        -- IGP-M / IGP-DI deflation is carried in BRL and EUR only. The USD-deflated
        -- combos (val_real_{igpm,igpdi}_usd) are intentionally NOT served: the BFF
        -- allowlist (serving/sql.ALLOWED_VALUE_COLUMNS) omits them, so the serving
        -- layer can never SELECT them — materializing them here would be dead bytes.
        sum(val_real_igpm_brl)      as val_real_igpm_brl,
        sum(val_real_igpm_eur)      as val_real_igpm_eur,
        sum(val_real_igpdi_brl)     as val_real_igpdi_brl,
        sum(val_real_igpdi_eur)     as val_real_igpdi_eur,
        sum(net_weight_kg)          as net_weight_kg,
        count(*)                    as source_rows,
        max(last_refresh)           as last_refresh
    from {{ ref('gold_comtrade_flows') }}
    where {{ hidden_code_predicate('comtrade', 'cmd_code') }}
    group by reference_year, flow, customs_code, cmd_code, tabela, reporter_code, partner_code, family

)

select
    ct.reference_year,
    date(ct.reference_year, 12, 31) as reference_date,
    ct.flow,
    ct.customs_code,
    -- Tipo de mercado (consumo/processamento) — a function of (customs_code, flow) from the
    -- researcher-editable dim_flow_market_scd2. FROZEN (2026-07, totals-only): the feature is
    -- UI-hidden and, with customs_code now a constant C00, the classification is inert. The
    -- column is KEPT (dormant scaffold) but its source join is guarded behind enable_curation
    -- so this LIVE mart never hard-depends on the gated SCD2 (a false flag would otherwise make
    -- ref() a parse-time error that breaks the WHOLE prod build). NULL when curation is off.
    {% if var('enable_curation', false) -%}
    fm.market                       as market_nature,
    {%- else -%}
    cast(null as string)            as market_nature,
    {%- endif %}
    ct.cmd_code,
    ct.tabela,
    ct.hs_chapter,
    ct.cmd_description,
    ct.reporter_code,
    ct.reporter_name,
    ct.reporter_iso_a3,
    ct.partner_code,
    ct.partner_name,
    ct.partner_iso_a3,
    x.agrupamento_id,
    x.agrupamento_nome,
    ct.family,
    ct.unit_native,
    ct.base_unit,
    ct.qty_native,
    ct.qty_base,
    ct.val_yearfx_brl,
    ct.val_yearfx_usd,
    ct.val_yearfx_eur,
    ct.val_real_ipca_brl,
    ct.val_real_ipca_usd,
    ct.val_real_ipca_eur,
    ct.val_real_igpm_brl,
    ct.val_real_igpm_eur,
    ct.val_real_igpdi_brl,
    ct.val_real_igpdi_eur,
    ct.net_weight_kg,
    ct.source_rows,
    ct.last_refresh
from comtrade ct
left join {{ ref('gold_produto_agrupamento') }} x
    on x.source = 'comtrade' and x.code = ct.cmd_code
    -- O TRIO no join: sem a tabela, um código presente nas duas tabelas de um banco
    -- casaria DUAS linhas do agrupamento e o LEFT JOIN dobraria as somas.
    and x.tabela = ct.tabela
-- Edit-driven market-nature (current classification per customs procedure × flow). GUARDED
-- behind enable_curation: only ref() the gated dim_flow_market_scd2 when curation is on, so a
-- future build with the flag off degrades market_nature to NULL rather than failing to compile
-- (the model is a view disabled by the flag; a hard ref() to a disabled model is a parse error
-- that breaks the whole prod build). ct is grouped by (customs_code, flow), so the join stays
-- at grain (one fm row per pair via is_current).
{% if var('enable_curation', false) -%}
left join {{ ref('dim_flow_market_scd2') }} fm
    on fm.customs_code = ct.customs_code and fm.flow_code = ct.flow and fm.is_current
{%- endif %}
