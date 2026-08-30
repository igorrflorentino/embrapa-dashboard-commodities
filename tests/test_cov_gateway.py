"""Coverage tests for src/embrapa_dashboard/serving/gateway.py.

Targets the gateway readers not exercised by tests/test_serving.py: the lazy
``_client`` builder, the geo-mesh / Curadoria-catalog / catalog-editors / orphan /
lifecycle direct-Gold readers, and the Dados raw-table + Referências seed
inspector branches (schema/rows/count, both the free ``list_rows`` shortcut and
the cost-guarded query path).

Mocking style is borrowed verbatim from tests/test_serving.py: monkeypatch
``gateway.run_query`` with a recorder, pin ``gateway.get_settings`` to a hermetic
``_isolated_settings()``, and run inside a SimpleCache-bound app context
(``_bind_simplecache``) so ``@cache.memoize`` resolves. ``_client`` is mocked for
the metadata (get_table / list_rows) reads.
"""

from __future__ import annotations

from unittest import mock

import pytest

# Reuse the shared helpers rather than redefining them.
from tests.test_serving import _bind_simplecache, _isolated_settings

# ── _client(): lazy per-process BigQuery client construction (68-69) ───────────


def test_client_builds_bigquery_client_from_settings(monkeypatch):
    """_client() is @lru_cache(maxsize=1); clear the cache, stub the BigQuery
    constructor + credentials, and assert it wires project/location/credentials
    from Settings — executing the construction body (68-69)."""
    from embrapa_dashboard.serving import gateway

    gateway._client.cache_clear()  # drop any client cached by an earlier test

    fake_client = object()
    captured = {}

    def fake_ctor(*, project, location, credentials):
        captured.update(project=project, location=location, credentials=credentials)
        return fake_client

    monkeypatch.setattr(gateway.bigquery, "Client", fake_ctor)
    monkeypatch.setattr(
        gateway, "get_settings", lambda: _isolated_settings(gcp_project_id="proj-x")
    )
    monkeypatch.setattr(gateway, "get_credentials", lambda settings: "CREDS")

    out = gateway._client()

    assert out is fake_client
    assert captured["project"] == "proj-x"
    assert captured["credentials"] == "CREDS"
    gateway._client.cache_clear()  # leave no fake client cached for later tests


# ── fetch_geo_municipio_mesh: static municipal mesh read (283-286) ─────────────


