"""Cross-source analytics for the seam layer (M3 builders).

The comparable cross-metric series + the four crosswalk-joined analytical
perspectives (market share, export coefficient, price spread, trade mirror). They
map the SAME commodity across PEVS / NCM / HS6 via gold_produto_agrupamento, then
compose existing ``serving.gateway`` readers filtered to that commodity's codes —
pure composition, no new BFF SQL beyond the crosswalk read (in ``seam_base``).

Imports only ``seam_base`` (the shared commodity toolkit) + the gateway, never
``seam`` itself, so the import graph stays acyclic. ``seam`` re-exports the public
builders so ``seam.market_share`` etc. keep working unchanged.
"""

from __future__ import annotations

from embrapa_dashboard.config import get_settings
from embrapa_dashboard.serving import gateway
from embrapa_dashboard.serving import sql as sqlbuild
from embrapa_dashboard.serving.cache import cache

from . import seam_base
from .registries import Banco, banco_by_id
from .seam_base import _LIVE_SOURCES

CROSS_DISPLAY_UNIT = {
    "ibge_pevs:prod_value": "R$ bi",
    "ibge_pevs:prod_mass": "mil t",
    "ibge_pevs:prod_volume": "mi m³",
    "mdic_comex:exp_value": "US$ bi",
    "mdic_comex:imp_value": "US$ bi",
    "mdic_comex:exp_weight": "mil t",
    "mdic_comex:exp_price": "US$/kg",
    "un_comtrade:exp_value": "US$ bi",
    "un_comtrade:imp_value": "US$ bi",
    "un_comtrade:world_exp": "US$ bi",
}


def _metric_meta(banco: Banco, metric_id: str) -> dict | None:
    return next((m for m in banco.metrics if m["id"] == metric_id), None)


def cross_metric_refs() -> list[dict]:
    """Every (banco, metric) the picker can offer (live bancos with a real series)."""
    refs = []
    for bid in ("ibge_pevs", "mdic_comex", "un_comtrade"):
        b = banco_by_id(bid)
        for m in b.metrics:
            if f"{bid}:{m['id']}" in CROSS_DISPLAY_UNIT:
                refs.append(
                    {
                        "banco": bid,
                        "banco_short": b.short,
                        "metric": m["id"],
                        "label": m["label"],
                        "family": m["family"],
                    }
                )
    return refs


def cross_series(
    banco_id: str,
    metric_id: str,
    y0: int | None = None,
    y1: int | None = None,
    uf_codes: tuple = (),
) -> dict | None:
    """Comparable annual series for (banco, metric), in its DISPLAY_UNIT magnitude.

    ``uf_codes`` optionally narrows to origin UFs (the cross-source per-UF scoping).
    It only affects the UF-capable bancos (IBGE PEVS production, MDIC COMEX export);
    a COMTRADE metric ignores it (no UF column) — the view notes that honestly."""
    key = f"{banco_id}:{metric_id}"
    unit = CROSS_DISPLAY_UNIT.get(key)
    banco = banco_by_id(banco_id)
    metric = _metric_meta(banco, metric_id)
    if unit is None or metric is None or banco_id not in _LIVE_SOURCES:
        return None
    # A cross metric must declare its coverage; no fabricated default window.
    cov = metric.get("years")
    if not cov:
        return None
    yy0, yy1 = (y0 or cov[0]), (y1 or cov[1])
    return {
        "banco": banco_id,
        "banco_short": banco.short,
        "metric": metric_id,
        "key": key,
        "label": metric["label"],
        "unit": unit,
        "family": metric["family"],
        "coverage": cov,
        "points": _cross_points(banco_id, metric_id, yy0, yy1, unit, uf_codes),
    }


