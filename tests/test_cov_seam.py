"""Coverage-focused unit tests for ``webapi/seam.py``.

Targets the view-composition branches that the main suite (tests/test_webapi_seam.py)
leaves uncovered: the trade final-fallback value column, the date/year parse-error
branches, the source_meta non-int ``year_end`` guard, the capability/None early-returns
on flow_data / products_by_uf / monthly_data, the empty inspectable_tables, and the
happy paths of the raw-table + seed inspection readers (table_page / seed_page).

Style mirrors tests/test_webapi_seam.py: the gateway readers are monkeypatched with
synthetic DataFrames (no BigQuery), gated behind ``pytest.importorskip('flask_caching')``.
"""

from __future__ import annotations

import pandas as pd
import pytest


def _seam():
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.webapi import seam

    return seam


# ── line 82: trade banco final fallback → val_real_ipca_brl ────────────────────


def test_effective_value_column_trade_final_fallback_to_real_ipca_brl(monkeypatch):
    """For a TRADE banco, when neither the requested column NOR its BRL sibling is in
    the mart allowlist, the fallback chain bottoms out at val_real_ipca_brl with the
    FOB/CIF valuation-basis note appended (line 82)."""
    seam = _seam()
    from embrapa_dashboard.webapi.registries import banco_by_id

    # Shrink the allowlist so both the requested column AND its BRL sibling are absent,
    # forcing the trade branch's terminal fallback.
    monkeypatch.setattr(seam.sqlbuild, "ALLOWED_VALUE_COLUMNS", frozenset({"val_real_ipca_brl"}))
    col, label = seam.effective_value_column(
        banco_by_id("un_comtrade"), {"currency": "USD", "correction": "IGP-M"}
    )
    assert col == "val_real_ipca_brl"
    assert "Valor real (IPCA)" in label
    assert "FOB" in label and "CIF" in label  # COMTRADE basis note still appended


# ── lines 104-105: _years_from_summary parse-error branch ──────────────────────


def test_years_from_summary_non_numeric_date_yields_none(monkeypatch):
    """A malformed date string (int(str(v)[:4]) raises ValueError) returns None for
    that bound rather than crashing — the except (TypeError, ValueError) branch."""
    seam = _seam()
    y0, y1 = seam._years_from_summary({"startDate": "abcd-01-01", "endDate": "2021"})
    assert y0 is None  # 'abcd' → ValueError → None
    assert y1 == 2021  # the well-formed bound still parses


# ── lines 339-340: source_meta non-int year_end guard ──────────────────────────


def test_source_meta_non_int_year_end_falls_back_to_none(monkeypatch):
    """A provenance row whose ``year_end`` cannot be coerced to int (e.g. a stray
    non-numeric string) is treated as None — the except (TypeError, ValueError) guard
    at lines 339-340 — so completeness still resolves without raising."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_source_metadata",
        lambda source=None: pd.DataFrame([{"source": "ibge_pevs", "year_end": "not-a-year"}]),
    )
    monkeypatch.setattr(seam.gateway, "fetch_banco_metadata", lambda banco_id: pd.DataFrame())
    meta = seam.source_meta("ibge_pevs")
    # year_end coerced to None → annual-banco trivially-complete shape (no months query).
    assert meta["latest_year_complete"] is True
    assert meta["months_in_latest_year"] is None
    assert meta["latest_complete_year"] is None


# ── line 542: flow_data None when banco lacks the 'flow' capability ────────────


def test_flow_data_none_without_flow_capability():
    """A live banco with no ``flow`` capability (PEVS is production-only) → None, so
    the Fluxos view shows its honest not-applicable note (line 542)."""
    seam = _seam()
    assert seam.flow_data("ibge_pevs", {"basket": ["1"]}) is None
    # A non-live banco also returns None via the same guard.
    assert seam.flow_data("sefaz_nfe") is None


# ── line 632: products_by_uf None for a geo banco that is neither COMEX nor PEVS ─


def test_products_by_uf_none_for_other_geo_banco(monkeypatch):
    """PAM/PPM expose a ``geo`` capability and pass the UF gate, but products_by_uf is
    only wired for COMEX + PEVS — any other geo banco hits the terminal ``return None``
    at line 632 (honest not-yet-wired)."""
    seam = _seam()
    called = {"n": 0}

    def fake_products_by_uf(**k):
        called["n"] += 1
        return pd.DataFrame()

    monkeypatch.setattr(seam.gateway, "fetch_products_by_uf", fake_products_by_uf)
    # ibge_pam is live + geo, with an explicit UF selection → reaches the dispatch but
    # matches neither the COMEX nor the PEVS branch.
    out = seam.products_by_uf("ibge_pam", {"states": ["PA"]})
    assert out is None
    assert called["n"] == 0  # no gateway query was issued


# ── line 651: monthly_data terminal None for a non-COMEX banco that has 'monthly' ─


def test_monthly_data_none_for_non_comex_monthly_banco(monkeypatch):
    """The terminal ``return None`` (line 651) is reached only when a banco is live and
    declares the ``monthly`` capability but is NOT mdic_comex. We synthesize that by
    handing a live non-COMEX banco a monthly-capable registry entry."""
    seam = _seam()

    class _FakeBanco:
        provides = ("product", "monthly", "quality")

    # un_comtrade is in _LIVE_SOURCES; give it a monthly-capable provides so the guard
    # passes but the mdic_comex dispatch does not match → falls through to line 651.
    monkeypatch.setattr(seam, "banco_by_id", lambda banco_id: _FakeBanco())
    assert seam.monthly_data("un_comtrade", {"basket": ["080121"]}) is None


# ── line 661: inspectable_tables empty for a non-live banco ─────────────────────


def test_inspectable_tables_empty_for_non_live_banco(monkeypatch):
    """A non-live banco has nothing to browse → [] (line 661), WITHOUT touching the
    gateway allowlist."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "inspectable_tables",
        lambda banco_id: pytest.fail("must not query the allowlist for a non-live banco"),
    )
    assert seam.inspectable_tables("sefaz_nfe") == []


