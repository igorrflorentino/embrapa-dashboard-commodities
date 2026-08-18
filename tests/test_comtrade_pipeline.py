"""Tests for the two-phase, chunked, resumable Comtrade pipeline. GCP + API mocked.

Phase 1 (sync_raw) archives one (year, reporter-batch) keyed call to the raw zone,
skipping past-year chunks already archived but always re-fetching the latest year;
Phase 2 (bronze_one) stamps ingestion_timestamp and loads Bronze. ``run`` enumerates
reporters and loops the chunk plan, resumable across a daily-quota interruption.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from embrapa_dashboard.comtrade import client, pipeline
from embrapa_dashboard.comtrade.client import ComtradeQuotaError
from embrapa_dashboard.config import Settings
from embrapa_dashboard.core import ChunkOutcome, IngestPartialFailure


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gcp_project_id="test-project",
        gcs_bucket="test-bucket",
        comtrade_api_key="secret-key",
        comtrade_cmd_codes="0801:castanha,44:madeira_carvao",
        comtrade_flows="X,M,RX,RM",
        comtrade_reporters="all",
        comtrade_start_year=2022,
        comtrade_end_year=2023,
        _env_file=None,
    )  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _stub_hs6(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-seed the HS6 cache (keyed on the fixture's scope) so sync_raw's
    resolve_cmd_codes never hits the network in tests (auto-reverted by monkeypatch)."""
    monkeypatch.setattr(
        pipeline, "_CMD_CODES_CACHE", {("0801", "44"): ["080121", "080122", "440710"]}
    )


def _bronze_df() -> pd.DataFrame:
    row = {c: "x" for c in client.BRONZE_COLUMNS}
    row["reporterCode"] = "76"
    row["partnerCode"] = "0"
    row["cmdCode"] = "080121"
    row["refYear"] = "2022"
    return pd.DataFrame([row], dtype="string").reindex(columns=client.BRONZE_COLUMNS)


# ─── _reporter_batches / _basename / plan_chunks ─────────────────────────────
def test_reporter_batches_sorts_then_chunks_by_size() -> None:
    reporters = [str(i) for i in range(60)]
    batches = pipeline._reporter_batches(reporters)
    assert len(batches) == 8  # 8×7 + 4 = 60 (REPORTER_BATCH_SIZE=8)
    assert [len(b) for b in batches] == [8, 8, 8, 8, 8, 8, 8, 4]
    # Deterministic sorted partition — input order doesn't matter.
    flat = [r for b in batches for r in b]
    assert flat == sorted(reporters)
    assert pipeline._reporter_batches(list(reversed(reporters))) == batches


def test_basename_is_stable_content_hash_not_index() -> None:
    # Same year + same reporter set (any order) → identical basename.
    a = pipeline._basename(2022, ["76", "842", "12"])
    assert a == pipeline._basename(2022, ["12", "76", "842"])
    assert a.startswith("2022_r")
    # Different reporter set or different year → different basename.
    assert pipeline._basename(2022, ["76", "842"]) != a
    assert pipeline._basename(2023, ["76", "842", "12"]) != a


def test_plan_chunks_enumerates_year_then_batch(settings) -> None:
    reporters = [str(i) for i in range(20)]  # 3 batches (8+8+4)
    chunks = pipeline.plan_chunks(settings, reporters)
    # 2 years × 3 batches = 6 chunks, year-then-batch order.
    assert [y for y, _ in chunks] == [2022, 2022, 2022, 2023, 2023, 2023]
    batches = pipeline._reporter_batches(reporters)
    assert [b for _, b in chunks] == batches + batches
    assert len(chunks[0][1]) == 8 and len(chunks[2][1]) == 4


# ─── resolve_cmd_codes ───────────────────────────────────────────────────────
def test_resolve_cmd_codes_expands_scope_once_and_caches(settings, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "_CMD_CODES_CACHE", {})  # override the autouse stub
    calls: list[list[str]] = []

    def fake_hs6(scope: list[str]) -> list[str]:
        calls.append(scope)
        return ["080121", "080122"]

    monkeypatch.setattr(pipeline.client, "list_hs6_codes", fake_hs6)
    first = pipeline.resolve_cmd_codes(settings)
    second = pipeline.resolve_cmd_codes(settings)
    assert first == ["080121", "080122"]
    assert second == first
    assert calls == [["0801", "44"]]  # scope from cmd_map keys; resolved once (cached)


