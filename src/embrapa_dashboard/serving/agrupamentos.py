"""Commodity groups (agrupamentos) — the first-class registry of commodity concepts.

A "group" (agrupamento) is the cross-source commodity concept that unifies raw codes
across bancos (e.g. "Madeira", "Castanha"). Historically a group was DERIVED — the
distinct set of ``agrupamento`` names carried on catalog entries — so it had no
independent lifecycle: no empty groups, no rename, no delete. This module promotes
groups to a FIRST-CLASS entity with their own append-only registry, keyed by
``group_id`` (== a catalog entry's ``agrupamento_id``): create (incl. EMPTY groups),
rename and delete (blocked while the group still has active members).

Reuses the shared append-log primitives in ``serving/research_inputs.py`` (IAP author
capture + latest-wins current state + optional change_id idempotency), exactly like
``serving/curation.py``. A RENAME re-stamps the denormalized ``agrupamento`` name on
the group's member catalog entries (so ``dim_produto_catalog`` and the crosswalk,
which read the entry's ``agrupamento``, need NO schema change). A DELETE is a tombstone
and is REJECTED while the group has active members — the researcher reassigns/removes
them first (never a silent cascade).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from google.api_core.exceptions import BadRequest, NotFound
from google.cloud import bigquery

from embrapa_dashboard.config import Settings, get_settings
from embrapa_dashboard.gcp.bigquery import ensure_dataset
from embrapa_dashboard.serving import curation, gateway
from embrapa_dashboard.serving import sql as sqlbuild
from embrapa_dashboard.serving.cache import cache
from embrapa_dashboard.serving.iap import author_email_from_headers
from embrapa_dashboard.serving.research_inputs import (
    MAX_NOTE_LEN,
    _bq_client,
    _change_id_seen,
    _resolve_change_id,
    ensure_no_change_id_conflict,
)

logger = logging.getLogger(__name__)

# Append-only groups registry. Explicit schema (autodetect drifts silently).
AGRUPAMENTO_LOG_SCHEMA = [
    bigquery.SchemaField("group_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("group_name", "STRING", mode="REQUIRED"),
    # active=false is a tombstone: the group was deleted (only ever when it had no
    # active members — a delete is rejected while members remain).
    bigquery.SchemaField("active", "BOOL", mode="REQUIRED"),
    bigquery.SchemaField("edited_by", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("edited_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("change_id", "STRING", mode="REQUIRED"),
]


def _group_log_ref(cfg: Settings) -> str:
    return sqlbuild.table_ref(cfg, "bq_research_inputs_dataset", cfg.bq_agrupamento_log_table)


def _catalog_log_ref(cfg: Settings) -> str:
    return sqlbuild.table_ref(cfg, "bq_research_inputs_dataset", cfg.bq_produto_catalog_log_table)


def ensure_agrupamento_log_table(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Create the append-only groups registry if missing (clustered by group_id).
    Idempotent — called on first write."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = _group_log_ref(cfg)
    ensure_dataset(bq, f"{cfg.gcp_project_id}.{cfg.bq_research_inputs_dataset}", cfg.bq_location)
    table = bigquery.Table(table_fqn, schema=AGRUPAMENTO_LOG_SCHEMA)
    table.clustering_fields = ["group_id"]
    bq.create_table(table, exists_ok=True)
    logger.info("Commodity-group registry ready at %s", table_fqn)
    return table_fqn


def _current_groups(bq: bigquery.Client, table_fqn: str) -> dict[str, str]:
    """Current active ``{group_id: group_name}`` (latest-wins). ``{}`` when the registry
    table doesn't exist yet."""
    sql = f"""
        select group_id, group_name from (
          select group_id, group_name, active, row_number() over (
            partition by group_id order by edited_at desc, change_id desc
          ) as _rn
          from `{table_fqn}`
        ) where _rn = 1 and active
    """
    try:
        return {r.group_id: r.group_name for r in bq.query(sql).result()}
    except NotFound:
        return {}