def _cross_points(
    banco_id: str, metric_id: str, y0: int, y1: int, unit: str, uf_codes: tuple = ()
) -> list[dict]:
    if banco_id == "ibge_pevs":
        return _pevs_cross_points(metric_id, y0, y1, uf_codes)
    if metric_id == "exp_price":
        return _exp_price_cross_points(y0, y1, uf_codes)
    df = gateway.fetch_cross_series(
        f"{banco_id}:{metric_id}", year_start=y0, year_end=y1, uf_codes=uf_codes
    )
    scale = 1e9 if unit.endswith("bi") else (1e6 if unit == "mil t" else 1.0)
    return [{"y": int(r.reference_year), "v": float(r.value or 0) / scale} for r in df.itertuples()]


def _pevs_cross_points(metric_id: str, y0: int, y1: int, uf_codes: tuple = ()) -> list[dict]:
    """PEVS cross points: value (÷1e9) or per-family native quantity (÷1e3 / ÷1e6)."""
    if metric_id == "prod_value":
        df = gateway.fetch_production_overview(
            year_start=y0, year_end=y1, value_column="val_real_ipca_brl", uf_codes=uf_codes
        )
        return [
            {"y": int(r.reference_year), "v": float(r.total_value or 0) / 1e9}
            for r in df.itertuples()
        ]
    fam = "massa" if metric_id == "prod_mass" else "volume"
    scale = 1e3 if metric_id == "prod_mass" else 1e6
    pts = gateway.fetch_product_timeseries(
        "ibge_pevs", year_start=y0, year_end=y1, value_column="val_real_ipca_brl", uf_codes=uf_codes
    )
    sub = pts[pts["family"] == fam].groupby("reference_year")["total_qty_native"].sum()
    return [{"y": int(y), "v": float(v) / scale} for y, v in sub.items()]


def _exp_price_cross_points(y0: int, y1: int, uf_codes: tuple = ()) -> list[dict]:
    """Derived COMEX export price: value(US$) ÷ weight(kg) = US$/kg."""
    val = gateway.fetch_cross_series(
        "mdic_comex:exp_value", year_start=y0, year_end=y1, uf_codes=uf_codes
    )
    wt = gateway.fetch_cross_series(
        "mdic_comex:exp_weight", year_start=y0, year_end=y1, uf_codes=uf_codes
    )
    wmap = {int(r.reference_year): float(r.value or 0) for r in wt.itertuples()}
    # A year with no (or zero) weight has no defined price: emit None (a gap
    # in the chart) — NEVER divide by 1, which would plot the year's raw
    # total US$ value as a 'US$/kg' point.
    return [
        {
            "y": int(r.reference_year),
            "v": (
                float(r.value or 0) / wmap[int(r.reference_year)]
                if wmap.get(int(r.reference_year))
                else None
            ),
        }
        for r in val.itertuples()
    ]


def _pevs_mass_by_year(pevs_codes: tuple, uf_codes: tuple = ()) -> dict:
    pts = gateway.fetch_product_timeseries(
        "ibge_pevs", codes=pevs_codes, value_column="val_real_ipca_brl", uf_codes=uf_codes
    )
    if pts is None or pts.empty:
        return {}
    g = pts.groupby("reference_year")["total_qty_native"].sum()
    return {int(y): float(v) / 1e3 for y, v in g.items()}  # t -> mil t


@cache.memoize()
def _pevs_family_by_agrupamento() -> dict:
    """agrupamento_id -> set of PEVS physical-unit families (massa/volume/...).

    Sourced from ``gold_pevs_production.family``. The ``'*'`` key holds every
    family present in PEVS — the basis of the "Cesta completa" / no-filter
    selection, which sums across ALL products. A mass↔weight ratio is only
    meaningful when the PEVS side is purely ``massa``; volume (m³) or mixed
    selections are not — Gold itself warns "NEVER sum qty_base across families".
    """
    s = get_settings()
    pevs = sqlbuild.table_ref(s, "bq_gold_dataset", "gold_pevs_production")
    xwalk = sqlbuild.table_ref(s, "bq_gold_dataset", "gold_produto_agrupamento")
    q = f"""
        select x.agrupamento_id as cid, p.family as family
        from `{xwalk}` x
        join `{pevs}` p on x.source = 'pevs' and p.product_code = x.code
        group by cid, family
        union all
        select '*' as cid, family from (select distinct family from `{pevs}`)
    """
    idx: dict = {}
    for r in gateway.run_query(q, []).itertuples():
        idx.setdefault(r.cid, set()).add(r.family)
    return idx


