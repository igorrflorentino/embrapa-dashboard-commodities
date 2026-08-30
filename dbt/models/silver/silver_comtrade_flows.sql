{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partition_by={
            'field': 'reference_year',
            'data_type': 'int64',
            'range': {'start': 1960, 'end': 2050, 'interval': 1}
        },
        cluster_by=['flow', 'cmd_code', 'reporter_code', 'partner_code'],
        on_schema_change='append_new_columns'
    )
}}

{#-
    UN Comtrade annual reporter→partner flows, cleaned, typed, deduplicated to the
    canonical bilateral grain — one row per (flow, year, reporter, partner, cmd).

    TOTALS-ONLY (2026-07): the base keeps ONLY the fully-aggregated record on every
    dimension, for HOMOGENEITY (every country reports the totals, even those that
    never break them down) and to be structurally free of double-counts.

    Filters vs the verbatim Bronze:
      • partner_code = '0' (World) is DROPPED — it is the reporter's
        pre-aggregated total over all partners and would double-count any
        SUM over partners. The total is recoverable at query time as
        GROUP BY reporter (the medallion principle: no pre-aggregated rows).
      • flow: ONLY the two direction TOTALS are kept and normalised — X→export,
        M→import. The sub-flows (RX re-export, RM re-import, DX/FM/MIP/…) are
        SUBSETS of X/M — neither ingested (config.comtrade_flows='X,M') nor kept —
        so X+M never double-counts a re-export against its parent export.
      • only HS6 rows are kept (length(cmdCode)=6): the ingest requests the
        6-digit leaves of the scope chapters, so any legacy HS4 aggregate row
        (0801/44) is excluded — keeping both would double-count in Gold.
      • KEEP ONLY THE FULLY-AGGREGATED RECORD (motCode=0, customsCode=C00,
        partner2Code=0, mosCode=0). The keyed API returns, per
        (reporter,partner,cmd,flow), one aggregate row PLUS optional breakdown rows
        by transport mode / customs procedure / second partner; the aggregate value
        equals the sum of its breakdowns. Keeping ONLY C00 (the "todos os regimes /
        total") is LOSSLESS for the total and collapses the grain to one row per
        (reporter,partner,cmd,flow,year). The ingest also requests customsCode=C00
        so the breakdowns are not even downloaded; this filter is the belt-and-
        suspenders guarantee for any historical Bronze that still holds them. The
        customs-procedure detail this discards is exactly what the FROZEN "tipo de
        mercado" feature needed — see that feature's memo. If a future analysis
        wants the mode/customs breakdowns, read the verbatim rows from Bronze.
      • reference_year is floored at var('comtrade_min_year', 2000): the base is
        anchored at the year-2000 boundary (config.comtrade_start_year), so a stale
        pre-2000 Bronze row the ingest no longer refreshes never reaches Silver.

    Quantity sentinels: chapter-44 rows routinely report qty = netWgt = '0.0'
    (quantity not collected). 0 is mapped to NULL so it reads as "no reading"
    (→ qty_base NULL, data_quality_flag MISSING_QUANTITY) rather than a real zero.

    Dedup is TWO-staged, because re-downloads replace whole chunks: ingestion
    lands one (year × reporter-batch) chunk per Bronze load, every row sharing
    ONE ingestion_timestamp (comtrade/pipeline.bronze_one stamps the frame once).
      1. latest_batch — keep only the rows of the most recent ingestion batch
         per (refYear, reporterCode). A re-published reporter-year thus REPLACES
         the previous generation: records the source retracted disappear here
         (row-level latest-wins alone would keep them forever). reporterCode —
         not the batch id — is the scope: a reporter-year is always fully
         contained in ONE chunk even if the reporter batching changes between
         runs. Residual limitation: a reporter-year republished EMPTY lands no
         new Bronze rows, so the previous generation keeps serving.
      2. deduplicated — row-level dedup on the natural key inside the surviving
         batch (the duplicate-qtyUnitCode collapse below).
    NOTE: this batch-scoped dedup shipped 2026-06 (audit fix). The model is
    incremental (below), so after any change to the dedup logic run ONE
    `dbt build --select silver_comtrade_flows --full-refresh` to purge phantom
    rows — a plain incremental build only reprocesses years with new Bronze.

    Materialized=incremental (insert_overwrite by reference_year), mirroring
    silver_ibge_pevs. The all-reporters historical backfill (COMTRADE_REPORTERS=
    all) makes Bronze tens of GB, so a daily FULL rebuild would scan all of it
    every run. Instead the build re-scans only the reference_year partitions that
    received new Bronze ingestions (affected_years, keyed on ingestion_timestamp)
    and insert_overwrites just those. The latest_batch dedup partitions by
    (refYear, reporterCode), so pulling the FULL affected year — every reporter —
    keeps the latest-batch-wins dedup exact. On --full-refresh / first build the
    is_incremental() branch is skipped and all of Bronze is scanned.
-#}

{% if is_incremental() %}
with affected_years as (

    -- Years with Bronze rows newer than the current Silver max. `>=` (not `>`):
    -- a row appended at a clock-identical timestamp to the Silver max would be
    -- `> max` = false and skipped forever; re-scanning the boundary year is safe
    -- (insert_overwrite replaces the whole partition — idempotent) and bounded
    -- to the year(s) tied at the max, not the full history.
    select distinct refYear
    from {{ source('bronze_comtrade', 'comtrade_flows_raw') }}
    where ingestion_timestamp >= (
        select coalesce(max(ingestion_timestamp), timestamp '1970-01-01') from {{ this }}
    )

),

latest_batch as (

    -- Pull EVERY Bronze row for the affected years (all reporters), so the
    -- per-(refYear, reporterCode) latest-batch dedup below sees the full
    -- partition; insert_overwrite then replaces only those reference_year
    -- partitions.
    select b.*
    from {{ source('bronze_comtrade', 'comtrade_flows_raw') }} b
    inner join affected_years ay on b.refYear = ay.refYear
    qualify ingestion_timestamp
        = max(ingestion_timestamp) over (partition by refYear, reporterCode)

),
{% else %}
with latest_batch as (

    -- First build / --full-refresh: scan all of Bronze.
    select *
    from {{ source('bronze_comtrade', 'comtrade_flows_raw') }}
    qualify ingestion_timestamp
        = max(ingestion_timestamp) over (partition by refYear, reporterCode)

),
{% endif %}

deduplicated as (

    -- TOTALS-ONLY grain (2026-07). Keep ONLY the fully-aggregated record on EVERY
    -- dimension: customsCode = C00 ("todos os regimes / total"), the two direction
    -- TOTALS X/M (their RX/RM/DX/… sub-flows are subsets — neither ingested nor kept),
    -- and the transport / supply / second-partner aggregates (mot/mos/partner2 = '0').
    -- Where a reporter also breaks C00 into per-regime rows, C00 = Σ(breakdowns)
    -- (verified: 100% reconciliation over 306k keys), so keeping only C00 is LOSSLESS
    -- for the total. This makes the base HOMOGENEOUS across reporters (every country
    -- reports the C00/X/M totals) and structurally free of the customs / flow / mode
    -- double-counts. reference_year is floored at the ingest start year (2000) so a
    -- re-anchored window doesn't keep stale pre-2000 rows the ingest no longer refreshes.
    select *
    from latest_batch
    where partnerCode != '0'                        -- drop the World partner aggregate
      and flowCode in ('X', 'M')                     -- the two direction TOTALS only
      and customsCode = 'C00'                         -- the all-regimes TOTAL only
      and length(cmdCode) = 6                         -- HS6 only (exclude legacy HS4)
      and motCode = '0'                               -- ┐ aggregate over transport /
      and partner2Code = '0'                          -- │ supply / second-partner
      and mosCode = '0'                               -- ┘
      and cast(refYear as int64) >= {{ var('comtrade_min_year', 2000) }}
    qualify row_number() over (
        partition by
            refYear, reporterCode, partnerCode, partner2Code,
            cmdCode, flowCode, customsCode, mosCode, motCode
        -- NOT partitioned by qtyUnitCode: the same fully-aggregated trade is
        -- sometimes returned under TWO qtyUnitCodes (e.g. '8' kg AND '-1'
        -- no-quantity) with an IDENTICAL primary value, so keeping both would
        -- DOUBLE-COUNT the value in gold_comtrade_flows (#102). Ordering
        -- rationale: recency FIRST (the project-wide dedup contract — a
        -- corrected re-publication must win even when it arrives only under
        -- the '-1' variant), unit preference as the TIEBREAKER. This cannot
        -- re-break the #102 collapse: latest_batch already restricted the
        -- partition to ONE ingestion generation, whose rows share a single
        -- ingestion_timestamp, so the tiebreaker is what actually arbitrates
        -- the duplicate unit variants — preferring a real measurement unit
        -- over '-1' so qty_native stays meaningful.
        order by ingestion_timestamp desc, (qtyUnitCode = '-1')
    ) = 1

),

parsed as (

    select
        -- The two direction TOTALS → readable, stable `flow` tokens (the filter values
        -- the backend allowlist + frontend send). TOTALS-ONLY: only X/M reach here (the
        -- `deduplicated` WHERE already restricts to them); any other code → NULL flow →
        -- dropped by the final WHERE, a defensive backstop for stray historical rows.
        case flowCode
            when 'X'   then 'export'
            when 'M'   then 'import'
        end                                                 as flow,
        cast(refYear as int64)                              as reference_year,
        reporterCode                                        as reporter_code,
        partnerCode                                         as partner_code,
        partner2Code                                        as partner2_code,
        cmdCode                                             as cmd_code,
        substr(cmdCode, 1, 2)                               as hs_chapter,
        customsCode                                         as customs_code,
        mosCode                                             as mode_of_supply_code,
        motCode                                             as mode_of_transport_code,
        qtyUnitCode                                         as qty_unit_code,
        -- 0.0 sentinel ('quantity not collected') → NULL, not a real zero.
        nullif({{ safe_numeric('qty') }},     0)            as qty_native_raw,
        nullif({{ safe_numeric('netWgt') }},  0)            as net_weight_kg,
        nullif({{ safe_numeric('grossWgt') }}, 0)           as gross_weight_kg,
        -- primaryValue is the headline trade value (US$): FOB for exports,
        -- CIF for imports. cif/fob are kept where the reporter splits them out.
        {{ safe_numeric('primaryValue') }}                  as primary_value_usd,
        {{ safe_numeric('cifvalue') }}                      as cif_value_usd,
        {{ safe_numeric('fobvalue') }}                      as fob_value_usd,
        ingestion_timestamp
    from deduplicated

)

-- Physical-unit family for the reported quantity. comtrade_unit maps the
-- numeric qty_unit_code → a canonical unit label (unit_raw); unit_family_conversions
-- turns that into family / base_unit / to_base. Units outside the 5 families
-- (e.g. length in metres, packages) fall to 'desconhecida' with NULL qty_base —
-- never an invented conversion. net_weight_kg is always kilograms (massa), the
-- measure comparable across HS codes, and is summed directly in Gold.
select
    -- A TABELA da fonte, carimbada AQUI, na primeira camada tipada — cada modelo Silver
    -- sabe de qual tabela ele lê, então a informação nasce onde é conhecida em vez de ser
    -- reconstituída depois. Fecha o trio `(banco, tabela, código)` em TODOS os bancos:
    -- COMTRADE não vem do SIDRA: id é um nome do PROJETO (config.py).
    -- Com isso as uniões do Gold são `select *` puro e nenhum consumidor ramifica por
    -- banco para saber se há tabela. Ver docs/audits/chave_produto_audit_2026-08-30.md.
    '{{ var("comtrade_table_id") }}' as tabela,
    p.flow,
    p.reference_year,
    p.reporter_code,
    p.partner_code,
    p.partner2_code,
    -- Transparent full-history normalization: a retired HS6 (reported under the
    -- revision in force that year — banana 080300, soja 120100, castanha 080120,
    -- old ch.44 wood) is rewritten to its CURRENT equivalent, so Gold / serving /
    -- the dashboard only ever expose current codes. The raw reported value is kept
    -- in cmd_code_reported for audit. See seed comtrade_hs_succession.
    coalesce(succ.current_code, p.cmd_code)             as cmd_code,
    p.cmd_code                                          as cmd_code_reported,
    p.hs_chapter,
    p.customs_code,
    -- Tipo de mercado (consumo/processamento) is NO LONGER carried here: it reverted
    -- from the comtrade_market_nature seed (v1.9.0) back to the researcher-editable
    -- append-log, and is now derived in the serving layer (serving_comtrade_annual
    -- LEFT JOINs dim_flow_market_scd2). Keeping it out of Silver/Gold avoids inverting
    -- the medallion (an editable classification would otherwise reach back into the fact).
    p.mode_of_supply_code,
    p.mode_of_transport_code,
    p.qty_unit_code,
    u.unit_name                                             as unit_native,
    u.unit_symbol                                           as unit_native_symbol,
    coalesce(ufc.family, 'desconhecida')                    as family,
    ufc.base_unit                                           as base_unit,
    p.qty_native_raw                                        as qty_native,
    p.qty_native_raw * ufc.to_base                          as qty_base,
    p.net_weight_kg,
    p.gross_weight_kg,
    p.primary_value_usd,
    p.cif_value_usd,
    p.fob_value_usd,
    p.ingestion_timestamp
from parsed p
left join {{ ref('comtrade_unit') }} u
    on p.qty_unit_code = u.qty_unit_code
left join {{ ref('unit_family_conversions') }} ufc
    on nullif(u.unit_raw, '') = ufc.unit_raw
left join {{ ref('comtrade_hs_succession') }} succ
    on p.cmd_code = succ.reported_code
where p.flow is not null
