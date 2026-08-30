"""Two-phase Bronze pipeline for IBGE PEVS.

Phase 1 (``extract_raw``) fetches the SIDRA response (already filtered by the
API query — table, classification, products, year window) and archives it
verbatim to the GCS raw zone. Phase 2 (``bronze_from_raw``) reads it back,
stamps ``ingestion_timestamp`` and loads BigQuery Bronze. See
``PLANS/raw_zone_architecture.md``.

SIDRA is queried fresh each run (a GET with no ETag), so Phase 1 always
re-extracts and overwrites the raw object for the configured window; the
``--from-raw`` path rebuilds Bronze from that archive without re-querying SIDRA.
"""

from __future__ import annotations

import logging
import time

import pandas as pd
from google.cloud import bigquery, storage

from embrapa_dashboard import observability
from embrapa_dashboard.config import Settings
from embrapa_dashboard.core import land_raw, list_raw, raw_provenance, read_raw
from embrapa_dashboard.gcp.bigquery import (
    bronze_products_present,
    ensure_dataset,
    latest_reference_year,
    load_dataframe,
)
from embrapa_dashboard.gcp.clients import resolve_clients
from embrapa_dashboard.ibge import catalog_resolver
from embrapa_dashboard.ibge.client import fetch_sidra_dataframe

logger = logging.getLogger(__name__)

# Segment under raw/ibge/<dataset>/ — one raw object per configured window.
RAW_DATASET = "pevs"

CLUSTERING_FIELDS = ["municipio_codigo", "ano", "variavel_codigo"]


