"""Engenharia de Atributos = the construction of NEW DERIVED COLUMNS on the data from
researcher input. This is what the codebase historically (mis)labelled "Curadoria";
the name "Curadoria" is now reserved for the catalog (what enters/exits the
dashboard — ``serving/curation.py``). The append-only writers here build TWO
researcher-editable derived attributes:
  * per-CODE industrialization (``record_code_industrialization`` →
    ``research_inputs.code_industrialization_log``), the editor's primary grain; and
  * (customs procedure × flow) market-nature (``record_flow_market`` →
    ``research_inputs.flow_market_log``) — reverted from the comtrade_market_nature seed
    (v1.9.0) back to the editable matrix.
The Gold tables are never touched; the Type-2 history (valid_from / valid_to /
is_current) is derived downstream by the SCD2 dbt views (gated by ``enable_curation``).

Two side effects matter:
  1. The author is taken from the IAP-verified header (``edited_by``), never from
     the dashboard's service account — every edit is attributable to a person.
  2. After the insert, the relevant live-classification cache is invalidated so
     the next read reflects the new value immediately (the marts are untouched, so
     their caches are left alone).

The cross-cutting primitives (BigQuery client, idempotency, length caps) live in
``serving/research_inputs.py`` — the shared layer common to this feature and the
catalog Curadoria.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from embrapa_dashboard.config import Settings, get_settings
from embrapa_dashboard.gcp.bigquery import ensure_dataset
from embrapa_dashboard.serving import gateway
from embrapa_dashboard.serving import sql as sqlbuild
from embrapa_dashboard.serving.cache import cache
from embrapa_dashboard.serving.iap import author_email_from_headers
from embrapa_dashboard.serving.research_inputs import (
    MAX_NOTE_LEN,
    MAX_STAGE_LEN,
    _bq_client,
    _change_id_seen,
    _resolve_change_id,
    ensure_no_change_id_conflict,
)

logger = logging.getLogger(__name__)

# The per-CODE industrialization log — the active grain. Explicit schema —
# autodetect is never used (it drifts silently across runs).
CODE_INDUSTRIALIZATION_LOG_SCHEMA = [
    bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("code", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("industrialization_level", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("note", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("edited_by", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("edited_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("change_id", "STRING", mode="REQUIRED"),
    # Parte da IDENTIDADE do produto desde que a chave virou (banco, tabela, código).
    # NULLABLE: os bancos de uma tabela só não a preenchem, e o `ifnull` do
    # `sql.CHAVE_*` a colapsa na sentinela. Sem ela aqui, uma instalação NOVA criaria
    # o log sem a coluna e o particionamento quebraria — furo que um teste pegou.
    bigquery.SchemaField("sidra_tabela", "STRING", mode="NULLABLE"),
]

# The (customs procedure × flow) → economic-purpose market log. A `market` of ''
# clears the pair (latest-wins on read). Backs dim_flow_market_scd2 → the
# serving_comtrade_annual.market_nature column (the "Tipo de mercado" filter + the
# "Finalidade econômica" analysis).
FLOW_MARKET_LOG_SCHEMA = [
    bigquery.SchemaField("customs_code", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("flow_code", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("market", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("edited_by", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("edited_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("change_id", "STRING", mode="REQUIRED"),
]


# ── Per-CODE industrialization log (the active grain) ─────────────────────────
def ensure_code_industrialization_log_table(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Create the per-code industrialization log dataset + table if missing.

    Follows the house auto-create pattern (like the Bronze ensure_* helpers) so a
    fresh project needs no manual DDL, clustered by (source, code) so the SCD2
    window scans one code's edits cheaply. Idempotent.
    """
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = sqlbuild.table_ref(
        cfg, "bq_research_inputs_dataset", cfg.bq_code_industrialization_log_table
    )
    ensure_dataset(bq, f"{cfg.gcp_project_id}.{cfg.bq_research_inputs_dataset}", cfg.bq_location)
    table = bigquery.Table(table_fqn, schema=CODE_INDUSTRIALIZATION_LOG_SCHEMA)
    table.clustering_fields = ["source", "code"]
    bq.create_table(table, exists_ok=True)
    logger.info("Code-industrialization log ready at %s", table_fqn)
    return table_fqn


