"""Tests for the embrapa doctor health-check probes."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import responses
from google.cloud.exceptions import NotFound

from embrapa_dashboard import doctor
from embrapa_dashboard.config import Settings


@pytest.fixture
def settings(settings_factory) -> Settings:
    # _env_file=None (via settings_factory) keeps these probes from reading the
    # developer's repo-root .env, so default-dependent assertions stay hermetic.
    return settings_factory(
        gcp_project_id="test-project",
        gcs_bucket="test-bucket",
        bcb_inflation_series="433:IPCA",
        bcb_currency_series="3694:USD",
    )


def test_check_env_passes_with_valid_settings(settings: Settings) -> None:
    result = doctor._check_env(settings)
    assert result.ok is True
    assert "433" in result.detail
    # The check vouches for ALL source mappings, not just PEVS/BCB.
    assert "pam=" in result.detail
    assert "comex=" in result.detail
    assert "comtrade=" in result.detail


def test_check_env_fails_on_bad_format(settings: Settings) -> None:
    # No colon — malformed pair.
    settings.bcb_inflation_series = "433_no_colon"
    result = doctor._check_env(settings)
    assert result.ok is False


def test_check_env_fails_on_bad_comex_ncm_codes(settings: Settings) -> None:
    """A malformed COMEX_NCM_CODES must fail '.env parsed' — not explode mid-ingest."""
    settings.comex_ncm_codes = "08012100_no_colon"
    result = doctor._check_env(settings)
    assert result.ok is False
    assert "08012100_no_colon" in result.detail


def test_check_env_fails_on_invalid_comtrade_flows(settings: Settings) -> None:
    settings.comtrade_flows = "X,Z"
    result = doctor._check_env(settings)
    assert result.ok is False
    assert "Z" in result.detail


def test_check_env_fails_on_empty_pam_codes(settings: Settings) -> None:
    settings.pam_product_codes = " , "
    result = doctor._check_env(settings)
    assert result.ok is False
    assert "PAM_PRODUCT_CODES" in result.detail


def test_check_inflation_pivot_codes_pass(settings: Settings) -> None:
    """All three Gold pivot codes present in BCB_INFLATION_SERIES → ok."""
    settings.bcb_inflation_series = "433:IPCA,189:IGPM,190:IGPDI"
    result = doctor._check_inflation_pivot_codes(settings)
    assert result.ok is True


def test_check_inflation_pivot_codes_fails_when_code_not_ingested(settings: Settings) -> None:
    """A pivot code absent from BCB_INFLATION_SERIES → fail.

    The fixture ingests only 433:IPCA, but the IGP-M (189) and IGP-DI (190)
    pivot codes default on, so they are missing from the ingested series —
    exactly the drift that would silently NULL the Gold val_real_igpm/igpdi_*
    columns.
    """
    result = doctor._check_inflation_pivot_codes(settings)
    assert result.ok is False
    assert "189" in result.detail or "190" in result.detail


def test_check_currency_series_codes_pass(settings: Settings) -> None:
    """The canonical daily PTAX codes (USD=1, EUR=21619) → ok."""
    settings.bcb_currency_series = "1:USD,21619:EUR"
    result = doctor._check_currency_series_codes(settings)
    assert result.ok is True
    assert "USD=1" in result.detail


def test_check_currency_series_codes_fails_on_stale_wrong_codes(settings: Settings) -> None:
    """The historical wrong USD code (3694, annual) → fail with a clear reason.

    The fixture defaults bcb_currency_series to the bad '3694:USD' — exactly the
    stale-.env drift that would silently regress the Gold val_yearfx_* columns."""
    result = doctor._check_currency_series_codes(settings)  # fixture = "3694:USD"
    assert result.ok is False
    assert "3694" in result.detail


def test_check_adc_returns_project_when_ok(settings: Settings) -> None:
    with patch("embrapa_dashboard.doctor.google.auth.default") as auth:
        auth.return_value = (MagicMock(), "test-project")
        result = doctor._check_adc(settings)
    assert result.ok is True
    assert "test-project" in result.detail


def test_check_adc_fails_with_recovery_hint(settings: Settings) -> None:
    with patch("embrapa_dashboard.doctor.google.auth.default") as auth:
        auth.side_effect = Exception("no credentials")
        result = doctor._check_adc(settings)
    assert result.ok is False
    assert "gcloud auth" in result.detail


def test_check_bq_calls_service_account(settings: Settings) -> None:
    with patch("embrapa_dashboard.doctor.bigquery.Client") as bq_cls:
        bq_cls.return_value.get_service_account_email.return_value = "sa@x.iam"
        result = doctor._check_bq(settings)
    assert result.ok is True
    assert "sa@x.iam" in result.detail


def test_check_gcs_reports_existing_bucket(settings: Settings) -> None:
    with patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls:
        gcs_cls.return_value.list_blobs.return_value = iter([object()])
        result = doctor._check_gcs(settings)
    assert result.ok is True
    assert "exists" in result.detail


def test_check_gcs_passes_when_bucket_missing(settings: Settings) -> None:
    """Missing bucket is OK — it'll be lazily created on first ingest."""
    from google.cloud.exceptions import NotFound

    with patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls:
        gcs_cls.return_value.list_blobs.side_effect = NotFound("bucket not found")
        result = doctor._check_gcs(settings)
    assert result.ok is True
    assert "will be created" in result.detail


