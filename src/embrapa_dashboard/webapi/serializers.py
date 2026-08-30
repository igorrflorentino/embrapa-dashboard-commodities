"""seam output → contracts.js JSON shapes.

Pure functions (no I/O, no Flask) so they unit-test in isolation. Each turns a
``seam`` result (pandas DataFrames for the snapshot; plain dicts for the cross
producers) into the exact shape the reused React views consume — see
``PLANS/react_migration_contract_map.md`` §2 for the field-by-field mapping and
the magnitude rules (productTS.v in millions, overviewTS.v in billions, mass
quantity in mil t, volume in mi m³).

What is NOT done here (by design — these are client-side registries the views
already own, joining them server-side would duplicate + drift): UF tile coords
``col``/``row``, quality-flag ``label``/``color``, ``bancoMeta``/``metricMeta``.
The JS data layer decorates the rows we emit (keyed by ``uf`` / flag ``id``).
"""

from __future__ import annotations

import math
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from embrapa_dashboard import __version__ as _APP_VERSION
from embrapa_dashboard import release

from . import format as fmt

# Sentinel so a genuine "no release date" (None) is cached instead of re-read forever.
_UNRESOLVED = object()
_APP_RELEASE_LABEL: str | None | object = _UNRESOLVED

# Gold timestamps are UTC; the dashboard provenance stamp is displayed in
# Brasília time (e.g. "28 mai 2026 · 04:30 BRT").
_SAO_PAULO = ZoneInfo("America/Sao_Paulo")

# Gold/PEVS physical-unit family is pt-BR ('massa'); the views key on the
# English 'mass' (dataFilters.js: `pt.family === 'mass'`). Map at the boundary.
# 'contagem' (head/eggs — PPM livestock) → 'count': without it the herd had no
# JS-side family and rendered no quantity.
_FAMILY_JS = {"massa": "mass", "volume": "volume", "contagem": "count"}

# data_quality_flag id → the qualityTs contract key (contracts.js qualityTs).
# These are the REAL Gold flags emitted by macros/data_quality_flag.sql
# (OK/MISSING_VALUE/MISSING_QUANTITY/INCOMPLETE for PEVS/PAM/COMTRADE) plus the
# COMEX-only MISSING_WEIGHT (gold_comex_flows.sql inline CASE). The earlier
# ESTIMATED/OUTLIER/BOUNDARY_HISTORIC keys were the prototype's synthetic
# taxonomy — Gold never emits them, so they silently dropped INCOMPLETE and
# (for COMEX) MISSING_WEIGHT out of the quality charts.
_FLAG_KEY = {
    "OK": "ok",
    "MISSING_VALUE": "missing_value",
    "MISSING_QUANTITY": "missing_quantity",
    "MISSING_WEIGHT": "missing_weight",
    "INCOMPLETE": "incomplete",
    # Q1 outlier/problemático tiers (emitted only when enable_quality_outliers is on).
    "OUTLIER_QUANTITY": "outlier_quantity",
    "PROBLEMATIC_QUANTITY": "problematic_quantity",
    "OUTLIER_VALUE": "outlier_value",
    "PROBLEMATIC_VALUE": "problematic_value",
    # Reserved for a FUTURE auto-fill pipeline (accepted-but-absent, 0 today — like the
    # outlier tiers when the var is off). No Gold CASE emits them yet.
    "INFERRED_QUANTITY": "inferred_quantity",
    "INFERRED_VALUE": "inferred_value",
    # PAM-only: planted < harvested area (a SIDRA source error). Emitted by gold_pam_production.
    "AREA_INCONSISTENT": "area_inconsistent",
}

# data_quality_flag id → pt-BR display label (the end user reads the donut/legend).
# The frontend's QUALITY_FLAGS registry lacks INCOMPLETE/MISSING_WEIGHT, so without
# a server-supplied label decorate.js falls back to the raw English id — a pt-BR
# rule violation. Emitting the label here keeps the chart Portuguese end-to-end.
# Labels follow the "Contrato de Dados" spreadsheet's "Qualidade dos dados" wording:
# the healthy row is "Normais" (not the English "OK"); the missing-value rung names
# the financeiro vs quantidade split. Keep in sync with frontend data.js QUALITY_FLAGS.
_FLAG_LABEL_PT = {
    "OK": "Normais",
    "MISSING_VALUE": "Valor financeiro ausente",
    "MISSING_QUANTITY": "Quantidade ausente",
    "MISSING_WEIGHT": "Peso ausente",
    "INCOMPLETE": "Incompleto",
    # Q1 outlier (atípico = válido) vs problemático (provável erro de digitação/inserção).
    "OUTLIER_QUANTITY": "Quantidade atípica (válida)",
    "PROBLEMATIC_QUANTITY": "Quantidade problemática (provável erro)",
    "OUTLIER_VALUE": "Valor atípico (válido)",
    "PROBLEMATIC_VALUE": "Valor problemático (provável erro)",
    # Reserved tier for a future auto-fill pipeline (0 today).
    "INFERRED_QUANTITY": "Quantidade inferida",
    "INFERRED_VALUE": "Valor financeiro inferido",
    # PAM-only: área plantada < área colhida (erro de fonte do SIDRA, agronomicamente impossível).
    "AREA_INCONSISTENT": "Área inconsistente (plantada < colhida)",
}


def _fam(value: Any) -> str:
    return _FAMILY_JS.get(value, value if isinstance(value, str) else "")


