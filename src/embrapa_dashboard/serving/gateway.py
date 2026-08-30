"""Cached, parameterized reads against the BigQuery serving marts.

Each public ``fetch_*`` function is the read half of one chart family: it builds
a parameterized query (``serving.sql``), runs it on BigQuery, and returns a small
Pandas DataFrame. The functions are decorated with ``@cache.memoize()`` so a
repeated (filters) combination is answered from cache instead of re-querying
BigQuery — the round-trip the stateless dashboard would otherwise pay on every
identical callback.

Caching policy (designed so the dashboard scales to N Cloud Run instances
WITHOUT a shared Redis — see ``serving.cache``):
  * Mart reads (``fetch_production_*``, ``fetch_comex_seasonality``) use the
    default TTL — the marts change solely on the nightly dbt rebuild, so every
    instance independently converges to the same data within the TTL.
  * ``fetch_current_code_industrialization`` uses a SHORT TTL
    (``CACHE_CLASSIFICATION_TIMEOUT``, default 30s) AND is explicitly invalidated
    by the curation writer. The invalidation makes a curation edit instant on the
    writing instance; the short TTL bounds cross-instance staleness to that window
    (eventual consistency) — which is what lets multiple instances run on
    per-process SimpleCache for free.

There is no global lock and no in-memory Gold DataFrame: state lives in BigQuery,
results are cached, and the process stays stateless and horizontally scalable.

Return-value contract (TRI-STATE — callers must handle all three):
  * most readers return a DataFrame (possibly empty) for a known source/filter;
  * the per-source quality readers (``fetch_quality_timeseries`` /
    ``fetch_quality_by_product``) return ``None`` for an UNKNOWN/unsupported source
    (not in ``_GOLD_TABLE`` / ``_GOLD_PRODUCT``) — a deliberate "this source has no
    such reader", distinct from "the query ran and was empty";
  * the curation reads (``fetch_current_*`` / ``fetch_attribute_editors`` /
    ``fetch_banco_metadata``) RAISE ``NotFound`` when the backing table does not
    exist yet, which the seam catches and treats as "nothing configured".
The webapi serializers normalize ``None`` and an empty DataFrame identically (see
``serializers._empty``), so a ``None`` from the quality readers is safe; the
distinction is preserved (rather than flattened to an empty frame) to keep the
"unknown source" signal explicit for any non-serializer caller.
"""

from __future__ import annotations

import functools
from collections.abc import Sequence

from google.api_core.exceptions import BadRequest, NotFound
from google.cloud import bigquery

from embrapa_dashboard.config import get_credentials, get_settings
from embrapa_dashboard.serving import sql as sqlbuild
from embrapa_dashboard.serving.cache import cache

# Fallback short TTL for the curation-classification read, used only until
# init_cache() binds the authoritative value from config.Settings. On
# multi-instance Cloud Run, per-process SimpleCache can't be invalidated across
# instances, so this TTL (not Redis) bounds cross-instance staleness.
#
# @cache.memoize fixes a *default* timeout at decoration time (before Settings
# exists), but flask-caching exposes a writable ``cache_timeout`` attribute on the
# decorated function that it re-reads on every call. init_cache() — which has
# Settings — sets that attribute to cfg.cache_classification_timeout, making the
# config field authoritative (no os.environ drift). See cache.init_cache and
# config.Settings.cache_classification_timeout.
DEFAULT_CLASSIFICATION_TTL = 30


@functools.lru_cache(maxsize=1)
def _client() -> bigquery.Client:
    """Lazily build one BigQuery client per process (reused across queries)."""
    settings = get_settings()
    return bigquery.Client(
        project=settings.gcp_project_id,
        location=settings.bq_location,
        credentials=get_credentials(settings),
    )


def run_query(sql: str, params: list, *, max_bytes: int | None = None) -> object:
    """Execute a parameterized query and return the result as a DataFrame.

    Applies a ``maximum_bytes_billed`` ceiling (``Settings.bq_max_bytes_billed``)
    so the /api serving path can't run an unbounded scan — a pathological filter
    or a cold Bronze read is FAILED by BigQuery (visibly) rather than silently
    billing a runaway query. ``None``/0 disables the cap. ``max_bytes`` is a per-call
    ceiling — used by the raw-table inspection path, whose ``SELECT *`` sort/filter
    scans are bounded well below the global default. The EFFECTIVE cap is the TIGHTER
    of ``max_bytes`` and the global ``Settings.bq_max_bytes_billed``, so an operator
    who sets a stricter global cost ceiling is honoured even on the per-call paths
    (0/None on either side means "unset" for that side).
    """
    cfg = get_settings()
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    caps = [c for c in (max_bytes, cfg.bq_max_bytes_billed) if c]
    cap = min(caps) if caps else None
    if cap:
        job_config.maximum_bytes_billed = cap
    job = _client().query(sql, job_config=job_config)
    return job.result().to_dataframe(create_bqstorage_client=False)


# (mart, product-code column, product-name column, default value column) per
# source. Drives the uniform products / productTS readers — one entry point each
# instead of three near-identical functions, since the three annual marts now
# share the same product/quantity columns.
_PRODUCT_SOURCES = {
    "ibge_pevs": (
        "serving_pevs_annual",
        "product_code",
        "product_description",
        "val_real_ipca_brl",
    ),
    "ibge_pam": (
        "serving_pam_annual",
        "product_code",
        "product_description",
        "val_real_ipca_brl",
    ),
    "ibge_ppm": (
        "serving_ppm_annual",
        "product_code",
        "product_description",
        "val_real_ipca_brl",
    ),
    "mdic_comex": ("serving_comex_annual", "ncm_code", "ncm_description", "val_yearfx_usd"),
    "un_comtrade": ("serving_comtrade_annual", "cmd_code", "cmd_description", "val_yearfx_usd"),
}


def _product_source(source: str) -> tuple[str, str, str, str]:
    try:
        return _PRODUCT_SOURCES[source]
    except KeyError:
        raise ValueError(
            f"unknown source {source!r}; choose one of {sorted(_PRODUCT_SOURCES)}"
        ) from None


# Sources whose mart carries the stock|flow ``measure_kind`` discriminator (only the
# livestock survey today). fetch_products surfaces it so the UI can split the herd
# (stock) from animal-product flows (eggs/milk) that share the ``contagem`` family.
# The production readers also pass ``has_measure_kind=source in _MEASURE_KIND_SOURCES``
# to the SQL builders so a VALUE aggregation is FLOW-only (herd stock has no value).
# CACHE NOTE: this treatment is SOURCE-DERIVED, and ``source`` is already a
# @cache.memoize argument on every reader, so it is part of the cache key — no
# collision is possible. If ``measure_kind`` ever becomes a USER-controllable filter
# (e.g. "flow only"), it MUST be added as an explicit reader parameter so it joins
# the memoize key, following the ``flow``/``customs``/``market`` precedent — a
# request differing only by an un-keyed filter would otherwise serve a stale result.
_MEASURE_KIND_SOURCES = {"ibge_ppm"}

# Fontes cujo mart carrega o id da TABELA SIDRA — os bancos multi-tabela. `fetch_products`
# o expõe porque a identidade de um produto é (banco, tabela, código) e duas tabelas de um
# mesmo banco podem trazer o MESMO nome (madeira/lenha/carvão no PEVS): sem o id, a tela
# não tem como distinguir duas entradas idênticas. Mesma nota de cache do conjunto acima —
# o tratamento é DERIVADO de `source`, que já entra na chave de memoize de todo leitor.
_SIDRA_TABELA_SOURCES = {"ibge_pevs", "ibge_ppm"}


# Production sources whose marts are COLUMN-IDENTICAL (PEVS shape: product_code,
# state_acronym, family, qty_native, val_*). fetch_production_* are generic over
# them — PAM rides them with no per-source SQL because serving_pam_annual matches
# serving_pevs_annual's schema. Trade marts are NOT here (different shape).
_PRODUCTION_MART = {
    "ibge_pevs": "serving_pevs_annual",
    "ibge_pam": "serving_pam_annual",
    "ibge_ppm": "serving_ppm_annual",
}


def _production_mart(source: str) -> str:
    try:
        return _PRODUCTION_MART[source]
    except KeyError:
        raise ValueError(
            f"unknown production source {source!r}; choose one of {sorted(_PRODUCTION_MART)}"
        ) from None


