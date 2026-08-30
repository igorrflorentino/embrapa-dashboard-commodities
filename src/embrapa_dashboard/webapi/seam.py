"""The single data seam between the UI and BigQuery.

This is the Python equivalent of the prototype's ``dataStore.datasetFor`` +
``applyFilters``. It does **not** issue its own SQL — it composes the verified
``serving.gateway`` readers (Pushdown Computing: parameterized queries against
the pre-aggregated marts, memoized by ``flask-caching``) into the
``BancoSnapshot`` shapes the views consume.

Golden rule (handoff): the views never change; this layer produces data in the
shape they expect. Every per-banco difference lives here, nowhere else.

M1 scope: the seam serves the PEVS-shaped generic snapshot (products, productTS,
overviewTS, ufData, quality) for the three live bancos. Trade-only adapters
(flow/partner/monthly) and the cross-source builders arrive in M2/M3.
"""

from __future__ import annotations

import pandas as pd
from google.api_core.exceptions import NotFound

from embrapa_dashboard.serving import gateway
from embrapa_dashboard.serving import sql as sqlbuild

from . import format as fmt
from .registries import BANCOS, Banco, banco_by_id
from .seam_base import (  # noqa: F401  (commodity toolkit re-exported via seam)
    _LIVE_SOURCES,
    _codes,
    _crosswalk_df,
    _xyear,
    produto_catalog,
)

# The registered banco ids — used to tell an UNKNOWN banco id (which banco_by_id
# silently maps to PEVS) from a real one, so source_meta never leaks PEVS cobertura
# for a nonexistent banco.
_REGISTERED_BANCO_IDS = frozenset(b.id for b in BANCOS)

# Trade bancos are USD-NATIVE (customs values declared in US$ — FOB exports, CIF
# imports for COMTRADE), but the serving marts now carry the SAME currency matrix
# as PEVS (val_yearfx_{brl,usd,eur} + val_real_{ipca,igpm,igpdi}_{brl,usd,eur} —
# the REAL year-FX / deflated values Gold computes), so a BRL/EUR display serves
# the real column instead of the frontend cross-converting USD via a mock FX rate.
_TRADE = {"mdic_comex", "un_comtrade"}


def _trade_valuation_note(banco: Banco) -> str:
    """The US$-source valuation basis a trade banco's value label must state.

    COMTRADE sums both flows where exports are FOB and imports CIF; COMEX is FOB
    for both. The note is appended to the convention label so a researcher reading
    a BRL/EUR figure still knows it is the year-FX conversion of the customs US$.
    """
    if banco.id == "un_comtrade":
        return "FOB exportação / CIF importação"
    return "FOB"


def effective_value_column(banco: Banco, conv: dict) -> tuple[str, str]:
    """Resolve (column, human_label) for the active convention, with fallback.

    Every live mart now carries the full {yearfx, real_ipca, real_igpm, real_igpdi}
    × {brl, usd, eur} matrix (minus the IGP-M/IGP-DI × USD combos the allowlist
    deliberately omits). We pick the requested column when the mart has it, else
    fall back to the nearest available, so the conventions strip never errors on an
    unmodelled combo (e.g. USD + IGP-M).

    For trade bancos the values are the year-FX conversion of US$ customs figures,
    so the label keeps the FOB/CIF basis note — but the figure IS in the requested
    currency (no client-side mock FX). The default request (empty conv) resolves to
    BRL·IPCA via :func:`embrapa_dashboard.webapi.format.monetary_column`; trade
    callers that want the US$-native default pass ``{"currency": "USD",
    "correction": "Nominal"}``.
    """
    requested = fmt.monetary_column(conv.get("currency", "BRL"), conv.get("correction", "IPCA"))
    if banco.id in _TRADE:
        note = _trade_valuation_note(banco)
        if requested in sqlbuild.ALLOWED_VALUE_COLUMNS:
            return requested, f"{fmt.convention_value_label(conv)} · {note}"
        # Fallback chain (same as PEVS): same correction in BRL, then real IPCA BRL —
        # all REAL columns, never a mock conversion.
        brl = fmt.monetary_column("BRL", conv.get("correction", "IPCA"))
        if brl in sqlbuild.ALLOWED_VALUE_COLUMNS:
            label = fmt.convention_value_label({**conv, "currency": "BRL"})
            return brl, f"{label} (moeda indisponível no mart → R$) · {note}"
        return "val_real_ipca_brl", f"Valor real (IPCA) — R$ · {note}"
    if requested in sqlbuild.ALLOWED_VALUE_COLUMNS:
        return requested, fmt.convention_value_label(conv)
    # Fallback chain: same correction in BRL, then real IPCA BRL.
    brl = fmt.monetary_column("BRL", conv.get("correction", "IPCA"))
    if brl in sqlbuild.ALLOWED_VALUE_COLUMNS:
        label = fmt.convention_value_label({**conv, "currency": "BRL"})
        return brl, f"{label} (moeda indisponível no mart → R$)"
    return "val_real_ipca_brl", "Valor real (IPCA) — R$"


def _years_from_summary(summary: dict | None) -> tuple[int | None, int | None]:
    """Parse (year_start, year_end) from the filter summary's date strings/years."""
    if not summary:
        return None, None

    def _year(key: str) -> int | None:
        v = summary.get(key)
        if not v:
            return None
        try:
            return int(str(v)[:4])
        except (TypeError, ValueError):
            return None

    return _year("startDate"), _year("endDate")


def _basket(summary: dict | None) -> tuple[str, ...]:
    """Product codes selected (empty tuple = no product filter = all)."""
    if not summary:
        return ()
    codes = summary.get("basket")
    return tuple(codes) if codes else ()


# The sentinel for "this code has no level yet". Offered as an explicit choice rather than
# folded into the others: a researcher slicing by level must be able to SEE what is
# unclassified instead of having it vanish from every slice, which is the project's
# no-invisible-filtering rule applied to a dimension that is curated by hand and therefore
# never complete by construction.
UNCLASSIFIED_LEVEL = "sem_classificacao"