def _validate_code_edit(source: str, code: str, level: str, note: str | None) -> None:
    """Validate a per-code edit: required keys present and free text within caps.

    ``industrialization_level`` is open-vocabulary (the UI offers the 8-level
    Commodity → Manufaturado scale, but an allowlist would break a future finer
    scheme); the cap is only a sanity bound on the immutable audit row.
    """
    if not source or not code or not level:
        raise ValueError("source, code e industrialization_level são obrigatórios.")
    # Cap the key fields too (both reach the INSERT) — a slug/code is short, MAX_STAGE_LEN
    # is generous headroom that still rejects a pathologically long value.
    if len(source) > MAX_STAGE_LEN:
        raise ValueError(f"source excede {MAX_STAGE_LEN} caracteres.")
    if len(code) > MAX_STAGE_LEN:
        raise ValueError(f"code excede {MAX_STAGE_LEN} caracteres.")
    if len(level) > MAX_STAGE_LEN:
        raise ValueError(f"industrialization_level excede {MAX_STAGE_LEN} caracteres.")
    if note is not None and len(note) > MAX_NOTE_LEN:
        raise ValueError(f"note excede {MAX_NOTE_LEN} caracteres.")


def record_code_industrialization(
    source: str,
    code: str,
    industrialization_level: str,
    headers: Mapping[str, str],
    *,
    note: str | None = None,
    change_id: str | None = None,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
    invalidate_cache: bool = True,
) -> dict:
    """Append one per-code industrialization edit and invalidate its cache.

    ``headers`` is the inbound request's headers (``flask.request.headers`` in a
    webapi route); the author email is read from the IAP-verified header (never the
    service account). Parameterized DML gives read-after-write consistency for the
    SCD2 view; ``change_id`` is an optional client-supplied idempotency key — a
    retried/double-clicked save reusing it is a no-op. Keyed by (source, code) →
    industrialization_level. Returns the row as written. Raises on empty inputs,
    an over-length level/note, or a missing author with no dev fallback.
    """
    cfg = settings or get_settings()
    source = (source or "").strip()
    code = (code or "").strip()
    industrialization_level = (industrialization_level or "").strip()
    note = note.strip() if note else note
    _validate_code_edit(source, code, industrialization_level, note)

    edited_by = author_email_from_headers(
        headers,
        dev_fallback=cfg.dev_author,
        audience=cfg.iap_audience,
    )
    change_id, supplied = _resolve_change_id(change_id)
    bq = client or _bq_client(cfg)
    table_fqn = sqlbuild.table_ref(
        cfg, "bq_research_inputs_dataset", cfg.bq_code_industrialization_log_table
    )
    # Self-heal the log table on a fresh project (house auto-create pattern).
    ensure_code_industrialization_log_table(cfg, bq)

    if supplied and _change_id_seen(bq, table_fqn, change_id):
        logger.info(
            "Curation(code): duplicate change_id %s ignored (%s:%s)", change_id, source, code
        )
        stored = _code_row_for_change_id(bq, table_fqn, change_id)
        # A change_id reused for a DIFFERENT (source, code) is not a safe replay → 409, not
        # the wrong prior row. An attribute-only divergence (level/note) stays a benign no-op.
        ensure_no_change_id_conflict(
            stored,
            {"source": source, "code": code},
            ("source", "code"),
            entity="código",
        )
        # Return the STORED row (read-after-write), not the retried request body.
        if stored is not None:
            return stored
        return {
            "source": source,
            "code": code,
            "industrialization_level": industrialization_level,
            "note": note,
            "edited_by": edited_by,
            "change_id": change_id,
            "deduped": True,
        }

    # A tabela SIDRA faz parte da CHAVE de um produto. Sem ela, a classificação cai na
    # sentinela `sql.SEM_TABELA` — uma identidade à parte — e a dim SCD2, que particiona
    # pela chave de 3 colunas, abriria uma linhagem paralela: as versões anteriores do
    # MESMO produto ficariam órfãs das novas, sem erro nenhum. O catálogo é a fonte de
    # verdade da identidade, então a tag vem dele.
    from embrapa_dashboard.serving.curation import tabela_do_produto

    sidra_tabela = tabela_do_produto(source, code, settings=cfg, client=bq)
    sql = f"""
        insert into `{table_fqn}`
            (source, code, industrialization_level, note, edited_by, edited_at, change_id,
             sidra_tabela)
        values
            (@source, @code, @level, @note, @edited_by, current_timestamp(), @change_id,
             @sidra_tabela)
    """
    params = [
        bigquery.ScalarQueryParameter("source", "STRING", source),
        bigquery.ScalarQueryParameter("code", "STRING", code),
        bigquery.ScalarQueryParameter("sidra_tabela", "STRING", sidra_tabela),
        bigquery.ScalarQueryParameter("level", "STRING", industrialization_level),
        bigquery.ScalarQueryParameter("note", "STRING", note),
        bigquery.ScalarQueryParameter("edited_by", "STRING", edited_by),
        bigquery.ScalarQueryParameter("change_id", "STRING", change_id),
    ]
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    logger.info(
        "Curation(code): %s:%s -> %s by %s", source, code, industrialization_level, edited_by
    )

    if invalidate_cache:
        invalidate_code_industrialization_cache()

    return {
        "source": source,
        "code": code,
        "industrialization_level": industrialization_level,
        "note": note,
        "edited_by": edited_by,
        "change_id": change_id,
        "deduped": False,
    }


