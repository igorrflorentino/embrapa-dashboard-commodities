"""Parameterized BigQuery SQL builders for the serving marts.

Every builder returns ``(sql, params)`` where ``params`` is a list of
``bigquery`` query-parameter objects. The dashboard's callbacks pass user
filters straight through as ``@param`` bindings — never string-formatted into
the SQL — so a malicious filter value can't alter the query (no SQL injection).

The one value that *cannot* be a bind parameter is a column identifier (you
cannot parameterize an identifier in standard SQL). The measure a chart sums is
chosen by the UI, so it is validated against :data:`ALLOWED_VALUE_COLUMNS`
before being interpolated — an allowlist, not escaping.

Pure module: builds strings and parameter objects, performs no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from google.cloud import bigquery

# Measures a chart may sum. Interpolated as an identifier (cannot be a bind
# param), so it MUST be validated against this allowlist first.
#
# EUR columns are served (the PEVS/PAM marts carry them — real BCB BRL/EUR
# series), so effective_value_column() resolves EUR server-side instead of
# falling back to BRL.
ALLOWED_VALUE_COLUMNS = frozenset(
    {
        "val_yearfx_brl",
        "val_yearfx_usd",
        "val_yearfx_eur",
        "val_real_ipca_brl",
        "val_real_ipca_usd",
        "val_real_ipca_eur",
        "val_real_igpm_brl",
        "val_real_igpm_eur",
        "val_real_igpdi_brl",
        "val_real_igpdi_eur",
        "net_weight_kg",
        "qty_base",
    }
)


def table_ref(settings, dataset_attr: str, table: str) -> str:
    """Build a fully-qualified `project.dataset.table` reference from settings."""
    project = settings.gcp_project_id
    dataset = getattr(settings, dataset_attr)
    return f"{project}.{dataset}.{table}"


def _validate_column(column: str, allowed: frozenset[str], kind: str) -> str:
    """Guard an interpolated identifier against an allowlist.

    Measure / filter / dimension / product columns cannot be bind parameters, so
    an allowlist — not escaping — is what keeps each one injection-safe.
    """
    if column not in allowed:
        raise ValueError(
            f"Coluna {column!r} não permitida; use uma de: {', '.join(sorted(allowed))}."
        )
    return column


def _year_bounds(
    conditions: list[str],
    params: list[bigquery.ScalarQueryParameter],
    year_start: int | None,
    year_end: int | None,
) -> None:
    if year_start is not None:
        conditions.append("reference_year >= @year_start")
        params.append(bigquery.ScalarQueryParameter("year_start", "INT64", year_start))
    if year_end is not None:
        conditions.append("reference_year <= @year_end")
        params.append(bigquery.ScalarQueryParameter("year_end", "INT64", year_end))


# Columns a filter may constrain with `IN UNNEST`. Like value_column, a column
# IDENTIFIER cannot be a bind parameter, so it is interpolated into the SQL and
# therefore MUST be validated against this allowlist. Every builder passes an
# internal literal today; this guarantees a future caller cannot interpolate a
# user-derived identifier (defense-in-depth — there is no current injection path).
# ``state_acronym`` is the UF-of-origin column the COMEX trade marts expose, used
# by the optional UF filter on the flow/partner readers (the filter VALUES stay
# bound — only this identifier is interpolated).
ALLOWED_FILTER_COLUMNS = frozenset(
    {
        "product_code",
        "ncm_code",
        "cmd_code",
        "state_acronym",
        "city_code",
        # COMTRADE country filters (reporter / partner side), narrowed via IN-list.
        "reporter_iso_a3",
        "partner_iso_a3",
    }
)

# Dimension columns the trade builders interpolate into SELECT / GROUP BY (origin,
# destination, partner — which differ by source: UF/country for COMEX,
# reporter/partner for COMTRADE). Same rule as value_column: an identifier cannot
# be bound, so each is validated against this allowlist before interpolation.
ALLOWED_DIMENSION_COLUMNS = frozenset(
    {
        "state_acronym",
        "state_name",
        "country_code",
        "country_name",
        "reporter_code",
        "reporter_name",
        "reporter_iso_a3",
        "partner_code",
        "partner_name",
        "partner_iso_a3",
    }
)


# Product key + label columns the products / productTS builders interpolate (one
# pair per source). Same allowlist rule as the other identifiers.
ALLOWED_PRODUCT_COLUMNS = frozenset(
    {
        "product_code",
        "product_description",
        "ncm_code",
        "ncm_description",
        "cmd_code",
        "cmd_description",
    }
)


def _in_array(
    conditions: list[str],
    params: list[bigquery.ArrayQueryParameter],
    column: str,
    param_name: str,
    values: Sequence[str],
) -> None:
    if values:
        _validate_column(column, ALLOWED_FILTER_COLUMNS, "filter column")
        conditions.append(f"{column} IN UNNEST(@{param_name})")
        params.append(bigquery.ArrayQueryParameter(param_name, "STRING", list(values)))


def _where(conditions: list[str]) -> str:
    return f"where {' and '.join(conditions)}" if conditions else ""


def _latest_year_condition(table: str, conditions: list[str]) -> str:
    """A predicate pinning ``reference_year`` to the MAX year under the SAME filters.

    The single-snapshot by-UF readers (``production_by_uf`` / ``comex_by_uf``) back
    a choropleth the UI labels as the latest year and compares against a latest-year
    national KPI — so they must aggregate ONE year, not cumulate the whole
    ``[year_start, year_end]`` window (which inflated every UF tile by the number of
    covered years). "Latest" honours the active period filter: the correlated
    subquery re-applies the same ``conditions`` (year bounds + product/code filters),
    so a user-scoped 2020-2022 request pins to 2022, not the table-wide max.

    The filter VALUES are still bound once (the outer query and the subquery share
    the SAME ``params`` list) — only the table identifier (already validated upstream)
    is interpolated.
    """
    inner = _where(conditions)
    return f"reference_year = (select max(reference_year) from `{table}` {inner})"


# The two PRIMARY UN Comtrade flows. re-export/re-import (and, if ingested, the other
# processing sub-flows) are SUBSETS of export/import — X already includes RX, M includes RM
# — so an "all flows" TOTAL must sum only these two, never add the sub-flows on top (that
# double-counts re-exports/re-imports). Verified in prod: summing every flow inflates the
# world total by ~0.3% (Brazil = 0, it reports no re-exports). COMTRADE readers pass this as
# ``sum_flows``; COMEX (no overlapping sub-flow) / PEVS (no flow column) pass None.
COMTRADE_TOTAL_FLOWS = ("export", "import")


def _flow(
    conditions: list[str],
    params: list[bigquery.ScalarQueryParameter],
    flow: str | None,
    *,
    sum_flows: tuple[str, ...] | None = None,
) -> None:
    """Flow predicate for the trade marts.

    - ``flow`` given → ``flow = @flow`` (the user picked one direction / sub-flow).
    - ``flow`` None + ``sum_flows`` → ``flow in (…)``: sum ONLY those flows (for COMTRADE,
      the primary totals :data:`COMTRADE_TOTAL_FLOWS`, so the re-export/re-import SUBSETS are
      not double-counted in an "all flows" total).
    - ``flow`` None + no ``sum_flows`` → no predicate (historical default; PEVS/COMEX).
    """
    if flow is not None:
        conditions.append("flow = @flow")
        params.append(bigquery.ScalarQueryParameter("flow", "STRING", flow))
    elif sum_flows:
        conditions.append("flow in unnest(@__sum_flows)")
        params.append(bigquery.ArrayQueryParameter("__sum_flows", "STRING", list(sum_flows)))


def _origem(
    conditions: list[str],
    params: list[bigquery.ScalarQueryParameter],
    origem: str | None,
) -> None:
    """Optional ``origem = @origem`` predicate — which half of the PEVS survey.

    ``extrativa`` (native forest, SIDRA t289) | ``silvicultura`` (planted, t291).

    ``None`` sums both, which is the survey's own total and what "Produção da Extração
    Vegetal e da Silvicultura" names. It is also what keeps every OTHER production mart
    unchanged: PAM and PPM have no ``origem`` column, so a reader that never receives the
    param emits a byte-identical query to the one it emitted before the axis existed.

    Unlike COMTRADE's flow, the two halves are DISJOINT — no row belongs to both — so the
    unfiltered sum is a clean total with nothing double-counted. What it must never be is
    silent: `origem` reaches the chip, the ABNT citation and the CSV precisely because a
    number that mixes native and planted has to say so.
    """
    if origem is not None:
        conditions.append("origem = @origem")
        params.append(bigquery.ScalarQueryParameter("origem", "STRING", origem))


def _customs(
    conditions: list[str],
    params: list[bigquery.ScalarQueryParameter],
    customs: str | None,
) -> None:
    """Optional `customs_code = @customs` predicate — the customs procedure (regime
    aduaneiro; UN Comtrade customsCode). None/absent references customs_code at all →
    the reader sums over every regime = the bilateral total (C00 and the per-regime
    breakdowns are mutually exclusive per key in silver_comtrade_flows, so the SUM is a
    clean total, and a request without this param stays byte-identical to before the
    regime dimension existed). Only the COMTRADE mart carries customs_code."""
    if customs is not None:
        conditions.append("customs_code = @customs")
        params.append(bigquery.ScalarQueryParameter("customs", "STRING", customs))


def _market_nature(
    conditions: list[str],
    params: list[bigquery.ScalarQueryParameter],
    market: str | None,
) -> None:
    """Optional `market_nature = @market` predicate — the tipo de mercado (economic
    purpose: consumo/processamento), edit-driven per (customs_code × flow). None/absent
    references market_nature at all → sums over every purpose (incl. the unmapped NULL rows),
    so a request without this param is byte-identical to before the dimension existed. Only
    the COMTRADE mart carries market_nature."""
    if market is not None:
        conditions.append("market_nature = @market")
        params.append(bigquery.ScalarQueryParameter("market", "STRING", market))


def _reporter(
    conditions: list[str],
    params: list[bigquery.ScalarQueryParameter],
    reporter_column: str | None,
    reporter_value: str | None,
) -> None:
    """Optional `<reporter_column> = @reporter` predicate pinning the COMTRADE
    reporter side to one country (Brazil). The COMTRADE marts are multi-reporter,
    so the Brazil-perspective views (partner ranking, flow Sankey, per-country
    cross metrics) must filter the reporter; COMEX (Brazil's own customs) leaves it
    unset. The VALUE is bound; the identifier is allowlist-validated (it is never
    request-derived — callers pass an internal literal column name)."""
    if reporter_value is not None:
        reporter_column = _validate_column(
            reporter_column, ALLOWED_DIMENSION_COLUMNS, "dimension column"
        )
        conditions.append(f"{reporter_column} = @reporter")
        params.append(bigquery.ScalarQueryParameter("reporter", "STRING", reporter_value))


def _value_sum(value_column: str, has_measure_kind: bool) -> str:
    """SQL for the value aggregation.

    For a source carrying the stock|flow ``measure_kind`` discriminator (PPM),
    value is FLOW-only by contract — herd STOCK rows (efetivo, cabeças) have no
    monetary value. The value column is already NULL on stock rows
    (gold_ppm_production leaves it NULL by design), so this CASE is a semantic
    no-op today; it makes the "value applies only to flow" contract EXPLICIT in
    the SQL and defends against a future upstream row that leaks a non-NULL value
    onto a stock row. Quantity aggregations are intentionally NOT guarded — a herd
    headcount is a valid quantity that backs the dedicated Rebanho view.
    ``value_column`` is caller-validated against ALLOWED_VALUE_COLUMNS.
    """
    if has_measure_kind:
        return f"sum(case when measure_kind = 'flow' then {value_column} end)"
    return f"sum({value_column})"


def production_overview(
    table: str,
    *,
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    uf_codes: Sequence[str] = (),
    has_measure_kind: bool = False,
    origem: str | None = None,
) -> tuple[str, list]:
    """Annual production total from ``serving_pevs_annual`` (backs overviewTS).

    ``uf_codes`` optionally narrows to the producing UFs (``state_acronym``) — the
    PEVS mart carries it; empty/absent = national (no filter). Used by the
    cross-source views' per-UF scoping."""
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _origem(conditions, params, origem)
    _in_array(conditions, params, "product_code", "product_codes", product_codes)
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    sql = f"""
        select
            reference_year,
            {_value_sum(value_column, has_measure_kind)} as total_value,
            sum(source_rows)    as source_rows
        from `{table}`
        {_where(conditions)}
        group by reference_year
        order by reference_year
    """
    return sql, params


def production_by_uf(
    table: str,
    *,
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    latest_year_only: bool = True,
    has_measure_kind: bool = False,
    origem: str | None = None,
) -> tuple[str, list]:
    """Production aggregated by UF from ``serving_pevs_annual`` (backs ufData).

    By default scoped to the LATEST year within the active ``[year_start, year_end]``
    window (``latest_year_only=True``), NOT cumulated over the whole window: the
    choropleth this backs is labelled — and compared against a latest-year national
    KPI — as a single year, so summing every covered year inflated each UF by the
    number of covered years. ``ufYearly`` (``production_by_uf_yearly``) keeps the
    full per-year history. ``latest_year_only=False`` restores the window-cumulative
    sum, which the export-coefficient by-UF reader needs (it compares production and
    export accumulated over the SAME common-year window).

    Quantities are split by ``family`` so they are only ever summed WITHIN a unit
    family (the same rule the marts enforce): ``q_mass`` sums ``qty_base`` (t) of
    the 'massa' family, ``q_vol`` sums ``qty_base`` (m³) of 'volume'. qty_base —
    not qty_native — is the only summable quantity across a family's mixed-unit
    codes. The serializer scales them to mil t / mi m³.
    """
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _origem(conditions, params, origem)
    _in_array(conditions, params, "product_code", "product_codes", product_codes)
    # `uf_codes` narrows to the researcher's selected states. It is applied BEFORE the
    # latest-year pin below, deliberately: with a UF filter active the reference year
    # must be the latest year THOSE states have, not the country's. A state whose
    # series ends earlier would otherwise pin to a year it has no rows in and read as
    # having stopped producing.
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    if latest_year_only:
        # Pin to the latest year under the same filters (correlated subquery reuses
        # the same bound params) — appended last so the subquery's WHERE excludes it.
        conditions.append(_latest_year_condition(table, conditions))
    sql = f"""
        select
            state_acronym,
            any_value(state_name)   as state_name,
            any_value(region)       as region,
            any_value(region_abbrev) as region_abbrev,
            {_value_sum(value_column, has_measure_kind)}     as total_value,
            sum(case when family = 'massa'  then qty_base end) as q_mass,
            sum(case when family = 'volume' then qty_base end) as q_vol,
            sum(case when family = 'contagem' then qty_base end) as q_count
        from `{table}`
        {_where(conditions)}
        group by state_acronym
        order by total_value desc
    """
    return sql, params


def production_by_uf_yearly(
    table: str,
    *,
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    has_measure_kind: bool = False,
    origem: str | None = None,
) -> tuple[str, list]:
    """Production by (UF, year) from ``serving_pevs_annual`` (backs the ano × UF heatmap).

    The year-grained companion to :func:`production_by_uf`: it adds
    ``reference_year`` to the grain so the geography heatmap renders REAL per-UF
    history instead of fabricating it from the national curve. Quantities are
    split by ``family`` (``q_mass`` = ``qty_base`` t of 'massa', ``q_vol`` = m³ of
    'volume') so they are only ever summed WITHIN a unit family — the same rule
    :func:`production_by_uf` follows.
    """
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _origem(conditions, params, origem)
    _in_array(conditions, params, "product_code", "product_codes", product_codes)
    sql = f"""
        select
            state_acronym,
            reference_year,
            any_value(state_name)    as state_name,
            any_value(region)        as region,
            any_value(region_abbrev) as region_abbrev,
            {_value_sum(value_column, has_measure_kind)}      as total_value,
            sum(case when family = 'massa'  then qty_base end) as q_mass,
            sum(case when family = 'volume' then qty_base end) as q_vol,
            sum(case when family = 'contagem' then qty_base end) as q_count
        from `{table}`
        {_where(conditions)}
        group by state_acronym, reference_year
        order by state_acronym, reference_year
    """
    return sql, params


def visibility_clause(settings, source_short: str, code_column: str) -> str:
    """The F7 Ciclo-de-Vida visibility gate, as a NOT EXISTS predicate — for the
    gateway's DIRECT-Gold readers (município drill-down, quality timeseries/by-product),
    which bypass the gated serving marts. Excludes any Gold row whose code matches a
    commodity a researcher marked "indisponível" (``dim_produto_visibility``) — the SAME
    single source of truth as the dbt ``hidden_code_predicate`` macro, never re-derived.
    ``source_short`` is the short banco token (pevs/pam/ppm/comex/comtrade); ``code_column``
    is this Gold table's product/NCM/HS code. A no-op while the view is empty (nothing
    hidden). Identifiers come from fixed gateway maps (never user input) → injection-safe.
    """
    vis = table_ref(settings, "bq_gold_dataset", "dim_produto_visibility")
    return (
        f"not exists (select 1 from `{vis}` v "
        f"where v.source = '{source_short}' and {code_column} = v.code)"
    )


def production_by_municipio_yearly(
    table: str,
    *,
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    city_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    visibility_predicate: str = "",
    origem: str | None = None,
) -> tuple[str, list]:
    """Production by (município, year) straight from ``gold_<source>_production``,
    which is ALREADY município-grained — backs the sub-UF + live-município geography
    cascade.

    Município is the finest grain and an on-demand/gated level, so it reads Gold
    DIRECTLY (basket-scoped + the gateway's ``maximum_bytes_billed`` guard) rather
    than via a redundant ~município-grain serving mart that would nearly duplicate
    Gold. ``city_codes`` is the KEY cost control: the client resolves the active
    sub-UF/município selection to its município code set via the cached mesh and
    passes it here, so a one-mesorregião narrowing scans ~tens of cities, not all
    ~5570 — the full município×year grid is ~146k rows, far too heavy to ship whole.
    The client then rolls these (already-narrowed) city rows up to the selected level.
    Quantities split by ``family`` so they are only ever summed WITHIN a unit family —
    identical rule to :func:`production_by_uf_yearly`."""
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _origem(conditions, params, origem)
    _in_array(conditions, params, "product_code", "product_codes", product_codes)
    _in_array(conditions, params, "city_code", "city_codes", city_codes)
    if visibility_predicate:
        conditions.append(visibility_predicate)
    sql = f"""
        select
            city_code,
            state_acronym,
            reference_year,
            sum({value_column})      as total_value,
            sum(case when family = 'massa'    then qty_base end) as q_mass,
            sum(case when family = 'volume'   then qty_base end) as q_vol,
            sum(case when family = 'contagem' then qty_base end) as q_count
        from `{table}`
        {_where(conditions)}
        group by city_code, state_acronym, reference_year
        order by city_code, reference_year
    """
    return sql, params


def products_by_municipio(
    table: str,
    *,
    code_column: str = "product_code",
    name_column: str = "product_description",
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    city_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    visibility_predicate: str = "",
    origem: str | None = None,
) -> tuple[str, list]:
    """Per-PRODUCT ranking WITHIN a município selection — what the território profile
    needs to answer "o que este município produz".

    This is to :func:`production_by_municipio_yearly` what :func:`products_by_uf` is to
    :func:`production_by_uf`: the município cube GROUPs BY city and sums products away,
    so it can plot a place's trajectory but can never name the products behind it.

    Reads Gold directly for the same reason the município cube does (finest grain, no
    mart), and carries the SAME cost control: ``city_codes`` is required by the caller,
    so this only ever scans the selected cities. Quantities stay split by ``family`` —
    they are only summable WITHIN a family.
    """
    code_column = _validate_column(code_column, ALLOWED_PRODUCT_COLUMNS, "product column")
    name_column = _validate_column(name_column, ALLOWED_PRODUCT_COLUMNS, "product column")
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, code_column, "product_codes", product_codes)
    _in_array(conditions, params, "city_code", "city_codes", city_codes)
    # The PEVS half — see products_by_uf. This reader names the produtos behind a place,
    # and madeira/lenha/carvão exist in BOTH halves, so without it a território profile
    # filtered to one half lists the other's produtos alongside.
    _origem(conditions, params, origem)
    if visibility_predicate:
        conditions.append(visibility_predicate)
    sql = f"""
        select
            {code_column}                                        as product_code,
            any_value({name_column})                             as product_name,
            sum({value_column})                                  as total_value,
            sum(case when family = 'massa'    then qty_base end) as q_mass,
            sum(case when family = 'volume'   then qty_base end) as q_vol,
            sum(case when family = 'contagem' then qty_base end) as q_count
        from `{table}`
        {_where(conditions)}
        group by {code_column}
        order by total_value desc
    """
    return sql, params