def _codes_for_levels(banco_id: str, niveis: tuple[str, ...], universe: set[str]) -> set[str]:
    """The codes of ``banco_id`` whose current industrialization level is in ``niveis``.

    ``universe`` is the banco's full code set, needed only for the ``sem_classificacao``
    sentinel: an unclassified code is defined by ABSENCE from the classification dim, so
    it cannot be selected by looking at the dim alone.

    Returns a SET so the caller can intersect it with the basket — the two narrowings
    compose (a researcher may want "só o açaí, e só o que é bruto"), and intersection is
    the only composition that keeps both promises.
    """
    if not niveis:
        return set(universe)
    df = gateway.fetch_current_code_industrialization()
    classificados: dict[str, str] = {}
    if df is not None and len(df):
        for row in df.itertuples(index=False):
            if row.source == banco_id:
                classificados[str(row.code)] = str(row.industrialization_level)
    escolhidos = {c for c, nivel in classificados.items() if nivel in niveis}
    if UNCLASSIFIED_LEVEL in niveis:
        escolhidos |= {c for c in universe if c not in classificados}
    return escolhidos


def _niveis_from_summary(summary: dict | None) -> tuple[str, ...]:
    """Industrialization levels selected (empty tuple = no level filter = all)."""
    if not summary:
        return ()
    niveis = summary.get("niveis")
    return tuple(niveis) if niveis else ()


def _states(summary: dict | None) -> tuple[str, ...]:
    """Origin-UF acronyms selected (empty tuple = no UF filter = all).

    The frontend's filter summary carries the UF selection under ``states``
    (``null``/absent = all · ``[]`` = none). Only the COMEX-origin readers can
    honour it (their mart carries ``state_acronym``); other trade grains surface
    it as not-applicable rather than silently dropping it.
    """
    if not summary:
        return ()
    states = summary.get("states")
    return tuple(states) if states else ()


def _flow_from_summary(summary: dict | None) -> str | None:
    """The server-side flow filter (export/import) from the FilterMenu selection.

    Flow is the ONE filter the snapshot applies server-side: the trade marts are
    pre-aggregated over flow, so picking a direction re-queries (product/geo/year
    stay client-side in dataFilters.js). ``'all'`` (or absent) → ``None``, which
    sums every flow — the historical default, so an unfiltered request stays
    byte-identical to before this param existed. Only trade marts carry ``flow``;
    the seam passes this ONLY in its trade branch.
    """
    if not summary:
        return None
    flow = summary.get("flow")
    if not flow or flow == "all":
        return None
    return flow


def _sidra_tabela_from_summary(summary: dict | None) -> str | None:
    """Which SIDRA TABLE the panel is scoped to, from the FilterMenu.

    A produto's identity is ``(banco, tabela, código)``, so the table is what tells the
    two halves of a multi-table banco apart — PEVS t289 (extração vegetal, native forest)
    vs t291 (silvicultura, planted). ``'all'`` / absent → ``None`` = sum every table,
    which for PEVS is the survey's own total and keeps an unfiltered request
    byte-identical to the one this seam emitted before the axis existed. Mirrors
    ``_flow_from_summary``; only the PEVS-shaped branch passes it, since single-table
    bancos have no ``sidra_tabela`` column to filter on.
    """
    if not summary:
        return None
    tabela = summary.get("sidraTabela")
    if not tabela or tabela == "all":
        return None
    return str(tabela)


def _customs_from_summary(summary: dict | None) -> str | None:
    """The server-side customs-procedure filter (regime aduaneiro) from the FilterMenu.

    Like ``flow``, this re-queries the trade snapshot server-side (the COMTRADE mart
    carries ``customs_code``). ``'all'`` / absent → ``None`` = sum every regime (the
    total, C00-equivalent), so an unfiltered request is byte-identical to before the
    regime dimension existed. Only the COMTRADE mart carries ``customs_code``, so the
    seam threads this through the COMTRADE productTS + overview readers ONLY.
    """
    if not summary:
        return None
    customs = summary.get("customs")
    if not customs or customs == "all":
        return None
    return customs


def _market_from_summary(summary: dict | None) -> str | None:
    """The server-side tipo-de-mercado filter (consumo/processamento) from the FilterMenu.

    Like ``flow``/``customs``, this re-queries the trade snapshot server-side (the COMTRADE
    mart carries the edit-driven ``market_nature`` column). ``'all'`` / absent → ``None``
    = sum every purpose (incl. unmapped), so an unfiltered request is byte-identical to
    before the dimension existed. Only the COMTRADE mart carries market_nature, so the seam
    threads this through the COMTRADE productTS + overview readers ONLY.
    """
    if not summary:
        return None
    market = summary.get("market")
    if not market or market == "all":
        return None
    return market


# The world sentinel the FilterMenu reporter picker emits: ``reporters == "__all__"`` means
# "todos os reporters" (world total) — DISTINCT from absent (Brazil default) and from a
# specific ISO list. Kept in sync with the frontend (urlState 'ALL' ↔ summary '__all__').
_REPORTER_WORLD = "__all__"


def _country_reader_kwargs(summary: dict | None) -> dict:
    """COMTRADE reporter/partner country filters → gateway reader kwargs (COMTRADE only).

    reporter is 3-state — absent → Brazil default (the gateway's own default, so we pass
    nothing), ``"__all__"`` → world total (``pin_reporter=None``, no reporter predicate), a
    list → ``reporters`` IN-list. partner is a plain list (absent → all). Returns ONLY the
    keys that differ from the gateway defaults, so an unfiltered COMTRADE request stays
    byte-identical to before this feature.
    """
    if not summary:
        return {}
    kw: dict = {}
    reporters = summary.get("reporters")
    if reporters == _REPORTER_WORLD:
        kw["pin_reporter"] = None
    elif reporters:
        kw["reporters"] = tuple(reporters)
    partners = summary.get("partners")
    if partners:
        kw["partners"] = tuple(partners)
    return kw


# A basket that no row can match — an EMPTY basket reads as "no product filter" downstream
# and would quietly serve the whole banco, the opposite of what was asked.
_NO_CODE_SENTINEL = "__nenhum_codigo_neste_nivel__"


