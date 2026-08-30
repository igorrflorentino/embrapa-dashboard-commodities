"""Coverage tests for ``webapi/seam_curation.py``.

These are focused unit tests over the thin curadoria (catalog) seam: they mock the
underlying gateway readers + ``serving/curation`` writers and assert the seam's
output shapes / error-degradation. They never touch a live warehouse, mirroring the
mock style in ``tests/test_serving.py`` (where ``orphan_worklist`` is already
exercised). This file targets the remaining uncovered branches:
``catalog_worklist``, ``record_catalog_entry``, ``remove_catalog_entry``,
``catalog_editor_emails``, and the NotFound/empty short-circuits of
``orphan_worklist``.
"""

from __future__ import annotations

import pandas as pd
import pytest
from google.api_core.exceptions import NotFound

from embrapa_dashboard.serving import gateway
from embrapa_dashboard.webapi import seam_curation

# ── catalog_worklist ──────────────────────────────────────────────────────────


def test_catalog_worklist_empty_when_log_table_absent(monkeypatch):
    """A genuine NotFound (no catalog log yet) degrades to an empty catalog, NOT an
    error — the editor must render before the first write (lines 31-34)."""

    def _raise(banco=None):
        raise NotFound("commodity catalog log table not found")

    monkeypatch.setattr(gateway, "fetch_produto_catalog", _raise)
    out = seam_curation.catalog_worklist()
    assert out == {"entries": [], "total": 0, "by_agrupamento": []}


def test_catalog_worklist_empty_when_dataframe_empty(monkeypatch):
    """An empty (or None) DataFrame is also the empty-catalog shape (line 35-36)."""
    monkeypatch.setattr(gateway, "fetch_produto_catalog", lambda banco=None: pd.DataFrame())
    assert seam_curation.catalog_worklist() == {
        "entries": [],
        "total": 0,
        "by_agrupamento": [],
    }
    monkeypatch.setattr(gateway, "fetch_produto_catalog", lambda banco=None: None)
    assert seam_curation.catalog_worklist()["total"] == 0


def test_catalog_worklist_shapes_entries_and_groups(monkeypatch):
    """The happy path projects each row, then groups by Agrupamento with per-group n +
    sorted banco set (lines 37-57). Includes a blank Agrupamento → the '—' bucket."""

    def _df(banco=None):
        return pd.DataFrame(
            [
                {
                    "codigo_produto": 4403,  # int → str() coercion exercised
                    "banco": "un_comtrade",
                    "agrupamento": "Madeira",
                    "descricao_produto": "Madeira em toras",
                    "ciclo_de_vida": "Fazer Ingestão e deixar disponível",
                    "code_prefix": 4403,
                    "agrupamento_id": "madeira",
                    "tabela": "3939",  # round-trips to the client so a saved tag is visible
                },
                {
                    "codigo_produto": "4407",
                    "banco": "comex",
                    "agrupamento": "Madeira",
                    "descricao_produto": "Madeira serrada",
                    "ciclo_de_vida": "Disponível",
                    "code_prefix": "4407",
                    "agrupamento_id": "madeira",
                },
                {
                    "codigo_produto": "9999",
                    "banco": "comex",
                    # A NULL STRING cell reads back from BigQuery as float('nan') — the
                    # worklist must coerce it to None (via _clean) or sorted(groups) chokes
                    # comparing a float key with the string keys. Bucketed under '—'.
                    "agrupamento": float("nan"),
                    "descricao_produto": "Sem agrupamento",
                    "ciclo_de_vida": float("nan"),
                    "code_prefix": "9999",
                    "agrupamento_id": float("nan"),
                },
            ]
        )

    monkeypatch.setattr(gateway, "fetch_produto_catalog", _df)
    # The worklist attaches the source's ORIGINAL description per (banco, codigo) via
    # fetch_source_products_gold(source) — UNGATED (the admin editor sees hidden products
    # too). Mock it: comex code 4407 has a name; 9999 does not.
    monkeypatch.setattr(
        gateway,
        "fetch_source_products_gold",
        lambda src: pd.DataFrame([{"code": "4407", "name": "Madeira serrada (NCM)"}]),
    )
    out = seam_curation.catalog_worklist(banco="any")

    assert out["total"] == 3
    # str() coercion on a numeric codigo_produto; code_prefix is gone entirely.
    first = out["entries"][0]
    assert first["codigo_produto"] == "4403" and "code_prefix" not in first
    # tabela round-trips to the client (was previously dropped at the gateway SELECT),
    # so a researcher's saved PPM tag is visible on reload.
    assert first["tabela"] == "3939"
    # Source description: 4407 (comex) resolves; the un_comtrade 4403 + comex 9999 don't.
    by_code = {(e["banco"], e["codigo_produto"]): e for e in out["entries"]}
    assert by_code[("comex", "4407")]["descricao_fonte"] == "Madeira serrada (NCM)"
    assert by_code[("comex", "9999")]["descricao_fonte"] is None
    # The NULL (NaN) fields on the 9999 row are normalized to None (not left as float nan).
    e9999 = by_code[("comex", "9999")]
    assert e9999["agrupamento"] is None
    assert e9999["ciclo_de_vida"] is None and e9999["agrupamento_id"] is None
    # The absent tabela cell (NaN from the mixed DataFrame) normalizes to None.
    assert e9999["tabela"] is None

    groups = {g["agrupamento"]: g for g in out["by_agrupamento"]}
    assert set(groups) == {"Madeira", "—"}
    # Madeira spans two bancos, sorted; the unique set collapses the duplicate 'comex'.
    assert groups["Madeira"]["n"] == 2
    assert groups["Madeira"]["bancos"] == ["comex", "un_comtrade"]
    assert groups["—"]["n"] == 1 and groups["—"]["bancos"] == ["comex"]