# ─── bronze_schema ───────────────────────────────────────────────────────────
def test_bronze_schema_shape() -> None:
    schema = pipeline.bronze_schema()
    assert [f.name for f in schema] == [*client.BRONZE_COLUMNS, "ingestion_timestamp"]
    by_name = {f.name: f for f in schema}
    assert by_name["ingestion_timestamp"].field_type == "TIMESTAMP"
    assert by_name["ingestion_timestamp"].mode == "REQUIRED"
    assert by_name["reporterCode"].mode == "NULLABLE"


# ─── sync_raw (Phase 1) ──────────────────────────────────────────────────────
def test_sync_raw_skips_settled_year_already_archived(settings) -> None:
    """A SETTLED past year (older than the recent re-fetch window) whose raw exists is
    skipped — no API call. 2020 is > 2 years before end_year 2023, so every reporter has
    long since filed and there is nothing new to absorb (recent years re-fetch; see below)."""
    with (
        patch.object(pipeline, "raw_provenance", return_value={"source": "un-comtrade"}),
        patch.object(client, "fetch_chunk_adaptive") as fetch,
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2020, ["76"], storage_client=MagicMock())
    assert changed is False
    fetch.assert_not_called()
    land.assert_not_called()


def test_sync_raw_always_refetches_latest_year(settings) -> None:
    """The latest configured year is re-fetched even when raw already exists."""
    with (
        patch.object(pipeline, "raw_provenance", return_value={"x": "y"}) as prov,
        patch.object(client, "fetch_chunk_adaptive", return_value=_bronze_df()) as fetch,
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2023, ["76"], storage_client=MagicMock())
    assert changed is True
    prov.assert_not_called()  # latest year skips the freshness lookup
    fetch.assert_called_once()
    land.assert_called_once()


def test_sync_raw_force_ignores_archive(settings) -> None:
    with (
        patch.object(pipeline, "raw_provenance") as prov,
        patch.object(client, "fetch_chunk_adaptive", return_value=_bronze_df()),
        patch.object(pipeline, "land_raw"),
    ):
        changed = pipeline.sync_raw(settings, 2022, ["76"], storage_client=MagicMock(), force=True)
    assert changed is True
    prov.assert_not_called()


def test_sync_raw_latest_year_empty_lands_nothing(settings) -> None:
    """The latest year is re-fetched every run regardless, so an empty latest-year
    chunk needs no sentinel — it lands nothing and returns False."""
    with (
        patch.object(pipeline, "raw_provenance", return_value=None),
        patch.object(
            client, "fetch_chunk_adaptive", return_value=pd.DataFrame(columns=client.BRONZE_COLUMNS)
        ),
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2023, ["76"], storage_client=MagicMock())
    assert changed is False
    land.assert_not_called()


def test_sync_raw_past_year_empty_lands_sentinel(settings) -> None:
    """A *past*-year empty chunk lands an empty SENTINEL raw object (flagged
    ``empty``) so its existence resume-skips the chunk next run instead of
    re-fetching and re-billing the daily quota on every run."""
    with (
        patch.object(pipeline, "raw_provenance", return_value=None),
        patch.object(
            client, "fetch_chunk_adaptive", return_value=pd.DataFrame(columns=client.BRONZE_COLUMNS)
        ),
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2022, ["76"], storage_client=MagicMock())
    assert changed is True
    land.assert_called_once()
    land_kwargs = land.call_args.kwargs
    assert land_kwargs["basename"] == pipeline._basename(2022, ["76"])
    assert land_kwargs["provenance"]["empty"] == "true"
    assert land_kwargs["provenance"]["year"] == "2022"
    # The sentinel carries the Bronze schema so Phase 2 reads a valid 0-row frame.
    landed = land.call_args.args[0]
    assert list(landed.columns) == pipeline.BRONZE_STRING_COLUMNS
    assert len(landed) == 0


def test_sync_raw_recent_empty_sentinel_refetches(settings) -> None:
    """A RECENT past year (within comtrade_recent_refetch_years of end_year) whose raw is
    an EMPTY sentinel is RE-FETCHED — UN Comtrade may have published it since. 2022 is
    within 2 years of end_year 2023, so its empty sentinel does not permanently skip it."""
    with (
        patch.object(
            pipeline, "raw_provenance", return_value={"source": "un-comtrade", "empty": "true"}
        ),
        patch.object(client, "fetch_chunk_adaptive", return_value=_bronze_df()) as fetch,
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2022, ["76"], storage_client=MagicMock())
    assert changed is True
    fetch.assert_called_once()  # re-fetched despite the existing sentinel
    land.assert_called_once()