def _num(value: Any) -> float:
    """Coerce to a JSON-safe float (NaN/None → 0.0)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def _empty(df: pd.DataFrame | None) -> bool:
    return df is None or getattr(df, "empty", True)


# ── snapshot ──────────────────────────────────────────────────────────────────


def serialize_snapshot(snap: dict) -> dict:
    """seam.snapshot() (DataFrames) → BancoSnapshot (contracts.js:45)."""
    return {
        "products": _products(snap.get("products")),
        "productTS": _product_ts(snap.get("product_ts")),
        "overviewTS": _overview_ts(snap.get("overview_ts")),
        "ufData": _uf_data(snap.get("uf_data")),
        "ufYearly": _uf_yearly(snap.get("uf_yearly")),
        "quality": _quality(snap.get("quality")),
        "qualityTs": _quality_ts(snap.get("quality_ts")),
        "qualityByProduct": _quality_by_product(snap.get("quality_by_product")),
        "valueLabel": snap.get("value_label", ""),
        "preview": False,
        "_synthetic": False,
    }


def _int_or_none(value: Any) -> int | None:
    """Coerce a numpy/pandas number to a JSON-safe int, or None for NaN/missing."""
    try:
        if value is None:
            return None
        f = float(value)
        return None if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return None


def _refresh_label(ts: Any) -> str | None:
    """UTC Gold timestamp → 'DD mês YYYY · HH:MM BRT' (Brasília, pt-BR), or None."""
    if ts is None:
        return None
    try:
        t = pd.Timestamp(ts)
    except (TypeError, ValueError):
        return None
    if t is None or pd.isna(t):
        return None
    t = (t.tz_localize("UTC") if t.tzinfo is None else t).tz_convert(_SAO_PAULO)
    month = fmt.MONTH_ABBR_PT[t.month - 1].lower()
    return f"{t.day:02d} {month} {t.year} · {t.hour:02d}:{t.minute:02d} BRT"


def _release_date_label() -> str | None:
    """The running version's release date as 'DD mês YYYY' (pt-BR), or None.

    Resolved once per process: it is a build-time constant, and the CHANGELOG is not
    re-read on every provenance request.
    """
    global _APP_RELEASE_LABEL
    if _APP_RELEASE_LABEL is _UNRESOLVED:
        d = release.release_date()
        _APP_RELEASE_LABEL = (
            None if d is None else f"{d.day:02d} {fmt.MONTH_ABBR_PT[d.month - 1].lower()} {d.year}"
        )
    return _APP_RELEASE_LABEL


def serialize_source_meta(meta: dict | None) -> dict:
    """gold_source_metadata row → page-hero provenance JSON.

    Converts the raw pandas/numpy row (numpy.int64 counters, a UTC Timestamp) into
    native JSON types the frontend can render directly: real coverage (yearStart/
    yearEnd), counters (totalRows/productsTotal/ufsTotal), the Gold table name, and
    the last-refresh stamp both as an ISO string (for staleness math) and a pt-BR
    Brasília label (for display). Empty dict when the source has no Gold row yet.
    """
    if not meta:
        return {}
    last = meta.get("last_refresh")
    iso = None
    if last is not None:
        try:
            ts = pd.Timestamp(last)
            iso = None if pd.isna(ts) else ts.isoformat()
        except (TypeError, ValueError):
            iso = None
    return {
        "source": meta.get("source"),
        "table": meta.get("gold_table"),
        "cadence": meta.get("cadence"),
        "yearStart": _int_or_none(meta.get("year_start")),
        "yearEnd": _int_or_none(meta.get("year_end")),
        "totalRows": _int_or_none(meta.get("total_rows")),
        "productsTotal": _int_or_none(meta.get("products_total")),
        "ufsTotal": _int_or_none(meta.get("ufs_total")),
        "lastRefresh": iso,
        "lastRefreshLabel": _refresh_label(last),
        # Latest-year completeness (FINDING #3): lets the frontend compute an honest
        # YoY for monthly-sourced bancos whose latest year is still partial — instead
        # of reading a partial-2026-vs-full-2025 drop as a real crash. For annual
        # bancos latestYearComplete is True and monthsInLatestYear is None.
        "monthsInLatestYear": _int_or_none(meta.get("months_in_latest_year")),
        "latestYearComplete": bool(meta.get("latest_year_complete", True)),
        "latestCompleteYear": _int_or_none(meta.get("latest_complete_year")),
        # Operator-editable lifecycle metadata (research_inputs.banco_metadata merged
        # over the registry default by seam._apply_banco_metadata). Lets a Console
        # flip — beta→estavel, a new note/date, updated coverage — reach the SPA's
        # MaturityTag/MaturityBanner/coverage WITHOUT a rebuild+redeploy.
        "maturity": meta.get("maturity"),
        "maturityNote": meta.get("maturity_note"),
        "maturityDate": meta.get("maturity_date"),
        "cobertura": meta.get("cobertura"),
        # The running dashboard version — the SINGLE SOURCE OF TRUTH is the installed
        # package version (pyproject.toml → importlib.metadata), the same value the release
        # tag bumps. Surfaced here so the SPA shows the REAL release (and tags feedback with
        # it) instead of a frontend package.json that drifts. Global, not per-banco, but rides
        # along the provenance payload the hero/Sobre already load.
        "appVersion": _APP_VERSION,
        # When that version shipped, from CHANGELOG.md (see embrapa_dashboard.release).
        # Sobre renders it right beside the version, so it must be the VERSION's date —
        # it previously sat next to the PEVS Gold refresh stamp under a lone "Versão"
        # label, which read as "this version is from 01 ago" while the build was current.
        # None when the CHANGELOG has no section for it; the SPA then shows the version
        # alone rather than inventing a date.
        "appReleaseDate": _release_date_label(),
    }


def _quality_by_product(df: pd.DataFrame | None, top: int = 20) -> list[dict]:
    """product×flag counts → [{code, name, OK, MISSING_VALUE, …}] per-product flag
    shares (fractions 0-1; FlagBars keys on the flag *ids*). Top-N by row volume so
    a 200-NCM banco stays a readable chart."""
    if _empty(df):
        return []
    by_code: dict[str, dict] = {}
    for r in df.itertuples():
        code = str(r.code)
        slot = by_code.setdefault(code, {"name": None, "counts": {}})
        slot["name"] = r.name if (isinstance(r.name, str) and r.name) else code
        slot["counts"][r.data_quality_flag] = slot["counts"].get(r.data_quality_flag, 0.0) + _num(
            r.n
        )
    ranked = sorted(by_code.items(), key=lambda kv: sum(kv[1]["counts"].values()), reverse=True)
    out = []
    for code, slot in ranked[:top]:
        total = sum(slot["counts"].values()) or 1.0
        row = {"code": code, "name": slot["name"]}
        for flag in _FLAG_KEY:  # the real Gold flag ids — absent flags read 0
            row[flag] = slot["counts"].get(flag, 0.0) / total
        out.append(row)
    return out


def _quality_ts(df: pd.DataFrame | None) -> list[dict]:
    """year×flag counts → [{y, ok, missing_value, …, incomplete}] as per-year shares
    (fractions 0-1; the views ×100 for %). Keys are the REAL Gold flags; any flag
    not in _FLAG_KEY still counts toward `total` (so an unexpected new flag lowers
    the known shares rather than vanishing silently). Flags absent in a year read 0."""
    if _empty(df):
        return []
    by_year: dict[int, dict[str, float]] = {}
    for r in df.itertuples():
        slot = by_year.setdefault(int(r.reference_year), {})
        slot[r.data_quality_flag] = slot.get(r.data_quality_flag, 0.0) + _num(r.n)
    out = []
    for y in sorted(by_year):
        flags = by_year[y]
        total = sum(flags.values()) or 1.0
        row: dict[str, Any] = {"y": y}
        for key in _FLAG_KEY.values():  # every contract key reads 0 if absent
            row[key] = 0.0
        for flag, n in flags.items():
            key = _FLAG_KEY.get(flag)
            if key:
                row[key] = n / total
        out.append(row)
    return out


def _products(df: pd.DataFrame | None) -> list[dict]:
    if _empty(df):
        return []
    out: list[dict] = []
    for r in df.itertuples():
        row = {
            "code": str(r.code),
            # a few COMEX codes have no description → fall back to the code
            "name": r.name if (isinstance(r.name, str) and r.name) else str(r.code),
            "unit": r.unit,
            "family": _fam(r.family),
        }
        # measure_kind (stock | flow) rides along ONLY for the livestock survey (the
        # gateway selects it just for PPM). It lets the UI separate the herd (stock,
        # value-less) from animal-product flows (eggs/milk) that share 'contagem'.
        # A TABELA SIDRA — só nos bancos multi-tabela (o gateway a seleciona para eles).
        # Sem ela a tela não distingue dois produtos que dividem o nome, e o Donut de
        # "Participação por produto" mostrava duas fatias rotuladas "Madeira em tora".
        st = getattr(r, "sidra_tabela", None)
        if isinstance(st, str) and st:
            row["sidra_tabela"] = st
        mk = getattr(r, "measure_kind", None)
        if isinstance(mk, str) and mk:
            row["measure_kind"] = mk
        out.append(row)
    return out


def _product_ts(df: pd.DataFrame | None) -> dict:
    """GROUP BY code → {code: [{y, v(mi), q(mil t | mi m³ | mi un | None), family}]}.

    ``q`` is the display quantity in the code's family base unit (massa → mil t,
    volume → mi m³, contagem → mi un, i.e. millions of head/eggs), read from the
    per-family ``q_mass`` / ``q_vol`` / ``q_count`` CASE columns so the families are
    never blended. ``contagem`` carries the livestock HEADCOUNT (PPM's herd, the
    defining content of that banco) and egg counts — without its own track it would
    be invisible in every quantity chart. energia/area/desconhecida still have no
    display convention → ``q`` is None (absent rather than mis-scaled).
    """
    if _empty(df):
        return {}
    out: dict[str, list[dict]] = {}
    for r in df.itertuples():
        fam_raw = getattr(r, "family", "")
        if fam_raw == "massa":
            q: float | None = _num(getattr(r, "q_mass", 0)) / 1e3  # t → mil t
        elif fam_raw == "volume":
            q = _num(getattr(r, "q_vol", 0)) / 1e6  # m³ → mi m³
        elif fam_raw == "contagem":
            q = _num(getattr(r, "q_count", 0)) / 1e6  # un → mi un (head / eggs)
        else:
            q = None  # energia/area/desconhecida: no display scale
        out.setdefault(str(r.code), []).append(
            {
                "y": int(r.reference_year),
                "v": _num(r.total_value) / 1e6,
                "q": q,
                "family": _fam(fam_raw),
            }
        )
    return out


def _overview_ts(df: pd.DataFrame | None) -> list[dict]:
    if _empty(df):
        return []
    out = []
    for r in df.itertuples():
        q_mass = _num(getattr(r, "q_mass", 0)) / 1e3
        q_vol = _num(getattr(r, "q_vol", 0)) / 1e6
        q_count = _num(getattr(r, "q_count", 0)) / 1e6  # un → mi un (head / eggs)
        out.append(
            {
                "y": int(r.reference_year),
                "v": _num(r.total_value) / 1e9,
                "q": q_mass,
                "q_mass": q_mass,
                "q_vol": q_vol,
                "q_count": q_count,
            }
        )
    return out


def _uf_data(df: pd.DataFrame | None) -> list[dict]:
    # value (the choropleth measure) → millions; q_mass/q_vol come from the by-UF
    # reader's per-family qty_base sums (massa → t, volume → m³), scaled the same
    # way as overviewTS: q_mass ÷1e3 → mil t, q_vol ÷1e6 → mi m³. col/row added
    # client-side from UF_DATA.
    if _empty(df):
        return []
    return [
        {
            "uf": r.state_acronym,
            "name": r.state_name,
            "region": r.region_abbrev,
            "value": _num(r.total_value) / 1e6,
            "q_mass": _num(getattr(r, "q_mass", 0)) / 1e3,
            "q_vol": _num(getattr(r, "q_vol", 0)) / 1e6,
            "q_count": _num(getattr(r, "q_count", 0)) / 1e6,  # un → mi un (head / eggs)
            # True for a real Brazilian UF, False for a COMEX special trade pseudo-code
            # (EX/ND/ZN/MN/RE…). These have no state_name from the UF lookup (same
            # discriminator gold_source_metadata.ufs_total uses), so the frontend can
            # count real UFs (27) instead of inflating the tally with pseudo-codes
            # (FINDING #4). PEVS/PAM rows are always real.
            "real": _is_real_uf(r),
        }
        for r in df.itertuples()
    ]


def _is_real_uf(row: Any) -> bool:
    """A real Brazilian UF iff it has a non-empty ``state_name`` (COMEX pseudo-codes
    like EX/ND/ZN have none — the same rule gold_source_metadata.ufs_total applies)."""
    name = getattr(row, "state_name", None)
    return isinstance(name, str) and bool(name.strip())


def _uf_yearly(df: pd.DataFrame | None) -> list[dict]:
    # Per-(UF, year) rows backing the geography 'ano × UF' heatmap — REAL Gold
    # history, never the national curve rescaled per UF. Same per-family scaling as
    # ufData/overviewTS: value ÷1e6 → millions, q_mass ÷1e3 → mil t, q_vol ÷1e6 →
    # mi m³. ``name``/``region`` ride along so the heatmap can label each row; col/row
    # come client-side from UF_DATA (decorate.js). ~27 UFs × covered years (small).
    if _empty(df):
        return []
    return [
        {
            "year": int(r.reference_year),
            "uf": r.state_acronym,
            "name": r.state_name,
            "region": r.region_abbrev,
            "value": _num(r.total_value) / 1e6,
            "q_mass": _num(getattr(r, "q_mass", 0)) / 1e3,
            "q_vol": _num(getattr(r, "q_vol", 0)) / 1e6,
            "q_count": _num(getattr(r, "q_count", 0)) / 1e6,  # un → mi un (head / eggs)
        }
        for r in df.itertuples()
    ]


def _municipio_yearly(df: pd.DataFrame | None) -> list[dict]:
    # Per-(município, year) rows backing the sub-UF + live-município geography
    # cascade. SAME per-family scaling as _uf_yearly (value ÷1e6 → mi, q_mass ÷1e3 →
    # mil t, q_vol ÷1e6 → mi m³, q_count ÷1e6 → mi un) so the client can aggregate
    # município rows up to ANY level and stay byte-consistent with the UF cube. The
    # município's UF/região/meso/micro/intermediária/imediata are NOT carried per row
    # (that would bloat ~5570× years × products) — the client maps cityCode → ancestry
    # via /geo-mesh, served once and cached.
    if _empty(df):
        return []
    return [
        {
            "year": int(r.reference_year),
            "cityCode": str(r.city_code),
            "uf": r.state_acronym,
            "value": _num(r.total_value) / 1e6,
            "q_mass": _num(getattr(r, "q_mass", 0)) / 1e3,
            "q_vol": _num(getattr(r, "q_vol", 0)) / 1e6,
            "q_count": _num(getattr(r, "q_count", 0)) / 1e6,
        }
        for r in df.itertuples()
    ]


def serialize_municipio_yearly(df: pd.DataFrame | None) -> dict:
    """seam.geo_municipio_yearly() → { municipioYearly: [{year, cityCode, uf, value,
    q_mass, q_vol, q_count}] }.

    The basket-scoped per-(município, year) cube — the finest geography grain. The
    client joins ``cityCode`` to /geo-mesh to roll it up to the selected sub-UF level
    (meso/micro/intermediária/imediata) or down to município. Empty list when the
    banco has no município grain (COMEX/COMTRADE)."""
    return {"municipioYearly": _municipio_yearly(df)}


def serialize_geo_mesh(df: pd.DataFrame | None) -> dict:
    """seam.geo_mesh() → { municipios: [{cityCode, cityName, uf, region, meso, micro,
    intermediaria, imediata}] }, each sub-UF level an {code, name} pair.

    The static IBGE municipal mesh universe (~5570). The SPA builds the geography
    cascade's per-level option lists + the cityCode→ancestry map from this single
    cached payload. An empty {code:'', name:''} pair means the município has no
    grouping at that level (e.g. a post-classic município has no meso/micro)."""
    if _empty(df):
        return {"municipios": []}
    return {
        "municipios": [
            {
                "cityCode": str(r.city_code),
                "cityName": r.city_name,
                "uf": r.state_acronym,
                "region": r.region_abbrev,
                "meso": {"code": str(r.meso_code or ""), "name": r.meso_name or ""},
                "micro": {"code": str(r.micro_code or ""), "name": r.micro_name or ""},
                "intermediaria": {
                    "code": str(r.intermediaria_code or ""),
                    "name": r.intermediaria_name or "",
                },
                "imediata": {"code": str(r.imediata_code or ""), "name": r.imediata_name or ""},
            }
            for r in df.itertuples()
        ]
    }


def _country_list(df: pd.DataFrame | None) -> list[dict]:
    """Shape a COMTRADE country frame (role, iso, name, code) into [{code, iso, name}],
    already ORDER BY name from the mart query. ``name`` falls back to the ISO code."""
    if _empty(df):
        return []
    return [{"code": str(r.code), "iso": r.iso, "name": r.name or r.iso} for r in df.itertuples()]


def serialize_countries(payload: dict | None) -> dict:
    """seam.comtrade_countries() → { reporters: [{code, iso, name}], partners: [...] }.

    The two country universes (país reporter ~203, país parceiro ~246) backing the
    COMTRADE filter pickers. Empty lists when the mart isn't built."""
    payload = payload or {}
    return {
        "reporters": _country_list(payload.get("reporters")),
        "partners": _country_list(payload.get("partners")),
    }