def _active_member_rows(bq: bigquery.Client, catalog_fqn: str, group_id: str) -> list:
    """Current ACTIVE catalog entries whose agrupamento_id == group_id (the group's
    members), with the fields needed to re-upsert them on a rename. ``[]`` when the
    catalog log doesn't exist yet.

    The ``agrupamento_id`` filter MUST be applied AFTER the latest-wins dedup, never
    inside the windowed subquery: ``agrupamento_id`` is a MUTABLE attribute (a product
    can be moved to another group, or removed via a tombstone whose agrupamento_id is
    NULL), not part of the ``(codigo_produto, banco)`` partition key. Pre-filtering it
    would rank only the rows that ever carried this group, so a stale row could win the
    partition and report a product that has since been moved out or removed as a current
    member — which a rename/delete would then silently re-stamp (reverting the move) or
    resurrect (undoing the removal). Dedup the full log first, THEN filter by the current
    state — the same pattern as ``_current_groups`` and ``gateway.fetch_agrupamentos``."""

    def _sql(cols: str) -> str:
        return f"""
            select {cols}
            from (
              select *, row_number() over (
                partition by codigo_produto, banco order by edited_at desc, change_id desc
              ) as _rn
              from `{catalog_fqn}`
            ) where _rn = 1 and active and agrupamento_id = @group_id
        """

    base_cols = "codigo_produto, banco, descricao_produto, ciclo_de_vida"
    params = [bigquery.ScalarQueryParameter("group_id", "STRING", group_id)]
    try:
        job = bq.query(
            _sql(f"{base_cols}, ingestao, visibilidade"),
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        )
        return list(job.result())
    except NotFound:
        return []
    except BadRequest:
        # The log table predates the two-axis columns. Re-read without them: the caller
        # reads the axes with getattr(..., None), so the writer falls back to its own
        # preservation. Without this branch a rename would 500 on a pre-split table.
        job = bq.query(_sql(base_cols), job_config=bigquery.QueryJobConfig(query_parameters=params))
        return list(job.result())


