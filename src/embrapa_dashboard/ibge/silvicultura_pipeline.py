"""Two-phase Bronze pipeline for the IBGE PEVS silviculture half (SIDRA 291).

PEVS has two halves and ``ibge.pipeline`` ingests only the first: table 289,
extraction from NATIVE forest. This is the second: table 291, PLANTED forest.

It is the same survey and the same banco — ``gold_pevs_production`` carries both,
discriminated by its ``origem`` column — so this module deliberately does NOT
introduce a new source in the medallion sense. What it owns is the fetch: a
different SIDRA table needs its own request, its own raw-zone segment and its own
Bronze table, and the two halves only converge once, in Gold.

Structurally a sibling of ``ibge.pam_pipeline``: same generic SIDRA client
(``fetch_sidra_dataframe``), same all-STRING Bronze schema
(``ibge.pipeline._bronze_schema``), same delta-by-default behaviour. It parallels
them rather than refactoring a shared engine, for the same reason PAM did: those
modules are the live production paths with test suites coupled to their
internals, so reusing their stable primitives is the zero-regression choice.

Phase 1 (``extract_raw``) fetches SIDRA t291/c194 for the configured products and
year window and archives the response verbatim to ``raw/ibge/silvicultura/``.
Phase 2 (``bronze_from_raw``) reads it back, stamps ``ingestion_timestamp`` and
appends to Bronze. ``--from-raw`` rebuilds Bronze from that archive without
re-querying SIDRA. See ``PLANS/silvicultura_source.md`` and
``PLANS/raw_zone_architecture.md``.
"""

from __future__ import annotations

import logging
import time

import pandas as pd
from google.cloud import bigquery, storage

from embrapa_dashboard import observability
from embrapa_dashboard.config import Settings
from embrapa_dashboard.core import land_raw, list_raw, read_raw
from embrapa_dashboard.gcp.bigquery import (
    bronze_products_present,
    ensure_dataset,
    latest_reference_year,
    load_dataframe,
)
from embrapa_dashboard.gcp.clients import resolve_clients
from embrapa_dashboard.ibge import catalog_resolver
from embrapa_dashboard.ibge.client import fetch_sidra_dataframe
from embrapa_dashboard.ibge.pipeline import _bronze_schema, _order_by_fetched_at

logger = logging.getLogger(__name__)

# Observability / log tag — distinguishes silviculture events from the extraction
# half ('ibge') and from PAM/PPM in the monitor and event logs.
PIPELINE = "ibge_silvicultura"

# Both halves are IBGE/SIDRA, so they share source='ibge' in the raw zone; the
# DATASET segment isolates them: raw/ibge/silvicultura/ vs raw/ibge/pevs/. A
# --from-raw replay of one can therefore never pick up the other's archives.
SOURCE = "ibge"
RAW_DATASET = "silvicultura"

# Municipality-grained like t289, and the SIDRA client emits the same snake_case
# columns, so the clustering key is identical.
CLUSTERING_FIELDS = ["municipio_codigo", "ano", "variavel_codigo"]

# The Bronze column carrying c194's product code. Derived by the client's
# `_clean_column_name` from SIDRA's "Tipo de produto da silvicultura (Código)";
# verified against a live t291 response rather than assumed, because the delta
# backfill guard below joins on it and a wrong name would silently disable that
# guard instead of failing.
PRODUCT_CODE_COLUMN = "tipo_de_produto_da_silvicultura_codigo"


def _bronze_fqn(settings: Settings) -> str:
    return (
        f"{settings.gcp_project_id}."
        f"{settings.bq_bronze_ibge_dataset}.{settings.bq_bronze_silvicultura_table}"
    )


def _basename(settings: Settings, product_codes: list[str]) -> str:
    """Raw object basename encoding the products + window — re-running the same code
    set overwrites one object; a code change yields a new archive, which Silver dedups
    by ``ingestion_timestamp``."""
    return (
        f"products_{'_'.join(product_codes)}"
        f"_{settings.silvicultura_start_year}_{settings.silvicultura_end_year}"
    )


def _product_codes(settings: Settings) -> list[str]:
    """The codes to fetch — the catalog's t291 entries, falling back to env.

    PEVS's catalog token (``'pevs'``) holds BOTH halves, so this must resolve with its
    own ``sidra_tabela``: asking for the token alone would hand the SILVICULTURE table
    the EXTRACTION codes, SIDRA would answer with an empty slice, and the pipeline would
    report a clean no-op — the worst kind of wrong.

    This read the env list exclusively until 2026-08-29, because the catalog could not
    yet tell the two halves apart. It now can (the pevs entries carry ``sidra_tabela``,
    the tag PPM already used), so both halves resolve the same way, and a produto a
    researcher adds to the silviculture half is ingested without an env edit.
    """
    return catalog_resolver.resolve_product_codes(
        settings,
        "pevs",
        env_fallback=settings.silvicultura_product_codes_list,
        sidra_tabela=settings.silvicultura_table_id,
    )