def serialize_product_uf(df: pd.DataFrame | None) -> dict:
    """seam.product_uf_ranking() → { uf: [{uf, name, region, value, q_mass, q_vol, q_count}] }.

    The real per-UF total for a single product (backs ViewProductProfile's
    'Onde X é produzido' bars, which previously faked the distribution with a
    sine jitter over a synthetic affinity table). ``value`` is the reader's raw
    total_value; the per-family quantities ride along (same ÷1e3/÷1e6 scaling as
    ufData) so a VALUE-LESS stock (the livestock herd) can rank UFs by headcount
    (``q_count``) instead of an all-zero value. Rows are emitted descending by value;
    the client re-sorts by the family it displays. Empty list when df is None/empty.
    """
    if _empty(df):
        return {"uf": []}
    rows = [
        {
            "uf": r.state_acronym,
            "name": r.state_name,
            "region": r.region_abbrev,
            # PEVS/PAM expose total_value; the COMEX-by-UF reader names it
            # total_value_usd — accept either so both geo bancos serialize.
            "value": _num(getattr(r, "total_value", getattr(r, "total_value_usd", None))),
            "q_mass": _num(getattr(r, "q_mass", 0)) / 1e3,
            "q_vol": _num(getattr(r, "q_vol", 0)) / 1e6,
            "q_count": _num(getattr(r, "q_count", 0)) / 1e6,
        }
        for r in df.itertuples()
    ]
    rows.sort(key=lambda d: d["value"], reverse=True)
    return {"uf": rows}