def _apply_levels(
    banco_id: str,
    summary: dict | None,
    codes: tuple[str, ...],
    *,
    products: pd.DataFrame | None = None,
) -> tuple[str, ...]:
    """Narrow a basket by the selected nível de industrialização.

    The level is a CURATED per-code axis living in its own SCD2 dim, not a column on any
    fact, so there is nothing to push down: it has to be resolved to codes here.
    Intersecting with the basket is what lets the two narrowings COMPOSE instead of one
    silently overriding the other.

    A helper because every basket-honouring reader needs it and only ``snapshot`` had it:
    shipped on 2026-08-29 threaded through that one path, so the map, the município cube,
    both product rankings and the three trade readers ignored the filter entirely — the
    snapshot showed 1,3 bi for commodity_pura while the map beside it showed the whole
    1.063,5 bi. Same defect as the table axis one day earlier, one axis over.

    ``products`` is the banco's product universe; callers that already fetched it pass it
    in (the reader is cached, so the others simply fetch it).
    """
    niveis = _niveis_from_summary(summary)
    if not niveis:
        return codes
    if products is None:
        products = gateway.fetch_products(banco_id)
    universo = {str(c) for c in (products["code"] if products is not None else [])}
    do_nivel = _codes_for_levels(banco_id, niveis, universo)
    codes = tuple(sorted(set(codes) & do_nivel)) if codes else tuple(sorted(do_nivel))
    return codes or (_NO_CODE_SENTINEL,)


def snapshot(banco_id: str, conv: dict, summary: dict | None = None) -> dict:
    """Return the per-banco serving snapshot for the active conventions + filters.

    Keys: products, product_ts, overview_ts, uf_data (None when no geo), quality,
    value_column, value_label. Each value is a pandas DataFrame (or None).
    """
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES:
        return {
            "products": None,
            "product_ts": None,
            "overview_ts": None,
            "uf_data": None,
            "uf_yearly": None,
            "quality": None,
            "value_column": None,
            "value_label": "",
        }

    value_col, value_label = effective_value_column(banco, conv)
    y0, y1 = _years_from_summary(summary)
    codes = _basket(summary)
    # Flow (export/import) is server-side — the trade marts are pre-aggregated over
    # flow, so it re-queries here (None = sum every flow, the historical default).
    flow = _flow_from_summary(summary)
    # Customs procedure (regime aduaneiro) is server-side too, but ONLY the COMTRADE mart
    # carries customs_code — so it is threaded through both the COMTRADE productTS and the
    # overview call below (None = sum every regime = the total).
    customs = _customs_from_summary(summary)
    # Tipo de mercado (consumo/processamento) — same server-side story, COMTRADE-only.
    market = _market_from_summary(summary)
    # Country filters (país reporter / parceiro) — server-side, COMTRADE only (COMEX has no
    # reporter/partner column). reporter is 3-state (absent=Brasil, "__all__"=mundo, list=IN);
    # partner is a list. Threaded into the productTS + overview readers below (the two series
    # the COMTRADE views actually render). Quality stays GLOBAL in v1 (not country-scoped).
    country_kw = _country_reader_kwargs(summary) if banco_id == "un_comtrade" else {}

    products = gateway.fetch_products(banco_id)
    quality = gateway.fetch_quality_by_source(source=banco_id)

    codes = _apply_levels(banco_id, summary, codes, products=products)

    if banco.id in _TRADE:
        # value_col is the currency×correction column the conventions resolve to —
        # now a REAL BRL/USD/EUR (or deflated) column the trade marts carry, so the
        # snapshot value is served IN the requested currency instead of always USD
        # (which the frontend used to cross-convert via a mock FX rate).
        # customs_code + market_nature live only on the COMTRADE mart, so the regime +
        # market filters reach the productTS + overview readers ONLY for un_comtrade
        # (COMEX has neither dimension) — productTS is the series the views actually
        # render, so it must honour the same server-side filter as the overview.
        regime_kw = {} if banco_id == "mdic_comex" else {"customs": customs, "market": market}
        product_ts = gateway.fetch_product_timeseries(
            banco_id,
            year_start=y0,
            year_end=y1,
            codes=codes,
            value_column=value_col,
            flow=flow,
            **regime_kw,
            **country_kw,
        )
        overview_fn = (
            gateway.fetch_comex_overview
            if banco_id == "mdic_comex"
            else gateway.fetch_comtrade_overview
        )
        code_kw = "ncm_codes" if banco_id == "mdic_comex" else "cmd_codes"
        overview_ts = overview_fn(
            year_start=y0,
            year_end=y1,
            value_column=value_col,
            flow=flow,
            **{code_kw: codes},
            **regime_kw,
            **country_kw,
        )
        uf_data = (
            gateway.fetch_comex_by_uf(
                year_start=y0, year_end=y1, ncm_codes=codes, value_column=value_col, flow=flow
            )
            if banco_id == "mdic_comex"
            else None
        )
        uf_yearly = (
            gateway.fetch_comex_by_uf_yearly(
                year_start=y0, year_end=y1, ncm_codes=codes, value_column=value_col, flow=flow
            )
            if banco_id == "mdic_comex"
            else None
        )
        overview_ts = overview_ts.rename(columns={"total_value_usd": "total_value"})
        if uf_data is not None:
            uf_data = uf_data.rename(columns={"total_value_usd": "total_value"})
        if uf_yearly is not None:
            uf_yearly = uf_yearly.rename(columns={"total_value_usd": "total_value"})
    else:  # PEVS-shaped (ibge_pevs, ibge_pam): production marts, BRL-native value matrix
        product_ts = gateway.fetch_product_timeseries(
            banco_id, year_start=y0, year_end=y1, codes=codes, value_column=value_col
        )
        # Only the PEVS-shaped branch carries `sidra_tabela` — of the production marts
        # only gold_pevs_production spans two tables. None (the default) sums both.
        sidra_tabela = _sidra_tabela_from_summary(summary)
        overview_ts = gateway.fetch_production_overview(
            year_start=y0,
            year_end=y1,
            product_codes=codes,
            value_column=value_col,
            source=banco_id,
            sidra_tabela=sidra_tabela,
        )
        uf_data = gateway.fetch_production_by_uf(
            year_start=y0,
            year_end=y1,
            product_codes=codes,
            value_column=value_col,
            source=banco_id,
            sidra_tabela=sidra_tabela,
        )
        uf_yearly = gateway.fetch_production_by_uf_yearly(
            year_start=y0,
            year_end=y1,
            product_codes=codes,
            value_column=value_col,
            source=banco_id,
            sidra_tabela=sidra_tabela,
        )

    return {
        "products": products,
        "product_ts": product_ts,
        "overview_ts": _with_overview_quantities(overview_ts, product_ts),
        "uf_data": uf_data,
        "uf_yearly": uf_yearly,
        "quality": quality,
        "quality_ts": gateway.fetch_quality_timeseries(banco_id),
        "quality_by_product": gateway.fetch_quality_by_product(banco_id),
        "value_column": value_col,
        "value_label": value_label,
    }