@cache.memoize()
def fetch_production_overview(
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    source: str = "ibge_pevs",
    uf_codes: Sequence[str] = (),
    sidra_tabela: str | None = None,
):
    """Annual production total for a PEVS-shaped source (backs overviewTS).

    ``uf_codes`` optionally narrows to the producing UFs (cross-source per-UF scoping).
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", _production_mart(source))
    sql, params = sqlbuild.production_overview(
        table,
        year_start=year_start,
        year_end=year_end,
        product_codes=tuple(product_codes),
        value_column=value_column,
        uf_codes=tuple(uf_codes),
        has_measure_kind=source in _MEASURE_KIND_SOURCES,
        sidra_tabela=sidra_tabela,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_production_by_uf(
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    source: str = "ibge_pevs",
    latest_year_only: bool = True,
    sidra_tabela: str | None = None,
):
    """Production aggregated by UF for a PEVS-shaped source (backs ufData).

    ``latest_year_only`` (default True) pins the choropleth to the latest year in
    the active window; the export-coefficient by-UF reader passes False for the
    window-cumulative sum it needs. ``uf_codes`` narrows to the selected states.
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", _production_mart(source))
    sql, params = sqlbuild.production_by_uf(
        table,
        year_start=year_start,
        year_end=year_end,
        product_codes=tuple(product_codes),
        uf_codes=tuple(uf_codes),
        value_column=value_column,
        latest_year_only=latest_year_only,
        has_measure_kind=source in _MEASURE_KIND_SOURCES,
        sidra_tabela=sidra_tabela,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_production_by_uf_yearly(
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    source: str = "ibge_pevs",
    sidra_tabela: str | None = None,
):
    """Production by (UF, year) for a PEVS-shaped source (backs the ano × UF heatmap)."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", _production_mart(source))
    sql, params = sqlbuild.production_by_uf_yearly(
        table,
        year_start=year_start,
        year_end=year_end,
        product_codes=tuple(product_codes),
        value_column=value_column,
        has_measure_kind=source in _MEASURE_KIND_SOURCES,
        sidra_tabela=sidra_tabela,
    )
    return run_query(sql, params)


# PEVS-shaped sources whose Gold is município-grained (carry city_code + family +
# qty_base). COMEX (UF origin only) and COMTRADE (international) have no município
# grain, so the município geo cube does not apply to them.
_MUNICIPIO_SOURCES = frozenset({"ibge_pevs", "ibge_pam", "ibge_ppm"})


@cache.memoize()
def fetch_production_by_municipio_yearly(
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    city_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    source: str = "ibge_pevs",
    sidra_tabela: str | None = None,
):
    """Production by (município, year) for a PEVS-shaped source, straight from
    gold_<source>_production (already município-grained) — backs the sub-UF +
    live-município geography cascade. Reads Gold directly (basket + ``city_codes``
    scoped + the run_query maximum_bytes_billed guard) since município is the finest,
    on-demand grain and a mart would near-duplicate Gold. ``city_codes`` is what keeps
    a narrowed selection cheap (the client passes only the selected municípios' codes).
    ``None`` for a source with no município grain (COMEX/COMTRADE), or when no
    ``city_codes`` scope is given — the cube is always city-scoped, so an empty set
    means "nothing to fetch" rather than a full ~146k-row município grid scan."""
    if source not in _MUNICIPIO_SOURCES or not city_codes:
        return None
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_gold_dataset", _GOLD_TABLE[source])
    sql, params = sqlbuild.production_by_municipio_yearly(
        table,
        year_start=year_start,
        year_end=year_end,
        product_codes=tuple(product_codes),
        city_codes=tuple(city_codes),
        value_column=value_column,
        # F7 gate: exclude commodities marked indisponível (no-op while none are).
        visibility_predicate=sqlbuild.visibility_clause(
            settings, _SHORT_SOURCE[source], _GOLD_PRODUCT[source][0]
        ),
        sidra_tabela=sidra_tabela,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_products_by_municipio(
    year_start: int | None = None,
    year_end: int | None = None,
    product_codes: Sequence[str] = (),
    city_codes: Sequence[str] = (),
    value_column: str = "val_real_ipca_brl",
    source: str = "ibge_pevs",
    sidra_tabela: str | None = None,
    include_sidra_tabela: bool = False,
):
    """Per-product ranking WITHIN the given municípios — "o que este lugar produz".

    The território profile needs this because the município cube
    (:func:`fetch_production_by_municipio_yearly`) sums products away: it can draw a
    city's trajectory but cannot name what is behind it. Same Gold-direct read and the
    same ``city_codes`` cost control for the same reason (finest grain, no mart).

    ``None`` for a source with no município grain (COMEX is UF-only, COMTRADE has no
    national geography) or when no city scope is given — never a full grid scan."""
    if source not in _MUNICIPIO_SOURCES or not city_codes:
        return None
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_gold_dataset", _GOLD_TABLE[source])
    code_column, name_column = _GOLD_PRODUCT[source]
    sql, params = sqlbuild.products_by_municipio(
        table,
        code_column=code_column,
        name_column=name_column,
        year_start=year_start,
        year_end=year_end,
        sidra_tabela=sidra_tabela,
        include_sidra_tabela=include_sidra_tabela,
        product_codes=tuple(product_codes),
        city_codes=tuple(city_codes),
        value_column=value_column,
        # F7 gate: exclude commodities marked indisponível (no-op while none are).
        visibility_predicate=sqlbuild.visibility_clause(
            settings, _SHORT_SOURCE[source], code_column
        ),
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_geo_municipio_mesh():
    """The full IBGE municipal mesh (``dim_geo_municipio``): every município → its UF
    + grande região + BOTH sub-UF divisions (classic meso/micro, 2017
    intermediária/imediata). Static (~5570 rows); served once and memoized so the
    SPA's geo cascade builds its per-level option lists + the city→ancestry map from
    a single cached read."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_gold_dataset", "dim_geo_municipio")
    sql, params = sqlbuild.geo_municipio_mesh(table)
    return run_query(sql, params)


@cache.memoize()
def fetch_productivity(
    product_code: str,
    source: str = "ibge_pam",
    year_start: int | None = None,
    year_end: int | None = None,
    uf_codes: Sequence[str] = (),
):
    """Production + harvested/planted area by (year, UF) for one crop, from a
    PAM-shaped mart (backs ViewProductivity). Yield is recomputed downstream.
    ``year_start``/``year_end`` scope the window to the view's active period filter."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", _production_mart(source))
    sql, params = sqlbuild.productivity(
        table,
        product_code=product_code,
        year_start=year_start,
        year_end=year_end,
        uf_codes=tuple(uf_codes),
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_comex_seasonality(
    year_start: int | None = None,
    year_end: int | None = None,
    ncm_codes: Sequence[str] = (),
    flow: str | None = None,
    uf_codes: Sequence[str] = (),
):
    """Monthly COMEX value for the seasonality view (backs monthlyData).

    ``uf_codes`` optionally narrows to the origin UFs (the mart now keeps
    ``state_acronym`` in its grain — P6 per-UF scoping)."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comex_seasonality")
    sql, params = sqlbuild.comex_seasonality(
        table,
        year_start=year_start,
        year_end=year_end,
        ncm_codes=tuple(ncm_codes),
        flow=flow,
        uf_codes=tuple(uf_codes),
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_comex_months_per_year():
    """Distinct months present per year from the COMEX seasonality mart (backs the
    partial-latest-year signal in source-meta). Cheap year×month aggregate, cached."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comex_seasonality")
    sql, params = sqlbuild.months_present_per_year(table)
    return run_query(sql, params)


@cache.memoize()
def fetch_comtrade_reporters_per_year():
    """Distinct exporting reporters present per year in the COMTRADE annual mart (backs
    the world-panel completeness clamp for market share — reporters file with a ~1-2y
    lag, so the most recent world years are under-reported). Cheap aggregate, cached."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comtrade_annual")
    sql, params = sqlbuild.reporters_present_per_year(table)
    return run_query(sql, params)