def invalidate_code_industrialization_cache() -> None:
    """Drop the cached per-code classification read so the next query is fresh.

    Best-effort: a no-op if the cache is not bound to an app (e.g. a CLI-driven
    write outside the webapi server). With the per-instance ``SimpleCache`` this
    clears only the current process — making the edit instant on the writing
    instance; other instances converge within the short classification TTL
    (``CACHE_CLASSIFICATION_TIMEOUT``). That bound is what lets multi-instance
    Cloud Run run on ``SimpleCache`` without ``RedisCache`` (see ``serving.cache``).
    """
    try:
        # flask-caching's delete_memoized bumps a per-function VERSION sentinel
        # rather than deleting each cached entry: the next read computes a fresh
        # key and misses, so subsequent reads see new data immediately. The old
        # entries are orphaned (unreferenced) and simply expire at their TTL.
        cache.delete_memoized(gateway.fetch_current_code_industrialization)
    except Exception as exc:  # pragma: no cover - cache unbound / backend down
        logger.warning("Could not invalidate code-industrialization cache: %s", exc)


# ── Flow-market log (customs procedure × flow → economic-purpose market) ──────
def ensure_flow_market_log_table(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Create the flow-market log dataset + table if missing (clustered by the
    pair). Idempotent — called on first write. Mirrors
    :func:`ensure_code_industrialization_log_table`."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = sqlbuild.table_ref(cfg, "bq_research_inputs_dataset", cfg.bq_flow_market_log_table)
    ensure_dataset(bq, f"{cfg.gcp_project_id}.{cfg.bq_research_inputs_dataset}", cfg.bq_location)
    table = bigquery.Table(table_fqn, schema=FLOW_MARKET_LOG_SCHEMA)
    table.clustering_fields = ["customs_code", "flow_code"]
    bq.create_table(table, exists_ok=True)
    logger.info("Flow-market log ready at %s", table_fqn)
    return table_fqn


def _validate_flow_market_edit(
    customs_code: str, flow_code: str, market: str
) -> tuple[str, str, str]:
    """Strip + validate a flow-market edit, returning the normalized triple.

    ``market`` is open-vocabulary (the UI offers consumo/processamento, and '' clears
    the pair); the cap is only a sanity bound on the immutable audit row."""
    customs_code = (customs_code or "").strip()
    flow_code = (flow_code or "").strip()
    market = (market or "").strip()
    if not customs_code or not flow_code:
        raise ValueError("customs_code e flow_code são obrigatórios.")
    # Cap the key fields too (both reach the INSERT) — a code is short, MAX_STAGE_LEN is
    # generous headroom that still rejects a pathologically long value.
    if len(customs_code) > MAX_STAGE_LEN:
        raise ValueError(f"customs_code excede {MAX_STAGE_LEN} caracteres.")
    if len(flow_code) > MAX_STAGE_LEN:
        raise ValueError(f"flow_code excede {MAX_STAGE_LEN} caracteres.")
    if len(market) > MAX_STAGE_LEN:
        raise ValueError(f"market excede {MAX_STAGE_LEN} caracteres.")
    return customs_code, flow_code, market


def record_flow_market(
    customs_code: str,
    flow_code: str,
    market: str,
    headers: Mapping[str, str],
    *,
    change_id: str | None = None,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
    invalidate_cache: bool = True,
) -> dict:
    """Append one (customs_code, flow_code) → market edit (market='' clears it).
    Auto-creates the log on first write. IAP author capture + read-after-write +
    optional ``change_id`` idempotency key, mirroring
    :func:`record_code_industrialization`."""
    cfg = settings or get_settings()
    customs_code, flow_code, market = _validate_flow_market_edit(customs_code, flow_code, market)

    edited_by = author_email_from_headers(
        headers,
        dev_fallback=cfg.dev_author,
        audience=cfg.iap_audience,
    )
    change_id, supplied = _resolve_change_id(change_id)
    bq = client or _bq_client(cfg)
    # Self-heal the log table on a fresh project (house auto-create pattern).
    ensure_flow_market_log_table(cfg, bq)
    table_fqn = sqlbuild.table_ref(cfg, "bq_research_inputs_dataset", cfg.bq_flow_market_log_table)

    if supplied and _change_id_seen(bq, table_fqn, change_id):
        logger.info(
            "Curation(flow): duplicate change_id %s ignored (%s×%s)",
            change_id,
            customs_code,
            flow_code,
        )
        stored = _flow_market_row_for_change_id(bq, table_fqn, change_id)
        # A change_id reused for a DIFFERENT (customs_code, flow_code) → 409, not the wrong row.
        ensure_no_change_id_conflict(
            stored,
            {"customs_code": customs_code, "flow_code": flow_code},
            ("customs_code", "flow_code"),
            entity="par regime×fluxo",
        )
        if stored is not None:
            return stored
        return _flow_market_row(customs_code, flow_code, market, edited_by, change_id, deduped=True)

    sql = f"""
        insert into `{table_fqn}`
            (customs_code, flow_code, market, edited_by, edited_at, change_id)
        values
            (@customs_code, @flow_code, @market, @edited_by, current_timestamp(), @change_id)
    """
    params = [
        bigquery.ScalarQueryParameter("customs_code", "STRING", customs_code),
        bigquery.ScalarQueryParameter("flow_code", "STRING", flow_code),
        bigquery.ScalarQueryParameter("market", "STRING", market),
        bigquery.ScalarQueryParameter("edited_by", "STRING", edited_by),
        bigquery.ScalarQueryParameter("change_id", "STRING", change_id),
    ]
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    logger.info("Curation(flow): %s×%s -> %s by %s", customs_code, flow_code, market, edited_by)

    if invalidate_cache:
        invalidate_flow_market_cache()

    return _flow_market_row(customs_code, flow_code, market, edited_by, change_id, deduped=False)


def _flow_market_row(
    customs_code: str,
    flow_code: str,
    market: str,
    edited_by: str,
    change_id: str,
    *,
    deduped: bool,
) -> dict:
    """The written/echoed flow-market row dict (shared by the write + dedup paths)."""
    return {
        "customs_code": customs_code,
        "flow_code": flow_code,
        "market": market,
        "edited_by": edited_by,
        "change_id": change_id,
        "deduped": deduped,
    }


def _code_row_for_change_id(bq, table_fqn: str, change_id: str) -> dict | None:
    """The STORED per-code industrialization row for ``change_id`` (unique per write). Echoes
    the ORIGINAL persisted values on an idempotent-retry dedup (read-after-write). None if not
    found. Mirrors ``curation._row_for_change_id``."""
    sql = f"""
        select source, code, industrialization_level, note, edited_by
        from `{table_fqn}`
        where change_id = @change_id
        order by edited_at desc
        limit 1
    """
    params = [bigquery.ScalarQueryParameter("change_id", "STRING", change_id)]
    rows = list(bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result())
    if not rows:
        return None
    r = rows[0]
    return {
        "source": r["source"],
        "code": r["code"],
        "industrialization_level": r["industrialization_level"],
        "note": r["note"],
        "edited_by": r["edited_by"],
        "change_id": change_id,
        "deduped": True,
    }


def _flow_market_row_for_change_id(bq, table_fqn: str, change_id: str) -> dict | None:
    """The STORED flow-market row for ``change_id`` (unique per write). Echoes the ORIGINAL
    persisted values on an idempotent-retry dedup (read-after-write). None if not found."""
    sql = f"""
        select customs_code, flow_code, market, edited_by
        from `{table_fqn}`
        where change_id = @change_id
        order by edited_at desc
        limit 1
    """
    params = [bigquery.ScalarQueryParameter("change_id", "STRING", change_id)]
    rows = list(bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result())
    if not rows:
        return None
    r = rows[0]
    return _flow_market_row(
        r["customs_code"], r["flow_code"], r["market"], r["edited_by"], change_id, deduped=True
    )


def invalidate_flow_market_cache() -> None:
    """Drop the cached current flow-market mapping so the next read is fresh
    (best-effort; mirrors :func:`invalidate_code_industrialization_cache`)."""
    try:
        cache.delete_memoized(gateway.fetch_current_flow_market)
    except Exception as exc:  # pragma: no cover - cache unbound / backend down
        logger.warning("Could not invalidate flow-market cache: %s", exc)


# The 25 (customs procedure × flow) → market pairs from the retired
# comtrade_market_nature seed (Contrato de Dados, "Tipos de Mercado"). Embedded here
# so the cutover backfill can seed the append-log even though the CSV was deleted in the
# same change. `flow` is the NORMALIZED token (matching serving_comtrade_annual.flow).
_SEED_FLOW_MARKET_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("C01", "import", "consumo"),
    ("C02", "re-import", "consumo"),
    ("C03", "export", "consumo"),
    ("C03", "national-export", "consumo"),
    ("C04", "export", "processamento"),
    ("C04", "foreign-import", "processamento"),
    ("C04", "import", "processamento"),
    ("C04", "re-export", "processamento"),
    ("C05", "import", "processamento"),
    ("C05", "national-export", "processamento"),
    ("C06", "import", "processamento"),
    ("C06", "import-inward-processing", "processamento"),
    ("C07", "export", "processamento"),
    ("C07", "import-outward-processing", "consumo"),
    ("C08", "import", "processamento"),
    ("C08", "import-inward-processing", "processamento"),
    ("C09", "import", "processamento"),
    ("C12", "export", "consumo"),
    ("C12", "import", "consumo"),
    ("C13", "export", "consumo"),
    ("C13", "import", "consumo"),
    ("C14", "export", "consumo"),
    ("C14", "import", "consumo"),
    ("C15", "export", "consumo"),
    ("C15", "import", "consumo"),
)