def serialize_geo_yearly(df: pd.DataFrame | None) -> dict:
    """seam.geo_yearly() → { ufYearly: [{year, uf, name, region, value, q_mass, q_vol, q_count}] }.

    The basket-scoped per-(UF, year) cube backing the geography-aware hero/map/series.
    Reuses :func:`_uf_yearly` so the value/quantity scaling (value ÷1e6 → mi, q_mass
    ÷1e3 → mil t, q_vol ÷1e6 → mi m³, q_count ÷1e6 → mi un) is BYTE-IDENTICAL to the
    snapshot's ``ufYearly`` — the frontend treats both interchangeably (so the cube path
    must keep q_count too, or a herd's geographic concentration zeroes out). ``{ ufYearly:
    [] }`` when df is None/empty (no geo grain, or the basket matched nothing)."""
    return {"ufYearly": _uf_yearly(df)}


def serialize_productivity(payload: dict | None) -> dict | None:
    """seam.productivity() → the ViewProductivity contract (área × rendimento).

    Recomputes yield (kg/ha) as ``production_kg / harvested-area_ha`` at each grain
    (a ratio is NOT summable): the national series per year + the per-UF map for the
    LATEST year. ``prodT`` (t) and ``areaHa`` (ha) stay raw — the view scales them
    (mi t / mil ha). Returns None when the banco lacks the yield capability so the
    view renders its honest empty-state.
    """
    if not payload:
        return None
    df = payload.get("rows")
    base = {
        "preview": False,
        "crop": {"code": payload.get("active", ""), "name": payload.get("active_name", "")},
        "crops": payload.get("crops", []),
        "yieldUnit": "kg/ha",
        "areaUnit": "ha",
        "series": [],
        # ProductivityData.national is {yieldKgHa, areaHa, prodT, yieldCagr} — the
        # latest-year totals + the CAGR over the covered span. "national" is the key's
        # historical name; with `states` non-empty these are the SELECTED states'
        # figures, and the view relabels them from that field rather than keeping the
        # word "nacional" over a subset (yield is a ratio — a subset's is a different
        # number, not a smaller one).
        "national": {"yieldKgHa": 0.0, "areaHa": 0.0, "prodT": 0.0, "yieldCagr": 0.0},
        "states": payload.get("states", []),
        "byUF": [],
    }
    if _empty(df):
        return base

    def _yield(prod_t: Any, area_ha: Any) -> float:
        area = _num(area_ha)
        return (_num(prod_t) * 1000.0) / area if area > 0 else 0.0

    # National series: production + harvested area summed per year (additive across
    # UFs); yield recomputed from the two totals, never averaged.
    nat = df.groupby("reference_year")[["production_t", "area_harvested_ha"]].sum().reset_index()
    base["series"] = [
        {
            "y": int(r.reference_year),
            "yieldKgHa": _yield(r.production_t, r.area_harvested_ha),
            "areaHa": _num(r.area_harvested_ha),
            "prodT": _num(r.production_t),
        }
        for r in nat.itertuples()
    ]

    # National totals = the latest year's summed production + area (matches the
    # latest-year grain of byUF); yield recomputed from those totals.
    series = base["series"]
    if series:
        latest_nat = series[-1]
        base["national"].update(
            yieldKgHa=latest_nat["yieldKgHa"],
            areaHa=latest_nat["areaHa"],
            prodT=latest_nat["prodT"],
        )

    # Yield CAGR over the covered span (first → last national yield).
    if len(series) >= 2:
        first, last = series[0]["yieldKgHa"], series[-1]["yieldKgHa"]
        span = series[-1]["y"] - series[0]["y"]
        if first > 0 and span > 0:
            base["national"]["yieldCagr"] = ((last / first) ** (1.0 / span) - 1.0) * 100.0

    # Per-UF productivity for the LATEST year (the map + ranking grain). Carry
    # areaHa/prodT too (ProductivityData.byUF declares them) so the view/export can
    # read them — yield alone is not summable, but area and production are.
    latest_year = int(df["reference_year"].max())
    latest = df[df["reference_year"] == latest_year]
    base["byUF"] = [
        {
            "uf": r.state_acronym,
            "name": r.state_name,
            "region": r.region_abbrev,
            "yieldKgHa": _yield(r.production_t, r.area_harvested_ha),
            "areaHa": _num(r.area_harvested_ha),
            "prodT": _num(r.production_t),
        }
        for r in latest.itertuples()
    ]
    return base