# ── source_codes (add-form autocomplete + client-side existence check) ─────────


def test_source_codes_unknown_banco_is_empty(monkeypatch):
    """An unknown banco token has no source id → an empty (not error) code list, so the
    add form degrades to a free-text field rather than blowing up."""
    out = seam_curation.source_codes("not_a_banco")
    assert out == {"banco": "not_a_banco", "codes": []}


def test_source_codes_empty_when_products_table_absent(monkeypatch):
    """A known banco whose products table isn't built yet → empty list (NotFound), not
    an error."""

    def _raise(src):
        raise NotFound("products table not built")

    monkeypatch.setattr(gateway, "fetch_source_products_gold", _raise)
    assert seam_curation.source_codes("comtrade") == {"banco": "comtrade", "codes": []}


def test_source_codes_empty_when_products_df_empty(monkeypatch):
    """A known banco whose products table is present but EMPTY → empty code list."""
    monkeypatch.setattr(gateway, "fetch_source_products_gold", lambda src: pd.DataFrame())
    assert seam_curation.source_codes("comtrade") == {"banco": "comtrade", "codes": []}


def test_source_codes_projects_code_and_name(monkeypatch):
    """The happy path maps the banco token to its source id, reads the products, and
    projects each to {code, name} (both str-coerced)."""
    seen = {}

    def _products(src):
        seen["src"] = src
        return pd.DataFrame([{"code": 4403, "name": "Madeira em toras"}, {"code": "4407"}])

    monkeypatch.setattr(gateway, "fetch_source_products_gold", _products)
    out = seam_curation.source_codes("comtrade")

    assert seen["src"] == "un_comtrade"  # short token → long source id
    assert out["banco"] == "comtrade"
    codes = {c["code"]: c["name"] for c in out["codes"]}
    assert codes["4403"] == "Madeira em toras"  # int code coerced to str
    assert codes["4407"] == ""  # a missing name normalizes to an empty string


# ── catalog_status (per-commodity Gold state: linhas + período) ────────────────


def test_catalog_status_empty_when_catalog_absent(monkeypatch):
    """No catalog yet (NotFound) → an empty status map, not an error."""

    def _raise(banco=None):
        raise NotFound("catalog log absent")

    monkeypatch.setattr(gateway, "fetch_produto_catalog", _raise)
    assert seam_curation.catalog_status() == {"status": {}}


def test_catalog_status_empty_when_catalog_df_empty(monkeypatch):
    """An empty catalog DataFrame → an empty status map (no Gold scans)."""
    monkeypatch.setattr(gateway, "fetch_produto_catalog", lambda banco=None: pd.DataFrame())
    assert seam_curation.catalog_status() == {"status": {}}


