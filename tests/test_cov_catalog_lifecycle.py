"""Coverage tests for ``serving/catalog_lifecycle.py``.

These exercise the REAL helper implementations (rather than monkeypatching them away
as the broader suite in ``tests/test_serving.py`` does): ``_insert_lifecycle_event``'s
parameterized DML, ``_current_status`` / ``_current_lifecycle`` reads + their empty/NotFound
branches, the ``auto_mark_orphans`` early-return branches, ``invalidate_lifecycle_cache``,
and the ``_backup_status`` body via ``purge_plan``.

Reuses the hermetic settings helpers from ``tests/test_serving.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest

from tests.test_serving import _one_orphan_df, _settings


def _status_df(rows):
    """Build a lifecycle-status DataFrame with the columns the helpers read."""
    import pandas as pd

    return pd.DataFrame(rows)


def test_insert_lifecycle_event_builds_parameterized_dml(monkeypatch):
    """_insert_lifecycle_event (lines 81-100): server-side timestamp + 8 scalar params."""
    # A tabela SIDRA faz parte da identidade do produto e o funil a resolve no
    # CATÁLOGO — senão o evento marca a sentinela em vez do produto. Este teste
    # exercita a DML do funil, não o catálogo, então a resolução é dublada.
    monkeypatch.setattr(
        "embrapa_dashboard.serving.curation.tabela_do_produto", lambda *a, **k: "291"
    )
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import catalog_lifecycle

    bq = mock.Mock()
    catalog_lifecycle._insert_lifecycle_event(
        bq,
        "proj.research_inputs.catalog_lifecycle_log",
        element_kind="commodity",
        banco="comex",
        code="20079926",
        status="descontinuado",
        reason="removed",
        purge_note="warning",
        edited_by="system:orphan-detector",
        change_id="descontinuado:commodity:comex:20079926:0",
    )

    # The DML ran (query().result()).
    bq.query.assert_called_once()
    sql_arg = bq.query.call_args.args[0]
    assert "insert into" in sql_arg
    assert "current_timestamp()" in sql_arg  # server-side timestamp, not a param
    job_config = bq.query.call_args.kwargs["job_config"]
    params = {p.name: p.value for p in job_config.query_parameters}
    assert params["element_kind"] == "commodity"
    assert params["banco"] == "comex"
    assert params["code"] == "20079926"
    assert params["status"] == "descontinuado"
    assert params["reason"] == "removed"
    assert params["purge_note"] == "warning"
    assert params["edited_by"] == "system:orphan-detector"
    assert params["change_id"] == "descontinuado:commodity:comex:20079926:0"
    bq.query.return_value.result.assert_called_once()


def test_current_status_maps_rows_and_normalizes_code(monkeypatch):
    """_current_status (lines 105, 109-111): maps a populated lifecycle df to a status dict,
    normalizing a non-None code to str and keeping a None code as None."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import catalog_lifecycle, gateway

    # A populated commodity row → code normalized to str.
    monkeypatch.setattr(
        gateway,
        "fetch_lifecycle_status",
        lambda: _status_df(
            [
                {
                    "element_kind": "commodity",
                    "banco": "comex",
                    "code": "20079926",
                    "status": "descontinuado",
                    "flagged_at": None,
                }
            ]
        ),
    )
    out = catalog_lifecycle._current_status(_settings())
    assert out[("commodity", "comex", "20079926")] == "descontinuado"

    # A banco row with a genuine None code → key keeps None (own single-col frame so
    # pandas doesn't promote None to NaN via a mixed-type column).
    monkeypatch.setattr(
        gateway,
        "fetch_lifecycle_status",
        lambda: _status_df(
            [
                {
                    "element_kind": "banco",
                    "banco": "comex",
                    "code": None,
                    "status": "purged",
                    "flagged_at": None,
                }
            ]
        ),
    )
    out2 = catalog_lifecycle._current_status(_settings())
    assert out2[("banco", "comex", None)] == "purged"


