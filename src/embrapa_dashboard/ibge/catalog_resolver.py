"""Resolve an IBGE/SIDRA pipeline's product-code list from the Curadoria catalog.

This is the seam that inverts the ingestion dependency: when
``settings.catalog_authoritative_ingestion`` is TRUE, the IBGE pipelines
(``pipeline``/``pam_pipeline``/``ppm_pipeline``) ask this module for the codes to
fetch instead of reading the ``*_product_codes`` env fields — making the editable
"Cadastro de produtos" catalog (``research_inputs.produto_catalog_log``) the
single source of truth for WHAT is ingested. The engineering metadata (table /
classification / variable ids, delta windows) stays in ``config`` regardless.

Design constraints (why this module is deliberately tiny and self-contained):

* **Runs in the slim ingestion image.** ``deploy/ingestion/Dockerfile`` installs
  ``uv sync --no-dev`` WITHOUT the ``webapi`` extra, so ``flask-caching`` is
  absent. This module must NOT import anything under ``serving/`` (``gateway`` is
  memoized with flask-caching and would fail to import). It depends only on
  ``google.cloud.bigquery`` (a core dep), ``config`` and the flask-free
  ``gcp.clients.resolve_bq_client`` — plus ``observability`` (also flask-free).
* **Runs BEFORE dbt.** The nightly ingestion writes Bronze hours before the daily
  ``dbt build``, so we read the RAW append-only log directly (latest-wins per
  ``(codigo_produto, banco)``, ``active``) — NOT the ``dim_produto_catalog`` dbt
  view, which may not exist yet.
* **Never breaks a run.** Any problem (flag off, table absent, empty result, a BQ
  error, or the safety cap tripping) falls back to the caller's ``env_fallback``
  — the exact codes ingestion used before this feature. The function never raises.
"""

from __future__ import annotations

import logging

from google.api_core.exceptions import BadRequest
from google.cloud import bigquery

from embrapa_dashboard import observability
from embrapa_dashboard.config import Settings
from embrapa_dashboard.gcp.clients import resolve_bq_client

logger = logging.getLogger(__name__)

# The banco tokens whose ingestion scope THIS module resolves — i.e. the only ones a
# catalog edit can actually steer. COMEX/COMTRADE are absent on purpose: their scope
# comes from ``settings.comex_*_codes`` / ``comtrade_cmd_codes``, so registering a code
# for them adds it to the catalog (and the crosswalk) but NEVER causes a fetch.
#
# Exported so the editor UI can say so instead of promising "será buscado na próxima
# ingestão" for every banco — a promise that, for a trade banco, never comes true.
CATALOG_DRIVEN_BANCOS: tuple[str, ...] = ("pevs", "pam", "ppm")


def resolve_product_codes(
    settings: Settings,
    banco: str,
    *,
    env_fallback: list[str],
    sidra_tabela: str | None = None,
    bq_client: bigquery.Client | None = None,
) -> list[str]:
    """Product codes to ingest for ``banco``: the catalog's active codes, else env.

    ``banco`` is the catalog token (``'pevs'`` / ``'pam'`` / ``'ppm'``). For PPM,
    pass ``sidra_tabela`` (``'3939'`` herd / ``'74'`` animal) so only the codes
    tagged for that SIDRA table are returned. ``env_fallback`` is the current
    ``settings.*_product_codes_list`` — returned verbatim whenever the catalog is
    not authoritative or cannot be trusted. Never raises.
    """
    if not settings.catalog_authoritative_ingestion:
        # Feature off → behave exactly like today (read the env codes). No BQ hit.
        return env_fallback

    try:
        codes = _query_catalog_codes(settings, banco, sidra_tabela, bq_client)
    except Exception as exc:
        logger.warning(
            "Catalog resolve failed for banco=%s (sidra_tabela=%s): %s — falling back "
            "to env product codes.",
            banco,
            sidra_tabela,
            exc,
        )
        _emit(banco, sidra_tabela, resolved=len(env_fallback), used="env-error")
        return env_fallback

    if not codes:
        # Empty/absent catalog for this banco → env fallback (cold-start / not yet
        # seeded). Informational: an intentionally-empty catalog is a normal state.
        logger.info(
            "Catalog has no active codes for banco=%s (sidra_tabela=%s) — using env product codes.",
            banco,
            sidra_tabela,
        )
        _emit(banco, sidra_tabela, resolved=len(env_fallback), used="env")
        return env_fallback

    if len(codes) > settings.catalog_resolver_max_codes:
        # Safety cap: a researcher edit now drives the nightly SIDRA pull. Refuse an
        # implausibly large set (fat-finger / bad import) rather than fire a huge,
        # slow, expensive request — fall back to the known-good env codes.
        logger.error(
            "Catalog resolved %d codes for banco=%s (sidra_tabela=%s), above the safety "
            "cap of %d — refusing and falling back to env product codes. Raise "
            "CATALOG_RESOLVER_MAX_CODES if this set is legitimate.",
            len(codes),
            banco,
            sidra_tabela,
            settings.catalog_resolver_max_codes,
        )
        _emit(banco, sidra_tabela, resolved=len(codes), used="cap")
        return env_fallback

    logger.info(
        "Catalog resolved %d codes for banco=%s (sidra_tabela=%s): %s",
        len(codes),
        banco,
        sidra_tabela,
        codes,
    )
    _emit(banco, sidra_tabela, resolved=len(codes), used="catalog")
    return codes