def test_sync_raw_old_empty_sentinel_still_skips(settings) -> None:
    """An empty sentinel OUTSIDE the recent window (year 2020, > 2 years before end_year
    2023) still resume-skips — that year is not coming, so no quota is re-billed."""
    with (
        patch.object(
            pipeline, "raw_provenance", return_value={"source": "un-comtrade", "empty": "true"}
        ),
        patch.object(client, "fetch_chunk_adaptive") as fetch,
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2020, ["76"], storage_client=MagicMock())
    assert changed is False
    fetch.assert_not_called()
    land.assert_not_called()


def test_sync_raw_recent_real_data_refetches(settings) -> None:
    """A recent year whose raw already holds REAL data is RE-FETCHED — reporters file with
    a ~1-2y lag, so an early fetch captured only some of the batch's reporters; the rest
    (and any revision to the early ones) would be frozen out forever if a non-empty recent
    raw resume-skipped. 2022 is within 2 years of end_year 2023, so it re-fetches."""
    with (
        patch.object(pipeline, "raw_provenance", return_value={"source": "un-comtrade"}),
        patch.object(client, "fetch_chunk_adaptive", return_value=_bronze_df()) as fetch,
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2022, ["76"], storage_client=MagicMock())
    assert changed is True
    fetch.assert_called_once()  # re-fetched despite existing real-data raw
    land.assert_called_once()


def test_sync_raw_fetches_and_lands_with_provenance(settings) -> None:
    with (
        patch.object(pipeline, "raw_provenance", return_value=None),
        patch.object(client, "fetch_chunk_adaptive", return_value=_bronze_df()) as fetch,
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2022, ["76", "842"], storage_client=MagicMock())
    assert changed is True
    fetch_kwargs = fetch.call_args.kwargs
    assert fetch_kwargs["reporters"] == ["76", "842"]
    assert fetch_kwargs["years"] == [2022]
    assert fetch_kwargs["cmd_codes"] == ["080121", "080122", "440710"]  # HS6-expanded
    assert fetch_kwargs["flows"] == ["X", "M", "RX", "RM"]
    land_kwargs = land.call_args.kwargs
    assert land_kwargs["source"] == "comtrade"
    assert land_kwargs["dataset"] == pipeline.RAW_DATASET
    # Content-keyed basename (not a positional index) + auditable reporter codes.
    assert land_kwargs["basename"] == pipeline._basename(2022, ["76", "842"])
    assert land_kwargs["provenance"]["source"] == "un-comtrade"
    assert land_kwargs["provenance"]["year"] == "2022"
    assert land_kwargs["provenance"]["reporter_codes"] == "76,842"
    assert land_kwargs["provenance"]["cmd_hs6_count"] == "3"


# ─── bronze_one (Phase 2) ────────────────────────────────────────────────────
def test_bronze_one_empty_raw_skips_load(settings) -> None:
    with (
        patch.object(
            pipeline, "read_raw", return_value=pd.DataFrame(columns=client.BRONZE_COLUMNS)
        ),
        patch.object(pipeline, "load_dataframe") as load,
    ):
        dest = pipeline.bronze_one(
            settings,
            2022,
            ["76"],
            storage_client=MagicMock(),
            bq_client=MagicMock(),
            table_fqn="p.d.t",
        )
    assert dest == ""
    load.assert_not_called()


def test_bronze_one_loads_with_timestamp_and_clustering(settings) -> None:
    with (
        patch.object(pipeline, "read_raw", return_value=_bronze_df()),
        patch.object(pipeline, "load_dataframe") as load,
    ):
        dest = pipeline.bronze_one(
            settings,
            2022,
            ["76"],
            storage_client=MagicMock(),
            bq_client=MagicMock(),
            table_fqn="p.d.t",
        )
    assert dest == "p.d.t"
    df = load.call_args.args[1]
    assert list(df.columns) == [*client.BRONZE_COLUMNS, "ingestion_timestamp"]
    kwargs = load.call_args.kwargs
    assert kwargs["clustering_fields"] == pipeline.CLUSTERING_FIELDS
    assert kwargs["time_partitioning_field"] == "ingestion_timestamp"