def _quality(df: pd.DataFrame | None) -> list[dict]:
    # color is added client-side from QUALITY_FLAGS; `label` is emitted here in
    # pt-BR because the frontend taxonomy lacks INCOMPLETE/MISSING_WEIGHT and would
    # otherwise fall back to the raw English id (a pt-BR rule violation). `share`
    # is the mart's 0-1 fraction (fmtPct ×100 expects that).
    if _empty(df):
        return []
    return [
        {
            "id": r.data_quality_flag,
            "label": _FLAG_LABEL_PT.get(r.data_quality_flag, r.data_quality_flag),
            "count": int(_num(r.n_rows)),
            "share": _num(r.share),
        }
        for r in df.itertuples()
    ]


# ── cross producers (already near-shape — snake→camel + preview flag) ──────────


def serialize_cross_series(d: dict | None) -> dict | None:
    """seam.cross_series() → SeriesResult. points[].v already in display
    magnitude (do not rescale). bancoMeta/metricMeta joined client-side."""
    if d is None:
        return None
    return {**d, "preview": False}


def serialize_market_share(d: dict) -> dict:
    return {
        "preview": False,
        "unit": d.get("unit", ""),
        "series": d.get("series", []),
        "byProduct": d.get("by_product", []),
    }


def serialize_export_coef(d: dict) -> dict:
    out = {
        "preview": False,
        "unit": d.get("unit", ""),
        "byUf": d.get("by_uf", []),
        # "national" is the key's historical name; with `states` non-empty these are
        # the SELECTED states' figures, and the view relabels from that field.
        "national": d.get("national", {}),
        "timeseries": d.get("timeseries", []),
        "states": d.get("states", []),
    }
    if d.get("incompatible"):
        out["incompatible"] = True
    return out