# ── lines 680, 682-693: table_page None + the full happy path ──────────────────


def test_table_page_none_for_non_live_banco():
    """A non-live banco has no inspectable tables → None (line 680)."""
    seam = _seam()
    assert seam.table_page("sefaz_nfe", "gold_x") is None


def test_table_page_composes_schema_rows_count_and_meta(monkeypatch):
    """For a live banco, table_page threads paging/order/filter args to the gateway and
    composes the {columns, df, total, table, label, grain} payload (lines 682-693)."""
    seam = _seam()
    recorded = {}

    def fake_schema(banco_id, table_id):
        recorded["schema"] = (banco_id, table_id)
        return {"columns": [{"name": "reference_year", "type": "INTEGER"}]}

    def fake_rows(banco_id, table_id, *, limit, offset, order_by, order_dir, filters):
        recorded["rows"] = dict(
            limit=limit, offset=offset, order_by=order_by, order_dir=order_dir, filters=filters
        )
        return pd.DataFrame([{"reference_year": 2022}])

    def fake_count(banco_id, table_id, filters):
        recorded["count_filters"] = filters
        return 42

    monkeypatch.setattr(seam.gateway, "fetch_table_schema", fake_schema)
    monkeypatch.setattr(seam.gateway, "fetch_table_rows", fake_rows)
    monkeypatch.setattr(seam.gateway, "fetch_table_count", fake_count)
    monkeypatch.setattr(
        seam.gateway,
        "inspectable_tables",
        lambda banco_id: [{"id": "gold_pevs_production", "label": "PEVS", "grain": "ano × UF"}],
    )

    out = seam.table_page(
        "ibge_pevs",
        "gold_pevs_production",
        limit=25,
        offset=50,
        order_by="reference_year",
        order_dir="desc",
        filters=(("reference_year", "=", "2022"),),
    )
    assert out["columns"] == [{"name": "reference_year", "type": "INTEGER"}]
    assert list(out["df"]["reference_year"]) == [2022]
    assert out["total"] == 42
    assert out["table"] == "gold_pevs_production"
    assert out["label"] == "PEVS" and out["grain"] == "ano × UF"
    # The paging/order/filter args were threaded down verbatim.
    assert recorded["rows"]["limit"] == 25 and recorded["rows"]["offset"] == 50
    assert recorded["rows"]["order_by"] == "reference_year"
    assert recorded["rows"]["order_dir"] == "desc"
    assert recorded["rows"]["filters"] == (("reference_year", "=", "2022"),)
    assert recorded["count_filters"] == (("reference_year", "=", "2022"),)


def test_table_page_meta_defaults_when_table_absent_from_allowlist(monkeypatch):
    """When the table id has no metadata row in the allowlist, label/grain fall back to
    None via meta.get (the ``meta = next(..., {})`` default in lines 692-693)."""
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway,
        "fetch_table_schema",
        lambda banco_id, table_id: {"columns": []},
    )
    monkeypatch.setattr(
        seam.gateway,
        "fetch_table_rows",
        lambda *a, **k: pd.DataFrame(),
    )
    monkeypatch.setattr(seam.gateway, "fetch_table_count", lambda *a, **k: 0)
    monkeypatch.setattr(seam.gateway, "inspectable_tables", lambda banco_id: [])
    out = seam.table_page("ibge_pevs", "some_table")
    assert out["label"] is None and out["grain"] is None
    assert out["total"] == 0 and out["table"] == "some_table"


# ── lines 728-738: seed_page happy path (after the meta-is-None raise) ──────────