@responses.activate
def test_check_ibge_reachable(settings: Settings) -> None:
    responses.add(
        responses.GET,
        re.compile(r"https://servicodados\.ibge\.gov\.br/api/v3/agregados/289/metadados.*"),
        json={"classificacoes": []},
        status=200,
    )
    result = doctor._check_ibge(settings)
    assert result.ok is True


@responses.activate
def test_check_ibge_handles_5xx(settings: Settings) -> None:
    responses.add(
        responses.GET,
        re.compile(r"https://servicodados\.ibge\.gov\.br/api/v3/agregados/289/metadados.*"),
        status=503,
    )
    result = doctor._check_ibge(settings)
    assert result.ok is False


@responses.activate
def test_check_bcb_reachable(settings: Settings) -> None:
    responses.add(
        responses.GET,
        re.compile(r"https://api\.bcb\.gov\.br/dados/serie/bcdata\.sgs\.433/dados.*"),
        json=[{"data": "01/01/2024", "valor": "0.16"}],
        status=200,
    )
    result = doctor._check_bcb(settings)
    assert result.ok is True
    assert "sgs.433" in result.detail


def _comex_url(settings: Settings, year: int) -> str:
    return f"{settings.comex_csv_base_url.rstrip('/')}/EXP_{year}.csv"


@responses.activate
def test_check_comex_ok_when_end_year_file_published(settings: Settings) -> None:
    settings.comex_end_year = 2026
    responses.add(responses.HEAD, _comex_url(settings, 2026), status=200)
    result = doctor._check_comex(settings)
    assert result.ok is True
    assert "EXP_2026.csv 200 OK" in result.detail


@responses.activate
def test_check_comex_treats_current_year_404_as_healthy(settings: Settings) -> None:
    """Early in the year MDIC hasn't published EXP_<end_year>.csv yet.

    The ingest pipeline classifies that 404 as an expected skip, so doctor
    must not exit 1 for it — it falls back to probing the previous year.
    """
    settings.comex_end_year = 2026
    responses.add(responses.HEAD, _comex_url(settings, 2026), status=404)
    responses.add(responses.HEAD, _comex_url(settings, 2025), status=200)
    result = doctor._check_comex(settings)
    assert result.ok is True
    assert "EXP_2025.csv 200 OK" in result.detail
    assert "not published yet" in result.detail


@responses.activate
def test_check_comex_fails_when_previous_year_also_unreachable(settings: Settings) -> None:
    """404 on BOTH years is a real problem (wrong base URL, host down), not
    the expected not-yet-published window."""
    settings.comex_end_year = 2026
    responses.add(responses.HEAD, _comex_url(settings, 2026), status=404)
    responses.add(responses.HEAD, _comex_url(settings, 2025), status=404)
    result = doctor._check_comex(settings)
    assert result.ok is False


@responses.activate
def test_check_comex_fails_on_5xx_without_fallback(settings: Settings) -> None:
    """Only the expected 404 triggers the previous-year fallback — a 5xx is a
    hard failure straight away."""
    settings.comex_end_year = 2026
    responses.add(responses.HEAD, _comex_url(settings, 2026), status=503)
    result = doctor._check_comex(settings)
    assert result.ok is False
    assert len(responses.calls) == 1


def test_check_bronze_tables_distinguishes_present_vs_missing(settings: Settings) -> None:
    with patch("embrapa_dashboard.doctor.bigquery.Client") as bq_cls:
        client = bq_cls.return_value
        # First table found, the rest missing. The count comes from the REGISTRY, not a
        # hand-kept literal: this test broke when the silviculture Bronze target was added
        # (2026-08-29) for no reason of its own, and the next source would have broken it
        # again. What it is about is present-vs-missing, not how many targets exist.
        client.get_table.side_effect = [MagicMock()] + [
            NotFound("nope") for _ in doctor.BRONZE_TARGETS[1:]
        ]
        result = doctor._check_bronze_tables(settings)
    assert result.ok is True  # informational only
    assert "missing" in result.detail


def test_check_serving_marts_all_present_and_populated(settings: Settings) -> None:
    with patch("embrapa_dashboard.doctor.bigquery.Client") as bq_cls:
        bq_cls.return_value.get_table.return_value = MagicMock(num_rows=100)
        result = doctor._check_serving_marts(settings)
    assert result.ok is True
    assert "all present" in result.detail


def test_check_serving_marts_reports_missing(settings: Settings) -> None:
    with patch("embrapa_dashboard.doctor.bigquery.Client") as bq_cls:
        # First seven marts present; gold_source_metadata (the 8th target) missing.
        bq_cls.return_value.get_table.side_effect = [
            MagicMock(num_rows=10),
            MagicMock(num_rows=10),
            MagicMock(num_rows=10),
            MagicMock(num_rows=10),
            MagicMock(num_rows=10),
            MagicMock(num_rows=10),
            MagicMock(num_rows=10),
            NotFound("nope"),
        ]
        result = doctor._check_serving_marts(settings)
    assert result.ok is True  # informational, never fails doctor on a fresh project
    assert "missing" in result.detail
    assert "dbt-build-prod" in result.detail