# ─── run orchestration ───────────────────────────────────────────────────────
def test_run_raises_without_api_key() -> None:
    s = Settings(gcp_project_id="p", gcs_bucket="b", comtrade_api_key="", _env_file=None)  # type: ignore[call-arg]
    with pytest.raises(RuntimeError, match="COMTRADE_API_KEY"):
        pipeline.run(s)


def test_run_enumerates_reporters_and_loads_changed_chunks(settings) -> None:
    reporters = [str(i) for i in range(30)]
    first_batch = pipeline._reporter_batches(reporters)[0]

    # Only (2022, first batch) "changed"; the rest skip → exactly one bronze load.
    def fake_sync(_s, year, batch, *, storage_client, force):
        return year == 2022 and batch == first_batch

    with (
        patch("embrapa_dashboard.gcp.clients.get_credentials", return_value=None),
        patch("embrapa_dashboard.gcp.clients.bigquery.Client"),
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch.object(pipeline, "ensure_destination", return_value="p.d.t"),
        patch.object(client, "list_reporters", return_value=reporters) as lr,
        patch.object(pipeline, "sync_raw", side_effect=fake_sync),
        patch.object(pipeline, "needs_bronze", side_effect=lambda *a, extracted, **k: extracted),
        patch.object(pipeline, "mark_bronze_loaded"),
        patch.object(pipeline, "bronze_one", return_value="p.d.t") as bronze,
    ):
        dest = pipeline.run(settings, full=False)
    assert dest == "p.d.t"
    lr.assert_called_once()  # "all" → enumerate from the reference
    assert bronze.call_count == 1
    assert bronze.call_args.args[1] == 2022
    assert bronze.call_args.args[2] == first_batch


def test_run_from_raw_skips_sync_uses_has_raw(settings) -> None:
    with (
        patch("embrapa_dashboard.gcp.clients.get_credentials", return_value=None),
        patch("embrapa_dashboard.gcp.clients.bigquery.Client"),
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch.object(pipeline, "ensure_destination", return_value="p.d.t"),
        patch.object(client, "list_reporters", return_value=[str(i) for i in range(30)]),
        patch.object(pipeline, "sync_raw") as sync,
        patch.object(pipeline, "has_raw", return_value=True),
        patch.object(pipeline, "mark_bronze_loaded"),
        patch.object(pipeline, "bronze_one", return_value="p.d.t") as bronze,
    ):
        dest = pipeline.run(settings, from_raw=True)
    assert dest == "p.d.t"
    sync.assert_not_called()  # from-raw never touches the API
    # 2 years × 4 batches (30 reporters / 8) = 8 chunks, all rebuilt.
    assert bronze.call_count == 8


def test_run_explicit_reporter_list_skips_enumeration(settings) -> None:
    settings = settings.model_copy(update={"comtrade_reporters": "76,842"})
    with (
        patch("embrapa_dashboard.gcp.clients.get_credentials", return_value=None),
        patch("embrapa_dashboard.gcp.clients.bigquery.Client"),
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch.object(pipeline, "ensure_destination", return_value="p.d.t"),
        patch.object(client, "list_reporters") as lr,
        patch.object(pipeline, "sync_raw", return_value=False),
        patch.object(pipeline, "bronze_one", return_value="p.d.t"),
    ):
        pipeline.run(settings)
    lr.assert_not_called()  # explicit list → no reference lookup


# ─── resolve_reporters (shared by run + CLI) ─────────────────────────────────
def test_resolve_reporters_all_enumerates_reference(settings) -> None:
    with patch.object(client, "list_reporters", return_value=["76", "842"]) as lr:
        assert pipeline.resolve_reporters(settings) == ["76", "842"]
    lr.assert_called_once()


def test_resolve_reporters_explicit_list_parses_csv(settings) -> None:
    settings = settings.model_copy(update={"comtrade_reporters": " 76 , 842 ,"})
    with patch.object(client, "list_reporters") as lr:
        assert pipeline.resolve_reporters(settings) == ["76", "842"]
    lr.assert_not_called()


