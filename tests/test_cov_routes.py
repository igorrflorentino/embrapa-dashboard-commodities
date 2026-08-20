"""Coverage-raising tests for ``webapi/routes.py`` error / authz / edge branches.

These complement ``test_webapi_routes.py`` (same Flask ``test_client`` + Settings-stub
pattern) by exercising the as-yet-uncovered paths:

- ``_authorize_catalog_editor`` 401/403 branches (forged IAP assertion, no identity),
- the catalog upsert / remove auth-failure + missing-field returns,
- ``_parse_table_filters`` malformed-shape ValueErrors (non-list payload, filter w/o 'col'),
- the ``/geo-yearly?flow=`` server-side flow re-query branch,
- the ``/products-by-uf`` route wiring,
- the ``/feedback`` ``InvalidIapAssertionError`` → 403 branch.

No BigQuery: Settings is stubbed and every seam/feedback dependency is monkeypatched.
The ``_client`` helper is reused verbatim from ``test_webapi_routes`` so the auth /
allowlist wiring matches the rest of the HTTP suite.
"""

from __future__ import annotations

from tests.test_webapi_routes import _client

# ── _authorize_catalog_editor: 403 (forged IAP) / 401 (no identity) (lines 173-176) ──


def test_catalog_editor_invalid_iap_assertion_is_403(monkeypatch):
    """An audience is configured but no signed JWT is present → InvalidIapAssertion →
    403 on the catalog-editor authz path (distinct from the attribute editor path)."""
    from embrapa_dashboard.webapi import routes

    client = _client(monkeypatch, iap_audience="/projects/1/global/backendServices/2")
    # Self-heal of the per-catalog editor table must never touch BigQuery here.
    monkeypatch.setattr(routes, "ensure_catalog_editors_table", lambda: None)
    resp = client.post(
        "/api/catalog/entry",
        json={"codigo_produto": "4403", "banco": "un_comtrade"},
    )
    assert resp.status_code == 403
    assert "error" in resp.get_json()


def test_catalog_editor_without_identity_is_401(monkeypatch):
    """No IAP header + no dev fallback → MissingAuthorError (a PermissionError) → 401
    on the catalog-editor authz path (never writes)."""
    from embrapa_dashboard.webapi import routes

    client = _client(monkeypatch)  # dev_author=None, iap_audience=None
    monkeypatch.setattr(routes, "ensure_catalog_editors_table", lambda: None)
    resp = client.post(
        "/api/catalog/entry/remove",
        json={"codigo_produto": "4403", "banco": "un_comtrade"},
    )
    assert resp.status_code == 401
    assert "error" in resp.get_json()


# ── catalog upsert / remove: auth-failure return + missing-field 400 (lines 232, 235) ──


def test_catalog_entry_upsert_auth_failure_returns_err(monkeypatch):
    """The upsert route short-circuits on the authz error tuple (no seam write)."""
    from embrapa_dashboard.webapi import routes, seam

    client = _client(monkeypatch, iap_audience="/projects/1/global/backendServices/2")
    monkeypatch.setattr(routes, "ensure_catalog_editors_table", lambda: None)

    def must_not_run(*a, **k):
        raise AssertionError("seam reached despite an auth failure")

    monkeypatch.setattr(seam, "record_catalog_entry", must_not_run)
    resp = client.post(
        "/api/catalog/entry",
        json={"codigo_produto": "4403", "banco": "un_comtrade"},
    )
    assert resp.status_code == 403


def test_catalog_entry_remove_missing_fields_is_400(monkeypatch):
    """Authorized (open allowlist) but an incomplete remove body → 400 before any write."""
    from embrapa_dashboard.webapi import routes, seam

    client = _client(monkeypatch, dev_author="researcher@embrapa.br")
    monkeypatch.setattr(routes, "ensure_catalog_editors_table", lambda: None)  # ensure OK
    monkeypatch.setattr(seam, "catalog_editor_emails", lambda resource=None: set())  # open

    def must_not_run(*a, **k):
        raise AssertionError("seam reached despite a missing field")

    monkeypatch.setattr(seam, "remove_catalog_entry", must_not_run)
    resp = client.post("/api/catalog/entry/remove", json={"banco": "un_comtrade"})  # no codigo
    assert resp.status_code == 400
    assert "obrigatórios" in resp.get_json()["error"]