def read_catalog_codes(
    settings: Settings,
    banco: str,
    *,
    sidra_tabela: str | None = None,
    bq_client: bigquery.Client | None = None,
) -> list[str]:
    """The catalog's active codes for a banco, IGNORING ``catalog_authoritative_ingestion``
    — for DIAGNOSTICS (``embrapa doctor``'s parity check) that preview what the catalog
    WOULD drive at cutover. Returns [] on absence / any error (never raises)."""
    try:
        return _query_catalog_codes(settings, banco, sidra_tabela, bq_client)
    except Exception:
        return []


def _query_catalog_codes(
    settings: Settings,
    banco: str,
    sidra_tabela: str | None,
    bq_client: bigquery.Client | None,
) -> list[str]:
    """Query the raw catalog log for the active codes of ``banco`` (latest-wins).

    Mirrors ``serving.gateway.fetch_produto_catalog`` but reads the raw log table
    directly (no dbt view, no flask-caching) and returns just the code list. The
    ``sidra_tabela`` column is only referenced when a value is supplied, so PEVS/PAM
    resolution stays robust even before that column exists on the log table.
    """
    client = resolve_bq_client(settings, bq_client)
    table = (
        f"{settings.gcp_project_id}.{settings.bq_research_inputs_dataset}."
        f"{settings.bq_produto_catalog_log_table}"
    )
    params: list[bigquery.ScalarQueryParameter] = [
        bigquery.ScalarQueryParameter("banco", "STRING", banco)
    ]
    if sidra_tabela is not None:
        extra_cols = ", sidra_tabela"
        extra_filter = "and sidra_tabela = @sidra_tabela"
        params.append(bigquery.ScalarQueryParameter("sidra_tabela", "STRING", sidra_tabela))
    else:
        extra_cols = ""
        extra_filter = ""

    def _sql(*, with_ingestao: bool) -> str:
        # `ingestao = 'pausada'` FREEZES a produto: stop fetching new data, keep everything
        # already in Gold (and keep showing it — visibility is a separate axis). Before the
        # two-axis split the only way to stop ingesting was to REMOVE the produto, which
        # turned it into an orphan awaiting purge. NULL predates the axis and must read as
        # 'ativa' — anything else would silently stop ingesting every produto registered
        # before the split.
        ingestao_col = ", ingestao" if with_ingestao else ""
        pause_filter = "and coalesce(ingestao, 'ativa') != 'pausada'" if with_ingestao else ""
        return f"""
            select codigo_produto from (
              select codigo_produto, active{ingestao_col}{extra_cols}, row_number() over (
                partition by codigo_produto, banco order by edited_at desc, change_id desc
              ) as _rn
              from `{table}`
              where banco = @banco
            )
            where _rn = 1 and active {pause_filter} {extra_filter}
            order by codigo_produto
        """

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    if settings.bq_max_bytes_billed:
        job_config.maximum_bytes_billed = settings.bq_max_bytes_billed
    try:
        rows = client.query(_sql(with_ingestao=True), job_config=job_config).result()
    except BadRequest:
        # The log table predates the `ingestao` column. Retry WITHOUT the pause filter
        # rather than let the caller's broad except fall back to the env codes: if the
        # column does not exist, no row can be paused, so dropping the filter is EXACTLY
        # equivalent — whereas the env fallback would abandon the catalog entirely
        # (skipping codes the researcher added, and re-fetching ones they paused).
        logger.warning(
            "Catalog log has no `ingestao` column yet (pre two-axis split) — resolving "
            "without the pause filter; no produto can be paused without that column."
        )
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        if settings.bq_max_bytes_billed:
            job_config.maximum_bytes_billed = settings.bq_max_bytes_billed
        rows = client.query(_sql(with_ingestao=False), job_config=job_config).result()
    # Strip FIRST, then keep only non-empty codes: a whitespace-only codigo_produto
    # (' ') is truthy BEFORE stripping, so a naive `if row[...]` would let it survive
    # as '' — inflating the resolved count against the safety cap and injecting an empty
    # token into the SIDRA URL (…/c289/3405,,3450). "No invisible filtering."
    return [c for row in rows if (c := str(row["codigo_produto"]).strip())]


def _emit(banco: str, sidra_tabela: str | None, *, resolved: int, used: str) -> None:
    """Observability breadcrumb so the monitor shows which source drove a run."""
    observability.emit(
        "catalog_resolve",
        banco=banco,
        sidra_tabela=sidra_tabela,
        resolved=resolved,
        used=used,
    )