# ─── continue-on-failure + aggregation + stop-on-quota (now inside run) ───────
def test_run_continues_after_chunk_failure_and_raises_aggregate(settings) -> None:
    """A transient chunk error doesn't strand the rest; with no on_chunk consumer
    the loop finishes then raises an aggregated IngestPartialFailure."""
    settings = settings.model_copy(update={"comtrade_reporters": "76,842"})  # 1 batch
    seen_years: list[int] = []

    def flaky(_s, year, _batch, *, storage_client, force):
        seen_years.append(year)
        if year == 2022:
            raise RuntimeError("network blip")
        return True

    with (
        patch("embrapa_dashboard.gcp.clients.get_credentials", return_value=None),
        patch("embrapa_dashboard.gcp.clients.bigquery.Client"),
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch.object(pipeline, "ensure_destination", return_value="p.d.t"),
        patch.object(pipeline, "sync_raw", side_effect=flaky),
        patch.object(pipeline, "needs_bronze", side_effect=lambda *a, extracted, **k: extracted),
        patch.object(pipeline, "mark_bronze_loaded"),
        patch.object(pipeline, "bronze_one", return_value="p.d.t"),
        pytest.raises(IngestPartialFailure) as exc,
    ):
        pipeline.run(settings, full=False)

    assert seen_years == [2022, 2023]  # 2022 failure did not stop 2023
    assert len(exc.value.failures) == 1  # the 2022 chunk


def test_run_with_on_chunk_reports_outcomes_without_raising(settings) -> None:
    settings = settings.model_copy(update={"comtrade_reporters": "76,842"})
    outcomes: list[ChunkOutcome] = []

    def flaky(_s, year, _batch, *, storage_client, force):
        if year == 2022:
            raise RuntimeError("blip")
        return True

    with (
        patch("embrapa_dashboard.gcp.clients.get_credentials", return_value=None),
        patch("embrapa_dashboard.gcp.clients.bigquery.Client"),
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch.object(pipeline, "ensure_destination", return_value="p.d.t"),
        patch.object(pipeline, "sync_raw", side_effect=flaky),
        patch.object(pipeline, "needs_bronze", side_effect=lambda *a, extracted, **k: extracted),
        patch.object(pipeline, "mark_bronze_loaded"),
        patch.object(pipeline, "bronze_one", return_value="p.d.t"),
    ):
        pipeline.run(settings, full=False, on_chunk=outcomes.append)

    assert [o.status for o in outcomes] == ["failed", "loaded"]


def test_run_stops_on_quota_and_propagates(settings) -> None:
    """A ComtradeQuotaError stops the loop immediately (no further chunks) and
    propagates so the CLI can report 'quota exhausted — re-run to resume'."""
    settings = settings.model_copy(update={"comtrade_reporters": "76,842"})
    seen_years: list[int] = []

    def quota_then_never(_s, year, _batch, *, storage_client, force):
        seen_years.append(year)
        raise ComtradeQuotaError("quota exhausted — re-run to resume")

    with (
        patch("embrapa_dashboard.gcp.clients.get_credentials", return_value=None),
        patch("embrapa_dashboard.gcp.clients.bigquery.Client"),
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch.object(pipeline, "ensure_destination", return_value="p.d.t"),
        patch.object(pipeline, "sync_raw", side_effect=quota_then_never),
        patch.object(pipeline, "bronze_one", return_value="p.d.t"),
        pytest.raises(ComtradeQuotaError),
    ):
        pipeline.run(settings, full=False)

    # Broke on the FIRST chunk's quota error — 2023 was never attempted.
    assert seen_years == [2022]


def test_run_one_chunk_marks_truncation_failed_without_stopping(settings, caplog) -> None:
    """A permanent ComtradeTruncationError is converted to a 'failed' outcome (the
    run keeps going for OTHER chunks, unlike quota which stops) but logged DISTINCTLY
    at error level with an 'operator action required' framing, so it surfaces as an
    action-required anomaly instead of blending into retryable noise."""
    import logging

    from embrapa_dashboard.comtrade.client import ComtradeTruncationError

    def truncate(*_a, **_k):
        raise ComtradeTruncationError("truncated at 100000 rows for reporters=['276']")

    with (
        patch.object(pipeline, "process_chunk", side_effect=truncate),
        caplog.at_level(logging.ERROR),
    ):
        outcome = pipeline._run_one_chunk(
            settings,
            2022,
            ["276"],
            "2022/276",
            storage_client=None,
            bq_client=None,
            table_fqn="p.d.t",
            from_raw=False,
            force=False,
        )

    assert outcome.status == "failed"  # NOT re-raised (run continues), unlike quota
    assert "permanent truncation" in outcome.detail
    assert any("PERMANENTLY truncated" in r.getMessage() for r in caplog.records)