def _with_overview_quantities(overview_ts: pd.DataFrame, product_ts: pd.DataFrame) -> pd.DataFrame:
    """Attach q_mass / q_vol / q_count per year, summed from the per-product series.

    ``production_overview`` sums only the value; quantities (which must never be
    summed across families) come from ``product_ts``' per-family base columns —
    ``q_mass`` (the 'massa' family), ``q_vol`` ('volume') and ``q_count``
    ('contagem', e.g. PPM herd head), already CASE-split upstream
    (sql.product_timeseries) so the families are never blended and an energy/area
    family contributes to none. Sums the base unit (t / m³ / un), NOT the native
    quantity: trade sources mix kg- and t-native codes inside the 'massa' family,
    so only the base unit is summable (for PEVS/PAM native == base, so nothing
    changes there). q_count rides along for parity with productTS/ufData so a
    consumer reading overviewTS.q_count gets the real headcount, not 0.
    """
    if overview_ts is None or overview_ts.empty:
        return overview_ts
    out = overview_ts.copy()
    _QCOLS = ("q_mass", "q_vol", "q_count")
    has_q = product_ts is not None and any(c in product_ts.columns for c in _QCOLS)
    if product_ts is None or product_ts.empty or not has_q:
        for c in _QCOLS:
            out[c] = None
        return out
    by_year = product_ts.groupby("reference_year")
    out = out.set_index("reference_year")
    # groupby.sum() skips the NaNs that the CASE columns carry for the other
    # family, so each total is purely its own family's base quantity.
    for c in _QCOLS:
        out[c] = by_year[c].sum() if c in product_ts.columns else 0.0
    return out.reset_index()


# Monthly-sourced bancos whose latest year can be PARTIAL (a year with < 12 months
# of published data). Only COMEX carries a month grain in serving; COMTRADE/PEVS/PAM
# are annual, so their latest year is always complete by construction.
_MONTHLY_SOURCES = {"mdic_comex"}


def _latest_year_completeness(banco_id: str, year_end: int | None) -> dict:
    """Whether ``year_end`` (the latest covered year) is COMPLETE, for YoY honesty.

    A monthly-sourced banco (COMEX) publishes the current year month-by-month, so its
    latest year is usually PARTIAL — a frontend YoY that compares it against a full
    prior year over-reads as a crash/boom (audit finding: COMEX 2026 ≈ 39% of 2025
    showed a spurious −41%). The frontend can't tell a year is partial from annual
    totals alone, so we expose the signal here, derived from the monthly mart:

      * ``monthsInLatestYear`` — distinct months present in ``year_end`` (None for an
        annual banco, which has no month grain).
      * ``latestYearComplete`` — True iff that year has all 12 months (always True for
        an annual banco — its latest year is complete by construction).
      * ``latestCompleteYear`` — the most recent FULLY-covered year (``year_end`` when
        complete, else ``year_end - 1``), so the frontend can anchor YoY on it.

    Annual bancos return the trivially-complete shape without any extra query.
    """
    if banco_id not in _MONTHLY_SOURCES or year_end is None:
        return {
            "months_in_latest_year": None,
            "latest_year_complete": True,
            "latest_complete_year": year_end,
        }
    df = gateway.fetch_comex_months_per_year()
    months_by_year = (
        {int(r.reference_year): int(r.n_months) for r in df.itertuples()}
        if df is not None and not df.empty
        else {}
    )
    n_months = months_by_year.get(int(year_end))
    # Fall back to the prior year only when the latest is genuinely partial AND we actually
    # observed its month count. An UNOBSERVED count (n_months is None — e.g. the monthly mart
    # lags gold_source_metadata after a partial rebuild) is treated as trivially complete:
    # we have no evidence the year is partial, so we must NOT blank/shift its YoY anchor.
    complete = n_months is None or n_months == 12
    return {
        "months_in_latest_year": n_months,
        "latest_year_complete": complete,
        "latest_complete_year": year_end if complete else (year_end - 1),
    }


def source_meta(banco_id: str) -> dict:
    """Provenance + lifecycle metadata for a banco (backs the page-hero meta).

    Gold provenance (rows, year span) + the latest-year completeness signal are
    present only for a live source that has a metadata row. The lifecycle
    maturity/note/coverage come from BigQuery (``research_inputs.banco_metadata``)
    for EVERY banco — the single source of truth — so even a planned banco with no
    Gold table reports its BQ maturity (and the frontend renders it).
    """
    meta: dict = {}
    if banco_id in _LIVE_SOURCES:
        df = gateway.fetch_source_metadata(source=banco_id)
        if df is not None and not df.empty:
            meta = df.iloc[0].to_dict()
            year_end = meta.get("year_end")
            try:
                year_end = int(year_end) if year_end is not None else None
            except (TypeError, ValueError):
                year_end = None
            meta.update(_latest_year_completeness(banco_id, year_end))
    _apply_banco_metadata(meta, banco_id)
    return meta