def test_catalog_entry_remove_auth_failure_returns_err(monkeypatch):
    """The remove route short-circuits on the authz error tuple (line 232)."""
    from embrapa_dashboard.webapi import routes, seam

    client = _client(monkeypatch, iap_audience="/projects/1/global/backendServices/2")
    monkeypatch.setattr(routes, "ensure_catalog_editors_table", lambda: None)

    def must_not_run(*a, **k):
        raise AssertionError("seam reached despite an auth failure")

    monkeypatch.setattr(seam, "remove_catalog_entry", must_not_run)
    resp = client.post(
        "/api/catalog/entry/remove",
        json={"codigo_produto": "4403", "banco": "un_comtrade"},
    )
    assert resp.status_code == 403


# ── _authorize_catalog_editor: CATALOG_EDITORS_ALLOWED_EMAILS env union ───────────


def test_catalog_editor_env_allowlist_denies_non_member(monkeypatch):
    """CATALOG_EDITORS_ALLOWED_EMAILS is UNIONed with the table (parity with the attribute editor
    env allowlist): an author outside it (empty table) gets 403 — no seam write."""
    from embrapa_dashboard.webapi import routes, seam

    client = _client(
        monkeypatch,
        dev_author="alice@embrapa.br",
        catalog_editors_allowed_emails="bob@embrapa.br",
    )
    monkeypatch.setattr(routes, "ensure_catalog_editors_table", lambda: None)
    monkeypatch.setattr(seam, "catalog_editor_emails", lambda resource=None: set())  # empty table
    resp = client.post(
        "/api/catalog/entry",
        json={"codigo_produto": "4403", "banco": "comtrade", "agrupamento": "Madeira"},
    )
    assert resp.status_code == 403


