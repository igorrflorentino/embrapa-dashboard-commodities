"""Curadoria (catalog) — what ENTERS and EXITS the dashboard.

This is the feature the project lead reserved the name "Curadoria" for: the
researcher-managed catalog of which commodities are in the dashboard, their
agrupamento (cross-source concept) and ciclo de vida (in/out). Each commodity is
registered by its EXACT source code (one code = one entry; no prefixes). It is the
editable successor to the version-controlled ``commodity_crosswalk`` seed (the seed
and this catalog are redundant — confirmed on real data; the catalog becomes the
single source of truth and ``gold_produto_agrupamento`` reads it).

NOT to be confused with ``serving/attribute_engineering.py`` (the FROZEN feature
that builds derived columns — per-code industrialization + market-nature). Both
reuse the shared primitives in ``serving/research_inputs.py``.

Design (honouring the lead's decisions):
  * **Append-only** log (``research_inputs.produto_catalog_log``): every edit is
    an immutable, IAP-attributed row; the CURRENT catalog is the latest row per
    ``(codigo_produto, banco)``. **No row is ever destroyed** — a removal appends
    an ``active=false`` tombstone (the entry leaves the catalog → its Gold data
    becomes an orphan, handled non-destructively by the lifecycle, never auto-deleted).
  * **Composite key** ``(codigo_produto, banco)``: both required — a blank either
    breaks the key, so the writer REJECTS it (fail loud) rather than ignoring it.
  * **Exact code only** (no prefixes): a NEW entry's ``codigo_produto`` need NOT already
    exist in the source's Gold — now that the catalog DRIVES ingestion
    (``catalog_authoritative_ingestion``), a not-yet-ingested code is accepted as
    *pendente de ingestão* (``_check_code_status`` only LOGS the pending state; the hard
    guards are the numeric-format check in ``_validate_catalog_edit`` and the banco
    allowlist). ``gold_produto_agrupamento`` / the visibility gate
    match on ``code = codigo_produto`` (equality, not ``LIKE``), so there is no
    prefix fan-out to double-count.
  * **Per-catalog allowlist** (``research_inputs.catalog_editors`` keyed by resource):
    each cadastro has its OWN authorized editors, distinct from the
    attribute-engineering ``attribute editors`` table.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Mapping

from google.api_core.exceptions import BadRequest, NotFound
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

# The resource id of the commodity catalog in the per-catalog allowlist.
PRODUTO_CATALOG_RESOURCE = "produto_catalog"

# Append-only commodity-catalog log. Explicit schema (autodetect drifts silently).
PRODUTO_CATALOG_LOG_SCHEMA = [
    bigquery.SchemaField("codigo_produto", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("banco", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("agrupamento", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("descricao_produto", "STRING", mode="NULLABLE"),
    # RETIRED (read-only history): the pre-split prose enum. New writes leave it NULL and
    # set `ingestao`/`visibilidade` instead; readers translate it via visibilidade_efetiva.
    bigquery.SchemaField("ciclo_de_vida", "STRING", mode="NULLABLE"),
    # The two lifecycle axes (coded). NULL on rows written before the split — readers
    # default them to ativa/visivel. Added late → self-healed via ALTER on existing tables.
    bigquery.SchemaField("ingestao", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("visibilidade", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("agrupamento_id", "STRING", mode="NULLABLE"),
    # PPM only: which SIDRA table this code belongs to ('3939' herd headcount /
    # '74' animal production) so catalog-driven ingestion routes it to the right
    # table. NULL for every other (single-table) banco. See catalog_resolver +
    # config.ppm_*_table_id. Added late → self-healed via ALTER on existing tables.
    bigquery.SchemaField("sidra_tabela", "STRING", mode="NULLABLE"),
    # active=false is a tombstone: the entry has left the catalog (→ Gold orphan).
    bigquery.SchemaField("active", "BOOL", mode="REQUIRED"),
    bigquery.SchemaField("edited_by", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("edited_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("change_id", "STRING", mode="REQUIRED"),
]

# Per-CATALOG editor allowlist (one row per (resource, email)).
CATALOG_EDITORS_SCHEMA = [
    bigquery.SchemaField("resource", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("email", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("added_by", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("added_at", "TIMESTAMP", mode="NULLABLE"),
]


def _catalog_log_ref(cfg: Settings) -> str:
    return sqlbuild.table_ref(cfg, "bq_research_inputs_dataset", cfg.bq_produto_catalog_log_table)


def ensure_produto_catalog_log_table(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Create the append-only commodity-catalog log if missing (clustered by the
    key). Idempotent — called on first write."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = _catalog_log_ref(cfg)
    ensure_dataset(bq, f"{cfg.gcp_project_id}.{cfg.bq_research_inputs_dataset}", cfg.bq_location)
    table = bigquery.Table(table_fqn, schema=PRODUTO_CATALOG_LOG_SCHEMA)
    table.clustering_fields = ["banco", "codigo_produto"]
    bq.create_table(table, exists_ok=True)
    # Self-heal a table that predates a late-added column: create_table(exists_ok) never
    # widens an existing schema, so add them idempotently. Best-effort — a transient
    # DDL/permission fault must not block the (rare) curation write.
    for column in ("sidra_tabela", "ingestao", "visibilidade"):
        try:
            bq.query(f"alter table `{table_fqn}` add column if not exists {column} STRING").result()
        except Exception as exc:
            logger.warning("Could not ensure %s column on %s: %s", column, table_fqn, exc)
    logger.info("Commodity-catalog log ready at %s", table_fqn)
    return table_fqn


def ensure_catalog_editors_table(
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Create the per-catalog editor allowlist table if missing. Idempotent.

    Console-managed: ``INSERT (resource, email) VALUES ('produto_catalog', 'a@x')``
    to authorize an editor — no redeploy. Empty/absent → any IAP-authenticated caller
    may edit (the same open-by-default posture as the attribute editors allowlist)."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = sqlbuild.table_ref(cfg, "bq_research_inputs_dataset", cfg.bq_catalog_editors_table)
    ensure_dataset(bq, f"{cfg.gcp_project_id}.{cfg.bq_research_inputs_dataset}", cfg.bq_location)
    bq.create_table(bigquery.Table(table_fqn, schema=CATALOG_EDITORS_SCHEMA), exists_ok=True)
    logger.info("Catalog-editors allowlist table ready at %s", table_fqn)
    return table_fqn


def add_catalog_editor(
    resource: str,
    email: str,
    *,
    added_by: str = "cli",
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str:
    """Authorize ``email`` to edit the ``resource`` catalog (append a row). Idempotent by
    effect — duplicates are harmless (the allowlist read DISTINCTs). Returns the normalized
    email. Backs ``embrapa editors add`` (the no-Console alternative)."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = ensure_catalog_editors_table(cfg, bq)
    email_norm = (email or "").strip().lower()
    if not email_norm:
        raise ValueError("email is required.")
    sql = (
        f"insert into `{table_fqn}` (resource, email, added_by, added_at) "
        "values (@resource, @email, @added_by, current_timestamp())"
    )
    p = bigquery.ScalarQueryParameter
    params = [
        p("resource", "STRING", resource),
        p("email", "STRING", email_norm),
        p("added_by", "STRING", added_by),
    ]
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    # A newly-added editor should be able to edit immediately, not after the TTL.
    invalidate_catalog_editors_cache()
    logger.info("Catalog editor authorized: %s on %s (by %s)", email_norm, resource, added_by)
    return email_norm