def banco_metadata_overrides(banco_id: str) -> dict:
    """Operator-set maturity/coverage overrides for a banco; empty dict when the
    override table is absent (none configured) or the banco has no row. Any OTHER
    error propagates — a transient BQ/permission fault must NOT silently erase a
    deliberate flip (e.g. beta→estavel) back to the registry default."""
    try:
        df = gateway.fetch_banco_metadata(banco_id)
    except NotFound:
        return {}
    if df is None or df.empty:
        return {}
    row = df.iloc[0].to_dict()
    # Keep only set columns: a NULL/NaN override means "use the registry default".
    return {
        k: v for k, v in row.items() if v is not None and not (isinstance(v, float) and pd.isna(v))
    }


def _apply_banco_metadata(meta: dict, banco_id: str) -> None:
    """Write maturity/maturity_note/maturity_date/cobertura into ``meta``.

    Maturity is sourced SOLELY from the BigQuery override table
    (``research_inputs.banco_metadata``) — the single source of truth. The Python
    registry no longer carries a per-banco maturity, so there is no fallback: a
    banco absent from the table reports ``maturity = None``. Coverage still merges
    the registry's static ``cobertura`` with any table override."""
    # Resolve WITHOUT banco_by_id's PEVS fallback: an UNKNOWN banco id must not inherit
    # PEVS's static cobertura (which would defeat serialize_source_meta's `if not meta`
    # empty-payload contract and attribute PEVS provenance to a nonexistent banco).
    banco = banco_by_id(banco_id) if banco_id in _REGISTERED_BANCO_IDS else None
    ov = banco_metadata_overrides(banco_id)
    meta["maturity"] = ov.get("maturity")
    meta["maturity_note"] = ov.get("maturity_note")
    meta["maturity_date"] = ov.get("maturity_date")
    cobertura = dict(banco.cobertura) if banco and banco.cobertura else {}
    for col, key in (
        ("cobertura_years", "years"),
        ("cobertura_atualizacao", "atualizacao"),
        ("cobertura_granularidade", "granularidade"),
    ):
        if ov.get(col):
            cobertura[key] = ov[col]
    meta["cobertura"] = cobertura or None


def product_uf_ranking(
    banco_id: str, code: str, conv: dict, summary: dict | None = None
) -> pd.DataFrame | None:
    """Per-UF value for a single product (backs the Perfil do produto ranking and
    the Rebanho per-UF map).

    Honours the UF filter. It did not before, which made both consumers show all 27
    states while the rest of the screen was narrowed to the researcher's selection —
    the same "displayed value computed over a different dataset than the filter"
    the geography audit removed everywhere else.
    """
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES or "geo" not in banco.provides:
        return None
    value_col, _ = effective_value_column(banco, conv)
    y0, y1 = _years_from_summary(summary)
    states = _states(summary)
    if banco_id == "mdic_comex":
        # Pin exports only: SG_UF_NCM is the UF *of the product*, so on import rows the
        # real direction is country→UF — summing export+import per UF would inflate and
        # mislabel the ranking (same rationale as flow_data/products_by_uf). Without this
        # the per-UF ranking would sum both flows while the rest of the screen honours
        # the selected direction — internally-inconsistent numbers in one session.
        return gateway.fetch_comex_by_uf(
            year_start=y0,
            year_end=y1,
            ncm_codes=(code,),
            uf_codes=states,
            value_column=value_col,
            flow="export",
        )
    return gateway.fetch_production_by_uf(
        year_start=y0,
        year_end=y1,
        product_codes=(code,),
        uf_codes=states,
        value_column=value_col,
        source=banco_id,
        sidra_tabela=_sidra_tabela_from_summary(summary),
    )


def geo_yearly(banco_id: str, conv: dict, summary: dict | None = None) -> pd.DataFrame | None:
    """Per-(UF, year) value/quantity for the SELECTED product basket (backs the
    geography-aware hero + map + series — Pushdown Computing at the product × UF ×
    year grain the snapshot deliberately omits).

    Like ``snapshot()``'s ``uf_yearly``, this pushes the active basket down to the
    by-UF-yearly mart query (``codes``), so the returned cube IS narrowed to the
    chosen products. The real difference is the YEAR window: ``snapshot()`` bounds
    ``uf_yearly`` to the selected period [y0, y1], while this reader leaves the
    window OPEN (full history) so the cube is cacheable across period changes — the
    client applies the period slice. The frontend then sums it over the selected
    states + window client-side, making VALOR TOTAL / quantities / the choropleth
    respect state + product + period together. ``None`` when the banco has no geo
    grain (e.g. COMTRADE: country-pair, no UF). Same value column + COMEX USD→display
    rename as the snapshot, so the cube shares the snapshot's currency basis exactly.
    """
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES or not banco or "geo" not in banco.provides:
        return None
    value_col, _ = effective_value_column(banco, conv)
    codes = _apply_levels(banco_id, summary, _basket(summary))
    # Flow (export/import) is server-side here too — without it the basket cube would
    # sum every flow while the snapshot honours the selected direction (a wrong,
    # internally-inconsistent VALOR TOTAL / map for a COMEX basket). None = every flow.
    flow = _flow_from_summary(summary)
    if banco_id == "mdic_comex":
        df = gateway.fetch_comex_by_uf_yearly(ncm_codes=codes, value_column=value_col, flow=flow)
        if df is not None:
            df = df.rename(columns={"total_value_usd": "total_value"})
        return df
    return gateway.fetch_production_by_uf_yearly(
        product_codes=codes,
        value_column=value_col,
        source=banco_id,
        sidra_tabela=_sidra_tabela_from_summary(summary),
    )


def geo_mesh() -> pd.DataFrame | None:
    """The IBGE municipal territorial mesh (dim_geo_municipio) — banco-agnostic.
    Every município → UF + grande região + BOTH sub-UF divisions (classic
    meso/micro, 2017 intermediária/imediata). Backs the SPA geo cascade's sub-UF +
    município option lists + the city→ancestry map. ``None`` if the dim isn't built."""
    try:
        return gateway.fetch_geo_municipio_mesh()
    except NotFound:
        # dim_geo_municipio not built yet (fresh/dev/PEVS-only env) → degrade to the
        # documented empty payload (serialize_geo_mesh(None) → {"municipios": []}),
        # NOT a 500 that breaks the whole geography filter menu. Mirrors
        # banco_metadata_overrides. Any other error still propagates.
        return None


