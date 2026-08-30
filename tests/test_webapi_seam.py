"""Unit tests for the seam's analytical core (+ the app's /api 404 contract).

Pure-ish: the gateway readers are monkeypatched with synthetic DataFrames, so no
BigQuery. Locks the curated-purpose contract (market-nature), the base-unit
quantity aggregation, the no-codes guards on the cross producers, the
exp_price/None gap, the export-coefficient window alignment, the COMEX Sankey
export filter, the value-added batching and the TTL-cached catalog.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from embrapa_dashboard.config import Settings


def _seam():
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.webapi import seam

    return seam


def _cross():
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.webapi import seam_cross

    return seam_cross


def _curation():
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.webapi import seam_attribute_engineering

    return seam_attribute_engineering


def _base():
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.webapi import seam_base

    return seam_base


def _bind_simplecache():
    """Bind the shared serving cache to a fresh Flask app (SimpleCache)."""
    from flask import Flask

    from embrapa_dashboard.serving.cache import cache

    app = Flask(__name__)
    cache.init_app(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300})
    return app, cache


def test_market_nature_sums_value_by_curated_purpose(monkeypatch):
    # Market nature is EDIT-DRIVEN again (dim_flow_market_scd2 LEFT JOINed into the mart):
    # the serving mart carries the market_nature column, so the analysis just sums
    # fetch_market_nature_series (already NULL-filtered + grouped by (market_nature × year))
    # into US$ bi.
    seam = _seam()
    df = pd.DataFrame(
        [
            {"reference_year": 2022, "market_nature": "processamento", "value_usd": 1e9},
            {"reference_year": 2022, "market_nature": "consumo", "value_usd": 2e9},
        ]
    )
    monkeypatch.setattr(seam.gateway, "fetch_market_nature_series", lambda codes=(): df)

    out = seam.market_nature()

    assert out["years"] == [2022]
    row = out["series"][0]
    assert row["y"] == 2022
    assert row["consumo"] == 2.0  # 2e9 USD → US$ bi
    assert row["processamento"] == 1.0  # 1e9 USD → US$ bi
    assert out["latest"] == row


def test_market_nature_empty_when_nothing_classified(monkeypatch):
    # An empty serving frame (no market_nature-mapped rows) → empty analysis.
    seam = _seam()
    monkeypatch.setattr(seam.gateway, "fetch_market_nature_series", lambda codes=(): pd.DataFrame())

    out = seam.market_nature()
    assert out["years"] == [] and out["series"] == [] and out["latest"] == {}


def test_flow_market_worklist_joins_mart_values_with_current_mapping(monkeypatch):
    # The matrix data = COMTRADE traded value (from the serving mart) ⟕ the current
    # market classification (from the live SCD2 view). Cells sort by value desc; the
    # classified count reflects only pairs with a market.
    cur = _curation()
    values = pd.DataFrame(
        [
            {"customs_code": "C04", "flow_code": "export", "value_usd": 5e9},
            {"customs_code": "C01", "flow_code": "import", "value_usd": 2e9},
        ]
    )
    mapping = pd.DataFrame([{"customs_code": "C01", "flow_code": "import", "market": "consumo"}])
    monkeypatch.setattr(cur.gateway, "fetch_flow_market_values", lambda: values)
    monkeypatch.setattr(cur.gateway, "fetch_current_flow_market", lambda: mapping)

    out = cur.flow_market_worklist()

    assert out["total"] == 2
    assert out["classified"] == 1  # only C01×import is classified
    # Highest-value pair first, and it carries no market (unclassified → None).
    assert out["cells"][0] == {
        "customs_code": "C04",
        "flow_code": "export",
        "value_usd": 5e9,
        "market": None,
    }
    assert out["cells"][1]["market"] == "consumo"
    # The flow label is the pt-BR name for the normalized token.
    assert {"code": "export", "label": "Exportação"} in out["flows"]


def test_flow_market_worklist_surfaces_classified_pairs_with_no_data(monkeypatch):
    # A pair classified in the SCD2 view but with NO COMTRADE value (e.g. a regime absent
    # from the data) must still render as a cell (value 0), else the researcher's saved
    # classification silently disappears from the matrix + KPI.
    cur = _curation()
    values = pd.DataFrame([{"customs_code": "C01", "flow_code": "import", "value_usd": 2e9}])
    mapping = pd.DataFrame(
        [
            {"customs_code": "C01", "flow_code": "import", "market": "consumo"},
            {"customs_code": "C09", "flow_code": "import", "market": "processamento"},  # no data
        ]
    )
    monkeypatch.setattr(cur.gateway, "fetch_flow_market_values", lambda: values)
    monkeypatch.setattr(cur.gateway, "fetch_current_flow_market", lambda: mapping)

    out = cur.flow_market_worklist()

    assert out["total"] == 2  # the data cell AND the no-data classified cell
    assert out["classified"] == 2
    c09 = next(c for c in out["cells"] if c["customs_code"] == "C09")
    assert c09 == {
        "customs_code": "C09",
        "flow_code": "import",
        "value_usd": 0.0,
        "market": "processamento",
    }


def test_flow_market_worklist_empty_when_view_absent(monkeypatch):
    # Before activation (SCD2 view / mart absent → NotFound) the matrix renders empty,
    # not a 500 — the classification just isn't available yet.
    from google.api_core.exceptions import NotFound

    cur = _curation()

    def _absent(*a, **k):
        raise NotFound("no view yet")

    monkeypatch.setattr(cur.gateway, "fetch_flow_market_values", _absent)
    monkeypatch.setattr(cur.gateway, "fetch_current_flow_market", _absent)

    out = cur.flow_market_worklist()
    assert out == {"customs": [], "flows": [], "cells": [], "classified": 0, "total": 0}


def test_flow_market_map_empty_when_reader_returns_empty(monkeypatch):
    # An empty SCD2 frame (nobody classified yet) → empty mapping, not a crash.
    cur = _curation()
    monkeypatch.setattr(cur.gateway, "fetch_current_flow_market", lambda: pd.DataFrame())
    assert cur._flow_market_map() == {}


def test_seam_record_flow_market_forwards_to_writer_without_request_context(monkeypatch):
    # The seam wrapper works outside a Flask request (headers={}), delegating to the BFF
    # writer verbatim — the path a CLI-driven write (flow-market-seed) takes.
    cur = _curation()
    from embrapa_dashboard.serving import attribute_engineering

    captured = {}

    def _writer(customs_code, flow_code, market, headers, change_id=None):
        captured.update(
            customs_code=customs_code,
            flow_code=flow_code,
            market=market,
            headers=headers,
            change_id=change_id,
        )
        return {"deduped": False}

    monkeypatch.setattr(attribute_engineering, "record_flow_market", _writer)
    out = cur.record_flow_market("C04", "export", "processamento", change_id="k-9")
    assert out == {"deduped": False}
    assert captured["customs_code"] == "C04" and captured["flow_code"] == "export"
    assert captured["market"] == "processamento" and captured["change_id"] == "k-9"
    assert captured["headers"] == {}  # no request context → empty headers


def test_market_nature_empty_for_commodity_without_comtrade_codes(monkeypatch):
    # A commodity scoped by the selector that has NO COMTRADE HS codes must return
    # empty — NOT silently fall through to the unscoped all-commodities total
    # (an empty codes tuple means "no filter" to fetch_market_nature_series).
    seam = _seam()
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {"manicoba": {"comtrade": [], "comex": ["1"], "pevs": ["2"]}},
    )
    # Data exists in the mart; the no-codes guard must still short-circuit to empty
    # (fetch_market_nature_series must never even be called for a code-less commodity).
    df = pd.DataFrame(
        [{"reference_year": 2022, "market_nature": "processamento", "value_usd": 1e9}]
    )
    monkeypatch.setattr(
        seam.gateway,
        "fetch_market_nature_series",
        lambda codes=(): pytest.fail("must not query the unscoped market-nature total") or df,
    )

    out = seam.market_nature("manicoba")
    assert out["years"] == [] and out["series"] == [] and out["latest"] == {}


# ── overview quantities: base unit (t / m³), never the mixed native units ──────


def test_with_overview_quantities_sums_qty_base_per_family():
    """q_mass/q_vol are the per-family base CASE columns: trade sources mix kg- and
    t-native codes inside 'massa', so summing/scaling the native quantity was
    ~1000× off, and mass and volume are never blended into one total."""
    seam = _seam()
    overview = pd.DataFrame([{"reference_year": 2022, "total_value": 1e9}])
    pts = pd.DataFrame(
        [
            # kg-native NCM: 5e9 kg native, 5e6 t base → q_mass (massa CASE column)
            {
                "code": "08012100",
                "reference_year": 2022,
                "total_qty_native": 5e9,
                "q_mass": 5e6,
                "q_vol": float("nan"),
                "family": "massa",
            },
            # t-native NCM in the same family (native == base)
            {
                "code": "44012200",
                "reference_year": 2022,
                "total_qty_native": 3e3,
                "q_mass": 3e3,
                "q_vol": float("nan"),
                "family": "massa",
            },
            {
                "code": "44071100",
                "reference_year": 2022,
                "total_qty_native": 7e6,
                "q_mass": float("nan"),
                "q_vol": 7e6,
                "family": "volume",
            },
        ]
    )
    out = seam._with_overview_quantities(overview, pts)
    assert float(out.loc[0, "q_mass"]) == 5_003_000.0  # t — never 5e9 + 3e3
    assert float(out.loc[0, "q_vol"]) == 7_000_000.0  # m³ — never blended with mass


# ── snapshot: a REAL per-(UF, year) frame backs the ano × UF heatmap ───────────


def _stub_snapshot_readers(seam, monkeypatch, *, uf_yearly, source):
    """Stub every gateway reader snapshot() touches with empty frames, except the
    year×UF reader under test which returns ``uf_yearly``."""
    empty = pd.DataFrame()
    for name in (
        "fetch_products",
        "fetch_quality_by_source",
        "fetch_product_timeseries",
        "fetch_quality_timeseries",
        "fetch_quality_by_product",
        "fetch_production_overview",
        "fetch_production_by_uf",
        "fetch_comex_overview",
        "fetch_comtrade_overview",
        "fetch_comex_by_uf",
    ):
        monkeypatch.setattr(seam.gateway, name, lambda *a, **k: empty)
    reader = (
        "fetch_production_by_uf_yearly" if source == "ibge_pevs" else "fetch_comex_by_uf_yearly"
    )
    monkeypatch.setattr(seam.gateway, reader, lambda *a, **k: uf_yearly)


def test_snapshot_exposes_real_uf_yearly_for_pevs(monkeypatch):
    seam = _seam()
    yearly = pd.DataFrame(
        [
            {
                "state_acronym": "PA",
                "state_name": "Pará",
                "region_abbrev": "N",
                "reference_year": 2020,
                "total_value": 1e6,
                "q_mass": 2e6,
                "q_vol": None,
            }
        ]
    )
    _stub_snapshot_readers(seam, monkeypatch, uf_yearly=yearly, source="ibge_pevs")
    out = seam.snapshot("ibge_pevs", {"currency": "BRL", "correction": "IPCA"})
    assert "uf_yearly" in out
    uy = out["uf_yearly"]
    assert list(uy["state_acronym"]) == ["PA"] and list(uy["reference_year"]) == [2020]


def test_snapshot_renames_comex_uf_yearly_value_column(monkeypatch):
    """The COMEX year×UF reader returns total_value_usd; snapshot() must rename it
    to total_value so the serializer/heatmap read the same field as PEVS/PAM."""
    seam = _seam()
    yearly = pd.DataFrame(
        [
            {
                "state_acronym": "SP",
                "state_name": "São Paulo",
                "region_abbrev": "SE",
                "reference_year": 2022,
                "total_value_usd": 9e6,
                "q_mass": 4e6,
                "q_vol": 0.0,
            }
        ]
    )
    _stub_snapshot_readers(seam, monkeypatch, uf_yearly=yearly, source="mdic_comex")
    out = seam.snapshot("mdic_comex", {})
    uy = out["uf_yearly"]
    assert "total_value" in uy.columns and "total_value_usd" not in uy.columns
    assert float(uy.loc[0, "total_value"]) == 9e6


# ── snapshot: the server-side flow (export/import) filter ──────────────────────


def _capture_flow_readers(seam, monkeypatch):
    """Stub the snapshot's trade readers; each records the `flow` kwarg it got."""
    empty = pd.DataFrame()
    captured = {}

    def spy(name):
        def _fn(*a, **k):
            captured[name] = k.get("flow", "MISSING")
            return empty

        return _fn

    for name in (
        "fetch_products",
        "fetch_quality_by_source",
        "fetch_quality_timeseries",
        "fetch_quality_by_product",
    ):
        monkeypatch.setattr(seam.gateway, name, lambda *a, **k: empty)
    for name in (
        "fetch_product_timeseries",
        "fetch_comex_overview",
        "fetch_comex_by_uf",
        "fetch_comex_by_uf_yearly",
    ):
        monkeypatch.setattr(seam.gateway, name, spy(name))
    return captured


def test_snapshot_threads_flow_to_every_trade_reader(monkeypatch):
    """A picked direction reaches all four COMEX snapshot readers, so the overview,
    per-product series and per-UF map stay mutually consistent under the filter."""
    seam = _seam()
    captured = _capture_flow_readers(seam, monkeypatch)
    seam.snapshot("mdic_comex", {"currency": "USD", "correction": "Nominal"}, {"flow": "import"})
    assert captured["fetch_product_timeseries"] == "import"
    assert captured["fetch_comex_overview"] == "import"
    assert captured["fetch_comex_by_uf"] == "import"
    assert captured["fetch_comex_by_uf_yearly"] == "import"