def geo_municipio_mesh(table: str) -> tuple[str, list]:
    """The full IBGE municipal territorial mesh (``dim_geo_municipio``) — every
    município with its UF + grande região AND BOTH sub-UF divisions (classic
    mesorregião/microrregião and current intermediária/imediata).

    Static reference (~5570 rows), served once and cached: the SPA's geo cascade
    resolves ``city_code`` → ancestry, builds the per-level option lists from it,
    and aggregates the município cube up to the selected level. No params (the whole
    mesh is small and shared across bancos/conventions)."""
    sql = f"""
        select
            city_code, city_name,
            uf_code, state_acronym, state_name,
            region_code, region_abbrev, region_name,
            meso_code, meso_name,
            micro_code, micro_name,
            intermediaria_code, intermediaria_name,
            imediata_code, imediata_name
        from `{table}`
        order by city_code
    """
    return sql, []


def productivity(
    table: str,
    *,
    product_code: str,
    year_start: int | None = None,
    year_end: int | None = None,
    uf_codes: Sequence[str] = (),
) -> tuple[str, list]:
    """Production (t) + planted/harvested area (ha) by (year, UF) for ONE crop,
    from a PAM-shaped mart (``serving_pam_annual``; backs ViewProductivity).

    Yield (kg/ha) is a RATIO — not summable — so it is deliberately NOT aggregated
    here; the seam recomputes it as ``production_kg / area_harvested_ha`` at each
    grain it needs (national per year, per UF for the latest year). ``product_code``
    is bound as a parameter (one crop at a time, picked by the view's selector).
    ``year_start``/``year_end`` apply the view's active period filter, and
    ``uf_codes`` the state filter.

    Because yield is a ratio, the UF filter is NOT cosmetic here: narrowing the rows
    changes the aggregate the serializer recomputes, so the "national" series becomes
    the selected states' series. The view relabels it accordingly — a ratio over a
    subset presented as a national figure would be a wrong number, not a smaller one.
    """
    conditions: list[str] = ["product_code = @product_code"]
    params: list = [bigquery.ScalarQueryParameter("product_code", "STRING", product_code)]
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    sql = f"""
        select
            reference_year,
            state_acronym,
            any_value(state_name)        as state_name,
            any_value(region)            as region,
            any_value(region_abbrev)     as region_abbrev,
            sum(qty_native)              as production_t,
            sum(area_planted_ha)         as area_planted_ha,
            sum(area_harvested_ha)       as area_harvested_ha
        from `{table}`
        {_where(conditions)}
        group by reference_year, state_acronym
        order by reference_year, state_acronym
    """
    return sql, params