def comtrade_countries() -> dict:
    """Distinct reporter + partner country universes for the COMTRADE filter pickers.

    Returns ``{"reporters": DataFrame|None, "partners": DataFrame|None}`` (rows split by the
    ``role`` column). Degrades to empty (``None`` frames) if the mart isn't built — NOT a
    500 that would break the filter menu — mirroring :func:`geo_mesh`."""
    try:
        df = gateway.fetch_comtrade_countries()
    except NotFound:
        return {"reporters": None, "partners": None}
    if df is None or df.empty:
        return {"reporters": None, "partners": None}
    return {
        "reporters": df[df["role"] == "reporter"],
        "partners": df[df["role"] == "partner"],
    }


def geo_municipio_yearly(
    banco_id: str, conv: dict, summary: dict | None = None
) -> pd.DataFrame | None:
    """Per-(município, year) cube for the SELECTED basket — the FINEST geography
    grain, backing the sub-UF + live-município cascade. The client rolls these city
    rows up to whichever level is active (meso/micro/intermediária/imediata/UF) via
    ``geo_mesh()``. Same value column as snapshot/``geo_yearly`` so the basis matches.
    ``None`` for a banco with no município grain (COMEX is UF-origin, COMTRADE
    international)."""
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES or not banco or "geo" not in banco.provides:
        return None
    value_col, _ = effective_value_column(banco, conv)
    codes = _apply_levels(banco_id, summary, _basket(summary))
    # The client resolves the active sub-UF/município selection to its município code
    # set (via the cached mesh) and sends it as cityCodes, so a narrowed selection
    # scans only those cities — never the whole ~5570-município grid.
    city_codes = tuple((summary or {}).get("cityCodes") or ())
    # The year window is the OTHER cost control, and it matters most exactly where
    # city_codes stops helping: a whole-UF municipal choropleth needs one YEAR over
    # many cities, and without this it fetched all ~39 of them. Measured on the full
    # 5570-city set: 153.634 rows / 16,9 MB / 28 s unbounded, against ~3.400 rows for
    # a single year. sqlbuild.production_by_municipio_yearly already took the bounds;
    # only this call site (and the route feeding it) never passed them through.
    y0, y1 = _years_from_summary(summary)
    try:
        return gateway.fetch_production_by_municipio_yearly(
            year_start=y0,
            year_end=y1,
            product_codes=codes,
            city_codes=city_codes,
            value_column=value_col,
            source=banco_id,
            sidra_tabela=_sidra_tabela_from_summary(summary),
        )
    except NotFound:
        # gold_<source>_production not built → documented None (serialize_municipio_yearly
        # (None) → {"municipioYearly": []}), not a 500. Other errors still propagate.
        return None


def products_by_municipio(
    banco_id: str, conv: dict, summary: dict | None = None
) -> pd.DataFrame | None:
    """Per-product ranking WITHIN the selected municípios — "o que este lugar produz".

    The território profile's counterpart to :func:`products_by_uf`. The município cube
    (:func:`geo_municipio_yearly`) sums products away, so it can plot a city's
    trajectory but never name the products behind it; this fills exactly that gap.

    Same value column as the cube so the two agree, and the same ``cityCodes`` cost
    control — no city scope means nothing to fetch, never a full grid scan. ``None``
    for a banco with no município grain (COMEX is UF-origin, COMTRADE international),
    which the serializer turns into ``{"products": []}``."""
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES or not banco or "geo" not in banco.provides:
        return None
    value_col, _ = effective_value_column(banco, conv)
    city_codes = tuple((summary or {}).get("cityCodes") or ())
    y0, y1 = _years_from_summary(summary)
    try:
        return gateway.fetch_products_by_municipio(
            year_start=y0,
            year_end=y1,
            product_codes=_apply_levels(banco_id, summary, _basket(summary)),
            city_codes=city_codes,
            value_column=value_col,
            source=banco_id,
            sidra_tabela=_sidra_tabela_from_summary(summary),
            # A metade viaja junto com a linha: madeira, lenha e carvão existem nas DUAS
            # com o mesmo nome, e quem exibe precisa distingui-las. Só o PEVS tem a coluna.
            include_sidra_tabela=True,
        )
    except NotFound:
        # gold_<source>_production not built → documented None (→ {"products": []}),
        # not a 500. Other errors still propagate.
        return None


def productivity(banco_id: str, crop: str | None, summary: dict | None = None) -> dict | None:
    """Área × rendimento for one crop (backs ViewProductivity).

    Returns ``{crops, active, active_name, rows, states}`` where ``rows`` is the
    per-(year, UF) production + harvested-area frame for the active crop, or ``None``
    when the banco lacks the ``yield`` capability (the router gates the perspective
    before this is reached). The serializer recomputes yield (= prod_kg / area_ha) and
    shapes the national series + per-UF latest-year geography.

    Honours the UF filter, which it did not before. Note this is NOT a cosmetic
    narrowing: yield is a RATIO, so restricting the rows changes the aggregate the
    serializer recomputes — the "national" trajectory becomes the selected states'
    trajectory. ``states`` is echoed back so the view can relabel it; presenting a
    subset's ratio as a national figure would be a wrong number, not a smaller one.
    """
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES or "yield" not in banco.provides:
        return None
    crops = _productivity_crops(gateway.fetch_products(banco_id))
    if not crops:
        return None
    codes = {c["code"] for c in crops}
    active = crop if (crop and crop in codes) else crops[0]["code"]
    active_name = next((c["name"] for c in crops if c["code"] == active), active)
    y0, y1 = _years_from_summary(summary)
    states = _states(summary)
    return {
        "crops": crops,
        "active": active,
        "active_name": active_name,
        "states": list(states),
        "rows": gateway.fetch_productivity(
            active, source=banco_id, year_start=y0, year_end=y1, uf_codes=states
        ),
    }