def serialize_price_spread(d: dict) -> dict:
    out = {"preview": False, "unit": d.get("unit", ""), "series": d.get("series", [])}
    if d.get("incompatible"):
        out["incompatible"] = True
    return out


def serialize_trade_mirror(d: dict) -> dict:
    return {
        "preview": False,
        "unit": d.get("unit", ""),
        "series": d.get("series", []),
        "discrepancy": d.get("discrepancy", []),
    }


# ── trade adapters (flow / partner / monthly) — USD-valued, values → millions ──


def serialize_flow(d: dict | None, max_links: int = 40) -> dict:
    """seam.flow_data() → FlowData. Builds the Sankey nodes/links from the
    origin→dest link frame (top ``max_links`` by value for a readable diagram)."""
    shell = {"preview": False, "unit": "US$", "originLabel": "Origem", "destLabel": "Destino"}
    if d is None:
        return {**shell, "nodes": [], "links": []}
    links_df = d.get("links")
    origin_label = d.get("origin_label", "Origem")
    dest_label = d.get("dest_label", "Destino")
    labels = {"originLabel": origin_label, "destLabel": dest_label}
    if _empty(links_df):
        return {**shell, **labels, "nodes": [], "links": []}
    df = links_df.head(max_links)
    origins: dict[str, str] = {}
    dests: dict[str, str] = {}
    nodes: list[dict] = []
    links: list[dict] = []
    for r in df.itertuples():
        oc, dc = str(r.origin_code), str(r.dest_code)
        if oc not in origins:
            origins[oc] = f"o{len(origins)}"
            nodes.append({"id": origins[oc], "label": r.origin_name, "side": "origin", "value": 0})
        if dc not in dests:
            dests[dc] = f"d{len(dests)}"
            nodes.append({"id": dests[dc], "label": r.dest_name, "side": "dest", "value": 0.0})
        v = _num(r.value_usd) / 1e6  # → US$ mi
        links.append({"source": origins[oc], "target": dests[dc], "value": v})
    by_id = {n["id"]: n for n in nodes}
    for link in links:
        by_id[link["source"]]["value"] += link["value"]
        by_id[link["target"]]["value"] += link["value"]
    return {
        "preview": False,
        "unit": "US$",
        "originLabel": origin_label,
        "destLabel": dest_label,
        "nodes": nodes,
        "links": links,
    }