def seed_flow_market_from_seed(
    headers: Mapping[str, str],
    *,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> dict:
    """One-shot cutover backfill: append the retired comtrade_market_nature seed's
    pairs into the flow-market log so the reverted matrix + the mart's market_nature
    start populated (nothing regresses). Idempotent — a pair already classified with
    the SAME market is skipped (so a re-run is a no-op). Mirrors
    ``serving.curation.seed_catalog_from_env``; the author defaults to the IAP header
    (a ``system:flow-market-seed`` fallback for a headless CLI run).

    Returns ``{"seeded": n, "skipped": n, "total": 25}``.
    """
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    ensure_flow_market_log_table(cfg, bq)

    # Current classifications (latest-wins per pair) already in the log — skip a pair
    # that is already set to the same market so a re-run appends nothing.
    existing: dict[tuple[str, str], str] = {}
    try:
        df = gateway.fetch_current_flow_market()
        if df is not None and not df.empty:
            existing = {(r.customs_code, r.flow_code): r.market for r in df.itertuples()}
    except NotFound as exc:  # pragma: no cover - view absent on a cold project
        # ONLY the genuine "view not built yet" (NotFound). A broad except would also eat a
        # TRANSIENT BQ fault → existing={} → the idempotency guard fails open and the seed
        # RE-APPENDS every pair into the append-only flow_market_log. Any other error propagates.
        logger.info("seed_flow_market: no current mapping yet (%s)", exc)

    seeded = skipped = 0
    for customs_code, flow_code, market in _SEED_FLOW_MARKET_PAIRS:
        if existing.get((customs_code, flow_code)) == market:
            skipped += 1
            continue
        record_flow_market(
            customs_code,
            flow_code,
            market,
            headers,
            settings=cfg,
            client=bq,
            invalidate_cache=False,  # one final invalidation below, not per-row
        )
        seeded += 1
    invalidate_flow_market_cache()
    logger.info(
        "seed_flow_market: %d seeded, %d skipped (of %d)",
        seeded,
        skipped,
        len(_SEED_FLOW_MARKET_PAIRS),
    )
    return {"seeded": seeded, "skipped": skipped, "total": len(_SEED_FLOW_MARKET_PAIRS)}