def test_catalog_status_joins_gold_stats_per_code(monkeypatch):
    """The happy path groups cataloged codes by banco, reads ONE Gold aggregate per banco,
    and keys the result pelo TRIO ``"<banco>:<tabela>:<code>"`` — a code with no Gold rows
    reports n_rows=0/has_data=False (a registered-but-empty commodity).

    O fixture traz o MESMO código em duas tabelas (a condição que a chave por par colapsava)
    e exige que os dois estados sobrevivam separados."""

    def _catalog(banco=None):
        return pd.DataFrame(
            [
                {"codigo_produto": "4403", "banco": "comtrade", "tabela": "comtrade_hs"},
                # mesmo CÓDIGO, outra tabela: duas entradas legítimas do catálogo, que a
                # chave por (banco, código) fundia numa só.
                {"codigo_produto": "4403", "banco": "comtrade", "tabela": "outra"},
                # cataloged, no Gold rows
                {"codigo_produto": "9999", "banco": "comtrade", "tabela": "comtrade_hs"},
            ]
        )

    def _stats(banco):
        # Only 4403 has Gold rows; 9999 is absent from the aggregate.
        return pd.DataFrame(
            [
                {
                    "code": "4403",
                    "tabela": "comtrade_hs",
                    "n_rows": 12,
                    "year_start": 2000,
                    "year_end": 2024,
                },
                {
                    "code": "4403",
                    "tabela": "outra",
                    "n_rows": 7,
                    "year_start": 2010,
                    "year_end": 2020,
                },
            ]
        )

    monkeypatch.setattr(gateway, "fetch_produto_catalog", _catalog)
    monkeypatch.setattr(gateway, "fetch_source_code_stats", _stats)

    status = seam_curation.catalog_status()["status"]
    assert status["comtrade:comtrade_hs:4403"] == {
        "n_rows": 12,
        "year_start": 2000,
        "year_end": 2024,
        "has_data": True,
    }
    # A OUTRA metade do mesmo código mantém o SEU estado — com a chave por par, uma das
    # duas sobrescrevia a outra e as duas linhas do editor mostravam o mesmo número.
    assert status["comtrade:outra:4403"] == {
        "n_rows": 7,
        "year_start": 2010,
        "year_end": 2020,
        "has_data": True,
    }
    assert status["comtrade:comtrade_hs:9999"] == {
        "n_rows": 0,
        "year_start": None,
        "year_end": None,
        "has_data": False,
    }


def test_catalog_status_skips_banco_when_stats_absent(monkeypatch):
    """A banco whose Gold fact table is missing (fetch_source_code_stats → NotFound) is
    skipped entirely rather than aborting the whole status map."""

    def _catalog(banco=None):
        return pd.DataFrame([{"codigo_produto": "1", "banco": "not_a_banco", "tabela": "t"}])

    def _raise(banco):
        raise NotFound("no Gold table for that banco")

    monkeypatch.setattr(gateway, "fetch_produto_catalog", _catalog)
    monkeypatch.setattr(gateway, "fetch_source_code_stats", _raise)
    assert seam_curation.catalog_status() == {"status": {}}


# ── record_catalog_entry ──────────────────────────────────────────────────────


def test_record_catalog_entry_threads_payload_without_request_context(monkeypatch):
    """Outside a request context, headers are an empty dict and every payload field is
    threaded as a keyword to the verified writer (lines 64-69, no-context branch)."""
    from embrapa_dashboard.serving import curation

    captured = {}

    def _record(codigo_produto, banco, headers, **kw):
        captured["args"] = (codigo_produto, banco)
        captured["headers"] = headers
        captured["kw"] = kw
        return {"ok": True}

    monkeypatch.setattr(curation, "record_produto_catalog", _record)

    payload = {
        "codigo_produto": "4403",
        "banco": "un_comtrade",
        "agrupamento": "Madeira",
        "descricao_produto": "Madeira em toras",
        "ciclo_de_vida": "Disponível",
        "agrupamento_id": "madeira",
        "change_id": "k1",
    }
    out = seam_curation.record_catalog_entry(payload)

    assert out == {"ok": True}
    assert captured["args"] == ("4403", "un_comtrade")
    assert captured["headers"] == {}  # no request context → empty headers
    assert captured["kw"]["agrupamento"] == "Madeira"
    assert captured["kw"]["change_id"] == "k1"
    assert "code_prefix" not in captured["kw"]  # prefixes removed from the writer


