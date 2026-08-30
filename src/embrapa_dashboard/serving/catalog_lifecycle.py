"""Curadoria lifecycle — orphan → Descontinuado (NON-destructive).

When a commodity is removed from the catalog (a tombstone, active=false) its already
ingested Gold data does not vanish — it lingers, "órfão". This module detects that
transition and appends a ``descontinuado`` lifecycle event WITH a deletion warning —
but it NEVER deletes anything. The actual purge is a separate, human-gated, backup-first
operator action (the lead's decision #2): auto-detect + auto-mark + warn is automatic;
the delete waits for a person.

Detection is precise (see ``gateway.fetch_orphan_produtos``): only a REMOVAL that
leaves Gold data behind counts — not every uncataloged Gold code (the catalog is a
cross-source bridge, not a full registry; that diff would false-flag legitimate products).

Append-only log ``research_inputs.catalog_lifecycle_log`` (latest-wins per
(element_kind, banco, code)); the auto-mark is idempotent (a deterministic change_id per
element), so re-running it is a no-op. The author is a reserved SYSTEM identity, so the
audit row is honest about being machine-generated.
"""

from __future__ import annotations

import logging
import re

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from embrapa_dashboard.config import Settings, get_settings
from embrapa_dashboard.gcp.bigquery import ensure_dataset
from embrapa_dashboard.serving import gateway
from embrapa_dashboard.serving import sql as sqlbuild
from embrapa_dashboard.serving.cache import cache
from embrapa_dashboard.serving.research_inputs import _bq_client, _change_id_seen

logger = logging.getLogger(__name__)

# The machine identity that marks orphans (never an IAP person — auto-mark has no request).
ORPHAN_DETECTOR_AUTHOR = "system:orphan-detector"
# The warning every Descontinuado element carries. The purge is human-gated, backup-first.
PURGE_WARNING = (
    "Descontinuada: será removida do Gold por um operador (com backup), nunca automaticamente."
)