def _is_mass_basis(agrupamento_id: str | None) -> bool:
    """True iff the PEVS side of this selection is purely mass (t) — the
    precondition for comparing PEVS production against COMEX shipment weight (kg).
    Volume commodities (madeira, m³) and the mixed "Cesta completa" return False."""
    fams = _pevs_family_by_agrupamento().get(agrupamento_id or "*", set())
    return fams == {"massa"}


def produto_catalog_with_family() -> dict:
    """The commodity catalog, each commodity TAGGED with its PEVS physical-unit
    family ('massa'/'volume'/… pt-BR, or None when it has no single PEVS family).

    Drives the frontend's family-gated cross pickers: the export coefficient and
    price spread compare PEVS MASS (mil t) to COMEX shipment weight (kg), so they
    must offer ONLY pure-mass commodities — a volume (m³) or mixed-family commodity
    is not interpretable there. A commodity is single-family by construction, so a
    set of >1 (or empty) collapses to None and those views drop it from the picker.
    Composes two cached reads (catalog + family index); kept un-memoized so a warm
    instance always reflects their own TTL refresh instead of pinning a stale merge.
    """
    fams = _pevs_family_by_agrupamento()
    out: dict = {}
    for cid, c in seam_base.produto_catalog().items():
        fset = fams.get(cid, set())
        out[cid] = {**c, "family": next(iter(fset)) if len(fset) == 1 else None}
    return out


# A world-export year is "settled" once ~all UN reporters have filed. Reporters lag
# ~1-2y, so the most recent year(s) carry far fewer reporters; dividing Brazil (a
# complete declarant) by that partial world total inflates the "current" share and
# fakes an upward tail / historic peak. A year counts as complete when its reporter
# count is at least this fraction of the best-covered year — the share series and KPI
# are capped at the latest such year (the COMTRADE analog of COMEX's partial-latest-year
# guard, seam._latest_year_completeness).
_WORLD_MIN_REPORTER_COVERAGE = 0.9


def _world_latest_complete_year() -> int | None:
    """The most recent world-export year whose reporter coverage is settled (>= the
    coverage threshold of the best-covered year); None when the mart has no reporters
    (then no clamp is applied — a safe no-op degrade to the raw common window).

    Only the TRAILING partial years are trimmed: an older year with naturally lower
    coverage (the world's trade data was thinner then) still sits at/below this year and
    is kept — the clamp caps the upper bound, it does not filter the interior.
    """
    df = gateway.fetch_comtrade_reporters_per_year()
    counts = (
        {int(r.reference_year): int(r.n_reporters) for r in df.itertuples()}
        if df is not None and not df.empty
        else {}
    )
    if not counts:
        return None
    threshold = max(counts.values()) * _WORLD_MIN_REPORTER_COVERAGE
    complete = [y for y, n in counts.items() if n >= threshold]
    return max(complete) if complete else None


def _market_share_series(comex_codes: tuple, comtrade_codes: tuple) -> list[dict]:
    """Yearly BR-export ÷ world-export share (US$ bi) over the common-year window,
    capped at the latest world year with SETTLED reporter coverage — a partially
    reported recent denominator would inflate the share and fake an upward tail."""
    br = seam_base._xyear("mdic_comex:exp_value", comex_codes)
    world = seam_base._xyear("un_comtrade:world_exp", comtrade_codes)
    cap = _world_latest_complete_year()
    years = [y for y in sorted(set(br) & set(world)) if cap is None or y <= cap]
    return [
        {
            "y": y,
            "br": br[y] / 1e9,
            "world": world[y] / 1e9,
            "share": (br[y] / world[y] * 100) if world[y] else 0,
        }
        for y in years
    ]