def test_snapshot_flow_all_and_absent_resolve_to_none(monkeypatch):
    """'all' and an absent flow both → None (sum every flow), so an unfiltered
    request is byte-identical to before the param existed."""
    seam = _seam()
    conv = {"currency": "USD", "correction": "Nominal"}

    captured = _capture_flow_readers(seam, monkeypatch)
    seam.snapshot("mdic_comex", conv, {"flow": "all"})
    assert captured["fetch_comex_overview"] is None

    captured = _capture_flow_readers(seam, monkeypatch)
    seam.snapshot("mdic_comex", conv, None)
    assert captured["fetch_comex_overview"] is None


# ── geo_yearly: basket-scoped per-(UF, year) cube ──────────────────────────────


def test_geo_yearly_pushes_basket_down_to_production_reader(monkeypatch):
    """geo_yearly threads the active basket into the by-UF-yearly reader so the
    returned (UF × year) cube is narrowed to the selected products (the snapshot's
    ufYearly is all-products; this is what makes the map/hero basket-aware)."""
    seam = _seam()
    captured = {}
    yearly = pd.DataFrame(
        [
            {
                "state_acronym": "PA",
                "state_name": "Pará",
                "region_abbrev": "N",
                "reference_year": 2021,
                "total_value": 5e6,
                "q_mass": 1e6,
                "q_vol": None,
            }
        ]
    )

    def fake(*a, **k):
        captured.update(k)
        return yearly

    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf_yearly", fake)
    out = seam.geo_yearly(
        "ibge_pevs", {"currency": "BRL", "correction": "IPCA"}, {"basket": ["3405"]}
    )
    assert list(out["state_acronym"]) == ["PA"]
    assert captured["product_codes"] == ("3405",)  # basket pushed down to the query
    assert captured["source"] == "ibge_pevs"


def test_geo_yearly_renames_comex_value_column(monkeypatch):
    """COMEX's year×UF reader returns total_value_usd; geo_yearly renames it to
    total_value so the shared _uf_yearly serializer reads the same field as PEVS."""
    seam = _seam()
    yearly = pd.DataFrame(
        [
            {
                "state_acronym": "MT",
                "state_name": "Mato Grosso",
                "region_abbrev": "CO",
                "reference_year": 2022,
                "total_value_usd": 7e6,
                "q_mass": 2e6,
                "q_vol": 0.0,
            }
        ]
    )
    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf_yearly", lambda *a, **k: yearly)
    out = seam.geo_yearly("mdic_comex", {"currency": "USD", "correction": "Nominal"}, None)
    assert "total_value" in out.columns and "total_value_usd" not in out.columns
    assert float(out.loc[0, "total_value"]) == 7e6


def test_geo_yearly_threads_flow_to_comex_reader(monkeypatch):
    """A picked direction reaches the COMEX by-(UF, year) cube reader — so a product
    basket's map/hero stays consistent with the flow-filtered snapshot. The audit M2
    gap was the cube summing every flow while the snapshot honoured the direction."""
    seam = _seam()
    captured = {}

    def fake(*a, **k):
        captured["flow"] = k.get("flow", "MISSING")
        return pd.DataFrame(
            {"state_acronym": ["PA"], "reference_year": [2022], "total_value_usd": [1.0]}
        )

    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf_yearly", fake)
    seam.geo_yearly("mdic_comex", {"currency": "USD", "correction": "Nominal"}, {"flow": "export"})
    assert captured["flow"] == "export"


def test_geo_yearly_flow_all_and_absent_resolve_to_none(monkeypatch):
    """'all'/absent flow → None (sum every flow), so an unfiltered basket cube is
    byte-identical to before the flow param threaded through."""
    seam = _seam()
    captured = {}

    def fake(*a, **k):
        captured["flow"] = k.get("flow", "MISSING")
        return pd.DataFrame()

    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf_yearly", fake)
    seam.geo_yearly("mdic_comex", {"currency": "USD", "correction": "Nominal"}, {"flow": "all"})
    assert captured["flow"] is None
    seam.geo_yearly("mdic_comex", {"currency": "USD", "correction": "Nominal"}, None)
    assert captured["flow"] is None


def test_geo_yearly_none_for_banco_without_geo_grain():
    """COMTRADE is country-pair (no UF) → geo_yearly returns None (the route then
    serializes { ufYearly: [] } and the client keeps its national series)."""
    seam = _seam()
    assert seam.geo_yearly("un_comtrade", {}, None) is None


# ── value label: Comtrade imports are CIF, not FOB ─────────────────────────────


def test_effective_value_column_states_both_valuation_bases_for_comtrade():
    seam = _seam()
    from embrapa_dashboard.webapi.registries import banco_by_id

    # US$-nominal request: the FOB/CIF basis is stated in the label, but the figure
    # IS in the requested currency (the real year-FX US$ column).
    col, label = seam.effective_value_column(
        banco_by_id("un_comtrade"), {"currency": "USD", "correction": "Nominal"}
    )
    assert col == "val_yearfx_usd"
    assert "FOB" in label and "CIF" in label  # exports FOB / imports CIF
    col, label = seam.effective_value_column(
        banco_by_id("mdic_comex"), {"currency": "USD", "correction": "Nominal"}
    )
    assert col == "val_yearfx_usd"
    assert "FOB" in label  # COMEX serves FOB for both flows


def test_effective_value_column_trade_serves_real_brl_eur_columns():
    """A BRL/EUR request on a trade banco now serves the REAL year-FX column the
    mart carries (no more client-side mock FX cross-conversion). The label keeps the
    customs FOB/CIF valuation-basis note so the researcher knows the US$ origin."""
    seam = _seam()
    from embrapa_dashboard.webapi.registries import banco_by_id

    # BRL · Nominal → the real year-FX BRL column.
    col, label = seam.effective_value_column(
        banco_by_id("mdic_comex"), {"currency": "BRL", "correction": "Nominal"}
    )
    assert col == "val_yearfx_brl"
    assert "R$" in label and "FOB" in label
    # EUR · IPCA → the real deflated EUR column.
    col, label = seam.effective_value_column(
        banco_by_id("un_comtrade"), {"currency": "EUR", "correction": "IPCA"}
    )
    assert col == "val_real_ipca_eur"
    assert "€" in label and "FOB" in label and "CIF" in label
    # The route default (BRL · IPCA, no explicit currency) resolves to the real
    # BRL column — NOT the old USD hard-lock.
    col, label = seam.effective_value_column(banco_by_id("mdic_comex"), {})
    assert col == "val_real_ipca_brl"


def test_effective_value_column_trade_falls_back_for_unmodelled_combo():
    """USD × IGP-M is omitted from the allowlist (no val_real_igpm_usd served), so a
    trade request for it falls back to the same correction in BRL — a REAL column,
    never a mock conversion — and the label flags the substitution + FOB/CIF basis."""
    seam = _seam()
    from embrapa_dashboard.webapi.registries import banco_by_id

    col, label = seam.effective_value_column(
        banco_by_id("un_comtrade"), {"currency": "USD", "correction": "IGP-M"}
    )
    assert col == "val_real_igpm_brl"
    assert "indisponível" in label and "FOB" in label and "CIF" in label


# ── COMEX Sankey: exports only (import rows run country→UF, not UF→country) ────


def test_flow_data_comex_filters_to_exports(monkeypatch):
    seam = _seam()
    recorded = {}

    def fake_flows(year_start=None, year_end=None, ncm_codes=(), flow=None, uf_codes=()):
        recorded["flow"] = flow
        return pd.DataFrame(
            [
                {
                    "origin_code": "PA",
                    "origin_name": "Pará",
                    "dest_code": "156",
                    "dest_name": "China",
                    "value_usd": 1e6,
                }
            ]
        )

    monkeypatch.setattr(seam.gateway, "fetch_comex_flows", fake_flows)
    out = seam.flow_data("mdic_comex")
    assert recorded["flow"] == "export"
    assert out is not None and not out["links"].empty


def test_flow_data_threads_basket_and_year_window(monkeypatch):
    """A non-None summary (basket + period) reaches the gateway flow reader as
    ncm_codes + year_start/year_end — the bug was the summary being discarded so
    a filtered request returned the unscoped flows."""
    seam = _seam()
    recorded = {}

    cols = ["origin_code", "origin_name", "dest_code", "dest_name", "value_usd"]

    def fake_flows(year_start=None, year_end=None, ncm_codes=(), flow=None, uf_codes=()):
        recorded.update(year_start=year_start, year_end=year_end, ncm_codes=ncm_codes)
        return pd.DataFrame(columns=cols)

    monkeypatch.setattr(seam.gateway, "fetch_comex_flows", fake_flows)
    seam.flow_data(
        "mdic_comex",
        {"basket": ["0801", "0802"], "startDate": "2018", "endDate": "2022"},
    )
    assert recorded["ncm_codes"] == ("0801", "0802")
    assert recorded["year_start"] == 2018
    assert recorded["year_end"] == 2022


def test_flow_data_comex_threads_uf_filter(monkeypatch):
    """The active origin-UF (``states``) selection reaches the COMEX flow reader as
    ``uf_codes`` — the audit gap was the UF dimension being dropped on the trade
    origin readers."""
    seam = _seam()
    recorded = {}
    cols = ["origin_code", "origin_name", "dest_code", "dest_name", "value_usd"]

    def fake_flows(year_start=None, year_end=None, ncm_codes=(), flow=None, uf_codes=()):
        recorded.update(uf_codes=uf_codes)
        return pd.DataFrame(columns=cols)

    monkeypatch.setattr(seam.gateway, "fetch_comex_flows", fake_flows)
    seam.flow_data("mdic_comex", {"states": ["PA", "SP"]})
    assert recorded["uf_codes"] == ("PA", "SP")


def test_flow_data_comex_no_uf_filter_passes_empty(monkeypatch):
    """No ``states`` selection → empty ``uf_codes`` tuple (no UF filter — the
    existing 'empty = unfiltered' convention)."""
    seam = _seam()
    recorded = {}
    cols = ["origin_code", "origin_name", "dest_code", "dest_name", "value_usd"]

    def fake_flows(year_start=None, year_end=None, ncm_codes=(), flow=None, uf_codes=()):
        recorded.update(uf_codes=uf_codes)
        return pd.DataFrame(columns=cols)

    monkeypatch.setattr(seam.gateway, "fetch_comex_flows", fake_flows)
    seam.flow_data("mdic_comex", {"basket": ["0801"]})
    assert recorded["uf_codes"] == ()


def test_flow_data_comtrade_ignores_uf_filter(monkeypatch):
    """COMTRADE's origin is a reporter country (no UF column), so its flow reader
    takes no ``uf_codes`` — a UF selection must NOT reach it (it would error / be
    meaningless). The frontend surfaces the not-applicable note instead."""
    seam = _seam()
    recorded = {}
    cols = ["origin_code", "origin_name", "dest_code", "dest_name", "value_usd"]

    def fake_flows(year_start=None, year_end=None, cmd_codes=(), **kwargs):
        recorded["called"] = True
        recorded["kwargs"] = kwargs
        return pd.DataFrame(columns=cols)

    monkeypatch.setattr(seam.gateway, "fetch_comtrade_flows", fake_flows)
    # No TypeError despite an active states filter: the seam never forwards uf_codes
    # to the COMTRADE reader (whose signature has none).
    out = seam.flow_data("un_comtrade", {"states": ["PA", "SP"]})
    assert recorded.get("called") and out is not None


def test_partner_data_comex_threads_uf_filter(monkeypatch):
    """The active UF (``states``) selection narrows the COMEX partner ranking via
    ``uf_codes``; empty = unfiltered."""
    seam = _seam()
    recorded = {}

    def fake_partners(
        year_start=None, year_end=None, ncm_codes=(), uf_codes=(), flow=None, rank_by="value"
    ):
        recorded.update(uf_codes=uf_codes, rank_by=rank_by, flow=flow)
        return pd.DataFrame(columns=["partner_code", "partner_name", "value_usd"])

    monkeypatch.setattr(seam.gateway, "fetch_comex_partners", fake_partners)
    seam.partner_data("mdic_comex", {"states": ["PA"]})
    assert recorded["uf_codes"] == ("PA",)
    recorded.clear()
    seam.partner_data("mdic_comex", {"basket": ["0801"]})
    assert recorded["uf_codes"] == ()
    # rank_by defaults to value and is threaded to the reader
    recorded.clear()
    seam.partner_data("mdic_comex", {}, rank_by="price")
    assert recorded["rank_by"] == "price"


def test_partner_data_comtrade_ignores_uf_filter(monkeypatch):
    """COMTRADE partner reader has no origin-UF column, so a UF selection never
    reaches it (the frontend surfaces not-applicable)."""
    seam = _seam()
    recorded = {}

    def fake_partners(year_start=None, year_end=None, cmd_codes=(), rank_by="value", **kwargs):
        recorded["called"] = True
        recorded["kwargs"] = kwargs
        return pd.DataFrame(columns=["partner_code", "partner_name", "value_usd"])

    monkeypatch.setattr(seam.gateway, "fetch_comtrade_partners", fake_partners)
    seam.partner_data("un_comtrade", {"states": ["PA"]})
    assert recorded.get("called")