def test_check_serving_marts_flags_empty_mart(settings: Settings) -> None:
    with patch("embrapa_dashboard.doctor.bigquery.Client") as bq_cls:
        # serving_pevs_annual is empty (0 rows); the view (last) reports
        # num_rows=0 too — but only the materialized mart may be flagged.
        bq_cls.return_value.get_table.side_effect = [
            MagicMock(num_rows=0, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=0, table_type="VIEW"),
        ]
        result = doctor._check_serving_marts(settings)
    assert result.ok is True
    assert "empty=['serving_pevs_annual']" in result.detail


def test_check_serving_marts_view_with_zero_num_rows_is_not_empty(settings: Settings) -> None:
    """The BigQuery API returns numRows=0 for VIEWs (verified against the live
    API) — gold_source_metadata must not be flagged 'empty' on every run."""
    with patch("embrapa_dashboard.doctor.bigquery.Client") as bq_cls:
        bq_cls.return_value.get_table.side_effect = [
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=10, table_type="TABLE"),
            MagicMock(num_rows=0, table_type="VIEW"),  # gold_source_metadata
        ]
        result = doctor._check_serving_marts(settings)
    assert result.ok is True
    assert "empty" not in result.detail
    assert "all present + populated" in result.detail


def _list_blobs_mock(prefixes: list[str]) -> MagicMock:
    """Build a list_blobs() return-value that exposes ``prefixes`` after iteration.

    The real GCS HTTPIterator only fills ``prefixes`` once the page iterator
    has been drained, so the production code does ``list(blobs)`` before
    reading ``.prefixes``. MagicMock's default ``__iter__`` already returns
    an empty iterator, so we only need to set the prefixes attribute.
    """
    iterator = MagicMock()
    iterator.prefixes = prefixes
    return iterator


def _mark_complete(gcs_cls: MagicMock, complete_markers: set[str] | None = None) -> None:
    """Configure which `_SUCCESS` marker blobs exist on the mocked GCS client.

    ``None`` means every snapshot is complete (every marker exists); otherwise
    only the given blob names exist — modelling crashed half-backups.
    """

    def _blob(name: str) -> MagicMock:
        blob = MagicMock()
        blob.exists.return_value = complete_markers is None or name in complete_markers
        return blob

    gcs_cls.return_value.bucket.return_value.blob.side_effect = _blob


def test_check_backup_freshness_reports_fresh_snapshot(settings: Settings) -> None:
    """Recent snapshot (well within threshold): ok=True, no warn marker."""
    now = datetime.now(UTC)
    recent = (now - timedelta(days=2)).strftime("%Y%m%dT%H%M%SZ")
    with patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls:
        gcs_cls.return_value.list_blobs.return_value = _list_blobs_mock([f"backups/run={recent}/"])
        _mark_complete(gcs_cls)
        result = doctor._check_backup_freshness(settings)
    assert result.ok is True
    assert "⚠" not in result.detail
    assert "2d ago" in result.detail or "1d ago" in result.detail


def test_check_backup_freshness_warns_on_stale(settings: Settings) -> None:
    """Snapshot older than BACKUP_STALENESS_DAYS: ok=True but ⚠ in detail."""
    settings.backup_staleness_days = 14
    stale_ts = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y%m%dT%H%M%SZ")
    with patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls:
        gcs_cls.return_value.list_blobs.return_value = _list_blobs_mock(
            [f"backups/run={stale_ts}/"]
        )
        _mark_complete(gcs_cls)
        result = doctor._check_backup_freshness(settings)
    assert result.ok is True  # warn, not fail
    assert "⚠" in result.detail
    assert "stale" in result.detail


def test_check_backup_freshness_picks_latest_of_many(settings: Settings) -> None:
    """When multiple snapshots exist, freshness is measured from the most recent one."""
    now = datetime.now(UTC)
    old = (now - timedelta(days=400)).strftime("%Y%m%dT%H%M%SZ")
    middle = (now - timedelta(days=100)).strftime("%Y%m%dT%H%M%SZ")
    recent = (now - timedelta(days=3)).strftime("%Y%m%dT%H%M%SZ")
    with patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls:
        gcs_cls.return_value.list_blobs.return_value = _list_blobs_mock(
            [
                f"backups/run={old}/",
                f"backups/run={recent}/",
                f"backups/run={middle}/",
            ]
        )
        _mark_complete(gcs_cls)
        result = doctor._check_backup_freshness(settings)
    assert result.ok is True
    assert "⚠" not in result.detail