def _market_share_latest(comex_codes: tuple, comtrade_codes: tuple) -> float | None:
    """Latest SETTLED common-year BR ÷ world share (%), or None when there is no
    overlap. Capped at the latest world year with complete reporter coverage so the
    "current share" KPI isn't inflated by a partially reported recent denominator."""
    b = seam_base._xyear("mdic_comex:exp_value", comex_codes)
    w = seam_base._xyear("un_comtrade:world_exp", comtrade_codes)
    cap = _world_latest_complete_year()
    common = [y for y in sorted(set(b) & set(w)) if cap is None or y <= cap]
    if not common:
        return None
    ly = common[-1]
    return (b[ly] / w[ly] * 100) if w[ly] else 0


def market_share(agrupamento_id: str | None) -> dict:
    """BR exports (COMEX) / world exports (COMTRADE), per year + per commodity."""
    comex_codes = seam_base._codes(agrupamento_id, "comex")
    comtrade_codes = seam_base._codes(agrupamento_id, "comtrade")
    series = []
    # Guard (mirrors market_nature): a scoped commodity missing codes for either
    # source must yield an EMPTY series — an empty tuple means "no filter" to the
    # readers, which would silently serve the ALL-commodities totals as if scoped.
    if not agrupamento_id or (comex_codes and comtrade_codes):
        series = _market_share_series(comex_codes, comtrade_codes)
    by_product = []
    for cid, c in seam_base.produto_catalog().items():
        if not (c["comex"] and c["comtrade"]):
            continue  # same guard per commodity — never the unscoped totals
        share = _market_share_latest(tuple(c["comex"]), tuple(c["comtrade"]))
        if share is not None:
            by_product.append({"code": cid, "name": c["name"], "share": share})
    by_product.sort(key=lambda x: x["share"], reverse=True)
    return {"unit": "US$ bi", "series": series, "by_product": by_product}


def _empty_export_coef(uf_codes: tuple) -> dict:
    """The no-data export-coefficient payload, echoing the active UF scope back."""
    return {
        "unit": "mil t",
        "by_uf": [],
        "national": {},
        "timeseries": [],
        "states": list(uf_codes),
    }


def export_coefficient(agrupamento_id: str | None, uf_codes: tuple = ()) -> dict:
    """Share of each UF's production (PEVS, mass) that is exported (COMEX weight).

    ``uf_codes`` narrows every side of the ratio to the selected origin UFs — the
    per-UF rows, the timeseries AND the aggregate. It did not before, so this view
    showed all 27 states (and a country-wide coefficient) while the rest of the
    session was narrowed. Both sides must be narrowed together: scoping only the
    production half would divide the selected states' output by the whole country's
    exports and silently deflate the coefficient. ``states`` is echoed back so the
    view relabels its "nacional" figures — a coefficient over a subset is a
    different ratio, not a smaller one.
    """
    if not _is_mass_basis(agrupamento_id):
        # Volume commodity (m³) or mixed basket: exported-kg ÷ produced-m³ is not a
        # share. Refuse rather than print a dimensionless-nonsense percentage.
        return {
            "unit": "mil t",
            "incompatible": True,
            "by_uf": [],
            "national": {},
            "timeseries": [],
            "states": list(uf_codes),
        }
    pevs_codes = seam_base._codes(agrupamento_id, "pevs")
    ncms = seam_base._codes(agrupamento_id, "comex")
    if agrupamento_id and not (pevs_codes and ncms):
        # Commodity has no codes for a needed source: empty payload, never the
        # unscoped ALL-commodities totals (empty codes mean "no filter").
        return _empty_export_coef(uf_codes)
    pevs_mass = _pevs_mass_by_year(pevs_codes, uf_codes)
    exp_mass = {
        y: v / 1e6 for y, v in seam_base._xyear("mdic_comex:exp_weight", ncms, uf_codes).items()
    }
    ts = sorted(set(pevs_mass) & set(exp_mass))
    timeseries = [
        {"y": y, "v": (exp_mass[y] / pevs_mass[y] * 100) if pevs_mass[y] else 0} for y in ts
    ]
    if not ts:
        return _empty_export_coef(uf_codes)
    # The by-UF/national ratios must compare the SAME window on both sides:
    # PEVS starts in 1986 but COMEX only in 1997, so unbounded cumulative sums
    # would systematically understate coefPct (and disagree with the timeseries,
    # which already intersects the two sources' years).
    by_uf = _export_coef_by_uf(pevs_codes, ncms, ts[0], ts[-1], uf_codes)
    return {
        "unit": "mil t",
        "by_uf": by_uf,
        "national": _export_coef_national(by_uf),
        "timeseries": timeseries,
        "states": list(uf_codes),
    }