def serialize_partner(df: pd.DataFrame | None, max_rows: int = 30) -> dict:
    """seam.partner_data() → PartnerData. Partner ranking with exp/imp split.

    Each partner carries three comparable measures so the view can rank/display by
    Capital / Volume / Preço médio without a re-fetch when the row set is unchanged:
    ``value``/``exp``/``imp`` in US$ mi, ``weight`` in mil t (net weight), and
    ``price`` in US$/kg (value ÷ net weight; ``None`` when the partner has no weight,
    so the view shows "—" instead of a divide-by-zero artefact). The row ORDER is
    the server-side ranking dimension (seam ``rank_by``), so ``df.head`` is the
    correct top-N for whichever metric was requested."""
    if _empty(df):
        return {"preview": False, "flowLabel": "Parceiro", "unit": "US$", "partners": []}
    partners = []
    for r in df.head(max_rows).itertuples():
        price = getattr(r, "price_usd_per_kg", None)
        partners.append(
            {
                "name": r.partner_name,
                "exp": _num(r.exp_value_usd) / 1e6,
                "imp": _num(r.imp_value_usd) / 1e6,
                "value": _num(r.value_usd) / 1e6,
                "weight": _num(getattr(r, "total_weight_kg", 0)) / 1e6,  # kg → mil t
                "price": None if price is None or pd.isna(price) else _num(price),  # US$/kg
            }
        )
    return {"preview": False, "flowLabel": "Parceiro", "unit": "US$", "partners": partners}


def serialize_products_by_uf(df: pd.DataFrame | None, max_rows: int = 100) -> dict:
    """seam.products_by_uf() → { products: [{code,name,value,q_mass,q_vol,q_count}] }.

    value in currency mi (the deflated column the conventions resolved), q_mass in
    mil t, q_vol in mi m³, q_count in mi un (livestock head/eggs) — the SAME magnitudes
    the snapshot's productTS/ufData use, so the view's UnitFamily formatters apply
    unchanged. Carrying q_count lets the 'Produtos do estado' ranking surface a herd by
    headcount (a value-less stock would otherwise rank all-zero). Rows arrive
    value-ranked; the view re-sorts client-side by the chosen metric over the (small)
    product set."""
    if _empty(df):
        return {"products": []}
    products = [
        {
            "code": str(r.product_code),
            "name": r.product_name,
            # A TABELA SIDRA da linha — o terceiro componente da identidade de um
            # produto, (banco, tabela, código). NÃO é decoração: madeira, lenha e carvão
            # existem nas DUAS tabelas do PEVS com o mesmo nome, então uma tela que rotule
            # as linhas pelo nome funde duas linhas legítimas — o gráfico "O que <lugar>
            # produz" desenhava uma barra só e dois rótulos sobrepostos. `None` nos bancos
            # de tabela única, o que mantém a chave presente e o contrato estável em vez de
            # aparecer e sumir por banco.
            "sidra_tabela": getattr(r, "sidra_tabela", None),
            "value": _num(r.total_value) / 1e6,
            "q_mass": _num(getattr(r, "q_mass", 0)) / 1e3,
            "q_vol": _num(getattr(r, "q_vol", 0)) / 1e6,
            "q_count": _num(getattr(r, "q_count", 0)) / 1e6,
        }
        for r in df.head(max_rows).itertuples()
    ]
    return {"products": products}


def _monthly_avg(matrix: dict[int, list[float | None]], years: list[int]) -> list[float]:
    """Per-calendar-month mean over the coverage years, excluding ABSENT (None)
    months only — a truthiness filter would silently drop genuine 0.0 months and
    bias the average upward."""
    out: list[float] = []
    for mi in range(12):
        vals = [matrix[y][mi] for y in years if matrix[y][mi] is not None]
        out.append(sum(vals) / len(vals) if vals else 0.0)
    return out