def test_current_status_notfound_returns_empty(monkeypatch):
    """_current_status (lines 106-108): a missing log (NotFound) → {}."""
    pytest.importorskip("flask_caching")
    from google.api_core.exceptions import NotFound

    from embrapa_dashboard.serving import catalog_lifecycle, gateway

    def _raise():
        raise NotFound("no lifecycle log yet")

    monkeypatch.setattr(gateway, "fetch_lifecycle_status", _raise)
    assert catalog_lifecycle._current_status(_settings()) == {}


def test_current_status_empty_df_returns_empty(monkeypatch):
    """_current_status (lines 109-110): an empty/None df → {}."""
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import catalog_lifecycle, gateway

    monkeypatch.setattr(gateway, "fetch_lifecycle_status", lambda: pd.DataFrame())
    assert catalog_lifecycle._current_status(_settings()) == {}
    monkeypatch.setattr(gateway, "fetch_lifecycle_status", lambda: None)
    assert catalog_lifecycle._current_status(_settings()) == {}


def test_current_lifecycle_maps_status_and_flagged_at(monkeypatch):
    """_current_lifecycle (lines 129-132): maps rows to (status, flagged_at) tuples."""
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import catalog_lifecycle, gateway

    flagged = pd.Timestamp("2026-06-26T12:00:00Z")
    monkeypatch.setattr(
        gateway,
        "fetch_lifecycle_status",
        lambda: _status_df(
            [
                {
                    "element_kind": "commodity",
                    "banco": "comex",
                    "code": "20079926",
                    "status": "descontinuado",
                    "flagged_at": flagged,
                }
            ]
        ),
    )
    out = catalog_lifecycle._current_lifecycle(_settings())
    status, at = out[("commodity", "comex", "20079926")]
    assert status == "descontinuado" and at == flagged


def test_current_lifecycle_empty_df_returns_empty(monkeypatch):
    """_current_lifecycle (line 128): an empty df → {}."""
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import catalog_lifecycle, gateway

    monkeypatch.setattr(gateway, "fetch_lifecycle_status", lambda: pd.DataFrame())
    assert catalog_lifecycle._current_lifecycle(_settings()) == {}


def test_current_lifecycle_notfound_returns_empty(monkeypatch):
    """_current_lifecycle (lines 125-126): NotFound → {}."""
    pytest.importorskip("flask_caching")
    from google.api_core.exceptions import NotFound

    from embrapa_dashboard.serving import catalog_lifecycle, gateway

    def _raise():
        raise NotFound("no lifecycle log yet")

    monkeypatch.setattr(gateway, "fetch_lifecycle_status", _raise)
    assert catalog_lifecycle._current_lifecycle(_settings()) == {}


def test_auto_mark_orphans_notfound_short_circuits(monkeypatch):
    """auto_mark_orphans (lines 144-146): a missing orphan source (NotFound) → all-zero."""
    pytest.importorskip("flask_caching")
    from google.api_core.exceptions import NotFound

    from embrapa_dashboard.serving import catalog_lifecycle, gateway

    def _raise():
        raise NotFound("no orphan view")

    monkeypatch.setattr(gateway, "fetch_orphan_produtos", _raise)
    res = catalog_lifecycle.auto_mark_orphans(settings=_settings(), client=mock.Mock())
    assert res == {"detected": 0, "newly_marked": 0, "already_marked": 0}


def test_auto_mark_orphans_empty_orphans_short_circuits(monkeypatch):
    """auto_mark_orphans (lines 147-148): no orphans (empty / None df) → all-zero."""
    pytest.importorskip("flask_caching")
    import pandas as pd

    from embrapa_dashboard.serving import catalog_lifecycle, gateway

    monkeypatch.setattr(gateway, "fetch_orphan_produtos", lambda: pd.DataFrame())
    res = catalog_lifecycle.auto_mark_orphans(settings=_settings(), client=mock.Mock())
    assert res == {"detected": 0, "newly_marked": 0, "already_marked": 0}

    monkeypatch.setattr(gateway, "fetch_orphan_produtos", lambda: None)
    res2 = catalog_lifecycle.auto_mark_orphans(settings=_settings(), client=mock.Mock())
    assert res2 == {"detected": 0, "newly_marked": 0, "already_marked": 0}