def products_by_uf(
    table: str,
    *,
    code_column: str,
    name_column: str,
    year_start: int | None = None,
    year_end: int | None = None,
    codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
    value_column: str = "val_yearfx_usd",
    flow: str | None = None,
    origem: str | None = None,
) -> tuple[str, list]:
    """Per-PRODUCT ranking WITHIN a UF selection (backs the "Base de dados" per-UF
    product breakdown). This is the INVERSE of production_by_uf / comex_by_uf (which
    GROUP BY state and sum products away): here we GROUP BY the product and constrain
    ``state_acronym`` to the selected UFs (``uf_codes``).

    Works for PEVS production (``flow`` None, code_column=product_code) and COMEX
    export (``flow='export'``, code_column=ncm_code). Each row carries value plus the
    family-split ``q_mass`` (t) / ``q_vol`` (m³) so the view can rank by Capital,
    Volume(massa) or Volume(volume) — quantities only ever sum WITHIN a family.
    """
    code_column = _validate_column(code_column, ALLOWED_PRODUCT_COLUMNS, "product column")
    name_column = _validate_column(name_column, ALLOWED_PRODUCT_COLUMNS, "product column")
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, code_column, "codes", codes)
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    _flow(conditions, params, flow)
    # The PEVS half (extrativa | silvicultura). Threaded here for the same reason the four
    # aggregate builders already carry it: the two halves differ ~6x in value, so a ranking
    # computed over both while the chip says one half is a wrong number under a right label.
    # Left off on 2026-08-29 when the axis was introduced — the aggregate path honoured it
    # and this one silently did not.
    _origem(conditions, params, origem)
    sql = f"""
        select
            {code_column}                                      as product_code,
            any_value({name_column})                           as product_name,
            sum({value_column})                                as total_value,
            sum(case when family = 'massa'  then qty_base end) as q_mass,
            sum(case when family = 'volume' then qty_base end) as q_vol,
            sum(case when family = 'contagem' then qty_base end) as q_count
        from `{table}`
        {_where(conditions)}
        group by {code_column}
        order by total_value desc
    """
    return sql, params