def test_seed_page_composes_schema_rows_count_and_meta(monkeypatch):
    """A known seed id resolves its metadata then threads paging/order/filter to the
    gateway and composes the {columns, df, total, table, label, grain, editable} payload
    (lines 728-738)."""
    seam = _seam()
    recorded = {}

    monkeypatch.setattr(
        seam.gateway,
        "seed_tables",
        lambda: [
            {
                "id": "historical_currency_factors",
                "label": "Fatores de reforma monetária",
                "description": "Fatores de conversão histórica",
                "editable": False,
            }
        ],
    )

    def fake_schema(seed_id):
        recorded["schema_seed"] = seed_id
        return {"columns": [{"name": "year", "type": "INTEGER"}]}

    def fake_rows(seed_id, *, limit, offset, order_by, order_dir, filters):
        recorded["rows"] = dict(
            seed_id=seed_id,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_dir=order_dir,
            filters=filters,
        )
        return pd.DataFrame([{"year": 1994}])

    def fake_count(seed_id, filters):
        recorded["count"] = (seed_id, filters)
        return 7

    monkeypatch.setattr(seam.gateway, "fetch_seed_schema", fake_schema)
    monkeypatch.setattr(seam.gateway, "fetch_seed_rows", fake_rows)
    monkeypatch.setattr(seam.gateway, "fetch_seed_count", fake_count)

    out = seam.seed_page(
        "historical_currency_factors",
        limit=10,
        offset=20,
        order_by="year",
        order_dir="desc",
        filters=(("year", ">", "1990"),),
    )
    assert out["columns"] == [{"name": "year", "type": "INTEGER"}]
    assert list(out["df"]["year"]) == [1994]
    assert out["total"] == 7
    assert out["table"] == "historical_currency_factors"
    assert out["label"] == "Fatores de reforma monetária"
    assert out["grain"] == "Fatores de conversão histórica"  # description → grain
    assert out["editable"] is False
    # Paging/order/filter threaded down verbatim.
    assert recorded["rows"]["limit"] == 10 and recorded["rows"]["offset"] == 20
    assert recorded["rows"]["order_by"] == "year" and recorded["rows"]["order_dir"] == "desc"
    assert recorded["rows"]["filters"] == (("year", ">", "1990"),)
    assert recorded["count"] == ("historical_currency_factors", (("year", ">", "1990"),))


def test_seed_page_unknown_seed_raises_value_error(monkeypatch):
    """An unknown seed id fails loud with ValueError (the guard just above line 728),
    rather than returning a silent empty page."""
    seam = _seam()
    monkeypatch.setattr(seam.gateway, "seed_tables", lambda: [])
    with pytest.raises(ValueError, match="não é uma tabela de referência consultável"):
        seam.seed_page("does_not_exist")


# ── _apply_levels: the nível narrowing every basket reader shares ─────────────
# It lived inline in `snapshot` until 2026-08-29, so seven other readers served the whole
# banco under a level's label. Extracted so there is ONE definition to get right.
def _levels_fixture(monkeypatch, por_nivel: dict[str, set[str]], universo: list[str]):
    seam = _seam()
    monkeypatch.setattr(
        seam.gateway, "fetch_products", lambda banco_id: pd.DataFrame({"code": universo})
    )
    monkeypatch.setattr(
        seam,
        "_codes_for_levels",
        lambda banco_id, niveis, universe: {
            c for n in niveis for c in por_nivel.get(n, set()) if c in universe
        },
    )
    return seam


def test_apply_levels_without_a_selection_returns_the_basket_untouched(monkeypatch):
    seam = _levels_fixture(monkeypatch, {}, ["1", "2"])
    assert seam._apply_levels("ibge_pevs", {}, ("1",)) == ("1",)
    assert seam._apply_levels("ibge_pevs", None, ()) == ()


def test_apply_levels_with_no_basket_yields_every_code_of_the_level(monkeypatch):
    seam = _levels_fixture(monkeypatch, {"pura": {"1", "2"}}, ["1", "2", "3"])
    out = seam._apply_levels("ibge_pevs", {"niveis": ["pura"]}, ())
    assert out == ("1", "2")


def test_apply_levels_intersects_with_the_basket_so_both_narrowings_compose(monkeypatch):
    """One must not override the other: a basket of {1,3} under a level of {1,2} is {1}."""
    seam = _levels_fixture(monkeypatch, {"pura": {"1", "2"}}, ["1", "2", "3"])
    assert seam._apply_levels("ibge_pevs", {"niveis": ["pura"]}, ("1", "3")) == ("1",)


def test_apply_levels_returns_a_sentinel_when_nothing_matches(monkeypatch):
    """An EMPTY basket reads as 'no product filter' downstream and would serve the whole
    banco — the opposite of what was asked. The sentinel keeps the answer honest."""
    seam = _levels_fixture(monkeypatch, {"pura": {"9"}}, ["1", "2"])
    assert seam._apply_levels("ibge_pevs", {"niveis": ["pura"]}, ("1",)) == (
        seam._NO_CODE_SENTINEL,
    )


def test_apply_levels_uses_the_products_passed_in_instead_of_refetching(monkeypatch):
    """`snapshot` already has the universe; the others fetch it (cached). Passing it must
    actually skip the read — otherwise every snapshot pays for a duplicate query."""
    seam = _levels_fixture(monkeypatch, {"pura": {"1"}}, ["1"])

    def _boom(banco_id):
        raise AssertionError("refetched the product universe despite being handed it")

    monkeypatch.setattr(seam.gateway, "fetch_products", _boom)
    out = seam._apply_levels(
        "ibge_pevs", {"niveis": ["pura"]}, (), products=pd.DataFrame({"code": ["1"]})
    )
    assert out == ("1",)