# ── scope widening: a settled year must re-fetch when a produto was ADDED ──────


def _settings_with_codes(codes: str):
    from tests.test_serving import _isolated_settings

    return _isolated_settings(gcp_project_id="p", comtrade_cmd_codes=codes)


def test_codes_added_since_detects_only_additions():
    """Only ADDED codes trigger a re-fetch. Removing or reordering leaves the archived
    superset usable (Silver filters), so re-fetching for that would burn the keyed daily
    quota for nothing."""
    from embrapa_dashboard.comtrade import pipeline as p

    s = _settings_with_codes("0803:banana,140110:bambu,200591:brotos")
    # Archived under the OLD scope → the two bamboo codes are new.
    assert p._codes_added_since({"cmd_scope": "0803"}, s) == {"140110", "200591"}
    # Same set, different order → nothing added.
    assert p._codes_added_since({"cmd_scope": "200591,0803,140110"}, s) == set()
    # Archived under a WIDER scope (a code was removed) → nothing to fetch.
    assert p._codes_added_since({"cmd_scope": "0803,140110,200591,4403"}, s) == set()


def test_codes_added_since_is_silent_without_recorded_scope():
    """No cmd_scope on the object (pre-provenance) → we cannot tell what it covered, and
    guessing 'refetch' would re-bill the entire archive on a hunch."""
    from embrapa_dashboard.comtrade import pipeline as p

    s = _settings_with_codes("0803:banana,140110:bambu")
    assert p._codes_added_since({}, s) == set()
    assert p._codes_added_since({"cmd_scope": ""}, s) == set()
    assert p._codes_added_since(None, s) == set()


def test_sync_raw_still_skips_settled_year_when_scope_is_unchanged(settings) -> None:
    """The steady state must stay cheap: same scope → the settled year still resume-skips,
    so a routine monthly run does not re-bill the keyed quota for the whole archive."""
    stored = {"source": "un-comtrade", "cmd_scope": "0801,44"}
    with (
        patch.object(pipeline, "raw_provenance", return_value=stored),
        patch.object(client, "fetch_chunk_adaptive") as fetch,
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2020, ["76"], storage_client=MagicMock())
    assert changed is False
    fetch.assert_not_called()
    land.assert_not_called()


def test_sync_raw_refetches_settled_year_when_a_code_was_added(settings) -> None:
    """A produto added AFTER the archive was built must backfill its history.

    The archived object only holds the codes requested at fetch time, so without this the
    new produto would appear only from the recent-refetch window on — a silent history
    truncation the researcher cannot see. This is the COMTRADE counterpart of COMEX's
    product-filter fingerprint (bamboo, 2026-08)."""
    stored = {"source": "un-comtrade", "cmd_scope": "0801"}  # archived BEFORE '44' existed
    with (
        patch.object(pipeline, "raw_provenance", return_value=stored),
        patch.object(client, "fetch_chunk_adaptive", return_value=_bronze_df()) as fetch,
        patch.object(pipeline, "land_raw") as land,
    ):
        changed = pipeline.sync_raw(settings, 2020, ["76"], storage_client=MagicMock())
    assert changed is True
    fetch.assert_called_once()
    land.assert_called_once()


def test_settled_year_scope_refetch_logs_only_the_true_reason(settings, caplog) -> None:
    """One decision, ONE reason — and the right one.

    The scope check first landed as a fall-through, so a settled year re-fetched for a
    widened scope ALSO logged "recent year — re-fetching", which is plainly false for year
    2000. An operator reading that log would misdiagnose why the quota was spent."""
    import logging

    stored = {"source": "un-comtrade", "cmd_scope": "0801"}
    with (
        patch.object(pipeline, "raw_provenance", return_value=stored),
        patch.object(client, "fetch_chunk_adaptive", return_value=_bronze_df()),
        patch.object(pipeline, "land_raw"),
        caplog.at_level(logging.INFO, logger="embrapa_dashboard.comtrade.pipeline"),
    ):
        pipeline.sync_raw(settings, 2020, ["76"], storage_client=MagicMock())

    text = caplog.text
    assert "code(s) were added" in text
    assert "recent year" not in text