def test_record_catalog_entry_captures_iap_headers_in_request_context(monkeypatch):
    """Inside a request context the IAP header dict is forwarded to the writer
    (line 68, has_request_context branch)."""
    pytest.importorskip("flask")
    from flask import Flask

    from embrapa_dashboard.serving import curation

    captured = {}

    def _record(codigo_produto, banco, headers, **kw):
        captured["headers"] = headers
        return {"ok": True}

    monkeypatch.setattr(curation, "record_produto_catalog", _record)

    app = Flask(__name__)
    with app.test_request_context(
        "/api/catalog/entry", headers={"X-Goog-Authenticated-User-Email": "a@embrapa.br"}
    ):
        out = seam_curation.record_catalog_entry({"codigo_produto": "4403", "banco": "un_comtrade"})

    assert out == {"ok": True}
    assert captured["headers"]["X-Goog-Authenticated-User-Email"] == "a@embrapa.br"


# ── remove_catalog_entry ──────────────────────────────────────────────────────


def test_remove_catalog_entry_threads_tombstone_without_request_context(monkeypatch):
    """The remove seam forwards (codigo, banco, headers={}, change_id) to the tombstone
    writer when there is no request context (lines 87-92)."""
    from embrapa_dashboard.serving import curation

    captured = {}

    def _remove(codigo_produto, banco, headers, *, change_id=None):
        captured.update(codigo=codigo_produto, banco=banco, headers=headers, change_id=change_id)
        return {"active": False}

    monkeypatch.setattr(curation, "remove_produto_catalog", _remove)

    out = seam_curation.remove_catalog_entry(
        {"codigo_produto": "4403", "banco": "un_comtrade", "change_id": "rm1"}
    )
    assert out == {"active": False}
    assert captured["codigo"] == "4403" and captured["banco"] == "un_comtrade"
    assert captured["headers"] == {} and captured["change_id"] == "rm1"


def test_remove_catalog_entry_captures_headers_in_request_context(monkeypatch):
    """The remove seam captures the IAP author header inside a request context
    (line 91, has_request_context branch)."""
    pytest.importorskip("flask")
    from flask import Flask

    from embrapa_dashboard.serving import curation

    captured = {}

    def _remove(codigo_produto, banco, headers, *, change_id=None):
        captured["headers"] = headers
        return {"active": False}

    monkeypatch.setattr(curation, "remove_produto_catalog", _remove)

    app = Flask(__name__)
    with app.test_request_context(
        "/api/catalog/entry/remove",
        headers={"X-Goog-Authenticated-User-Email": "b@embrapa.br"},
    ):
        seam_curation.remove_catalog_entry({"codigo_produto": "4403", "banco": "un_comtrade"})
    assert captured["headers"]["X-Goog-Authenticated-User-Email"] == "b@embrapa.br"


# ── catalog_editor_emails ─────────────────────────────────────────────────────


def test_catalog_editor_emails_empty_when_allowlist_table_absent(monkeypatch):
    """A missing allowlist table → empty set (open by default), NOT an error
    (lines 104-107)."""

    def _raise(resource):
        raise NotFound("catalog_editors table not found")

    monkeypatch.setattr(gateway, "fetch_catalog_editors", _raise)
    assert seam_curation.catalog_editor_emails() == set()


def test_catalog_editor_emails_empty_when_dataframe_empty(monkeypatch):
    """An empty / None allowlist DataFrame is also the open (empty-set) gate
    (lines 108-109)."""
    monkeypatch.setattr(
        gateway, "fetch_catalog_editors", lambda resource: pd.DataFrame({"email": []})
    )
    assert seam_curation.catalog_editor_emails("produto_catalog") == set()
    monkeypatch.setattr(gateway, "fetch_catalog_editors", lambda resource: None)
    assert seam_curation.catalog_editor_emails() == set()


def test_catalog_editor_emails_normalizes_emails(monkeypatch):
    """The happy path lowercases + strips the emails and drops blanks (line 110)."""

    def _df(resource):
        # Keep the column object-typed strings (no None → no NaN coercion); the empty
        # string is the falsy entry the comprehension drops.
        return pd.DataFrame({"email": ["  Researcher@Embrapa.BR ", "OTHER@embrapa.br", ""]})

    monkeypatch.setattr(gateway, "fetch_catalog_editors", _df)
    out = seam_curation.catalog_editor_emails("produto_catalog")
    assert out == {"researcher@embrapa.br", "other@embrapa.br"}


# ── orphan_worklist: NotFound / empty short-circuits ──────────────────────────