def test_fetch_geo_municipio_mesh_reads_dim_geo_municipio(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        return "MESH"

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_geo_municipio_mesh()

    assert out == "MESH"
    assert "p.gold.dim_geo_municipio" in recorded["query"]


def test_fetch_comtrade_reporters_per_year_counts_export_reporters(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        return "REPORTERS"

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_comtrade_reporters_per_year()

    assert out == "REPORTERS"
    assert "count(distinct reporter_iso_a3)" in recorded["query"]
    assert "serving_comtrade_annual" in recorded["query"]


# ── fetch_produto_catalog: latest-active row per (codigo, banco) (725-742) ───


def test_fetch_produto_catalog_unscoped_has_no_where_and_no_params(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        recorded["params"] = params
        return "CATALOG"

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_produto_catalog()

    assert out == "CATALOG"
    q = recorded["query"].lower()
    assert "p.research_inputs.produto_catalog_log" in q
    assert "where banco = @banco" not in q  # unscoped → no WHERE
    assert "_rn = 1 and active" in q
    assert recorded["params"] == []  # no banco → no bound params


def test_fetch_produto_catalog_scoped_binds_banco_param(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        recorded["params"] = {p.name: p for p in params}
        return "CATALOG"

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        gateway.fetch_produto_catalog(banco="ibge_pevs")

    assert "where banco = @banco" in recorded["query"]
    assert recorded["params"]["banco"].value == "ibge_pevs"


def test_fetch_produto_catalog_self_heals_on_missing_column(monkeypatch):
    """A produto_catalog_log that predates a SELECTed column (e.g. tabela added late)
    raises BadRequest; fetch self-heals via ensure + retries once instead of 500ing the read."""
    pytest.importorskip("flask_caching")
    from google.api_core.exceptions import BadRequest

    from embrapa_dashboard.serving import curation, gateway

    calls = {"n": 0, "ensured": False}

    def flaky(query, params, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BadRequest("Unrecognized name: tabela")
        return "CATALOG"

    monkeypatch.setattr(gateway, "run_query", flaky)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(
        curation,
        "ensure_produto_catalog_log_table",
        lambda *a, **k: calls.update(ensured=True) or "t",
    )
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_produto_catalog()

    assert out == "CATALOG"  # the retry after self-heal succeeded
    assert calls["n"] == 2 and calls["ensured"] is True


# ── fetch_catalog_editors: per-resource allowlist (751-760) ────────────────────


def test_fetch_catalog_editors_filters_by_resource_param(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        recorded["params"] = {p.name: p for p in params}
        return "EDITORS"

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_catalog_editors("produto_catalog")

    assert out == "EDITORS"
    q = recorded["query"].lower()
    assert "p.research_inputs.catalog_editors" in q
    assert "distinct lower(trim(email))" in q
    assert "resource = @resource" in q
    assert recorded["params"]["resource"].value == "produto_catalog"


# ── fetch_source_code_stats: per-code Gold aggregate (catalog status columns) ───


def test_fetch_source_code_stats_unknown_source_raises(monkeypatch):
    """An unknown banco token has no Gold fact table → NotFound (the seam skips it)."""
    pytest.importorskip("flask_caching")
    from google.api_core.exceptions import NotFound

    from embrapa_dashboard.serving import gateway

    app, cache = _bind_simplecache()
    with app.app_context(), pytest.raises(NotFound):
        cache.clear()
        gateway.fetch_source_code_stats("not_a_banco")


def test_fetch_source_code_stats_aggregates_by_code(monkeypatch):
    """A known banco drives ONE column-pruned aggregate over the Gold fact table:
    count(*) + min/max(reference_year) grouped by the exact code, max_bytes-guarded."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        recorded["max_bytes"] = kwargs.get("max_bytes")
        return "STATS"

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_source_code_stats("comtrade")

    assert out == "STATS"
    q = recorded["query"].lower()
    assert "gold_comtrade_flows" in q  # the comtrade Gold fact table
    assert "cast(cmd_code as string) as code" in q  # the comtrade code column
    assert "count(*) as n_rows" in q
    assert "min(reference_year) as year_start" in q and "max(reference_year) as year_end" in q
    assert "group by code" in q
    assert recorded["max_bytes"] == gateway.RAW_TABLE_MAX_BYTES  # cost guard applied


# ── fetch_orphan_produtos: tombstone step + Gold-exists step (782-820) ───────


def test_fetch_orphan_produtos_returns_early_when_no_tombstones(monkeypatch):
    """Step 1 returns an empty frame (nothing removed) → the function returns it
    WITHOUT scanning any Gold table (the common, cheap path)."""
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import gateway

    calls = []

    def recorder(query, params, **kwargs):
        calls.append(query)
        return pd.DataFrame()  # empty tombstone set → early return

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_orphan_produtos()

    assert out is not None and out.empty
    assert len(calls) == 1  # only the cheap tombstone scan ran, no Gold union
    assert "not active" in calls[0].lower()


def test_fetch_orphan_produtos_returns_empty_when_banco_unknown(monkeypatch):
    """A tombstoned row whose banco is NOT a known Gold source → the second-step
    set is empty, so an empty slice is returned without a Gold scan (line 804)."""
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import gateway

    calls = []

    def recorder(query, params, **kwargs):
        calls.append(query)
        return pd.DataFrame({"banco": ["unknown_banco"], "codigo_produto": ["X"]})

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_orphan_produtos()

    assert out is not None and out.empty
    assert len(calls) == 1  # no Gold-union query when no known banco


def test_fetch_orphan_produtos_scans_gold_for_known_banco(monkeypatch):
    """A tombstoned row for a KNOWN banco (pevs) drives the Step-2 Gold-union scan:
    the second run_query carries the gold_codes CTE + the LIKE-prefix EXISTS."""
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import gateway

    calls = []

    def recorder(query, params, **kwargs):
        calls.append(query)
        if len(calls) == 1:
            return pd.DataFrame({"banco": ["pevs"], "codigo_produto": ["X"]})
        return "ORPHANS"  # the Step-2 union query result

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_orphan_produtos()

    assert out == "ORPHANS"
    assert len(calls) == 2
    step2 = calls[1].lower()
    assert "gold_codes" in step2
    assert "gold_pevs_production" in step2
    assert "g.code = t.codigo_produto" in step2


# ── fetch_lifecycle_status: latest-wins status per element (828-842) ───────────


def test_fetch_lifecycle_status_reads_latest_row_per_element(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        recorded["params"] = params
        return "LIFECYCLE"

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_lifecycle_status()

    assert out == "LIFECYCLE"
    q = recorded["query"].lower()
    assert "p.research_inputs.catalog_lifecycle_log" in q
    assert "_rn = 1" in q
    assert "edited_at as flagged_at" in q
    assert recorded["params"] == []


# ── Dados inspector: _resolve_inspect_table success + visibility "" branches ───


def test_resolve_inspect_table_success_returns_fqn(monkeypatch):
    """The allowlisted (banco, table) resolves to a fully-qualified ref (line 1163)."""
    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    ref = gateway._resolve_inspect_table("ibge_pevs", "serving_pevs_annual")
    assert ref == "p.serving.serving_pevs_annual"


def test_inspect_visibility_predicate_empty_for_unknown_short_token(monkeypatch):
    """A Gold-fact table_id match whose banco has no short token / code map yields
    '' (line 1183). Patch the maps so the Gold table matches but the short lookup
    misses, exercising the early-return guard that is otherwise unreached."""
    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setitem(gateway._GOLD_TABLE, "weird_banco", "gold_weird")
    # No matching _SHORT_SOURCE / _GOLD_PRODUCT entry for "weird_banco".
    assert gateway._inspect_visibility_predicate("weird_banco", "gold_weird") == ""


# ── fetch_table_schema: column metadata read (1192-1194) ───────────────────────


def _schema_client(num_rows=7):
    """A mock BQ client whose get_table returns a 2-column schema + num_rows."""
    field_a = mock.Mock()
    field_a.name, field_a.field_type = "year", "INT64"
    field_b = mock.Mock()
    field_b.name, field_b.field_type = "product_code", "STRING"
    table = mock.Mock()
    table.schema = [field_a, field_b]
    table.num_rows = num_rows
    client = mock.Mock()
    client.get_table.return_value = table
    return client


def test_fetch_table_schema_returns_columns_and_row_count(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client(num_rows=42))
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_table_schema("ibge_pevs", "gold_pevs_production")

    assert out["num_rows"] == 42
    assert {c["name"] for c in out["columns"]} == {"year", "product_code"}
    assert {c["type"] for c in out["columns"]} == {"INT64", "STRING"}


# ── fetch_table_rows: free list_rows shortcut vs cost-guarded query (1212-1238) ─


def test_fetch_table_rows_serving_mart_uses_free_list_rows(monkeypatch):
    """A serving mart (vis == '') with no order/filter takes the FREE list_rows
    shortcut — run_query is never called."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    client = mock.Mock()
    client.list_rows.return_value.to_dataframe.return_value = "ROWS"

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: client)

    def boom(*a, **k):
        raise AssertionError("run_query must not run on the free list_rows path")

    monkeypatch.setattr(gateway, "run_query", boom)
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_table_rows("ibge_pevs", "serving_pevs_annual", limit=10)

    assert out == "ROWS"
    # limit is clamped via min(limit, RAW_TABLE_MAX_LIMIT); offset defaults to 0.
    assert client.list_rows.call_args.kwargs["max_results"] == 10
    assert client.list_rows.call_args.kwargs["start_index"] == 0


def test_fetch_table_rows_with_order_runs_cost_guarded_query(monkeypatch):
    """An ORDER BY forces the query path: it pulls the schema for the column
    allowlist and calls run_query with a tight max_bytes cap."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        recorded["max_bytes"] = kwargs.get("max_bytes")
        return "SORTED"

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client())
    monkeypatch.setattr(gateway, "run_query", recorder)
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_table_rows(
            "ibge_pevs", "serving_pevs_annual", limit=5, order_by="year", order_dir="desc"
        )

    assert out == "SORTED"
    assert recorded["max_bytes"] == gateway.RAW_TABLE_MAX_BYTES
    assert "order by" in recorded["query"].lower()


def test_fetch_table_rows_gated_gold_fact_always_queries(monkeypatch):
    """A Gold fact (vis != '') CANNOT use the free shortcut even with no order/filter —
    the F7 predicate forces the query path (the `not vis` guard at line 1218)."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        return "GATED"

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client())
    monkeypatch.setattr(gateway, "run_query", recorder)
    # Force a non-empty visibility predicate so the gated-Gold branch is taken.
    monkeypatch.setattr(gateway, "_inspect_visibility_predicate", lambda b, t: "and not exists (x)")
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_table_rows("ibge_pevs", "gold_pevs_production", limit=3)

    assert out == "GATED"
    assert recorded["query"]  # query path ran despite no order/filter


# ── fetch_table_count: cached num_rows vs cost-guarded COUNT(*) (1245-1259) ─────


def test_fetch_table_count_unfiltered_ungated_uses_cached_num_rows(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client(num_rows=99))

    def boom(*a, **k):
        raise AssertionError("run_query must not run for the free count path")

    monkeypatch.setattr(gateway, "run_query", boom)
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        n = gateway.fetch_table_count("ibge_pevs", "serving_pevs_annual")

    assert n == 99


def test_fetch_table_count_filtered_runs_count_query(monkeypatch):
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        return pd.DataFrame({"n": [17]})

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client())
    monkeypatch.setattr(gateway, "run_query", recorder)
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        n = gateway.fetch_table_count(
            "ibge_pevs", "serving_pevs_annual", filters=(("year", "eq", "2020"),)
        )

    assert n == 17
    assert "count" in recorded["query"].lower()


def test_fetch_table_count_filtered_empty_result_returns_zero(monkeypatch):
    """A filtered COUNT(*) whose result frame is empty → 0 (the falsy-empty branch)."""
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client())
    monkeypatch.setattr(gateway, "run_query", lambda q, p, **k: pd.DataFrame({"n": []}))
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        n = gateway.fetch_table_count(
            "ibge_pevs", "serving_pevs_annual", filters=(("year", "eq", "2020"),)
        )

    assert n == 0


# ── Referências seed inspector: resolve + schema + rows + count ────────────────


def test_resolve_seed_table_success_returns_silver_fqn(monkeypatch):
    """A consultable seed resolves to project.silver.<seed> (line 1388)."""
    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    ref = gateway._resolve_seed_table("historical_currency_factors")
    assert ref == "p.silver.historical_currency_factors"


def test_fetch_seed_schema_returns_columns_and_row_count(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client(num_rows=5))
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_seed_schema("historical_currency_factors")

    assert out["num_rows"] == 5
    assert {c["name"] for c in out["columns"]} == {"year", "product_code"}


def test_fetch_seed_rows_uses_free_list_rows_without_order(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    client = mock.Mock()
    client.list_rows.return_value.to_dataframe.return_value = "SEEDROWS"

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: client)

    def boom(*a, **k):
        raise AssertionError("run_query must not run on the free seed list_rows path")

    monkeypatch.setattr(gateway, "run_query", boom)
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_seed_rows("historical_currency_factors", limit=20, offset=3)

    assert out == "SEEDROWS"
    assert client.list_rows.call_args.kwargs["max_results"] == 20
    assert client.list_rows.call_args.kwargs["start_index"] == 3


def test_fetch_seed_rows_with_filter_runs_query(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        recorded["max_bytes"] = kwargs.get("max_bytes")
        return "FILTERED"

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client())
    monkeypatch.setattr(gateway, "run_query", recorder)
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        out = gateway.fetch_seed_rows(
            "historical_currency_factors",
            limit=10,
            filters=(("year", "eq", "1994"),),
        )

    assert out == "FILTERED"
    assert recorded["max_bytes"] == gateway.RAW_TABLE_MAX_BYTES


def test_fetch_seed_count_unfiltered_uses_cached_num_rows(monkeypatch):
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client(num_rows=123))

    def boom(*a, **k):
        raise AssertionError("run_query must not run for the free seed count path")

    monkeypatch.setattr(gateway, "run_query", boom)
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        n = gateway.fetch_seed_count("historical_currency_factors")

    assert n == 123


def test_fetch_seed_count_filtered_runs_count_query(monkeypatch):
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        return pd.DataFrame({"n": [8]})

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client())
    monkeypatch.setattr(gateway, "run_query", recorder)
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        n = gateway.fetch_seed_count(
            "historical_currency_factors", filters=(("year", "eq", "1994"),)
        )

    assert n == 8
    assert "count" in recorded["query"].lower()


