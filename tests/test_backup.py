"""Tests for the Gold cold-storage backup pipeline (GCP fully mocked)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound

from embrapa_dashboard import backup
from embrapa_dashboard.config import Settings


@pytest.fixture
def settings(settings_factory) -> Settings:
    # _env_file=None (via settings_factory) keeps bq_gold_dataset etc. from being
    # overridden by the developer's repo-root .env, so the extract URIs stay fixed.
    return settings_factory(
        gcp_project_id="test-project",
        gcs_bucket="test-bucket",
        bq_gold_dataset="gold",
    )


def _fake_table(table_id: str, table_type: str = "TABLE") -> MagicMock:
    """Stand-in for a `google.cloud.bigquery.table.TableListItem`."""
    t = MagicMock()
    t.table_id = table_id
    t.table_type = table_type
    return t


def _list_tables_por_dataset(gold: list, curadoria: list | None = None):
    """`list_tables` dispatching on the dataset argument.

    `backup.run` introspects TWO datasets since 2026-08-29 (Gold + research_inputs), so a
    single `return_value` would hand the curation half the Gold list and double every
    extract — which is exactly how these tests first failed."""

    def _dispatch(dataset_ref, *a, **k):
        if dataset_ref.endswith(".gold") or dataset_ref.endswith("_gold"):
            return gold
        if curadoria is None:
            raise NotFound("dataset ausente")
        return curadoria

    return _dispatch


def test_run_extracts_every_gold_table(settings: Settings) -> None:
    """Happy path: introspect Gold → 1 extract per `gold_*` table → URIs returned.

    Today only `gold_pevs_production` exists in the dbt project; this test
    exercises the multi-table path with a synthetic list so the contract
    survives when new Gold lineages (per-source: `gold_comex_*`,
    `gold_nfe_*`) are added later.
    """
    with (
        patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch("embrapa_dashboard.backup.ensure_bucket"),
    ):
        client = bq_cls.return_value
        client.list_tables.side_effect = _list_tables_por_dataset(
            [
                _fake_table("gold_pevs_production"),
                _fake_table("gold_comex_flows"),
                _fake_table("gold_nfe_flows"),
            ],
            [],
        )
        client.extract_table.return_value.result.return_value = None

        run_id, uris = backup.run(settings)

    assert client.extract_table.call_count == 3
    assert len(uris) == 3
    # All URIs land under the same run_id prefix.
    assert all(f"backups/run={run_id}/" in uri for uri in uris)
    # Each URI ends in a wildcard so BQ can shard the export.
    assert all(uri.endswith("-*.parquet") for uri in uris)


def test_run_filters_by_prefix_and_table_type(settings: Settings) -> None:
    """Introspection skips: (a) tables outside the prefix, (b) views.

    Replaces the old `test_run_skips_missing_tables` — the new flow can't see
    missing tables (`list_tables` only returns extant), so we test the filter
    that protects against backing up unrelated artefacts.
    """
    with (
        patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch("embrapa_dashboard.backup.ensure_bucket"),
    ):
        client = bq_cls.return_value
        client.list_tables.side_effect = _list_tables_por_dataset(
            [
                _fake_table("gold_pevs_production"),  # backed up
                _fake_table("gold_explore_temp"),  # backed up (matches prefix)
                _fake_table("staging_temp"),  # filtered: wrong prefix
                _fake_table("gold_legacy_view", table_type="VIEW"),  # filtered: VIEW
            ],
            [],
        )
        client.extract_table.return_value.result.return_value = None

        _, uris = backup.run(settings)

    assert client.extract_table.call_count == 2
    assert len(uris) == 2
    # Filtered names never reach extract_table.
    extracted_names = [call.args[0] for call in client.extract_table.call_args_list]
    assert all("staging_temp" not in n for n in extracted_names)
    assert all("legacy_view" not in n for n in extracted_names)


def test_run_raises_when_dataset_is_empty(settings: Settings) -> None:
    """Gold dataset has no matching tables → RuntimeError pointing at dbt-build-prod."""
    with (
        patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch("embrapa_dashboard.backup.ensure_bucket"),
    ):
        client = bq_cls.return_value
        client.list_tables.side_effect = _list_tables_por_dataset([], [])

        with pytest.raises(RuntimeError, match="dbt-build-prod"):
            backup.run(settings)


def test_run_writes_success_marker_after_all_extracts(settings: Settings) -> None:
    """A complete snapshot ends with the `_SUCCESS` manifest under the run prefix.

    Doctor's freshness check requires this marker — without it a snapshot does
    not count as complete (see test_run_skips_marker_when_extract_fails).
    """
    with (
        patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.gcp.clients.storage.Client") as gcs_cls,
        patch("embrapa_dashboard.backup.ensure_bucket"),
    ):
        client = bq_cls.return_value
        client.list_tables.side_effect = _list_tables_por_dataset(
            [
                _fake_table("gold_pevs_production"),
                _fake_table("gold_comex_flows"),
            ],
            [],
        )
        client.extract_table.return_value.result.return_value = None

        run_id, _ = backup.run(settings)

        bucket = gcs_cls.return_value.bucket
        bucket.assert_called_once_with("test-bucket")
        blob = bucket.return_value.blob
        blob.assert_called_once_with(f"backups/run={run_id}/_SUCCESS")
        upload = blob.return_value.upload_from_string
        upload.assert_called_once()
        manifest = json.loads(upload.call_args.args[0])

    assert manifest["run_id"] == run_id
    assert manifest["table_count"] == 2
    assert manifest["tables"] == ["gold_comex_flows", "gold_pevs_production"]
    assert "completed_at" in manifest


def test_run_skips_marker_when_extract_fails(settings: Settings) -> None:
    """A failed extract must abort BEFORE the `_SUCCESS` marker is written.

    The marker is what lets doctor distinguish a complete snapshot from a
    crashed half-backup — writing it on failure would defeat the check.
    """
    with (
        patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.gcp.clients.storage.Client") as gcs_cls,
        patch("embrapa_dashboard.backup.ensure_bucket"),
    ):
        client = bq_cls.return_value
        client.list_tables.side_effect = _list_tables_por_dataset(
            [
                _fake_table("gold_pevs_production"),
                _fake_table("gold_comex_flows"),
            ],
            [],
        )
        # First extract OK, second blows up mid-run.
        ok_job = MagicMock()
        boom_job = MagicMock()
        boom_job.result.side_effect = RuntimeError("extract failed")
        client.extract_table.side_effect = [ok_job, boom_job]

        with pytest.raises(RuntimeError, match="extract failed"):
            backup.run(settings)

        gcs_cls.return_value.bucket.return_value.blob.assert_not_called()


def test_run_uses_parquet_snappy_format(settings: Settings) -> None:
    """ExtractJobConfig must be Parquet + Snappy so backups are restorable."""
    with (
        patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch("embrapa_dashboard.backup.ensure_bucket"),
    ):
        client = bq_cls.return_value
        client.list_tables.side_effect = _list_tables_por_dataset(
            [_fake_table("gold_pevs_production")], []
        )
        client.extract_table.return_value.result.return_value = None

        backup.run(settings)

    call_kwargs = client.extract_table.call_args.kwargs
    cfg = call_kwargs["job_config"]
    assert cfg.destination_format == "PARQUET"
    assert cfg.compression == "SNAPPY"


# ── curation coverage: the one dataset nothing else can rebuild ───────────────
def test_run_also_snapshots_the_curation_dataset(settings: Settings) -> None:
    """Gold is DERIVABLE (Bronze → dbt → Gold); research_inputs is AUTHORED. It was the
    only dataset with no backup while the reproducible half had a near-daily one."""
    with (
        patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.gcp.clients.storage.Client"),
        patch("embrapa_dashboard.backup.ensure_bucket"),
    ):
        client = bq_cls.return_value
        client.list_tables.side_effect = _list_tables_por_dataset(
            [_fake_table("gold_pevs_production")],
            [_fake_table("produto_catalog_log"), _fake_table("agrupamento_log")],
        )
        client.extract_table.return_value.result.return_value = None

        run_id, uris = backup.run(settings)

    assert len(uris) == 3, "1 tabela Gold + 2 de curadoria"
    curadoria = [u for u in uris if f"/{backup.CURATION_DIR}/" in u]
    assert len(curadoria) == 2
    # The Gold layout stays byte-identical to every pre-coverage snapshot.
    ouro = [u for u in uris if f"/{backup.CURATION_DIR}/" not in u]
    assert ouro == [
        f"gs://test-bucket/backups/run={run_id}/gold_pevs_production/gold_pevs_production-*.parquet"
    ]


def test_curation_tables_are_not_prefix_filtered(settings: Settings) -> None:
    """Unlike Gold, no prefix filter: every table in research_inputs is authored, and a
    filter is one more thing to keep in sync (the hardcoded Gold list taught that)."""
    with patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls:
        client = bq_cls.return_value
        client.list_tables.return_value = [
            _fake_table("produto_catalog_log"),
            _fake_table("curators"),
            _fake_table("uma_view", table_type="VIEW"),
        ]
        out = backup._curation_tables(settings, client)

    assert [t.split(".")[-1] for t in out] == ["curators", "produto_catalog_log"]


def test_missing_curation_dataset_degrades_to_gold_only(settings: Settings) -> None:
    """A cold install / dev .env has no research_inputs. That must not fail the backup —
    the manifest records the zero so an operator can tell it apart from coverage."""
    with (
        patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.gcp.clients.storage.Client") as gcs_cls,
        patch("embrapa_dashboard.backup.ensure_bucket"),
    ):
        client = bq_cls.return_value
        client.list_tables.side_effect = _list_tables_por_dataset(
            [_fake_table("gold_pevs_production")], None
        )
        client.extract_table.return_value.result.return_value = None

        _, uris = backup.run(settings)
        corpo = gcs_cls.return_value.bucket.return_value.blob.return_value
        manifesto = json.loads(corpo.upload_from_string.call_args.args[0])

    assert len(uris) == 1
    assert manifesto["curation_table_count"] == 0


def test_manifest_declares_curation_coverage(settings: Settings) -> None:
    """The KEY is the signal doctor reads: absent = snapshot predates coverage, 0 = covered
    but empty. Conflating them would call an unprotected snapshot protected."""
    with (
        patch("embrapa_dashboard.gcp.clients.bigquery.Client") as bq_cls,
        patch("embrapa_dashboard.gcp.clients.storage.Client") as gcs_cls,
        patch("embrapa_dashboard.backup.ensure_bucket"),
    ):
        client = bq_cls.return_value
        client.list_tables.side_effect = _list_tables_por_dataset(
            [_fake_table("gold_pevs_production")], [_fake_table("produto_catalog_log")]
        )
        client.extract_table.return_value.result.return_value = None

        backup.run(settings)
        corpo = gcs_cls.return_value.bucket.return_value.blob.return_value
        manifesto = json.loads(corpo.upload_from_string.call_args.args[0])

    assert manifesto["curation_table_count"] == 1
    assert manifesto["curation_tables"] == ["produto_catalog_log"]
    assert manifesto["curation_dataset"] == settings.bq_research_inputs_dataset