def test_productivity_threads_year_window_to_gateway(monkeypatch):
    """ViewProductivity's period filter reaches fetch_productivity as
    year_start/year_end — previously the summary was ignored, so a year window
    left the yield/area trajectory unchanged."""
    seam = _seam()
    recorded = {}

    monkeypatch.setattr(
        seam.gateway,
        "fetch_products",
        lambda banco_id: pd.DataFrame([{"code": "2713", "name": "Café"}]),
    )

    def fake_productivity(
        product_code, source="ibge_pam", year_start=None, year_end=None, uf_codes=()
    ):
        recorded.update(
            product_code=product_code,
            source=source,
            year_start=year_start,
            year_end=year_end,
            uf_codes=uf_codes,
        )
        return pd.DataFrame(columns=["reference_year", "state_acronym"])

    monkeypatch.setattr(seam.gateway, "fetch_productivity", fake_productivity)
    out = seam.productivity("ibge_pam", "2713", {"startDate": "2010", "endDate": "2020"})
    assert out is not None and out["active"] == "2713"
    assert recorded["product_code"] == "2713"
    assert recorded["year_start"] == 2010
    assert recorded["year_end"] == 2020


# ── exp_price: a year without weight is a gap (None), never value ÷ 1 ──────────


def test_cross_points_exp_price_emits_none_when_weight_missing(monkeypatch):
    seam = _seam()
    val = pd.DataFrame(
        [
            {"reference_year": 2020, "value": 5e9},
            {"reference_year": 2021, "value": 6e9},
        ]
    )
    wt = pd.DataFrame([{"reference_year": 2020, "value": 1e9}])  # 2021 missing

    def fake_cross(metric, year_start=None, year_end=None, codes=(), uf_codes=()):
        return val if metric == "mdic_comex:exp_value" else wt

    monkeypatch.setattr(seam.gateway, "fetch_cross_series", fake_cross)
    pts = seam._cross_points("mdic_comex", "exp_price", 2020, 2021, "US$/kg")
    assert pts == [{"y": 2020, "v": 5.0}, {"y": 2021, "v": None}]


# ── cross producers: no codes for a needed source → honest empty, never the ────
# unscoped ALL-commodities totals (empty codes mean "no filter" to the readers)


def _no_codes_catalog(mod, monkeypatch):
    # `mod` is the seam_base module (the shared toolkit the cross/curation readers
    # resolve produto_catalog/_codes/_xyear through), so a single patch reaches
    # both the direct calls and the indirect _codes -> produto_catalog chain.
    monkeypatch.setattr(
        mod,
        "produto_catalog",
        lambda: {"manicoba": {"name": "Maniçoba", "pevs": ["9"], "comex": [], "comtrade": []}},
    )
    monkeypatch.setattr(
        mod,
        "_xyear",
        lambda metric, codes, uf_codes=(): pytest.fail("must not query the unscoped totals"),
    )


def test_market_share_empty_for_commodity_without_codes(monkeypatch):
    seam = _seam()
    _no_codes_catalog(_base(), monkeypatch)
    out = seam.market_share("manicoba")
    assert out == {"unit": "US$ bi", "series": [], "by_product": []}


def test_trade_mirror_empty_for_commodity_without_codes(monkeypatch):
    seam = _seam()
    _no_codes_catalog(_base(), monkeypatch)
    out = seam.trade_mirror("manicoba")
    assert out == {"unit": "US$ bi", "series": [], "discrepancy": []}


def test_price_spread_empty_for_commodity_without_comex_codes(monkeypatch):
    seam = _seam()
    _no_codes_catalog(_base(), monkeypatch)
    monkeypatch.setattr(_cross(), "_is_mass_basis", lambda cid: True)  # mass PEVS side
    out = seam.price_spread("manicoba")
    assert out == {"unit": "US$/kg", "series": []}


def test_export_coefficient_empty_for_commodity_without_comex_codes(monkeypatch):
    seam = _seam()
    _no_codes_catalog(_base(), monkeypatch)
    monkeypatch.setattr(_cross(), "_is_mass_basis", lambda cid: True)
    monkeypatch.setattr(
        _cross(),
        "_pevs_mass_by_year",
        lambda codes, uf_codes=(): pytest.fail("must not query the unscoped totals"),
    )
    out = seam.export_coefficient("manicoba")
    assert out == {
        "unit": "mil t",
        "by_uf": [],
        "national": {},
        "timeseries": [],
        "states": [],
    }


# ── export coefficient: by-UF/national restricted to the common year window ────


def test_export_coefficient_aligns_by_uf_window_to_common_years(monkeypatch):
    """PEVS starts in 1986 but COMEX in 1997 — the cumulative by-UF/national
    ratios must cover the SAME window the timeseries intersects, or coefPct is
    systematically understated."""
    seam = _seam()
    monkeypatch.setattr(_cross(), "_is_mass_basis", lambda cid: True)
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {
            "castanha": {
                "name": "Castanha",
                "pevs": ["3405"],
                "comex": ["08012100"],
                "comtrade": ["080121"],
            }
        },
    )
    monkeypatch.setattr(
        _cross(),
        "_pevs_mass_by_year",
        lambda codes, uf_codes=(): {1986: 5.0, 1997: 10.0, 2000: 20.0},
    )
    monkeypatch.setattr(  # exp_weight (kg): years 1997/2000/2024
        _base(), "_xyear", lambda metric, codes, uf_codes=(): {1997: 2e9, 2000: 4e9, 2024: 1e9}
    )
    recorded = {}

    def fake_prod(**kw):
        recorded["prod"] = kw
        return pd.DataFrame(
            [
                {
                    "state_acronym": "PA",
                    "state_name": "Pará",
                    "region_abbrev": "N",
                    "total_value": 10_000,  # qty_base (t)
                }
            ]
        )

    def fake_exp(**kw):
        recorded["exp"] = kw
        return pd.DataFrame([{"state_acronym": "PA", "total_weight_kg": 2_000_000}])

    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf", fake_prod)
    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf", fake_exp)

    out = seam.export_coefficient("castanha")

    # Both readers bounded to the intersection window 1997–2000 (1986 excluded).
    assert recorded["prod"]["year_start"] == 1997 and recorded["prod"]["year_end"] == 2000
    assert recorded["exp"]["year_start"] == 1997 and recorded["exp"]["year_end"] == 2000
    assert recorded["exp"]["flow"] == "export"
    # The export coefficient is window-CUMULATIVE on BOTH sides — never the snapshot's
    # latest-year scoping (which would make it a single-year ratio and reintroduce the
    # year-window mismatch). FINDING #1/#11: the by-UF readers opt out of latest-year.
    assert recorded["prod"]["latest_year_only"] is False
    assert recorded["exp"]["latest_year_only"] is False
    assert [d["y"] for d in out["timeseries"]] == [1997, 2000]
    assert out["by_uf"][0]["coefPct"] == pytest.approx(20.0)  # 2 mil t / 10 mil t


# ── value added: set-based (2 queries per level), never 2 per code ─────────────


def test_value_added_batches_codes_per_level(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        _curation(),
        "_current_code_levels",
        lambda: {
            ("mdic_comex", "A"): "commodity_pura",
            ("mdic_comex", "B"): "commodity_pura",
            ("mdic_comex", "C"): "manufaturado_industrial",
            ("ibge_pevs", "Z"): "commodity_pura",  # other source — out of scope
            ("mdic_comex", "D"): "not_a_level",  # free-text value outside the 8-level scale
        },
    )
    calls = []

    def fake_xyear(metric, codes, uf_codes=()):
        calls.append((metric, codes))
        return {2020: 2e9} if metric.endswith("exp_value") else {2020: 1e9}

    monkeypatch.setattr(_base(), "_xyear", fake_xyear)

    out = seam.value_added()

    assert len(calls) == 4  # 2 per present level — flat in the number of codes
    assert ("mdic_comex:exp_value", ("A", "B")) in calls
    assert ("mdic_comex:exp_weight", ("A", "B")) in calls
    assert ("mdic_comex:exp_value", ("C",)) in calls
    assert ("mdic_comex:exp_weight", ("C",)) in calls
    assert out["n_codes"] == 3
    assert out["levels"] == ["commodity_pura", "manufaturado_industrial"]  # ordinal order
    row = out["series"][0]
    assert row["y"] == 2020
    pura, ind = row["levels"]["commodity_pura"], row["levels"]["manufaturado_industrial"]
    assert pura["v"] == 2.0 and ind["v"] == 2.0
    # weight (mil t) + absolute unit price (US$/kg) surfaced per level
    assert pura["w"] == 1000.0 and ind["w"] == 1000.0  # 1e9 kg ÷1e6 → mil t
    assert pura["price"] == 2.0 and ind["price"] == 2.0  # (2 US$bi ÷ 1000 mil t)×1e3
    assert out["premium"] == 1.0  # equal prices → most ÷ least = 1


# ── catalog caching: flask-caching TTL (refreshable), not process-lifetime ─────


def test_produto_catalog_is_ttl_cached_not_process_lifetime(monkeypatch):
    """The crosswalk/catalog reads honor the serving cache policy: memoized via
    flask-caching (CACHE_DEFAULT_TIMEOUT), so a warm instance converges to the
    nightly dbt rebuild — unlike functools.lru_cache, which never expires."""
    seam = _seam()
    # flask-caching memoize marker (lru_cache has cache_clear, not uncached)
    assert hasattr(seam.produto_catalog, "uncached")
    assert hasattr(seam._crosswalk_df, "uncached")
    assert hasattr(seam._pevs_family_by_agrupamento, "uncached")
    assert hasattr(seam._code_to_agrupamento, "uncached")

    calls = {"n": 0}

    def fake_run(query, params):
        calls["n"] += 1
        return pd.DataFrame(
            [{"agrupamento_id": "x", "agrupamento_nome": "X", "source": "pevs", "code": "1"}]
        )

    monkeypatch.setattr(seam.gateway, "run_query", fake_run)
    monkeypatch.setattr(_base(), "get_settings", lambda: Settings(gcp_project_id="p"))
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        assert seam.produto_catalog()["x"]["pevs"] == ["1"]
        seam.produto_catalog()  # served from cache
        assert calls["n"] == 1
        cache.clear()  # cache expiry/invalidation → re-queries (lru never would)
        seam.produto_catalog()
        assert calls["n"] == 2


def test_produto_catalog_skips_null_id_rows_and_stays_json_safe(monkeypatch):
    """A crosswalk row with a NULL agrupamento_id (a catalog entry saved without an
    agrupamento — prod codes pevs:3433/3434) must be SKIPPED, not turned into a
    NaN float dict key. Such a key 500s the WHOLE /api/catalog: the JSON provider's
    sort_keys can't order float(NaN) against the str ids, taking down every
    cross-source view. Regression guard for that outage."""
    seam = _seam()

    def fake_run(query, params):
        # one valid row + two poison rows (NULL id, the exact prod shape: codes 3433/3434,
        # one NaN-float and one None so both missing-value flavors are covered).
        return pd.DataFrame(
            {
                "agrupamento_id": ["acai", float("nan"), None],
                "agrupamento_nome": ["Açaí", None, None],
                "source": ["pevs", "pevs", "pevs"],
                "code": ["3403", "3433", "3434"],
            }
        )

    monkeypatch.setattr(seam.gateway, "run_query", fake_run)
    monkeypatch.setattr(_base(), "get_settings", lambda: Settings(gcp_project_id="p"))
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        cat = seam.produto_catalog()

    # only the valid row survives; the id-less rows are dropped, never a key
    assert set(cat) == {"acai"}
    assert cat["acai"]["pevs"] == ["3403"]
    assert not any(pd.isna(k) for k in cat)
    # the actual failure mode: sort_keys must not raise "'<' not supported
    # between instances of 'float' and 'str'"
    json.dumps(cat, sort_keys=True)


# ── app: unknown /api paths are JSON 404, never the SPA index.html ─────────────


def test_unknown_api_path_returns_json_404(monkeypatch):
    pytest.importorskip("flask_caching")
    import embrapa_dashboard.config as config_mod
    from embrapa_dashboard.webapi import app as app_mod
    from embrapa_dashboard.webapi import seam

    # create_app binds the cache via init_cache_safely → config.get_settings (a
    # lazy import), so patch the source module. _env_file=None keeps it hermetic.
    def _stub_settings():
        return Settings(_env_file=None, gcp_project_id="p")

    monkeypatch.setattr(config_mod, "get_settings", _stub_settings)
    app = app_mod.create_app()
    app.config.update(TESTING=True)
    client = app.test_client()

    for resp in (client.get("/api/definitely-not-a-route"), client.post("/api/nope")):
        assert resp.status_code == 404
        assert resp.content_type.startswith("application/json")
        assert resp.get_json()["error"] == "endpoint de API não encontrado"

    # Registered routes still win over the catch-all.
    # routes.py calls seam.produto_catalog_with_family (the facade's re-exported
    # binding — the family-tagged catalog), so this route test patches the facade.
    monkeypatch.setattr(
        seam, "produto_catalog_with_family", lambda: {"x": {"name": "X", "family": "massa"}}
    )
    resp = client.get("/api/catalog")
    assert resp.status_code == 200 and resp.get_json() == {"x": {"name": "X", "family": "massa"}}
    assert client.get("/healthz").status_code == 200


# ── effective_value_column: convention → column with fallback chain ────────────


