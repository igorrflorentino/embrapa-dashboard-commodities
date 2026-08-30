"""Two-phase Bronze pipeline for IBGE PPM (Pesquisa da Pecuária Municipal, SIDRA).

PPM is the *third* IBGE/SIDRA source. Like PEVS and PAM it reuses the generic
SIDRA client (``fetch_sidra_dataframe``: per-state parallelism + recursive
period-halving) and the all-STRING Bronze schema (``ibge.pipeline._bronze_schema``),
but it diverges in one structural way: PPM is **multi-table**. Its measures live
in TWO distinct SIDRA tables with different classification axes:

* ``3939`` "Efetivo dos rebanhos" — herd HEADCOUNT (variable 105, unit *Cabeças*),
  classification 79 (*tipo de rebanho*). A STOCK, with NO monetary value.
* ``74`` "Produção de origem animal" — milk/eggs/honey/wool output (variable 106
  quantity + 215 value; the derived 1000215 *percentual* series is excluded),
  classification 80 (*tipo de produto de origem animal*). A FLOW with value.

Each table lands in its OWN Bronze table and its OWN raw-zone segment
(``raw/ibge/ppm_herd/`` vs ``raw/ibge/ppm_animal/``), so a ``--from-raw`` replay
of one never picks up the other (the same isolation PEVS/PAM use against each
other). Silver unions the two into ``silver_ibge_ppm``.

Phase 1 (``extract_raw``) fetches each SIDRA response and archives it verbatim.
Phase 2 (``bronze_from_raw``) reads it back, stamps ``ingestion_timestamp`` and
appends to that table's BigQuery Bronze. Delta-by-default (per table): a routine
run re-fetches only the recent, still-revisable window. See
``PLANS/raw_zone_architecture.md``.

This module deliberately parallels ``ibge.pam_pipeline`` rather than refactoring
it into a shared engine: the divergence is the per-table spec loop, kept thin and
local so the stable PEVS/PAM primitives stay untouched.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

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

# Observability / log tag — distinguishes PPM events from PEVS ('ibge') and PAM in
# the monitor and event logs.
PIPELINE = "ibge_ppm"

# All three IBGE/SIDRA sources share source='ibge' in the raw zone; the DATASET
# segment isolates them. PPM additionally splits its OWN two tables into separate
# segments (ppm_herd / ppm_animal) so their --from-raw replays never cross.
SOURCE = "ibge"

# PPM is municipality-grained like PEVS/PAM; the SIDRA client emits the same
# snake_case columns for both tables, so the clustering key is identical.
CLUSTERING_FIELDS = ["municipio_codigo", "ano", "variavel_codigo"]


@dataclass(frozen=True)
class _Spec:
    """One SIDRA table to ingest (PPM spans two — herd + animal production)."""

    key: str  # short id: log tag + raw-zone segment suffix (raw/ibge/ppm_<key>/)
    table_id: str
    classification_id: str
    product_codes: tuple[str, ...]
    variable_codes: str  # comma-joined SIDRA variable subset (never v/all)
    bronze_table: str  # this table's Bronze destination table name

    @property
    def raw_dataset(self) -> str:
        return f"ppm_{self.key}"


def _specs(settings: Settings, bq_client: bigquery.Client | None = None) -> list[_Spec]:
    """The two PPM SIDRA tables, built from settings.

    Each table's product codes come from the Curadoria catalog when
    ``catalog_authoritative_ingestion`` is set — routed by ``tabela`` (the
    SIDRA table id) so herd (3939) and animal (74) codes never cross — else from
    the env fields (see ``catalog_resolver``). ``bq_client`` is reused when given.
    """
    return [
        _Spec(
            key="herd",
            table_id=settings.ppm_herd_table_id,
            classification_id=settings.ppm_herd_classification_id,
            product_codes=tuple(
                catalog_resolver.resolve_product_codes(
                    settings,
                    "ppm",
                    env_fallback=settings.ppm_herd_product_codes_list,
                    tabela=settings.ppm_herd_table_id,
                    bq_client=bq_client,
                )
            ),
            variable_codes=settings.ppm_herd_variable_codes,
            bronze_table=settings.bq_bronze_ppm_herd_table,
        ),
        _Spec(
            key="animal",
            table_id=settings.ppm_animal_table_id,
            classification_id=settings.ppm_animal_classification_id,
            product_codes=tuple(
                catalog_resolver.resolve_product_codes(
                    settings,
                    "ppm",
                    env_fallback=settings.ppm_animal_product_codes_list,
                    tabela=settings.ppm_animal_table_id,
                    bq_client=bq_client,
                )
            ),
            variable_codes=settings.ppm_animal_variable_codes,
            bronze_table=settings.bq_bronze_ppm_animal_table,
        ),
    ]


def _basename(spec: _Spec, start_year: int, end_year: int) -> str:
    """Raw object basename encoding the table + products + window — re-running the
    same config overwrites a single object per table (idempotent extract)."""
    return f"{spec.key}_products_{'_'.join(spec.product_codes)}_{start_year}_{end_year}"


def extract_raw(
    settings: Settings,
    spec: _Spec,
    *,
    start_year: int,
    storage_client: storage.Client,
) -> str | None:
    """Phase 1: fetch one SIDRA table and archive the verbatim response. Returns
    the raw basename, or ``None`` when SIDRA had no rows (nothing archived)."""
    product_codes = list(spec.product_codes)
    started = time.monotonic()
    logger.info(
        "Ingesting PPM table=%s classification=%s products=%s years=%d-%d",
        spec.table_id,
        spec.classification_id,
        product_codes,
        start_year,
        settings.ppm_end_year,
    )
    df = fetch_sidra_dataframe(
        table_id=spec.table_id,
        start_year=start_year,
        end_year=settings.ppm_end_year,
        classification=spec.classification_id,
        products=product_codes,
        geo_level="n6",
        # Fetch only the substantive variables, not v/all — table 74's derived
        # "percentual" series (1000215) would push a dense state past SIDRA's cell
        # limit, exactly like PAM's table 5457.
        variables=spec.variable_codes,
    )
    if df.empty:
        # SIDRA had nothing — almost always PPM_END_YEAR set past the latest
        # published year. Skip so the raw zone / Bronze don't accumulate empties.
        observability.emit(
            "ingest_empty",
            pipeline=PIPELINE,
            table=spec.table_id,
            start_year=start_year,
            end_year=settings.ppm_end_year,
            duration_s=round(time.monotonic() - started, 2),
        )
        logger.warning(
            "PPM ingest skipped for table %s: SIDRA returned no rows for %d-%d — "
            "usually PPM_END_YEAR is ahead of the latest published year, an "
            "expected state that resolves once IBGE publishes the new year. Do NOT "
            "pin PPM_END_YEAR to the latest published year (END must float ahead, "
            "else the nightly delta skips and stops absorbing revisions).",
            spec.table_id,
            start_year,
            settings.ppm_end_year,
        )
        return None

    basename = _basename(spec, start_year, settings.ppm_end_year)
    land_raw(
        df.astype(str),
        settings=settings,
        storage_client=storage_client,
        source=SOURCE,
        dataset=spec.raw_dataset,
        basename=basename,
        provenance={
            "source": "ibge-sidra",
            "table_id": spec.table_id,
            "classification": spec.classification_id,
            "products": ",".join(product_codes),
            "start_year": str(start_year),
            "end_year": str(settings.ppm_end_year),
        },
    )
    return basename


def bronze_from_raw(
    settings: Settings,
    spec: _Spec,
    basenames: list[str],
    *,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
) -> str:
    """Phase 2: read each raw SIDRA archive for this table, stamp ingestion_timestamp,
    append to that table's Bronze. ``basenames`` are ordered oldest-fetch-first by
    the caller so Silver's dedup keeps the newest extract."""
    dataset_id = f"{settings.gcp_project_id}.{settings.bq_bronze_ppm_dataset}"
    destination = f"{dataset_id}.{spec.bronze_table}"
    for basename in basenames:
        df = read_raw(
            storage_client,
            settings=settings,
            source=SOURCE,
            dataset=spec.raw_dataset,
            basename=basename,
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
            "ingest_loaded",
            pipeline=PIPELINE,
            table=spec.table_id,
            rows=len(df),
            destination=destination,
        )
    return destination


