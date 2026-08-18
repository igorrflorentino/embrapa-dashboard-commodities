"""Curadoria (catalog) seam readers/writers — what ENTERS and EXITS the dashboard.

The seam layer over ``serving/curation.py``: the current commodity catalog (for the
admin UI), the append-only upsert/remove writers (IAP author capture), and the
per-catalog editor allowlist. Reads degrade gracefully to an EMPTY catalog when the
log table doesn't exist yet (no catalog configured) — distinct from a transient
error, which propagates. Imports only the gateway (never ``seam``), so the import
graph stays acyclic; ``seam`` re-exports the public surface.

Not to be confused with ``seam_attribute_engineering`` (the FROZEN derived-columns
feature). This is the catalog the lead reserved the name "Curadoria" for.
"""

from __future__ import annotations

from google.api_core.exceptions import NotFound

from embrapa_dashboard.serving import gateway
from embrapa_dashboard.serving.curation import ingestao_efetiva, visibilidade_efetiva

PRODUTO_CATALOG_RESOURCE = "produto_catalog"


def _clean(x):
    """A NULL STRING cell reads back from BigQuery as float('nan'); normalize it to
    None so JSON serialization and the ``sorted(groups.items())`` grouping don't choke
    on a float mixed with strings (a catalog entry may legitimately have no
    agrupamento/descrição/ciclo)."""
    return None if (isinstance(x, float) and x != x) else x


# Catalog banco token → the long source id ``fetch_products`` expects, so the editor can
# show each code's ORIGINAL source description (IBGE product / NCM / HS6 name).
_BANCO_TO_SOURCE = {
    "pevs": "ibge_pevs",
    "pam": "ibge_pam",
    "ppm": "ibge_ppm",
    "comex": "mdic_comex",
    "comtrade": "un_comtrade",
}


def catalog_worklist(banco: str | None = None) -> dict:
    """The current commodity catalog (latest-wins, active) — backs the admin editor.

    Returns ``{entries, total, by_agrupamento}``; the per-Agrupamento grouping backs
    the lead's per-Agrupamento edit grain. Empty (not an error) before the catalog
    exists, so the editor renders before the first write."""
    try:
        df = gateway.fetch_produto_catalog(banco)
    except NotFound:
        # Log table genuinely absent (no catalog yet) — render empty. Any OTHER error
        # propagates instead of being masked as "not configured".
        return {"entries": [], "total": 0, "by_agrupamento": []}
    if df is None or df.empty:
        return {"entries": [], "total": 0, "by_agrupamento": []}
    entries = [
        {
            "codigo_produto": str(r.codigo_produto),
            "banco": r.banco,
            "agrupamento": _clean(r.agrupamento),
            "descricao_produto": _clean(r.descricao_produto),
            "ciclo_de_vida": _clean(r.ciclo_de_vida),
            # The two lifecycle axes, always EFFECTIVE: a legacy row (prose ciclo_de_vida,
            # both columns NULL) is translated here exactly as the dbt gate translates it,
            # so the editor and the researcher-facing gate can never disagree about whether
            # a produto is hidden.
            "ingestao": ingestao_efetiva(getattr(r, "ingestao", None)),
            "visibilidade": visibilidade_efetiva(getattr(r, "visibilidade", None), r.ciclo_de_vida),
            "agrupamento_id": _clean(r.agrupamento_id),
            # PPM herd/animal SIDRA-table tag (NULL for single-table bancos) — echoed back
            # so an inline re-save carries the real value instead of relying solely on the
            # writer's server-side preservation.
            "sidra_tabela": _clean(getattr(r, "sidra_tabela", None)),
        }
        for r in df.itertuples()
    ]
    # Attach the source's ORIGINAL product description per (banco, codigo) — the name the
    # source (IBGE/COMEX/Comtrade) gives that code — so a bare numeric code isn't opaque.
    # Read once per source (memoized). UNGATED (fetch_source_products_gold, straight from
    # Gold) — NOT fetch_products, whose serving marts apply the F7 visibility gate: the admin
    # editor must see a hidden-but-active product's description too, else it would read "—"
    # (falsely "sem descrição / não ingerido") while the Linhas/Período columns show its data.
    source_names: dict[str, dict] = {}
    for b in {e["banco"] for e in entries}:
        src = _BANCO_TO_SOURCE.get(b)
        if not src:
            continue
        try:
            pdf = gateway.fetch_source_products_gold(src)
        except NotFound:
            continue
        if pdf is not None and not pdf.empty:
            source_names[b] = {str(p.code): p.name for p in pdf.itertuples()}
    for e in entries:
        e["descricao_fonte"] = source_names.get(e["banco"], {}).get(e["codigo_produto"])
    groups: dict = {}
    for e in entries:
        groups.setdefault(e["agrupamento"] or "—", []).append(e)
    by_agrupamento = [
        {"agrupamento": k, "n": len(v), "bancos": sorted({e["banco"] for e in v})}
        for k, v in sorted(groups.items())
    ]
    return {"entries": entries, "total": len(entries), "by_agrupamento": by_agrupamento}