def comex_seasonality(
    table: str,
    *,
    year_start: int | None = None,
    year_end: int | None = None,
    ncm_codes: Sequence[str] = (),
    flow: str | None = None,
    uf_codes: Sequence[str] = (),
) -> tuple[str, list]:
    """Monthly COMEX value + net weight from ``serving_comex_seasonality`` (backs
    monthlyData). Both metrics are carried so the seasonal profile can overlay
    Volume (peso) and Capital (US$) on the same month axis.

    ``uf_codes`` optionally narrows to the origin UFs (``state_acronym``) — the mart
    now keeps it in the grain (P6), so the seasonal profile can be scoped to one
    state; empty/absent = national."""
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, "ncm_code", "ncm_codes", ncm_codes)
    _flow(conditions, params, flow)
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    sql = f"""
        select
            reference_year,
            reference_month,
            any_value(month_abbr_pt) as month_abbr_pt,
            sum(val_yearfx_usd)      as total_value_usd,
            sum(net_weight_kg)       as total_weight_kg
        from `{table}`
        {_where(conditions)}
        group by reference_year, reference_month
        order by reference_year, reference_month
    """
    return sql, params


def months_present_per_year(table: str) -> tuple[str, list]:
    """Distinct ``reference_month`` count per ``reference_year`` from a monthly mart
    (``serving_comex_seasonality``; backs the partial-latest-year signal).

    A monthly-sourced banco's most recent year is often INCOMPLETE (e.g. COMEX
    publishes through the current month), so a headline YoY that compares a partial
    latest year against a full prior year over-reads as a crash/boom. The seam turns
    this (year → months) map into ``monthsInLatestYear`` / ``latestYearComplete`` /
    ``latestCompleteYear`` in source-meta so the frontend can compute YoY against the
    last COMPLETE year (or label the partial one). Cheap year×month aggregate, cached.
    """
    sql = f"""
        select
            reference_year,
            count(distinct reference_month) as n_months
        from `{table}`
        group by reference_year
        order by reference_year
    """
    return sql, []


def reporters_present_per_year(table: str) -> tuple[str, list]:
    """Distinct exporting ``reporter_iso_a3`` count per ``reference_year`` from the
    COMTRADE annual mart (backs the world-panel completeness signal for market share).

    UN Comtrade reporters file with a ~1-2y lag, so the most recent year(s) of the
    world export panel carry far fewer reporters than fully-settled years — dividing
    Brazil (a complete declarant) by that partial world total inflates the "current"
    share and fakes an upward tail / historic peak. The seam turns this (year ->
    reporters) map into the latest COMPLETE world year and clamps the share series/KPI
    to it. Cheap year aggregate, cached. ``flow`` is the constant literal the mart
    stores for exports (never user input).
    """
    sql = f"""
        select
            reference_year,
            count(distinct reporter_iso_a3) as n_reporters
        from `{table}`
        where flow = 'export'
        group by reference_year
        order by reference_year
    """
    return sql, []


def current_code_industrialization(table: str) -> tuple[str, list]:
    """Live current industrialization level per (source, code) from
    ``dim_code_industrialization_scd2``.

    The result of this query is the ONLY serving cache that a curation write
    invalidates (the marts are unaffected by a reclassification). The UI LEFT
    JOINs the Gold code universe (DISTINCT source/code) to this set on
    (source, code); an unmatched code is "a classificar".
    """
    sql = f"""
        select
            source,
            code,
            industrialization_level,
            edited_by,
            valid_from
        from `{table}`
        where is_current
        order by source, code
    """
    return sql, []


def current_flow_market(table: str) -> tuple[str, list]:
    """Live current market-nature per (customs_code, flow_code) from
    ``dim_flow_market_scd2`` — the researcher-editable (customs procedure × flow)
    matrix. A cleared pair (``market = ''``) is dropped, so only real
    classifications surface. Mirrors :func:`current_code_industrialization`: the
    matrix editor reads this live view (a fresh INSERT is visible immediately),
    while the mart's ``market_nature`` column lags to the next dbt build.
    """
    sql = f"""
        select
            customs_code,
            flow_code,
            market,
            edited_by,
            valid_from
        from `{table}`
        where is_current and market != ''
        order by customs_code, flow_code
    """
    return sql, []


# ── Trade marts (serving_comex_annual / serving_comtrade_annual) ──────────────
# Raw US$/kg sums; the snapshot layer scales to display magnitudes (÷1e9, ÷1e6)
# per frontend_data_contract.md §2. ``code_column`` is ncm_code (COMEX) or
# cmd_code (COMTRADE); the origin/destination/partner dimensions differ by source
# and are passed as validated identifiers.


def trade_overview(
    table: str,
    *,
    code_column: str,
    year_start: int | None = None,
    year_end: int | None = None,
    codes: Sequence[str] = (),
    flow: str | None = None,
    customs: str | None = None,
    market: str | None = None,
    value_column: str = "val_yearfx_usd",
    reporter_column: str | None = None,
    reporter_value: str | None = None,
    # Optional multi-country COMTRADE filters — reporter_iso_a3 / partner_iso_a3 IN
    # UNNEST(...). Mutually exclusive with the reporter_value scalar pin (the gateway
    # passes ONE or the other, never both). Empty = no filter.
    reporters: Sequence[str] = (),
    partners: Sequence[str] = (),
    sum_flows: tuple[str, ...] | None = None,
) -> tuple[str, list]:
    """Annual trade value + weight from a trade annual mart (backs overviewTS).

    ``value_column`` picks the currency×correction measure — the trade marts now
    carry the full {nominal, real IPCA/IGP-M/IGP-DI} × {BRL, USD, EUR} set (the
    real year-FX / deflated values, NULL pre-1994), so a BRL/EUR display serves the
    REAL column instead of the frontend cross-converting USD via a mock FX rate. The
    output alias stays ``total_value_usd`` (the seam renames it to ``total_value``)
    so the serializer is currency-agnostic regardless of which column is summed.

    ``reporter_*`` optionally pins a geo column (``reporter_iso_a3``) to one country
    (Brazil) for the multi-reporter COMTRADE mart, so the banco's OWN overviewTS is
    Brazil's view — NOT a sum over every reporter (which for the all-reporters years
    would conflate the entire world's trade). COMEX is Brazil's own customs and has
    no reporter dimension, so its caller leaves these ``None``.
    """
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, code_column, "codes", codes)
    _flow(conditions, params, flow, sum_flows=sum_flows)
    _customs(conditions, params, customs)
    _market_nature(conditions, params, market)
    _reporter(conditions, params, reporter_column, reporter_value)
    _in_array(conditions, params, "reporter_iso_a3", "reporters", reporters)
    _in_array(conditions, params, "partner_iso_a3", "partners", partners)
    sql = f"""
        select
            reference_year,
            sum({value_column}) as total_value_usd,
            sum(net_weight_kg)  as total_weight_kg,
            sum(source_rows)    as source_rows
        from `{table}`
        {_where(conditions)}
        group by reference_year
        order by reference_year
    """
    return sql, params