def test_check_backup_freshness_skips_incomplete_snapshot(settings: Settings) -> None:
    """A crashed half-backup (run prefix without _SUCCESS) must not satisfy
    freshness — the newest COMPLETE snapshot counts instead."""
    now = datetime.now(UTC)
    complete_ts = (now - timedelta(days=3)).strftime("%Y%m%dT%H%M%SZ")
    partial_ts = (now - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
    with patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls:
        gcs_cls.return_value.list_blobs.return_value = _list_blobs_mock(
            [f"backups/run={complete_ts}/", f"backups/run={partial_ts}/"]
        )
        _mark_complete(gcs_cls, {f"backups/run={complete_ts}/_SUCCESS"})
        result = doctor._check_backup_freshness(settings)
    assert result.ok is True
    assert "3d ago" in result.detail  # measured from the complete one, not 1d
    assert "skipped 1 newer" in result.detail


def test_latest_complete_run_skips_snapshot_of_different_dataset(settings: Settings) -> None:
    """A COMPLETE snapshot whose manifest records a DIFFERENT dataset (e.g. a dev-pointed .env
    snapshotting dbt_dev_gold) must NOT satisfy a gate for settings.bq_gold_dataset — the newest
    matching-dataset run wins instead, and the mismatch counts as skipped."""
    import json as _json

    now = datetime.now(UTC)
    newer = (now - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
    older = (now - timedelta(days=3)).strftime("%Y%m%dT%H%M%SZ")
    runs = [
        (datetime.strptime(newer, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC), f"backups/run={newer}/"),
        (datetime.strptime(older, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC), f"backups/run={older}/"),
    ]
    other = settings.bq_gold_dataset + "_other"  # guaranteed != the configured dataset

    def _blob(name: str) -> MagicMock:
        blob = MagicMock()
        blob.exists.return_value = True
        dataset = other if newer in name else settings.bq_gold_dataset
        blob.download_as_text.return_value = _json.dumps({"dataset": dataset})
        return blob

    client = MagicMock()
    client.bucket.return_value.blob.side_effect = _blob
    latest, skipped = doctor._latest_complete_run(client, settings, runs)
    assert latest == runs[1][0]  # the older run OF THE CONFIGURED dataset, not the newer dev one
    assert skipped == 1  # the newer, other-dataset snapshot was skipped


def test_check_backup_freshness_fails_when_only_incomplete_snapshots(settings: Settings) -> None:
    """Run prefixes exist but none carries the _SUCCESS marker → hard fail.

    This is exactly the partial/failed-backup scenario: the operator must not
    be told the cold-storage rollback path is intact."""
    fresh_ts = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
    with patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls:
        gcs_cls.return_value.list_blobs.return_value = _list_blobs_mock(
            [f"backups/run={fresh_ts}/"]
        )
        _mark_complete(gcs_cls, set())  # no marker anywhere
        result = doctor._check_backup_freshness(settings)
    assert result.ok is False
    assert "_SUCCESS" in result.detail
    assert "dbt-build-prod-with-backup" in result.detail


def test_check_backup_freshness_fails_when_no_snapshot(settings: Settings) -> None:
    """Empty backups/ prefix is a hard fail with a recovery hint."""
    with patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls:
        gcs_cls.return_value.list_blobs.return_value = _list_blobs_mock([])
        result = doctor._check_backup_freshness(settings)
    assert result.ok is False
    assert "dbt-build-prod-with-backup" in result.detail


def test_check_backup_freshness_ignores_malformed_prefixes(settings: Settings) -> None:
    """Stray prefixes that don't match the run=<ts>/ pattern are skipped.

    A human poking around with `gsutil cp` could land arbitrary objects under
    `backups/`; the probe must not crash and must not let them count as a
    snapshot.
    """
    with patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls:
        gcs_cls.return_value.list_blobs.return_value = _list_blobs_mock(
            ["backups/ad-hoc-thing/", "backups/run=not-a-timestamp/"]
        )
        result = doctor._check_backup_freshness(settings)
    assert result.ok is False  # no valid snapshot → fail like the empty case
    assert "no snapshot" in result.detail


def test_run_all_executes_every_probe(settings: Settings) -> None:
    """run_all should call each probe exactly once in CHECKS order."""
    with (
        patch("embrapa_dashboard.doctor.google.auth.default") as auth,
        patch("embrapa_dashboard.doctor.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.doctor.storage.Client") as gcs_cls,
        patch("embrapa_dashboard.doctor.requests.get") as get,
        patch("embrapa_dashboard.doctor.requests.head") as head,
    ):
        auth.return_value = (MagicMock(), "p")
        bq_cls.return_value.get_service_account_email.return_value = "sa@x"
        bq_cls.return_value.get_table.return_value = MagicMock()
        gcs_cls.return_value.bucket.return_value.exists.return_value = True
        # list_blobs is consumed twice: once by _check_gcs (truthy iterator)
        # and once by _check_backup_freshness (prefixes attribute).
        gcs_cls.return_value.list_blobs.return_value = _list_blobs_mock([])
        get.return_value.status_code = 200
        get.return_value.raise_for_status.return_value = None
        # _check_comex probes with HEAD (avoids pulling the 100+ MB body).
        head.return_value.status_code = 200
        head.return_value.raise_for_status.return_value = None

        results = doctor.run_all(settings)

    assert len(results) == len(doctor.CHECKS)
    assert [r.name for r in results] == [
        ".env parsed",
        "Inflation pivot codes",
        "Currency series codes",
        "PAM variable codes",
        "IBGE PEVS variable codes",
        "IBGE silvicultura variable codes",
        "ADC credentials",
        "BigQuery reachable",
        "GCS bucket",
        "IBGE SIDRA reachable",
        "IBGE SIDRA silvicultura reachable",
        "IBGE PAM reachable",
        "IBGE PPM reachable",
        "BCB SGS reachable",
        "COMEX reachable",
        "COMTRADE reachable",
        "Bronze tables",
        "Serving marts",
        "Catalog↔env product codes",
        "Curation referential integrity",
        "Catalog orphan lifecycle",
        "Catalog → Gold arrival",
        "Gold backup freshness",
        "Source data freshness",
        "Ingest heartbeat",
    ]


# cli.INGESTS source name → the doctor SOURCE_CHECKS key that covers it. The two
# registries are independent lists keyed by DIFFERENT names: the CLI uses
# 'ibge-pam'/'bcb-inflation'/'bcb-currency'; doctor groups them as 'pam'/'bcb'
# (one probe per upstream API, not per ingest leg). This map IS the documented
# contract (docs/adding_a_data_source.md, CLAUDE.md) — the test below fails the
# moment a new IngestSpec is added without wiring up its doctor coverage.
_INGEST_TO_DOCTOR_CHECK = {
    "ibge": "ibge",
    # The other half of the SAME survey (SIDRA t291) — its own ingest and its own
    # SIDRA-reachability probe, one banco.
    "ibge-silvicultura": "silvicultura",
    "ibge-pam": "pam",
    "ibge-ppm": "ppm",
    "bcb-inflation": "bcb",
    "bcb-currency": "bcb",
    "comex": "comex",
    "comtrade": "comtrade",
}


def test_every_ingest_source_is_covered_by_a_doctor_check() -> None:
    """Registry-drift guard. Adding a source means updating cli.INGESTS AND
    doctor.SOURCE_CHECKS/BRONZE_TARGETS (per docs/adding_a_data_source.md), but the
    lists don't reference each other, so a missed doctor entry is silent today. This
    pins the three registries together."""
    from embrapa_dashboard import cli

    ingest_names = {spec.name for spec in cli.INGESTS}
    doctor_keys = {name for name, _ in doctor.SOURCE_CHECKS}

    # The alias map covers exactly the registered ingest sources (fails if a new
    # IngestSpec lands without being mapped here).
    assert ingest_names == set(_INGEST_TO_DOCTOR_CHECK), (
        "cli.INGESTS drifted from the registry-drift map; "
        f"symmetric diff: {ingest_names ^ set(_INGEST_TO_DOCTOR_CHECK)}"
    )

    # Every mapped doctor key actually exists as a SOURCE_CHECK …
    missing = {k for k in _INGEST_TO_DOCTOR_CHECK.values() if k not in doctor_keys}
    assert not missing, f"ingest sources map to non-existent doctor checks: {missing}"

    # … and no SOURCE_CHECK is an orphan (unreachable from any ingest source).
    orphans = doctor_keys - set(_INGEST_TO_DOCTOR_CHECK.values())
    assert not orphans, f"doctor SOURCE_CHECKS has keys no ingest source maps to: {orphans}"


def test_pam_variable_codes_parity_passes_on_defaults(settings: Settings) -> None:
    """The 5 dbt PAM variable roles (8331/216/214/112/215) are all in the default
    PAM_VARIABLE_CODES → the parity check passes."""
    result = doctor._check_pam_variable_codes(settings)
    assert result.ok is True
    assert "5" in result.detail


def test_pam_variable_codes_parity_fails_when_a_dbt_code_is_dropped(settings_factory) -> None:
    """Dropping a code the dbt model needs (here 215 valor) must fail the parity
    check — that column would silently come out empty in Gold."""
    s = settings_factory(pam_variable_codes="8331,216,214,112")  # no 215 (valor)
    result = doctor._check_pam_variable_codes(s)
    assert result.ok is False
    assert "215" in result.detail


def test_ibge_variable_codes_parity_passes_on_defaults(settings: Settings) -> None:
    """The 2 PEVS variable codes (144 quantidade, 145 valor) match the defaults →
    the parity check passes (the PEVS analogue of the PAM check)."""
    result = doctor._check_ibge_variable_codes(settings)
    assert result.ok is True
    assert "144" in result.detail and "145" in result.detail


def test_ibge_variable_codes_parity_fails_on_typo(settings_factory) -> None:
    """A mistyped PEVS quantity code (144→143) must fail parity — silver_ibge_pevs would
    filter to a non-existent code and the quantity Gold column would come out empty."""
    s = settings_factory(ibge_variable_quantity_code="143")
    result = doctor._check_ibge_variable_codes(s)
    assert result.ok is False
    assert "144" in result.detail  # the required 'quantidade' code, now missing


def _small_codes(settings_factory):
    return settings_factory(
        ibge_product_codes="3405",
        pam_product_codes="40124",
        ppm_herd_product_codes="2670",
        ppm_animal_product_codes="2682",
    )


def test_catalog_parity_empty_uses_env(monkeypatch, settings_factory) -> None:
    """An empty/absent catalog → the check reports env fallback, no drift, never fails."""
    from embrapa_dashboard.ibge import catalog_resolver

    monkeypatch.setattr(catalog_resolver, "read_catalog_codes", lambda *a, **k: [])
    r = doctor._check_catalog_resolver_parity(_small_codes(settings_factory))
    assert r.ok is True
    assert "vazio" in r.detail and "DRIFT" not in r.detail


def test_catalog_parity_matches_env(monkeypatch, settings_factory) -> None:
    """Catalog codes equal to the .env codes per banco → OK, no drift."""
    from embrapa_dashboard.ibge import catalog_resolver

    codes = {
        ("pevs", None): ["3405"],
        ("pam", None): ["40124"],
        ("ppm", "3939"): ["2670"],
        ("ppm", "74"): ["2682"],
    }
    monkeypatch.setattr(
        catalog_resolver,
        "read_catalog_codes",
        lambda s, banco, *, sidra_tabela=None, bq_client=None: codes[(banco, sidra_tabela)],
    )
    r = doctor._check_catalog_resolver_parity(_small_codes(settings_factory))
    assert r.ok is True
    assert "OK" in r.detail and "DRIFT" not in r.detail


def test_catalog_parity_reports_drift_without_failing(monkeypatch, settings_factory) -> None:
    """An extra catalog code is reported as DRIFT but the check still passes (intended
    change, not an error) — an operator sees what the next run would pull."""
    from embrapa_dashboard.ibge import catalog_resolver

    codes = {
        ("pevs", None): ["3405", "9999"],
        ("pam", None): ["40124"],
        ("ppm", "3939"): ["2670"],
        ("ppm", "74"): ["2682"],
    }
    monkeypatch.setattr(
        catalog_resolver,
        "read_catalog_codes",
        lambda s, banco, *, sidra_tabela=None, bq_client=None: codes[(banco, sidra_tabela)],
    )
    r = doctor._check_catalog_resolver_parity(_small_codes(settings_factory))
    assert r.ok is True  # never fails on intended drift
    assert "DRIFT" in r.detail and "9999" in r.detail


def test_bronze_targets_reference_real_settings_fields(settings: Settings) -> None:
    """Typo guard for the third registry: every (dataset_attr, table_attr) in
    doctor.BRONZE_TARGETS must name a real Settings field, else _check_bronze_tables
    would raise AttributeError at runtime instead of probing the table."""
    for dataset_attr, table_attr in doctor.BRONZE_TARGETS:
        assert hasattr(settings, dataset_attr), f"BRONZE_TARGETS: no Settings.{dataset_attr}"
        assert hasattr(settings, table_attr), f"BRONZE_TARGETS: no Settings.{table_attr}"


class _N:
    def __init__(self, n: int) -> None:
        self.n = n


def test_check_orphan_lifecycle_flags_unmarked(monkeypatch, settings: Settings) -> None:
    """A soft-warn when more catalog removals exist than lifecycle-marked ones (the
    mark-orphans step probably didn't run). Advisory (ok=True)."""
    client = MagicMock()
    client.query.return_value.result.side_effect = [[_N(3)], [_N(1)]]
    monkeypatch.setattr("embrapa_dashboard.gcp.clients.resolve_bq_client", lambda s: client)

    r = doctor._check_orphan_lifecycle(settings)

    assert r.ok is True and "unmarked" in r.detail


def test_check_orphan_lifecycle_all_marked(monkeypatch, settings: Settings) -> None:
    """When every removal is already marked, the check reports the clean state."""
    client = MagicMock()
    client.query.return_value.result.side_effect = [[_N(2)], [_N(2)]]
    monkeypatch.setattr("embrapa_dashboard.gcp.clients.resolve_bq_client", lambda s: client)

    r = doctor._check_orphan_lifecycle(settings)

    assert r.ok is True and "all marked" in r.detail


def test_check_orphan_lifecycle_error_degrades_to_skipped(monkeypatch, settings: Settings) -> None:
    """Any fault (tables absent / perms) degrades to an advisory 'skipped', never failing."""

    def _boom(s):
        raise RuntimeError("no dataset")

    monkeypatch.setattr("embrapa_dashboard.gcp.clients.resolve_bq_client", _boom)

    r = doctor._check_orphan_lifecycle(settings)

    assert r.ok is True and "skipped" in r.detail


class _Row:
    def __init__(self, banco: str, codigo_produto: str) -> None:
        self.banco = banco
        self.codigo_produto = codigo_produto


def test_check_catalog_data_arrival_clean(monkeypatch, settings: Settings) -> None:
    """No cataloged produto missing from Gold → the clean state."""
    client = MagicMock()
    client.query.return_value.result.return_value = []
    monkeypatch.setattr("embrapa_dashboard.gcp.clients.resolve_bq_client", lambda s: client)

    r = doctor._check_catalog_data_arrival(settings)

    assert r.ok is True and "every cataloged produto has data" in r.detail


def test_check_catalog_data_arrival_reports_missing_grouped_by_banco(
    monkeypatch, settings: Settings
) -> None:
    """The source-agnostic backstop for "registered, but the pipeline never fetched it".

    Each banco family solves scope growth differently (IBGE full-window backfill, COMEX
    filter fingerprint, COMTRADE cmd_scope re-fetch) — and COMTRADE had NO mechanism until
    2026-08, so a produto registered against it sat empty with nothing reporting the fact.
    This check does not care HOW a banco ingests, only whether what a researcher registered
    actually shows up, so a FUTURE banco with a missing or broken mechanism is covered too.
    """
    client = MagicMock()
    client.query.return_value.result.return_value = [
        _Row("comtrade", "140110"),
        _Row("comtrade", "200591"),
    ]
    monkeypatch.setattr("embrapa_dashboard.gcp.clients.resolve_bq_client", lambda s: client)

    r = doctor._check_catalog_data_arrival(settings)

    # Advisory, never a failure: a produto registered minutes ago is legitimately empty.
    assert r.ok is True
    assert "2 cataloged produto(s) with NO Gold data" in r.detail
    assert "comtrade: 140110,200591" in r.detail


def test_check_catalog_data_arrival_degrades_on_error(monkeypatch, settings: Settings) -> None:
    """A missing table / permission fault degrades to 'skipped' — doctor must not blow up
    over an advisory probe."""
    client = MagicMock()
    client.query.side_effect = RuntimeError("no such table")
    monkeypatch.setattr("embrapa_dashboard.gcp.clients.resolve_bq_client", lambda s: client)

    r = doctor._check_catalog_data_arrival(settings)

    assert r.ok is True and r.detail.startswith("skipped:")


# ── advisory fall-throughs that were never exercised (coverage-gate re-arm, 2026-08-20) ──
#
# `doctor` is a health REPORT: a probe that cannot answer must degrade to an advisory
# line, never crash the whole report or — worse — report a false green.


def test_check_ibge_variable_codes_degrades_when_the_config_read_faults(
    monkeypatch, settings: Settings
) -> None:
    """A malformed/unreadable variable-code config must surface as a FAILED check with
    the reason, not raise out of `doctor` and take every remaining probe with it."""

    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError("config exploded")

    r = doctor._check_ibge_variable_codes(_Boom())

    assert r.ok is False
    assert "config exploded" in r.detail


def test_check_catalog_resolver_parity_is_advisory_when_the_catalog_read_faults(
    monkeypatch, settings: Settings
) -> None:
    """This probe DIFFS the catalog against .env — informational only. If the catalog
    can't be read it reports `skipped` and stays ok=True: a curation-side fault must not
    make the pipeline's health look broken."""
    monkeypatch.setattr(
        "embrapa_dashboard.ibge.catalog_resolver.read_catalog_codes",
        MagicMock(side_effect=RuntimeError("research_inputs absent")),
    )

    r = doctor._check_catalog_resolver_parity(settings)

    assert r.ok is True
    assert "skipped" in r.detail


def test_check_catalog_resolver_parity_falls_back_to_env_when_the_catalog_is_empty(
    monkeypatch, settings: Settings
) -> None:
    """An empty catalog is the pre-adoption state, not drift: the probe says so per
    banco (`vazio→.env(n)`) instead of reporting every configured code as removed."""
    monkeypatch.setattr(
        "embrapa_dashboard.ibge.catalog_resolver.read_catalog_codes", MagicMock(return_value=[])
    )

    r = doctor._check_catalog_resolver_parity(settings)

    assert r.ok is True
    assert "vazio→.env(" in r.detail


# ── Source data freshness ────────────────────────────────────────────────────
# The check answers "is the newest reference period as new as the cadence implies?", NOT
# "did the scheduler run" — see the docstring. These pin the cadence-dependent floor,
# because that is the whole content of the check.
def _freshness_rows(*triples):
    return [SimpleNamespace(source=s, cadence=c, year_end=y) for s, c, y in triples]


def _patch_freshness(rows):
    """Stand in for the one BigQuery read the check makes."""
    client = MagicMock()
    client.query.return_value.result.return_value = rows
    return patch("embrapa_dashboard.doctor.bigquery.Client", return_value=client)


def test_source_freshness_all_current(settings: Settings) -> None:
    year = datetime.now(UTC).year
    settings.source_freshness_annual_slack_years = 2
    with _patch_freshness(
        _freshness_rows(("ibge_pevs", "annual", year - 2), ("mdic_comex", "monthly", year))
    ):
        result = doctor._check_source_data_freshness(settings)
    assert result.ok is True
    assert "⚠" not in result.detail
    assert "every source current" in result.detail


def test_source_freshness_warns_when_annual_source_falls_behind(settings: Settings) -> None:
    """One year past the slack window: the publication window came and went."""
    year = datetime.now(UTC).year
    settings.source_freshness_annual_slack_years = 2
    with _patch_freshness(
        _freshness_rows(("ibge_ppm", "annual", year - 3), ("ibge_pevs", "annual", year - 1))
    ):
        result = doctor._check_source_data_freshness(settings)
    assert result.ok is True  # warn, never fail — a lagging source is a signal to look
    assert "⚠" in result.detail
    assert "ibge_ppm" in result.detail
    assert "ibge_pevs" not in result.detail  # the healthy one is not named as overdue


def test_source_freshness_holds_monthly_sources_to_a_tighter_floor(settings: Settings) -> None:
    """A monthly source one whole year behind is late even where an annual one is fine."""
    year = datetime.now(UTC).year
    settings.source_freshness_annual_slack_years = 2
    with _patch_freshness(
        _freshness_rows(("mdic_comex", "monthly", year - 2), ("ibge_pam", "annual", year - 2))
    ):
        result = doctor._check_source_data_freshness(settings)
    assert "⚠" in result.detail
    assert "mdic_comex" in result.detail
    assert "ibge_pam" not in result.detail


def test_source_freshness_flags_a_missing_year_end(settings: Settings) -> None:
    with _patch_freshness(_freshness_rows(("sefaz_nf", "monthly", None))):
        result = doctor._check_source_data_freshness(settings)
    assert "⚠" in result.detail
    assert "no year_end" in result.detail


def test_source_freshness_handles_an_empty_metadata_table(settings: Settings) -> None:
    with _patch_freshness([]):
        result = doctor._check_source_data_freshness(settings)
    assert result.ok is True
    assert "empty" in result.detail


def test_source_freshness_reports_a_query_failure(settings: Settings) -> None:
    client = MagicMock()
    client.query.side_effect = RuntimeError("permission denied on gold_source_metadata")
    with patch("embrapa_dashboard.doctor.bigquery.Client", return_value=client):
        result = doctor._check_source_data_freshness(settings)
    assert result.ok is False
    assert "permission denied" in result.detail


# ─── silvicultura probes ──────────────────────────────────────────────────────
def test_silvicultura_variable_codes_check_passes_on_the_configured_pair(
    settings: Settings,
) -> None:
    assert doctor._check_silvicultura_variable_codes(settings).ok is True


def test_silvicultura_variable_codes_check_fails_when_one_is_mistyped(
    settings: Settings,
) -> None:
    """The failure this exists for: a typo drops that variable from Silver and empties
    half a Gold column with NO downstream error."""
    settings.silvicultura_variable_value_code = "1443"  # transposed
    result = doctor._check_silvicultura_variable_codes(settings)
    assert result.ok is False
    assert "143" in result.detail and "origem" in result.detail


def test_silvicultura_variable_codes_check_reports_an_unexpected_error() -> None:
    """A probe must never raise INTO run_all — one broken check would take down the whole
    report, which is the opposite of what a health command is for."""

    class Broken:
        @property
        def silvicultura_variable_quantity_code(self) -> str:
            raise RuntimeError("boom")

    result = doctor._check_silvicultura_variable_codes(Broken())  # type: ignore[arg-type]
    assert result.ok is False
    assert "boom" in result.detail


def test_silvicultura_sidra_probe_reports_reachability(settings: Settings) -> None:
    with patch("embrapa_dashboard.doctor.requests.get") as get:
        get.return_value.raise_for_status.return_value = None
        ok = doctor._check_silvicultura(settings)
        get.side_effect = RuntimeError("timeout")
        bad = doctor._check_silvicultura(settings)
    assert ok.ok is True and "t291" in ok.detail
    assert bad.ok is False


class _GrupoRow:
    def __init__(self, codigo_produto: str, banco: str, agrupamento_id: str) -> None:
        self.codigo_produto = codigo_produto
        self.banco = banco
        self.agrupamento_id = agrupamento_id


class _NivelRow:
    def __init__(self, source: str, code: str, industrialization_level: str) -> None:
        self.source = source
        self.code = code
        self.industrialization_level = industrialization_level


def _curation_client(monkeypatch, grupos: list, niveis: list, registrados: set[str]) -> MagicMock:
    """Wire both log queries + the agrupamentos registry the integrity check reads."""
    client = MagicMock()
    client.query.return_value.result.side_effect = [grupos, niveis]
    monkeypatch.setattr("embrapa_dashboard.gcp.clients.resolve_bq_client", lambda s: client)
    monkeypatch.setattr(
        "embrapa_dashboard.serving.agrupamentos._current_groups",
        lambda *a, **k: registrados,
    )
    monkeypatch.setattr(
        "embrapa_dashboard.serving.agrupamentos._group_log_ref", lambda cfg: "proj.ds.log"
    )
    return client


def test_curation_integrity_clean(monkeypatch, settings: Settings) -> None:
    """Every agrupamento registered and every level in scale → the clean state."""
    _curation_client(
        monkeypatch,
        grupos=[_GrupoRow("3405", "ibge_pevs", "madeira")],
        niveis=[_NivelRow("ibge_pevs", "3405", "commodity_pura")],
        registrados={"madeira"},
    )

    r = doctor._check_curation_referential_integrity(settings)

    assert r.ok is True and "every agrupamento_id registered" in r.detail


def test_curation_integrity_fails_on_unregistered_agrupamento(
    monkeypatch, settings: Settings
) -> None:
    """The 2026-08-29 defect: entries naming a group that was never created. The products
    vanish from every grouped view while the log stays self-consistent, so only a check
    that crosses the catalog WITH the registry can see it."""
    _curation_client(
        monkeypatch,
        grupos=[
            _GrupoRow("3405", "ibge_pevs", "madeira"),
            _GrupoRow("3406", "ibge_pevs", "lenha"),
        ],
        niveis=[],
        registrados={"madeira"},
    )

    r = doctor._check_curation_referential_integrity(settings)

    assert r.ok is False
    assert "1 catalog entr" in r.detail and "lenha" in r.detail
    assert "madeira" not in r.detail  # the registered one is not accused


def test_curation_integrity_fails_on_level_outside_scale(monkeypatch, settings: Settings) -> None:
    """The writer is open-vocabulary, so a typo'd level is stored and then matches no
    filter AND no 'sem classificação' — invisible either way."""
    _curation_client(
        monkeypatch,
        grupos=[],
        niveis=[
            _NivelRow("ibge_pevs", "3405", "commodity_pura"),
            _NivelRow("ibge_pevs", "3406", "commodity_purra"),
        ],
        registrados=set(),
    )

    r = doctor._check_curation_referential_integrity(settings)

    assert r.ok is False
    assert "1 classification" in r.detail and "commodity_purra" in r.detail


def test_curation_integrity_level_query_excludes_the_explicit_clear(
    monkeypatch, settings: Settings
) -> None:
    """An empty level is the un-classify CLEAR (latest-wins), not an invalid value. It is
    excluded in SQL, so assert on the emitted query — a fake client cannot filter."""
    client = _curation_client(monkeypatch, grupos=[], niveis=[], registrados=set())

    doctor._check_curation_referential_integrity(settings)

    nivel_sql = client.query.call_args_list[1].args[0]
    assert "industrialization_level != ''" in nivel_sql


def test_curation_integrity_error_degrades_to_skipped(monkeypatch, settings: Settings) -> None:
    """A cold install has no logs to read and must not report a red integrity check."""

    def _boom(s):
        raise RuntimeError("no dataset")

    monkeypatch.setattr("embrapa_dashboard.gcp.clients.resolve_bq_client", _boom)

    r = doctor._check_curation_referential_integrity(settings)

    assert r.ok is True and "skipped" in r.detail
