"""One row per ingest run, written whether or not the run had anything to ingest.

The blind spot this closes: the Cloud Monitoring policy alerts on a **failed** Cloud Run
execution, so a scheduled run that completes green and writes NOTHING is indistinguishable
from "the source has not published yet". For the annual sources that quiet state is normal
~11 months a year, so a trigger that silently stopped firing could sit unnoticed until
someone happened to look.

Bronze cannot answer it either: the delta pipelines deliberately write nothing when there
is no new data, so "no new rows" is the healthy case as often as it is the broken one.

The heartbeat separates the two by recording the RUN, not its output:

    no row in the expected window  →  the trigger did not fire      (cadence broken)
    row with outcome='ok'          →  it ran; whether data arrived is a separate
                                      question, answered by doctor's
                                      "Source data freshness" check
    row with outcome='failed'      →  it ran and broke (the alert also fires)

Writing here must NEVER break an ingest: every failure is swallowed with a warning. A
monitor that can take down the thing it monitors is worse than no monitor.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from embrapa_dashboard.config import Settings, get_settings
from embrapa_dashboard.gcp.bigquery import ensure_dataset
from embrapa_dashboard.serving import sql as sqlbuild
from embrapa_dashboard.serving.research_inputs import _bq_client

logger = logging.getLogger(__name__)

HEARTBEAT_SCHEMA = [
    bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("run_ts", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("outcome", "STRING", mode="REQUIRED"),  # ok | failed
    bigquery.SchemaField("duration_s", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("detail", "STRING", mode="NULLABLE"),
]


def table_fqn(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    return sqlbuild.table_ref(cfg, "bq_research_inputs_dataset", cfg.bq_heartbeat_table)


def ensure_heartbeat_table(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Create the heartbeat table if missing; return its FQN. Idempotent.

    Append-only and tiny (one row per ingest run — a few thousand a year), so it needs no
    partitioning or clustering.
    """
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    fqn = table_fqn(cfg)
    ensure_dataset(bq, f"{cfg.gcp_project_id}.{cfg.bq_research_inputs_dataset}", cfg.bq_location)
    bq.create_table(bigquery.Table(fqn, schema=HEARTBEAT_SCHEMA), exists_ok=True)
    return fqn


def record(
    source: str,
    outcome: str,
    *,
    duration_s: float | None = None,
    detail: str | None = None,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> bool:
    """Append one heartbeat. Returns True when written; NEVER raises.

    Swallowing the error is deliberate — see the module docstring. The caller is an
    ingest that has already done its real work; failing it because a monitoring row could
    not be written would turn an observability aid into an outage.
    """
    try:
        cfg = settings or get_settings()
        bq = client or _bq_client(cfg)
        fqn = table_fqn(cfg)
        row = {
            "source": source,
            "run_ts": datetime.now(UTC).isoformat(),
            "outcome": outcome,
            "duration_s": duration_s,
            "detail": (detail or "")[:500] or None,
        }
        try:
            errors = bq.insert_rows_json(fqn, [row])
        except NotFound:
            # First run after this shipped (or someone dropped the table). Create it and
            # retry once. Deliberately NOT done on every write: the table exists on all but
            # the first heartbeat, and paying a get_dataset + create_table round-trip per
            # ingest to re-learn that would be a monitor charging rent.
            ensure_heartbeat_table(cfg, bq)
            errors = bq.insert_rows_json(fqn, [row])
        if errors:
            logger.warning("Heartbeat insert reported errors for %s: %s", source, errors)
            return False
        return True
    except Exception as exc:  # pragma: no cover - defensive; exercised by a unit test
        logger.warning("Could not record ingest heartbeat for %s: %s", source, exc)
        return False
