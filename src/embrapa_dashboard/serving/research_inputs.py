"""Shared infrastructure for researcher-authored inputs persisted to the
``research_inputs`` BigQuery dataset.

This is the NEUTRAL layer common to BOTH researcher-facing features, so neither
"owns" the shared plumbing:
  * **Curadoria** (catalog — what enters/exits the dashboard): ``serving/curation.py``.
  * **Engenharia de Atributos** (derived columns from researcher input):
    ``serving/attribute_engineering.py`` (the per-code industrialization +
    customs×flow market-nature writers; currently FROZEN).

It owns the cross-cutting primitives: BigQuery client resolution, the
append-only idempotency helpers (``change_id``), the free-text length caps, the
attribute editor ALLOWLIST table, and the operator-editable banco-metadata override table.
Schemas are always EXPLICIT — autodetect drifts silently across runs.
"""

from __future__ import annotations

import logging
import uuid

from google.cloud import bigquery

from embrapa_dashboard.config import Settings, get_settings
from embrapa_dashboard.gcp.bigquery import ensure_dataset
from embrapa_dashboard.gcp.clients import resolve_bq_client
from embrapa_dashboard.serving import sql as sqlbuild

logger = logging.getLogger(__name__)

# Free-text length caps. Open-vocabulary fields (an industrialization level / note
# / market label) are intentionally NOT allowlisted — a researcher may coin
# arbitrary labels (an allowlist would break that UX). These caps are a cheap
# guard against an absurdly large value (a runaway paste / malformed client)
# bloating an immutable audit row, not a content restriction.
MAX_STAGE_LEN = 200
MAX_NOTE_LEN = 2000
# A client idempotency key (change_id) is normally a 32-char uuid hex; 128 is generous
# headroom that still caps a pathologically long value before it is stored as the audit key.
MAX_CHANGE_ID_LEN = 128