def record_group(
    group_name: str,
    headers: Mapping[str, str],
    *,
    group_id: str | None = None,
    change_id: str | None = None,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
    invalidate_cache: bool = True,
) -> dict:
    """Create a group (``group_id`` omitted → a NEW group, possibly empty) or RENAME an
    existing one (``group_id`` given). Create rejects a duplicate group_id; rename
    re-stamps the new name onto the group's member catalog entries so downstream reads
    (which use the entry's ``agrupamento``) stay consistent. IAP author + optional
    change_id idempotency. Raises ValueError (→ HTTP 400) on a bad/duplicate name."""
    cfg = settings or get_settings()
    group_name = (group_name or "").strip()
    if not group_name:
        raise ValueError("O nome do agrupamento é obrigatório.")
    if len(group_name) > MAX_NOTE_LEN:
        raise ValueError(f"O nome do agrupamento excede {MAX_NOTE_LEN} caracteres.")

    edited_by = author_email_from_headers(
        headers, dev_fallback=cfg.dev_author, audience=cfg.iap_audience
    )
    change_id, supplied = _resolve_change_id(change_id)
    bq = client or _bq_client(cfg)
    table_fqn = _group_log_ref(cfg)
    ensure_agrupamento_log_table(cfg, bq)

    current = _current_groups(bq, table_fqn)
    renaming = group_id is not None
    group_id = (group_id or curation._slug(group_name)).strip() or None
    if not group_id:
        raise ValueError(
            f"O nome {group_name!r} não gera um identificador válido — use ao menos "
            "uma letra ou número (acentos e símbolos são ignorados)."
        )

    # Dedup FIRST (before the existence validations): a retried CREATE whose first attempt
    # already landed would otherwise fail the "já existe" check instead of returning the
    # documented deduped no-op — the change_id the seam plumbs must make the retry idempotent.
    if supplied and _change_id_seen(bq, table_fqn, change_id):
        stored = _group_row_for_change_id(bq, table_fqn, change_id)
        # A change_id reused for a DIFFERENT group (or a create/delete flip) is not a safe
        # replay → 409 instead of echoing an unrelated row. An attribute-only divergence
        # (e.g. a re-run that only changes the name) stays a benign no-op.
        ensure_no_change_id_conflict(
            stored,
            {"group_id": group_id, "active": True},
            ("group_id", "active"),
            entity="agrupamento",
        )
        # A RENAME is a COMPOSITE op (registry-row insert + member re-stamp). The re-stamp is
        # idempotent, so on a retry re-run it to CONVERGE — the first attempt may have failed
        # after the row insert but before/mid re-stamp, leaving members with the old name. Use
        # the STORED name (what the registry row holds), not the request body.
        if renaming:
            _restamp_members(
                bq, cfg, headers, group_id, stored["group_name"] if stored else group_name
            )
            if invalidate_cache:
                invalidate_group_cache()
        # Return the STORED row (read-after-write), not the retried request body.
        if stored is not None:
            return stored
        return _group_row(group_id, group_name, True, edited_by, change_id, deduped=True)

    if renaming and group_id not in current:
        raise ValueError(f"O agrupamento {group_id!r} não existe (nada a renomear).")
    if not renaming and group_id in current:
        raise ValueError(f"O agrupamento {group_name!r} já existe.")
    # Reject a RENAME that would collide with ANOTHER active group's name. The create path
    # already blocks a duplicate (group_id == slug(name)), but a rename keeps the old id, so
    # without this two active groups could share a name — which the UI (labels groups by name)
    # and ``catalog_worklist.by_agrupamento`` (keyed by name) would silently MERGE into one.
    _name_key = group_name.strip().lower()
    if any(
        gid != group_id and gname.strip().lower() == _name_key for gid, gname in current.items()
    ):
        raise ValueError(f"Já existe um agrupamento chamado {group_name!r}.")

    _insert_group_row(bq, table_fqn, group_id, group_name, True, edited_by, change_id)
    logger.info("Group: %s -> %r by %s", group_id, group_name, edited_by)

    # RENAME: re-stamp the new name onto the group's member catalog entries.
    if renaming:
        _restamp_members(bq, cfg, headers, group_id, group_name)

    if invalidate_cache:
        invalidate_group_cache()
    return _group_row(group_id, group_name, True, edited_by, change_id, deduped=False)


def delete_group(
    group_id: str,
    headers: Mapping[str, str],
    *,
    change_id: str | None = None,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
    invalidate_cache: bool = True,
) -> dict:
    """Tombstone (soft-delete) a group. REJECTED while the group still has active
    catalog members — the researcher reassigns/removes them first (never a silent
    cascade that would orphan Gold data). Raises ValueError (→ HTTP 400)."""
    cfg = settings or get_settings()
    group_id = (group_id or "").strip()
    if not group_id:
        raise ValueError("group_id é obrigatório.")
    edited_by = author_email_from_headers(
        headers, dev_fallback=cfg.dev_author, audience=cfg.iap_audience
    )
    change_id, supplied = _resolve_change_id(change_id)
    bq = client or _bq_client(cfg)
    table_fqn = _group_log_ref(cfg)
    ensure_agrupamento_log_table(cfg, bq)

    # Dedup FIRST (before the state validations): a retried delete (the tombstone already
    # landed, the client re-POSTs with the SAME change_id) finds the group no longer in
    # `current`; without this the retry would fail "não existe (nada a excluir)" instead of
    # returning the documented deduped no-op — mirroring curation.remove_produto_catalog.
    if supplied and _change_id_seen(bq, table_fqn, change_id):
        stored = _group_row_for_change_id(bq, table_fqn, change_id)
        # A reused change_id whose stored row is a different group / not a delete is not a safe
        # replay → 409 instead of echoing an unrelated row.
        ensure_no_change_id_conflict(
            stored,
            {"group_id": group_id, "active": False},
            ("group_id", "active"),
            entity="agrupamento",
        )
        # Return the STORED row (its REAL name), not the group_id placeholder.
        if stored is not None:
            return stored
        return _group_row(group_id, group_id, False, edited_by, change_id, deduped=True)

    current = _current_groups(bq, table_fqn)
    if group_id not in current:
        raise ValueError(f"O agrupamento {group_id!r} não existe (nada a excluir).")
    members = _active_member_rows(bq, _catalog_log_ref(cfg), group_id)
    if members:
        raise ValueError(
            f"O agrupamento {current[group_id]!r} ainda tem {len(members)} produto(s) — "
            "reatribua ou remova antes de excluir o agrupamento."
        )

    name = current[group_id]
    _insert_group_row(bq, table_fqn, group_id, name, False, edited_by, change_id)
    logger.info("Group: %s -> deleted (tombstone) by %s", group_id, edited_by)
    if invalidate_cache:
        invalidate_group_cache()
    return _group_row(group_id, name, False, edited_by, change_id, deduped=False)