def remove_catalog_editor(
    resource: str,
    email: str,
    *,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> int:
    """De-authorize ``email`` from the ``resource`` catalog (delete matching rows,
    case-insensitive). Returns the number of rows removed. Backs ``embrapa editors remove``."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    table_fqn = ensure_catalog_editors_table(cfg, bq)
    email_norm = (email or "").strip().lower()
    sql = f"delete from `{table_fqn}` where resource = @resource and lower(trim(email)) = @email"
    p = bigquery.ScalarQueryParameter
    params = [p("resource", "STRING", resource), p("email", "STRING", email_norm)]
    job = bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    # Revocation must take effect at once — drop the memoized allowlist so the removed
    # editor cannot keep writing for the cache-TTL window.
    invalidate_catalog_editors_cache()
    return int(getattr(job, "num_dml_affected_rows", 0) or 0)


def _slug(name: str | None) -> str:
    """ASCII slug of an agrupamento → agrupamento_id (matches the seed's slugs:
    'Castanha-do-pará' → 'castanha_do_para', 'Açaí' → 'acai')."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


# ── Lifecycle vocabulary ──────────────────────────────────────────────────────
# TWO ORTHOGONAL AXES, stored as STABLE MACHINE CODES (never display prose):
#
#   ingestao      ativa | pausada    — should the pipeline keep FETCHING new data?
#   visibilidade  visivel | oculto   — should the researcher SEE it in the dashboard?
#
# Why two axes: "buscar dados novos?" and "pesquisador vê?" are independent decisions.
# The retired single `ciclo_de_vida` enum crossed them into two prose options that BOTH
# began "Fazer Ingestão" — so the ingestion half carried no information (catalog_resolver
# never read the column), and the useful "freeze the series but keep the history" state was
# inexpressible: the only way to stop ingesting was to REMOVE the produto, turning it into
# an orphan awaiting purge.
#
# Why codes, not the pt-BR sentence: the old value WAS the display string, hardcoded as a
# literal in dim_produto_visibility.sql, in this module and in the UI dropdown — so a reword
# meant a coordinated 3-place change plus a data migration, and a silent drift would fail
# the visibility gate OPEN. Codes are stable; the pt-BR labels live only in the UI.
INGESTAO_ATIVA = "ativa"
INGESTAO_PAUSADA = "pausada"
_INGESTAO_VALUES = frozenset({INGESTAO_ATIVA, INGESTAO_PAUSADA})

VISIBILIDADE_VISIVEL = "visivel"
VISIBILIDADE_OCULTO = "oculto"
_VISIBILIDADE_VALUES = frozenset({VISIBILIDADE_VISIVEL, VISIBILIDADE_OCULTO})

# LEGACY (retired, read-only): the prose values written into `ciclo_de_vida` before the
# two-axis split. The log is APPEND-ONLY, so these rows are never rewritten — every reader
# translates them on read instead (see `visibilidade_efetiva` here and the dbt
# `catalog_visibilidade` macro, which MUST agree). Kept as constants so the translation is
# expressed once, not re-typed as literals.
CICLO_DE_VIDA_VISIVEL = "Fazer Ingestão e deixar disponível"
CICLO_DE_VIDA_OCULTO = "Fazer Ingestão mas deixar indisponível"
_CICLO_DE_VIDA_VALUES = frozenset({CICLO_DE_VIDA_VISIVEL, CICLO_DE_VIDA_OCULTO})
_LEGACY_CICLO_TO_VISIBILIDADE = {
    CICLO_DE_VIDA_VISIVEL: VISIBILIDADE_VISIVEL,
    CICLO_DE_VIDA_OCULTO: VISIBILIDADE_OCULTO,
}


def visibilidade_efetiva(visibilidade: str | None, ciclo_de_vida: str | None) -> str:
    """The effective visibility of a catalog row: the new coded column when present, else
    the translated legacy prose, else visible.

    The Python twin of the dbt `catalog_visibilidade` macro — the two MUST agree, since one
    drives the researcher-facing gate (dbt) and the other the admin editor (this module).
    Defaults to VISIVEL: an unset stage has always meant "not hidden" (the gate is a
    NOT EXISTS over hidden codes), so an unknown/NULL value must never hide a produto."""
    if visibilidade in _VISIBILIDADE_VALUES:
        return visibilidade
    return _LEGACY_CICLO_TO_VISIBILIDADE.get(ciclo_de_vida or "", VISIBILIDADE_VISIVEL)


def ingestao_efetiva(ingestao: str | None) -> str:
    """The effective ingestion state: the coded column when present, else ATIVA.

    Legacy rows predate the axis and were all ingested (catalog_resolver filtered on
    `active` alone), so NULL must read as ATIVA — anything else would silently stop
    ingesting every produto registered before the split."""
    return ingestao if ingestao in _INGESTAO_VALUES else INGESTAO_ATIVA


# Source codes are numeric and short (NCM 8 digits, HS <=6, SIDRA <=~7); 32 is generous
# headroom that still rejects a pathologically long value before it is stored.
MAX_CODE_LEN = 32


def _validate_lifecycle(ingestao: str | None, visibilidade: str | None) -> None:
    """Reject an out-of-vocabulary lifecycle code — a LOUD 400 instead of a silent
    fail-open of the visibility gate (an unrecognized value reads as VISIVEL, so a typo'd
    'ocluto' would quietly leave a produto the researcher meant to hide on display)."""
    if ingestao is not None and ingestao not in _INGESTAO_VALUES:
        raise ValueError(f"ingestao {ingestao!r} inválido — use um de {sorted(_INGESTAO_VALUES)}.")
    if visibilidade is not None and visibilidade not in _VISIBILIDADE_VALUES:
        raise ValueError(
            f"visibilidade {visibilidade!r} inválido — use um de "
            f"{sorted(_VISIBILIDADE_VALUES)} (mantém o gate de visibilidade em sincronia)."
        )


def _registered_group_ids(cfg: Settings, bq: bigquery.Client) -> set[str]:
    """Ids of the agrupamentos that actually exist. Empty set when the registry table is
    absent — a cold install must not be unable to register its first product, so the
    caller treats "no registry at all" as "nothing to check against" rather than as
    "everything is invalid"."""
    from embrapa_dashboard.serving import agrupamentos

    try:
        return set(agrupamentos._current_groups(bq, agrupamentos._group_log_ref(cfg)))
    except Exception:  # uma leitura do registro nunca pode bloquear uma edição
        return set()


# `ibge_pevs` (o token de FONTE, usado pelos registros por-código) → `pevs` (o token de
# BANCO, usado pelo catálogo). Derivado do vocabulário único em `sql`, não redigitado: esta
# era uma de QUATRO cópias à mão do mesmo mapeamento, e a inversa de outra logo abaixo.
_SOURCE_PARA_BANCO = sqlbuild.SOURCE_TO_BANCO


def tabela_do_produto(
    banco_ou_source: str,
    codigo_produto: str,
    *,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> str | None:
    """A tabela SIDRA que a entrada de catálogo deste produto carrega.

    O catálogo é a fonte de verdade da identidade: um produto é `(banco, tabela, código)`, e
    os OUTROS registros por-código (nível de industrialização, ciclo de vida) precisam da
    mesma tabela para que suas escritas caiam sobre o mesmo produto. Sem ela, a escrita cai
    na sentinela `sql.SEM_TABELA` — uma identidade à parte, que não corresponde a dado
    nenhum e que nenhum erro denuncia.

    Aceita tanto o token de banco (`pevs`) quanto o de fonte (`ibge_pevs`). Devolve None
    quando não há entrada de catálogo ou quando o banco é de uma tabela só — nos dois casos
    o `ifnull` da chave colapsa na sentinela, que é o comportamento certo.
    """
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    banco = _SOURCE_PARA_BANCO.get(banco_ou_source, banco_ou_source)
    return _current_sidra_tabela(bq, _catalog_log_ref(cfg), codigo_produto, banco)


def _validate_catalog_edit(codigo_produto: str, banco: str, ciclo_de_vida: str | None) -> None:
    """The composite key (codigo_produto, banco) is required — a blank either breaks
    the key, so we REJECT (fail loud) instead of silently dropping the row. The code
    must be all-digits (every source code — SIDRA, NCM, HS — is numeric), a cheap
    typo guard now that a NEW code need NOT already exist in Gold (pending ingestion,
    see ``_check_code_status``). Messages are pt-BR: a researcher reads them (the
    route surfaces ``str(exc)`` on a 400)."""
    if not codigo_produto or not banco:
        raise ValueError("codigo_produto e banco são obrigatórios (a chave do catálogo).")
    if len(codigo_produto) > MAX_CODE_LEN:
        raise ValueError(
            f"O código excede {MAX_CODE_LEN} caracteres — os códigos das fontes "
            "(SIDRA, NCM, HS) têm no máximo 8 dígitos."
        )
    if not re.fullmatch(r"[0-9]+", codigo_produto):
        raise ValueError(
            f"O código {codigo_produto!r} deve conter apenas dígitos — os códigos de "
            "todas as fontes (SIDRA, NCM, HS) são numéricos."
        )
    if ciclo_de_vida is not None and len(ciclo_de_vida) > MAX_STAGE_LEN:
        raise ValueError(f"ciclo_de_vida excede {MAX_STAGE_LEN} caracteres.")
    if ciclo_de_vida and ciclo_de_vida not in _CICLO_DE_VIDA_VALUES:
        raise ValueError(
            f"ciclo_de_vida {ciclo_de_vida!r} inválido — use exatamente um de "
            f"{sorted(_CICLO_DE_VIDA_VALUES)} (mantém o gate de visibilidade em sincronia)."
        )


# Catalog banco token → the long source id. Doubles as the allowlist of the 5 valid catalog
# banco tokens (its keys) that _assert_code_exists validates against before the Gold read.
# Alias do vocabulário único em `sql` — mesmo objeto, não uma cópia que possa divergir.
_BANCO_TO_SOURCE = sqlbuild.BANCO_TO_SOURCE


def _is_active_entry(bq: bigquery.Client, table_fqn: str, codigo_produto: str, banco: str) -> bool:
    """Whether (codigo_produto, banco) is CURRENTLY an active catalog entry (latest-wins)
    — i.e. this write is an UPDATE, not a new registration. ``False`` when the log table
    doesn't exist yet."""
    sql = f"""
        select active from (
          select active, row_number() over (
            partition by {sqlbuild.CHAVE_CATALOGO} order by edited_at desc, change_id desc
          ) as _rn
          from `{table_fqn}`
          where codigo_produto = @codigo and banco = @banco
        ) where _rn = 1
    """
    params = [
        bigquery.ScalarQueryParameter("codigo", "STRING", codigo_produto),
        bigquery.ScalarQueryParameter("banco", "STRING", banco),
    ]
    try:
        rows = list(
            bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        )
    except NotFound:
        return False
    return bool(rows) and bool(rows[0].active)


# Os bancos que unem DUAS tabelas SIDRA sob um token só. Uma constante e não um literal
# espalhado: `banco == "ppm"` era exatamente a forma que deixou o pevs de fora da regra.
_BANCOS_MULTI_TABELA = ("ppm", "pevs")


def _tabelas_validas_por_banco(cfg: Settings) -> dict[str, set[str]]:
    """As tabelas SIDRA que cada banco multi-tabela aceita."""
    return {
        "ppm": {cfg.ppm_herd_table_id, cfg.ppm_animal_table_id},
        "pevs": {cfg.ibge_table_id, cfg.silvicultura_table_id},
    }


def _validate_sidra_tabela(
    banco: str, sidra_tabela: str | None, cfg: Settings, *, require_for_ppm: bool = True
) -> None:
    """Some bancos span TWO SIDRA tables under a single banco token, so their entries tag
    which table the code belongs to — the catalog-driven ingestion resolver routes by it
    (``catalog_resolver``). Every other (single-table) banco must NOT carry one.

    TWO bancos are multi-table, and they differ in whether the tag is mandatory:

    * ``ppm`` — rebanho (3939) / produção animal (74). REQUIRED on a new entry: the two
      tables share no codes and there is no defensible default.
    * ``pevs`` — extração vegetal (289) / silvicultura (291), since the silviculture half
      was ingested on 2026-08-29.

    A tag é OBRIGATÓRIA nos dois desde que a identidade de um produto passou a ser
    ``(banco, tabela, código)``: sem ela a entrada não cai em nenhuma das duas metades, cai
    numa TERCEIRA identidade (a sentinela ``sql.SEM_TABELA``) que não corresponde a dado
    nenhum. Era opcional no pevs enquanto a chave a ignorava; virou obrigatória junto com a
    chave, e o histórico foi completado na mesma migração
    (``scripts/migrate_catalog_key_add_table.py``).

    ``require_for_ppm`` — mantido o nome por compatibilidade de chamada — é True para uma
    entrada NOVA e False para um UPDATE, onde o chamador preserva a tag guardada. Fail loud
    (400, pt-BR)."""
    valid_por_banco = _tabelas_validas_por_banco(cfg)
    valid = valid_por_banco.get(banco)
    if valid is None:
        if sidra_tabela:
            raise ValueError(
                f"sidra_tabela só se aplica aos bancos {sorted(valid_por_banco)} "
                f"(recebido para {banco!r})."
            )
        return
    if not sidra_tabela:
        if require_for_ppm:
            raise ValueError(
                f"sidra_tabela é obrigatória para o banco {banco!r} — informe "
                f"{sorted(valid)}. Ela faz parte da identidade do produto: sem ela a "
                "entrada não pertence a nenhuma das duas tabelas do banco."
            )
        return  # UPDATE — o chamador preserva a tag já guardada
    if sidra_tabela not in valid:
        raise ValueError(
            f"sidra_tabela {sidra_tabela!r} inválida para o banco {banco!r} — "
            f"use um de {sorted(valid)}."
        )


def _current_sidra_tabela(
    bq: bigquery.Client, table_fqn: str, codigo_produto: str, banco: str
) -> str | None:
    """The active entry's stored ``sidra_tabela`` — reused to PRESERVE it on a PPM update
    that doesn't re-send it (the admin table's inline ciclo/agrupamento edits). Returns None
    when absent / the column doesn't exist yet — wrapped so a pre-migration table can't break
    the write."""
    sql = f"""
        select sidra_tabela from (
          select sidra_tabela, row_number() over (
            partition by {sqlbuild.CHAVE_CATALOGO} order by edited_at desc, change_id desc
          ) as _rn
          from `{table_fqn}`
          where codigo_produto = @codigo and banco = @banco
        ) where _rn = 1
    """
    params = [
        bigquery.ScalarQueryParameter("codigo", "STRING", codigo_produto),
        bigquery.ScalarQueryParameter("banco", "STRING", banco),
    ]
    try:
        rows = list(
            bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        )
    except (NotFound, BadRequest):
        # ONLY the pre-migration cases are legitimately "no stored tag": the log table is
        # absent (NotFound) or the sidra_tabela column doesn't exist yet (BadRequest,
        # "Unrecognized name"). Any OTHER error (a transient BQ/permission fault) must
        # PROPAGATE — swallowing it here returns None, and _validate_sidra_tabela accepts a
        # NULL tag on an update (require_for_ppm=False), so the append-only overwrite would
        # DROP the PPM routing tag and silently exclude the code from catalog-driven ingestion.
        return None
    return rows[0].sidra_tabela if rows else None


def _current_descricao(
    bq: bigquery.Client, table_fqn: str, codigo_produto: str, banco: str
) -> str | None:
    """The active entry's stored ``descricao_produto`` — the researcher's own annotation —
    so an update that doesn't re-send it PRESERVES it instead of erasing it.

    Same hazard the two lifecycle axes have (the writer overwrites the whole row), but the
    loss is worse: an axis can be re-picked from a dropdown, whereas a free-text note typed
    by a researcher is gone for good. The live UI always re-sends the full entry, so nothing
    was losing notes in practice — this closes the asymmetry so a partial write from a script
    or curl can't silently wipe them either.

    NOTE the None-vs-empty distinction, which is load-bearing: ``None`` means *omitted*
    (preserve), while ``''`` is an explicit CLEAR the researcher asked for (the ✎ field
    commits a trimmed empty string). Never normalize ``''`` to None on the way in.

    Returns None when absent / the column doesn't exist yet; any other BQ fault PROPAGATES
    rather than silently clearing the note."""
    sql = f"""
        select descricao_produto from (
          select descricao_produto, row_number() over (
            partition by {sqlbuild.CHAVE_CATALOGO} order by edited_at desc, change_id desc
          ) as _rn
          from `{table_fqn}`
          where codigo_produto = @codigo and banco = @banco
        ) where _rn = 1
    """
    params = [
        bigquery.ScalarQueryParameter("codigo", "STRING", codigo_produto),
        bigquery.ScalarQueryParameter("banco", "STRING", banco),
    ]
    try:
        rows = list(
            bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        )
    except (NotFound, BadRequest):
        return None
    return rows[0].descricao_produto if rows else None


def _current_lifecycle(
    bq: bigquery.Client, table_fqn: str, codigo_produto: str, banco: str
) -> tuple[str | None, str | None]:
    """The active entry's EFFECTIVE (ingestao, visibilidade) — legacy prose already
    translated — so an update that doesn't re-send them PRESERVES them.

    The writer overwrites the whole row (append-only latest-wins), so an omitted axis would
    otherwise be stored as NULL. For visibilidade that is a fail-OPEN: a produto the
    researcher had hidden would silently come back into every chart on an unrelated edit
    (e.g. renaming its agrupamento). The retired `ciclo_de_vida` had no such preservation
    and relied on the UI always re-sending the whole entry — that coupling is what this
    replaces, so any client (or a script) is now safe by default.

    Returns (None, None) only when there is genuinely no prior row / the table predates the
    columns; a transient BQ fault PROPAGATES rather than silently clearing the axes."""
    sql = f"""
        select ciclo_de_vida, ingestao, visibilidade from (
          select ciclo_de_vida, ingestao, visibilidade, row_number() over (
            partition by {sqlbuild.CHAVE_CATALOGO} order by edited_at desc, change_id desc
          ) as _rn
          from `{table_fqn}`
          where codigo_produto = @codigo and banco = @banco
        ) where _rn = 1
    """
    params = [
        bigquery.ScalarQueryParameter("codigo", "STRING", codigo_produto),
        bigquery.ScalarQueryParameter("banco", "STRING", banco),
    ]
    try:
        rows = list(
            bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        )
    except (NotFound, BadRequest):
        # Same narrow contract as _current_sidra_tabela: only the pre-migration shapes
        # (absent table / absent columns) are legitimately "nothing stored".
        return None, None
    if not rows:
        return None, None
    row = rows[0]
    return (
        ingestao_efetiva(row.ingestao),
        visibilidade_efetiva(row.visibilidade, row.ciclo_de_vida),
    )


def _check_code_status(
    bq: bigquery.Client, table_fqn: str, codigo_produto: str, banco: str, *, is_active: bool
) -> None:
    """Validate the banco (HARD) and NOTE (advisorily) whether the code already has Gold data.

    Hard rejection — an UNKNOWN banco token: it would write a junk row that never joins in
    gold_produto_agrupamento (source ∈ pevs/pam/ppm/comex/comtrade) → silent orphaned data.
    No other layer validates the banco, so reject it loudly here.

    Advisory only (does NOT raise) — a code with no Gold data yet: now that the Curadoria
    catalog DRIVES ingestion (``catalog_authoritative_ingestion``), a researcher registers a
    product precisely so the next run fetches it, so a not-yet-ingested code is legitimately
    "pendente de ingestão" (the catalog status view's ``has_data`` surfaces it). An UPDATE to
    an already-active entry (``is_active``) is likewise fine. We only LOG the pending state —
    the cheap numeric-format guard in ``_validate_catalog_edit`` is what catches gross typos."""
    if is_active:
        return  # update of an existing entry — not a new registration
    source = _BANCO_TO_SOURCE.get(banco)
    if source is None:
        raise ValueError(f"banco {banco!r} inválido — use um de {sorted(_BANCO_TO_SOURCE)}.")
    try:
        stats = gateway.fetch_source_code_stats(banco)
    except NotFound:
        return  # source Gold table not built yet — nothing to check against
    if stats is None or stats.empty:
        return
    codes = {str(r.code) for r in stats.itertuples()}
    if codigo_produto not in codes:
        logger.info(
            "Catalog: %s:%s has no Gold data yet — registering as pendente de ingestão "
            "(the next ingestion run will attempt to fetch it).",
            banco,
            codigo_produto,
        )


def _validate_agrupamento(
    agrupamento: str | None, agrupamento_id: str | None, descricao_produto: str | None
) -> None:
    """The researcher-supplied text fields: present where required, and within caps.

    ``agrupamento`` names the commodity (``agrupamento_nome``) AND seeds ``agrupamento_id``;
    both are NOT NULL downstream (``dim_produto_catalog`` → ``gold_produto_agrupamento``).
    A blank one yields NULLs that fail the nightly prod ``dbt build`` not_null tests — so
    fail loud HERE (a 400 the researcher can fix), never at build time.

    ``agrupamento_id`` is user-writable (a client may send it directly, winning over the
    ``_slug`` default), so it is capped too — a slug is short, MAX_STAGE_LEN is headroom."""
    if not agrupamento_id or not agrupamento:
        raise ValueError("agrupamento é obrigatório (nomeia o produto e gera o agrupamento_id).")
    if len(agrupamento) > MAX_NOTE_LEN:
        raise ValueError(f"agrupamento excede {MAX_NOTE_LEN} caracteres.")
    if len(agrupamento_id) > MAX_STAGE_LEN:
        raise ValueError(f"agrupamento_id excede {MAX_STAGE_LEN} caracteres.")
    if descricao_produto is not None and len(descricao_produto) > MAX_NOTE_LEN:
        raise ValueError(f"descricao_produto excede {MAX_NOTE_LEN} caracteres.")


def _validate_group_registered(
    agrupamento: str | None, agrupamento_id: str | None, grupos: set[str]
) -> None:
    """E o agrupamento tem de EXISTIR no registro de grupos.

    Sem esta guarda, uma escrita pode apontar para um agrupamento_id que nenhum grupo
    respalda — e nada quebra: o catálogo aceita, a Gold materializa o id, e o produto some
    numa seção "Sem agrupamento registrado" que só um humano olhando a tela nota. Foi
    exatamente o que aconteceu em 2026-08-29: uma reorganização escreveu 37 entradas
    apontando para `lenha` e `carvao_vegetal`, grupos que nunca foram criados.

    A tela já sabia dizer "registrado"; o que faltava era isto recusar antes. O ``grupos``
    vazio (registro ainda não materializado) não bloqueia — não há o que conferir contra."""
    if grupos and agrupamento_id not in grupos:
        raise ValueError(
            f"O agrupamento {agrupamento!r} (id {agrupamento_id!r}) não existe no registro "
            "de agrupamentos. Crie-o primeiro — um produto apontando para um agrupamento "
            "inexistente fica fora de toda análise cruzada sem nenhum erro visível."
        )


def _preserve_omitted_fields(
    bq: bigquery.Client,
    table_fqn: str,
    codigo_produto: str,
    banco: str,
    *,
    is_active: bool,
    sidra_tabela: str | None,
    descricao_produto: str | None,
    ingestao: str | None,
    visibilidade: str | None,
) -> tuple[str | None, str | None, str, str]:
    """Fill in every field the caller OMITTED, reading the stored entry when there is one.

    This is one policy, not four coincidences — the writer's docstring states it: every
    field a researcher OWNS is preserve-on-omit. The write is an append-only whole-row
    overwrite, so a caller that sends only the field it means to change would otherwise
    NULL the rest. ``None`` means "leave it alone"; only an explicit value (including ``''``
    for the note) changes it. That makes a partial write from any client safe by
    construction, and it is why the four live together instead of scattered along the flow.

    Returns ``(sidra_tabela, descricao_produto, ingestao, visibilidade)``. Validation of the
    resulting tag stays with the CALLER: it is a gate, and a gate belongs in the main flow
    where it can be read.

    ``sidra_tabela`` preservation applies to every multi-table banco, not to a named one.
    It was once closed over ``banco == "ppm"`` and pevs escaped: an update that did not
    re-send the tag DROPPED it, moving the entry to the ``sql.SEM_TABELA`` sentinel — a
    produto that vanishes from both halves. That is the "conditional naming ONE banco"
    pattern: it encodes a census of the world, and the world grew when silviculture
    arrived."""
    if banco in _BANCOS_MULTI_TABELA and sidra_tabela is None and is_active:
        sidra_tabela = _current_sidra_tabela(bq, table_fqn, codigo_produto, banco)
    if descricao_produto is None and is_active:
        descricao_produto = _current_descricao(bq, table_fqn, codigo_produto, banco)
    # On an UPDATE, keeping what is stored (an unrelated edit must never un-hide a produto
    # or resume a paused one); on a NEW entry, the safe defaults — ingest it (that is why it
    # was registered) and show it (hiding is an explicit act).
    if ingestao is None or visibilidade is None:
        stored_ingestao, stored_visibilidade = (
            _current_lifecycle(bq, table_fqn, codigo_produto, banco) if is_active else (None, None)
        )
        # `is None`, não `or`: um `''` seria falsy e cairia no default. Hoje o chamador
        # normaliza `''` para None antes de chegar aqui, mas depender disso amarraria esta
        # função a uma linha quarenta acima — e "omitido" é o que None significa, não o que
        # falsy significa.
        if ingestao is None:
            ingestao = stored_ingestao or INGESTAO_ATIVA
        if visibilidade is None:
            visibilidade = stored_visibilidade or VISIBILIDADE_VISIVEL
    return sidra_tabela, descricao_produto, ingestao, visibilidade


def record_produto_catalog(
    codigo_produto: str,
    banco: str,
    headers: Mapping[str, str],
    *,
    agrupamento: str | None = None,
    descricao_produto: str | None = None,
    ciclo_de_vida: str | None = None,
    ingestao: str | None = None,
    visibilidade: str | None = None,
    agrupamento_id: str | None = None,
    sidra_tabela: str | None = None,
    change_id: str | None = None,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
    invalidate_cache: bool = True,
) -> dict:
    """Append one commodity-catalog edit (upsert by latest-wins). IAP author capture +
    read-after-write + optional ``change_id`` idempotency, mirroring the
    attribute-engineering writers. Each commodity is registered by its EXACT source code
    (no prefixes); ``agrupamento_id`` defaults to the agrupamento slug. ``sidra_tabela``
    (PPM only: '3939' herd / '74' animal) routes catalog-driven ingestion. Validates the
    key (numeric code), the agrupamento, and the sidra_tabela rule; a NEW code need NOT yet
    exist in Gold — it registers as *pendente de ingestão*.

    The lifecycle is TWO coded axes: ``ingestao`` (ativa|pausada — keep fetching?) and
    ``visibilidade`` (visivel|oculto — researcher sees it?). Omitting one on an UPDATE
    PRESERVES the stored value (see _current_lifecycle); a NEW entry defaults to
    ativa/visivel. ``ciclo_de_vida`` is the RETIRED prose enum: still accepted so an old
    client keeps working (it is translated into the axes), never written going forward.

    Every field a researcher OWNS is preserve-on-omit: the two axes, ``sidra_tabela`` and
    ``descricao_produto``. The write is an append-only whole-row overwrite, so a caller that
    sends only the field it means to change would otherwise NULL the rest — omitting a field
    means "leave it alone", and only an explicit value (including ``''`` for the note) changes
    it. That makes a partial write from any client safe by construction.

    Raises ValueError on a bad key / over-length / a bad sidra_tabela / an out-of-vocabulary
    lifecycle code."""
    cfg = settings or get_settings()
    codigo_produto = (codigo_produto or "").strip()
    banco = (banco or "").strip()
    ciclo_de_vida = ciclo_de_vida.strip() if ciclo_de_vida else ciclo_de_vida
    _validate_catalog_edit(codigo_produto, banco, ciclo_de_vida)
    ingestao = ingestao.strip() if ingestao else None
    visibilidade = visibilidade.strip() if visibilidade else None
    _validate_lifecycle(ingestao, visibilidade)
    # Back-compat: a client still sending the retired prose enum gets it translated onto the
    # visibility axis rather than rejected — the value it expressed is still meaningful.
    if visibilidade is None and ciclo_de_vida:
        visibilidade = _LEGACY_CICLO_TO_VISIBILIDADE.get(ciclo_de_vida)
    sidra_tabela = sidra_tabela.strip() if sidra_tabela else None
    # Reject a bad tag EARLY (no BQ round-trip): a single-table banco carrying one, or a
    # multi-table banco carrying a table that is not its own. Delegates to the one validator
    # rather than restating the rule — this check WAS a verbatim copy, and when pevs became
    # multi-table on 2026-08-29 only the copy in _validate_sidra_tabela was updated, so
    # every pevs stamp was still rejected with the old "só se aplica ao banco 'ppm'". The
    # mandatory-for-new-ppm half is enforced below, once new-vs-update is known.
    _validate_sidra_tabela(banco, sidra_tabela, cfg, require_for_ppm=False)
    agrupamento = agrupamento.strip() if agrupamento else agrupamento
    agrupamento_id = (agrupamento_id or _slug(agrupamento)).strip() or None
    _validate_agrupamento(agrupamento, agrupamento_id, descricao_produto)

    edited_by = author_email_from_headers(
        headers, dev_fallback=cfg.dev_author, audience=cfg.iap_audience
    )
    change_id, supplied = _resolve_change_id(change_id)
    bq = client or _bq_client(cfg)
    _validate_group_registered(agrupamento, agrupamento_id, _registered_group_ids(cfg, bq))
    table_fqn = _catalog_log_ref(cfg)
    ensure_produto_catalog_log_table(cfg, bq)

    # Whether this write UPDATES an already-active entry (vs a new registration).
    is_active = _is_active_entry(bq, table_fqn, codigo_produto, banco)
    # Validate the banco and note whether the code already has Gold data (a not-yet-
    # ingested code is accepted as *pendente de ingestão*). Read state AFTER ensure.
    _check_code_status(bq, table_fqn, codigo_produto, banco, is_active=is_active)
    sidra_tabela, descricao_produto, ingestao, visibilidade = _preserve_omitted_fields(
        bq,
        table_fqn,
        codigo_produto,
        banco,
        is_active=is_active,
        sidra_tabela=sidra_tabela,
        descricao_produto=descricao_produto,
        ingestao=ingestao,
        visibilidade=visibilidade,
    )
    # O portão fica AQUI, no fluxo principal, e não dentro do preservador: exigir a tag numa
    # entrada nova é uma recusa, e uma recusa tem de ser legível onde a escrita acontece.
    # Roda para todo banco — num de tabela única `_validate_sidra_tabela` só recusa uma tag
    # indevida, que a checagem antecipada lá em cima já teria pego.
    _validate_sidra_tabela(banco, sidra_tabela, cfg, require_for_ppm=not is_active)

    if supplied and _change_id_seen(bq, table_fqn, change_id):
        logger.info(
            "Catalog: duplicate change_id %s ignored (%s:%s)", change_id, banco, codigo_produto
        )
        # Return the STORED row (read-after-write consistency), not the retried request body.
        stored = _row_for_change_id(bq, table_fqn, change_id)
        # A change_id reused for a DIFFERENT produto — a chave INTEIRA, tabela SIDRA
        # inclusa — ou um flip record/remove não é replay seguro → 409 (não a linha
        # anterior errada). Sem a tabela, o mesmo change_id nas DUAS metades de um banco
        # multi-tabela passaria por replay e a segunda edição sumiria em silêncio. Uma
        # divergência só de atributos sob a mesma chave segue sendo no-op benigno
        # (seed_catalog_from_env depende disso).
        ensure_no_change_id_conflict(
            stored,
            {
                "codigo_produto": codigo_produto,
                "banco": banco,
                "sidra_tabela": sidra_tabela,
                "active": True,
            },
            ("codigo_produto", "banco", "sidra_tabela", "active"),
            entity="produto do catálogo",
        )
        if stored is not None:
            return stored
        return _catalog_row(  # fallback: stored row vanished (shouldn't happen)
            codigo_produto,
            banco,
            agrupamento,
            descricao_produto,
            None,
            agrupamento_id,
            True,
            edited_by,
            change_id,
            sidra_tabela=sidra_tabela,
            ingestao=ingestao,
            visibilidade=visibilidade,
            deduped=True,
        )
    _insert_catalog_row(
        bq,
        table_fqn,
        codigo_produto,
        banco,
        agrupamento,
        descricao_produto,
        # ciclo_de_vida is RETIRED: never written again. The axes carry the meaning, and
        # leaving it NULL keeps the legacy translation unambiguous (a row with BOTH would
        # invite the two to disagree).
        None,
        agrupamento_id,
        True,
        edited_by,
        change_id,
        sidra_tabela=sidra_tabela,
        ingestao=ingestao,
        visibilidade=visibilidade,
    )
    logger.info(
        "Catalog: %s:%s -> active (ingestao=%s, visibilidade=%s) by %s",
        banco,
        codigo_produto,
        ingestao,
        visibilidade,
        edited_by,
    )
    if invalidate_cache:
        invalidate_produto_catalog_cache()
    return _catalog_row(
        codigo_produto,
        banco,
        agrupamento,
        descricao_produto,
        None,
        agrupamento_id,
        True,
        edited_by,
        change_id,
        sidra_tabela=sidra_tabela,
        ingestao=ingestao,
        visibilidade=visibilidade,
        deduped=False,
    )


def remove_produto_catalog(
    codigo_produto: str,
    banco: str,
    headers: Mapping[str, str],
    *,
    change_id: str | None = None,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
    invalidate_cache: bool = True,
) -> dict:
    """Append an ``active=false`` TOMBSTONE — the entry leaves the catalog (its Gold
    data becomes an orphan, handled non-destructively by the lifecycle; NEVER auto-
    deleted). The historical rows stay; only the current state flips to removed."""
    cfg = settings or get_settings()
    codigo_produto = (codigo_produto or "").strip()
    banco = (banco or "").strip()
    _validate_catalog_edit(codigo_produto, banco, None)
    edited_by = author_email_from_headers(
        headers, dev_fallback=cfg.dev_author, audience=cfg.iap_audience
    )
    change_id, supplied = _resolve_change_id(change_id)
    bq = client or _bq_client(cfg)
    table_fqn = _catalog_log_ref(cfg)
    ensure_produto_catalog_log_table(cfg, bq)
    if supplied and _change_id_seen(bq, table_fqn, change_id):
        stored = _row_for_change_id(bq, table_fqn, change_id)
        # A reused change_id whose stored row has a different key / active state is not a safe
        # replay → 409 instead of echoing an unrelated row (mirrors record_produto_catalog).
        ensure_no_change_id_conflict(
            stored,
            {
                "codigo_produto": codigo_produto,
                "banco": banco,
                "sidra_tabela": _current_sidra_tabela(bq, table_fqn, codigo_produto, banco),
                "active": False,
            },
            ("codigo_produto", "banco", "sidra_tabela", "active"),
            entity="produto do catálogo",
        )
        if stored is not None:
            return stored
        return _catalog_row(  # fallback: stored row vanished (shouldn't happen)
            codigo_produto,
            banco,
            None,
            None,
            None,
            None,
            False,
            edited_by,
            change_id,
            deduped=True,
        )
    # A tombstone must reference a currently-ACTIVE entry (removing a never-cataloged key
    # would write a phantom tombstone → a false orphan). Orphan detection now keys off the
    # exact codigo_produto (no prefixes).
    if not _is_active_entry(bq, table_fqn, codigo_produto, banco):
        raise ValueError(
            f"{codigo_produto!r} não está cadastrada (ativa) em {banco!r} — nada a remover."
        )
    # A tabela SIDRA faz parte da CHAVE. Um tombstone sem ela não marca a entrada real:
    # marca a sentinela `sql.SEM_TABELA`, uma identidade à parte — e a entrada continuaria
    # ativa, com o delete reportando sucesso. Preservar a tag guardada é o que faz o
    # tombstone cair sobre o produto certo.
    _insert_catalog_row(
        bq,
        table_fqn,
        codigo_produto,
        banco,
        None,
        None,
        None,
        None,
        False,
        edited_by,
        change_id,
        sidra_tabela=_current_sidra_tabela(bq, table_fqn, codigo_produto, banco),
    )
    logger.info("Catalog: %s:%s -> removed (tombstone) by %s", banco, codigo_produto, edited_by)
    if invalidate_cache:
        invalidate_produto_catalog_cache()
    return _catalog_row(
        codigo_produto,
        banco,
        None,
        None,
        None,
        None,
        False,
        edited_by,
        change_id,
        deduped=False,
    )


def _insert_catalog_row(
    bq,
    table_fqn,
    codigo_produto,
    banco,
    agrupamento,
    descricao_produto,
    ciclo_de_vida,
    agrupamento_id,
    active,
    edited_by,
    change_id,
    *,
    sidra_tabela=None,
    ingestao=None,
    visibilidade=None,
) -> None:
    """Append one catalog row with a server-side timestamp (parameterized DML).

    New writes set the coded axes (ingestao/visibilidade) and leave the retired
    `ciclo_de_vida` NULL; readers translate the legacy prose on the rows that still
    carry it (visibilidade_efetiva / the catalog_visibilidade macro)."""
    sql = f"""
        insert into `{table_fqn}`
            (codigo_produto, banco, agrupamento, descricao_produto,
             ciclo_de_vida, ingestao, visibilidade, agrupamento_id, sidra_tabela,
             active, edited_by, edited_at, change_id)
        values
            (@codigo_produto, @banco, @agrupamento, @descricao_produto,
             @ciclo_de_vida, @ingestao, @visibilidade, @agrupamento_id, @sidra_tabela,
             @active, @edited_by, current_timestamp(), @change_id)
    """
    p = bigquery.ScalarQueryParameter
    params = [
        p("codigo_produto", "STRING", codigo_produto),
        p("banco", "STRING", banco),
        p("agrupamento", "STRING", agrupamento),
        p("descricao_produto", "STRING", descricao_produto),
        p("ciclo_de_vida", "STRING", ciclo_de_vida),
        p("ingestao", "STRING", ingestao),
        p("visibilidade", "STRING", visibilidade),
        p("agrupamento_id", "STRING", agrupamento_id),
        p("sidra_tabela", "STRING", sidra_tabela),
        p("active", "BOOL", active),
        p("edited_by", "STRING", edited_by),
        p("change_id", "STRING", change_id),
    ]
    bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


def _catalog_row(
    codigo_produto,
    banco,
    agrupamento,
    descricao_produto,
    ciclo_de_vida,
    agrupamento_id,
    active,
    edited_by,
    change_id,
    *,
    deduped,
    sidra_tabela=None,
    ingestao=None,
    visibilidade=None,
) -> dict:
    """The written/echoed catalog row dict (shared by the write + dedup paths).

    Echoes the EFFECTIVE axes so a client reading the response sees what the row now means,
    whether the value came from the request, from preservation, or from a legacy row."""
    return {
        "codigo_produto": codigo_produto,
        "banco": banco,
        "agrupamento": agrupamento,
        "descricao_produto": descricao_produto,
        "ciclo_de_vida": ciclo_de_vida,
        "ingestao": ingestao_efetiva(ingestao),
        "visibilidade": visibilidade_efetiva(visibilidade, ciclo_de_vida),
        "agrupamento_id": agrupamento_id,
        "sidra_tabela": sidra_tabela,
        "active": active,
        "edited_by": edited_by,
        "change_id": change_id,
        "deduped": deduped,
    }


def _row_for_change_id(bq, table_fqn: str, change_id: str) -> dict | None:
    """The STORED catalog-log row for ``change_id`` (change_id is unique per write, so this
    is THE row). Used to echo the ORIGINAL persisted values on an idempotent-retry dedup —
    read-after-write consistency: a retry reusing the key must return what was actually
    STORED, not the (possibly changed) new request body. None if not found."""
    sql = f"""
        select codigo_produto, banco, agrupamento, descricao_produto, ciclo_de_vida,
               ingestao, visibilidade, agrupamento_id, sidra_tabela, active, edited_by
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
    return _catalog_row(
        r["codigo_produto"],
        r["banco"],
        r["agrupamento"],
        r["descricao_produto"],
        r["ciclo_de_vida"],
        r["agrupamento_id"],
        bool(r["active"]),
        r["edited_by"],
        change_id,
        sidra_tabela=r["sidra_tabela"],
        ingestao=r["ingestao"],
        visibilidade=r["visibilidade"],
        deduped=True,
    )


def invalidate_produto_catalog_cache() -> None:
    """Drop the cached current-catalog read so the next query is fresh (best-effort).

    Also drops ``fetch_orphan_produtos``: the orphan worklist derives its tombstones
    from the SAME produto_catalog_log, so a catalog write (especially a removal) must
    refresh it too — otherwise the Descontinuados view lags read-after-write up to its TTL.
    Same reasoning for ``fetch_agrupamentos``: each group's ``n_members`` is computed from
    that same catalog log, so an add/remove must refresh the groups list too — otherwise
    the delete-blocking hint (n_members) lags read-after-write up to its TTL.
    """
    for fn in (
        gateway.fetch_produto_catalog,
        gateway.fetch_orphan_produtos,
        gateway.fetch_agrupamentos,
    ):
        try:
            cache.delete_memoized(fn)
        except Exception as exc:  # pragma: no cover - cache unbound / backend down
            logger.warning("Could not invalidate commodity-catalog cache: %s", exc)


def invalidate_catalog_editors_cache() -> None:
    """Drop the cached editor allowlist so an add/remove takes effect IMMEDIATELY,
    not after the ~30s classification-cache TTL. Critical for REVOCATION: a de-authorized
    editor must lose write access at once — otherwise they can keep POSTing successful
    (audit-logged) edits until the stale allowlist expires. Best-effort."""
    try:
        cache.delete_memoized(gateway.fetch_catalog_editors)
    except Exception as exc:  # pragma: no cover - cache unbound / backend down
        logger.warning("Could not invalidate catalog-editors cache: %s", exc)


# The env → catalog banco/sidra_tabela plan for catalog_authoritative_ingestion cutover.
def _seed_plan(cfg: Settings) -> list[tuple[str, str, str | None]]:
    """(banco, codigo_produto, sidra_tabela) for every configured IBGE env code — the
    exact set the catalog-driven resolver must reproduce on day one."""
    plan: list[tuple[str, str, str | None]] = []
    plan += [("pevs", c, None) for c in cfg.product_codes]
    plan += [("pam", c, None) for c in cfg.pam_product_codes_list]
    plan += [("ppm", c, cfg.ppm_herd_table_id) for c in cfg.ppm_herd_product_codes_list]
    plan += [("ppm", c, cfg.ppm_animal_table_id) for c in cfg.ppm_animal_product_codes_list]
    return plan


def seed_catalog_from_env(
    headers: Mapping[str, str],
    *,
    agrupamento_default: str | None = None,
    settings: Settings | None = None,
    client: bigquery.Client | None = None,
) -> dict:
    """Seed the catalog with the current IBGE ``*_PRODUCT_CODES`` env codes so the
    catalog-driven ingestion resolver reproduces them exactly (the cutover backfill for
    ``catalog_authoritative_ingestion``). Idempotent: a deterministic per-code ``change_id``
    makes a re-run a no-op. An already-cataloged code keeps its agrupamento; a NEW code uses
    ``agrupamento_default`` or falls back to the code itself (the researcher renames/groups
    it later). PPM codes are tagged with their ``sidra_tabela`` (herd/animal). Returns
    ``{seeded, skipped}``."""
    cfg = settings or get_settings()
    bq = client or _bq_client(cfg)
    existing: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    try:
        df = gateway.fetch_produto_catalog(None)
    except NotFound:
        df = None
    if df is not None and not df.empty:
        # Coerce pandas nulls (NaN floats / pd.NA) to None — a NULL agrupamento_id would
        # otherwise reach record_produto_catalog as a float and blow up on ``.strip()``.
        def _clean(v: object) -> str | None:
            return v.strip() or None if isinstance(v, str) else None

        for r in df.itertuples():
            existing[(str(r.banco), str(r.codigo_produto))] = (
                _clean(r.agrupamento),
                _clean(r.agrupamento_id),
            )

    seeded = skipped = 0
    for banco, code, sidra_tabela in _seed_plan(cfg):
        agr, agr_id = existing.get((banco, code), (None, None))
        agrupamento = agr or agrupamento_default or code
        rec = record_produto_catalog(
            code,
            banco,
            headers,
            agrupamento=agrupamento,
            agrupamento_id=agr_id,
            ciclo_de_vida=CICLO_DE_VIDA_VISIVEL,
            sidra_tabela=sidra_tabela,
            change_id=f"seed-from-env:{banco}:{code}:{sidra_tabela or '-'}",
            settings=cfg,
            client=bq,
            invalidate_cache=False,
        )
        if rec.get("deduped"):
            skipped += 1
        else:
            seeded += 1
    invalidate_produto_catalog_cache()
    return {"seeded": seeded, "skipped": skipped}