CATALOG_LIFECYCLE_LOG_SCHEMA = [
    bigquery.SchemaField("element_kind", "STRING", mode="REQUIRED"),  # 'commodity' | 'banco'
    bigquery.SchemaField("banco", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("code", "STRING", mode="NULLABLE"),  # codigo_produto; NULL for a banco
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),  # 'descontinuado' | 'purged'
    bigquery.SchemaField("reason", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("scheduled_purge_note", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("edited_by", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("edited_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("change_id", "STRING", mode="REQUIRED"),
    # Parte da IDENTIDADE do produto desde que a chave virou (banco, tabela, código).
    # NULLABLE: os bancos de uma tabela só não a preenchem, e o `ifnull` do
    # `sql.CHAVE_*` a colapsa na sentinela. Sem ela aqui, uma instalação NOVA criaria
    # o log sem a coluna e o particionamento quebraria — furo que um teste pegou.
    bigquery.SchemaField("tabela", "STRING", mode="NULLABLE"),
]


def _lifecycle_log_ref(cfg: Settings) -> str:
    return sqlbuild.table_ref(cfg, "bq_research_inputs_dataset", cfg.bq_catalog_lifecycle_log_table)


def ensure_catalog_lifecycle_log_table(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Create the append-only lifecycle log if missing (clustered by element). Idempotent."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = _lifecycle_log_ref(cfg)
    ensure_dataset(bq, f"{cfg.gcp_project_id}.{cfg.bq_research_inputs_dataset}", cfg.bq_location)
    table = bigquery.Table(table_fqn, schema=CATALOG_LIFECYCLE_LOG_SCHEMA)
    table.clustering_fields = ["element_kind", "banco"]
    bq.create_table(table, exists_ok=True)
    logger.info("Catalog-lifecycle log ready at %s", table_fqn)
    return table_fqn


def _insert_lifecycle_event(
    bq, table_fqn, *, element_kind, banco, code, status, reason, purge_note, edited_by, change_id
) -> None:
    """Append one lifecycle event (parameterized DML, server-side timestamp).

    Funil único dos três escritores (auto_mark_orphans, mark_purged, o manual), então a
    tabela SIDRA entra aqui uma vez só. Ela faz parte da CHAVE de um produto: sem ela o
    evento cai na sentinela `sql.SEM_TABELA` — uma identidade à parte — e o produto real
    ficaria sem o evento, com a marcação reportando sucesso.
    """
    from embrapa_dashboard.serving.curation import tabela_do_produto

    tabela = tabela_do_produto(banco, code, client=bq)
    sql = f"""
        insert into `{table_fqn}`
            (element_kind, banco, code, status, reason, scheduled_purge_note,
             edited_by, edited_at, change_id, tabela)
        values
            (@element_kind, @banco, @code, @status, @reason, @purge_note,
             @edited_by, current_timestamp(), @change_id, @tabela)
    """
    p = bigquery.ScalarQueryParameter
    params = [
        p("element_kind", "STRING", element_kind),
        p("banco", "STRING", banco),
        p("code", "STRING", code),
        p("tabela", "STRING", tabela),
        p("status", "STRING", status),
        p("reason", "STRING", reason),
        p("purge_note", "STRING", purge_note),
        p("edited_by", "STRING", edited_by),
        p("change_id", "STRING", change_id),
    ]
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


def _current_status(settings: Settings) -> dict:
    """{(element_kind, banco, code): status} from the lifecycle log; {} when absent."""
    try:
        df = gateway.fetch_lifecycle_status()
    except NotFound:
        return {}
    if df is None or df.empty:
        return {}
    return {
        (r.element_kind, r.banco, None if r.code is None else str(r.code)): r.status
        for r in df.itertuples()
    }


def _current_lifecycle(settings: Settings) -> dict:
    """{(element_kind, banco, code): (status, flagged_at)} from the lifecycle log
    (latest-wins); {} when absent. Carries ``flagged_at`` so the auto-marker can tell a
    FRESH removal (an entry re-added then re-removed AFTER a prior descontinuado/purge)
    from one already covered — status alone can't, because the log is immutable and the
    old terminal status would suppress the new generation forever."""
    try:
        df = gateway.fetch_lifecycle_status()
    except NotFound:
        return {}
    if df is None or df.empty:
        return {}
    return {
        (r.element_kind, r.banco, None if r.code is None else str(r.code)): (r.status, r.flagged_at)
        for r in df.itertuples()
    }


def auto_mark_orphans(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> dict:
    """Detect orphan commodities and append a ``descontinuado`` event for any not already
    marked (the automatic half of the lifecycle). Idempotent; NON-destructive. Returns
    ``{detected, newly_marked, already_marked}``."""
    cfg = settings or get_settings()
    try:
        orphans = gateway.fetch_orphan_produtos()
    except NotFound:
        return {"detected": 0, "newly_marked": 0, "already_marked": 0}
    if orphans is None or orphans.empty:
        return {"detected": 0, "newly_marked": 0, "already_marked": 0}

    already = _current_lifecycle(cfg)
    bq = client or _bq_client(cfg)
    table_fqn = _lifecycle_log_ref(cfg)
    ensure_catalog_lifecycle_log_table(cfg, bq)

    newly = 0
    for o in orphans.itertuples():
        code = str(o.codigo_produto)
        banco = o.banco
        removed_at = getattr(o, "removed_at", None)
        prev = already.get(("commodity", banco, code))
        if prev is not None:
            prev_status, prev_at = prev
            # Skip only when the latest lifecycle event already covers THIS removal —
            # i.e. it was recorded at/after the tombstone. A NEWER removal (re-added →
            # re-removed after a prior descontinuado/purge) has removed_at > prev_at, so
            # it re-marks: a fresh flagged_at + re-opening the purge gate (which requires
            # the CURRENT status to be 'descontinuado', not the stale 'purged').
            if removed_at is not None and prev_at is not None:
                if prev_at >= removed_at:
                    continue
            elif prev_status in ("descontinuado", "purged"):
                continue  # no timestamps to compare → fall back to status (idempotent)
        # change_id is generation-aware (carries the removal time) so a genuine re-removal
        # is not collapsed by the idempotency check, while a re-run within one generation is.
        gen = removed_at.isoformat() if removed_at is not None else "0"
        change_id = f"descontinuado:commodity:{banco}:{code}:{gen}"
        if _change_id_seen(bq, table_fqn, change_id):
            continue
        reason = (
            f"Removida do cadastro; dados em Gold pendentes "
            f"(agrupamento {getattr(o, 'agrupamento', None) or '—'})."
        )
        _insert_lifecycle_event(
            bq,
            table_fqn,
            element_kind="commodity",
            banco=banco,
            code=code,
            status="descontinuado",
            reason=reason,
            purge_note=PURGE_WARNING,
            edited_by=ORPHAN_DETECTOR_AUTHOR,
            change_id=change_id,
        )
        newly += 1
        logger.info("Lifecycle: %s:%s -> descontinuado (orphan)", banco, code)

    if newly:
        invalidate_lifecycle_cache()
    return {
        "detected": len(orphans),
        "newly_marked": newly,
        "already_marked": len(orphans) - newly,
    }


def invalidate_lifecycle_cache() -> None:
    """Drop the cached lifecycle-status + orphan reads (best-effort)."""
    for fn in (gateway.fetch_lifecycle_status, gateway.fetch_orphan_produtos):
        try:
            cache.delete_memoized(fn)
        except Exception as exc:  # pragma: no cover - cache unbound / backend down
            logger.warning("Could not invalidate lifecycle cache: %s", exc)


# ── Human-gated purge (the LAST destructive step — never automatic) ───────────
# The Gold fact table(s) whose rows an orphan's purge would delete (matched by the
# exact code). Gold is rebuilt from Bronze by dbt, so a true purge also needs the
# Bronze rows gone + the ingestion scope updated — the plan spells that out.
_PURGE_TARGETS = {
    "pevs": [("bq_gold_dataset", "gold_pevs_production", "product_code")],
    "pam": [("bq_gold_dataset", "gold_pam_production", "product_code")],
    "ppm": [("bq_gold_dataset", "gold_ppm_production", "product_code")],
    "comex": [("bq_gold_dataset", "gold_comex_flows", "ncm_code")],
    "comtrade": [("bq_gold_dataset", "gold_comtrade_flows", "cmd_code")],
}


def _backup_status(settings: Settings) -> tuple[bool, str]:
    """Is there a COMPLETE Gold snapshot OF THE DATASET BEING PURGED, newer than
    BACKUP_STALENESS_DAYS? Reuses the doctor's backup-freshness logic — the purge MUST NOT
    proceed without a fresh rollback point (the project's backup-first posture). Because
    ``_latest_complete_run`` now matches the snapshot's recorded dataset against
    ``settings.bq_gold_dataset``, a dev-dataset snapshot can no longer satisfy a prod purge
    gate (the exact dev/prod .env drift the runbook warns about)."""
    from datetime import UTC, datetime

    from google.cloud import storage

    from embrapa_dashboard import doctor
    from embrapa_dashboard.config import get_credentials

    try:
        client = storage.Client(
            project=settings.gcp_project_id, credentials=get_credentials(settings)
        )
        runs = doctor._list_backup_runs(client, settings)
        if not runs:
            return False, "no Gold snapshot — run `make dbt-build-prod-with-backup` first."
        latest, _ = doctor._latest_complete_run(client, settings, runs)
        if latest is None:
            return (
                False,
                "no COMPLETE Gold snapshot (all partial) — run a backup first.",
            )
        age_days = (datetime.now(UTC) - latest).total_seconds() / 86400
        if age_days > settings.backup_staleness_days:
            return (
                False,
                f"latest snapshot is {age_days:.0f}d old "
                f"(> {settings.backup_staleness_days}d) — run a fresh backup first.",
            )
        return (
            True,
            f"complete Gold snapshot of {settings.bq_gold_dataset!r} at "
            f"{latest.strftime('%Y-%m-%d %H:%M UTC')}",
        )
    except Exception as exc:  # pragma: no cover - GCS unreachable / perms
        return False, f"could not verify the backup: {exc}"


def _refuse_if_re_added(cfg: Settings, banco: str, code: str) -> None:
    """Refuse the purge when the code was RE-ADDED to the catalog after being marked
    Descontinuado. The lifecycle log is append-only and record_produto_catalog writes NO
    reactivation event, so ``_current_status`` still reads 'descontinuado' for a re-added
    (currently active) code — the gate's blind spot. Cross-check the catalog's live state
    (latest-wins active) and reject an in-use product, so the operator can never purge the
    Gold data of a commodity that is back in the dashboard."""
    from embrapa_dashboard.serving import curation

    bq = _bq_client(cfg)
    if curation._is_active_entry(bq, curation._catalog_log_ref(cfg), code, banco):
        raise ValueError(
            f"{banco}:{code} was re-added to the catalog (active) — no longer an orphan; "
            "refuse to purge (remove it from the catalog again first if you truly intend to)."
        )


def purge_plan(banco: str, code: str, settings: Settings | None = None) -> dict:
    """Build the human-runnable PURGE PLAN for a Descontinuado orphan: the scoped DELETE
    for each Gold table whose rows carry the EXACT code, the backup status, and the
    re-ingestion caveat. Does NOT delete anything — the operator runs the printed
    statements (the project hands destructive deletes to a human). Raises ValueError if
    the element is not currently Descontinuado, or the banco/code is malformed.

    ``code`` is the codigo_produto — the orphan worklist identity AND the exact Gold
    code (commodities are registered by exact code now; no prefixes), so the DELETE is a
    plain equality that matches exactly what orphan detection flagged.

    ⚠ O DELETE casa por CÓDIGO, não pela chave inteira. Desde v1.39.0 a identidade de um
    produto é (banco, tabela SIDRA, código), e o Gold destes bancos carrega um
    discriminador semântico (`measure_kind` / `origem`), não o id da tabela — então um
    código presente nas DUAS metades de um banco multi-tabela seria purgado por inteiro,
    incluindo a metade que NÃO foi marcada como órfã. Não há caso hoje (`embrapa doctor` →
    `shared-code` vigia), e o plano é impresso para revisão humana antes de qualquer
    execução — mas quem revisar precisa saber disso, então o aviso vai no plano."""
    cfg = settings or get_settings()
    banco = (banco or "").strip()
    code = (code or "").strip()
    # The code is interpolated verbatim into a printed DELETE, so it must be a plain literal
    # token. Enforce DIGITS-ONLY to match the catalog write validation (_validate_catalog_edit
    # accepts only [0-9]+): a lifecycle entry can only originate from a validated catalog_log
    # row today, but a looser regex here would let a future direct lifecycle writer slip a
    # dot/hyphen code into a DELETE. Keep the two validators in lockstep.
    if not banco or not code or not re.fullmatch(r"[0-9]+", code):
        raise ValueError("banco and a digits-only product code are required.")
    if _current_status(cfg).get(("commodity", banco, code)) != "descontinuado":
        raise ValueError(
            f"{banco}:{code} is not marked Descontinuado — refuse to plan a purge "
            "(only orphans that were detected + marked may be purged)."
        )
    _refuse_if_re_added(cfg, banco, code)
    # O aviso vai NO PLANO, não só no docstring: quem executa lê isto, não o código.
    statements = [
        "-- ⚠ casa por CÓDIGO, não pela chave (banco, tabela SIDRA, código). Se este código "
        "existir nas DUAS tabelas do banco, o DELETE leva as duas metades.",
        *(
            f"DELETE FROM `{sqlbuild.table_ref(cfg, dataset_attr, table)}` WHERE {col} = '{code}';"
            for dataset_attr, table, col in _PURGE_TARGETS.get(banco, [])
        ),
    ]
    backup_ok, backup_msg = _backup_status(cfg)
    return {
        "banco": banco,
        "code": code,
        "statements": statements,
        "backup_ok": backup_ok,
        "backup_msg": backup_msg,
    }


def mark_purged(
    banco: str,
    code: str,
    *,
    edited_by: str,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> dict:
    """Append a terminal ``purged`` lifecycle event AFTER the operator ran the DELETEs
    (who/when, for the audit trail). Idempotent PER GENERATION. Does NOT itself delete data.

    The change_id carries the current descontinuado GENERATION (its ``flagged_at``), mirroring
    auto_mark_orphans: a retry within one generation dedups, but a code that was re-added,
    re-removed (a NEW descontinuado generation) and re-purged records its OWN terminal event
    instead of being silently collapsed onto the first purge's audit row. An element whose
    CURRENT status is already ``purged`` (no fresh removal) is a no-op; one that is NOT currently
    Descontinuado raises ValueError (mirrors purge_plan's gate) rather than recording a premature
    terminal event that would lock the purge plan out while Gold data still lingers."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = _lifecycle_log_ref(cfg)
    ensure_catalog_lifecycle_log_table(cfg, bq)
    status, flagged_at = _current_lifecycle(cfg).get(("commodity", banco, str(code)), (None, None))
    if status == "purged":
        # Already purged for the current generation — nothing fresh to record.
        return {"banco": banco, "code": code, "status": "purged", "deduped": True}
    if status != "descontinuado":
        # Mirror purge_plan's gate: a terminal 'purged' event may only be recorded for an
        # element the lifecycle currently marks Descontinuado. Recording it for anything else
        # (never-marked → gen falls back to '0') would falsely lock the purge plan out while
        # Gold data still lingers, and auto_mark_orphans would not re-mark it.
        raise ValueError(
            f"{banco}:{code} is not marked Descontinuado — refuse to record the purge "
            "(only orphans that were detected + marked may be purged)."
        )
    # Marked Descontinuado — but the code may have been RE-ADDED (active) to the catalog (the
    # append-only lifecycle log still reads 'descontinuado'). Refuse to stamp a terminal
    # 'purged' event on an in-use product (checked last: it hits BQ for the live catalog state).
    _refuse_if_re_added(cfg, banco, str(code))
    # Generation = the descontinuado event's flagged_at (stable for the whole purge window), so a
    # later re-removal (a new descontinuado, new flagged_at) is NOT collapsed onto this change_id.
    gen = flagged_at.isoformat() if (status == "descontinuado" and flagged_at is not None) else "0"
    change_id = f"purged:commodity:{banco}:{code}:{gen}"
    if _change_id_seen(bq, table_fqn, change_id):
        return {"banco": banco, "code": code, "status": "purged", "deduped": True}
    _insert_lifecycle_event(
        bq,
        table_fqn,
        element_kind="commodity",
        banco=banco,
        code=str(code),
        status="purged",
        reason="Purga manual executada pelo operador.",
        purge_note=None,
        edited_by=edited_by,
        change_id=change_id,
    )
    invalidate_lifecycle_cache()
    logger.info("Lifecycle: %s:%s -> purged by %s", banco, code, edited_by)
    return {"banco": banco, "code": code, "status": "purged", "deduped": False}