def _restamp_members(bq, cfg, headers, group_id, group_name) -> None:
    """Re-stamp the (denormalized) agrupamento name onto the group's ACTIVE member catalog
    entries — the entry's ``agrupamento`` is what ``dim_produto_catalog`` / the crosswalk
    read. Idempotent (``record_produto_catalog`` upserts latest-wins), so it is safe to
    re-run on an idempotent retry."""
    members = _active_member_rows(bq, _catalog_log_ref(cfg), group_id)
    for m in members:
        curation.record_produto_catalog(
            str(m.codigo_produto),
            m.banco,
            headers,
            agrupamento=group_name,
            descricao_produto=m.descricao_produto,
            ciclo_de_vida=m.ciclo_de_vida,
            # Forward the stored lifecycle axes. The writer would PRESERVE them anyway
            # when omitted, but only by issuing an extra read per member — and this row
            # was already fetched. On a large agrupamento that is one avoided BigQuery
            # round-trip per member.
            ingestao=getattr(m, "ingestao", None),
            visibilidade=getattr(m, "visibilidade", None),
            agrupamento_id=group_id,
            settings=cfg,
            client=bq,
            invalidate_cache=False,
        )
    if members:
        logger.info("Group %s rename re-tagged %d member(s)", group_id, len(members))


def _insert_group_row(bq, table_fqn, group_id, group_name, active, edited_by, change_id) -> None:
    """Append one group-registry row with a server-side timestamp (parameterized DML)."""
    sql = f"""
        insert into `{table_fqn}`
            (group_id, group_name, active, edited_by, edited_at, change_id)
        values
            (@group_id, @group_name, @active, @edited_by, current_timestamp(), @change_id)
    """
    p = bigquery.ScalarQueryParameter
    params = [
        p("group_id", "STRING", group_id),
        p("group_name", "STRING", group_name),
        p("active", "BOOL", active),
        p("edited_by", "STRING", edited_by),
        p("change_id", "STRING", change_id),
    ]
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


def _group_row(group_id, group_name, active, edited_by, change_id, *, deduped) -> dict:
    """The written/echoed group row dict (shared by the write + dedup paths)."""
    return {
        "group_id": group_id,
        "group_name": group_name,
        "active": active,
        "edited_by": edited_by,
        "change_id": change_id,
        "deduped": deduped,
    }


def _group_row_for_change_id(bq, table_fqn: str, change_id: str) -> dict | None:
    """The STORED group-registry row for ``change_id`` (unique per write). Echoes the
    ORIGINAL persisted values on an idempotent-retry dedup (read-after-write: return what
    was STORED, not the possibly-different request body). None if not found. Mirrors
    ``curation._row_for_change_id``."""
    sql = f"""
        select group_id, group_name, active, edited_by
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
    return _group_row(
        r["group_id"], r["group_name"], bool(r["active"]), r["edited_by"], change_id, deduped=True
    )


def invalidate_group_cache() -> None:
    """Drop the cached group + catalog reads (a rename changes member names) — best-effort."""
    for fn in (gateway.fetch_agrupamentos, gateway.fetch_produto_catalog):
        try:
            cache.delete_memoized(fn)
        except Exception as exc:  # pragma: no cover - cache unbound / backend down
            logger.warning("Could not invalidate commodity-group cache: %s", exc)