def _export_coef_by_uf(
    pevs_codes: tuple, ncms: tuple, y0: int, y1: int, uf_codes: tuple = ()
) -> list[dict]:
    """Per-UF production (mil t) vs exported weight (mil t) and their coefficient.

    Both readers are window-CUMULATIVE (``latest_year_only=False``): the coefficient
    is exported-over-window ÷ produced-over-window across the SAME ``[y0, y1]``
    common-year intersection, NOT a single latest-year ratio (that is the snapshot
    choropleth's job). A single-year ratio would also reintroduce the year-window
    mismatch the cumulative sums were built to avoid.
    """
    prod = gateway.fetch_production_by_uf(
        year_start=y0,
        year_end=y1,
        value_column="qty_base",
        product_codes=pevs_codes,
        uf_codes=uf_codes,
        latest_year_only=False,
    )
    exp = gateway.fetch_comex_by_uf(
        year_start=y0,
        year_end=y1,
        ncm_codes=ncms,
        uf_codes=uf_codes,
        flow="export",
        latest_year_only=False,
    )
    exp_by_uf = {r.state_acronym: float(r.total_weight_kg or 0) / 1e6 for r in exp.itertuples()}
    prod_by_uf = {
        r.state_acronym: {
            "name": r.state_name,
            "region": r.region_abbrev,
            "production": float(r.total_value or 0) / 1e3,  # qty_base (t) -> mil t
        }
        for r in prod.itertuples()
    }
    # Union the UF universe (FINDING #3): a UF that EXPORTS but has no PEVS
    # production row (port/warehousing states shipping goods grown elsewhere) must
    # NOT be dropped — otherwise its exports vanish from the choropleth AND from the
    # national aggregate, making the national KPI disagree with the (all-UF)
    # timeseries. Export-only UFs carry production=0; the view filters production>0
    # for the ranking, so the ranking stays clean while the national totals and the
    # map become complete and consistent with the timeseries.
    by_uf = []
    for uf in sorted(set(prod_by_uf) | set(exp_by_uf)):
        pr = prod_by_uf.get(uf)
        p = pr["production"] if pr else 0.0
        e = exp_by_uf.get(uf, 0.0)
        by_uf.append(
            {
                "uf": uf,
                "name": pr["name"] if pr else uf,
                "region": pr["region"] if pr else None,
                "production": p,
                "exportV": e,
                "coefPct": (e / p * 100) if p else 0,
            }
        )
    return by_uf


def _export_coef_national(by_uf: list[dict]) -> dict:
    """Aggregate the per-UF rows into the national production/export/coefficient."""
    tp = sum(d["production"] for d in by_uf)
    te = sum(d["exportV"] for d in by_uf)
    return {"production": tp, "exportV": te, "coefPct": (te / tp * 100) if tp else 0}


def _fob_price_by_year(ncms: tuple, uf_codes: tuple = ()) -> dict:
    """FOB export unit price (US$/kg) = COMEX value ÷ weight, per common year."""
    val = seam_base._xyear("mdic_comex:exp_value", ncms, uf_codes)
    wt = seam_base._xyear("mdic_comex:exp_weight", ncms, uf_codes)
    return {y: (val[y] / wt[y]) for y in (set(val) & set(wt)) if wt[y]}


