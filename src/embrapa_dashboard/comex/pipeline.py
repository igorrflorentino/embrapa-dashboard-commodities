"""Two-phase Bronze pipeline for MDIC Comex Stat foreign-trade flows.

Phase 1 (``sync_raw``) downloads the verbatim per-(flow, year) CSV, converts it
to Parquet and archives it in the GCS raw zone — but only when the source file
actually changed, decided by comparing the live HTTP ``ETag``/``Last-Modified``
against the archived object's stored provenance. Phase 2 (``bronze_one``) reads
the raw Parquet back, filters to the configured NCMs/chapters, and loads
BigQuery Bronze. See ``PLANS/raw_zone_architecture.md``.

Why two phases: re-filtering (new products/rules) or re-deriving Bronze re-runs
Phase 2 only — reading from GCS, never re-downloading. And the ETag freshness
check catches revisions to *any* year, not just the current one (the old delta
skipped past years permanently once loaded).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import tempfile
from collections.abc import Callable
from datetime import UTC

import pandas as pd
from google.cloud import bigquery, storage

from embrapa_dashboard.comex import client
from embrapa_dashboard.config import Settings
from embrapa_dashboard.core import (
    ChunkOutcome,
    SourceTransientError,
    download_raw,
    land_raw_file,
    mark_raw_bronze_loaded,
    raw_bronze_loaded,
    raw_bronze_loaded_filter,
    raw_provenance,
    run_chunks,
)
from embrapa_dashboard.gcp.bigquery import ensure_dataset, load_dataframe
from embrapa_dashboard.gcp.clients import resolve_clients

logger = logging.getLogger(__name__)

# Segment under raw/comex/<dataset>/ — one raw object per (flow, year).
RAW_DATASET = "comex_flows"

# Bronze layout: flow + the raw source columns (all STRING) + the typed
# ingestion timestamp. Order here is the on-table column order.
BRONZE_STRING_COLUMNS: list[str] = ["flow", *client.SOURCE_COLUMNS]

# Clustering mirrors the columns Silver dedupes / filters on most. BigQuery
# caps clustering at 4 columns, so the full natural key
# (flow, CO_ANO, CO_MES, CO_NCM, CO_PAIS, SG_UF_NCM) is trimmed to the four
# most selective for typical product×year×country queries.
CLUSTERING_FIELDS: list[str] = ["flow", "CO_NCM", "CO_ANO", "CO_PAIS"]


def _basename(flow: str, year: int) -> str:
    """Raw object basename for a (flow, year) — e.g. ``EXP_2023``."""
    return f"{client.FILE_PREFIX[flow]}_{year}"


def bronze_schema() -> list[bigquery.SchemaField]:
    """``flow`` + raw STRING columns + typed ``ingestion_timestamp``.

    All source columns are NULLABLE: export rows legitimately lack
    ``VL_FRETE``/``VL_SEGURO``, and a raw feed may carry blank fields elsewhere.
    """
    schema = [bigquery.SchemaField("flow", "STRING", mode="REQUIRED")]
    schema += [
        bigquery.SchemaField(col, "STRING", mode="NULLABLE") for col in client.SOURCE_COLUMNS
    ]
    schema.append(bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP", mode="REQUIRED"))
    return schema


def all_chunks(settings: Settings) -> list[tuple[str, int]]:
    """Every configured ``(flow, year)``, in flow-then-year order.

    Two-phase ingestion enumerates the full window every run — the per-file
    freshness check (Phase 1) makes re-visiting cheap (a HEAD), so there is no
    Bronze-presence delta to compute up front.
    """
    start, end = settings.comex_start_year, settings.comex_end_year
    return [(flow, year) for flow in settings.comex_flows_list for year in range(start, end + 1)]


def _raw_is_current(
    stored: dict[str, str] | None, head: dict[str, str], *, label: str = ""
) -> bool:
    """True when the archived raw matches the live source by the ETag (the only
    STRONG validator). Missing archive or no ETag on both sides → not current
    (re-extract to be safe).

    Neither Content-Length NOR Last-Modified is a confirming identifier:
    Content-Length is too weak (a same-byte value correction is misread as
    unchanged), and Last-Modified is a WEAK validator too (1-second granularity,
    RFC 7232) — a corrected file republished within the same wall-clock second, or
    without bumping Last-Modified, would be misread as unchanged. So only the ETag
    may short-circuit to "current"; when it is absent on either side we fall
    through to the re-download branch below even if Last-Modified/Content-Length
    match.

    When an archive *does* exist but no ETag is present on both sides, the function
    returns ``False`` (forcing a full re-download) and emits a WARNING: that silent
    degradation — a server dropping the ETag — would otherwise re-download every
    file every run with no visible cause. The cost is at most a redundant download
    when the server drops ETag, which is the safe direction. ``label`` (e.g.
    ``"EXP_2026"``) tags the warning.
    """
    if not stored:
        return False
    # ONLY the ETag confirms "current". Content-Length (same-byte correction) and
    # Last-Modified (1-second granularity, same-second republish) are both too weak
    # to trust, so a present-but-ETag-less archive is re-downloaded, not trusted.
    etag_live, etag_archived = head.get("source_etag"), stored.get("source_etag")
    if etag_live is not None and etag_archived is not None:
        return etag_live == etag_archived
    logger.warning(
        "Comex %s: raw is archived but no ETag is present on both sides — forcing a "
        "full re-download (Last-Modified and Content-Length are too weak to trust: a "
        "same-second republish or same-byte correction would be misread as unchanged). "
        "The source may have stopped sending the ETag; freshness short-circuiting is "
        "degraded until it resumes.",
        label or "(unknown)",
    )
    return False


def sync_raw(
    settings: Settings,
    flow: str,
    year: int,
    *,
    storage_client: storage.Client,
    force: bool = False,
) -> bool:
    """Phase 1: archive the verbatim ``(flow, year)`` CSV as raw Parquet if changed.

    Returns ``True`` when it (re)extracted, ``False`` when the archived raw was
    already current (download skipped). ``force`` ignores the freshness check.
    """
    basename = _basename(flow, year)
    head = client.head_source(settings.comex_csv_base_url, flow, year)
    if not force:
        stored = raw_provenance(
            storage_client,
            settings=settings,
            source="comex",
            dataset=RAW_DATASET,
            basename=basename,
        )
        if _raw_is_current(stored, head, label=basename):
            logger.info(
                "Comex %s %d: raw current (source unchanged), skipping download.", flow, year
            )
            return False

    fd, pq_path = tempfile.mkstemp(prefix=f"comex_raw_{basename}_", suffix=".parquet")
    os.close(fd)
    try:
        rows = client.extract_to_parquet(settings.comex_csv_base_url, flow, year, pq_path)
        land_raw_file(
            pq_path,
            settings=settings,
            storage_client=storage_client,
            source="comex",
            dataset=RAW_DATASET,
            basename=basename,
            provenance=head,
            rows=rows,
        )
    finally:
        with contextlib.suppress(OSError):
            os.unlink(pq_path)
    return True


def bronze_one(
    settings: Settings,
    flow: str,
    year: int,
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
    table_fqn: str,
) -> str:
    """Phase 2: filter the raw ``(flow, year)`` Parquet and load BigQuery Bronze.

    Returns the destination, or ``""`` when no configured product matched (no
    empty Bronze append).
    """
    basename = _basename(flow, year)
    raw_bytes = download_raw(
        storage_client, settings=settings, source="comex", dataset=RAW_DATASET, basename=basename
    )
    df = client.filter_products(
        raw_bytes,
        set(settings.comex_ncm_map),
        set(settings.comex_chapter_map),
        set(settings.comex_heading_map),
    )
    if df.empty:
        logger.info("Comex %s %d: no configured products in raw, skipping bronze.", flow, year)
        return ""

    # NaN (reindexed import-only columns on export, or blank source fields)
    # must land as SQL NULL, not the literal string "nan".
    df = df.astype(object).where(pd.notna(df), None)
    df.insert(0, "flow", flow)
    df["ingestion_timestamp"] = pd.Timestamp.now(tz=UTC)
    df = df[[*BRONZE_STRING_COLUMNS, "ingestion_timestamp"]]

    load_dataframe(
        bq_client,
        df,
        table_fqn,
        bronze_schema(),
        time_partitioning_field="ingestion_timestamp",
        clustering_fields=CLUSTERING_FIELDS,
    )
    return table_fqn


def has_raw(settings: Settings, flow: str, year: int, *, storage_client: storage.Client) -> bool:
    """Whether a raw object exists for ``(flow, year)`` (used by ``--from-raw``)."""
    return (
        raw_provenance(
            storage_client,
            settings=settings,
            source="comex",
            dataset=RAW_DATASET,
            basename=_basename(flow, year),
        )
        is not None
    )


def _product_filter_fingerprint(settings: Settings) -> str:
    """Stable hash of the configured COMEX product filter (NCM + chapter + heading codes).

    Phase 2 filters the archived raw to THIS set, so the bronze-loaded marker records which
    filter loaded a chunk. Without it, a historical raw whose ETag never changes stays marked
    "loaded" under the OLD filter and resume-skips Phase 2 forever — so a newly-added NCM/
    heading never backfills its history (only the current-year file, whose ETag churns, picks
    it up). Keying on the sorted code union means adding/removing a product changes the
    fingerprint, so ``needs_bronze`` re-runs Phase 2 (a cheap GCS read + in-memory re-filter,
    no source re-download; Silver dedups the re-append) and the new product lands across all
    years. Chapter/heading are prefix rules and NCM is exact — all three define the row set,
    so all three enter the fingerprint.
    """
    codes = sorted(
        set(settings.comex_ncm_map)
        | set(settings.comex_chapter_map)
        | set(settings.comex_heading_map)
    )
    return hashlib.sha256("\n".join(codes).encode()).hexdigest()[:16]


def needs_bronze(
    settings: Settings, flow: str, year: int, *, extracted: bool, storage_client: storage.Client
) -> bool:
    """Whether Phase 2 must run for ``(flow, year)`` after Phase 1.

    Always when Phase 1 (re)extracted. When the raw was unchanged, run Phase 2 if either
    (a) Bronze has not yet been loaded from it — a prior run archived the raw then aborted
    before the load — or (b) it was loaded under a DIFFERENT product filter than the one now
    configured (a new NCM/heading was added), so the archived raw must be re-filtered to
    backfill the new product across its history. A marker without a fingerprint (pre-this-
    feature, or a chunk not re-marked since) re-runs once to establish it — cheap (a GCS read
    + in-memory re-filter of the already-filtered raw, no source re-download) and Silver
    dedups the re-append. Steady state: same filter → fingerprint matches → skip.
    """
    if extracted:
        return True
    stored = raw_provenance(
        storage_client,
        settings=settings,
        source="comex",
        dataset=RAW_DATASET,
        basename=_basename(flow, year),
    )
    if stored is None:
        return False
    if not raw_bronze_loaded(stored):
        return True
    return raw_bronze_loaded_filter(stored) != _product_filter_fingerprint(settings)


def mark_bronze_loaded(
    settings: Settings, flow: str, year: int, *, storage_client: storage.Client
) -> None:
    """Stamp the ``(flow, year)`` raw object as loaded into Bronze (Phase 2 done), recording
    the product-filter fingerprint that loaded it so a later filter change re-runs Phase 2.

    **Semantics: at-least-once, not exactly-once.** The marker is written *after*
    the Bronze load, so a crash in the window between the load and this stamp
    leaves the partition loaded but unmarked; the next run sees ``needs_bronze``
    true and loads it again. Duplicate rows are expected and safe: Silver dedupes
    on the natural key by ``ingestion_timestamp desc``, so Gold stays correct.
    """
    mark_raw_bronze_loaded(
        storage_client,
        settings=settings,
        source="comex",
        dataset=RAW_DATASET,
        basename=_basename(flow, year),
        filter_fingerprint=_product_filter_fingerprint(settings),
    )


def ensure_destination(settings: Settings, bq_client: bigquery.Client) -> str:
    """Create the Bronze dataset if needed and return the table FQN."""
    dataset_id = f"{settings.gcp_project_id}.{settings.bq_bronze_comex_dataset}"
    ensure_dataset(bq_client, dataset_id, settings.bq_location)
    return f"{dataset_id}.{settings.bq_bronze_comex_flows_table}"


def _is_current_year_missing(exc: Exception, flow: str, year: int, settings: Settings) -> bool:
    """True when ``exc`` is a 404 for the latest configured year.

    The blind cron asks for the current calendar year before MDIC has published
    its file; the HEAD/GET then 404s. That is an *expected* not-yet-published
    state, not a pipeline failure — so the orchestrator skips it instead of
    aborting. Scoped to the latest year on purpose: a 404 on a historical year is
    anomalous and must surface as a real failure.
    """
    return year == settings.comex_end_year and "HTTP 404" in str(exc)


def process_chunk(
    settings: Settings,
    flow: str,
    year: int,
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
    table_fqn: str,
    from_raw: bool = False,
    force: bool = False,
) -> ChunkOutcome:
    """Run both phases for a single ``(flow, year)`` chunk and describe the result.

    The one per-chunk unit of work, shared by :func:`run` and the CLI so the
    orchestration logic lives in exactly one place. Resume/idempotency is
    preserved verbatim: ``needs_bronze`` still reloads an unchanged-but-unmarked
    raw (a prior run that aborted before Phase 2), and a *loaded* partition is
    still followed by :func:`mark_bronze_loaded` (at-least-once — see its
    docstring). A "" destination (no configured product matched) is intentionally
    left unmarked so a later product addition can backfill it.

    A current-year 404 (file not published yet) is reported as ``skipped``, not
    raised, so the blind cron never aborts on it.
    """
    chunk_id = _basename(flow, year)
    try:
        if from_raw:
            process = has_raw(settings, flow, year, storage_client=storage_client)
        else:
            extracted = sync_raw(settings, flow, year, storage_client=storage_client, force=force)
            # Skip Phase 2 only when the raw is unchanged AND already in Bronze;
            # an unchanged-but-never-loaded raw (aborted prior run) still loads.
            process = needs_bronze(
                settings, flow, year, extracted=extracted, storage_client=storage_client
            )
    except Exception as exc:
        if _is_current_year_missing(exc, flow, year, settings):
            logger.info("Comex %s %d: source file not published yet (404), skipping.", flow, year)
            return ChunkOutcome(chunk_id, "skipped", detail="not published yet (404)")
        raise

    if not process:
        return ChunkOutcome(chunk_id, "skipped", detail="source unchanged")

    destination = bronze_one(
        settings,
        flow,
        year,
        storage_client=storage_client,
        bq_client=bq_client,
        table_fqn=table_fqn,
    )
    if not destination:
        # ``bronze_one`` returns "" only when NO configured product matched the
        # raw — never a genuine empty year (the COMEX per-year file always has
        # rows). Do NOT stamp bronze_loaded here: stamping would freeze this raw
        # out of Phase 2 forever, so a later product addition could never backfill
        # it without a --from-raw rebuild. Leaving it unmarked re-runs Phase 2 each
        # nightly run (a cheap GCS read + in-memory filter, no source re-download),
        # which is exactly what lets a new product land on the next run.
        return ChunkOutcome(chunk_id, "skipped", detail="no configured products")
    mark_bronze_loaded(settings, flow, year, storage_client=storage_client)
    return ChunkOutcome(chunk_id, "loaded", destination=destination)


def run(
    settings: Settings,
    *,
    full: bool = False,
    from_raw: bool = False,
    storage_client: storage.Client | None = None,
    bq_client: bigquery.Client | None = None,
    on_chunk_start: Callable[[str], None] | None = None,
    on_chunk: Callable[[ChunkOutcome], None] | None = None,
) -> str:
    """Sync raw (Phase 1) then load Bronze (Phase 2). Returns the last destination, or ``""``.

    **Single source of truth for the ``(flow, year)`` loop**, with continue-on-
    failure baked in: one bad chunk (a 503, a non-current-year glitch) is recorded
    and the loop moves on instead of stranding the rest. Default: per (flow,
    year), re-download only if the source changed, and load Bronze for the ones
    that changed. ``full`` forces a re-download of every file. ``from_raw`` skips
    Phase 1 entirely and rebuilds Bronze from whatever raw is already archived.

    Hooks let the CLI present progress without re-deriving the loop:
    ``on_chunk_start(chunk_id)`` fires before each chunk; ``on_chunk(outcome)``
    fires after with its :class:`ChunkOutcome`. When **no** ``on_chunk`` consumer
    is given (e.g. ``ingest all`` calls ``run`` bare) and any chunk failed, the
    aggregated failures are raised as :class:`IngestPartialFailure` so a
    source-level handler can collect them; with a consumer, ``run`` returns
    normally and the caller decides the exit code from the outcomes it saw.
    """
    bq_client, storage_client = resolve_clients(settings, bq_client, storage_client)
    table_fqn = ensure_destination(settings, bq_client)

    def _chunks():
        # One (chunk_id, thunk) per (flow, year). The default-arg binds capture
        # this iteration's flow/year/chunk_id (avoiding the late-binding closure
        # trap) so run_chunks can call each thunk lazily.
        for flow, year in all_chunks(settings):
            chunk_id = _basename(flow, year)
            yield (
                chunk_id,
                lambda flow=flow, year=year, chunk_id=chunk_id: _run_one_chunk(
                    settings,
                    flow,
                    year,
                    chunk_id,
                    storage_client=storage_client,
                    bq_client=bq_client,
                    table_fqn=table_fqn,
                    from_raw=from_raw,
                    force=full,
                ),
            )

    return run_chunks(_chunks(), on_chunk_start=on_chunk_start, on_chunk=on_chunk)


def _run_one_chunk(
    settings: Settings,
    flow: str,
    year: int,
    chunk_id: str,
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
    table_fqn: str,
    from_raw: bool,
    force: bool,
) -> ChunkOutcome:
    """Process one (flow, year) chunk, turning a transient error into a ``failed``
    outcome so the loop can continue on to the next chunk."""
    try:
        return process_chunk(
            settings,
            flow,
            year,
            storage_client=storage_client,
            bq_client=bq_client,
            table_fqn=table_fqn,
            from_raw=from_raw,
            force=force,
        )
    except Exception as exc:
        return ChunkOutcome(
            chunk_id, "failed", detail=str(exc), transient=isinstance(exc, SourceTransientError)
        )