# Bronze product-code column per PPM table — herd (3939) vs animal production (74) live in
# separate tables with distinct product dims. Used to spot a newly-added product needing a
# full-history backfill (the delta window is table-global, not per-product).
_PPM_PRODUCT_COLUMN = {
    "herd": "tipo_de_rebanho_codigo",
    "animal": "tipo_de_produto_de_origem_animal_codigo",
}


def _delta_start_year(settings: Settings, spec: _Spec, bq_client: bigquery.Client) -> int | None:
    """Effective re-fetch start for one table so a routine run re-fetches only the
    recent (still-revisable) years. Returns ``ppm_start_year`` when Bronze is cold
    (full window) OR when a newly-added product is absent from Bronze (so its full history
    backfills instead of being truncated to the delta overlap), or ``None`` — a logged clean
    no-op — when Bronze is already at or past ``ppm_end_year``. Clamped to never exceed
    ``ppm_end_year`` (no inverted window).
    """
    table_fqn = f"{settings.gcp_project_id}.{settings.bq_bronze_ppm_dataset}.{spec.bronze_table}"
    last_year = latest_reference_year(bq_client, table_fqn)
    if last_year is None:
        return settings.ppm_start_year
    # A newly-added product has NO Bronze rows, so the table-global delta window would start
    # it at last_year - overlap and silently truncate its history. Backfill the full window
    # for this table if any configured code is absent (self-heals to delta next run). Precedes
    # the "already current" skip so a product added at end_year still backfills.
    present = bronze_products_present(
        bq_client, table_fqn, _PPM_PRODUCT_COLUMN[spec.key], spec.product_codes
    )
    missing = sorted(set(spec.product_codes) - present)
    if missing:
        logger.info(
            "PPM delta (table %s): product(s) %s absent from Bronze — full-window backfill "
            "so their history is not truncated to the delta overlap.",
            spec.table_id,
            ",".join(missing),
        )
        return settings.ppm_start_year
    if last_year >= settings.ppm_end_year:
        logger.info(
            "PPM delta (table %s): Bronze already at year %d (>= PPM_END_YEAR %d) — "
            "nothing new to fetch, skipping. Raise PPM_END_YEAR or use --full.",
            spec.table_id,
            last_year,
            settings.ppm_end_year,
        )
        return None
    floor = settings.ppm_start_year if settings.ppm_start_year is not None else 0
    effective_start = min(
        max(floor, last_year - settings.ppm_delta_overlap_years), settings.ppm_end_year
    )
    logger.info(
        "PPM delta (table %s): re-fetching %d-%d (latest Bronze year %d, overlap %d).",
        spec.table_id,
        effective_start,
        settings.ppm_end_year,
        last_year,
        settings.ppm_delta_overlap_years,
    )
    return effective_start


