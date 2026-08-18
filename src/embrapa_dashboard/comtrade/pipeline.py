"""Two-phase, chunked, resumable Bronze pipeline for UN Comtrade.

The keyed API is pre-filtered by query (our HS codes, reporter batch, flows,
years), so — like IBGE — the fetched frame *is* the Bronze content; Phase 1
archives it verbatim to the raw zone, Phase 2 stamps ingestion_timestamp and
loads BigQuery. See ``PLANS/comtrade_flows.md``.

Chunk = ``(year, reporter-batch)`` → one API call. Resumable: a SETTLED past-year
chunk whose raw already exists is skipped, but the recent window
(``comtrade_recent_refetch_years`` back from ``comtrade_end_year``) is always
re-fetched — UN Comtrade reporters file with a ~1-2y lag, so a recent year lands
incomplete and its later reporter submissions/revisions must keep flowing in. So a
daily-quota interruption just leaves the un-archived chunks for the next run — no
lost work, no duplication beyond what Silver dedupes.

A chunk's raw object is keyed by the *content* of its reporter batch (a stable
hash of the sorted reporter codes), not by a positional index — see ``_basename``.
This makes resume robust to the UN reference reordering or changing its reporter
set between runs: a basename always refers to exactly the reporters it archived.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC

import pandas as pd
from google.cloud import bigquery, storage

from embrapa_dashboard.comtrade import client
from embrapa_dashboard.comtrade.client import ComtradeQuotaError, ComtradeTruncationError
from embrapa_dashboard.config import Settings
from embrapa_dashboard.core import (
    ChunkOutcome,
    SourceTransientError,
    land_raw,
    mark_raw_bronze_loaded,
    raw_bronze_loaded,
    raw_provenance,
    read_raw,
    run_chunks,
)
from embrapa_dashboard.gcp.bigquery import ensure_dataset, load_dataframe
from embrapa_dashboard.gcp.clients import resolve_clients

logger = logging.getLogger(__name__)

RAW_DATASET = "comtrade_flows"

# Reporters per (year) chunk = one raw archive object. The keyed per-call cap is
# enforced separately by client.fetch_chunk_adaptive (which splits/recurses within
# a chunk), so this only controls raw-file / resume granularity, not call size.
REPORTER_BATCH_SIZE = 8

# Bronze layout: the curated API columns (all STRING) + the typed timestamp.
BRONZE_STRING_COLUMNS: list[str] = list(client.BRONZE_COLUMNS)
CLUSTERING_FIELDS: list[str] = ["reporterCode", "partnerCode", "cmdCode", "refYear"]


def bronze_schema() -> list[bigquery.SchemaField]:
    schema = [bigquery.SchemaField(col, "STRING", mode="NULLABLE") for col in client.BRONZE_COLUMNS]
    schema.append(bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP", mode="REQUIRED"))
    return schema


# Keyed on the scope tuple (not a bare list) so a different COMTRADE_CMD_CODES in
# the same process resolves independently instead of reusing the first run's HS6 list.
_CMD_CODES_CACHE: dict[tuple[str, ...], list[str]] = {}


def resolve_cmd_codes(settings: Settings) -> list[str]:
    """The HS6 leaf codes to request, expanded from the configured scope
    (``comtrade_cmd_codes``, e.g. ``0801``/``44``) via the public HS reference.
    Cached per scope so the HS reference is fetched once per scope, not per chunk."""
    scope = tuple(settings.comtrade_cmd_map)
    if scope not in _CMD_CODES_CACHE:
        _CMD_CODES_CACHE[scope] = client.list_hs6_codes(list(scope))
    return _CMD_CODES_CACHE[scope]


def resolve_reporters(settings: Settings) -> list[str]:
    """The reporter M49 codes to fetch, from ``comtrade_reporters``.

    ``"all"`` (case-insensitive) expands to every real reporter via the public
    Reporters reference; otherwise the comma-separated list is parsed verbatim.
    One definition shared by :func:`run` and the CLI so the two never drift on
    how ``all`` is interpreted.
    """
    if settings.comtrade_reporters.strip().lower() == "all":
        return client.list_reporters()
    return [c.strip() for c in settings.comtrade_reporters.split(",") if c.strip()]


def _reporter_batches(reporters: list[str]) -> list[list[str]]:
    """Fixed-size batches over a deterministically *sorted* reporter list, so the
    same reporter set yields the same batches regardless of the order the UN
    reference returned them in."""
    ordered = sorted(reporters)
    return [
        ordered[i : i + REPORTER_BATCH_SIZE] for i in range(0, len(ordered), REPORTER_BATCH_SIZE)
    ]


def _basename(year: int, reporters: list[str]) -> str:
    """Raw object basename for a (year, reporter-batch) chunk — e.g. ``2022_r1a2b3c4d5e``.

    The suffix is a stable content hash of the batch's *sorted* reporter codes,
    NOT a positional index: a basename therefore always refers to exactly the
    reporters it archived. If the UN reference reorders or changes its reporter
    set between runs, resume can never silently skip a chunk whose membership
    shifted under a reused index — it simply re-fetches the affected batch (and
    Silver dedupes the overlap).
    """
    digest = hashlib.sha1(",".join(sorted(reporters)).encode("utf-8")).hexdigest()
    return f"{year}_r{digest[:10]}"


def plan_chunks(settings: Settings, reporters: list[str]) -> list[tuple[int, list[str]]]:
    """Every ``(year, reporter_batch)`` to fetch, year-then-batch."""
    batches = _reporter_batches(reporters)
    return [
        (year, batch)
        for year in range(settings.comtrade_start_year, settings.comtrade_end_year + 1)
        for batch in batches
    ]


def sync_raw(
    settings: Settings,
    year: int,
    reporters: list[str],
    *,
    storage_client: storage.Client,
    force: bool = False,
) -> bool:
    """Phase 1: fetch one (year, reporter-batch) chunk and archive it. Returns
    ``True`` if (re)fetched (incl. a past-year empty sentinel landed), ``False``
    if skipped (a settled past-year chunk already raw) or the latest year came back empty.

    Every year within the recent window (``comtrade_recent_refetch_years`` back from
    ``comtrade_end_year``) is re-fetched regardless of whether its raw already holds
    data — reporters file with a lag, so a recent year is incomplete when first fetched
    and its later submissions/revisions must keep flowing in. Only years older than that
    window resume-skip. ``force`` re-fetches everything. A *past*-year empty fetch still
    lands an empty sentinel so an older chunk resume-skips instead of re-billing quota.
    """
    basename = _basename(year, reporters)
    is_latest = year == settings.comtrade_end_year
    if not force and not is_latest:
        stored = raw_provenance(
            storage_client,
            settings=settings,
            source="comtrade",
            dataset=RAW_DATASET,
            basename=basename,
        )
        if stored is not None:
            # A RECENT year is re-fetched every run REGARDLESS of whether its raw is empty or
            # already holds data: UN Comtrade reporters file with a ~1-2y lag, so a batch of 8
            # reporters fetched early lands NON-empty with only 1-2 of them present, and the
            # other reporters' later submissions (plus revisions of the early ones) would be
            # frozen out forever if a non-empty raw resume-skipped. Gating the re-fetch on the
            # empty sentinel was the bug: any single early reporter defeated it. Only years
            # OLDER than the recent window (settled — every reporter has long since filed) still
            # resume-skip. COMTRADE is excluded from `reconcile`, so this window is the ONLY
            # path that absorbs late reporters/revisions — it must not be defeated by partial data.
            recent = year >= settings.comtrade_end_year - settings.comtrade_recent_refetch_years
            if not recent:
                # A settled year still re-fetches when the SCOPE widened: the archived object
                # holds only the codes requested back then, so a newly-cataloged produto is
                # absent from it and would otherwise never backfill its history.
                added = _codes_added_since(stored, settings)
                if not added:
                    logger.info("Comtrade %s: raw exists (settled year), skipping.", basename)
                    return False
                logger.info(
                    "Comtrade %s: settled year, but %d code(s) were added since it was "
                    "fetched (%s) — re-fetching so their history is not truncated.",
                    basename,
                    len(added),
                    ",".join(sorted(added)),
                )
            else:
                # ELSE, not a fall-through: a settled year re-fetched for a WIDENED SCOPE
                # would otherwise also log "recent year", which is simply false for, say,
                # year 2000 — two reasons printed for one decision, one of them wrong.
                logger.info(
                    "Comtrade %s: recent year — re-fetching (late reporters / revisions may "
                    "have arrived since it was landed).",
                    basename,
                )

    cmd_codes = resolve_cmd_codes(settings)
    # Adaptive: a single dense reporter can exceed the per-call cap at HS6, so the
    # client splits/recurses (reporters→flows→cmd) and concatenates — the frame
    # below is the complete chunk regardless of how many sub-calls it took.
    df = client.fetch_chunk_adaptive(
        settings.comtrade_api_base_url,
        settings.comtrade_api_key,
        reporters=reporters,
        years=[year],
        cmd_codes=cmd_codes,
        flows=settings.comtrade_flows_list,
        customs_code=settings.comtrade_customs_code,
    )
    provenance = {
        "source": "un-comtrade",
        "year": str(year),
        "reporters": str(len(reporters)),
        # The exact codes (not just the count) so a content-keyed raw object
        # is auditable: you can confirm which reporters a basename covers.
        "reporter_codes": ",".join(sorted(reporters)),
        "cmd_scope": ",".join(settings.comtrade_cmd_map),
        "cmd_hs6_count": str(len(cmd_codes)),
        "flows": ",".join(settings.comtrade_flows_list),
        # "C00" for the totals-only pull, "" when unfiltered — auditable per object.
        "customs_code": settings.comtrade_customs_code or "all",
    }
    if df.empty:
        # A latest-year empty chunk is re-fetched every run anyway (revisions),
        # so landing nothing is correct there. A *past*-year empty chunk has no
        # other resume signal than the raw object's existence — without a sentinel
        # its absence reads as "never fetched", re-billing the daily quota on every
        # run. Land an empty SENTINEL (flagged ``empty``) so raw_provenance is
        # non-None next run and the chunk resume-skips. The frame already carries
        # the BRONZE_COLUMNS schema (fetch_chunk returns an empty typed frame), so
        # Phase 2 reads a valid 0-row parquet and skips the load.
        if is_latest:
            logger.info("Comtrade %s: no rows (latest year — re-fetched next run).", basename)
            return False
        logger.info("Comtrade %s: no rows — landing empty sentinel.", basename)
        land_raw(
            df.reindex(columns=BRONZE_STRING_COLUMNS),
            settings=settings,
            storage_client=storage_client,
            source="comtrade",
            dataset=RAW_DATASET,
            basename=basename,
            provenance={**provenance, "empty": "true"},
        )
        return True
    land_raw(
        df,
        settings=settings,
        storage_client=storage_client,
        source="comtrade",
        dataset=RAW_DATASET,
        basename=basename,
        provenance=provenance,
    )
    return True


def bronze_one(
    settings: Settings,
    year: int,
    reporters: list[str],
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
    table_fqn: str,
) -> str:
    """Phase 2: read the raw chunk, stamp ingestion_timestamp, load Bronze."""
    basename = _basename(year, reporters)
    df = read_raw(
        storage_client, settings=settings, source="comtrade", dataset=RAW_DATASET, basename=basename
    )
    if df.empty:
        return ""
    df = df.astype(object).where(pd.notna(df), None)
    df = df[BRONZE_STRING_COLUMNS]
    df["ingestion_timestamp"] = pd.Timestamp.now(tz=UTC)

    load_dataframe(
        bq_client,
        df,
        table_fqn,
        bronze_schema(),
        time_partitioning_field="ingestion_timestamp",
        clustering_fields=CLUSTERING_FIELDS,
    )
    return table_fqn


def has_raw(
    settings: Settings, year: int, reporters: list[str], *, storage_client: storage.Client
) -> bool:
    return (
        raw_provenance(
            storage_client,
            settings=settings,
            source="comtrade",
            dataset=RAW_DATASET,
            basename=_basename(year, reporters),
        )
        is not None
    )


def _codes_added_since(stored: dict | None, settings: Settings) -> set[str]:
    """Codes configured NOW that the archived raw was not fetched under.

    A settled-year raw resume-skips forever, which is right while the scope is stable and
    WRONG the moment a produto is added: the archived object only ever contained the codes
    requested at fetch time, so the new one would be missing from every past year and the
    dashboard would show it starting from the recent-refetch window only — a silent history
    truncation. COMEX solves the same problem by re-filtering its archived raw; here the raw
    simply does not contain the rows, so the API must be asked again.

    Deliberately ONE-DIRECTIONAL: only codes ADDED trigger work. Removing or reordering the
    scope leaves the archived superset perfectly usable (Silver filters), and re-fetching for
    that would burn the keyed daily quota for nothing.

    An object with no ``cmd_scope`` recorded (pre-provenance) returns empty: we cannot tell
    what it covered, and guessing "refetch" would re-bill the whole archive on a hunch. Every
    raw in the live bucket carries it, so this is a safety valve, not the normal path.
    """
    if not stored:
        return set()
    prior = {c for c in (stored.get("cmd_scope") or "").split(",") if c}
    if not prior:
        return set()
    return {c for c in settings.comtrade_cmd_map if c not in prior}


def needs_bronze(
    settings: Settings,
    year: int,
    reporters: list[str],
    *,
    extracted: bool,
    storage_client: storage.Client,
) -> bool:
    """Whether Phase 2 must run for this (year, reporter-batch) after Phase 1.

    Always when Phase 1 (re)fetched. When the raw already existed and was not
    re-fetched, only if Bronze has not yet been loaded from it — i.e. a prior run
    archived the raw then aborted before the load. Without this check, the
    raw-exists skip would leave that chunk permanently absent from Bronze.
    """
    if extracted:
        return True
    stored = raw_provenance(
        storage_client,
        settings=settings,
        source="comtrade",
        dataset=RAW_DATASET,
        basename=_basename(year, reporters),
    )
    return stored is not None and not raw_bronze_loaded(stored)


def mark_bronze_loaded(
    settings: Settings, year: int, reporters: list[str], *, storage_client: storage.Client
) -> None:
    """Stamp the (year, reporter-batch) raw object as loaded into Bronze.

    **Semantics: at-least-once, not exactly-once.** The marker is written *after*
    the Bronze load, so a crash between the load and this stamp leaves the chunk
    loaded but unmarked, and the next run reloads it. Duplicate rows are expected
    and safe: Silver dedupes on the natural key by ``ingestion_timestamp desc``,
    so Gold stays correct.
    """
    mark_raw_bronze_loaded(
        storage_client,
        settings=settings,
        source="comtrade",
        dataset=RAW_DATASET,
        basename=_basename(year, reporters),
    )


def ensure_destination(settings: Settings, bq_client: bigquery.Client) -> str:
    dataset_id = f"{settings.gcp_project_id}.{settings.bq_bronze_comtrade_dataset}"
    ensure_dataset(bq_client, dataset_id, settings.bq_location)
    return f"{dataset_id}.{settings.bq_bronze_comtrade_flows_table}"


def process_chunk(
    settings: Settings,
    year: int,
    reporters: list[str],
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
    table_fqn: str,
    from_raw: bool = False,
    force: bool = False,
) -> ChunkOutcome:
    """Run both phases for a single ``(year, reporter-batch)`` chunk.

    The one per-chunk unit of work, shared by :func:`run` and the CLI. Resume is
    preserved verbatim: a past-year chunk already archived is skipped, the latest
    year is always re-fetched, and an unchanged-but-unmarked raw still loads
    (``needs_bronze``). ``ComtradeQuotaError`` from the fetch is **not** caught
    here — it propagates so :func:`run` can stop the whole run early (re-running
    resumes from the un-archived chunks).
    """
    chunk_id = _basename(year, reporters)
    if from_raw:
        process = has_raw(settings, year, reporters, storage_client=storage_client)
    else:
        extracted = sync_raw(settings, year, reporters, storage_client=storage_client, force=force)
        # Skip Phase 2 only when the raw is unchanged AND already in Bronze;
        # an unchanged-but-never-loaded raw (aborted prior run) still loads.
        process = needs_bronze(
            settings, year, reporters, extracted=extracted, storage_client=storage_client
        )
    if not process:
        return ChunkOutcome(chunk_id, "skipped", detail="already archived")

    destination = bronze_one(
        settings,
        year,
        reporters,
        storage_client=storage_client,
        bq_client=bq_client,
        table_fqn=table_fqn,
    )
    mark_bronze_loaded(settings, year, reporters, storage_client=storage_client)
    if not destination:
        return ChunkOutcome(chunk_id, "skipped", detail="no rows")
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
    """Sync raw (Phase 1) then load Bronze (Phase 2), chunk by (year, batch).

    **Single source of truth for the ``(year, reporter-batch)`` loop**, with
    continue-on-failure: a transient chunk error is recorded and the loop moves
    on. Resumable across runs: re-running picks up only chunks not yet archived
    (+ the latest year). ``from_raw`` rebuilds Bronze from archived raw without
    calling the API.

    **Stops on quota.** When a chunk raises :class:`ComtradeQuotaError` (the
    daily call budget is exhausted), the loop breaks immediately and the error
    propagates — retrying the remaining chunks would only burn failed calls.
    Re-run later to resume from the un-archived chunks; nothing is lost.

    Hooks mirror the other pipelines: ``on_chunk_start(chunk_id)`` before each
    chunk, ``on_chunk(outcome)`` after. With no ``on_chunk`` consumer and any
    failure, the aggregated failures raise :class:`IngestPartialFailure`.
    """
    if not settings.comtrade_api_key:
        raise RuntimeError(
            "COMTRADE_API_KEY is empty — set it in .env (free key from comtradedeveloper.un.org)."
        )
    bq_client, storage_client = resolve_clients(settings, bq_client, storage_client)
    table_fqn = ensure_destination(settings, bq_client)

    reporters = resolve_reporters(settings)

    def _chunks():
        # One (chunk_id, thunk) per (year, reporter-batch). Default-arg binds
        # capture this iteration's values (no late-binding closure trap) so
        # run_chunks can call each thunk lazily.
        for year, reporter_batch in plan_chunks(settings, reporters):
            chunk_id = _basename(year, reporter_batch)
            yield (
                chunk_id,
                lambda year=year, reporter_batch=reporter_batch, chunk_id=chunk_id: _run_one_chunk(
                    settings,
                    year,
                    reporter_batch,
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
    year: int,
    reporter_batch: list[str],
    chunk_id: str,
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
    table_fqn: str,
    from_raw: bool,
    force: bool,
) -> ChunkOutcome:
    """Process one chunk, converting a transient error into a ``failed`` outcome.

    ``ComtradeQuotaError`` is NOT swallowed — it propagates so :func:`run` stops
    the whole run early (remaining chunks would only burn failed calls; re-running
    resumes from the un-archived chunks).
    """
    try:
        return process_chunk(
            settings,
            year,
            reporter_batch,
            storage_client=storage_client,
            bq_client=bq_client,
            table_fqn=table_fqn,
            from_raw=from_raw,
            force=force,
        )
    except ComtradeQuotaError:
        logger.warning("Comtrade quota exhausted at %s — stopping run.", chunk_id)
        raise
    except ComtradeTruncationError as exc:
        # A single (reporter, flow, cmd, year) exceeds the per-call row cap and
        # CANNOT be split further — it will truncate IDENTICALLY every run, so this
        # is a PERMANENT gap, not a transient failure. The outcome is still "failed"
        # (the chunk is left un-archived for an operator to address), but log it
        # DISTINCTLY at error level so it surfaces as an action-required anomaly
        # rather than blending into retryable noise: it will NOT self-heal on retry
        # (the fix is widening the split scope, e.g. a partner enumeration tier).
        logger.error(
            "Comtrade chunk %s PERMANENTLY truncated (un-splittable dense key) — "
            "operator action required; it will not self-heal on the next run. %s",
            chunk_id,
            exc,
        )
        return ChunkOutcome(chunk_id, "failed", detail=f"permanent truncation: {exc}")
    except Exception as exc:
        return ChunkOutcome(
            chunk_id, "failed", detail=str(exc), transient=isinstance(exc, SourceTransientError)
        )