def serialize_monthly(df: pd.DataFrame | None) -> dict:
    """seam.monthly_data() → MonthlyData. year→12 monthly values + the 12-month avg,
    for BOTH Capital (value, US$ mi) and Volume (net weight, mil t), so the seasonal
    profile can overlay the two metrics on one month axis."""
    base = {"preview": False, "unit": "US$", "weightUnit": "mil t", "months": list(range(1, 13))}
    if _empty(df):
        # Always 12 values, even with no data: ViewSeasonality computes peak/low/
        # amplitude over monthlyAvg and would crash on an empty list (indexOf max of
        # [] = -1 → monthlyAvg[-1] = undefined → fmt throws). 12 zeros match the
        # loading shell producers.js ships, so the empty state renders honestly.
        return {
            **base,
            "years": [],
            "matrix": {},
            "monthlyAvg": [0.0] * 12,
            "weightMatrix": {},
            "weightMonthlyAvg": [0.0] * 12,
            "series": [],
        }
    # Seed absent months as None (not 0.0) so the 12-month average can tell a
    # genuine 0-export month from a month with no data row. The emitted matrices
    # still use 0.0 for absent months (the contract is 12 numbers per year).
    v_matrix: dict[int, list[float | None]] = {}
    w_matrix: dict[int, list[float | None]] = {}
    series: list[dict] = []
    for r in df.itertuples():
        y, m = int(r.reference_year), int(r.reference_month)
        v = _num(r.total_value_usd) / 1e6  # US$ mi
        w = _num(getattr(r, "total_weight_kg", 0)) / 1e6  # kg → mil t
        v_matrix.setdefault(y, [None] * 12)[m - 1] = v
        w_matrix.setdefault(y, [None] * 12)[m - 1] = w
        series.append({"ym": f"{y}-{m:02d}", "y": y, "m": m, "v": v, "w": w})
    years = sorted(v_matrix)
    fill = lambda mx: {str(y): [c if c is not None else 0.0 for c in mx[y]] for y in years}  # noqa: E731
    return {
        **base,
        "years": years,
        "matrix": fill(v_matrix),
        "monthlyAvg": _monthly_avg(v_matrix, years),
        "weightMatrix": fill(w_matrix),
        "weightMonthlyAvg": _monthly_avg(w_matrix, years),
        "series": series,
    }


def serialize_value_added(d: dict) -> dict:
    """seam.value_added() → ValueAddedAnalysis (per-level gradient).

    The seam returns a per-year series where each point carries ``levels[<id>] =
    {v (US$ bi), w (mil t), price (US$/kg)}`` for the levels present that year, plus
    the ``levels`` present overall (ordinal order), the ``premium`` (most- ÷
    least-processed price) and the ``predominant`` level. The view's stacked-area +
    price charts want one continuous array per level, so pivot into
    ``byLevel``/``byLevelWeight``/``byLevelPrice`` = {<id>: [{y, v}]} — every present
    level gets a point for every year (0 where it has no export that year)."""
    series = d.get("series", [])
    years = [r["y"] for r in series]
    levels = d.get("levels", [])

    def _pivot(metric: str) -> dict:
        return {
            lvl: [{"y": r["y"], "v": r["levels"].get(lvl, {}).get(metric, 0)} for r in series]
            for lvl in levels
        }

    return {
        "preview": False,
        "years": years,
        "levels": levels,
        "byLevel": _pivot("v"),
        "byLevelWeight": _pivot("w"),
        "byLevelPrice": _pivot("price"),
        "series": series,
        "premium": d.get("premium", 0.0),
        "predominant": d.get("predominant"),
        "nCodes": d.get("n_codes", 0),
    }


def serialize_market_nature(d: dict) -> dict:
    """seam.market_nature() → MarketNatureAnalysis. Already in shape (series rows
    are {y, <marketId>…}); just stamp preview:false."""
    return {
        "preview": False,
        "years": d.get("years", []),
        "series": d.get("series", []),
        "latest": d.get("latest", {}),
    }


def serialize_table_page(page: dict | None) -> dict:
    """seam.table_page() → { columns:[{name,type}], rows:[[…]], total, table, label, grain }.

    ``rows`` are RAW values aligned to ``columns`` (schema order) — this view is a faithful
    window onto the table, so nothing is reshaped or rescaled. The app's SafeJSONProvider
    coerces NaN/Inf → null and numpy/Timestamp scalars to JSON natives on dumps, so the grid
    renders the table verbatim. ``None`` (non-live banco) → an empty page."""
    if not page:
        return {"columns": [], "rows": [], "total": 0, "table": None, "label": None, "grain": None}
    df = page["df"]
    type_of = {c["name"]: c["type"] for c in page["columns"]}
    if _empty(df):
        columns, rows = page["columns"], []
    else:
        columns = [{"name": c, "type": type_of.get(c, "STRING")} for c in df.columns]
        rows = df.values.tolist()
    return {
        "columns": columns,
        "rows": rows,
        "total": int(page["total"]),
        "table": page["table"],
        "label": page.get("label"),
        "grain": page.get("grain"),
    }


def serialize_seed_page(page: dict | None) -> dict:
    """seam.seed_page() → the table-page grid shape + an ``editable`` flag.

    Reuses :func:`serialize_table_page` (identical grid contract — columns/rows/total/
    table/label/grain, with ``grain`` carrying the seed's pt-BR description) and adds
    ``editable`` so the UI shows a read-only badge + the "report a value" affordance."""
    out = serialize_table_page(page)
    out["editable"] = bool(page.get("editable")) if page else False
    return out


def serialize_catalog_worklist(worklist: dict | None) -> dict:
    """seam.catalog_worklist() → the admin-editor payload (already JSON-native:
    entries + the per-Agrupamento grouping). Normalizes ``None`` to an empty catalog."""
    if not worklist:
        return {"entries": [], "total": 0, "by_agrupamento": []}
    return {
        "entries": worklist.get("entries", []),
        "total": int(worklist.get("total", 0)),
        "by_agrupamento": worklist.get("by_agrupamento", []),
    }


def serialize_orphan_worklist(worklist: dict | None) -> dict:
    """seam.orphan_worklist() → the Descontinuados payload (already JSON-native): orphan
    commodities + their flagged date + deletion warning. Normalizes None to empty."""
    if not worklist:
        return {"orphans": [], "total": 0}
    return {"orphans": worklist.get("orphans", []), "total": int(worklist.get("total", 0))}