def test_fetch_seed_count_filtered_empty_result_returns_zero(monkeypatch):
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    monkeypatch.setattr(gateway, "_client", lambda: _schema_client())
    monkeypatch.setattr(gateway, "run_query", lambda q, p, **k: pd.DataFrame({"n": []}))
    app, cache = _bind_simplecache()

    with app.app_context():
        cache.clear()
        n = gateway.fetch_seed_count(
            "historical_currency_factors", filters=(("year", "eq", "1994"),)
        )

    assert n == 0


# ── fetch_source_products_gold: UNGATED admin-editor product read (949-962) ────


def test_fetch_source_products_gold_reads_gold_ungated(monkeypatch):
    """The admin editor's product read hits the Gold fact table directly (no F7 gate),
    grouping by code — exercising the query builder body."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import gateway

    recorded = {}

    def recorder(query, params, **kwargs):
        recorded["query"] = query
        recorded["max_bytes"] = kwargs.get("max_bytes")
        return "PRODUCTS"

    monkeypatch.setattr(gateway, "run_query", recorder)
    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()
    with app.app_context():
        cache.clear()
        out = gateway.fetch_source_products_gold("ibge_pevs")

    assert out == "PRODUCTS"
    assert "gold_pevs_production" in recorded["query"]
    assert "group by code" in recorded["query"]
    assert recorded["max_bytes"] is not None  # cost-guarded


def test_fetch_source_products_gold_unknown_source_raises(monkeypatch):
    """An unknown source id → NotFound (no query)."""
    pytest.importorskip("flask_caching")
    from google.api_core.exceptions import NotFound

    from embrapa_dashboard.serving import gateway

    monkeypatch.setattr(gateway, "get_settings", lambda: _isolated_settings())
    app, cache = _bind_simplecache()
    with app.app_context():
        cache.clear()
        with pytest.raises(NotFound):
            gateway.fetch_source_products_gold("not_a_source")