def _run_spec(
    settings: Settings,
    spec: _Spec,
    *,
    full: bool,
    from_raw: bool,
    storage_client: storage.Client,
    bq_client: bigquery.Client,
) -> str:
    """Run one SIDRA table through extract→raw→Bronze. Returns its Bronze
    destination, or ``""`` when nothing was loaded (empty fetch / delta no-op)."""
    if from_raw:
        basenames = list_raw(
            storage_client, settings=settings, source=SOURCE, dataset=spec.raw_dataset
        )
        if not basenames:
            logger.warning("PPM --from-raw: no raw archived for dataset %s.", spec.raw_dataset)
            return ""
        basenames = _order_by_fetched_at(
            basenames,
            storage_client=storage_client,
            settings=settings,
            source=SOURCE,
            dataset=spec.raw_dataset,
        )
    else:
        start_year = settings.ppm_start_year
        if start_year is None:
            raise RuntimeError(
                "PPM_START_YEAR is empty. Run `embrapa discover ibge-periods "
                f"--table-id {spec.table_id}` to find the first available year."
            )
        if not full:
            delta_start = _delta_start_year(settings, spec, bq_client)
            if delta_start is None:
                return ""  # Bronze already current — clean no-op.
            start_year = delta_start
        basename = extract_raw(settings, spec, start_year=start_year, storage_client=storage_client)
        if basename is None:
            return ""
        basenames = [basename]

    return bronze_from_raw(
        settings, spec, basenames, storage_client=storage_client, bq_client=bq_client
    )


def run(
    settings: Settings,
    *,
    full: bool = False,
    from_raw: bool = False,
    storage_client: storage.Client | None = None,
    bq_client: bigquery.Client | None = None,
) -> str:
    """Ingest BOTH PPM SIDRA tables (herd + animal production) into Bronze.

    Each table runs extract→raw (Phase 1) then raw→Bronze (Phase 2), delta by
    default (per table). ``full`` re-fetches the whole configured window; ``from_raw``
    rebuilds Bronze from the archived raw trail without re-querying SIDRA. Returns the
    loaded Bronze destinations joined by ``"; "``, or ``""`` when nothing was loaded.
    """
    bq_client, storage_client = resolve_clients(settings, bq_client, storage_client)
    dataset_id = f"{settings.gcp_project_id}.{settings.bq_bronze_ppm_dataset}"
    ensure_dataset(bq_client, dataset_id, settings.bq_location)

    destinations = [
        dest
        for spec in _specs(settings, bq_client=bq_client)
        if (
            dest := _run_spec(
                settings,
                spec,
                full=full,
                from_raw=from_raw,
                storage_client=storage_client,
                bq_client=bq_client,
            )
        )
    ]
    return "; ".join(destinations)