def source_codes(banco: str) -> dict:
    """The source's real product codes (+ names) for ONE banco token — backs the add
    form's autocomplete and the client-side "já existe na Gold?" advisory hint (a code
    absent from the list is still accepted as *pendente de ingestão*; the server does NOT
    reject it). Empty when the banco is unknown or its products table isn't built."""
    src = _BANCO_TO_SOURCE.get((banco or "").strip())
    if src is None:
        return {"banco": banco, "codes": []}
    try:
        # UNGATED (straight from Gold): the admin add form must autocomplete every real
        # source code, including one a researcher marked "indisponível" (F7) — the gate
        # applies to researcher-facing views, never to the catalog editor.
        df = gateway.fetch_source_products_gold(src)
    except NotFound:
        return {"banco": banco, "codes": []}
    if df is None or df.empty:
        return {"banco": banco, "codes": []}
    codes = [
        # _clean maps a NULL name (float NaN from BigQuery) to None → "" (never the literal
        # string "nan"), so the datalist option label is empty rather than misleading.
        {"code": str(p.code), "name": str(_clean(getattr(p, "name", None)) or "")}
        for p in df.itertuples()
    ]
    return {"banco": banco, "codes": codes}


def catalog_status() -> dict:
    """Per-commodity Gold STATE for every cataloged (banco, code): row count + reference-
    year span. Backs the catalog's status columns. One cheap aggregate per source that has
    catalog entries (cached); a cataloged code with no Gold rows reports n_rows=0 /
    has_data=False (a registered-but-empty commodity). Keyed ``"<banco>:<code>"``."""
    import collections

    try:
        df = gateway.fetch_produto_catalog(None)
    except NotFound:
        return {"status": {}}
    if df is None or df.empty:
        return {"status": {}}
    by_banco: dict[str, set] = collections.defaultdict(set)
    for r in df.itertuples():
        by_banco[r.banco].add(str(r.codigo_produto))
    status: dict[str, dict] = {}
    for banco, codes in by_banco.items():
        try:
            sdf = gateway.fetch_source_code_stats(banco)
        except NotFound:
            continue
        stat = (
            {str(r.code): r for r in sdf.itertuples()} if sdf is not None and not sdf.empty else {}
        )
        for code in codes:
            s = stat.get(code)
            # _clean(x) is None both for SQL NULL and a pandas float NaN (a plain
            # ``is not None`` would let a NaN through to int() → ValueError).
            year_start = _clean(s.year_start) if s is not None else None
            year_end = _clean(s.year_end) if s is not None else None
            status[f"{banco}:{code}"] = {
                "n_rows": int(s.n_rows) if s is not None else 0,
                "year_start": int(year_start) if year_start is not None else None,
                "year_end": int(year_end) if year_end is not None else None,
                "has_data": bool(s is not None and s.n_rows),
            }
    return {"status": status}


def record_catalog_entry(payload: dict) -> dict:
    """Upsert one catalog entry from a request body. Author from the IAP header (dev
    fallback per config). Wraps the verified writer; raises ValueError on a bad key /
    over-length / an invalid banco or ciclo / a missing PPM sidra_tabela (→ HTTP 400). A
    code absent from the source's Gold is NOT rejected — it registers as *pendente de
    ingestão*."""
    from flask import has_request_context, request

    from embrapa_dashboard.serving import curation

    headers = dict(request.headers) if has_request_context() else {}
    return curation.record_produto_catalog(
        payload.get("codigo_produto"),
        payload.get("banco"),
        headers,
        agrupamento=payload.get("agrupamento"),
        descricao_produto=payload.get("descricao_produto"),
        ciclo_de_vida=payload.get("ciclo_de_vida"),
        # The two lifecycle axes. Omitting one PRESERVES the stored value server-side,
        # so a partial edit can never silently un-hide or un-pause a produto.
        ingestao=payload.get("ingestao"),
        visibilidade=payload.get("visibilidade"),
        agrupamento_id=payload.get("agrupamento_id"),
        # PPM (SIDRA tables 3939/74) routes catalog-driven ingestion by sidra_tabela;
        # the writer requires it for a new PPM entry — a dropped value 400s the save.
        sidra_tabela=payload.get("sidra_tabela"),
        change_id=payload.get("change_id"),
    )


def remove_catalog_entry(payload: dict) -> dict:
    """Append an active=false tombstone for one (codigo_produto, banco) — the entry
    leaves the catalog (NON-destructive: the Gold data becomes an orphan, never
    auto-deleted). Author from the IAP header."""
    from flask import has_request_context, request

    from embrapa_dashboard.serving import curation

    headers = dict(request.headers) if has_request_context() else {}
    return curation.remove_produto_catalog(
        payload.get("codigo_produto"),
        payload.get("banco"),
        headers,
        change_id=payload.get("change_id"),
    )