def test_effective_value_column_pevs_picks_requested_when_mart_has_it():
    seam = _seam()
    from embrapa_dashboard.webapi.registries import banco_by_id

    pevs = banco_by_id("ibge_pevs")
    col, label = seam.effective_value_column(pevs, {"currency": "BRL", "correction": "IGP-M"})
    assert col == "val_real_igpm_brl"
    assert label == "Valor real (IGP-M) — R$"


def test_effective_value_column_pevs_falls_back_to_brl_when_combo_absent():
    """USD + IGP-M is not in the mart (ALLOWED_VALUE_COLUMNS), so the seam swaps it
    for the same correction in BRL and flags the substitution in the label."""
    seam = _seam()
    from embrapa_dashboard.webapi.registries import banco_by_id

    pevs = banco_by_id("ibge_pevs")
    col, label = seam.effective_value_column(pevs, {"currency": "USD", "correction": "IGP-M"})
    assert col == "val_real_igpm_brl"
    assert "R$" in label and "moeda indisponível" in label


def test_effective_value_column_final_fallback_to_real_ipca_brl(monkeypatch):
    """When neither the requested combo NOR its BRL sibling is in the mart, the
    fallback chain bottoms out at val_real_ipca_brl."""
    seam = _seam()
    from embrapa_dashboard.webapi.registries import banco_by_id

    pevs = banco_by_id("ibge_pevs")
    # Shrink the allowlist to exclude both the requested column and its BRL sibling.
    monkeypatch.setattr(seam.sqlbuild, "ALLOWED_VALUE_COLUMNS", frozenset({"val_real_ipca_brl"}))
    col, label = seam.effective_value_column(pevs, {"currency": "USD", "correction": "IGP-M"})
    assert col == "val_real_ipca_brl"
    assert label == "Valor real (IPCA) — R$"


# ── snapshot: PEVS-shaped (production marts) + the dead/None banco path ────────


def test_snapshot_returns_empty_shape_for_non_live_banco():
    seam = _seam()
    out = seam.snapshot("sefaz_nfe", {"currency": "BRL", "correction": "IPCA"})
    assert out["products"] is None and out["uf_data"] is None and out["uf_yearly"] is None
    assert out["value_column"] is None and out["value_label"] == ""


def test_snapshot_pevs_threads_the_sidra_tabela_axis_to_every_production_reader(monkeypatch):
    """A chosen half of the survey must reach EVERY reader, not just the first.

    gold_pevs_production carries extraction and silviculture together. If one reader
    gets the filter and another does not, the same panel shows a scoped headline over an
    unscoped map — the two disagreeing about which half they describe, with nothing on
    screen saying so. 'all' must resolve to None (every table), the survey's own total.
    """
    seam = _seam()
    seen: dict[str, object] = {}

    def _rec(key):
        def fake(**kw):
            seen[key] = kw.get("sidra_tabela")
            return pd.DataFrame()

        return fake

    monkeypatch.setattr(seam.gateway, "fetch_products", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_source", lambda source=None: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_product_timeseries", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_timeseries", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_product", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_production_overview", _rec("ov"))
    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf", _rec("uf"))
    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf_yearly", _rec("ufy"))

    seam.snapshot("ibge_pevs", {"currency": "BRL", "correction": "IPCA"}, {"sidraTabela": "291"})
    assert seen == {"ov": "291", "uf": "291", "ufy": "291"}

    seen.clear()
    seam.snapshot("ibge_pevs", {"currency": "BRL", "correction": "IPCA"}, {"sidraTabela": "all"})
    assert seen == {"ov": None, "uf": None, "ufy": None}


def test_snapshot_pevs_threads_basket_window_and_value_column(monkeypatch):
    """PEVS snapshot: every production reader gets the resolved value column +
    parsed year window + basket; overview gains q_mass/q_vol from product_ts."""
    seam = _seam()
    recorded = {}

    def fake_products(banco_id):
        return pd.DataFrame([{"code": "1", "name": "Açaí"}])

    def fake_pts(source, year_start=None, year_end=None, codes=(), value_column=None, uf_codes=()):
        recorded["pts"] = dict(
            source=source, y0=year_start, y1=year_end, codes=codes, value_column=value_column
        )
        return pd.DataFrame(
            [
                {
                    "code": "1",
                    "reference_year": 2020,
                    "total_qty_native": 2e3,
                    "q_mass": 2e3,
                    "q_vol": float("nan"),
                    "family": "massa",
                }
            ]
        )

    def fake_overview(
        year_start=None,
        year_end=None,
        product_codes=(),
        value_column=None,
        source=None,
        sidra_tabela=None,
    ):
        recorded["ov"] = dict(value_column=value_column, source=source, sidra_tabela=sidra_tabela)
        return pd.DataFrame([{"reference_year": 2020, "total_value": 9.0}])

    monkeypatch.setattr(seam.gateway, "fetch_products", fake_products)
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_source", lambda source=None: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_product_timeseries", fake_pts)
    monkeypatch.setattr(seam.gateway, "fetch_production_overview", fake_overview)
    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf", lambda **k: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf_yearly", lambda **k: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_timeseries", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_product", lambda b: pd.DataFrame())

    out = seam.snapshot(
        "ibge_pevs",
        {"currency": "BRL", "correction": "IPCA"},
        {"basket": ["1"], "startDate": "2018-01-01", "endDate": "2021"},
    )
    assert recorded["pts"]["codes"] == ("1",)
    assert recorded["pts"]["y0"] == 2018 and recorded["pts"]["y1"] == 2021
    assert recorded["pts"]["value_column"] == "val_real_ipca_brl"
    assert recorded["ov"]["source"] == "ibge_pevs"
    # No `sidraTabela` in the summary → None = every table, which is what the
    # reader emitted before the axis existed. The axis must be opt-IN, never a default
    # that silently narrows an unfiltered panel to one half.
    assert recorded["ov"]["sidra_tabela"] is None
    # overview carries the q_mass summed from product_ts' per-family q_mass column.
    assert float(out["overview_ts"].loc[0, "q_mass"]) == 2e3
    assert out["value_column"] == "val_real_ipca_brl"


def test_snapshot_comtrade_uses_comtrade_overview_and_no_geo(monkeypatch):
    """COMTRADE snapshot: routes to fetch_comtrade_overview (cmd_codes), renames
    total_value_usd→total_value, and carries no per-UF geography (uf_data None)."""
    seam = _seam()
    recorded = {}

    def fake_overview(
        year_start=None,
        year_end=None,
        cmd_codes=(),
        flow=None,
        customs=None,
        market=None,
        value_column=None,
    ):
        recorded["cmd_codes"] = cmd_codes
        recorded["value_column"] = value_column
        recorded["customs"] = customs  # the regime filter reaches the comtrade overview
        recorded["market"] = market  # the market-nature filter reaches it too
        return pd.DataFrame([{"reference_year": 2022, "total_value_usd": 4.0}])

    monkeypatch.setattr(seam.gateway, "fetch_products", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_source", lambda source=None: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_product_timeseries", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_comtrade_overview", fake_overview)
    monkeypatch.setattr(seam.gateway, "fetch_quality_timeseries", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_product", lambda b: pd.DataFrame())

    out = seam.snapshot(
        "un_comtrade", {"currency": "USD", "correction": "Nominal"}, {"basket": ["080121"]}
    )
    assert recorded["cmd_codes"] == ("080121",)
    # The requested currency×correction now drives the overview measure (the trade
    # mart carries the full matrix) instead of being hard-locked to USD.
    assert recorded["value_column"] == "val_yearfx_usd"
    assert out["uf_data"] is None and out["uf_yearly"] is None
    assert "total_value" in out["overview_ts"].columns
    assert float(out["overview_ts"].loc[0, "total_value"]) == 4.0


def test_snapshot_comtrade_threads_customs_and_market_to_productts(monkeypatch):
    """The regime (customs) + tipo-de-mercado (market) filters must reach the COMTRADE
    productTS reader — NOT only the overview — because the views recompute every
    displayed value from productTS, so a filter that skipped it would leave the charts
    showing all-regime totals (audit HIGH finding). COMEX (which has neither dimension)
    must NOT receive them."""
    seam = _seam()
    recorded = {}

    def fake_pts(*a, **k):
        recorded["customs"] = k.get("customs", "MISSING")
        recorded["market"] = k.get("market", "MISSING")
        return pd.DataFrame()

    monkeypatch.setattr(seam.gateway, "fetch_products", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_source", lambda source=None: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_product_timeseries", fake_pts)
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comtrade_overview",
        lambda **k: pd.DataFrame([{"reference_year": 2022, "total_value_usd": 4.0}]),
    )
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comex_overview",
        lambda **k: pd.DataFrame([{"reference_year": 2022, "total_value_usd": 4.0}]),
    )
    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf", lambda **k: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf_yearly", lambda **k: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_timeseries", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_product", lambda b: pd.DataFrame())

    conv = {"currency": "USD", "correction": "Nominal"}
    seam.snapshot("un_comtrade", conv, {"customs": "C01", "market": "consumo"})
    assert recorded["customs"] == "C01"
    assert recorded["market"] == "consumo"

    # COMEX has neither dimension → the productTS reader must not receive them.
    seam.snapshot("mdic_comex", conv, {"customs": "C01", "market": "consumo"})
    assert recorded["customs"] == "MISSING"
    assert recorded["market"] == "MISSING"


def test_snapshot_comtrade_customs_all_and_absent_resolve_to_none(monkeypatch):
    """'all'/absent customs+market both → None on productTS (sum every regime/purpose),
    so an unfiltered COMTRADE request is byte-identical to before those dims existed."""
    seam = _seam()
    recorded = {}

    def fake_pts(*a, **k):
        recorded["customs"] = k.get("customs", "MISSING")
        recorded["market"] = k.get("market", "MISSING")
        return pd.DataFrame()

    monkeypatch.setattr(seam.gateway, "fetch_products", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_source", lambda source=None: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_product_timeseries", fake_pts)
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comtrade_overview",
        lambda **k: pd.DataFrame([{"reference_year": 2022, "total_value_usd": 4.0}]),
    )
    monkeypatch.setattr(seam.gateway, "fetch_quality_timeseries", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_product", lambda b: pd.DataFrame())

    conv = {"currency": "USD", "correction": "Nominal"}
    seam.snapshot("un_comtrade", conv, {"customs": "all", "market": "all"})
    assert recorded["customs"] is None and recorded["market"] is None

    seam.snapshot("un_comtrade", conv, None)
    assert recorded["customs"] is None and recorded["market"] is None


def test_snapshot_comex_brl_request_serves_real_brl_column_not_usd(monkeypatch):
    """The mock-FX regression fix: a BRL display on COMEX must thread the REAL
    year-FX BRL column into EVERY value reader (overview, productTS, by-UF, year×UF)
    — never the USD column the frontend would then cross-convert via a mock rate."""
    seam = _seam()
    recorded = {}

    def fake_overview(year_start=None, year_end=None, ncm_codes=(), flow=None, value_column=None):
        recorded["overview"] = value_column
        return pd.DataFrame([{"reference_year": 2022, "total_value_usd": 7.0}])

    def fake_by_uf(year_start=None, year_end=None, ncm_codes=(), flow=None, value_column=None):
        recorded["uf"] = value_column
        return pd.DataFrame([{"state_acronym": "SP", "total_value_usd": 3.0}])

    def fake_by_uf_yearly(
        year_start=None, year_end=None, ncm_codes=(), flow=None, value_column=None
    ):
        recorded["uf_yearly"] = value_column
        return pd.DataFrame(
            [{"state_acronym": "SP", "reference_year": 2022, "total_value_usd": 3.0}]
        )

    def fake_pts(
        source, year_start=None, year_end=None, codes=(), value_column=None, uf_codes=(), flow=None
    ):
        recorded["pts"] = value_column
        return pd.DataFrame()

    monkeypatch.setattr(seam.gateway, "fetch_products", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_source", lambda source=None: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_product_timeseries", fake_pts)
    monkeypatch.setattr(seam.gateway, "fetch_comex_overview", fake_overview)
    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf", fake_by_uf)
    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf_yearly", fake_by_uf_yearly)
    monkeypatch.setattr(seam.gateway, "fetch_quality_timeseries", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_product", lambda b: pd.DataFrame())

    out = seam.snapshot("mdic_comex", {"currency": "BRL", "correction": "Nominal"})
    assert recorded["overview"] == "val_yearfx_brl"
    assert recorded["uf"] == "val_yearfx_brl"
    assert recorded["uf_yearly"] == "val_yearfx_brl"
    assert recorded["pts"] == "val_yearfx_brl"
    # The value_column the snapshot reports is the real BRL column (no USD-derived
    # mock conversion), and the label states R$ + the FOB customs basis.
    assert out["value_column"] == "val_yearfx_brl"
    assert "R$" in out["value_label"] and "FOB" in out["value_label"]


def test_with_overview_quantities_none_when_product_ts_has_no_quantity_columns():
    """When product_ts lacks the q_mass/q_vol columns (or is empty), q_mass/q_vol
    fall back to None rather than crashing the groupby."""
    seam = _seam()
    overview = pd.DataFrame([{"reference_year": 2022, "total_value": 1.0}])
    out = seam._with_overview_quantities(overview, pd.DataFrame([{"reference_year": 2022}]))
    assert out.loc[0, "q_mass"] is None and out.loc[0, "q_vol"] is None


def test_with_overview_quantities_passthrough_on_empty_overview():
    seam = _seam()
    empty = pd.DataFrame()
    assert seam._with_overview_quantities(empty, pd.DataFrame()).empty
    assert seam._with_overview_quantities(None, None) is None


# ── source_meta / product_uf_ranking ──────────────────────────────────────────


def test_source_meta_returns_first_row_dict(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_source_metadata",
        lambda source=None: pd.DataFrame([{"source": "ibge_pevs", "rows": 100}]),
    )
    monkeypatch.setattr(seam.gateway, "fetch_banco_metadata", lambda banco_id: pd.DataFrame())
    meta = seam.source_meta("ibge_pevs")
    # The provenance row is preserved verbatim...
    assert meta["source"] == "ibge_pevs" and meta["rows"] == 100
    # ...and augmented with the latest-year completeness signal (annual banco, no
    # year_end in this fixture → trivially complete, no months query).
    assert meta["latest_year_complete"] is True
    assert meta["months_in_latest_year"] is None
    # ...and the lifecycle maturity, sourced SOLELY from the BQ override table:
    # an empty override row means no maturity (the registry carries none anymore).
    assert meta["maturity"] is None


def test_source_meta_no_gold_provenance_for_absent_or_non_live(monkeypatch):
    """A non-live banco or an empty metadata row carries NO Gold provenance (no
    rows/year span). Maturity still comes solely from BigQuery — with no override
    row mocked here, that is None (the registry no longer provides a fallback)."""
    seam = _seam()
    monkeypatch.setattr(seam.gateway, "fetch_banco_metadata", lambda banco_id: pd.DataFrame())
    out = seam.source_meta("sefaz_nf")  # non-live: no Gold table
    assert "rows" not in out and out.get("maturity") is None
    monkeypatch.setattr(seam.gateway, "fetch_source_metadata", lambda source=None: pd.DataFrame())
    out2 = seam.source_meta("ibge_pevs")  # empty provenance row
    assert "rows" not in out2 and out2.get("maturity") is None


def test_source_meta_annual_banco_latest_year_always_complete(monkeypatch):
    """An annual banco (PEVS) has no month grain: its latest year is complete by
    construction (no months query is issued) — FINDING #3."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_source_metadata",
        lambda source=None: pd.DataFrame([{"source": "ibge_pevs", "year_end": 2024}]),
    )
    monkeypatch.setattr(seam.gateway, "fetch_banco_metadata", lambda banco_id: pd.DataFrame())
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comex_months_per_year",
        lambda: pytest.fail("annual banco must not query the monthly mart"),
    )
    meta = seam.source_meta("ibge_pevs")
    assert meta["latest_year_complete"] is True
    assert meta["months_in_latest_year"] is None
    assert meta["latest_complete_year"] == 2024


def test_source_meta_comex_partial_latest_year_flags_incomplete(monkeypatch):
    """COMEX 2026 has < 12 months → the latest year is PARTIAL; latest_complete_year
    falls back to 2025 so the frontend anchors YoY on the last full year."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_source_metadata",
        lambda source=None: pd.DataFrame([{"source": "mdic_comex", "year_end": 2026}]),
    )
    monkeypatch.setattr(seam.gateway, "fetch_banco_metadata", lambda banco_id: pd.DataFrame())
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comex_months_per_year",
        lambda: pd.DataFrame(
            [{"reference_year": 2025, "n_months": 12}, {"reference_year": 2026, "n_months": 5}]
        ),
    )
    meta = seam.source_meta("mdic_comex")
    assert meta["months_in_latest_year"] == 5
    assert meta["latest_year_complete"] is False
    assert meta["latest_complete_year"] == 2025


