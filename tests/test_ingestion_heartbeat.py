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


def _patch(rows, table_age_days: float = 1.0):
    """`table_age_days` = how long the heartbeat table has existed.

    It is the reference for "never reported": before the table outlives a source's
    window, silence means nothing (the table starts empty); after, it means the trigger
    never fired once. Defaults to 1 day so the existing cases stay in the first regime.
    """
    client = MagicMock()
    client.query.return_value.result.return_value = rows
    client.get_table.return_value.created = datetime.now(UTC) - timedelta(days=table_age_days)
    return patch("embrapa_dashboard.doctor.bigquery.Client", return_value=client)


def test_heartbeat_check_passes_when_every_source_ran_in_window(settings) -> None:
    with _patch(_rows(("ibge", 1), ("ibge-pam", 10))):
        result = doctor._check_ingest_heartbeat(settings)
    assert result.ok is True
    assert "⚠" not in result.detail


def test_heartbeat_check_warns_when_a_daily_source_stopped(settings) -> None:
    """The blind spot itself: the daily FX trigger silent for a week, no failure anywhere."""
    with _patch(_rows(("bcb-currency", 7), ("ibge-pam", 10))):
        result = doctor._check_ingest_heartbeat(settings)
    assert "⚠" in result.detail
    assert "bcb-currency" in result.detail
    assert "ibge-pam" not in result.detail.split("(")[0]


def test_heartbeat_check_gives_monthly_sources_a_monthly_window(settings) -> None:
    """10 days silent is fine for a monthly trigger and broken for a daily one."""
    with _patch(_rows(("ibge-pam", 10))):
        assert "⚠" not in doctor._check_ingest_heartbeat(settings).detail
    with _patch(_rows(("ibge-pam", 40))):
        assert "⚠" in doctor._check_ingest_heartbeat(settings).detail


def test_heartbeat_check_is_quiet_before_any_run_is_recorded(settings) -> None:
    with _patch([]):
        result = doctor._check_ingest_heartbeat(settings)
    assert result.ok is True
    assert "no heartbeat recorded yet" in result.detail


def test_heartbeat_check_does_not_call_a_never_observed_source_broken_too_early(settings) -> None:
    """A source absent from a NEW table is not called broken — the table fills forward.

    It is still NAMED, though. The check used to drop such a source from the line and
    then conclude "every scheduled ingest ran" over the survivors — a sentence that
    claimed the whole while counting a subset. It now accounts for every source.
    """
    with _patch(_rows(("ibge", 1)), table_age_days=1):
        result = doctor._check_ingest_heartbeat(settings)
    assert "⚠" not in result.detail
    assert "comtrade" in result.detail  # named, not silently dropped
    assert "sem primeiro registro" in result.detail
    assert "every" not in result.detail.lower()  # no claim over the subset that reported


def test_heartbeat_check_flags_a_source_that_NEVER_reported_once_the_table_outlives_its_window(
    settings,
) -> None:
    """The case a brand-new trigger is in, and the one that used to be invisible.

    A scheduler created with the wrong args/service account never fires at all, so it
    never writes a heartbeat — and "no row" read identically to "not shipped yet",
    forever. Once the table has existed longer than the source's own window, silence
    stops being "not yet".
    """
    # 40 days of observation: past every source's window (daily 4, weekly 10, monthly 34).
    with _patch(_rows(("bcb-currency", 0)), table_age_days=40):
        result = doctor._check_ingest_heartbeat(settings)
    assert "⚠" in result.detail
    assert "nunca rodou" in result.detail
    assert "ibge" in result.detail  # the weekly batch's sources
    assert "bcb-currency" not in result.detail.split("nunca rodou")[1]  # this one did run


def test_heartbeat_check_separates_stopped_from_never_started(settings) -> None:
    """Two different diagnoses: a trigger that DIED vs one that was never born.

    They need different fixes — check the Job's executions vs check how the scheduler was
    created — so the line must not merge them into one word.
    """
    with _patch(_rows(("bcb-currency", 30)), table_age_days=40):
        detail = doctor._check_ingest_heartbeat(settings).detail
    assert "parou de rodar" in detail and "bcb-currency" in detail.split("parou de rodar")[1]
    assert "nunca rodou" in detail


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