def group_worklist() -> dict:
    """The current commodity GROUPS (agrupamentos) registry — id, name and a live count
    of active catalog members (0 = an empty group; the UI blocks deleting a non-empty
    one). Backs the group-management UI. Empty (not an error) before the registry exists."""
    try:
        df = gateway.fetch_agrupamentos()
    except NotFound:
        return {"groups": [], "total": 0}
    if df is None or df.empty:
        return {"groups": [], "total": 0}
    groups = [
        {
            "group_id": r.group_id,
            "group_name": r.group_name,
            "n_members": int(r.n_members),
        }
        for r in df.itertuples()
    ]
    return {"groups": groups, "total": len(groups)}


def record_group(payload: dict) -> dict:
    """Create (group_id omitted) or RENAME (group_id given) a group. Author from the IAP
    header. Raises ValueError on a bad/duplicate name (→ HTTP 400)."""
    from flask import has_request_context, request

    from embrapa_dashboard.serving import agrupamentos

    headers = dict(request.headers) if has_request_context() else {}
    return agrupamentos.record_group(
        payload.get("group_name"),
        headers,
        group_id=payload.get("group_id"),
        change_id=payload.get("change_id"),
    )


def remove_group(payload: dict) -> dict:
    """Tombstone (delete) a group — rejected while it still has active members. Author
    from the IAP header. Raises ValueError (→ HTTP 400) when non-empty or absent."""
    from flask import has_request_context, request

    from embrapa_dashboard.serving import agrupamentos

    headers = dict(request.headers) if has_request_context() else {}
    return agrupamentos.delete_group(
        payload.get("group_id"),
        headers,
        change_id=payload.get("change_id"),
    )


def catalog_editor_emails(resource: str = PRODUTO_CATALOG_RESOURCE) -> set[str]:
    """Lowercased editor emails authorized for a catalog resource; empty set when the
    allowlist table is absent (open by default). Any OTHER error propagates — a
    transient BQ/permission fault must NOT silently widen the gate to everyone."""
    try:
        df = gateway.fetch_catalog_editors(resource)
    except NotFound:
        return set()
    if df is None or df.empty:
        return set()
    return {str(e).strip().lower() for e in df["email"] if e}


def orphan_worklist() -> dict:
    """Orphan commodities — removed from the catalog with Gold data still lingering —
    overlaid with their Descontinuado lifecycle status (flagged date + deletion warning).
    Backs the editor's "Descontinuados" section. Empty (not an error) before any catalog
    exists. The orphan IS descontinuado by definition; ``flagged_at`` is None until the
    auto-marker has recorded it (the doctor/CLI cadence)."""
    from embrapa_dashboard.serving.catalog_lifecycle import PURGE_WARNING

    try:
        orphans = gateway.fetch_orphan_produtos()
    except NotFound:
        orphans = None
    if orphans is None or orphans.empty:
        return {"orphans": [], "total": 0}
    try:
        status_df = gateway.fetch_lifecycle_status()
        status = (
            {(r.element_kind, r.banco, str(r.code)): r for r in status_df.itertuples()}
            if status_df is not None and not status_df.empty
            else {}
        )
    except NotFound:
        status = {}
    rows = []
    for o in orphans.itertuples():
        code = str(o.codigo_produto)
        st = status.get(("commodity", o.banco, code))
        rows.append(
            {
                "codigo_produto": code,
                "banco": o.banco,
                "agrupamento": _clean(o.agrupamento),
                # Honor the recorded status: a re-orphaned, already-purged code reads
                # 'purged', not a hardcoded 'descontinuado'. None until the marker runs.
                "status": (st.status if st is not None else "descontinuado"),
                "flagged_at": str(st.flagged_at) if st is not None else None,
                # 'purged' events carry no purge note → fall back to the standing warning.
                "warning": (
                    st.scheduled_purge_note
                    if (st is not None and st.scheduled_purge_note)
                    else PURGE_WARNING
                ),
            }
        )
    return {"orphans": rows, "total": len(rows)}


def catalog_driven_bancos() -> list[str]:
    """Banco tokens whose INGESTION a catalog edit actually steers, right now.

    Two conditions, both required: the banco must be one the IBGE pipelines resolve
    through ``catalog_resolver`` (COMEX/COMTRADE read their scope from config, so a
    catalog entry there never triggers a fetch), AND the
    ``catalog_authoritative_ingestion`` flag must be ON (with it off, even the IBGE
    pipelines fall back to the env codes).

    The editor UI keys its "será buscado na próxima ingestão" wording off this list, so
    it stops promising an ingestion that will never come. Empty list = the catalog is
    documentation only, for every banco."""
    from embrapa_dashboard.config import get_settings
    from embrapa_dashboard.ibge.catalog_resolver import CATALOG_DRIVEN_BANCOS

    try:
        authoritative = get_settings().catalog_authoritative_ingestion
    except Exception:
        # Settings unbuildable (no .env / missing GCP_PROJECT_ID — CI, a fresh worktree).
        # Degrade to "promise nothing" rather than raise: this is a cosmetic affordance
        # riding on a READ endpoint, and a 400 here would blank the whole editor. Failing
        # CLOSED is also the honest direction — if we cannot tell whether the catalog
        # steers ingestion, we must not claim that it does.
        return []
    if not authoritative:
        return []
    return list(CATALOG_DRIVEN_BANCOS)