def comex_by_uf(
    table: str,
    *,
    year_start: int | None = None,
    year_end: int | None = None,
    ncm_codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
    flow: str | None = None,
    value_column: str = "val_yearfx_usd",
    latest_year_only: bool = True,
) -> tuple[str, list]:
    """COMEX value + weight by UF from ``serving_comex_annual`` (backs ufData for COMEX).

    By default scoped to the LATEST year within the active ``[year_start, year_end]``
    window (``latest_year_only=True``), NOT cumulated over the whole window — same
    reasoning as :func:`production_by_uf`: the choropleth is a single labelled year
    compared against a latest-year national KPI. ``latest_year_only=False`` restores
    the window-cumulative sum the export-coefficient by-UF reader needs.

    ``q_mass``/``q_vol`` sum ``qty_base`` (t / m³) per ``family`` — the family-split,
    summable quantity (the same basis the snapshot overview uses), so the COMEX
    geography map can render real mass/volume. ``total_weight_kg`` (raw kg) is kept
    for export_coefficient, which works in kg. ``value_column`` picks the
    currency×correction measure (BRL/USD/EUR — the real columns the mart now carries);
    the alias stays ``total_value_usd`` (the seam renames it ``total_value``).
    """
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, "ncm_code", "ncm_codes", ncm_codes)
    # See production_by_uf: applied before the latest-year pin so a UF filter reports
    # the latest year THOSE states have, not the country's.
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    _flow(conditions, params, flow)
    if latest_year_only:
        # Pin to the latest year under the same filters (correlated subquery reuses
        # the same bound params) — appended last so the subquery's WHERE excludes it.
        conditions.append(_latest_year_condition(table, conditions))
    sql = f"""
        select
            state_acronym,
            any_value(state_name)    as state_name,
            any_value(region)        as region,
            any_value(region_abbrev) as region_abbrev,
            sum({value_column})      as total_value_usd,
            sum(net_weight_kg)       as total_weight_kg,
            sum(case when family = 'massa'  then qty_base end) as q_mass,
            sum(case when family = 'volume' then qty_base end) as q_vol
        from `{table}`
        {_where(conditions)}
        group by state_acronym
        order by total_value_usd desc
    """
    return sql, params


def comex_by_uf_yearly(
    table: str,
    *,
    year_start: int | None = None,
    year_end: int | None = None,
    ncm_codes: Sequence[str] = (),
    flow: str | None = None,
    value_column: str = "val_yearfx_usd",
) -> tuple[str, list]:
    """COMEX value by (UF, year) from ``serving_comex_annual`` (backs the ano × UF heatmap).

    The year-grained companion to :func:`comex_by_uf`: same per-family ``qty_base``
    split, with ``reference_year`` added to the grain so the COMEX geography heatmap
    renders real per-UF history. ``total_value_usd`` (renamed by the seam to
    ``total_value``) is the choropleth/heatmap measure. ``value_column`` picks the
    currency×correction measure (BRL/USD/EUR — the real columns the mart now carries).
    """
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, "ncm_code", "ncm_codes", ncm_codes)
    _flow(conditions, params, flow)
    sql = f"""
        select
            state_acronym,
            reference_year,
            any_value(state_name)    as state_name,
            any_value(region)        as region,
            any_value(region_abbrev) as region_abbrev,
            sum({value_column})      as total_value_usd,
            sum(case when family = 'massa'  then qty_base end) as q_mass,
            sum(case when family = 'volume' then qty_base end) as q_vol
        from `{table}`
        {_where(conditions)}
        group by state_acronym, reference_year
        order by state_acronym, reference_year
    """
    return sql, params


# Partner-ranking metric → the SELECT alias to ORDER BY. The ranking dimension
# MUST be applied server-side (not by re-sorting a top-N-by-value page): a niche
# high-unit-price buyer — top of the "preço médio" ranking — has a small total
# value and would never appear in the value-ranked page, so a client-side re-sort
# would silently drop it. Keys are an exact-match enum (validated below); the
# values are trusted literal expressions, never user input.
_PARTNER_RANK_EXPR = {
    "value": "value_usd",
    "weight": "total_weight_kg",
    "price": "price_usd_per_kg",
}


def trade_by_partner(
    table: str,
    *,
    partner_code_column: str,
    partner_name_column: str,
    code_column: str,
    year_start: int | None = None,
    year_end: int | None = None,
    codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
    flow: str | None = None,
    sum_flows: tuple[str, ...] | None = None,
    customs: str | None = None,
    market: str | None = None,
    reporter_column: str | None = None,
    reporter_value: str | None = None,
    reporters: Sequence[str] = (),
    partners: Sequence[str] = (),
    rank_by: str = "value",
) -> tuple[str, list]:
    """Partner ranking with export/import split (backs partnerData).

    COMEX: partner = country_*; COMTRADE: partner = partner_*. The World partner is
    already dropped upstream (Silver), so no extra filter is needed for COMTRADE.

    ``flow`` narrows to one direction (export/import) so the server-side ranking is by
    that flow; ``None`` + ``sum_flows`` sums only the primary totals
    (:data:`COMTRADE_TOTAL_FLOWS`) so the ranking metrics (value_usd / total_weight_kg /
    price) never double-count the re-export/re-import SUBSETS (X ⊇ RX, M ⊇ RM). ``customs``
    (regime aduaneiro) and ``market`` (tipo de mercado) narrow the COMTRADE mart to one
    procedure / purpose; only ``un_comtrade`` carries them, so COMEX passes ``None`` for
    all four and its query stays byte-identical to before these were threaded.

    ``uf_codes`` optionally narrows to the origin UFs (``state_acronym``) — only the
    COMEX mart carries that column, so the COMTRADE caller leaves it empty (its
    origin is a reporter country, not a Brazilian UF). Empty/absent = no filter.

    ``reporter_*`` optionally pins the REPORTER side to one country (Brazil) — the
    COMTRADE mart is multi-reporter (it carries every reporter's bilateral flows,
    incl. the all-reporters years), so without this the ranking would conflate
    'Brazil's trade with partner X' with 'the world's trade with X'. COMEX is
    Brazil's own customs (no reporter concept), so its caller leaves it unset.

    ``rank_by`` ∈ {value, weight, price} picks the ORDER BY dimension so the
    top-N cut (applied by the serializer) is the top-N *by that metric*: ``value``
    = total traded US$, ``weight`` = net weight (kg), ``price`` = implied unit
    price (US$/kg = value ÷ weight). Each row carries all three measures regardless,
    so the view can switch the displayed metric without a re-fetch when the cut is
    unaffected — but a re-fetch with the new ``rank_by`` is needed to re-rank.
    """
    partner_code_column = _validate_column(
        partner_code_column, ALLOWED_DIMENSION_COLUMNS, "dimension column"
    )
    partner_name_column = _validate_column(
        partner_name_column, ALLOWED_DIMENSION_COLUMNS, "dimension column"
    )
    order_expr = _PARTNER_RANK_EXPR.get(rank_by, "value_usd")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, code_column, "codes", codes)
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    _flow(conditions, params, flow, sum_flows=sum_flows)
    _customs(conditions, params, customs)
    _market_nature(conditions, params, market)
    _reporter(conditions, params, reporter_column, reporter_value)
    _in_array(conditions, params, "reporter_iso_a3", "reporters", reporters)
    _in_array(conditions, params, "partner_iso_a3", "partners", partners)
    sql = f"""
        select
            {partner_code_column}                                  as partner_code,
            any_value({partner_name_column})                       as partner_name,
            sum(case when flow = 'export' then val_yearfx_usd end) as exp_value_usd,
            sum(case when flow = 'import' then val_yearfx_usd end) as imp_value_usd,
            sum(val_yearfx_usd)                                    as value_usd,
            sum(net_weight_kg)                                     as total_weight_kg,
            safe_divide(sum(val_yearfx_usd), sum(net_weight_kg))   as price_usd_per_kg
        from `{table}`
        {_where(conditions)}
        group by {partner_code_column}
        order by {order_expr} desc nulls last
    """
    return sql, params


