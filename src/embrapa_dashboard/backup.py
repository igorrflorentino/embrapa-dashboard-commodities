"""Manual snapshot of Gold tables to GCS for cold-storage / academic conformance.

Triggered via ``embrapa backup-gold`` or ``make backup-gold`` — the latter is
also what ``make dbt-build-prod-with-backup`` chains after a prod dbt build.
Each backup lands at:

    gs://${GCS_BUCKET}/backups/run=<UTC-timestamp>/<table>/<table>-*.parquet

GCS lifecycle rules scoped to the ``backups/`` prefix transition objects to
Nearline at 30d and Coldline at 90d, then DELETE at 365d (see
``gcp/storage.py``) — old snapshots referencing dropped schemas aren't
restorable anyway. ``embrapa doctor`` raises when no snapshot exists and warns
when the latest is older than ``BACKUP_STALENESS_DAYS``.

A snapshot is only *complete* once the ``_SUCCESS`` manifest lands at the end
of the run prefix — a crash mid-run leaves a partial ``run=<ts>/`` without it,
and ``doctor._check_backup_freshness`` skips marker-less runs so a half-backup
can never satisfy the freshness check.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from embrapa_dashboard.config import Settings
from embrapa_dashboard.gcp.clients import resolve_clients
from embrapa_dashboard.gcp.storage import ensure_bucket

logger = logging.getLogger(__name__)

BACKUP_PREFIX = "backups"

# Completeness marker written as the LAST object of a snapshot (Hadoop-style
# _SUCCESS convention). Its JSON body records the table inventory so a restore
# can verify nothing is missing. Doctor requires it — see _check_backup_freshness.
SUCCESS_MARKER = "_SUCCESS"

# Wall-clock ceiling for blocking on one Gold→GCS extract job. Generous (Gold
# tables can be large) but bounded so a wedged export can't hang the backup
# step indefinitely; the job keeps running server-side past this.
EXTRACT_TIMEOUT_S: float = 1800.0


def _gold_tables(settings: Settings, bq_client: bigquery.Client) -> list[str]:
    """List the Gold tables to snapshot, derived by introspecting the dataset.

    Replaces the old hardcoded list — it silenced a real bug when
    commit a078a24 removed 3 of the 4 Gold dbt models without anyone updating
    the backup. The truth now comes from BigQuery at runtime.

    Filters:
    - ``settings.backup_gold_prefix`` (default ``"gold_"``) excludes ad-hoc /
      temp tables the operator may have created for exploration.
    - ``table_type == "TABLE"`` excludes views (there are no Gold views today, but
      the guard avoids a surprise when someone adds one).
    """
    dataset_ref = f"{settings.gcp_project_id}.{settings.bq_gold_dataset}"
    prefix = settings.backup_gold_prefix
    return sorted(
        f"{dataset_ref}.{t.table_id}"
        for t in bq_client.list_tables(dataset_ref)
        if t.table_id.startswith(prefix) and t.table_type == "TABLE"
    )


# Sub-prefix for the curation snapshot inside a run. Keeps the Gold layout
# (``run=<id>/<table>/``) byte-identical to every snapshot taken before curation was
# covered, so any restore tooling written against it still works.
CURATION_DIR = "_curation"


def _curation_tables(settings: Settings, bq_client: bigquery.Client) -> list[str]:
    """The researcher-authored tables to snapshot, introspected like the Gold ones.

    THE reason this exists: Gold is DERIVABLE — losing it costs a `dbt build`, since every
    row traces back to Bronze. ``research_inputs`` is AUTHORED: the produto catalog, the
    agrupamentos registry, the industrialization classifications, the lifecycle log and the
    per-catalog editor allowlists. None of it can be recomputed from any source. It was the
    one dataset with no backup while the reproducible half had a daily-ish one — 1310 rows
    and ~220 KiB in prod on 2026-08-29, so the cost of covering it rounds to nothing.

    No prefix filter (unlike Gold): every table in this dataset is authored, and a filter
    is one more thing to keep in sync — the hardcoded Gold list already taught that lesson.
    Returns ``[]`` when the dataset is absent (a cold install or a dev .env), which the
    manifest records so an operator can tell "nothing to back up" from "not covered".
    """
    dataset_ref = f"{settings.gcp_project_id}.{settings.bq_research_inputs_dataset}"
    try:
        return sorted(
            f"{dataset_ref}.{t.table_id}"
            for t in bq_client.list_tables(dataset_ref)
            if t.table_type == "TABLE"
        )
    except NotFound:
        logger.warning(
            "Curation dataset %s not found — snapshot will cover Gold only.", dataset_ref
        )
        return []


def run(settings: Settings) -> tuple[str, list[str]]:
    """Extract every Gold table to GCS Parquet. Returns (run_id, list of GCS URIs).

    Writes the ``_SUCCESS`` manifest only after every extract finished, so a
    failed/interrupted run leaves no completeness marker behind.

    Raises ``RuntimeError`` if the Gold dataset has no matching tables (typical
    when the user runs ``backup-gold`` before any ``make dbt-build-prod``).
    """
    bq_client, storage_client = resolve_clients(settings)
    ensure_bucket(
        storage_client,
        settings.gcs_bucket,
        settings.bq_location,
        raw_prefix=settings.gcs_raw_prefix,
    )

    table_fqns = _gold_tables(settings, bq_client)
    if not table_fqns:
        raise RuntimeError("No Gold tables found to back up. Run `make dbt-build-prod` first.")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    uris: list[str] = []

    curation_fqns = _curation_tables(settings, bq_client)

    for table_fqn in table_fqns + curation_fqns:
        table_name = table_fqn.split(".")[-1]
        sub = f"{CURATION_DIR}/" if table_fqn in curation_fqns else ""
        # Wildcard suffix is required so BigQuery can shard the export when
        # the table grows past a single-file limit (~1 GB Parquet).
        destination_uri = (
            f"gs://{settings.gcs_bucket}/{BACKUP_PREFIX}/run={run_id}/"
            f"{sub}{table_name}/{table_name}-*.parquet"
        )
        job_config = bigquery.ExtractJobConfig(
            destination_format=bigquery.DestinationFormat.PARQUET,
            # Snappy is the default for Parquet exports but stating it makes
            # the resulting object size predictable.
            compression="SNAPPY",
        )
        logger.info("Backing up %s → %s", table_fqn, destination_uri)
        extract_job = bq_client.extract_table(
            table_fqn,
            destination_uri,
            location=settings.bq_location,
            job_config=job_config,
        )
        extract_job.result(timeout=EXTRACT_TIMEOUT_S)
        uris.append(destination_uri)

    # Every extract succeeded — seal the snapshot. Anything that raised above
    # leaves the run prefix WITHOUT this marker, which is how doctor tells a
    # partial/failed snapshot apart from a complete one.
    manifest = {
        "run_id": run_id,
        # The SOURCE dataset — dev (dbt_dev_gold) and prod (gold) hold identically-named
        # tables, so without this a dev-pointed .env snapshot is indistinguishable from a
        # prod one and would satisfy doctor freshness AND the purge-orphan backup gate for a
        # PROD purge (whose only rollback point would then be 7-day-TTL dev data). Doctor and
        # the purge gate cross-check this against the dataset being operated on.
        "dataset": settings.bq_gold_dataset,
        "table_count": len(table_fqns),
        "tables": [fqn.split(".")[-1] for fqn in table_fqns],
        # Declared explicitly so an operator (and doctor) can tell a snapshot that COVERS
        # curation from one taken before it did — an absent key means "not covered", which
        # is a different thing from an empty list ("covered, nothing there").
        "curation_dataset": settings.bq_research_inputs_dataset,
        "curation_table_count": len(curation_fqns),
        "curation_tables": [fqn.split(".")[-1] for fqn in curation_fqns],
        "completed_at": datetime.now(UTC).isoformat(),
    }
    marker_name = f"{BACKUP_PREFIX}/run={run_id}/{SUCCESS_MARKER}"
    storage_client.bucket(settings.gcs_bucket).blob(marker_name).upload_from_string(
        json.dumps(manifest), content_type="application/json"
    )
    logger.info("Backup complete — wrote gs://%s/%s", settings.gcs_bucket, marker_name)

    return run_id, uris