# The attribute editor ALLOWLIST — who may POST an edit (authorization, distinct from IAP
# authentication). Console-managed: add/remove an attribute editor by INSERT/DELETE here, no
# redeploy. Empty/absent table → no allowlist (any IAP-authenticated caller may write).
ATTRIBUTE_EDITORS_SCHEMA = [
    bigquery.SchemaField("email", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("added_by", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("added_at", "TIMESTAMP", mode="NULLABLE"),
]

# Sparse per-banco metadata overrides (one row per banco the operator has touched).
# Every override column is NULLABLE — a NULL means "keep the registry default".
BANCO_METADATA_SCHEMA = [
    bigquery.SchemaField("banco_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("maturity", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("maturity_note", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("maturity_date", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("cobertura_years", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("cobertura_atualizacao", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("cobertura_granularidade", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("updated_by", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
]


def _bq_client(settings: Settings) -> bigquery.Client:
    return resolve_bq_client(settings)


def ensure_attribute_editors_table(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Create the attribute editor allowlist table if missing; return its FQN. Idempotent.

    Tiny (one row per attribute editor), so no clustering. Manage rows in the BigQuery
    Console (or via SQL) to control who may curate — no redeploy needed.
    """
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = sqlbuild.table_ref(
        cfg, "bq_research_inputs_dataset", cfg.bq_attribute_editors_table
    )
    ensure_dataset(bq, f"{cfg.gcp_project_id}.{cfg.bq_research_inputs_dataset}", cfg.bq_location)
    bq.create_table(bigquery.Table(table_fqn, schema=ATTRIBUTE_EDITORS_SCHEMA), exists_ok=True)
    logger.info("Attribute editors allowlist table ready at %s", table_fqn)
    return table_fqn


def add_attribute_editor(
    email: str,
    *,
    added_by: str = "cli",
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Authorize ``email`` to curate (attribute engineering) — append a row. Idempotent by
    effect (the allowlist read DISTINCTs). Returns the normalized email. Backs
    ``embrapa attribute-editors add`` (the no-Console alternative)."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = ensure_attribute_editors_table(cfg, bq)
    email_norm = (email or "").strip().lower()
    if not email_norm:
        raise ValueError("email is required.")
    sql = (
        f"insert into `{table_fqn}` (email, added_by, added_at) "
        "values (@email, @added_by, current_timestamp())"
    )
    p = bigquery.ScalarQueryParameter
    params = [p("email", "STRING", email_norm), p("added_by", "STRING", added_by)]
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    # A newly-added editor should be able to curate immediately, not after the TTL.
    invalidate_attribute_editors_cache()
    logger.info("Attribute editor authorized: %s (by %s)", email_norm, added_by)
    return email_norm


def remove_attribute_editor(
    email: str,
    *,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> int:
    """De-authorize ``email`` (delete matching rows, case-insensitive). Returns the number
    of rows removed. Backs ``embrapa attribute-editors remove``."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = ensure_attribute_editors_table(cfg, bq)
    email_norm = (email or "").strip().lower()
    sql = f"delete from `{table_fqn}` where lower(trim(email)) = @email"
    params = [bigquery.ScalarQueryParameter("email", "STRING", email_norm)]
    job = bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    # Revocation must take effect at once — drop the memoized allowlist so the removed
    # editor cannot keep writing for the cache-TTL window.
    invalidate_attribute_editors_cache()
    return int(getattr(job, "num_dml_affected_rows", 0) or 0)


def invalidate_attribute_editors_cache() -> None:
    """Drop the cached attribute-editor allowlist so an add/remove takes effect IMMEDIATELY,
    not after the ~30s classification-cache TTL — REVOCATION must remove write access at
    once. Best-effort. Lazy import to avoid any serving-module import cycle."""
    try:
        from embrapa_dashboard.serving import gateway
        from embrapa_dashboard.serving.cache import cache

        cache.delete_memoized(gateway.fetch_attribute_editors)
    except Exception as exc:  # pragma: no cover - cache unbound / backend down
        logger.warning("Could not invalidate attribute-editors cache: %s", exc)


def ensure_banco_metadata_table(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Create the operator-editable banco-metadata override table if missing.

    Idempotent; returns its FQN. Tiny (one row per overridden banco), so no
    clustering. Manage rows in the BigQuery Console (or via SQL) to flip a banco's
    maturity / note / coverage with no redeploy — e.g.::

        MERGE `<project>.research_inputs.banco_metadata` t
        USING (SELECT 'un_comtrade' banco_id, 'estavel' maturity) s
        ON t.banco_id = s.banco_id
        WHEN MATCHED THEN UPDATE SET maturity = s.maturity, updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (banco_id, maturity, updated_at)
            VALUES (s.banco_id, s.maturity, CURRENT_TIMESTAMP());

    ``maturity_note`` REPLACES the stage's standard caveat text for that banco (it is
    not appended to it), so it must carry a caveat true of THAT banco — never a
    description of what the banco covers, which belongs in the SPA registry. Pasted
    here, such a description silently displaces "Disponível para testes e validações,
    resultados podem mudar." for every reader. See docs/operations_runbook.md
    § "Changing a banco's maturity / note / coverage".
    """
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = sqlbuild.table_ref(cfg, "bq_research_inputs_dataset", cfg.bq_banco_metadata_table)
    ensure_dataset(bq, f"{cfg.gcp_project_id}.{cfg.bq_research_inputs_dataset}", cfg.bq_location)
    bq.create_table(bigquery.Table(table_fqn, schema=BANCO_METADATA_SCHEMA), exists_ok=True)
    logger.info("Banco metadata override table ready at %s", table_fqn)
    return table_fqn


def _resolve_change_id(change_id: str | None) -> tuple[str, bool]:
    """Return ``(change_id, client_supplied)``. A non-empty client value is the
    IDEMPOTENCY KEY (a retried/double-clicked save reuses it); when absent we mint
    a fresh uuid (which can never pre-exist, so it needs no dedupe check)."""
    cleaned = (change_id or "").strip()
    if len(cleaned) > MAX_CHANGE_ID_LEN:
        raise ValueError(
            f"O identificador de alteração (change_id) excede {MAX_CHANGE_ID_LEN} caracteres."
        )
    return (cleaned, True) if cleaned else (uuid.uuid4().hex, False)


def _change_id_seen(bq: bigquery.Client, table_fqn: str, change_id: str) -> bool:
    """True when a row with this client-supplied ``change_id`` already exists in
    the log — the dedupe guard that makes a retried write a no-op. The lookup is a
    single-key scan on a clustered table (cheap). NOTE: this is a best-effort
    SELECT-then-INSERT, not a transaction — two near-simultaneous retries on
    DIFFERENT instances could still both insert. That's acceptable: both rows are
    byte-identical and the SCD2 view collapses them by latest edit, so the worst
    case is one redundant audit row, never a wrong current value."""
    sql = f"select 1 from `{table_fqn}` where change_id = @change_id limit 1"
    params = [bigquery.ScalarQueryParameter("change_id", "STRING", change_id)]
    job = bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    return any(True for _ in job.result())


class ChangeIdConflictError(Exception):
    """A client reused an idempotency ``change_id`` for a DIFFERENT logical write — the row
    already stored under that change_id has a different natural key (or active state) than the
    retried request, so replaying it would echo an UNRELATED prior row. The webapi maps this to
    HTTP 409 Conflict (distinct from the ValueError->400 validation path) so the caller
    regenerates the key instead of silently getting back the wrong row. An attribute-only
    divergence under the SAME key is deliberately NOT a conflict — a stable-change_id re-seed
    (``seed_catalog_from_env``) relies on that staying a benign idempotent no-op."""


def ensure_no_change_id_conflict(
    stored: dict | None, incoming: dict, fields: tuple[str, ...], *, entity: str
) -> None:
    """Guard an idempotent-retry replay: raise ``ChangeIdConflictError`` when the row already
    stored under this change_id disagrees with the retried request on any natural-key ``field``
    (never the mutable attributes — see the class docstring). ``stored is None`` (the row
    vanished) is a no-op; the caller then echoes the request body. ``entity`` is a pt-BR label
    for the message the SPA surfaces."""
    if stored is None:
        return
    if any(stored.get(f) != incoming.get(f) for f in fields):
        raise ChangeIdConflictError(
            f"O change_id informado já foi usado para outro {entity}. "
            "Gere uma nova alteração e tente novamente."
        )