def trade_flows(
    table: str,
    *,
    origin_code_column: str,
    origin_name_column: str,
    dest_code_column: str,
    dest_name_column: str,
    code_column: str,
    year_start: int | None = None,
    year_end: int | None = None,
    codes: Sequence[str] = (),
    flow: str | None = None,
    sum_flows: tuple[str, ...] | None = None,
    customs: str | None = None,
    market: str | None = None,
    uf_codes: Sequence[str] = (),
    reporter_column: str | None = None,
    reporter_value: str | None = None,
    reporters: Sequence[str] = (),
    partners: Sequence[str] = (),
) -> tuple[str, list]:
    """Origin->destination links for the Sankey (backs flowData).

    COMEX: origin = UF (state), dest = country. COMTRADE: origin = reporter,
    dest = partner. ``value_usd`` is raw ``val_yearfx_usd``.

    ``flow`` narrows to one direction; ``None`` + ``sum_flows`` sums only the primary
    totals (:data:`COMTRADE_TOTAL_FLOWS`) so the Sankey links never double-count the
    re-export/re-import SUBSETS. ``customs`` (regime aduaneiro) and ``market`` (tipo de
    mercado) narrow the COMTRADE mart to one procedure / purpose; only ``un_comtrade``
    carries them, so COMEX passes ``None`` and its query stays byte-identical.

    ``uf_codes`` optionally narrows to the origin UFs (``state_acronym``) — only the
    COMEX mart carries that column, so the COMTRADE caller leaves it empty (its
    origin is a reporter country, not a Brazilian UF). Empty/absent = no filter.

    ``reporter_*`` optionally pins the REPORTER side to Brazil for the multi-reporter
    COMTRADE mart, so the Sankey shows Brazil's own export/import links rather than
    every reporter's flows blended together (which surfaced non-Brazil origin nodes
    for the all-reporters years). COMEX (Brazil's own customs) leaves it unset.
    """
    origin_code_column = _validate_column(
        origin_code_column, ALLOWED_DIMENSION_COLUMNS, "dimension column"
    )
    origin_name_column = _validate_column(
        origin_name_column, ALLOWED_DIMENSION_COLUMNS, "dimension column"
    )
    dest_code_column = _validate_column(
        dest_code_column, ALLOWED_DIMENSION_COLUMNS, "dimension column"
    )
    dest_name_column = _validate_column(
        dest_name_column, ALLOWED_DIMENSION_COLUMNS, "dimension column"
    )
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, code_column, "codes", codes)
    _flow(conditions, params, flow, sum_flows=sum_flows)
    _customs(conditions, params, customs)
    _market_nature(conditions, params, market)
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    _reporter(conditions, params, reporter_column, reporter_value)
    _in_array(conditions, params, "reporter_iso_a3", "reporters", reporters)
    _in_array(conditions, params, "partner_iso_a3", "partners", partners)
    sql = f"""
        select
            {origin_code_column}             as origin_code,
            any_value({origin_name_column})  as origin_name,
            {dest_code_column}               as dest_code,
            any_value({dest_name_column})    as dest_name,
            sum(val_yearfx_usd)              as value_usd
        from `{table}`
        {_where(conditions)}
        group by {origin_code_column}, {dest_code_column}
        order by value_usd desc
    """
    return sql, params


def comtrade_countries(table: str) -> tuple[str, list]:
    """Distinct reporter + partner countries in the COMTRADE mart (backs the country
    pickers). One row per (role, iso, name, code); ``role`` ∈ {reporter, partner}. The
    two universes differ (~203 reporters vs ~246 partners), so BOTH are returned and
    split by ``role`` in the seam. No bound params — a small DISTINCT over the clustered
    mart, memoized so it runs once."""
    sql = f"""
        select
            'reporter'               as role,
            reporter_iso_a3          as iso,
            any_value(reporter_name) as name,
            any_value(reporter_code) as code
        from `{table}`
        where reporter_iso_a3 is not null
        group by reporter_iso_a3
        union all
        select
            'partner'                as role,
            partner_iso_a3           as iso,
            any_value(partner_name)  as name,
            any_value(partner_code)  as code
        from `{table}`
        where partner_iso_a3 is not null
        group by partner_iso_a3
        order by role, name
    """
    return sql, []


def quality_timeseries(table: str, *, visibility_predicate: str = "") -> tuple[str, list]:
    """data_quality_flag counts per year, straight from a Gold table (backs the
    quality-over-time charts). A small year×flag aggregate — cheap columnar scan,
    memoized by flask-caching. The serving layer has no year-grained quality mart,
    so this reads Gold directly (the same source ``serving_quality_by_source``
    aggregates); promote to a mart if it ever gets hot."""
    where = f"where {visibility_predicate}" if visibility_predicate else ""
    sql = f"""
        select
            reference_year,
            data_quality_flag,
            count(*) as n
        from `{table}`
        {where}
        group by reference_year, data_quality_flag
        order by reference_year
    """
    return sql, []


def flow_market_values(table: str) -> tuple[str, list]:
    """Total traded value (nominal US$) per (customs_code, flow) from the serving mart —
    the materiality signal shown in each matrix cell so a researcher classifies the pairs
    that actually move value. The C00 aggregate ("todos os regimes / total") is excluded:
    it is not a real regime to classify (the matrix rows are the specific C0x procedures).
    Cheap grouped sum over the pre-aggregated mart — no Bronze scan. ``flow`` is the
    normalized token (export/import/…), aliased to ``flow_code`` to match the log grain."""
    sql = f"""
        select
            customs_code,
            flow                as flow_code,
            sum(val_yearfx_usd) as value_usd
        from `{table}`
        where customs_code != 'C00'
        group by customs_code, flow
    """
    return sql, []


def market_nature_series(table: str, *, codes: Sequence[str] = ()) -> tuple[str, list]:
    """COMTRADE trade value (nominal US$) by (economic-purpose market_nature × year) from
    the serving mart. ``market_nature`` is the consumo/processamento column, now EDIT-DRIVEN
    (LEFT JOIN dim_flow_market_scd2, reverted from the comtrade_market_nature seed; NULL where
    the customs×flow pair is unclassified — excluded). Optional ``codes`` narrows to one
    commodity's HS codes (cmd_code). The mart already dedups + preserves customs/flow, so this
    is a plain grouped sum (no Bronze scan). Reflects a matrix edit after the next dbt build.
    Sums only the PRIMARY flows (export/import): re-export/re-import are SUBSETS of those (X ⊇
    RX, M ⊇ RM), so including them would double-count re-exported/re-imported value — this
    reader is NOT reporter-pinned, so it sees every reporter's re-exports (Brazil has none)."""
    conditions = ["market_nature is not null", "flow in unnest(@__sum_flows)"]
    params: list = [
        bigquery.ArrayQueryParameter("__sum_flows", "STRING", list(COMTRADE_TOTAL_FLOWS))
    ]
    if codes:
        conditions.append("cmd_code IN UNNEST(@cmd_codes)")
        params.append(bigquery.ArrayQueryParameter("cmd_codes", "STRING", list(codes)))
    sql = f"""
        select
            market_nature,
            reference_year,
            sum(val_yearfx_usd) as value_usd
        from `{table}`
        {_where(conditions)}
        group by market_nature, reference_year
        order by reference_year
    """
    return sql, params


def quality_by_product(
    table: str, *, code_column: str, name_column: str, visibility_predicate: str = ""
) -> tuple[str, list]:
    """data_quality_flag counts per product, from a Gold table (backs the
    per-product quality FlagBars). Same cheap-aggregate rationale as
    :func:`quality_timeseries`. ``code_column``/``name_column`` are validated
    identifiers (one pair per source)."""
    code_column = _validate_column(code_column, ALLOWED_PRODUCT_COLUMNS, "product column")
    name_column = _validate_column(name_column, ALLOWED_PRODUCT_COLUMNS, "product column")
    where = f"where {visibility_predicate}" if visibility_predicate else ""
    sql = f"""
        select
            {code_column}            as code,
            any_value({name_column}) as name,
            data_quality_flag,
            count(*)                 as n
        from `{table}`
        {where}
        group by {code_column}, data_quality_flag
    """
    return sql, []


def quality_by_source(
    table: str,
    *,
    source: str | None = None,
) -> tuple[str, list]:
    """data_quality_flag breakdown from ``serving_quality_by_source`` (backs quality)."""
    conditions: list[str] = []
    params: list = []
    if source is not None:
        conditions.append("source = @source")
        params.append(bigquery.ScalarQueryParameter("source", "STRING", source))
    sql = f"""
        select
            source,
            data_quality_flag,
            n_rows,
            share
        from `{table}`
        {_where(conditions)}
        order by n_rows desc
    """
    return sql, params