def test_source_meta_comex_full_latest_year_is_complete(monkeypatch):
    """A COMEX year with all 12 months is complete; latest_complete_year == year_end."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_source_metadata",
        lambda source=None: pd.DataFrame([{"source": "mdic_comex", "year_end": 2024}]),
    )
    monkeypatch.setattr(seam.gateway, "fetch_banco_metadata", lambda banco_id: pd.DataFrame())
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comex_months_per_year",
        lambda: pd.DataFrame([{"reference_year": 2024, "n_months": 12}]),
    )
    meta = seam.source_meta("mdic_comex")
    assert meta["months_in_latest_year"] == 12
    assert meta["latest_year_complete"] is True
    assert meta["latest_complete_year"] == 2024


def test_source_meta_unknown_banco_does_not_leak_pevs_cobertura(monkeypatch):
    """An UNKNOWN banco id must NOT inherit PEVS's static cobertura. banco_by_id silently
    falls back to PEVS, which previously stamped PEVS's coverage onto a nonexistent banco;
    the fix resolves WITHOUT that fallback so cobertura stays None (audit finding)."""
    seam = _seam()
    monkeypatch.setattr(seam.gateway, "fetch_banco_metadata", lambda banco_id: pd.DataFrame())
    meta = seam.source_meta("qualquer-coisa-inexistente")
    assert meta.get("cobertura") is None
    assert meta.get("maturity") is None


def test_source_meta_comex_unobserved_month_count_is_treated_complete(monkeypatch):
    """When the monthly mart has NO row for year_end (n_months unobserved — e.g. it lags
    gold_source_metadata after a partial rebuild), we have no evidence the year is partial,
    so it is treated as trivially complete: latest_complete_year stays year_end and the YoY
    anchor is NOT shifted back (matches the documented guard, audit finding)."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_source_metadata",
        lambda source=None: pd.DataFrame([{"source": "mdic_comex", "year_end": 2026}]),
    )
    monkeypatch.setattr(seam.gateway, "fetch_banco_metadata", lambda banco_id: pd.DataFrame())
    # Mart only knows 2025 — 2026 (the metadata year_end) has no month-count row.
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comex_months_per_year",
        lambda: pd.DataFrame([{"reference_year": 2025, "n_months": 12}]),
    )
    meta = seam.source_meta("mdic_comex")
    assert meta["months_in_latest_year"] is None
    assert meta["latest_year_complete"] is True
    assert meta["latest_complete_year"] == 2026


def test_source_meta_override_flips_maturity_and_coverage(monkeypatch):
    """An override row in research_inputs.banco_metadata wins over the registry —
    the no-redeploy Console flip (beta→estavel) + a new note/coverage. NULL columns
    (here maturity_date) are dropped, so they fall back to the registry default."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_source_metadata",
        lambda source=None: pd.DataFrame([{"source": "un_comtrade", "year_end": 2024}]),
    )
    monkeypatch.setattr(
        seam.gateway,
        "fetch_banco_metadata",
        lambda banco_id: pd.DataFrame(
            [
                {
                    "maturity": "manutencao",  # differs from the estavel registry default
                    "maturity_note": "Em correção.",
                    "maturity_date": None,  # NULL → stripped → registry default stands
                    "cobertura_years": "1997 → presente",
                    "cobertura_atualizacao": None,
                    "cobertura_granularidade": None,
                }
            ]
        ),
    )
    meta = seam.source_meta("un_comtrade")
    assert meta["maturity"] == "manutencao"  # override beats the registry default (estavel)
    assert meta["maturity_note"] == "Em correção."
    assert meta["cobertura"]["years"] == "1997 → presente"  # overridden field
    assert meta["cobertura"]["granularidade"]  # NULL override → registry default kept


def test_source_meta_override_table_absent_yields_no_maturity(monkeypatch):
    """A missing override table (NotFound) is 'no overrides'. Maturity lives ONLY in
    BigQuery now (the registry carries none), so an absent table → maturity None."""
    from google.api_core.exceptions import NotFound

    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_source_metadata",
        lambda source=None: pd.DataFrame([{"source": "un_comtrade", "year_end": 2023}]),
    )

    def _raise(banco_id):
        raise NotFound("table not found")

    monkeypatch.setattr(seam.gateway, "fetch_banco_metadata", _raise)
    meta = seam.source_meta("un_comtrade")
    assert meta["maturity"] is None  # BQ is the single source; no registry fallback


def test_product_uf_ranking_pevs_and_comex(monkeypatch):
    seam = _seam()
    recorded = {}

    def fake_prod(**k):
        recorded["pevs"] = k
        return pd.DataFrame([{"state_acronym": "PA", "total_value": 5.0}])

    def fake_comex(**k):
        recorded["comex"] = k
        return pd.DataFrame([{"state_acronym": "SP", "total_value_usd": 7.0}])

    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf", fake_prod)
    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf", fake_comex)
    pevs = seam.product_uf_ranking("ibge_pevs", "1", {"currency": "BRL", "correction": "IPCA"})
    assert recorded["pevs"]["product_codes"] == ("1",)
    assert list(pevs["state_acronym"]) == ["PA"]
    comex = seam.product_uf_ranking("mdic_comex", "0801", {})
    assert recorded["comex"]["ncm_codes"] == ("0801",)
    assert list(comex["state_acronym"]) == ["SP"]


def test_product_uf_ranking_none_without_geo(monkeypatch):
    seam = _seam()
    # COMTRADE has no 'geo' capability → ranking is unavailable.
    assert seam.product_uf_ranking("un_comtrade", "080121", {}) is None
    assert seam.product_uf_ranking("sefaz_nfe", "1", {}) is None


# ── productivity: crops list, default-crop fallback, None without yield ────────


def test_productivity_defaults_to_first_crop_when_requested_absent(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_products",
        lambda b: pd.DataFrame([{"code": "2713", "name": "Café"}, {"code": "9", "name": "Soja"}]),
    )
    monkeypatch.setattr(
        seam.gateway,
        "fetch_productivity",
        lambda *a, **k: pd.DataFrame(columns=["reference_year", "state_acronym"]),
    )
    out = seam.productivity("ibge_pam", "nonexistent")
    assert out["active"] == "2713" and out["active_name"] == "Café"
    assert {c["code"] for c in out["crops"]} == {"2713", "9"}


def test_productivity_none_when_banco_lacks_yield():
    seam = _seam()
    # PEVS has no 'yield' capability.
    assert seam.productivity("ibge_pevs", "1") is None


def test_ppm_is_live_production_shaped_without_yield():
    """PPM is a live, PEVS-shaped production source: in _LIVE_SOURCES, NOT a trade
    source, and (livestock → no planted area) has no productivity/'yield'."""
    from embrapa_dashboard.webapi import seam, seam_base

    assert "ibge_ppm" in seam_base._LIVE_SOURCES
    assert "ibge_ppm" not in seam._TRADE  # BRL-native production, not origin→dest flow
    assert "ibge_ppm" not in seam._MONTHLY_SOURCES  # annual, like PEVS/PAM
    assert _seam().productivity("ibge_ppm", None) is None


def test_source_registries_have_no_live_drift():
    """Drift guard across the parallel source registries. A banco with a Gold product table
    (``gateway._PRODUCT_SOURCES``) or inspectable tables (``gateway._INSPECT_TABLES``) that is
    NOT in ``seam_base._LIVE_SOURCES`` would be SILENTLY dead end-to-end: every seam reader
    early-returns ``None``/``[]`` for a non-live banco, so its dashboard surface — including the
    'Dados' view — vanishes even though the gateway supports it. This invariant (every data
    source / inspectable banco is live) fails LOUDLY the moment a future banco is added to one
    registry but forgotten in ``_LIVE_SOURCES`` — the exact class of regression that the
    'PPM is gated off' report mistook for a live bug (it had already been wired in #147)."""
    from embrapa_dashboard.serving import gateway
    from embrapa_dashboard.webapi import seam_base

    live = set(seam_base._LIVE_SOURCES)
    product = set(gateway._PRODUCT_SOURCES)
    inspectable = set(gateway._INSPECT_TABLES)

    # every banco with a Gold product table must be live (else overview/geo/… early-return None)
    assert product <= live, f"product sources missing from _LIVE_SOURCES: {product - live}"
    # every inspectable banco must be live (else seam.inspectable_tables returns [] despite the
    # gateway allowlist — the 'Dados' view would silently disappear for that banco)
    assert inspectable <= live, (
        f"inspectable bancos missing from _LIVE_SOURCES: {inspectable - live}"
    )
    # ibge_ppm (live since v1.3.0 / #147) must be present in all three
    assert {"ibge_ppm"} <= product & inspectable & live


def test_productivity_none_when_no_crops(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(seam.gateway, "fetch_products", lambda b: pd.DataFrame())
    assert seam.productivity("ibge_pam", None) is None


# ── partner_data / monthly_data: capability gating + dispatch ──────────────────


def test_partner_data_dispatches_by_banco(monkeypatch):
    seam = _seam()
    recorded = {}
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comex_partners",
        lambda **k: recorded.setdefault("comex", k) or pd.DataFrame([{"country_code": "156"}]),
    )
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comtrade_partners",
        lambda **k: recorded.setdefault("comtrade", k) or pd.DataFrame([{"partner_code": "156"}]),
    )
    seam.partner_data("mdic_comex", {"basket": ["0801"], "startDate": "2019", "endDate": "2021"})
    assert recorded["comex"]["ncm_codes"] == ("0801",)
    assert recorded["comex"]["year_start"] == 2019 and recorded["comex"]["year_end"] == 2021
    seam.partner_data("un_comtrade", {"basket": ["080121"]})
    assert recorded["comtrade"]["cmd_codes"] == ("080121",)


def test_partner_data_none_without_partner_capability():
    seam = _seam()
    assert seam.partner_data("ibge_pevs") is None