def _productivity_crops(products: pd.DataFrame | None) -> list[dict]:
    """Shape the products frame into [{code, name}] (name falls back to code)."""
    if products is None or products.empty:
        return []
    return [
        {
            "code": str(r.code),
            "name": (r.name if isinstance(r.name, str) and r.name else str(r.code)),
        }
        for r in products.itertuples()
    ]


# ── Trade adapters (flow / partner / monthly) — M2 ───────────────────────────
# The generic adapters from the contract (previewData.js). Each dispatches by
# banco to the matching gateway reader and returns the raw USD-valued frame; the
# views format/scale. None when the banco lacks the capability (the router gates
# the perspective to "Não se aplica" before these are ever called).


def flow_data(banco_id: str, summary: dict | None = None) -> dict | None:
    """Origin→destination links for the Sankey (backs Fluxos territoriais).

    COMEX: UF de origem → país parceiro. COMTRADE: país reporter → país parceiro.
    Returns {links, origin_label, dest_label} or None when the banco lacks `flow`.
    The active UF (``states``) filter narrows the COMEX origin; COMTRADE's origin is
    a reporter country (no UF column), so the UF selection does not reach its reader
    — the frontend producer surfaces that as an honest "não se aplica" note.
    """
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES or "flow" not in banco.provides:
        return None
    y0, y1 = _years_from_summary(summary)
    codes = _apply_levels(banco_id, summary, _basket(summary))
    if banco_id == "mdic_comex":
        # Exports only: SG_UF_NCM is the UF *of the product*, so on import rows
        # the real direction is country→UF — summing them into the directed
        # 'UF de origem → país parceiro' links would inflate and mislabel them.
        links = gateway.fetch_comex_flows(
            year_start=y0, year_end=y1, ncm_codes=codes, flow="export", uf_codes=_states(summary)
        )
    else:
        # The active flow / regime (customs) / tipo-de-mercado filters are server-side on
        # the COMTRADE mart and must narrow the Sankey too — otherwise it shows all-flow /
        # all-regime totals while the filter chips claim the view is scoped (the v1.10.11
        # productTS no-op class). COMEX carries none of these dimensions (its Sankey is
        # exports-only by direction; see above), so only the COMTRADE branch threads them.
        links = gateway.fetch_comtrade_flows(
            year_start=y0,
            year_end=y1,
            cmd_codes=codes,
            flow=_flow_from_summary(summary),
            customs=_customs_from_summary(summary),
            market=_market_from_summary(summary),
            **_country_reader_kwargs(summary),
        )
    dims = banco.dimensions
    return {
        "links": links,
        "origin_label": dims.get("origin", {}).get("label", "Origem"),
        "dest_label": dims.get("dest", {}).get("label", "Destino"),
    }


def partner_data(
    banco_id: str, summary: dict | None = None, rank_by: str = "value"
) -> pd.DataFrame | None:
    """Partner ranking with export/import split (backs Parceiros comerciais).

    The active UF (``states``) filter narrows the COMEX partner ranking to those
    origin UFs (``state_acronym``). COMTRADE has no origin-UF column (its origin is
    a reporter country), so the UF selection does not reach its reader — the
    frontend producer surfaces that as an honest "não se aplica" note.

    ``rank_by`` ∈ {value, weight, price} chooses the ranking dimension (Capital /
    Volume / Preço médio), applied server-side so the top-N is by that metric.
    """
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES or "partner" not in banco.provides:
        return None
    y0, y1 = _years_from_summary(summary)
    codes = _apply_levels(banco_id, summary, _basket(summary))
    # The active flow / regime (customs) / tipo-de-mercado filters must reach the ranking:
    # the server-side ORDER BY sums the metric over the returned rows, so an unfiltered
    # ranking under an "Importação" (or a regime/market) selection ranks by the wrong,
    # broader population while the chips claim it is scoped. COMEX has only ``flow`` (no
    # regime/market column); COMTRADE carries all three.
    if banco_id == "mdic_comex":
        return gateway.fetch_comex_partners(
            year_start=y0,
            year_end=y1,
            ncm_codes=codes,
            uf_codes=_states(summary),
            flow=_flow_from_summary(summary),
            rank_by=rank_by,
        )
    return gateway.fetch_comtrade_partners(
        year_start=y0,
        year_end=y1,
        cmd_codes=codes,
        flow=_flow_from_summary(summary),
        customs=_customs_from_summary(summary),
        market=_market_from_summary(summary),
        rank_by=rank_by,
        **_country_reader_kwargs(summary),
    )


def products_by_uf(
    banco_id: str, summary: dict | None = None, conv: dict | None = None
) -> pd.DataFrame | None:
    """Per-product ranking WITHIN the selected UF(s) — the "Base de dados" per-UF
    product breakdown (the inverse of the by-UF rankings, which sum products away).

    Only meaningful with a geo banco AND an explicit UF selection (``states``). With
    no UF selected it returns None so the view shows its "selecione uma UF" hint
    instead of a nationwide product ranking (which Visão geral already covers).
    Supported for IBGE PEVS (production) and MDIC COMEX (export); other geo bancos
    return None (honest not-yet-wired)."""
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES or "geo" not in banco.provides:
        return None
    states = _states(summary)
    if not states:
        return None
    value_col, _ = effective_value_column(banco, conv or {})
    y0, y1 = _years_from_summary(summary)
    codes = _apply_levels(banco_id, summary, _basket(summary))
    if banco_id == "mdic_comex":
        return gateway.fetch_products_by_uf(
            table_key="serving_comex_annual",
            code_column="ncm_code",
            name_column="ncm_description",
            year_start=y0,
            year_end=y1,
            codes=codes,
            uf_codes=states,
            value_column=value_col,
            flow="export",
        )
    if banco_id == "ibge_pevs":
        return gateway.fetch_products_by_uf(
            table_key="serving_pevs_annual",
            code_column="product_code",
            name_column="product_description",
            year_start=y0,
            year_end=y1,
            codes=codes,
            uf_codes=states,
            value_column=value_col,
            sidra_tabela=_sidra_tabela_from_summary(summary),
            # A metade viaja junto com a linha: madeira, lenha e carvão existem nas DUAS
            # com o mesmo nome, e quem exibe precisa distingui-las. Só o PEVS tem a coluna.
            include_sidra_tabela=True,
        )
    return None