def test_catalog_editor_env_allowlist_allows_member(monkeypatch):
    """An author present in CATALOG_EDITORS_ALLOWED_EMAILS is authorized even with an
    empty table (the union), and the seam write runs."""
    from embrapa_dashboard.webapi import routes, seam

    client = _client(
        monkeypatch,
        dev_author="alice@embrapa.br",
        catalog_editors_allowed_emails="alice@embrapa.br",
    )
    monkeypatch.setattr(routes, "ensure_catalog_editors_table", lambda: None)
    monkeypatch.setattr(seam, "catalog_editor_emails", lambda resource=None: set())
    monkeypatch.setattr(seam, "record_catalog_entry", lambda body: {"ok": True})
    resp = client.post(
        "/api/catalog/entry",
        json={"codigo_produto": "4403", "banco": "comtrade", "agrupamento": "Madeira"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


# ── _parse_table_filters malformed shapes → 400 (lines 296, 300) ──────────────────


def test_table_route_400_on_non_list_filters(monkeypatch):
    """A `filters` payload that parses to JSON but is NOT a list (e.g. an object) is a
    clean 400 — the route's "filtro deve ser uma lista" guard (line 296)."""
    client = _client(monkeypatch)
    # filters is a JSON object, not a list
    resp = client.get('/api/table?banco=ibge_ppm&table=x&filters={"col":"reference_year"}')
    assert resp.status_code == 400
    assert "lista" in resp.get_json()["error"]


def test_table_route_400_on_filter_missing_col(monkeypatch):
    """A filter element without a 'col' key (or not a dict) is a 400 — line 300."""
    client = _client(monkeypatch)
    resp = client.get('/api/table?banco=ibge_ppm&table=x&filters=[{"op":"eq","val":"1"}]')
    assert resp.status_code == 400
    assert "col" in resp.get_json()["error"]


# ── /geo-yearly?flow= server-side flow re-query branch (line 420) ─────────────────


def test_geo_yearly_route_threads_flow_to_seam(monkeypatch):
    """A ?flow= reaches the seam as summary['flow'] (the trade cube re-queries by
    direction server-side, same as /snapshot) — line 420."""
    from embrapa_dashboard.webapi import seam, serializers

    client = _client(monkeypatch)
    captured = {}

    def fake_geo_yearly(banco, conv, summary=None):
        captured.update(banco=banco, conv=conv, summary=summary)
        return None

    monkeypatch.setattr(seam, "geo_yearly", fake_geo_yearly)
    monkeypatch.setattr(serializers, "serialize_geo_yearly", lambda *a, **k: {"ufYearly": []})
    resp = client.get(
        "/api/geo-yearly?banco=mdic_comex&codes=0801&flow=export&currency=BRL&correction=IPCA"
    )
    assert resp.status_code == 200
    assert captured["summary"] == {"basket": ["0801"], "flow": "export"}


# ── /products-by-uf route wiring (lines 484-489) ──────────────────────────────────


def test_products_by_uf_route_threads_filters_conv_to_seam(monkeypatch):
    """/products-by-uf forwards the active filter summary (codes/states/y0/y1) + the
    currency/correction conventions to the seam, and returns the serialized shape."""
    from embrapa_dashboard.webapi import seam, serializers

    client = _client(monkeypatch)
    captured = {}

    def fake_products_by_uf(banco, summary, conv):
        captured.update(banco=banco, summary=summary, conv=conv)
        return None

    monkeypatch.setattr(seam, "products_by_uf", fake_products_by_uf)
    monkeypatch.setattr(serializers, "serialize_products_by_uf", lambda *a, **k: {"products": []})
    resp = client.get(
        "/api/products-by-uf?banco=ibge_pevs&states=SP,PA&codes=3405&y0=2010&y1=2020"
        "&currency=USD&correction=IGP-M"
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"products": []}
    assert captured["banco"] == "ibge_pevs"
    assert captured["conv"] == {"currency": "USD", "correction": "IGP-M"}
    assert captured["summary"] == {
        "basket": ["3405"],
        "states": ["SP", "PA"],
        "startDate": "2010",
        "endDate": "2020",
    }


def test_products_by_uf_route_rejects_invalid_convention(monkeypatch):
    """An invalid currency 400s at the boundary BEFORE the seam runs (the conv guard
    on the /products-by-uf route — lines 485-487)."""
    from embrapa_dashboard.webapi import seam

    client = _client(monkeypatch)

    def must_not_run(*a, **k):
        raise AssertionError("seam reached despite an invalid convention")

    monkeypatch.setattr(seam, "products_by_uf", must_not_run)
    resp = client.get("/api/products-by-uf?banco=ibge_pevs&currency=GBP")
    assert resp.status_code == 400


# ── /feedback InvalidIapAssertionError → 403 (line 689) ───────────────────────────


def test_feedback_invalid_iap_assertion_is_403(monkeypatch):
    """record_feedback raising InvalidIapAssertionError (a forged/invalid IAP JWT)
    maps to a 403 on the feedback route — line 689."""
    from embrapa_dashboard.serving.iap import InvalidIapAssertionError
    from embrapa_dashboard.webapi import routes

    client = _client(monkeypatch)

    def raise_invalid(*a, **k):
        raise InvalidIapAssertionError("forged assertion")

    monkeypatch.setattr(routes, "record_feedback", raise_invalid)
    resp = client.post("/api/feedback", json={"category": "bug", "message": "oi"})
    assert resp.status_code == 403
    assert "error" in resp.get_json()


# ── the authz fall-throughs and the group routes (coverage-gate re-arm, 2026-08-20) ──
#
# The two authz tests below are the security-relevant ones: both assert the endpoint
# FAILS CLOSED. An allowlist that cannot be read must never be mistaken for an empty
# allowlist, because empty means "open to every IAP caller" by design.


def test_catalog_write_is_503_when_the_editor_allowlist_cannot_be_ensured(monkeypatch):
    """Empty allowlist = open mode — but ONLY when we could confirm the table's state.

    If ensuring the table failed, an empty read is indistinguishable from "allowlist
    unavailable". Admitting everyone there would silently open the catalog to any IAP
    caller, so the endpoint refuses with 503 instead.
    """
    from embrapa_dashboard.webapi import routes

    client = _client(monkeypatch, dev_author="alice@embrapa.br")
    monkeypatch.setattr(routes, "_ensure_catalog_editors_table", lambda: False)
    monkeypatch.setattr(routes, "_catalog_editor_allowlist", lambda _r: set())

    resp = client.post("/api/catalog/entry", json={"codigo_produto": "4403", "banco": "pevs"})
    assert resp.status_code == 503
    assert "indisponível" in resp.get_json()["error"]


def test_can_edit_reports_false_when_the_allowlist_lookup_faults(monkeypatch):
    """`/me`'s can_edit is only a UX affordance, but a lookup fault must still read as
    "cannot edit" (hide the controls) rather than leaking an optimistic true."""
    from embrapa_dashboard.webapi import routes

    client = _client(monkeypatch, dev_author="alice@embrapa.br")

    def boom(_resource):
        raise RuntimeError("bigquery down")

    monkeypatch.setattr(routes, "_catalog_editor_allowlist", boom)
    monkeypatch.setattr(routes.seam, "catalog_worklist", lambda _b=None: [])
    monkeypatch.setattr(routes.seam, "catalog_driven_bancos", lambda: [])
    body = client.get("/api/catalog/entries").get_json()
    assert body["can_edit"] is False


def test_group_worklist_is_readable_behind_iap(monkeypatch):
    """Read is open behind IAP — no editor allowlist required."""
    from embrapa_dashboard.webapi import routes

    client = _client(monkeypatch, dev_author="alice@embrapa.br")
    monkeypatch.setattr(
        routes.seam, "group_worklist", lambda: [{"group_id": "g1", "group_name": "Madeira", "n": 3}]
    )
    resp = client.get("/api/catalog/groups")
    assert resp.status_code == 200
    assert resp.get_json()[0]["group_name"] == "Madeira"


def test_group_upsert_rejects_a_missing_name_before_writing(monkeypatch):
    """A nameless group would be unidentifiable in the UI forever (the log is
    append-only), so the write is refused rather than recorded."""
    from embrapa_dashboard.webapi import routes

    client = _client(monkeypatch, dev_author="alice@embrapa.br")
    monkeypatch.setattr(routes, "_ensure_catalog_editors_table", lambda: True)
    monkeypatch.setattr(routes, "_catalog_editor_allowlist", lambda _r: set())
    recorded = []
    monkeypatch.setattr(routes.seam, "record_group", lambda b: recorded.append(b) or {})

    resp = client.post("/api/catalog/group", json={"group_name": "   "})
    assert resp.status_code == 400
    assert recorded == []  # nothing was written


def test_group_remove_requires_an_editor(monkeypatch):
    """The delete path goes through the same allowlist as every other catalog write."""
    from embrapa_dashboard.webapi import routes

    client = _client(monkeypatch)  # no identity at all
    monkeypatch.setattr(routes, "ensure_catalog_editors_table", lambda: None)
    resp = client.post("/api/catalog/group/remove", json={"group_id": "g1"})
    assert resp.status_code == 401


def test_group_upsert_requires_an_editor(monkeypatch):
    """The create/rename path goes through the same allowlist as every other catalog
    write — no identity, no write (and the 401 comes back before the body is even read)."""
    from embrapa_dashboard.webapi import routes

    client = _client(monkeypatch)  # no identity at all
    monkeypatch.setattr(routes, "ensure_catalog_editors_table", lambda: None)
    recorded = []
    monkeypatch.setattr(routes.seam, "record_group", lambda b: recorded.append(b) or {})

    resp = client.post("/api/catalog/group", json={"group_name": "Madeira"})
    assert resp.status_code == 401
    assert recorded == []