def test_products_by_uf_gates_on_uf_and_dispatches_by_banco(monkeypatch):
    """products_by_uf returns None without a UF selection, and dispatches to the
    right mart/columns/flow per banco when a UF is selected."""
    seam = _seam()
    recorded = {}
    monkeypatch.setattr(
        seam.gateway,
        "fetch_products_by_uf",
        lambda **k: recorded.update(k) or pd.DataFrame([{"product_code": "4407"}]),
    )
    # No UF → None (Visão geral already covers the nationwide product ranking)
    assert seam.products_by_uf("mdic_comex", {}) is None
    assert seam.products_by_uf("mdic_comex", {"states": []}) is None
    # COMEX export form: USD/Nominal → val_yearfx_usd, flow=export, UF pushed down
    out = seam.products_by_uf(
        "mdic_comex",
        {"states": ["AC"], "basket": ["4407"]},
        {"currency": "USD", "correction": "Nominal"},
    )
    assert out is not None
    assert recorded["table_key"] == "serving_comex_annual"
    assert recorded["code_column"] == "ncm_code" and recorded["name_column"] == "ncm_description"
    assert recorded["flow"] == "export"
    assert recorded["uf_codes"] == ("AC",) and recorded["codes"] == ("4407",)
    assert recorded["value_column"] == "val_yearfx_usd"
    assert recorded.get("include_sidra_tabela") in (None, False), (
        "o COMEX não tem coluna origem — pedi-la quebraria a consulta"
    )
    # PEVS production form: product columns, NO flow predicate
    recorded.clear()
    seam.products_by_uf("ibge_pevs", {"states": ["PA"]})
    assert recorded["table_key"] == "serving_pevs_annual"
    assert recorded["code_column"] == "product_code"
    assert recorded.get("flow") is None
    # E a METADE viaja junto: madeira, lenha e carvão existem nas duas com o MESMO nome, e
    # sem a coluna a tela funde duas linhas legítimas numa barra só (o Plotly junta
    # categorias homônimas). Só o PEVS a tem — pedi-la no COMEX quebraria a consulta.
    assert recorded["include_sidra_tabela"] is True


def test_products_by_uf_none_without_geo_capability():
    seam = _seam()
    # un_comtrade has no `geo` (origin is a reporter country, not a UF)
    assert seam.products_by_uf("un_comtrade", {"states": ["AC"]}) is None


def test_monthly_data_comex_only(monkeypatch):
    seam = _seam()
    recorded = {}
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comex_seasonality",
        lambda **k: recorded.update(k) or pd.DataFrame([{"month": 1, "value_usd": 5.0}]),
    )
    out = seam.monthly_data("mdic_comex", {"basket": ["0801"]})
    assert recorded["ncm_codes"] == ("0801",)
    assert not out.empty
    # COMTRADE has no monthly grain capability.
    assert seam.monthly_data("un_comtrade") is None
    assert seam.monthly_data("ibge_pevs") is None


# ── cross_metric_refs / cross_series ───────────────────────────────────────────


def test_cross_metric_refs_lists_only_known_display_unit_metrics():
    seam = _seam()
    refs = seam.cross_metric_refs()
    keys = {f"{r['banco']}:{r['metric']}" for r in refs}
    assert keys <= set(seam.CROSS_DISPLAY_UNIT)
    assert "ibge_pevs:prod_value" in keys
    assert "mdic_comex:exp_price" in keys  # derived metric is offered
    assert "un_comtrade:world_exp" in keys


def test_cross_series_none_for_unknown_metric():
    seam = _seam()
    assert seam.cross_series("ibge_pevs", "not_a_metric") is None
    assert seam.cross_series("sefaz_nfe", "exp_value") is None


def test_cross_series_pevs_prod_value_scales_to_bi(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_production_overview",
        lambda **k: pd.DataFrame([{"reference_year": 2020, "total_value": 5e9}]),
    )
    out = seam.cross_series("ibge_pevs", "prod_value", 2020, 2020)
    assert out["unit"] == "R$ bi"
    assert out["points"] == [{"y": 2020, "v": 5.0}]


def test_cross_series_pevs_prod_mass_filters_family_and_scales(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_product_timeseries",
        lambda *a, **k: pd.DataFrame(
            [
                {"reference_year": 2020, "total_qty_native": 4e3, "family": "massa"},
                {"reference_year": 2020, "total_qty_native": 9e6, "family": "volume"},
            ]
        ),
    )
    out = seam.cross_series("ibge_pevs", "prod_mass", 2020, 2020)
    assert out["unit"] == "mil t"
    assert out["points"] == [{"y": 2020, "v": 4.0}]  # 4e3 t / 1e3 — volume excluded


def test_cross_series_comex_exp_value_scales_to_bi(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_cross_series",
        lambda metric, year_start=None, year_end=None, codes=(), uf_codes=(): pd.DataFrame(
            [{"reference_year": 2022, "value": 3e9}]
        ),
    )
    out = seam.cross_series("mdic_comex", "exp_value", 2022, 2022)
    assert out["unit"] == "US$ bi" and out["points"] == [{"y": 2022, "v": 3.0}]


# ── _pevs_mass_by_year / _is_mass_basis ────────────────────────────────────────


def test_pevs_mass_by_year_scales_t_to_mil_t(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_product_timeseries",
        lambda *a, **k: pd.DataFrame(
            [
                {"reference_year": 2020, "total_qty_native": 5e3},
                {"reference_year": 2020, "total_qty_native": 1e3},
            ]
        ),
    )
    assert seam._pevs_mass_by_year(("1",)) == {2020: 6.0}  # (5e3 + 1e3) / 1e3


def test_pevs_mass_by_year_empty(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(seam.gateway, "fetch_product_timeseries", lambda *a, **k: pd.DataFrame())
    assert seam._pevs_mass_by_year(()) == {}


def test_is_mass_basis_true_only_for_pure_massa(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        _cross(),
        "_pevs_family_by_agrupamento",
        lambda: {"castanha": {"massa"}, "madeira": {"volume"}, "*": {"massa", "volume"}},
    )
    assert seam._is_mass_basis("castanha") is True
    assert seam._is_mass_basis("madeira") is False
    assert seam._is_mass_basis(None) is False  # the "*" all-products basket is mixed


# ── market_share / price_spread / trade_mirror: happy paths ───────────────────


def test_market_share_happy_path_with_by_product(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {
            "castanha": {
                "name": "Castanha",
                "comex": ["0801"],
                "comtrade": ["080121"],
                "pevs": ["1"],
            }
        },
    )

    def fake_xyear(metric, codes, uf_codes=()):
        return {2022: 2e9} if metric.startswith("mdic_comex") else {2022: 8e9}

    monkeypatch.setattr(_base(), "_xyear", fake_xyear)
    # No world reporter-count query in this unit test → no completeness clamp.
    monkeypatch.setattr(_cross(), "_world_latest_complete_year", lambda: None)
    out = seam.market_share("castanha")
    assert out["unit"] == "US$ bi"
    row = out["series"][0]
    assert row["y"] == 2022 and row["br"] == 2.0 and row["world"] == 8.0
    assert row["share"] == pytest.approx(25.0)  # 2 / 8 * 100
    assert out["by_product"][0]["code"] == "castanha"
    assert out["by_product"][0]["share"] == pytest.approx(25.0)


def test_price_spread_happy_path_markup(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(_cross(), "_is_mass_basis", lambda cid: True)
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {
            "castanha": {
                "name": "Castanha",
                "comex": ["0801"],
                "comtrade": ["080121"],
                "pevs": ["1"],
            }
        },
    )
    # FOB = 6e9 US$ / 2e9 kg = 3 US$/kg
    monkeypatch.setattr(
        _base(),
        "_xyear",
        lambda metric, codes, uf_codes=(): (
            {2022: 6e9} if metric.endswith("exp_value") else {2022: 2e9}
        ),
    )
    # gate = value(US$) / (q(t) * 1000) = 2e6 / (1e3 * 1000) = 2 US$/kg
    monkeypatch.setattr(
        seam.gateway,
        "fetch_product_timeseries",
        lambda *a, **k: pd.DataFrame(
            [{"reference_year": 2022, "total_value": 2e6, "total_qty_native": 1e3}]
        ),
    )
    out = seam.price_spread("castanha")
    assert out["unit"] == "US$/kg"
    row = out["series"][0]
    assert row["y"] == 2022
    assert row["fob"] == pytest.approx(3.0) and row["gate"] == pytest.approx(2.0)
    assert row["spread"] == pytest.approx(1.0)
    assert row["markup"] == pytest.approx(1.5)


def test_price_spread_incompatible_for_volume_basis(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(_cross(), "_is_mass_basis", lambda cid: False)
    out = seam.price_spread("madeira")
    assert out == {"unit": "US$/kg", "incompatible": True, "series": []}


def test_export_coefficient_incompatible_for_volume_basis(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(_cross(), "_is_mass_basis", lambda cid: False)
    out = seam.export_coefficient("madeira")
    assert out["incompatible"] is True and out["by_uf"] == []


def test_export_coefficient_empty_timeseries_when_no_year_overlap(monkeypatch):
    """Mass basis + codes present, but PEVS and COMEX share no year → empty."""
    seam = _seam()
    monkeypatch.setattr(_cross(), "_is_mass_basis", lambda cid: True)
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {"c": {"name": "C", "pevs": ["1"], "comex": ["0801"], "comtrade": ["080121"]}},
    )
    monkeypatch.setattr(_cross(), "_pevs_mass_by_year", lambda codes, uf_codes=(): {1986: 5.0})
    monkeypatch.setattr(_base(), "_xyear", lambda metric, codes, uf_codes=(): {2022: 1e6})
    out = seam.export_coefficient("c")
    assert out == {
        "unit": "mil t",
        "by_uf": [],
        "national": {},
        "timeseries": [],
        "states": [],
    }


# ── The three readers that used to IGNORE the UF filter ───────────────────────
# Their maps showed all 27 states while the rest of the session was narrowed to the
# researcher's selection — the "displayed value computed over a different dataset
# than the filter" the geography audit removed everywhere else.


def test_product_uf_ranking_threads_states_to_the_production_gateway(monkeypatch):
    seam = _seam()
    recorded = {}

    def fake(**kw):
        recorded.update(kw)
        return pd.DataFrame()

    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf", fake)
    seam.product_uf_ranking(
        "ibge_pevs", "3405", {"currency": "BRL", "correction": "IPCA"}, {"states": ["PA", "AM"]}
    )
    assert tuple(recorded["uf_codes"]) == ("PA", "AM")
    assert recorded["product_codes"] == ("3405",)


def test_product_uf_ranking_threads_states_on_the_comex_path(monkeypatch):
    """The COMEX branch keeps its export-only pin AND gains the UF scope."""
    seam = _seam()
    recorded = {}

    def fake(**kw):
        recorded.update(kw)
        return pd.DataFrame()

    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf", fake)
    seam.product_uf_ranking(
        "mdic_comex", "08012100", {"currency": "USD", "correction": "Nominal"}, {"states": ["MT"]}
    )
    assert tuple(recorded["uf_codes"]) == ("MT",)
    assert recorded["flow"] == "export"


def test_product_uf_ranking_sends_no_uf_scope_without_a_state_filter(monkeypatch):
    seam = _seam()
    recorded = {}

    def fake(**kw):
        recorded.update(kw)
        return pd.DataFrame()

    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf", fake)
    seam.product_uf_ranking("ibge_pevs", "3405", {"currency": "BRL", "correction": "IPCA"}, None)
    assert tuple(recorded["uf_codes"]) == ()


def test_productivity_threads_states_and_echoes_them_back(monkeypatch):
    """Yield is a RATIO, so narrowing the rows changes the aggregate the serializer
    recomputes — the 'national' trajectory becomes the selected states'. The seam
    echoes `states` so the view can relabel instead of calling a subset national."""
    seam = _seam()
    recorded = {}

    monkeypatch.setattr(
        seam.gateway,
        "fetch_products",
        lambda banco_id: pd.DataFrame([{"code": "2713", "name": "Café"}]),
    )

    def fake_productivity(
        product_code, source="ibge_pam", year_start=None, year_end=None, uf_codes=()
    ):
        recorded.update(uf_codes=uf_codes)
        return pd.DataFrame(columns=["reference_year", "state_acronym"])

    monkeypatch.setattr(seam.gateway, "fetch_productivity", fake_productivity)
    out = seam.productivity("ibge_pam", "2713", {"states": ["MG", "SP"]})
    assert tuple(recorded["uf_codes"]) == ("MG", "SP")
    assert out["states"] == ["MG", "SP"]


def test_export_coefficient_narrows_BOTH_sides_of_the_ratio(monkeypatch):
    """The decisive one: production AND exports must be scoped together. Narrowing
    only the production half would divide the selected states' output by the WHOLE
    country's exports and silently deflate the coefficient — a wrong ratio, not a
    smaller one."""
    seam = _seam()
    monkeypatch.setattr(_cross(), "_is_mass_basis", lambda cid: True)
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {
            "castanha": {
                "name": "Castanha",
                "pevs": ["3405"],
                "comex": ["08012100"],
                "comtrade": ["080121"],
            }
        },
    )
    seen = {}

    def fake_mass(codes, uf_codes=()):
        seen["pevs_uf"] = tuple(uf_codes)
        return {2000: 10.0}

    def fake_xyear(metric, codes, uf_codes=()):
        seen["comex_uf"] = tuple(uf_codes)
        return {2000: 4e9}

    monkeypatch.setattr(_cross(), "_pevs_mass_by_year", fake_mass)
    monkeypatch.setattr(_base(), "_xyear", fake_xyear)

    def fake_prod(**kw):
        seen["prod_uf"] = tuple(kw.get("uf_codes") or ())
        return pd.DataFrame(
            [{"state_acronym": "PA", "state_name": "Pará", "region_abbrev": "N", "total_value": 1}]
        )

    def fake_exp(**kw):
        seen["exp_uf"] = tuple(kw.get("uf_codes") or ())
        return pd.DataFrame([{"state_acronym": "PA", "total_weight_kg": 1}])

    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf", fake_prod)
    monkeypatch.setattr(seam.gateway, "fetch_comex_by_uf", fake_exp)

    out = seam.export_coefficient("castanha", ("PA",))
    # Every one of the four readers behind the ratio carries the same UF scope.
    assert seen["pevs_uf"] == ("PA",)
    assert seen["comex_uf"] == ("PA",)
    assert seen["prod_uf"] == ("PA",)
    assert seen["exp_uf"] == ("PA",)
    # And the scope is echoed so the view can relabel its "nacional" figures.
    assert out["states"] == ["PA"]


def test_trade_mirror_happy_path_discrepancy(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {
            "castanha": {
                "name": "Castanha",
                "comex": ["0801"],
                "comtrade": ["080121"],
                "pevs": ["1"],
            }
        },
    )

    def fake_xyear(metric, codes, uf_codes=()):
        if metric.startswith("mdic_comex"):
            return {2022: 4e9}
        if metric == "un_comtrade:partner_exp":
            return {2022: 7e9}
        return {2022: 6e9}

    monkeypatch.setattr(_base(), "_xyear", fake_xyear)
    out = seam.trade_mirror("castanha")
    # The third "Reportado pelos parceiros" line (partner=Brazil on imports) must
    # be present so ViewMirror's third series gets data, per the contract.
    assert out["series"][0] == {"y": 2022, "mdic": 4.0, "comtrade": 6.0, "partners": 7.0}
    # |4-6| / ((4+6)/2) * 100 = 2 / 5 * 100 = 40
    assert out["discrepancy"][0]["v"] == pytest.approx(40.0)


def test_trade_mirror_partners_none_when_no_partner_data(monkeypatch):
    """A year present in mdic & comtrade but missing partner-reported data carries
    partners=None (the front end renders a gap, not a fabricated zero)."""
    seam = _seam()
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {
            "castanha": {
                "name": "Castanha",
                "comex": ["0801"],
                "comtrade": ["080121"],
                "pevs": ["1"],
            }
        },
    )

    def fake_xyear(metric, codes, uf_codes=()):
        if metric.startswith("mdic_comex"):
            return {2022: 4e9}
        if metric == "un_comtrade:partner_exp":
            return {}
        return {2022: 6e9}

    monkeypatch.setattr(_base(), "_xyear", fake_xyear)
    out = seam.trade_mirror("castanha")
    assert out["series"][0] == {"y": 2022, "mdic": 4.0, "comtrade": 6.0, "partners": None}