@cache.memoize()
def fetch_comex_overview(
    year_start: int | None = None,
    year_end: int | None = None,
    ncm_codes: Sequence[str] = (),
    flow: str | None = None,
    value_column: str = "val_yearfx_usd",
):
    """Annual COMEX value + weight (backs overviewTS for COMEX).

    ``value_column`` picks the currency×correction measure (the seam resolves it
    from the active conventions; default USD). The mart carries the full BRL/USD/EUR
    matrix, so a BRL/EUR display serves the REAL column.
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comex_annual")
    sql, params = sqlbuild.trade_overview(
        table,
        code_column="ncm_code",
        year_start=year_start,
        year_end=year_end,
        codes=tuple(ncm_codes),
        flow=flow,
        value_column=value_column,
    )
    return run_query(sql, params)


# ── COMTRADE reporter-pin resolution ─────────────────────────────────────────
# Sentinel for the COMTRADE readers' ``pin_reporter`` arg: "caller didn't specify → use the
# Brazil default". A STRING (not object()) so it serializes cleanly into flask-caching's
# memoize key; real reporter values are ISO-A3 codes, so there is no collision. Every legacy
# caller (cross-source metrics, tests) omits ``pin_reporter`` and keeps the byte-identical
# Brazil pin; only the seam passes an explicit value (None = world / list, or a specific ISO).
_REPORTER_PIN_DEFAULT = "__brazil_default__"


def _resolve_reporter_pin(
    settings, pin_reporter: str | None, reporters: Sequence[str]
) -> str | None:
    """Scalar reporter pin for a COMTRADE reader — mutually exclusive with the ``reporters``
    IN-list:

    - ``reporters`` non-empty → ``None`` (the IN-list governs; no scalar pin).
    - ``pin_reporter`` is the sentinel (caller omitted it) → the Brazil default.
    - otherwise → ``pin_reporter`` verbatim (``None`` = world / no pin, or a specific ISO).
    """
    if reporters:
        return None
    if pin_reporter == _REPORTER_PIN_DEFAULT:
        return settings.comtrade_brazil_iso
    return pin_reporter


@cache.memoize()
def fetch_comtrade_overview(
    year_start: int | None = None,
    year_end: int | None = None,
    cmd_codes: Sequence[str] = (),
    flow: str | None = None,
    customs: str | None = None,
    market: str | None = None,
    value_column: str = "val_yearfx_usd",
    reporters: Sequence[str] = (),
    partners: Sequence[str] = (),
    pin_reporter: str | None = _REPORTER_PIN_DEFAULT,
):
    """Annual COMTRADE value + weight (backs overviewTS for COMTRADE).

    ``value_column`` picks the currency×correction measure (default USD); the mart
    carries the full BRL/USD/EUR matrix so BRL/EUR serves the REAL column. ``customs``
    optionally narrows to one customs procedure (regime aduaneiro); None sums every
    regime (the total).

    ``reporters``/``partners`` are the country multi-selects (ISO-A3), each narrowing via
    ``<col> IN UNNEST(...)``. ``pin_reporter`` resolves the single-country reporter pin when
    ``reporters`` is empty — the sentinel default keeps the Brazil pin (unchanged); the seam
    passes ``None`` for a world/list selection (see :func:`_resolve_reporter_pin`).
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comtrade_annual")
    sql, params = sqlbuild.trade_overview(
        table,
        code_column="cmd_code",
        year_start=year_start,
        year_end=year_end,
        codes=tuple(cmd_codes),
        flow=flow,
        customs=customs,
        market=market,
        value_column=value_column,
        reporter_column="reporter_iso_a3",
        reporter_value=_resolve_reporter_pin(settings, pin_reporter, reporters),
        reporters=tuple(reporters),
        partners=tuple(partners),
        # "All flows" sums only the primary totals (export/import): re-export/re-import are
        # subsets (X ⊇ RX, M ⊇ RM), so adding them would double-count.
        sum_flows=sqlbuild.COMTRADE_TOTAL_FLOWS,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_comex_by_uf(
    year_start: int | None = None,
    year_end: int | None = None,
    ncm_codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
    flow: str | None = None,
    value_column: str = "val_yearfx_usd",
    latest_year_only: bool = True,
):
    """COMEX value + weight aggregated by UF (backs ufData for COMEX).

    ``value_column`` picks the currency×correction measure (default USD; the mart
    carries the full BRL/USD/EUR matrix). ``total_weight_kg`` (raw kg) is always
    present for export_coefficient regardless of which value column is summed.
    ``latest_year_only`` (default True) pins the choropleth to the latest year in
    the active window; the export-coefficient by-UF reader passes False for the
    window-cumulative sum it needs. ``uf_codes`` narrows to the selected origin UFs.
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comex_annual")
    sql, params = sqlbuild.comex_by_uf(
        table,
        year_start=year_start,
        year_end=year_end,
        ncm_codes=tuple(ncm_codes),
        uf_codes=tuple(uf_codes),
        flow=flow,
        value_column=value_column,
        latest_year_only=latest_year_only,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_comex_by_uf_yearly(
    year_start: int | None = None,
    year_end: int | None = None,
    ncm_codes: Sequence[str] = (),
    flow: str | None = None,
    value_column: str = "val_yearfx_usd",
):
    """COMEX value by (UF, year) (backs the ano × UF heatmap for COMEX).

    ``value_column`` picks the currency×correction measure (default USD; the mart
    carries the full BRL/USD/EUR matrix).
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comex_annual")
    sql, params = sqlbuild.comex_by_uf_yearly(
        table,
        year_start=year_start,
        year_end=year_end,
        ncm_codes=tuple(ncm_codes),
        flow=flow,
        value_column=value_column,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_comex_partners(
    year_start: int | None = None,
    year_end: int | None = None,
    ncm_codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
    flow: str | None = None,
    rank_by: str = "value",
):
    """COMEX partner (country) ranking with export/import split (backs partnerData).

    ``uf_codes`` optionally narrows to the origin UFs (``state_acronym``); empty =
    no UF filter. COMTRADE has no origin-UF column, so its partner reader omits it.
    ``flow`` narrows the ranking to one direction (export/import); ``None`` sums both
    (COMEX has no overlapping sub-flow, so no ``sum_flows`` guard is needed). ``rank_by``
    ∈ {value, weight, price} picks the server-side ORDER BY dimension.
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comex_annual")
    sql, params = sqlbuild.trade_by_partner(
        table,
        partner_code_column="country_code",
        partner_name_column="country_name",
        code_column="ncm_code",
        year_start=year_start,
        year_end=year_end,
        codes=tuple(ncm_codes),
        uf_codes=tuple(uf_codes),
        flow=flow,
        rank_by=rank_by,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_comtrade_partners(
    year_start: int | None = None,
    year_end: int | None = None,
    cmd_codes: Sequence[str] = (),
    flow: str | None = None,
    customs: str | None = None,
    market: str | None = None,
    rank_by: str = "value",
    reporters: Sequence[str] = (),
    partners: Sequence[str] = (),
    pin_reporter: str | None = _REPORTER_PIN_DEFAULT,
):
    """COMTRADE partner ranking with export/import split (backs partnerData).

    ``flow`` narrows the ranking to one direction; ``None`` sums only the primary
    totals (``COMTRADE_TOTAL_FLOWS``) so the ranking metrics never double-count the
    re-export/re-import subsets. ``customs`` (regime aduaneiro) / ``market`` (tipo de
    mercado) narrow to one procedure / purpose (None = every one). ``rank_by`` ∈
    {value, weight, price} picks the server-side ORDER BY dimension. ``reporters``/
    ``partners`` (ISO-A3) narrow the ranking by country; ``pin_reporter`` keeps the
    Brazil pin by default (see :func:`_resolve_reporter_pin`).
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comtrade_annual")
    sql, params = sqlbuild.trade_by_partner(
        table,
        partner_code_column="partner_code",
        partner_name_column="partner_name",
        code_column="cmd_code",
        year_start=year_start,
        year_end=year_end,
        codes=tuple(cmd_codes),
        flow=flow,
        sum_flows=sqlbuild.COMTRADE_TOTAL_FLOWS,
        customs=customs,
        market=market,
        reporter_column="reporter_iso_a3",
        reporter_value=_resolve_reporter_pin(settings, pin_reporter, reporters),
        reporters=tuple(reporters),
        partners=tuple(partners),
        rank_by=rank_by,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_products_by_uf(
    *,
    table_key: str,
    code_column: str,
    name_column: str,
    year_start: int | None = None,
    year_end: int | None = None,
    codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
    value_column: str = "val_yearfx_usd",
    flow: str | None = None,
    sidra_tabela: str | None = None,
    include_sidra_tabela: bool = False,
):
    """Per-product ranking within a UF selection (backs the 'Base de dados' per-UF
    product breakdown). ``table_key`` + columns are internal literals the seam picks
    per banco (PEVS production / COMEX export); the SQL builder validates each
    interpolated identifier against its allowlist."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", table_key)
    sql, params = sqlbuild.products_by_uf(
        table,
        code_column=code_column,
        name_column=name_column,
        year_start=year_start,
        year_end=year_end,
        codes=tuple(codes),
        uf_codes=tuple(uf_codes),
        value_column=value_column,
        flow=flow,
        sidra_tabela=sidra_tabela,
        include_sidra_tabela=include_sidra_tabela,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_comex_flows(
    year_start: int | None = None,
    year_end: int | None = None,
    ncm_codes: Sequence[str] = (),
    flow: str | None = None,
    uf_codes: Sequence[str] = (),
):
    """COMEX origin(UF)->destination(country) links (backs flowData for COMEX).

    ``uf_codes`` optionally narrows the Sankey to those origin UFs
    (``state_acronym``); empty = no UF filter.
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comex_annual")
    sql, params = sqlbuild.trade_flows(
        table,
        origin_code_column="state_acronym",
        origin_name_column="state_name",
        dest_code_column="country_code",
        dest_name_column="country_name",
        code_column="ncm_code",
        year_start=year_start,
        year_end=year_end,
        codes=tuple(ncm_codes),
        flow=flow,
        uf_codes=tuple(uf_codes),
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_comtrade_flows(
    year_start: int | None = None,
    year_end: int | None = None,
    cmd_codes: Sequence[str] = (),
    flow: str | None = None,
    customs: str | None = None,
    market: str | None = None,
    reporters: Sequence[str] = (),
    partners: Sequence[str] = (),
    pin_reporter: str | None = _REPORTER_PIN_DEFAULT,
):
    """COMTRADE reporter->partner links (backs flowData for COMTRADE).

    ``flow`` narrows the Sankey to one direction; ``None`` sums only export/import
    (re-export/re-import are subsets → no double-count). ``customs`` (regime aduaneiro)
    / ``market`` (tipo de mercado) narrow to one procedure / purpose (None = every one).
    ``reporters``/``partners`` (ISO-A3) narrow the Sankey by country; ``pin_reporter``
    keeps Brazil's own links by default (see :func:`_resolve_reporter_pin`).
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comtrade_annual")
    sql, params = sqlbuild.trade_flows(
        table,
        origin_code_column="reporter_code",
        origin_name_column="reporter_name",
        dest_code_column="partner_code",
        dest_name_column="partner_name",
        code_column="cmd_code",
        year_start=year_start,
        year_end=year_end,
        codes=tuple(cmd_codes),
        flow=flow,
        # "All flows" sums only export/import (re-export/re-import are subsets → no double-count).
        sum_flows=sqlbuild.COMTRADE_TOTAL_FLOWS,
        customs=customs,
        market=market,
        reporter_column="reporter_iso_a3",
        reporter_value=_resolve_reporter_pin(settings, pin_reporter, reporters),
        reporters=tuple(reporters),
        partners=tuple(partners),
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_comtrade_countries():
    """Distinct reporter + partner countries in the COMTRADE mart (backs the country
    pickers). Memoized → one DISTINCT scan per process; the seam splits the rows by
    ``role`` into the two universes."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comtrade_annual")
    sql, params = sqlbuild.comtrade_countries(table)
    return run_query(sql, params)


@cache.memoize()
def fetch_quality_by_source(source: str | None = None):
    """data_quality_flag breakdown per source (backs the quality donut)."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_quality_by_source")
    sql, params = sqlbuild.quality_by_source(table, source=source)
    return run_query(sql, params)


# Source → its comprehensive Gold table (the year-grained quality scan reads here,
# since the serving marts aren't year×flag). Matches gold_source_metadata.gold_table.
_GOLD_TABLE = {
    "ibge_pevs": "gold_pevs_production",
    "ibge_pam": "gold_pam_production",
    "ibge_ppm": "gold_ppm_production",
    "mdic_comex": "gold_comex_flows",
    "un_comtrade": "gold_comtrade_flows",
}

# Banco id (long) → the short source token the catalog / dim_produto_visibility use.
# Threads the F7 visibility gate into the direct-Gold readers (which bypass the marts).
_SHORT_SOURCE = {
    "ibge_pevs": "pevs",
    "ibge_pam": "pam",
    "ibge_ppm": "ppm",
    "mdic_comex": "comex",
    "un_comtrade": "comtrade",
}


@cache.memoize()
def fetch_quality_timeseries(source: str):
    """data_quality_flag counts per year for a source (backs quality-over-time).

    Returns ``None`` for an unknown/unsupported source (the deliberate tri-state
    documented in the module docstring); the serializers treat that as empty.
    """
    table_name = _GOLD_TABLE.get(source)
    if table_name is None:
        return None
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_gold_dataset", table_name)
    vis = sqlbuild.visibility_clause(settings, _SHORT_SOURCE[source], _GOLD_PRODUCT[source][0])
    sql, params = sqlbuild.quality_timeseries(table, visibility_predicate=vis)
    return run_query(sql, params, max_bytes=RAW_TABLE_MAX_BYTES)


# Source → its Gold product (code, name) columns.
_GOLD_PRODUCT = {
    "ibge_pevs": ("product_code", "product_description"),
    "ibge_pam": ("product_code", "product_description"),
    "ibge_ppm": ("product_code", "product_description"),
    "mdic_comex": ("ncm_code", "ncm_description"),
    "un_comtrade": ("cmd_code", "cmd_description"),
}


@cache.memoize()
def fetch_market_nature_series(codes: tuple = ()):
    """COMTRADE trade value (US$) by (economic-purpose market_nature × year), summed from
    the serving mart's ``market_nature`` column (rows with no market nature are excluded).
    Backs the "Finalidade econômica" analysis. ``codes`` optionally narrows to one
    commodity's HS codes. The mart column is edit-driven (LEFT JOIN dim_flow_market_scd2,
    materialized at build time) → the default mart TTL; it reflects a matrix edit after the
    next dbt build (the editor's live reads use fetch_current_flow_market's short TTL)."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comtrade_annual")
    sql, params = sqlbuild.market_nature_series(table, codes=codes)
    return run_query(sql, params)


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_current_flow_market():
    """Current (customs_code, flow_code) → market from ``dim_flow_market_scd2`` (the
    live SCD2 view over the flow-market log). Short classification TTL (mirrors
    ``fetch_current_code_industrialization``) so a fresh matrix edit is visible to the
    editor within the window. Raises NotFound when the view doesn't exist yet (curation
    not enabled / nothing classified) — the seam treats it as an empty mapping."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "dim_flow_market_scd2")
    sql, params = sqlbuild.current_flow_market(table)
    return run_query(sql, params)


@cache.memoize()
def fetch_flow_market_values():
    """Total traded value (US$) per (customs_code, flow) from serving_comtrade_annual —
    the materiality signal in each matrix cell. Pre-aggregated mart → the default TTL."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "serving_comtrade_annual")
    sql, params = sqlbuild.flow_market_values(table)
    return run_query(sql, params)


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_attribute_editors():
    """Distinct attribute-editor emails from the allowlist (research_inputs.<attribute_editors>).

    Short TTL (like the classification reads) so a Console add/remove takes effect
    within the window. Raises NotFound when the table doesn't exist — the seam
    treats that as 'no allowlist configured'. Bounded by maximum_bytes_billed.
    """
    settings = get_settings()
    table = sqlbuild.table_ref(
        settings, "bq_research_inputs_dataset", settings.bq_attribute_editors_table
    )
    sql = f"select distinct lower(trim(email)) as email from `{table}` where email is not null"
    return run_query(sql, [])


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_banco_metadata(banco_id: str):
    """Operator-editable maturity/coverage overrides for one banco
    (research_inputs.<banco_metadata>). Short TTL (like the attribute editors read) so a
    Console flip — e.g. beta→estavel — takes effect within the window. Raises
    NotFound when the table doesn't exist — the seam treats that as 'no overrides'
    and uses the registry defaults. Bounded by maximum_bytes_billed."""
    settings = get_settings()
    table = sqlbuild.table_ref(
        settings, "bq_research_inputs_dataset", settings.bq_banco_metadata_table
    )
    sql = (
        "select maturity, maturity_note, maturity_date, cobertura_years, "
        "cobertura_atualizacao, cobertura_granularidade "
        f"from `{table}` where banco_id = @banco_id limit 1"
    )
    params = [bigquery.ScalarQueryParameter("banco_id", "STRING", banco_id)]
    return run_query(sql, params)


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_agrupamentos():
    """The CURRENT active commodity GROUPS (agrupamentos) — the first-class registry
    (latest row per group_id, active=true) with a live count of each group's active
    catalog members (so the UI can block deleting a non-empty group). EMPTY groups
    (member count 0) are included. Raises NotFound when the registry table doesn't
    exist yet — the seam treats that as no groups."""
    settings = get_settings()
    group_table = sqlbuild.table_ref(
        settings, "bq_research_inputs_dataset", settings.bq_agrupamento_log_table
    )
    catalog_table = sqlbuild.table_ref(
        settings, "bq_research_inputs_dataset", settings.bq_produto_catalog_log_table
    )
    # NB: ``groups`` is a BigQuery reserved keyword — the CTE is ``grps``.
    sql = f"""
        with grps as (
          select group_id, group_name from (
            select group_id, group_name, active, row_number() over (
              partition by group_id order by edited_at desc, change_id desc
            ) as _rn from `{group_table}`
          ) where _rn = 1 and active
        ),
        members as (
          select agrupamento_id, count(*) as n_members from (
            select codigo_produto, banco, agrupamento_id, active, row_number() over (
              partition by {sqlbuild.CHAVE_CATALOGO} order by edited_at desc, change_id desc
            ) as _rn from `{catalog_table}`
          ) where _rn = 1 and active
          group by agrupamento_id
        )
        select g.group_id, g.group_name, coalesce(m.n_members, 0) as n_members
        from grps g left join members m on g.group_id = m.agrupamento_id
        order by lower(g.group_name)
    """
    return run_query(sql, [])


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_produto_catalog(banco: str | None = None):
    """The CURRENT active commodity catalog (latest row per (codigo_produto, banco),
    active=true) from the append-only Curadoria log. Optionally scoped to one banco.
    Raises NotFound when the log table doesn't exist yet (no catalog configured) — the
    seam treats that as an empty catalog. Short TTL + bounded by maximum_bytes_billed."""
    settings = get_settings()
    table = sqlbuild.table_ref(
        settings, "bq_research_inputs_dataset", settings.bq_produto_catalog_log_table
    )
    where = "where banco = @banco" if banco else ""
    sql = f"""
        select codigo_produto, banco, agrupamento, descricao_produto,
               ciclo_de_vida, ingestao, visibilidade, agrupamento_id, sidra_tabela
        from (
          select *, row_number() over (
            partition by {sqlbuild.CHAVE_CATALOGO} order by edited_at desc, change_id desc
          ) as _rn
          from `{table}` {where}
        )
        where _rn = 1 and active
    """
    params = [bigquery.ScalarQueryParameter("banco", "STRING", banco)] if banco else []
    try:
        return run_query(sql, params)
    except BadRequest:
        # An older produto_catalog_log predates a column the SELECT names (sidra_tabela /
        # agrupamento_id were added late). The writer self-heals via ALTER on every write, but a
        # read on a not-yet-written table would 500. Self-heal here (idempotent) + retry once,
        # so viewing the Cadastro never fails on a stale schema. Deferred import breaks the
        # curation→gateway cycle.
        from embrapa_dashboard.serving.curation import ensure_produto_catalog_log_table

        ensure_produto_catalog_log_table(settings)
        return run_query(sql, params)


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_catalog_editors(resource: str):
    """Distinct editor emails authorized for one catalog RESOURCE (research_inputs.
    <catalog_editors>). Short TTL so a Console add/remove takes effect within the
    window. Raises NotFound when the table doesn't exist — the seam treats that as
    'no allowlist configured' (open by default). Bounded by maximum_bytes_billed."""
    settings = get_settings()
    table = sqlbuild.table_ref(
        settings, "bq_research_inputs_dataset", settings.bq_catalog_editors_table
    )
    sql = (
        f"select distinct lower(trim(email)) as email from `{table}` "
        "where email is not null and resource = @resource"
    )
    params = [bigquery.ScalarQueryParameter("resource", "STRING", resource)]
    return run_query(sql, params)


# Gold fact tables per source, for the orphan diff (DISTINCT code is column-pruned → cheap).
# Shared with doctor's orphan health check — see sqlbuild.GOLD_CODE_SOURCES for why it
# lives in the flask-free module rather than here.
_GOLD_CODE_SOURCES = sqlbuild.GOLD_CODE_SOURCES


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_source_code_stats(source: str):
    """Per-code Gold state for a source: row count + reference-year span, from ONE
    aggregate over the Gold fact table (column-pruned to the code + reference_year, so a
    cheap scan; cached + maximum_bytes_billed-guarded). Backs the catalog's per-commodity
    status columns (linhas na Gold, período). ``source`` is the short banco token
    (pevs/comex/comtrade/pam/ppm). Raises NotFound if the token is unknown."""
    if source not in _GOLD_CODE_SOURCES:
        raise NotFound(f"unknown source {source!r}")
    table_name, code_col = _GOLD_CODE_SOURCES[source]
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_gold_dataset", table_name)
    sql = f"""
        select cast({code_col} as string) as code,
               count(*) as n_rows,
               min(reference_year) as year_start,
               max(reference_year) as year_end
        from `{table}`
        group by code
    """
    return run_query(sql, [], max_bytes=RAW_TABLE_MAX_BYTES)


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_source_products_gold(source: str):
    """Distinct (code, name) product list read DIRECTLY from a source's Gold fact table —
    UNGATED (no F7 visibility filter), unlike ``fetch_products`` which reads the gated
    serving marts. Backs the Curadoria ADMIN editor, which BY DESIGN must see hidden-but-
    active products too (``dim_produto_visibility`` deliberately isolates the gate from the
    admin editor). ``source`` is the long source id (ibge_pevs/…/un_comtrade); raises
    NotFound if unknown. Cheap (one code group-by, column-pruned) + maximum_bytes_billed."""
    table_name = _GOLD_TABLE.get(source)
    cols = _GOLD_PRODUCT.get(source)
    if table_name is None or cols is None:
        raise NotFound(f"unknown source {source!r}")
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_gold_dataset", table_name)
    code_col, name_col = cols
    sql = f"""
        select cast({code_col} as string) as code, any_value({name_col}) as name
        from `{table}`
        group by code
        order by code
    """
    return run_query(sql, [], max_bytes=RAW_TABLE_MAX_BYTES)


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_orphan_produtos():
    """Detect ORPHAN commodities — the "ficou órfão" transition: an entry that WAS in
    the catalog, was REMOVED (current state active=false), and whose Gold data STILL
    lingers (the entry's EXACT code still exists in the banco's Gold table). This is NOT
    "every uncataloged Gold code" (the catalog is a cross-source bridge, not a full
    registry — that diff would false-flag ~111 legitimate products); only a removal
    leaves data behind. Raises NotFound when the catalog log is absent (→ no orphans).
    Bounded by maximum_bytes_billed."""
    settings = get_settings()
    log = sqlbuild.table_ref(
        settings, "bq_research_inputs_dataset", settings.bq_produto_catalog_log_table
    )
    tombstoned_sql = f"""
        select codigo_produto, banco, agrupamento, removed_at from (
          select
            codigo_produto, banco, active, change_id,
            edited_at as removed_at,
            -- The tombstone row (active=false) carries agrupamento=NULL, so surface the
            -- LAST value the commodity had while still active (ignore the NULL tombstone),
            -- otherwise the Descontinuados view could never show the orphan's agrupamento.
            last_value(agrupamento ignore nulls) over (
              partition by {sqlbuild.CHAVE_CATALOGO} order by edited_at, change_id
              rows between unbounded preceding and unbounded following
            ) as agrupamento,
            row_number() over (
              partition by {sqlbuild.CHAVE_CATALOGO} order by edited_at desc, change_id desc
            ) as _rn
          from `{log}`
        ) where _rn = 1 and not active
    """
    # Step 1 (cheap — scans only the small catalog log): the tombstoned entries. The
    # COMMON case (nothing removed) returns here WITHOUT scanning any Gold table, so the
    # editor's orphan read is fast unless a removal actually happened.
    tomb = run_query(tombstoned_sql, [])
    if tomb is None or tomb.empty:
        return tomb
    # Step 2: keep only those whose EXACT code still exists in the banco's Gold (data
    # lingers) — scanning ONLY the Gold tables for the bancos that have a removal.
    bancos = {b for b in tomb["banco"].tolist() if b in _GOLD_CODE_SOURCES}
    if not bancos:
        return tomb.iloc[0:0]
    gold_union = " union all ".join(
        f"select '{src}' as src, {col} as code from "
        f"`{sqlbuild.table_ref(settings, 'bq_gold_dataset', tbl)}`"
        for src, (tbl, col) in _GOLD_CODE_SOURCES.items()
        if src in bancos
    )
    # A correlated EXISTS against a UNION ALL'd subquery (2+ bancos) is not something
    # BigQuery can de-correlate ("Correlated subqueries that reference other tables are
    # not supported..."); a plain JOIN expresses the same semantics and *is* supported.
    sql = f"""
        with tombstoned as ({tombstoned_sql}),
        gold_codes as ({gold_union})
        select distinct t.codigo_produto, t.banco, t.agrupamento, t.removed_at
        from tombstoned t
        join gold_codes g on g.src = t.banco and g.code = t.codigo_produto
    """
    return run_query(sql, [], max_bytes=RAW_TABLE_MAX_BYTES)


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_lifecycle_status():
    """Current lifecycle status per (element_kind, banco, code) from the lifecycle log
    (latest-wins): the flagged_at + reason + purge note for each Descontinuado/purged
    element. Raises NotFound when the log is absent (nothing marked yet)."""
    settings = get_settings()
    table = sqlbuild.table_ref(
        settings, "bq_research_inputs_dataset", settings.bq_catalog_lifecycle_log_table
    )
    sql = f"""
        select element_kind, banco, code, status, reason, scheduled_purge_note,
               edited_at as flagged_at
        from (
          select *, row_number() over (
            partition by {sqlbuild.CHAVE_CICLO_DE_VIDA} order by edited_at desc, change_id desc
          ) as _rn
          from `{table}`
        ) where _rn = 1
    """
    return run_query(sql, [])


@cache.memoize()
def fetch_quality_by_product(source: str):
    """data_quality_flag counts per product for a source (backs per-product FlagBars).

    Returns ``None`` for an unknown/unsupported source (the deliberate tri-state
    documented in the module docstring); the serializers treat that as empty.
    """
    table_name = _GOLD_TABLE.get(source)
    cols = _GOLD_PRODUCT.get(source)
    if table_name is None or cols is None:
        return None
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_gold_dataset", table_name)
    vis = sqlbuild.visibility_clause(settings, _SHORT_SOURCE[source], cols[0])
    sql, params = sqlbuild.quality_by_product(
        table, code_column=cols[0], name_column=cols[1], visibility_predicate=vis
    )
    return run_query(sql, params, max_bytes=RAW_TABLE_MAX_BYTES)


@cache.memoize()
def fetch_products(source: str):
    """Distinct product list for a source (backs `products`)."""
    table_name, code_col, name_col, _ = _product_source(source)
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", table_name)
    sql, params = sqlbuild.products(
        table,
        code_column=code_col,
        name_column=name_col,
        with_measure_kind=source in _MEASURE_KIND_SOURCES,
        with_sidra_tabela=source in _SIDRA_TABELA_SOURCES,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_product_timeseries(
    source: str,
    year_start: int | None = None,
    year_end: int | None = None,
    codes: Sequence[str] = (),
    value_column: str | None = None,
    uf_codes: Sequence[str] = (),
    flow: str | None = None,
    customs: str | None = None,
    market: str | None = None,
    reporters: Sequence[str] = (),
    partners: Sequence[str] = (),
    pin_reporter: str | None = _REPORTER_PIN_DEFAULT,
):
    """Annual per-product series (value + native quantity) for a source (backs productTS).

    ``uf_codes`` optionally narrows to the producing/origin UFs (cross-source per-UF
    scoping: PEVS mass/volume + farm-gate price). ``flow`` narrows trade sources to
    one direction (export/import); production sources must leave it ``None`` (their
    marts have no ``flow`` column). ``customs`` (regime aduaneiro) and ``market`` (tipo
    de mercado) narrow the COMTRADE mart to one customs procedure / economic purpose;
    only ``un_comtrade`` carries those columns, so other sources leave them ``None``.

    ``reporters``/``partners`` + ``pin_reporter`` (the country multi-selects) apply ONLY to
    ``un_comtrade`` — other sources have no reporter/partner columns, so they are forced
    empty and the pin stays unset.
    """
    table_name, code_col, _, default_value = _product_source(source)
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", table_name)
    # serving_comtrade_annual is multi-reporter; the country filters + the Brazil-default
    # pin apply only there. Production/COMEX marts have no reporter/partner dimension →
    # force them empty and leave the pin unset.
    is_comtrade = source == "un_comtrade"
    reporter_column = "reporter_iso_a3" if is_comtrade else None
    reporter_value = (
        _resolve_reporter_pin(settings, pin_reporter, reporters) if is_comtrade else None
    )
    rep = tuple(reporters) if is_comtrade else ()
    par = tuple(partners) if is_comtrade else ()
    sql, params = sqlbuild.product_timeseries(
        table,
        code_column=code_col,
        value_column=value_column or default_value,
        year_start=year_start,
        year_end=year_end,
        codes=tuple(codes),
        uf_codes=tuple(uf_codes),
        flow=flow,
        # COMTRADE "all flows" (flow=None) must sum ONLY export/import — re-export/re-import
        # are subsets (X ⊇ RX, M ⊇ RM), so adding them double-counts. COMEX/production have
        # no overlapping sub-flow, so they leave sum_flows None (flow=None sums every flow).
        sum_flows=sqlbuild.COMTRADE_TOTAL_FLOWS if is_comtrade else None,
        customs=customs,
        market=market,
        reporter_column=reporter_column,
        reporter_value=reporter_value,
        reporters=rep,
        partners=par,
        has_measure_kind=source in _MEASURE_KIND_SOURCES,
    )
    return run_query(sql, params)


@cache.memoize()
def fetch_source_metadata(source: str | None = None):
    """Per-source provenance from gold_source_metadata (backs dataStore.meta)."""
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_gold_dataset", "gold_source_metadata")
    sql, params = sqlbuild.source_metadata(table, source=source)
    return run_query(sql, params)


# Cross-source metric -> (mart, measure column, flow, code column, brazil_column).
# COMEX is Brazil's own customs (no reporter concept) → brazil_column None.
# COMTRADE is global: the per-country metrics pin ONE side to Brazil:
#   * exp_value/imp_value → reporter_iso_a3 = Brazil (Brazil's OWN declaration);
#   * partner_exp → partner_iso_a3 = Brazil on IMPORT rows (every OTHER country's
#     declaration of what it imported FROM Brazil — the trade-mirror's third line);
#   * world_exp → no Brazil filter (sum over all reporters).
# exp_price is NOT here — the UI derives it as exp_value / exp_weight.
_CROSS_METRICS = {
    "mdic_comex:exp_value": ("serving_comex_annual", "val_yearfx_usd", "export", "ncm_code", None),
    "mdic_comex:imp_value": ("serving_comex_annual", "val_yearfx_usd", "import", "ncm_code", None),
    "mdic_comex:exp_weight": ("serving_comex_annual", "net_weight_kg", "export", "ncm_code", None),
    "un_comtrade:exp_value": (
        "serving_comtrade_annual",
        "val_yearfx_usd",
        "export",
        "cmd_code",
        "reporter_iso_a3",
    ),
    "un_comtrade:imp_value": (
        "serving_comtrade_annual",
        "val_yearfx_usd",
        "import",
        "cmd_code",
        "reporter_iso_a3",
    ),
    "un_comtrade:partner_exp": (
        "serving_comtrade_annual",
        "val_yearfx_usd",
        "import",
        "cmd_code",
        "partner_iso_a3",
    ),
    "un_comtrade:world_exp": (
        "serving_comtrade_annual",
        "val_yearfx_usd",
        "export",
        "cmd_code",
        None,
    ),
}


def _cross_metric(metric: str) -> tuple[str, str, str, str, str | None]:
    try:
        return _CROSS_METRICS[metric]
    except KeyError:
        raise ValueError(
            f"unknown cross metric {metric!r}; choose one of {sorted(_CROSS_METRICS)}"
        ) from None


def fetch_cross_series(
    metric: str,
    year_start: int | None = None,
    year_end: int | None = None,
    codes: Sequence[str] = (),
    uf_codes: Sequence[str] = (),
):
    """Annual single-metric series for the cross-source view (backs crossSeries).

    ``codes`` optionally narrows to a commodity (per-source code) for market share.
    Brazil's COMTRADE share is exp_value (reporter=Brazil) ÷ world_exp (all reporters);
    partner_exp pins partner=Brazil instead (the mirror perspective). ``exp_price``
    is not served here — it is derived UI-side as exp_value / exp_weight.

    ``uf_codes`` optionally narrows to the origin UFs (cross-source per-UF scoping).
    Only the COMEX mart carries ``state_acronym``, so the filter is applied ONLY for
    COMEX metrics; for COMTRADE metrics it is dropped (its origin is a reporter
    country, not a Brazilian UF), keeping the query valid and the series national.

    The uf_codes are NORMALIZED before the memoized boundary (dropped for non-COMEX
    metrics) so two UF selections that build the identical national COMTRADE query share
    one cache entry instead of fanning out redundant keys + BigQuery round-trips.
    """
    table_name = _cross_metric(metric)[0]
    uf = tuple(uf_codes) if table_name == "serving_comex_annual" else ()
    return _fetch_cross_series_cached(metric, year_start, year_end, tuple(codes), uf)


@cache.memoize()
def _fetch_cross_series_cached(
    metric: str,
    year_start: int | None,
    year_end: int | None,
    codes: tuple[str, ...],
    uf_codes: tuple[str, ...],
):
    """Cached core of :func:`fetch_cross_series` — keyed on the NORMALIZED uf_codes."""
    table_name, measure, flow, code_column, brazil_column = _cross_metric(metric)
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", table_name)
    sql, params = sqlbuild.cross_annual(
        table,
        measure_column=measure,
        flow=flow,
        code_column=code_column,
        codes=tuple(codes),
        reporter_column=brazil_column,
        reporter_value=settings.comtrade_brazil_iso if brazil_column else None,
        year_start=year_start,
        year_end=year_end,
        uf_codes=uf_codes,
    )
    return run_query(sql, params)


@cache.memoize(timeout=DEFAULT_CLASSIFICATION_TTL)
def fetch_current_code_industrialization():
    """Live current industrialization level per (source, code) from the SCD2 view.

    Short TTL (``Settings.cache_classification_timeout``, default 30s, bound by
    ``init_cache`` onto this function's writable ``cache_timeout``) + explicit
    invalidation on save: the writing instance sees the edit instantly, other
    instances converge within the TTL — so this scales across Cloud Run instances
    on per-process SimpleCache, no shared Redis required.
    """
    settings = get_settings()
    table = sqlbuild.table_ref(settings, "bq_serving_dataset", "dim_code_industrialization_scd2")
    sql, params = sqlbuild.current_code_industrialization(table)
    return run_query(sql, params)


# ── Raw table inspection (the "Dados" perspective) ─────────────────────────────
# The ALLOWLIST of tables a researcher may browse per banco: the comprehensive Gold
# table + the serving marts that feed its charts (NOT the Silver/Bronze pipeline
# internals, NOT the shared cross-source marts). Each entry is
# (table, dataset_attr, label, grain); `table` is BOTH the BigQuery table name and the
# stable id /api/table resolves. The endpoint REFUSES any (banco, table) not in this map
# — the security boundary that stops a raw-row endpoint from reading an arbitrary table.
# The four medallion LAYERS, in lineage order — drives the "Estrutura de dados" explorer's
# grouping + the per-layer explanation. Each _INSPECT_TABLES row carries its layer (5th field).
_INSPECT_LAYERS = ("bronze", "silver", "gold", "serving")

# Shared deflation/FX reference (Silver) — feeds the real (inflation-corrected) and
# currency-converted values of EVERY monetary banco's Gold, so it is surfaced (labelled
# "apoio · compartilhada") under each banco's Silver layer. No commodity code → no F7 gate.
_SILVER_DEFLATION: list[tuple[str, str, str, str, str]] = [
    (
        "silver_bcb_inflation",
        "bq_silver_dataset",
        "Inflação IPCA/IGP — apoio (compartilhada)",
        "Índices mensais encadeados (IPCA, IGP-M, IGP-DI) — base da correção para valores reais.",
        "silver",
    ),
    (
        "silver_bcb_currency",
        "bq_silver_dataset",
        "Câmbio PTAX — apoio (compartilhada)",
        "Cotações diárias de BRL por USD/EUR — base da conversão entre moedas.",
        "silver",
    ),
]

# Allowlist of inspectable tables per banco, now spanning ALL FOUR medallion layers
# (Bronze → Silver → Gold → Serving) for the "Estrutura de dados" perspective. Each entry is
# (table, dataset_attr, label, grain, layer); `table` is BOTH the BigQuery table name and the
# stable id /api/table resolves. The endpoint REFUSES any (banco, table) not in this map — the
# security boundary that stops a raw-row endpoint from reading an arbitrary table. Browsing is
# free (tabledata.list, storage order); ORDER BY / filter is cost-guarded (RAW_TABLE_MAX_BYTES).
# NOTE: the F7 visibility gate is applied only to the Gold fact (see _inspect_visibility_predicate);
# Bronze/Silver are PRE-curation raw lineage, shown ungated on purpose (transparency tool).
_INSPECT_TABLES: dict[str, list[tuple[str, str, str, str, str]]] = {
    "ibge_pevs": [
        (
            "sidra_t289_raw",
            "bq_bronze_ibge_dataset",
            "SIDRA 289 — extração vegetal (bruto)",
            "Cópia fiel do IBGE/SIDRA (PEVS), append-only, todas as colunas como texto.",
            "bronze",
        ),
        (
            "silver_ibge_pevs",
            "bq_silver_dataset",
            "PEVS padronizado",
            "Deduplicado por chave natural, tipado e com a marca de qualidade — antes do Gold.",
            "silver",
        ),
        *_SILVER_DEFLATION,
        (
            "gold_pevs_production",
            "bq_gold_dataset",
            "Produção PEVS",
            "Tabela principal — uma linha por (ano, UF, município, produto).",
            "gold",
        ),
        (
            "serving_pevs_annual",
            "bq_serving_dataset",
            "Mart anual",
            "Derivada — agregado (ano × UF × produto × família) que alimenta os gráficos.",
            "serving",
        ),
    ],
    "ibge_pam": [
        (
            "sidra_t5457_raw",
            "bq_bronze_pam_dataset",
            "SIDRA 5457 — produção agrícola (bruto)",
            "Cópia fiel do IBGE/SIDRA (PAM), append-only, todas as colunas como texto.",
            "bronze",
        ),
        (
            "silver_ibge_pam",
            "bq_silver_dataset",
            "PAM padronizado",
            "Deduplicado, tipado, com área plantada/colhida e a marca de qualidade.",
            "silver",
        ),
        *_SILVER_DEFLATION,
        (
            "gold_pam_production",
            "bq_gold_dataset",
            "Produção PAM",
            "Tabela principal — uma linha por (ano, UF, município, produto), com área.",
            "gold",
        ),
        (
            "serving_pam_annual",
            "bq_serving_dataset",
            "Mart anual",
            "Derivada — agregado (ano × UF × produto × família) com área/rendimento.",
            "serving",
        ),
    ],
    "ibge_ppm": [
        (
            "sidra_t3939_raw",
            "bq_bronze_ppm_dataset",
            "SIDRA 3939 — efetivo dos rebanhos (bruto)",
            "Cópia fiel do IBGE/SIDRA (PPM, rebanhos/cabeças), append-only, colunas como texto.",
            "bronze",
        ),
        (
            "sidra_t74_raw",
            "bq_bronze_ppm_dataset",
            "SIDRA 74 — produção animal (bruto)",
            "Cópia fiel do IBGE/SIDRA (PPM, leite/ovos/mel/lã), append-only, colunas como texto.",
            "bronze",
        ),
        (
            "silver_ibge_ppm",
            "bq_silver_dataset",
            "PPM padronizado",
            "União das duas tabelas Bronze, tipado, com measure_kind (estoque|fluxo) e qualidade.",
            "silver",
        ),
        *_SILVER_DEFLATION,
        (
            "gold_ppm_production",
            "bq_gold_dataset",
            "Pecuária PPM",
            "Tabela principal — uma linha por (ano, UF, município, produto/rebanho).",
            "gold",
        ),
        (
            "serving_ppm_annual",
            "bq_serving_dataset",
            "Mart anual",
            "Derivada — agregado (ano × UF × produto × família) com measure_kind.",
            "serving",
        ),
    ],
    "mdic_comex": [
        (
            "comex_flows_raw",
            "bq_bronze_comex_dataset",
            "Comex Stat — fluxos (bruto)",
            "Cópia fiel do CSV do MDIC/SECEX (EXP/IMP), append-only, colunas como texto.",
            "bronze",
        ),
        (
            "silver_comex_flows",
            "bq_silver_dataset",
            "COMEX padronizado",
            "Deduplicado, tipado, NCM aposentado normalizado e a marca de qualidade.",
            "silver",
        ),
        *_SILVER_DEFLATION,
        (
            "gold_comex_flows",
            "bq_gold_dataset",
            "Fluxos COMEX",
            "Tabela principal — fluxos mensais (ano, mês, NCM, UF, país, fluxo).",
            "gold",
        ),
        (
            "serving_comex_annual",
            "bq_serving_dataset",
            "Mart anual",
            "Derivada — agregado anual (ano × NCM × UF × fluxo) dos gráficos.",
            "serving",
        ),
        (
            "serving_comex_seasonality",
            "bq_serving_dataset",
            "Mart de sazonalidade",
            "Derivada — grão mensal (ano × mês × NCM × UF × fluxo) da view Sazonalidade.",
            "serving",
        ),
    ],
    "un_comtrade": [
        (
            "comtrade_flows_raw",
            "bq_bronze_comtrade_dataset",
            "UN Comtrade — fluxos (bruto)",
            "Cópia fiel da API da ONU, append-only, todas as colunas como texto.",
            "bronze",
        ),
        (
            "silver_comtrade_flows",
            "bq_silver_dataset",
            "COMTRADE padronizado",
            "Deduplicado, tipado, HS aposentado normalizado e a marca de qualidade.",
            "silver",
        ),
        *_SILVER_DEFLATION,
        (
            "gold_comtrade_flows",
            "bq_gold_dataset",
            "Fluxos COMTRADE",
            "Tabela principal — fluxos (ano, HS, reporter, parceiro, fluxo).",
            "gold",
        ),
        (
            "serving_comtrade_annual",
            "bq_serving_dataset",
            "Mart anual",
            "Derivada — agregado anual (ano × HS × reporter × parceiro × fluxo).",
            "serving",
        ),
    ],
}


# A TIGHTER per-call byte cap for raw-table sort/filter queries than the 100 GiB global
# guard — a SELECT * sort of the largest Gold table scans ~a couple GiB, so 10 GiB allows
# every legitimate query yet FAILS a pathological one far below the global ceiling
# (defense-in-depth for a raw-data endpoint).
RAW_TABLE_MAX_BYTES = 10 * 1024**3

# Upper bound on the pagination OFFSET for the raw-table / seed browse. The free
# tabledata.list browse path passes ``start_index=offset`` straight to BigQuery, which
# skips proportionally through storage — so an absurd ``?offset=9999999999`` on a large
# Bronze table would trigger a needless deep skip (no bytes billed, but wasted compute).
# The UI paginates 100 rows/page, so 5M rows deep is far past any manual browse; clamp
# there to bound the worst case while keeping every realistic page reachable (audit COST-1).
RAW_TABLE_MAX_OFFSET = 5_000_000


def inspectable_tables(banco_id: str) -> list[dict]:
    """The allowlisted tables a researcher may browse for a banco (the 'Dados' picker).

    Returns ``[{id, label, grain, layer}]`` — empty for an unknown banco. ``id`` is the
    BigQuery table name, the same token /api/table resolves; ``layer`` is one of
    _INSPECT_LAYERS (bronze|silver|gold|serving) so the UI groups the pipeline. (The dataset is
    resolved server-side in _resolve_inspect_table — never exposed, so the payload leaks no
    internal attr.)"""
    return [
        {"id": table, "label": label, "grain": grain, "layer": layer}
        for table, _dataset_attr, label, grain, layer in _INSPECT_TABLES.get(banco_id, [])
    ]


def _resolve_inspect_table(banco_id: str, table_id: str) -> str:
    """Resolve an allowlisted (banco, table) to a fully-qualified ``project.dataset.table``.

    The SECURITY boundary of the raw-row endpoint: a (banco, table) outside _INSPECT_TABLES
    raises ValueError (→ 400), so no caller can read an arbitrary BigQuery table."""
    for table, dataset_attr, _label, _grain, _layer in _INSPECT_TABLES.get(banco_id, []):
        if table == table_id:
            return sqlbuild.table_ref(get_settings(), dataset_attr, table)
    raise ValueError(
        f"table {table_id!r} is not inspectable for banco {banco_id!r}; "
        f"choose one of {[t[0] for t in _INSPECT_TABLES.get(banco_id, [])]}"
    )


def _inspect_visibility_predicate(banco_id: str, table_id: str) -> str:
    """The F7 visibility gate for the Dados raw-row inspector. When the inspected table is the
    banco's GOLD fact, return the NOT EXISTS predicate (serving/sql.visibility_clause) so a
    commodity marked indisponível is excluded from raw browse / sort / filter / CSV export too —
    matching every other researcher-facing Gold read. The serving marts are already gated at
    build time (hidden_code_predicate), so they get no extra predicate; returns '' for them and
    for any source without a known short token / code column. Identifiers come from fixed maps
    (never user input) → injection-safe. No-op while dim_produto_visibility is empty."""
    if _GOLD_TABLE.get(banco_id) != table_id:
        return ""
    short = _SHORT_SOURCE.get(banco_id)
    cols = _GOLD_PRODUCT.get(banco_id)
    if not short or not cols:
        return ""
    return sqlbuild.visibility_clause(get_settings(), short, cols[0])


@cache.memoize()
def fetch_table_schema(banco_id: str, table_id: str) -> dict:
    """Column names + types + row count for an allowlisted table (FREE — table metadata,
    no query). Drives the grid headers AND the order-by/filter column allowlist."""
    ref = _resolve_inspect_table(banco_id, table_id)
    table = _client().get_table(ref)
    columns = [{"name": f.name, "type": f.field_type} for f in table.schema]
    return {"columns": columns, "num_rows": int(table.num_rows or 0)}


@cache.memoize()
def fetch_table_rows(
    banco_id: str,
    table_id: str,
    *,
    limit: int,
    offset: int = 0,
    order_by: str | None = None,
    order_dir: str = "asc",
    filters: tuple = (),
):
    """A page of raw rows for an allowlisted table. HYBRID: a plain browse (no order/filter)
    uses the FREE ``tabledata.list`` (storage order, no scan billed); an ORDER BY or filter
    runs a cost-guarded query. ``filters`` is a tuple of ``(col, op, val)`` tuples (hashable
    for the memoize key)."""
    ref = _resolve_inspect_table(banco_id, table_id)
    vis = _inspect_visibility_predicate(banco_id, table_id)
    lim = max(1, min(int(limit), sqlbuild.RAW_TABLE_MAX_LIMIT))
    off = max(0, min(int(offset), RAW_TABLE_MAX_OFFSET))
    # A gated Gold fact (vis != '') CANNOT use the free tabledata.list shortcut — that path
    # can't carry the F7 predicate — so it always goes through the (cost-guarded) query path.
    if not order_by and not filters and not vis:
        return (
            _client()
            .list_rows(ref, max_results=lim, start_index=off)
            .to_dataframe(create_bqstorage_client=False)
        )
    columns_types = {
        c["name"]: c["type"] for c in fetch_table_schema(banco_id, table_id)["columns"]
    }
    flt = [{"col": c, "op": o, "val": v} for (c, o, v) in filters]
    sql, params = sqlbuild.raw_table_rows(
        ref,
        columns_types=columns_types,
        limit=lim,
        offset=off,
        order_by=order_by,
        order_dir=order_dir,
        filters=flt,
        visibility_predicate=vis,
    )
    return run_query(sql, params, max_bytes=RAW_TABLE_MAX_BYTES)


@cache.memoize()
def fetch_table_count(banco_id: str, table_id: str, filters: tuple = ()) -> int:
    """Total matching rows (the pagination denominator). Unfiltered → the table's cached
    ``num_rows`` (free); filtered → a cost-guarded ``COUNT(*)``.

    The unfiltered denominator inherits the table-metadata cache TTL, so in the brief window
    right after a nightly dbt rebuild changes the row count it can momentarily disagree with a
    freshly-fetched page — the same CACHE_DEFAULT_TIMEOUT convergence the serving marts follow
    (ARCHITECTURE.md). Deliberately accepted: a shorter dedicated TTL would multiply free-but-
    frequent metadata reads for a cosmetic, self-healing off-by-N on a once-a-day boundary."""
    vis = _inspect_visibility_predicate(banco_id, table_id)
    # Unfiltered + ungated → the table's cached num_rows (free). A gated Gold fact must run a
    # real COUNT(*) so the denominator matches the gated page (hidden rows excluded from both).
    if not filters and not vis:
        return fetch_table_schema(banco_id, table_id)["num_rows"]
    ref = _resolve_inspect_table(banco_id, table_id)
    columns_types = {
        c["name"]: c["type"] for c in fetch_table_schema(banco_id, table_id)["columns"]
    }
    flt = [{"col": c, "op": o, "val": v} for (c, o, v) in filters]
    sql, params = sqlbuild.raw_table_count(
        ref, columns_types=columns_types, filters=flt, visibility_predicate=vis
    )
    df = run_query(sql, params, max_bytes=RAW_TABLE_MAX_BYTES)
    return int(df["n"].iloc[0]) if not df.empty else 0


# ── Reference-table consultation (the "Referências" perspective) ───────────────
# Read-only catalog of the dbt SEEDS a researcher may CONSULT (never edit here) to
# confirm the reference values the pipeline relies on, and report a wrong value via
# the feedback channel. Seeds materialize into the SILVER dataset (dbt_project.yml
# seeds +schema = BQ_SILVER_DATASET). Each entry is (seed_id, label, editable,
# description); seed_id is BOTH the BigQuery table name and the stable id /api/seed
# resolves — the endpoint REFUSES any id not in this map (the security boundary, like
# _INSPECT_TABLES). `editable` records whether the value is researcher-editable
# *elsewhere* (the commodity catalog) vs engineer-only CALIBRATION: a wrong currency
# factor silently rescales every historical value by 10^6–10^9, so those stay read-only.
# Labels/descriptions are pt-BR (the end user reads them — project language rule).
# NOTE: this list is SEEDS ONLY (a test asserts it matches dbt/seeds/*.csv one-to-one).
# Non-seed reference tables live in _REFERENCE_TABLE_CATALOG below; the perspective shows
# both, and _resolve_seed_table accepts both.
_SEED_CATALOG: list[tuple[str, str, bool, str]] = [
    # NOTE: commodity_crosswalk is NOT here — it became the editable Curadoria catalog
    # (research_inputs.produto_catalog_log → dim_produto_catalog), edited via the
    # "Cadastro de commodities" admin view, not consulted as a read-only seed. The seeds
    # below are all read-only CALIBRATION / source-faithful dimensions (engineer-owned).
    (
        "historical_currency_factors",
        "Fatores de reforma monetária",
        False,
        "Multiplicadores que convertem valores históricos (Cruzeiro, Cruzado, …) para o "
        "Real atual. Calibração de alta precisão: um valor errado distorce em milhões de "
        "vezes todos os números anteriores a 1994.",
    ),
    (
        "unit_family_conversions",
        "Conversões de unidade",
        False,
        "Converte cada unidade de origem (t, m³, saca, …) para a unidade-base da sua "
        "família. Fonte única da normalização de quantidade.",
    ),
    (
        "product_unit_factors",
        "Fatores de unidade por produto",
        False,
        "Override de conversão para unidades cujo fator depende do produto "
        "(saca, arroba, bushel, barril).",
    ),
    (
        "comex_ncm",
        "NCM (COMEX)",
        False,
        "Descrições dos códigos NCM no escopo COMEX (dimensão do MDIC).",
    ),
    (
        "comex_ncm_succession",
        "Sucessão de NCM (COMEX)",
        False,
        "Mapa de NCM antigo → atual, para um histórico transparente quando um código é renumerado.",
    ),
    (
        "comex_country",
        "Países (COMEX)",
        False,
        "Dimensão de país do MDIC (CO_PAIS → ISO-3 + nome).",
    ),
    (
        "comex_unit",
        "Unidades estatísticas (COMEX)",
        False,
        "Dimensão de unidade estatística do MDIC (CO_UNID → rótulo).",
    ),
    (
        "comex_via",
        "Vias de transporte (COMEX)",
        False,
        "Dimensão de via de transporte do MDIC (CO_VIA → rótulo).",
    ),
    (
        "comtrade_hs",
        "HS (COMTRADE)",
        False,
        "Descrições dos códigos HS no escopo COMTRADE (dimensão de mercadoria da ONU).",
    ),
    (
        "comtrade_hs_succession",
        "Sucessão de HS (COMTRADE)",
        False,
        "Mapa de HS antigo → atual, para um histórico transparente entre revisões do "
        "Sistema Harmonizado.",
    ),
    (
        "comtrade_country",
        "Áreas/países (COMTRADE)",
        False,
        "Dimensão de área M49 da ONU → ISO-3 + nome (reporter e parceiro).",
    ),
    (
        "comtrade_unit",
        "Unidades de quantidade (COMTRADE)",
        False,
        "Dimensão de unidade de quantidade do COMTRADE → família física.",
    ),
    (
        "ibge_municipio_mesh",
        "Malha municipal (IBGE)",
        False,
        "Cada município → suas regiões (UF, grande região, meso/micro e "
        "intermediária/imediata). ~5570 linhas, regenerada por script.",
    ),
]
_SEED_BY_ID: dict[str, tuple[str, str, bool, str]] = {s[0]: s for s in _SEED_CATALOG}

# Consultable reference tables that are NOT dbt seeds: Silver dbt MODELS built from an
# INGESTED source rather than a CSV. Kept in a SEPARATE list because a test asserts a strict
# bijection between _SEED_CATALOG and dbt/seeds/*.csv (so a new seed can never ship
# unexposed); these have no CSV and would break it. Same shape and same read path — they
# live in the SAME silver dataset, so _resolve_seed_table resolves them identically.
#
# The BCB series belong here for the researcher, not just in "Estrutura de dados": they are
# the CALIBRATION behind every displayed monetary figure — the FX table converts BRL↔USD/EUR
# and the inflation table deflates to real values. Consulting them is the same act as
# consulting historical_currency_factors (a seed, already listed): confirming the reference
# values the pipeline applied. All read-only (source-owned: Banco Central).
_REFERENCE_TABLE_CATALOG: list[tuple[str, str, bool, str]] = [
    (
        "silver_bcb_currency",
        "Câmbio PTAX (BCB)",
        False,
        "Cotações diárias do Banco Central: quantos reais vale uma unidade de cada moeda "
        "estrangeira (USD, EUR). É a base da conversão quando você troca a moeda nas "
        "convenções métricas.",
    ),
    (
        "silver_bcb_inflation",
        "Índices de inflação (BCB)",
        False,
        "Séries mensais de IPCA, IGP-M e IGP-DI, com a variação do mês e o índice "
        "encadeado. É a base da correção monetária que converte valores nominais em "
        "valores reais, comparáveis entre anos.",
    ),
]
_REFERENCE_BY_ID: dict[str, tuple[str, str, bool, str]] = {
    s[0]: s for s in _REFERENCE_TABLE_CATALOG
}
# Everything /api/seed may read — the allowlist enforced by _resolve_seed_table.
_CONSULTABLE_BY_ID: dict[str, tuple[str, str, bool, str]] = {
    **_SEED_BY_ID,
    **_REFERENCE_BY_ID,
}


# Display order of the picker, by THEME rather than by which catalog an entry came from:
# the monetary trio (currency reform → FX → inflation) reads as one story, so the two BCB
# tables sit next to historical_currency_factors instead of trailing the source dimensions.
# Only ids that need to be pulled forward are listed; everything else keeps catalog order.
_REFERENCE_DISPLAY_AFTER: dict[str, tuple[str, ...]] = {
    "historical_currency_factors": ("silver_bcb_currency", "silver_bcb_inflation"),
}


def seed_tables() -> list[dict]:
    """The read-only reference tables a researcher may consult ('Referências').

    Banco-agnostic (shared reference data): the dbt SEEDS (calibration + source dimensions)
    plus the non-seed Silver reference models (the BCB FX / inflation series), ordered by
    theme via _REFERENCE_DISPLAY_AFTER. Returns ``[{id, label, editable, description}]``
    straight from the static catalogs — no BigQuery round-trip (row counts arrive when one
    is opened, via its schema)."""

    def _as_dict(item: tuple[str, str, bool, str]) -> dict:
        sid, label, editable, desc = item
        return {"id": sid, "label": label, "editable": editable, "description": desc}

    pulled = {sid for ids in _REFERENCE_DISPLAY_AFTER.values() for sid in ids}
    out: list[dict] = []
    for item in (*_SEED_CATALOG, *_REFERENCE_TABLE_CATALOG):
        if item[0] in pulled:
            continue  # emitted right after its anchor instead
        out.append(_as_dict(item))
        for sid in _REFERENCE_DISPLAY_AFTER.get(item[0], ()):
            out.append(_as_dict(_CONSULTABLE_BY_ID[sid]))
    return out


def _resolve_seed_table(seed_id: str) -> str:
    """Resolve a consultable reference id to its fully-qualified ``project.silver.<table>``.

    The SECURITY boundary of the seed endpoint: an id outside the consultable catalogs
    raises ValueError (→ 400), so no caller can read an arbitrary BigQuery table."""
    if seed_id not in _CONSULTABLE_BY_ID:
        raise ValueError(
            f"seed {seed_id!r} is not a consultable reference table; "
            f"choose one of {list(_CONSULTABLE_BY_ID)}"
        )
    return sqlbuild.table_ref(get_settings(), "bq_silver_dataset", seed_id)


@cache.memoize()
def fetch_seed_schema(seed_id: str) -> dict:
    """Column names + types + row count for a consultable seed (FREE — table metadata,
    no query). Drives the grid headers AND the order-by/filter column allowlist."""
    ref = _resolve_seed_table(seed_id)
    table = _client().get_table(ref)
    columns = [{"name": f.name, "type": f.field_type} for f in table.schema]
    return {"columns": columns, "num_rows": int(table.num_rows or 0)}


@cache.memoize()
def fetch_seed_rows(
    seed_id: str,
    *,
    limit: int,
    offset: int = 0,
    order_by: str | None = None,
    order_dir: str = "asc",
    filters: tuple = (),
):
    """A page of rows for a consultable seed. Mirrors :func:`fetch_table_rows` (same
    HYBRID free-``tabledata.list`` browse vs cost-guarded ORDER/filter query, same
    column-allowlist-from-schema and value-binding), but seed-scoped to the Silver
    reference tables. Read-only — there is no write counterpart for seeds."""
    ref = _resolve_seed_table(seed_id)
    lim = max(1, min(int(limit), sqlbuild.RAW_TABLE_MAX_LIMIT))
    off = max(0, min(int(offset), RAW_TABLE_MAX_OFFSET))
    if not order_by and not filters:
        return (
            _client()
            .list_rows(ref, max_results=lim, start_index=off)
            .to_dataframe(create_bqstorage_client=False)
        )
    columns_types = {c["name"]: c["type"] for c in fetch_seed_schema(seed_id)["columns"]}
    flt = [{"col": c, "op": o, "val": v} for (c, o, v) in filters]
    sql, params = sqlbuild.raw_table_rows(
        ref,
        columns_types=columns_types,
        limit=lim,
        offset=off,
        order_by=order_by,
        order_dir=order_dir,
        filters=flt,
    )
    return run_query(sql, params, max_bytes=RAW_TABLE_MAX_BYTES)


@cache.memoize()
def fetch_seed_count(seed_id: str, filters: tuple = ()) -> int:
    """Total matching rows for a consultable seed (the pagination denominator).
    Unfiltered → the cached ``num_rows`` (free); filtered → a cost-guarded ``COUNT(*)``."""
    if not filters:
        return fetch_seed_schema(seed_id)["num_rows"]
    ref = _resolve_seed_table(seed_id)
    columns_types = {c["name"]: c["type"] for c in fetch_seed_schema(seed_id)["columns"]}
    flt = [{"col": c, "op": o, "val": v} for (c, o, v) in filters]
    sql, params = sqlbuild.raw_table_count(ref, columns_types=columns_types, filters=flt)
    df = run_query(sql, params, max_bytes=RAW_TABLE_MAX_BYTES)
    return int(df["n"].iloc[0]) if not df.empty else 0