def _bronze_schema(columns: list[str]) -> list[bigquery.SchemaField]:
    """All raw SIDRA columns are STRING; only ingestion_timestamp is typed."""
    schema = [
        bigquery.SchemaField(col, "STRING", mode="NULLABLE")
        for col in columns
        if col != "ingestion_timestamp"
    ]
    schema.append(bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP", mode="REQUIRED"))
    return schema


def _basename(settings: Settings, product_codes: list[str]) -> str:
    """Raw object basename encoding the products + window — re-running the same
    resolved code set overwrites one object; a catalog-driven code change yields a
    new basename (a new archive), which Silver dedups by ``ingestion_timestamp``."""
    return f"products_{'_'.join(product_codes)}_{settings.ibge_start_year}_{settings.ibge_end_year}"


def extract_raw(
    settings: Settings,
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client | None = None,
) -> str | None:
    """Phase 1: fetch SIDRA and archive the verbatim response. Returns the raw
    basename, or ``None`` when SIDRA had no rows (nothing archived).

    The product-code list comes from the Curadoria catalog when
    ``catalog_authoritative_ingestion`` is set (else the env codes) — see
    ``catalog_resolver``; ``bq_client`` lets it reuse the caller's client."""
    if settings.ibge_start_year is None:
        raise RuntimeError(
            "IBGE_START_YEAR is empty. Run `embrapa discover ibge-periods "
            f"--table-id {settings.ibge_table_id}` to find the first available year."
        )
    product_codes = catalog_resolver.resolve_product_codes(
        settings,
        "pevs",
        env_fallback=settings.product_codes,
        # PEVS spans TWO SIDRA tables under one banco token since 2026-08-29 (t289 here,
        # t291 in silvicultura_pipeline). Without this filter the catalog hands t289 the
        # silviculture codes too, and SIDRA answers with an empty slice that this pipeline
        # reports as a clean no-op — the extraction half would stop ingesting and nothing
        # would say so. An UNTAGGED entry resolves here (see catalog_resolver).
        tabela=settings.ibge_table_id,
        bq_client=bq_client,
    )
    started = time.monotonic()
    logger.info(
        "Ingesting PEVS table=%s classification=%s products=%s years=%d-%d",
        settings.ibge_table_id,
        settings.ibge_classification_id,
        product_codes,
        settings.ibge_start_year,
        settings.ibge_end_year,
    )
    df = fetch_sidra_dataframe(
        table_id=settings.ibge_table_id,
        start_year=settings.ibge_start_year,
        end_year=settings.ibge_end_year,
        classification=settings.ibge_classification_id,
        products=product_codes,
        geo_level="n6",
    )
    if df.empty:
        # SIDRA had nothing — almost always IBGE_END_YEAR set past the latest
        # published year. Skip so the raw zone / Bronze don't accumulate empties.
        observability.emit(
            "ingest_empty",
            pipeline="ibge",
            start_year=settings.ibge_start_year,
            end_year=settings.ibge_end_year,
            duration_s=round(time.monotonic() - started, 2),
        )
        logger.warning(
            "IBGE ingest skipped: SIDRA returned no rows for %d-%d — usually "
            "IBGE_END_YEAR is ahead of the latest published PEVS year, an "
            "expected state that resolves itself once IBGE publishes the new "
            "year. Do NOT pin IBGE_END_YEAR to the latest published year: once "
            "Bronze reaches it, the nightly delta skips entirely and stops "
            "absorbing PEVS revisions of recent years (END must float ahead).",
            settings.ibge_start_year,
            settings.ibge_end_year,
        )
        return None

    basename = _basename(settings, product_codes)
    land_raw(
        df.astype(str),
        settings=settings,
        storage_client=storage_client,
        source="ibge",
        dataset=RAW_DATASET,
        basename=basename,
        provenance={
            "source": "ibge-sidra",
            "table_id": settings.ibge_table_id,
            "classification": settings.ibge_classification_id,
            "products": ",".join(product_codes),
            "start_year": str(settings.ibge_start_year),
            "end_year": str(settings.ibge_end_year),
        },
    )
    return basename


def _order_by_fetched_at(
    basenames: list[str],
    *,
    storage_client: storage.Client,
    settings: Settings,
    source: str,
    dataset: str,
) -> list[str]:
    """Order raw basenames by their stored ``fetched_at`` provenance, oldest first.

    IBGE/PAM basenames encode products + year-window only — NOT extraction time —
    so ``list_raw``'s lexical order need not match fetch recency (unlike BCB,
    whose basenames are run-stamped). The replay stamps each object with a fresh
    ``ingestion_timestamp`` and Silver dedupes by ``ingestion_timestamp desc``,
    so whichever object is appended LAST wins the natural key: replaying a stale
    overlapping window after a newer one would silently resurrect old readings
    into Silver/Gold. ``fetched_at`` is the ISO-8601 UTC stamp ``land_raw``
    writes on every raw object; objects missing it (pre-provenance archives)
    sort first so any stamped extract outranks them. Lexical basename is the
    deterministic tie-break.
    """

    def sort_key(basename: str) -> tuple[str, str]:
        stored = (
            raw_provenance(
                storage_client,
                settings=settings,
                source=source,
                dataset=dataset,
                basename=basename,
            )
            or {}
        )
        return (str(stored.get("fetched_at", "")), basename)

    return sorted(basenames, key=sort_key)


def bronze_from_raw(
    settings: Settings,
    basenames: list[str],
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
) -> str:
    """Phase 2: read each raw SIDRA archive, stamp ingestion_timestamp, append to Bronze.

    Multiple ``basenames`` (``--from-raw`` replaying the delta trail) are appended
    in the order given — the caller orders them oldest-fetch-first (see
    ``_order_by_fetched_at``) so Silver's dedup on the natural key by
    ``ingestion_timestamp desc`` collapses overlapping windows to the newest
    *extract*, not to whichever basename happened to sort last.
    """
    dataset_id = f"{settings.gcp_project_id}.{settings.bq_bronze_ibge_dataset}"
    destination = f"{dataset_id}.{settings.bq_bronze_ibge_table}"
    for basename in basenames:
        df = read_raw(
            storage_client, settings=settings, source="ibge", dataset=RAW_DATASET, basename=basename
        )
        df = df.astype(str)
        df["ingestion_timestamp"] = pd.Timestamp.now(tz="UTC")
        load_dataframe(
            bq_client,
            df,
            destination,
            _bronze_schema(list(df.columns)),
            time_partitioning_field="ingestion_timestamp",
            clustering_fields=CLUSTERING_FIELDS,
        )
        observability.emit("ingest_loaded", pipeline="ibge", rows=len(df), destination=destination)
    return destination


def _delta_start_year(settings: Settings, bq_client: bigquery.Client) -> Settings | None:
    """Re-window ``settings`` to a recent delta start so a routine run re-fetches
    only the latest (still-revisable) years, not the whole 1986→today history.

    PEVS only revises recent years, so refetching the last few absorbs revisions
    and picks up a newly published year, while the heavy full-history request
    (which can blow the SIDRA slow-byte deadline) is reserved for ``--full``.

    Returns ``settings`` unchanged when Bronze has no data yet (cold table →
    full). Returns ``None`` — a logged clean no-op — when Bronze is already at or
    past ``ibge_end_year``: there is no newer year to fetch, and the naive
    ``last_year - overlap`` could otherwise land *after* ``end_year`` and produce
    an inverted (empty) period list that crashes the SIDRA client. The effective
    start is also clamped to never exceed ``end_year`` for the same reason.
    """
    table_fqn = (
        f"{settings.gcp_project_id}.{settings.bq_bronze_ibge_dataset}."
        f"{settings.bq_bronze_ibge_table}"
    )
    last_year = latest_reference_year(bq_client, table_fqn)
    if last_year is None:
        return settings
    # A newly-added product has NO Bronze rows, so the table-global delta window would
    # start it at last_year - overlap and silently truncate its history. If any resolved
    # code is absent from Bronze, fetch the FULL configured window so it backfills; the
    # existing products just re-fetch their full window that one run — a one-time cost that
    # self-heals (once the new product is in Bronze it is no longer new, and the next run
    # returns to the delta window). This precedes the "already current" skip below so a new
    # product added when Bronze is at end_year still backfills instead of being skipped.
    resolved = catalog_resolver.resolve_product_codes(
        settings,
        "pevs",
        env_fallback=settings.product_codes,
        # PEVS spans TWO SIDRA tables under one banco token since 2026-08-29 (t289 here,
        # t291 in silvicultura_pipeline). Without this filter the catalog hands t289 the
        # silviculture codes too, and SIDRA answers with an empty slice that this pipeline
        # reports as a clean no-op — the extraction half would stop ingesting and nothing
        # would say so. An UNTAGGED entry resolves here (see catalog_resolver).
        tabela=settings.ibge_table_id,
        bq_client=bq_client,
    )
    present = bronze_products_present(
        bq_client, table_fqn, "tipo_de_produto_extrativo_codigo", resolved
    )
    missing = sorted(set(resolved) - present)
    if missing:
        logger.info(
            "IBGE delta: product(s) %s absent from Bronze — full-window backfill (%s-%d) "
            "so their history is not truncated to the delta overlap.",
            ",".join(missing),
            settings.ibge_start_year,
            settings.ibge_end_year,
        )
        return settings
    if last_year >= settings.ibge_end_year:
        # Bronze already holds the latest configured year — nothing newer to
        # pull. Skip cleanly instead of building an inverted window.
        logger.info(
            "IBGE delta: Bronze already at year %d (>= IBGE_END_YEAR %d) — "
            "nothing new to fetch, skipping. Raise IBGE_END_YEAR or use --full "
            "to force a re-fetch.",
            last_year,
            settings.ibge_end_year,
        )
        return None
    floor = settings.ibge_start_year if settings.ibge_start_year is not None else 0
    # Clamp to <= end_year so the window can never invert (start > end).
    effective_start = min(
        max(floor, last_year - settings.ibge_delta_overlap_years), settings.ibge_end_year
    )
    logger.info(
        "IBGE delta: re-fetching %d-%d (latest Bronze year %d, overlap %d).",
        effective_start,
        settings.ibge_end_year,
        last_year,
        settings.ibge_delta_overlap_years,
    )
    return settings.model_copy(update={"ibge_start_year": effective_start})


def run(
    settings: Settings,
    *,
    full: bool = False,
    from_raw: bool = False,
    storage_client: storage.Client | None = None,
    bq_client: bigquery.Client | None = None,
) -> str:
    """Extract→raw (Phase 1) then raw→Bronze (Phase 2). Returns destination, or ``""``.

    Delta by default: re-fetches only the recent overlap window (see
    ``_delta_start_year``). ``full`` re-fetches the whole configured window (used
    by ``ingest --full`` and per-chunk by ``ingest ibge-batch``). ``from_raw``
    rebuilds Bronze from the archived raw trail without re-querying SIDRA.
    Optional clients let the batch CLI reuse one client across chunks.
    """
    bq_client, storage_client = resolve_clients(settings, bq_client, storage_client)
    dataset_id = f"{settings.gcp_project_id}.{settings.bq_bronze_ibge_dataset}"
    ensure_dataset(bq_client, dataset_id, settings.bq_location)

    if from_raw:
        basenames = list_raw(storage_client, settings=settings, source="ibge", dataset=RAW_DATASET)
        if not basenames:
            logger.warning("IBGE --from-raw: no raw archived for dataset %s.", RAW_DATASET)
            return ""
        # Replay oldest-fetch-first so the newest extract wins Silver dedup.
        basenames = _order_by_fetched_at(
            basenames,
            storage_client=storage_client,
            settings=settings,
            source="ibge",
            dataset=RAW_DATASET,
        )
    else:
        if not full:
            delta_settings = _delta_start_year(settings, bq_client)
            if delta_settings is None:
                # Bronze already current — clean no-op (see _delta_start_year).
                return ""
            settings = delta_settings
        basename = extract_raw(settings, storage_client=storage_client, bq_client=bq_client)
        if basename is None:
            return ""
        basenames = [basename]

    return bronze_from_raw(settings, basenames, storage_client=storage_client, bq_client=bq_client)