def extract_raw(
    settings: Settings,
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client | None = None,
) -> str | None:
    """Phase 1: fetch SIDRA t291 and archive the verbatim response. Returns the raw
    basename, or ``None`` when SIDRA had no rows (nothing archived)."""
    product_codes = _product_codes(settings)
    started = time.monotonic()
    logger.info(
        "Ingesting PEVS silvicultura table=%s classification=%s products=%s years=%d-%d",
        settings.silvicultura_table_id,
        settings.silvicultura_classification_id,
        product_codes,
        settings.silvicultura_start_year,
        settings.silvicultura_end_year,
    )
    df = fetch_sidra_dataframe(
        table_id=settings.silvicultura_table_id,
        start_year=settings.silvicultura_start_year,
        end_year=settings.silvicultura_end_year,
        classification=settings.silvicultura_classification_id,
        products=product_codes,
        geo_level="n6",
        variables=settings.silvicultura_variable_codes,
    )
    if df.empty:
        # SIDRA had nothing — almost always the end year running ahead of the latest
        # published one. Skip so the raw zone / Bronze don't accumulate empties.
        observability.emit(
            "ingest_empty",
            pipeline=PIPELINE,
            start_year=settings.silvicultura_start_year,
            end_year=settings.silvicultura_end_year,
            duration_s=round(time.monotonic() - started, 2),
        )
        logger.warning(
            "Silvicultura ingest skipped: SIDRA returned no rows for %d-%d — usually "
            "SILVICULTURA_END_YEAR is ahead of the latest published year, which resolves "
            "itself once IBGE publishes it. Do NOT pin END to the latest published year: "
            "once Bronze reaches it the delta skips entirely and stops absorbing revisions.",
            settings.silvicultura_start_year,
            settings.silvicultura_end_year,
        )
        return None

    basename = _basename(settings, product_codes)
    land_raw(
        df.astype(str),
        settings=settings,
        storage_client=storage_client,
        source=SOURCE,
        dataset=RAW_DATASET,
        basename=basename,
        provenance={
            "source": "ibge-sidra",
            "table_id": settings.silvicultura_table_id,
            "classification": settings.silvicultura_classification_id,
            "products": ",".join(product_codes),
            "start_year": str(settings.silvicultura_start_year),
            "end_year": str(settings.silvicultura_end_year),
        },
    )
    return basename


def bronze_from_raw(
    settings: Settings,
    basenames: list[str],
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
) -> str:
    """Phase 2: read each raw archive, stamp ingestion_timestamp, append to Bronze.

    Multiple ``basenames`` are appended in the order given — the caller orders them
    oldest-fetch-first so Silver's dedup on the natural key by ``ingestion_timestamp
    desc`` collapses overlapping windows to the newest *extract*.
    """
    destination = _bronze_fqn(settings)
    for basename in basenames:
        df = read_raw(
            storage_client, settings=settings, source=SOURCE, dataset=RAW_DATASET, basename=basename
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
        observability.emit(
            "ingest_loaded", pipeline=PIPELINE, rows=len(df), destination=destination
        )
    return destination


def _delta_start_year(settings: Settings, bq_client: bigquery.Client) -> Settings | None:
    """Re-window ``settings`` so a routine run re-fetches only the recent years.

    Mirrors ``pam_pipeline._delta_start_year``: a cold Bronze falls back to the full
    window; a Bronze already at or past the end year is a logged clean no-op (``None``)
    rather than an inverted, empty period list; a product absent from Bronze forces one
    full-window run so its history is not truncated to the overlap.
    """
    table_fqn = _bronze_fqn(settings)
    last_year = latest_reference_year(bq_client, table_fqn)
    if last_year is None:
        return settings
    resolved = _product_codes(settings)
    present = bronze_products_present(bq_client, table_fqn, PRODUCT_CODE_COLUMN, resolved)
    missing = sorted(set(resolved) - present)
    if missing:
        logger.info(
            "Silvicultura delta: product(s) %s absent from Bronze — full-window backfill "
            "(%d-%d) so their history is not truncated to the delta overlap.",
            ",".join(missing),
            settings.silvicultura_start_year,
            settings.silvicultura_end_year,
        )
        return settings
    if last_year >= settings.silvicultura_end_year:
        logger.info(
            "Silvicultura delta: Bronze already at year %d (>= SILVICULTURA_END_YEAR %d) — "
            "nothing new to fetch, skipping. Raise the end year or use --full.",
            last_year,
            settings.silvicultura_end_year,
        )
        return None
    effective_start = min(
        max(
            settings.silvicultura_start_year,
            last_year - settings.silvicultura_delta_overlap_years,
        ),
        settings.silvicultura_end_year,
    )
    logger.info(
        "Silvicultura delta: re-fetching %d-%d (latest Bronze year %d, overlap %d).",
        effective_start,
        settings.silvicultura_end_year,
        last_year,
        settings.silvicultura_delta_overlap_years,
    )
    return settings.model_copy(update={"silvicultura_start_year": effective_start})


def run(
    settings: Settings,
    *,
    full: bool = False,
    from_raw: bool = False,
    storage_client: storage.Client | None = None,
    bq_client: bigquery.Client | None = None,
) -> str:
    """Extract→raw (Phase 1) then raw→Bronze (Phase 2). Returns destination, or ``""``."""
    bq_client, storage_client = resolve_clients(settings, bq_client, storage_client)
    dataset_id = f"{settings.gcp_project_id}.{settings.bq_bronze_ibge_dataset}"
    ensure_dataset(bq_client, dataset_id, settings.bq_location)

    if from_raw:
        basenames = list_raw(storage_client, settings=settings, source=SOURCE, dataset=RAW_DATASET)
        if not basenames:
            logger.warning("Silvicultura --from-raw: no raw archived for dataset %s.", RAW_DATASET)
            return ""
        basenames = _order_by_fetched_at(
            basenames,
            storage_client=storage_client,
            settings=settings,
            source=SOURCE,
            dataset=RAW_DATASET,
        )
    else:
        if not full:
            delta_settings = _delta_start_year(settings, bq_client)
            if delta_settings is None:
                return ""
            settings = delta_settings
        basename = extract_raw(settings, storage_client=storage_client, bq_client=bq_client)
        if basename is None:
            return ""
        basenames = [basename]

    return bronze_from_raw(settings, basenames, storage_client=storage_client, bq_client=bq_client)