# ── Curadoria reads: attribute_editor_emails, worklist, current code levels ────────────


def test_attribute_editor_emails_lowercases_and_strips(monkeypatch):
    seam = _seam()
    # The gateway query filters `where email is not null`, so emails arrive as
    # non-null strings; the seam lowercases + strips them.
    monkeypatch.setattr(
        seam.gateway,
        "fetch_attribute_editors",
        lambda: pd.DataFrame([{"email": " Alice@EMBRAPA.br "}, {"email": "bob@x.org"}]),
    )
    assert seam.attribute_editor_emails() == {"alice@embrapa.br", "bob@x.org"}


def test_attribute_editor_emails_empty_on_notfound(monkeypatch):
    seam = _seam()
    from google.api_core.exceptions import NotFound

    def boom():
        raise NotFound("no allowlist table")

    monkeypatch.setattr(seam.gateway, "fetch_attribute_editors", boom)
    assert seam.attribute_editor_emails() == set()


def test_attribute_editor_emails_propagates_other_errors(monkeypatch):
    """A transient/permission fault must NOT be swallowed into 'open gate'."""
    seam = _seam()

    def boom():
        raise RuntimeError("transient BQ")

    monkeypatch.setattr(seam.gateway, "fetch_attribute_editors", boom)
    with pytest.raises(RuntimeError):
        seam.attribute_editor_emails()


def test_current_code_levels_empty_on_notfound(monkeypatch):
    seam = _seam()
    from google.api_core.exceptions import NotFound

    def boom():
        raise NotFound("scd2 view absent")

    monkeypatch.setattr(seam.gateway, "fetch_current_code_industrialization", boom)
    assert seam._current_code_levels() == {}


def test_curation_worklist_joins_catalog_entries_to_levels(monkeypatch):
    """The worklist reads the SAME live catalog the Curadoria editor uses
    (seam_curation.catalog_worklist) ⟕ the current levels, so the two features share
    banco+código+descrição+agrupamento and PAM/PPM are grouped by commodity."""
    from embrapa_dashboard.webapi import seam_curation

    seam = _seam()
    monkeypatch.setattr(
        _curation(),
        "_current_code_levels",
        lambda: {("mdic_comex", "0801"): "commodity_acondicionada"},
    )
    # The catalog carries banco (short token), codigo_produto, agrupamento, agrupamento_id
    # and both descriptions — a PAM row is included to prove PAM/PPM group by commodity.
    monkeypatch.setattr(
        seam_curation,
        "catalog_worklist",
        lambda: {
            "entries": [
                {
                    "banco": "comex",
                    "codigo_produto": "0801",
                    "agrupamento": "Castanha",
                    "agrupamento_id": "castanha",
                    "descricao_produto": "Castanhas",
                    "descricao_fonte": "Castanhas do Pará",
                },
                {
                    "banco": "comex",
                    "codigo_produto": "0802",
                    "agrupamento": "Castanha",
                    "agrupamento_id": "castanha",
                    "descricao_produto": "Nozes",
                    "descricao_fonte": None,
                },
                {
                    "banco": "pam",
                    "codigo_produto": "40102",
                    "agrupamento": "Arroz",
                    "agrupamento_id": "arroz",
                    "descricao_produto": "Arroz (em casca)",
                    "descricao_fonte": "Arroz",
                },
            ]
        },
    )
    out = seam.curation_worklist()
    assert out["total"] == 3 and out["classified"] == 1 and out["pending"] == 2
    assert out["by_level"]["commodity_acondicionada"] == 1
    classified_row = next(r for r in out["rows"] if r["code"] == "0801")
    assert classified_row["level"] == "commodity_acondicionada"
    assert classified_row["source"] == "mdic_comex"
    assert classified_row["commodity"] == "castanha"
    assert classified_row["agrupamento_nome"] == "Castanha"
    assert classified_row["name"] == "Castanhas do Pará"  # descricao_fonte preferred
    unclassified = next(r for r in out["rows"] if r["code"] == "0802")
    assert unclassified["level"] is None
    assert unclassified["name"] == "Nozes"  # falls back to descricao_produto
    # a PAM entry is present and grouped by its agrupamento (crosswalk lacks PAM/PPM)
    pam_row = next(r for r in out["rows"] if r["source"] == "ibge_pam")
    assert pam_row["commodity"] == "arroz" and pam_row["agrupamento_nome"] == "Arroz"


# ── value_added: empty until codes are classified ──────────────────────────────


def test_value_added_empty_when_nothing_classified(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(_curation(), "_current_code_levels", lambda: {})
    out = seam.value_added()
    assert out == {
        "series": [],
        "levels": [],
        "premium": 0.0,
        "predominant": None,
        "n_codes": 0,
    }


# ── crosswalk-derived indices: _xyear, _code_to_agrupamento, family-by-commodity ─


def test_xyear_maps_year_to_value(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_cross_series",
        lambda metric, codes=(), uf_codes=(): pd.DataFrame(
            [{"reference_year": 2021, "value": 3.0}, {"reference_year": 2022, "value": 5.0}]
        ),
    )
    assert seam._xyear("mdic_comex:exp_value", ("0801",)) == {2021: 3.0, 2022: 5.0}


def test_code_to_agrupamento_reverse_indexes_every_source(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {
            "castanha": {
                "name": "Castanha",
                "pevs": ["1"],
                "comex": ["0801"],
                "comtrade": ["080121"],
            }
        },
    )
    idx = seam._code_to_agrupamento()
    assert idx[("ibge_pevs", "1")] == "castanha"
    assert idx[("mdic_comex", "0801")] == "castanha"
    assert idx[("un_comtrade", "080121")] == "castanha"


def test_pevs_family_by_agrupamento_indexes_run_query(monkeypatch):
    seam = _seam()
    monkeypatch.setattr(_cross(), "get_settings", lambda: Settings(gcp_project_id="p"))
    monkeypatch.setattr(
        seam.gateway,
        "run_query",
        lambda q, p: pd.DataFrame(
            [
                {"cid": "castanha", "family": "massa"},
                {"cid": "madeira", "family": "volume"},
                {"cid": "*", "family": "massa"},
                {"cid": "*", "family": "volume"},
            ]
        ),
    )
    app, cache = _bind_simplecache()
    with app.app_context():
        cache.clear()
        idx = seam._pevs_family_by_agrupamento()
    assert idx["castanha"] == {"massa"}
    assert idx["madeira"] == {"volume"}
    assert idx["*"] == {"massa", "volume"}


def test_produto_catalog_with_family_tags_each_commodity(monkeypatch):
    """The catalog is tagged with each commodity's single PEVS family; a commodity
    with no PEVS side (or a mixed family set) collapses to None, so the family-gated
    export-coefficient / price-spread pickers drop it."""
    seam = _seam()
    monkeypatch.setattr(
        _base(),
        "produto_catalog",
        lambda: {
            "castanha": {
                "id": "castanha",
                "name": "Castanha",
                "pevs": ["1"],
                "comex": ["0801"],
                "comtrade": [],
            },
            "madeira": {
                "id": "madeira",
                "name": "Madeira",
                "pevs": ["2"],
                "comex": [],
                "comtrade": [],
            },
            "soja": {
                "id": "soja",
                "name": "Soja",
                "pevs": [],
                "comex": ["1201"],
                "comtrade": [],
            },
        },
    )
    monkeypatch.setattr(
        _cross(),
        "_pevs_family_by_agrupamento",
        lambda: {"castanha": {"massa"}, "madeira": {"volume"}},
    )
    cat = seam.produto_catalog_with_family()
    assert cat["castanha"]["family"] == "massa"  # single mass family
    assert cat["madeira"]["family"] == "volume"  # single volume family
    assert cat["soja"]["family"] is None  # no PEVS side → no family
    assert cat["castanha"]["name"] == "Castanha"  # the rest of the entry survives


# ── curation writers: header capture from the request context ──────────────────


def test_record_code_level_forwards_headers_to_writer(monkeypatch):
    seam = _seam()
    from embrapa_dashboard.serving import attribute_engineering as curation

    captured = {}

    def fake_writer(source, code, level, headers, change_id=None):
        captured.update(source=source, code=code, level=level, headers=headers, change_id=change_id)
        return {"ok": True}

    monkeypatch.setattr(curation, "record_code_industrialization", fake_writer)
    # No request context → headers default to {}.
    out = seam.record_code_level("mdic_comex", "0801", "processada", change_id="abc")
    assert out == {"ok": True}
    assert captured["source"] == "mdic_comex" and captured["level"] == "processada"
    assert captured["headers"] == {} and captured["change_id"] == "abc"


# ── P6: per-UF scoping threads through the cross-source / curated / seasonality seam ──


def test_cross_series_threads_uf_to_uf_capable_readers(monkeypatch):
    """cross_series passes uf_codes to the PEVS production + COMEX cross readers."""
    seam = _seam()
    rec = {}
    monkeypatch.setattr(
        seam.gateway,
        "fetch_production_overview",
        lambda **k: (
            rec.update(pevs=k.get("uf_codes"))
            or pd.DataFrame([{"reference_year": 2020, "total_value": 1e9}])
        ),
    )
    monkeypatch.setattr(
        seam.gateway,
        "fetch_cross_series",
        lambda metric, **k: (
            rec.update(comex=k.get("uf_codes"))
            or pd.DataFrame([{"reference_year": 2020, "value": 2e9}])
        ),
    )
    seam.cross_series("ibge_pevs", "prod_value", 2019, 2021, ("AC",))
    assert rec["pevs"] == ("AC",)
    seam.cross_series("mdic_comex", "exp_value", 2019, 2021, ("AC",))
    assert rec["comex"] == ("AC",)


def test_value_added_threads_uf_to_export_side(monkeypatch):
    """value_added narrows the per-level export split to the UF via _xyear."""
    seam = _seam()
    monkeypatch.setattr(
        _curation(), "_current_code_levels", lambda: {("mdic_comex", "A"): "commodity_pura"}
    )
    seen = []
    monkeypatch.setattr(
        _base(),
        "_xyear",
        lambda metric, codes, uf_codes=(): (
            seen.append(uf_codes) or ({2020: 2e9} if metric.endswith("exp_value") else {2020: 1e9})
        ),
    )
    seam.value_added(None, ("AC",))
    assert seen and all(u == ("AC",) for u in seen)


def test_monthly_data_threads_uf_to_seasonality_reader(monkeypatch):
    """monthly_data now passes the active UF selection to the seasonality reader
    (the mart keeps state_acronym in its grain — P6)."""
    seam = _seam()
    rec = {}
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comex_seasonality",
        lambda **k: rec.update(uf_codes=k.get("uf_codes")) or pd.DataFrame(),
    )
    seam.monthly_data("mdic_comex", {"states": ["AC"]})
    assert rec["uf_codes"] == ("AC",)
    rec.clear()
    seam.monthly_data("mdic_comex", {})  # no UF → national
    assert rec["uf_codes"] == ()