def _gate_price_by_year(pevs_codes: tuple, uf_codes: tuple = ()) -> dict:
    """Farm-gate implied price (US$/kg) = PEVS value ÷ (quantity × 1000), per year."""
    pts = gateway.fetch_product_timeseries(
        "ibge_pevs", codes=pevs_codes, value_column="val_yearfx_usd", uf_codes=uf_codes
    )
    if pts is None or pts.empty:
        return {}
    g = pts.groupby("reference_year").agg(v=("total_value", "sum"), q=("total_qty_native", "sum"))
    return {int(y): (row.v / (row.q * 1000)) if row.q else 0 for y, row in g.iterrows()}


def price_spread(agrupamento_id: str | None, uf_codes: tuple = ()) -> dict:
    """Farm-gate implied price (PEVS, US$/kg) vs FOB export price (COMEX, US$/kg).

    ``uf_codes`` optionally narrows BOTH sides to the same origin UF(s) — the
    porteira-vs-FOB spread for a single state (cross-source per-UF scoping)."""
    if not _is_mass_basis(agrupamento_id):
        # Gate price = PEVS value ÷ PEVS quantity; for a volume commodity that is
        # US$/m³, not the US$/kg the FOB price uses — markup/spread would be invalid.
        return {"unit": "US$/kg", "incompatible": True, "series": []}
    ncms = seam_base._codes(agrupamento_id, "comex")
    if agrupamento_id and not ncms:
        # No NCM codes for this commodity: empty payload, never the unscoped
        # ALL-commodities FOB price (empty codes mean "no filter" to the reader).
        return {"unit": "US$/kg", "series": []}
    fob = _fob_price_by_year(ncms, uf_codes)
    gate = _gate_price_by_year(seam_base._codes(agrupamento_id, "pevs"), uf_codes)
    series = [
        {
            "y": y,
            "fob": fob[y],
            "gate": gate[y],
            "spread": fob[y] - gate[y],
            "markup": (fob[y] / gate[y]) if gate[y] else 0,
        }
        for y in sorted(set(fob) & set(gate))
    ]
    return {"unit": "US$/kg", "series": series}


def trade_mirror(agrupamento_id: str | None) -> dict:
    """The same BR exports seen by MDIC (COMEX) vs UN Comtrade (reporter = Brazil)."""
    comex_codes = seam_base._codes(agrupamento_id, "comex")
    comtrade_codes = seam_base._codes(agrupamento_id, "comtrade")
    if agrupamento_id and not (comex_codes and comtrade_codes):
        # Missing codes for one side: empty payload, never a "mirror" of the
        # unscoped ALL-commodities totals (empty codes mean "no filter").
        return {"unit": "US$ bi", "series": [], "discrepancy": []}
    mdic = {y: v / 1e9 for y, v in seam_base._xyear("mdic_comex:exp_value", comex_codes).items()}
    comtrade = {
        y: v / 1e9 for y, v in seam_base._xyear("un_comtrade:exp_value", comtrade_codes).items()
    }
    # Third line: every OTHER country's declaration of what it imported FROM Brazil
    # (partner = Brazil on import rows) — the mirror view's "Reportado pelos parceiros".
    partners = {
        y: v / 1e9 for y, v in seam_base._xyear("un_comtrade:partner_exp", comtrade_codes).items()
    }
    years = sorted(set(mdic) & set(comtrade))
    series = [
        {"y": y, "mdic": mdic[y], "comtrade": comtrade[y], "partners": partners.get(y)}
        for y in years
    ]
    discrepancy = [
        {
            "y": d["y"],
            "v": abs(d["mdic"] - d["comtrade"]) / (((d["mdic"] + d["comtrade"]) / 2) or 1) * 100,
        }
        for d in series
    ]
    return {"unit": "US$ bi", "series": series, "discrepancy": discrepancy}