# ── products / productTS — uniform across the three annual marts ──────────────
# All three marts (serving_{pevs,comex,comtrade}_annual) carry the same
# family/unit_native/base_unit/qty_native/qty_base set, so these two builders work
# for any source by swapping the code/name columns. ``unit`` = base_unit (the
# normalised unit), ``unit_native`` = the source label that qty_native is in.


def products(
    table: str, *, code_column: str, name_column: str, with_measure_kind: bool = False
) -> tuple[str, list]:
    """Distinct product list ``(code, name, unit, unit_native, family)`` (backs `products`).

    ``with_measure_kind`` adds ``measure_kind`` (stock | flow) — the livestock
    discriminator that ONLY ``serving_ppm_annual`` carries. The seam sets it for PPM
    so the herd (stock, value-less) can be told apart from animal-product flows (eggs,
    milk) that share the ``contagem`` family. Other marts have no such column, so the
    flag defaults False and the SELECT stays schema-compatible with them.
    """
    code_column = _validate_column(code_column, ALLOWED_PRODUCT_COLUMNS, "product column")
    name_column = _validate_column(name_column, ALLOWED_PRODUCT_COLUMNS, "product column")
    extra = ",\n            any_value(measure_kind) as measure_kind" if with_measure_kind else ""
    sql = f"""
        select
            {code_column}            as code,
            any_value({name_column}) as name,
            any_value(base_unit)     as unit,
            any_value(unit_native)   as unit_native,
            any_value(family)        as family{extra}
        from `{table}`
        group by {code_column}
        order by {code_column}
    """
    return sql, []