def test_trade_adapters_thread_flow_filter(monkeypatch):
    """The active flow filter reaches the seasonality, Sankey and partner-ranking readers —
    not just /snapshot. Otherwise an 'Importação' selection would render export-dominated
    numbers (COMEX exports ~40x imports) while the filter chips claim the view is scoped."""
    seam = _seam()
    rec = {}
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comex_seasonality",
        lambda **k: rec.update(m=k.get("flow")) or pd.DataFrame(),
    )
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comtrade_flows",
        lambda **k: (
            rec.update(f=k.get("flow"), c=k.get("customs"), mk=k.get("market"))
            or pd.DataFrame(
                columns=["origin_code", "origin_name", "dest_code", "dest_name", "value_usd"]
            )
        ),
    )
    monkeypatch.setattr(
        seam.gateway,
        "fetch_comtrade_partners",
        lambda **k: (
            rec.update(pf=k.get("flow"))
            or pd.DataFrame(columns=["partner_code", "partner_name", "value_usd"])
        ),
    )
    seam.monthly_data("mdic_comex", {"flow": "import"})
    assert rec["m"] == "import"  # seasonality honours flow
    seam.flow_data("un_comtrade", {"flow": "import", "customs": "C01", "market": "consumo"})
    assert (rec["f"], rec["c"], rec["mk"]) == (
        "import",
        "C01",
        "consumo",
    )  # Sankey honours all three
    seam.partner_data("un_comtrade", {"flow": "import"})
    assert rec["pf"] == "import"  # partner ranking honours flow


def test_country_reader_kwargs_encodes_world_list_and_partners():
    seam = _seam()
    assert seam._country_reader_kwargs(None) == {}
    assert seam._country_reader_kwargs({}) == {}
    # world sentinel → pin_reporter None (sum over ALL reporters, no Brazil pin)
    world = {"reporters": seam._REPORTER_WORLD}
    assert seam._country_reader_kwargs(world) == {"pin_reporter": None}
    # explicit reporter list → IN-list
    assert seam._country_reader_kwargs({"reporters": ["BRA", "USA"]}) == {
        "reporters": ("BRA", "USA")
    }
    # partner list
    assert seam._country_reader_kwargs({"partners": ["CHN"]}) == {"partners": ("CHN",)}


def test_comtrade_countries_degrades_and_splits(monkeypatch):
    from google.cloud.exceptions import NotFound

    seam = _seam()

    def _nf():
        raise NotFound("mart not built")

    # NotFound (mart absent) and empty df both degrade to the empty payload, not a 500.
    monkeypatch.setattr(seam.gateway, "fetch_comtrade_countries", _nf)
    assert seam.comtrade_countries() == {"reporters": None, "partners": None}
    monkeypatch.setattr(seam.gateway, "fetch_comtrade_countries", lambda: pd.DataFrame())
    assert seam.comtrade_countries() == {"reporters": None, "partners": None}
    # happy path splits by the ``role`` column.
    df = pd.DataFrame({"role": ["reporter", "partner"], "iso": ["BRA", "CHN"]})
    monkeypatch.setattr(seam.gateway, "fetch_comtrade_countries", lambda: df)
    out = seam.comtrade_countries()
    assert list(out["reporters"]["iso"]) == ["BRA"]
    assert list(out["partners"]["iso"]) == ["CHN"]


def test_catalog_driven_bancos_lists_only_what_a_registration_steers(monkeypatch):
    """The editor promises "será buscado na próxima ingestão" off this list, so it must
    contain ONLY bancos a catalog edit actually steers.

    COMEX/COMTRADE resolve their scope from config, never from the catalog — registering a
    code there leaves it pendente forever, so promising a fetch is a lie the researcher
    cannot check. Found by registering bamboo end-to-end through the real UI."""
    from embrapa_dashboard.webapi import seam_curation

    class _S:
        catalog_authoritative_ingestion = True

    monkeypatch.setattr("embrapa_dashboard.config.get_settings", lambda: _S())
    driven = seam_curation.catalog_driven_bancos()
    assert driven == ["pevs", "pam", "ppm"]
    assert "comex" not in driven and "comtrade" not in driven


def test_catalog_driven_bancos_is_empty_when_the_flag_is_off(monkeypatch):
    """With catalog_authoritative_ingestion off, even the IBGE pipelines fall back to the
    env codes — so NO banco is steered and the UI must promise nothing at all."""
    from embrapa_dashboard.webapi import seam_curation

    class _S:
        catalog_authoritative_ingestion = False

    monkeypatch.setattr("embrapa_dashboard.config.get_settings", lambda: _S())
    assert seam_curation.catalog_driven_bancos() == []


def test_catalog_driven_bancos_promises_nothing_when_settings_cannot_be_built(monkeypatch):
    """No .env / missing GCP_PROJECT_ID (CI, a fresh worktree) must not raise.

    The value is a cosmetic affordance riding on the READ endpoint that renders the whole
    editor — letting it propagate turned /api/catalog/entries into a 400 and blanked the
    page (caught by CI, which has no .env). Failing CLOSED is also the honest direction:
    unable to tell whether the catalog steers ingestion, we must not claim it does."""
    from embrapa_dashboard.webapi import seam_curation

    def _boom():
        raise ValueError("1 validation error for Settings")

    monkeypatch.setattr("embrapa_dashboard.config.get_settings", _boom)
    assert seam_curation.catalog_driven_bancos() == []


# ── crosswalk buckets: adding a banco to the bridge must not break anything ────


def _crosswalk_rows():
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "agrupamento_id": "castanha_de_caju",
                "agrupamento_nome": "Castanha-de-caju",
                "source": "pevs",
                "code": "3404",
            },
            {
                "agrupamento_id": "castanha_de_caju",
                "agrupamento_nome": "Castanha-de-caju",
                "source": "pam",
                "code": "40143",
            },
            {
                "agrupamento_id": "castanha_de_caju",
                "agrupamento_nome": "Castanha-de-caju",
                "source": "comex",
                "code": "08013200",
            },
        ]
    )


def test_produto_catalog_carries_every_source_without_keyerror(monkeypatch):
    """PAM/PPM joined the bridge in 2026-08. The bucket dict used to be a hand-written
    pevs/comex/comtrade literal indexed as c[r.source], so the first row of a new source
    raised KeyError and took down EVERY cross-source view. Buckets now derive from
    sqlbuild.GOLD_CODE_SOURCES, so adding a banco cannot break this again."""
    from embrapa_dashboard.serving import sql as sqlbuild
    from embrapa_dashboard.webapi import seam_base
    from tests.test_serving import _bind_simplecache

    app, _ = _bind_simplecache()
    monkeypatch.setattr(seam_base, "_crosswalk_df", lambda: _crosswalk_rows())
    with app.app_context():
        cat = seam_base.produto_catalog()

    grupo = cat["castanha_de_caju"]
    assert grupo["pam"] == ["40143"]  # the new source landed
    assert grupo["pevs"] == ["3404"]
    # Every known source has a bucket, so callers can index without guarding.
    assert set(sqlbuild.GOLD_CODE_SOURCES) <= set(grupo)
    assert grupo["comtrade"] == []  # present and empty, not missing


def test_codes_stays_source_scoped_so_nothing_sums_across_sources(monkeypatch):
    """The reason adding PAM changed no existing computation: each view asks for its
    source BY NAME. The export coefficient reads 'pevs' and must keep seeing ONLY the
    PEVS code even though the same agrupamento now also carries a PAM one — otherwise
    extractive and cultivated output would silently merge into one denominator."""
    from embrapa_dashboard.webapi import seam_base
    from tests.test_serving import _bind_simplecache

    app, _ = _bind_simplecache()
    monkeypatch.setattr(seam_base, "_crosswalk_df", lambda: _crosswalk_rows())

    with app.app_context():
        assert seam_base._codes("castanha_de_caju", "pevs") == ("3404",)
        assert seam_base._codes("castanha_de_caju", "pam") == ("40143",)
        # An unknown source degrades to "no codes" instead of 500-ing the view.
        assert seam_base._codes("castanha_de_caju", "sefaz") == ()


# ─── nível de industrialização ────────────────────────────────────────────────
def _levels_df(pares):
    return pd.DataFrame(
        [{"source": s, "code": c, "industrialization_level": n} for s, c, n in pares]
    )


def test_codes_for_levels_selects_only_the_chosen_levels_of_that_banco(monkeypatch):
    """The dim is keyed by (source, code): another banco's code with the same digits must
    not be pulled in."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_current_code_industrialization",
        lambda: _levels_df(
            [
                ("ibge_pevs", "3435", "commodity_acondicionada"),
                ("ibge_pevs", "3405", "commodity_pura"),
                ("mdic_comex", "3435", "manufaturado_industrial"),
            ]
        ),
    )
    universo = {"3435", "3405", "9999"}
    assert seam._codes_for_levels("ibge_pevs", ("commodity_pura",), universo) == {"3405"}
    # O caso que expõe a contaminação: `manufaturado_industrial` só existe no COMEX. Se o
    # resolvedor ignorasse a fonte, o código 3435 da PEVS herdaria o nível do código
    # homônimo do COMEX e apareceria aqui. Pedir esse nível na PEVS tem de dar VAZIO.
    assert seam._codes_for_levels("ibge_pevs", ("manufaturado_industrial",), universo) == set()


def test_codes_for_levels_resolves_the_unclassified_sentinel_by_absence(monkeypatch):
    """`sem_classificacao` cannot be read off the dim — it is defined by ABSENCE from it,
    which is why the universe has to be passed in. Offering it at all is the point: the
    axis is curated by hand and never complete, so what has no level must stay visible."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_current_code_industrialization",
        lambda: _levels_df([("ibge_pevs", "3435", "commodity_acondicionada")]),
    )
    universo = {"3435", "3403", "3404"}
    assert seam._codes_for_levels("ibge_pevs", ("sem_classificacao",), universo) == {
        "3403",
        "3404",
    }
    # Combinado com um nível real, os dois conjuntos se somam.
    assert (
        seam._codes_for_levels(
            "ibge_pevs", ("commodity_acondicionada", "sem_classificacao"), universo
        )
        == universo
    )


def test_no_levels_selected_means_no_filter(monkeypatch):
    seam = _seam()
    universo = {"a", "b"}
    assert seam._codes_for_levels("ibge_pevs", (), universo) == universo


def _snapshot_codes(monkeypatch, summary, niveis_df, produtos):
    """Drive snapshot() and return the product_codes that reached the readers."""
    seam = _seam()
    visto: dict[str, object] = {}

    def _rec(**kw):
        visto["codes"] = kw.get("product_codes")
        return pd.DataFrame()

    monkeypatch.setattr(seam.gateway, "fetch_products", lambda b: pd.DataFrame({"code": produtos}))
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_source", lambda source=None: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_product_timeseries", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_timeseries", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_quality_by_product", lambda b: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf", lambda **k: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_production_by_uf_yearly", lambda **k: pd.DataFrame())
    monkeypatch.setattr(seam.gateway, "fetch_production_overview", _rec)
    monkeypatch.setattr(seam.gateway, "fetch_current_code_industrialization", lambda: niveis_df)
    seam.snapshot("ibge_pevs", {"currency": "BRL", "correction": "IPCA"}, summary)
    return visto["codes"]


def test_snapshot_resolves_levels_to_codes_and_intersects_with_the_basket(monkeypatch):
    """The WIRE, not the resolver: a level chosen in the menu has to reach the readers as
    codes. And it must COMPOSE with the basket — "só o açaí, e só o que é bruto" is one
    question, not two competing ones, so the answer is the intersection."""
    niveis = _levels_df(
        [
            ("ibge_pevs", "3403", "commodity_pura"),
            ("ibge_pevs", "3405", "commodity_pura"),
            ("ibge_pevs", "3435", "commodity_acondicionada"),
        ]
    )
    produtos = ["3403", "3405", "3435"]

    # Só o nível: todos os códigos daquele nível.
    assert _snapshot_codes(monkeypatch, {"niveis": ["commodity_pura"]}, niveis, produtos) == (
        "3403",
        "3405",
    )

    # Nível + cesta: a interseção, não um sobrescrevendo o outro.
    assert _snapshot_codes(
        monkeypatch, {"niveis": ["commodity_pura"], "basket": ["3403", "3435"]}, niveis, produtos
    ) == ("3403",)


def test_snapshot_never_lets_an_empty_level_result_become_no_filter(monkeypatch):
    """A basket that resolves to NOTHING must not collapse into "sem filtro de produto",
    which downstream would serve the whole banco — the exact opposite of what was asked.
    The sentinel matches no row, so the panel comes back honestly empty."""
    niveis = _levels_df([("ibge_pevs", "3403", "commodity_pura")])
    codes = _snapshot_codes(
        monkeypatch,
        {"niveis": ["commodity_pura"], "basket": ["3435"]},  # interseção vazia
        niveis,
        ["3403", "3435"],
    )
    assert codes and all(c not in ("3403", "3435") for c in codes)