def test_orphan_worklist_empty_when_orphan_table_absent(monkeypatch):
    """No orphan source table (NotFound) degrades to an empty worklist, never an error —
    exercises the orphans-NotFound→None branch and the empty short-circuit (lines
    122-126). ``fetch_lifecycle_status`` must NOT be reached on this path."""

    def _raise():
        raise NotFound("orphan commodities source not found")

    def _boom():
        raise AssertionError("lifecycle status must not be queried on the empty path")

    monkeypatch.setattr(gateway, "fetch_orphan_produtos", _raise)
    monkeypatch.setattr(gateway, "fetch_lifecycle_status", _boom)
    assert seam_curation.orphan_worklist() == {"orphans": [], "total": 0}


def test_orphan_worklist_empty_when_no_orphans(monkeypatch):
    """An empty / None orphan DataFrame short-circuits to the empty worklist (line 126),
    again without touching the lifecycle-status reader."""

    def _boom():
        raise AssertionError("lifecycle status must not be queried on the empty path")

    monkeypatch.setattr(gateway, "fetch_lifecycle_status", _boom)
    monkeypatch.setattr(gateway, "fetch_orphan_produtos", lambda: pd.DataFrame())
    assert seam_curation.orphan_worklist() == {"orphans": [], "total": 0}
    monkeypatch.setattr(gateway, "fetch_orphan_produtos", lambda: None)
    assert seam_curation.orphan_worklist() == {"orphans": [], "total": 0}


# ── group_worklist + group write seams (first-class agrupamentos) ──────────────


def test_group_worklist_shapes_groups(monkeypatch):
    def _df():
        return pd.DataFrame(
            [
                {"group_id": "madeira", "group_name": "Madeira", "n_members": 2},
                {"group_id": "castanha", "group_name": "Castanha", "n_members": 0},
            ]
        )

    monkeypatch.setattr(gateway, "fetch_agrupamentos", _df)
    out = seam_curation.group_worklist()
    assert out["total"] == 2
    assert out["groups"][0] == {"group_id": "madeira", "group_name": "Madeira", "n_members": 2}


def test_group_worklist_empty_on_not_found(monkeypatch):
    def _raise():
        raise NotFound("no registry")

    monkeypatch.setattr(gateway, "fetch_agrupamentos", _raise)
    assert seam_curation.group_worklist() == {"groups": [], "total": 0}
    monkeypatch.setattr(gateway, "fetch_agrupamentos", lambda: pd.DataFrame())
    assert seam_curation.group_worklist() == {"groups": [], "total": 0}


def test_record_group_seam_threads_payload(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos

    captured = {}

    def _rec(group_name, headers, **kw):
        captured["name"] = group_name
        captured["headers"] = headers
        captured["kw"] = kw
        return {"ok": True}

    monkeypatch.setattr(agrupamentos, "record_group", _rec)
    out = seam_curation.record_group(
        {"group_name": "Madeira", "group_id": "madeira", "change_id": "k"}
    )
    assert out == {"ok": True}
    assert captured["name"] == "Madeira" and captured["headers"] == {}  # no request context
    assert captured["kw"]["group_id"] == "madeira" and captured["kw"]["change_id"] == "k"


def test_remove_group_seam_threads_payload(monkeypatch):
    from embrapa_dashboard.serving import agrupamentos

    captured = {}

    def _del(group_id, headers, **kw):
        captured["gid"] = group_id
        captured["kw"] = kw
        return {"ok": True}

    monkeypatch.setattr(agrupamentos, "delete_group", _del)
    out = seam_curation.remove_group({"group_id": "madeira", "change_id": "k"})
    assert (
        out == {"ok": True} and captured["gid"] == "madeira" and captured["kw"]["change_id"] == "k"
    )


def test_catalog_worklist_skips_source_desc_on_not_found(monkeypatch):
    """A source whose products mart is absent (NotFound) leaves descricao_fonte None —
    never masks the whole worklist as an error."""

    def _df(banco=None):
        return pd.DataFrame(
            [
                {
                    "codigo_produto": "4403",
                    "banco": "comex",
                    "agrupamento": "Madeira",
                    "descricao_produto": None,
                    "ciclo_de_vida": "x",
                    "code_prefix": "4403",
                    "agrupamento_id": "madeira",
                }
            ]
        )

    def _raise(src):
        raise NotFound("no mart")

    monkeypatch.setattr(gateway, "fetch_produto_catalog", _df)
    monkeypatch.setattr(gateway, "fetch_source_products_gold", _raise)
    out = seam_curation.catalog_worklist()
    assert out["entries"][0]["descricao_fonte"] is None