def product_timeseries(
    table: str,
    *,
    code_column: str,
    value_column: str = "val_yearfx_usd",
    year_start: int | None = None,
    year_end: int | None = None,
    codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
    flow: str | None = None,
    sum_flows: tuple[str, ...] | None = None,
    customs: str | None = None,
    market: str | None = None,
    reporter_column: str | None = None,
    reporter_value: str | None = None,
    reporters: Sequence[str] = (),
    partners: Sequence[str] = (),
    has_measure_kind: bool = False,
) -> tuple[str, list]:
    """Annual per-product series — value + quantities (backs productTS).

    ``total_qty_native`` is the statistical quantity in ``unit_native`` (used by
    the PEVS cross-source views, whose codes are single-family). ``q_mass`` and
    ``q_vol`` are the family base unit (t for 'massa', m³ for 'volume') summed
    PER FAMILY via CASE — mass and volume are NEVER summed together, and a
    count/energy/area family contributes to neither (it has no display scale), so
    the snapshot can never mis-scale a non-mass/volume quantity nor blend units
    for a mixed-unit code. ``family`` (the any_value tag) rides along for the UI;
    a code is conceptually single-family.

    ``uf_codes`` optionally narrows to the producing/origin UFs (``state_acronym``)
    — the PEVS/COMEX marts carry it; empty/absent = national. Used by the
    cross-source views' per-UF scoping (PEVS prod_mass/volume + farm-gate price).

    ``flow`` optionally narrows to one trade direction (export/import) — only the
    trade marts carry a ``flow`` column, so callers pass it ONLY for trade sources
    (the seam's trade branch); production marts always receive ``None``, leaving the
    predicate absent. ``None`` + ``sum_flows`` sums ONLY those flows (for COMTRADE the
    primary totals :data:`COMTRADE_TOTAL_FLOWS`, so the re-export/re-import SUBSETS are
    not double-counted in an "all flows" total); ``None`` + no ``sum_flows`` sums every
    flow (the historical default; COMEX has no overlapping sub-flow so it passes None).

    ``customs`` (regime aduaneiro) and ``market`` (tipo de mercado) optionally narrow
    to one customs procedure / economic purpose — ONLY the COMTRADE mart carries
    ``customs_code`` and ``market_nature``, so callers pass them solely for
    ``un_comtrade``. ``None`` sums every regime / purpose (the total), so a request
    without them stays byte-identical to before those dimensions existed.

    ``reporter_*`` optionally pins ``reporter_iso_a3`` to one country (Brazil) for
    the multi-reporter COMTRADE mart, so the banco's OWN per-product series is
    Brazil's view rather than a sum over every reporter (which would conflate the
    whole world's trade in the all-reporters years). Production/COMEX marts have no
    reporter dimension, so their callers leave these ``None``.
    """
    code_column = _validate_column(code_column, ALLOWED_PRODUCT_COLUMNS, "product column")
    value_column = _validate_column(value_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    _in_array(conditions, params, code_column, "codes", codes)
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    _flow(conditions, params, flow, sum_flows=sum_flows)
    _customs(conditions, params, customs)
    _market_nature(conditions, params, market)
    _reporter(conditions, params, reporter_column, reporter_value)
    _in_array(conditions, params, "reporter_iso_a3", "reporters", reporters)
    _in_array(conditions, params, "partner_iso_a3", "partners", partners)
    sql = f"""
        select
            {code_column}       as code,
            reference_year,
            {_value_sum(value_column, has_measure_kind)} as total_value,
            sum(qty_native)     as total_qty_native,
            sum(case when family = 'massa' then qty_base end)  as q_mass,
            sum(case when family = 'volume' then qty_base end) as q_vol,
            sum(case when family = 'contagem' then qty_base end) as q_count,
            any_value(family)   as family
        from `{table}`
        {_where(conditions)}
        group by {code_column}, reference_year
        order by {code_column}, reference_year
    """
    return sql, params


def source_metadata(table: str, *, source: str | None = None) -> tuple[str, list]:
    """Per-source provenance from ``gold_source_metadata`` (backs dataStore.meta)."""
    conditions: list[str] = []
    params: list = []
    if source is not None:
        conditions.append("source = @source")
        params.append(bigquery.ScalarQueryParameter("source", "STRING", source))
    sql = f"""
        select
            source,
            gold_table,
            cadence,
            year_start,
            year_end,
            total_rows,
            products_total,
            ufs_total,
            last_refresh
        from `{table}`
        {_where(conditions)}
        order by source
    """
    return sql, params


def cross_annual(
    table: str,
    *,
    measure_column: str,
    flow: str | None = None,
    code_column: str | None = None,
    codes: Sequence[str] = (),
    reporter_column: str | None = None,
    reporter_value: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    uf_codes: Sequence[str] = (),
) -> tuple[str, list]:
    """Annual single-measure series for the cross-source view (backs crossSeries points).

    Raw magnitude (the snapshot scales ÷1e9 / ÷1e6). ``codes`` optionally narrows to
    a commodity (per-source code) for market share. ``reporter_*`` pins a geo column
    (reporter_iso_a3 OR partner_iso_a3) to one country (Brazil) for the per-country
    COMTRADE metrics — exp/imp_value filter the reporter, partner_exp the partner;
    ``world_exp`` omits it to sum over every reporter. (``exp_price`` is derived
    UI-side as value ÷ weight, so it has no builder.)

    ``uf_codes`` optionally narrows to the origin UFs (``state_acronym``) — ONLY the
    COMEX mart carries it, so callers pass it solely for ``mdic_comex`` metrics
    (the per-UF cross-source scoping); COMTRADE callers leave it empty.
    """
    measure_column = _validate_column(measure_column, ALLOWED_VALUE_COLUMNS, "value_column")
    conditions: list[str] = []
    params: list = []
    _year_bounds(conditions, params, year_start, year_end)
    if code_column is not None:
        _in_array(conditions, params, code_column, "codes", codes)
    _flow(conditions, params, flow)
    _in_array(conditions, params, "state_acronym", "uf_codes", uf_codes)
    _reporter(conditions, params, reporter_column, reporter_value)
    sql = f"""
        select
            reference_year,
            sum({measure_column}) as value
        from `{table}`
        {_where(conditions)}
        group by reference_year
        order by reference_year
    """
    return sql, params


# ── Raw table inspection (the "Dados" perspective) ─────────────────────────────
# Researchers browse the actual rows of a banco's Gold table + serving marts to verify
# data line-by-line. The (banco, table) pair is allowlisted in the gateway; here every
# interpolated IDENTIFIER (order-by + filter columns) is validated against the TABLE'S
# OWN live schema — the column set IS the allowlist — and every filter VALUE stays a
# bound @param. limit/offset are int-coerced literals (BigQuery forbids a parameter in
# LIMIT/OFFSET), so they cannot carry injection.

# Cap a page so one read can never pull an unbounded payload (the cost guard in
# run_query is the BYTES backstop; this bounds the ROW/JSON size).
RAW_TABLE_MAX_LIMIT = 500

# Comparison operators a filter may use → the SQL operator. contains/is_null/not_null
# are handled separately (a LIKE pattern / no bound value).
_RAW_FILTER_OPS = {"eq": "=", "ne": "!=", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}


def _bq_param_type(bq_type: str) -> str:
    """Map a BigQuery column type to the bind-parameter type for a filter value."""
    t = (bq_type or "").upper()
    if t in ("INTEGER", "INT64"):
        return "INT64"
    if t in ("FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
        return "FLOAT64"
    if t in ("BOOLEAN", "BOOL"):
        return "BOOL"
    return "STRING"


def _coerce_filter_value(param_type: str, raw: object) -> object:
    """Coerce a filter value to the column's bind type. Raises ValueError (→ HTTP 400,
    never an uncaught 500) for a value that doesn't fit the column — a missing/None value,
    a non-numeric string on a numeric column, or a non-finite (inf/nan) float."""
    if raw is None:
        raise ValueError("Informe um valor para este operador de filtro.")
    try:
        if param_type == "INT64":
            return int(raw)
        if param_type == "FLOAT64":
            v = float(raw)
            if not math.isfinite(v):
                raise ValueError("non-finite")
            return v
    except (TypeError, ValueError):
        raise ValueError(
            f"O valor {raw!r} não é compatível com o tipo da coluna ({param_type})."
        ) from None
    if param_type == "BOOL":
        return str(raw).strip().lower() in ("true", "1", "yes", "sim")
    return str(raw)


def _raw_filter_predicate(
    conditions: list[str], params: list, f: dict, columns_types: dict, i: int
) -> None:
    """Append one parameterized filter predicate. ``f`` is ``{col, op, val}``; the column
    is validated against the table schema and the value is bound by the column type."""
    col = _validate_column(f["col"], frozenset(columns_types), "filter column")
    op = f.get("op", "eq")
    if op == "is_null":
        conditions.append(f"`{col}` is null")
        return
    if op == "not_null":
        conditions.append(f"`{col}` is not null")
        return
    pname = f"f{i}"
    if op == "contains":
        # Case-insensitive substring match on any column type — CONTAINS_SUBSTR takes the
        # search as a plain bound literal (no LIKE wildcards to escape / over-match). A
        # missing/None value is rejected with 400 (like the comparison ops), not silently
        # turned into the literal string "None" (which would match rows containing 'none').
        val = f.get("val")
        if val is None:
            raise ValueError("Informe um valor para este operador de filtro.")
        conditions.append(f"contains_substr(`{col}`, @{pname})")
        params.append(bigquery.ScalarQueryParameter(pname, "STRING", str(val)))
        return
    sqlop = _RAW_FILTER_OPS.get(op)
    if sqlop is None:
        raise ValueError(f"Operador de filtro {op!r} inválido.")
    ptype = _bq_param_type(columns_types[col])
    # A STRING-typed bind compares against CAST(col AS STRING) so a DATE/TIMESTAMP column
    # (which binds as STRING) does not raise a BigQuery type mismatch; numeric/bool direct.
    lhs = f"cast(`{col}` as string)" if ptype == "STRING" else f"`{col}`"
    conditions.append(f"{lhs} {sqlop} @{pname}")
    params.append(
        bigquery.ScalarQueryParameter(pname, ptype, _coerce_filter_value(ptype, f.get("val")))
    )


def raw_table_rows(
    table: str,
    *,
    columns_types: dict,
    limit: int,
    offset: int = 0,
    order_by: str | None = None,
    order_dir: str = "asc",
    filters: Sequence[dict] = (),
    visibility_predicate: str = "",
) -> tuple[str, list]:
    """``SELECT *`` over one allowlisted table, optionally ordered + filtered, paginated.

    Used when an ORDER BY / filter is requested OR (for a Gold fact) when the F7 visibility
    gate must apply — a plain ungated browse goes through the FREE ``tabledata.list`` path
    (gateway.fetch_table_rows). ``columns_types`` is the table's live schema ``{name: bq_type}``;
    order-by + filter columns are validated against it (the schema IS the allowlist) and filter
    values stay bound. ``visibility_predicate`` is the F7 gate (a NOT EXISTS over
    dim_produto_visibility built by visibility_clause from fixed maps — injection-safe); when
    given it is ANDed in so a commodity marked indisponível never appears in the raw browse."""
    conditions: list[str] = []
    params: list = []
    for i, f in enumerate(filters):
        _raw_filter_predicate(conditions, params, f, columns_types, i)
    if visibility_predicate:
        conditions.append(visibility_predicate)
    order_clause = ""
    if order_by:
        col = _validate_column(order_by, frozenset(columns_types), "order_by column")
        direction = "desc" if str(order_dir).lower() == "desc" else "asc"
        order_clause = f"order by `{col}` {direction}"
    elif conditions:
        # This filtered/gated path runs one BigQuery job PER PAGE, and BigQuery guarantees
        # NO result ordering without ORDER BY — so a bare LIMIT/OFFSET can duplicate/skip
        # rows across pages (a researcher filtering + paging would see the same row twice
        # and miss others). When the caller requests no explicit sort, order by every column
        # (schema order) as a deterministic tiebreak so offset pagination is stable. The
        # column names come from the live schema (the allowlist), never request-derived. (A
        # truly unfiltered/ungated browse never reaches here — it uses the free tabledata.list
        # storage-ordered path — so this only stabilises the query path that needs it.)
        tiebreak = ", ".join(f"`{c}`" for c in columns_types)
        order_clause = f"order by {tiebreak}" if tiebreak else ""
    lim = max(1, min(int(limit), RAW_TABLE_MAX_LIMIT))
    off = max(0, int(offset))
    sql = f"""
        select * from `{table}`
        {_where(conditions)}
        {order_clause}
        limit {lim} offset {off}
    """
    return sql, params


def raw_table_count(
    table: str,
    *,
    columns_types: dict,
    filters: Sequence[dict] = (),
    visibility_predicate: str = "",
) -> tuple[str, list]:
    """``COUNT(*)`` under the same filters (the pagination total). Unfiltered + ungated counts
    use the table's cached ``num_rows`` (free) instead — see gateway.fetch_table_count. A Gold
    fact passes ``visibility_predicate`` (the F7 gate) so the denominator matches the gated page
    (a hidden commodity is excluded from both)."""
    conditions: list[str] = []
    params: list = []
    for i, f in enumerate(filters):
        _raw_filter_predicate(conditions, params, f, columns_types, i)
    if visibility_predicate:
        conditions.append(visibility_predicate)
    sql = f"select count(*) as n from `{table}` {_where(conditions)}"
    return sql, params


# banco token → (Gold fact table, the column holding that source's EXACT product code).
# Lives here, in the flask-free module, because TWO callers need it and they must agree on
# what "this commodity still has Gold data" means: gateway.fetch_orphan_produtos (the
# researcher-facing Descontinuados worklist, flask-caching memoized) and
# doctor._check_orphan_lifecycle (runs inside a bare `embrapa doctor`, so it cannot import
# gateway). Duplicating the map would let the operator's health check and the UI disagree
# about which produtos are orphans.
#
# NOTE the granularity differs per banco and MUST match the catalog's registration
# granularity for the exact-match join to mean anything: comex is 8-digit NCM, comtrade
# 6-digit HS, the IBGE bancos their SIDRA codes.
GOLD_CODE_SOURCES: dict[str, tuple[str, str]] = {
    "pevs": ("gold_pevs_production", "product_code"),
    "comex": ("gold_comex_flows", "ncm_code"),
    "comtrade": ("gold_comtrade_flows", "cmd_code"),
    "pam": ("gold_pam_production", "product_code"),
    "ppm": ("gold_ppm_production", "product_code"),
}