def monthly_data(banco_id: str, summary: dict | None = None) -> pd.DataFrame | None:
    """Monthly seasonality value (backs Sazonalidade). COMEX only (monthly grain).

    The seasonality mart (``serving_comex_seasonality``) now KEEPS ``state_acronym``
    in its grain (P6), so the active UF (``states``) selection narrows the seasonal
    profile to one origin state; empty = national. The basket + year window apply too.
    """
    banco = banco_by_id(banco_id)
    if banco_id not in _LIVE_SOURCES or "monthly" not in banco.provides:
        return None
    y0, y1 = _years_from_summary(summary)
    codes = _apply_levels(banco_id, summary, _basket(summary))
    if banco_id == "mdic_comex":
        # The active flow filter (export/import) is server-side on the seasonality mart
        # (which keeps ``flow`` in its grain) and must narrow the seasonal profile — COMEX
        # exports are ~40x imports, so an unfiltered heatmap under an "Importação" selection
        # renders essentially the EXPORT profile while the chips say otherwise.
        return gateway.fetch_comex_seasonality(
            year_start=y0,
            year_end=y1,
            ncm_codes=codes,
            uf_codes=_states(summary),
            flow=_flow_from_summary(summary),
        )
    return None


# ── Raw table inspection (the "Dados" perspective) ─────────────────────────────


def inspectable_tables(banco_id: str) -> list[dict]:
    """Allowlisted tables a researcher may browse for a banco (the 'Dados' picker).
    Empty for a non-live banco (nothing to browse)."""
    if banco_id not in _LIVE_SOURCES:
        return []
    return gateway.inspectable_tables(banco_id)


def table_page(
    banco_id: str,
    table_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
    order_by: str | None = None,
    order_dir: str = "asc",
    filters: tuple = (),
) -> dict | None:
    """One page of raw rows for an allowlisted (banco, table) + its schema + total count.

    Returns ``{columns, df, total, table, label, grain}`` (serialize_table_page shapes it);
    ``None`` for a non-live banco. An unknown table raises ValueError → HTTP 400."""
    if banco_id not in _LIVE_SOURCES:
        return None
    schema = gateway.fetch_table_schema(banco_id, table_id)
    df = gateway.fetch_table_rows(
        banco_id,
        table_id,
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_dir=order_dir,
        filters=filters,
    )
    total = gateway.fetch_table_count(banco_id, table_id, filters)
    meta = next((t for t in gateway.inspectable_tables(banco_id) if t["id"] == table_id), {})
    return {
        "columns": schema["columns"],
        "df": df,
        "total": total,
        "table": table_id,
        "label": meta.get("label"),
        "grain": meta.get("grain"),
    }


# ── Seed reference consultation (the "Referências" perspective) ────────────────


def seed_tables() -> list[dict]:
    """The read-only seed reference tables a researcher may consult ('Referências').
    Banco-agnostic — the seeds are shared reference data, not per-banco."""
    return gateway.seed_tables()


def seed_page(
    seed_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
    order_by: str | None = None,
    order_dir: str = "asc",
    filters: tuple = (),
) -> dict:
    """One page of rows for a consultable seed + schema, total, label, description and
    editable flag (serialize_seed_page shapes it). An unknown seed id raises ValueError
    → HTTP 400 — we FAIL LOUD rather than returning a silent empty page, so a broken id
    is visible instead of looking like an empty reference table."""
    meta = next((s for s in gateway.seed_tables() if s["id"] == seed_id), None)
    if meta is None:
        raise ValueError(f"{seed_id!r} não é uma tabela de referência consultável.")
    schema = gateway.fetch_seed_schema(seed_id)
    df = gateway.fetch_seed_rows(
        seed_id,
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_dir=order_dir,
        filters=filters,
    )
    total = gateway.fetch_seed_count(seed_id, filters)
    return {
        "columns": schema["columns"],
        "df": df,
        "total": total,
        "table": seed_id,
        "label": meta["label"],
        "grain": meta["description"],
        "editable": meta["editable"],
    }


# ── Cross-source analytics + atributos — extracted to seam_cross / seam_attribute_engineering ──
# Re-exported so the public seam surface stays unchanged after the split (routes +
# tests reference seam.market_share, seam._xyear, seam.curation_worklist, …). The
# shared commodity toolkit lives in seam_base; both modules depend only on it, so
# the import graph is an acyclic base ← {cross, curation} ← seam.
from .seam_attribute_engineering import (  # noqa: E402, F401  (re-exported at module end)
    CUR_LEVELS,
    ENRICH_MARKETS,
    _code_to_agrupamento,
    _current_code_levels,
    _value_added_accumulate,
    _value_added_codes_by_level,
    _value_added_series_point,
    attribute_editor_emails,
    curation_worklist,
    flow_market_worklist,
    market_nature,
    record_code_level,
    record_flow_market,
    value_added,
)
from .seam_cross import (  # noqa: E402, F401  (re-exported at module end, intentional)
    CROSS_DISPLAY_UNIT,
    _cross_points,
    _exp_price_cross_points,
    _export_coef_by_uf,
    _export_coef_national,
    _fob_price_by_year,
    _gate_price_by_year,
    _is_mass_basis,
    _market_share_latest,
    _market_share_series,
    _metric_meta,
    _pevs_cross_points,
    _pevs_family_by_agrupamento,
    _pevs_mass_by_year,
    cross_metric_refs,
    cross_series,
    export_coefficient,
    market_share,
    price_spread,
    produto_catalog_with_family,
    trade_mirror,
)
from .seam_curation import (  # noqa: E402, F401  (catalog/Curadoria seam, re-exported)
    PRODUTO_CATALOG_RESOURCE,
    catalog_driven_bancos,
    catalog_editor_emails,
    catalog_status,
    catalog_worklist,
    group_worklist,
    orphan_worklist,
    record_catalog_entry,
    record_group,
    remove_catalog_entry,
    remove_group,
    source_codes,
)
