"""The heartbeat records that a run HAPPENED — and must never be able to break it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from embrapa_dashboard import doctor, ingestion_heartbeat


@pytest.fixture
def settings(settings_factory):
    return settings_factory()


def test_record_writes_one_row(settings) -> None:
    client = MagicMock()
    client.insert_rows_json.return_value = []
    assert ingestion_heartbeat.record(
        "ibge-pam", "ok", duration_s=12.5, settings=settings, client=client
    )
    (fqn, rows), _ = client.insert_rows_json.call_args
    assert "ingestion_heartbeat" in fqn
    assert rows[0]["source"] == "ibge-pam"
    assert rows[0]["outcome"] == "ok"
    assert rows[0]["duration_s"] == 12.5


def test_record_never_raises_when_bigquery_fails(settings) -> None:
    """The contract that matters: a monitoring row must not be able to fail an ingest."""
    client = MagicMock()
    client.insert_rows_json.side_effect = RuntimeError("quota exceeded")
    assert ingestion_heartbeat.record("comex", "ok", settings=settings, client=client) is False


def test_record_reports_insert_errors_without_raising(settings) -> None:
    client = MagicMock()
    client.insert_rows_json.return_value = [{"index": 0, "errors": ["bad row"]}]
    assert ingestion_heartbeat.record("comex", "ok", settings=settings, client=client) is False


def test_record_truncates_a_long_detail(settings) -> None:
    client = MagicMock()
    client.insert_rows_json.return_value = []
    ingestion_heartbeat.record("x", "failed", detail="e" * 900, settings=settings, client=client)
    (_, rows), _ = client.insert_rows_json.call_args
    assert len(rows[0]["detail"]) == 500


# ── doctor's reader ──────────────────────────────────────────────────────────
def _rows(*pairs):
    now = datetime.now(UTC)
    return [SimpleNamespace(source=s, last_run=now - timedelta(days=d)) for s, d in pairs]


def _patch(rows):
    client = MagicMock()
    client.query.return_value.result.return_value = rows
    return patch("embrapa_dashboard.doctor.bigquery.Client", return_value=client)


def test_heartbeat_check_passes_when_every_source_ran_in_window(settings) -> None:
    with _patch(_rows(("ibge", 1), ("ibge-pam", 10))):
        result = doctor._check_ingest_heartbeat(settings)
    assert result.ok is True
    assert "⚠" not in result.detail


def test_heartbeat_check_warns_when_a_daily_source_stopped(settings) -> None:
    """The blind spot itself: nightly source silent for a week, no failure anywhere."""
    with _patch(_rows(("ibge", 7), ("ibge-pam", 10))):
        result = doctor._check_ingest_heartbeat(settings)
    assert "⚠" in result.detail
    assert "ibge " in result.detail + " "
    assert "ibge-pam" not in result.detail.split("(")[0]


def test_heartbeat_check_gives_monthly_sources_a_monthly_window(settings) -> None:
    """10 days silent is fine for a monthly trigger and broken for a nightly one."""
    with _patch(_rows(("ibge-pam", 10))):
        assert "⚠" not in doctor._check_ingest_heartbeat(settings).detail
    with _patch(_rows(("ibge-pam", 40))):
        assert "⚠" in doctor._check_ingest_heartbeat(settings).detail


def test_heartbeat_check_is_quiet_before_any_run_is_recorded(settings) -> None:
    with _patch([]):
        result = doctor._check_ingest_heartbeat(settings)
    assert result.ok is True
    assert "no heartbeat recorded yet" in result.detail


def test_heartbeat_check_ignores_a_source_never_observed(settings) -> None:
    """A source absent from the table is not called broken — the table only fills forward."""
    with _patch(_rows(("ibge", 1))):
        result = doctor._check_ingest_heartbeat(settings)
    assert "⚠" not in result.detail
    assert "comtrade" not in result.detail


def test_heartbeat_check_reports_a_query_failure(settings) -> None:
    client = MagicMock()
    client.query.side_effect = RuntimeError("table not found")
    with patch("embrapa_dashboard.doctor.bigquery.Client", return_value=client):
        assert doctor._check_ingest_heartbeat(settings).ok is False


def test_record_creates_the_table_once_and_retries(settings) -> None:
    """First heartbeat ever: the insert 404s, the table is created, the retry lands.

    Pinned because the alternative — ensuring the table on EVERY write — is what the first
    version did, and it charged a get_dataset + create_table round-trip to every ingest.
    """
    from google.api_core.exceptions import NotFound

    client = MagicMock()
    client.insert_rows_json.side_effect = [NotFound("no such table"), []]
    with patch("embrapa_dashboard.ingestion_heartbeat.ensure_heartbeat_table") as ensure:
        assert ingestion_heartbeat.record("ibge", "ok", settings=settings, client=client) is True
    assert ensure.call_count == 1
    assert client.insert_rows_json.call_count == 2


def test_record_does_not_touch_the_table_when_the_insert_succeeds(settings) -> None:
    client = MagicMock()
    client.insert_rows_json.return_value = []
    with patch("embrapa_dashboard.ingestion_heartbeat.ensure_heartbeat_table") as ensure:
        ingestion_heartbeat.record("ibge", "ok", settings=settings, client=client)
    ensure.assert_not_called()