def test_auto_mark_orphans_skips_already_marked_no_timestamps(monkeypatch):
    """auto_mark_orphans (lines 171-172): the orphan has no removed_at and a prior lifecycle
    entry whose status is 'descontinuado' → fall back to status, skip (no insert)."""
    pytest.importorskip("flask_caching")

    from embrapa_dashboard.serving import catalog_lifecycle, gateway

    # _one_orphan_df has NO removed_at column → removed_at is None.
    monkeypatch.setattr(gateway, "fetch_orphan_produtos", _one_orphan_df)
    # A prior lifecycle entry for the SAME (commodity, comex, 20079926), flagged_at None.
    monkeypatch.setattr(
        gateway,
        "fetch_lifecycle_status",
        lambda: _status_df(
            [
                {
                    "element_kind": "commodity",
                    "banco": "comex",
                    "code": "20079926",
                    "status": "descontinuado",
                    "flagged_at": None,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        catalog_lifecycle, "ensure_catalog_lifecycle_log_table", lambda *a, **k: "p.r.l"
    )
    # If we reach the insert path the test fails — the elif-status branch must `continue`.
    monkeypatch.setattr(
        catalog_lifecycle,
        "_insert_lifecycle_event",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not insert when status-marked")),
    )
    monkeypatch.setattr(catalog_lifecycle, "_change_id_seen", lambda *a, **k: False)

    res = catalog_lifecycle.auto_mark_orphans(settings=_settings(), client=mock.Mock())
    assert res == {"detected": 1, "newly_marked": 0, "already_marked": 1}


def test_invalidate_lifecycle_cache_calls_delete_memoized(monkeypatch):
    """invalidate_lifecycle_cache (lines 209-211): delete_memoized is called for both readers."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import catalog_lifecycle, gateway
    from embrapa_dashboard.serving.cache import cache

    deleted = []
    monkeypatch.setattr(cache, "delete_memoized", lambda fn: deleted.append(fn))
    catalog_lifecycle.invalidate_lifecycle_cache()
    assert gateway.fetch_lifecycle_status in deleted
    assert gateway.fetch_orphan_produtos in deleted


def test_invalidate_lifecycle_cache_swallows_backend_error(monkeypatch):
    """invalidate_lifecycle_cache: a cache-backend error is logged, not raised (best-effort)."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import catalog_lifecycle
    from embrapa_dashboard.serving.cache import cache

    def _boom(fn):
        raise RuntimeError("cache unbound")

    monkeypatch.setattr(cache, "delete_memoized", _boom)
    # Must not raise.
    catalog_lifecycle.invalidate_lifecycle_cache()


def test_purge_plan_backup_status_complete(monkeypatch):
    """purge_plan + _backup_status (lines 233-260, happy path): a fresh COMPLETE snapshot →
    backup_ok True with the snapshot timestamp message, and scoped DELETEs for the banco."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard import doctor
    from embrapa_dashboard.serving import catalog_lifecycle

    monkeypatch.setattr(catalog_lifecycle.gateway, "fetch_orphan_produtos", _one_orphan_df)
    # The re-added guard hits BQ for the live catalog state; stub it for the backup-gate cases.
    monkeypatch.setattr(catalog_lifecycle, "_refuse_if_re_added", lambda *a, **k: None)
    monkeypatch.setattr(
        catalog_lifecycle,
        "_current_status",
        lambda cfg: {("commodity", "comex", "20079926"): "descontinuado"},
    )
    # Stub the GCS client + credentials so _backup_status runs its real body.
    monkeypatch.setattr("embrapa_dashboard.config.get_credentials", lambda s: None)
    monkeypatch.setattr(
        "google.cloud.storage.Client", lambda project=None, credentials=None: mock.Mock()
    )
    # Relative to now so the stubbed snapshot is ALWAYS inside the staleness window.
    # A hardcoded date silently becomes "stale" once wall-clock passes
    # backup_staleness_days (14), flipping backup_ok to False — this test failed on
    # exactly the 14-day boundary (stub 2026-06-27 vs a 2026-07-11 CI run).
    latest = datetime.now(UTC) - timedelta(days=2)
    monkeypatch.setattr(doctor, "_list_backup_runs", lambda c, s: [(latest, "run=x/")])
    monkeypatch.setattr(doctor, "_latest_complete_run", lambda c, s, runs: (latest, 0))

    plan = catalog_lifecycle.purge_plan("comex", "20079926", settings=_settings())
    assert plan["backup_ok"] is True
    assert latest.strftime("%Y-%m-%d") in plan["backup_msg"]
    assert any("gold_comex_flows" in s and "= '20079926'" in s for s in plan["statements"])
    assert all(s.strip().startswith("DELETE FROM") for s in plan["statements"])


def test_purge_plan_backup_no_runs(monkeypatch):
    """_backup_status (lines 245-246): no snapshot runs at all → backup_ok False."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard import doctor
    from embrapa_dashboard.serving import catalog_lifecycle

    monkeypatch.setattr(catalog_lifecycle.gateway, "fetch_orphan_produtos", _one_orphan_df)
    # The re-added guard hits BQ for the live catalog state; stub it for the backup-gate cases.
    monkeypatch.setattr(catalog_lifecycle, "_refuse_if_re_added", lambda *a, **k: None)
    monkeypatch.setattr(
        catalog_lifecycle,
        "_current_status",
        lambda cfg: {("commodity", "pevs", "1234"): "descontinuado"},
    )
    monkeypatch.setattr("embrapa_dashboard.config.get_credentials", lambda s: None)
    monkeypatch.setattr(
        "google.cloud.storage.Client", lambda project=None, credentials=None: mock.Mock()
    )
    monkeypatch.setattr(doctor, "_list_backup_runs", lambda c, s: [])

    plan = catalog_lifecycle.purge_plan("pevs", "1234", settings=_settings())
    assert plan["backup_ok"] is False
    assert "no Gold snapshot" in plan["backup_msg"]


def test_purge_plan_backup_only_partial(monkeypatch):
    """_backup_status (lines 247-252): runs exist but none are COMPLETE → backup_ok False."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard import doctor
    from embrapa_dashboard.serving import catalog_lifecycle

    monkeypatch.setattr(catalog_lifecycle.gateway, "fetch_orphan_produtos", _one_orphan_df)
    # The re-added guard hits BQ for the live catalog state; stub it for the backup-gate cases.
    monkeypatch.setattr(catalog_lifecycle, "_refuse_if_re_added", lambda *a, **k: None)
    monkeypatch.setattr(
        catalog_lifecycle,
        "_current_status",
        lambda cfg: {("commodity", "comex", "20079926"): "descontinuado"},
    )
    monkeypatch.setattr("embrapa_dashboard.config.get_credentials", lambda s: None)
    monkeypatch.setattr(
        "google.cloud.storage.Client", lambda project=None, credentials=None: mock.Mock()
    )
    monkeypatch.setattr(
        doctor, "_list_backup_runs", lambda c, s: [(datetime(2026, 1, 1, tzinfo=UTC), "run=x/")]
    )
    monkeypatch.setattr(doctor, "_latest_complete_run", lambda c, s, runs: (None, 1))

    plan = catalog_lifecycle.purge_plan("comex", "20079926", settings=_settings())
    assert plan["backup_ok"] is False
    assert "COMPLETE" in plan["backup_msg"]


def test_purge_plan_backup_stale(monkeypatch):
    """_backup_status (lines 253-259): the newest complete snapshot is older than the
    staleness threshold → backup_ok False with the age message."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard import doctor
    from embrapa_dashboard.serving import catalog_lifecycle

    monkeypatch.setattr(catalog_lifecycle.gateway, "fetch_orphan_produtos", _one_orphan_df)
    # The re-added guard hits BQ for the live catalog state; stub it for the backup-gate cases.
    monkeypatch.setattr(catalog_lifecycle, "_refuse_if_re_added", lambda *a, **k: None)
    monkeypatch.setattr(
        catalog_lifecycle,
        "_current_status",
        lambda cfg: {("commodity", "comex", "20079926"): "descontinuado"},
    )
    monkeypatch.setattr("embrapa_dashboard.config.get_credentials", lambda s: None)
    monkeypatch.setattr(
        "google.cloud.storage.Client", lambda project=None, credentials=None: mock.Mock()
    )
    # A snapshot well beyond the default staleness window (14 days).
    old = datetime(2020, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(doctor, "_list_backup_runs", lambda c, s: [(old, "run=x/")])
    monkeypatch.setattr(doctor, "_latest_complete_run", lambda c, s, runs: (old, 0))

    plan = catalog_lifecycle.purge_plan("comex", "20079926", settings=_settings())
    assert plan["backup_ok"] is False
    assert "fresh backup" in plan["backup_msg"]


def test_purge_plan_backup_gcs_unreachable(monkeypatch):
    """_backup_status (lines 261-262): a GCS error is caught → backup_ok False."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import catalog_lifecycle

    monkeypatch.setattr(catalog_lifecycle.gateway, "fetch_orphan_produtos", _one_orphan_df)
    # The re-added guard hits BQ for the live catalog state; stub it for the backup-gate cases.
    monkeypatch.setattr(catalog_lifecycle, "_refuse_if_re_added", lambda *a, **k: None)
    monkeypatch.setattr(
        catalog_lifecycle,
        "_current_status",
        lambda cfg: {("commodity", "comex", "20079926"): "descontinuado"},
    )
    monkeypatch.setattr("embrapa_dashboard.config.get_credentials", lambda s: None)

    def _boom(project=None, credentials=None):
        raise RuntimeError("GCS unreachable")

    monkeypatch.setattr("google.cloud.storage.Client", _boom)

    plan = catalog_lifecycle.purge_plan("comex", "20079926", settings=_settings())
    assert plan["backup_ok"] is False
    assert "could not verify the backup" in plan["backup_msg"]


def test_mark_purged_refuses_when_not_descontinuado(monkeypatch):
    """mark_purged gate: a code whose current status is neither descontinuado nor purged
    (e.g. never marked) must raise ValueError, not record a premature terminal event."""
    pytest.importorskip("flask_caching")
    from embrapa_dashboard.serving import catalog_lifecycle as cl

    monkeypatch.setattr(cl, "ensure_catalog_lifecycle_log_table", lambda *a, **k: "t")
    # No lifecycle row for this code at all -> status is None -> refuse.
    monkeypatch.setattr(cl, "_current_lifecycle", lambda cfg: {})
    seen = []
    monkeypatch.setattr(cl, "_change_id_seen", lambda *a, **k: seen.append(1) or False)
    inserted = []
    monkeypatch.setattr(cl, "_insert_lifecycle_event", lambda *a, **k: inserted.append(k))
    with pytest.raises(ValueError):
        cl.mark_purged(
            "comex",
            "20079926",
            edited_by="op@embrapa.br",
            settings=_settings(),
            client=mock.Mock(),
        )
    assert inserted == []  # nothing recorded
    assert seen == []  # gate fires BEFORE the dedup/insert path


def test_mark_purged_records_when_descontinuado(monkeypatch):
    """mark_purged happy path: a currently-Descontinuado code records the terminal event."""
    pytest.importorskip("flask_caching")
    from datetime import datetime

    from embrapa_dashboard.serving import catalog_lifecycle as cl

    flagged = datetime(2026, 6, 26, 12, 0, 0)
    monkeypatch.setattr(cl, "ensure_catalog_lifecycle_log_table", lambda *a, **k: "t")
    monkeypatch.setattr(
        cl,
        "_current_lifecycle",
        lambda cfg: {("commodity", "comex", "20079926"): ("descontinuado", flagged)},
    )
    monkeypatch.setattr(cl, "_refuse_if_re_added", lambda *a, **k: None)
    monkeypatch.setattr(cl, "_change_id_seen", lambda *a, **k: False)
    monkeypatch.setattr(cl, "invalidate_lifecycle_cache", lambda: None)
    inserted = []
    monkeypatch.setattr(cl, "_insert_lifecycle_event", lambda *a, **k: inserted.append(k))
    out = cl.mark_purged(
        "comex",
        "20079926",
        edited_by="op@embrapa.br",
        settings=_settings(),
        client=mock.Mock(),
    )
    assert out["status"] == "purged" and out["deduped"] is False
    assert len(inserted) == 1 and inserted[0]["status"] == "purged"
