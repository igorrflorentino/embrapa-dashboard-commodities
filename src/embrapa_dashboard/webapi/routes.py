"""``/api`` blueprint — thin REST wrappers over the serving BFF seam.

Each endpoint wraps an existing ``seam`` function and serializes (via
``serializers``) to the exact shape the prototype's ``contracts.js`` defines, so
the reused React views fetch these instead of computing synthetically. Same
Pushdown model underneath — parameterized BigQuery, memoized by flask-caching.

See ``PLANS/react_migration_contract_map.md`` §1 for the endpoint table. The
data-blocked producers (chain/lag) have no endpoint — the views ship honest
placeholders. (market-nature IS live now — seed-driven, /api/cross/market-nature.)
"""

from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, HTTPException

from embrapa_dashboard.config import get_settings
from embrapa_dashboard.serving.cache import cache
from embrapa_dashboard.serving.curation import ensure_catalog_editors_table
from embrapa_dashboard.serving.feedback import FeedbackValidationError, record_feedback
from embrapa_dashboard.serving.iap import InvalidIapAssertionError
from embrapa_dashboard.serving.research_inputs import (
    ChangeIdConflictError,
    ensure_attribute_editors_table,
    ensure_banco_metadata_table,
)

from . import seam, serializers
from .auth import current_author
from .format import _CORRECTION_INFIX, _CURRENCY_SUFFIX

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__)


# Canonical convention vocabularies (the keys monetary_column matches on). Read
# straight from the format maps — not duplicated — so a new currency/correction
# stays validated automatically. Keys are case-sensitive exact-match (e.g.
# "IPCA"), so a typo or wrong case must 400 here instead of silently deflating
# with the BRL/IPCA fallback in monetary_column.
_ALLOWED_CURRENCIES = frozenset(_CURRENCY_SUFFIX)
_ALLOWED_CORRECTIONS = frozenset(_CORRECTION_INFIX)


def _conversion_or_400():
    """Parse + validate the currency/correction query params into a conv dict.

    Returns ``(conv, None)`` when both are valid (defaulting to BRL/IPCA when
    absent), else ``(None, (response, 400))`` with a pt-BR error naming the bad
    value. Without this, an invalid value silently falls back to BRL/IPCA inside
    monetary_column, so the user sees the wrong deflated series with no signal."""
    currency = request.args.get("currency", "BRL")
    correction = request.args.get("correction", "IPCA")
    if currency not in _ALLOWED_CURRENCIES:
        return None, (jsonify(error=f"moeda inválida: {currency!r}"), 400)
    if correction not in _ALLOWED_CORRECTIONS:
        return None, (jsonify(error=f"correção inválida: {correction!r}"), 400)
    return {"currency": currency, "correction": correction}, None


# Trade-direction vocabulary the gateway binds (sql._flow). 'all'/absent sums every flow.
# Values are the readable `flow` tokens produced in silver_comtrade_flows — hyphenated
# 're-export'/'re-import', matching the Gold/serving data verbatim so the bound
# `flow = @flow` predicate hits real rows (the frontend previously sent underscore
# 're_export' → zero rows AND was rejected here). COMEX exposes only export/import;
# Comtrade adds the two re-flows (both present in gold_comtrade_flows). The six detailed
# UN regimes (DX/FM/MIP/MOP/XIP/XOP) join this set once a re-ingestion with the widened
# COMTRADE_FLOWS lands their rows in Gold.
_ALLOWED_FLOWS = frozenset({"export", "import", "re-export", "re-import", "all"})


def _flow_or_400(flow: str | None):
    """Validate the optional trade ``flow`` query param. Returns ``(flow, None)`` for a
    valid value (None/absent passes through), else ``(None, (response, 400))`` with a pt-BR
    error. Mirrors ``_conversion_or_400``: without this, a typo like ``flow=Exportacao``
    binds verbatim, matches zero rows and returns an empty-but-200 result with no signal."""
    if flow and flow not in _ALLOWED_FLOWS:
        return None, (jsonify(error=f"fluxo inválido: {flow!r}"), 400)
    return flow, None


def _customs_or_400(customs: str | None):
    """Validate the optional customs-procedure param (regime aduaneiro; the COMTRADE
    server-side regime filter). UN customsCode is 'C' + two digits (C00 = total / todos
    os regimes); 'all'/absent passes through (→ sum every regime). A malformed value 400s
    rather than binding verbatim and matching zero rows (mirrors _flow_or_400). The value
    is bound as a query param downstream, so this guards typos, not injection."""
    if (
        customs
        and customs != "all"
        and not (len(customs) == 3 and customs[0] == "C" and customs[1:].isdigit())
    ):
        return None, (jsonify(error=f"regime aduaneiro inválido: {customs!r}"), 400)
    return customs, None


# Tipo de mercado (economic purpose) the seed classifies — the COMTRADE server-side market
# filter. 'all'/absent sums every purpose.
_ALLOWED_MARKETS = frozenset({"consumo", "processamento", "all"})


def _market_or_400(market: str | None):
    """Validate the optional tipo-de-mercado param (consumo/processamento; the COMTRADE
    server-side market filter). 'all'/absent passes through. A value outside the seed's
    market ids 400s rather than binding verbatim and matching zero rows (mirrors
    _flow_or_400)."""
    if market and market not in _ALLOWED_MARKETS:
        return None, (jsonify(error=f"tipo de mercado inválido: {market!r}"), 400)
    return market, None


def _json_object() -> dict:
    """Return the request's JSON body as a dict, or raise ValueError → HTTP 400.

    ``request.get_json(silent=True) or {}`` alone accepts a JSON array/string/number
    body (all truthy), which then AttributeErrors on ``.get`` → an opaque 500. A
    non-object body is client garbage, so 400 it with a pt-BR reason (via the
    ValueError→400 errorhandler) instead of masquerading as a server fault."""
    body = request.get_json(silent=True)
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ValueError("o corpo da requisição deve ser um objeto JSON")
    return body


def _coerce_str_fields(body: dict, *keys: str, keep_blank: tuple[str, ...] = ()) -> None:
    """Coerce the named body fields to stripped str in place (leaving None/absent as None).

    A non-string scalar (e.g. a numeric code sent as a JSON number — the codes ARE
    numeric) would AttributeError on ``.strip()`` deep in the serving writers → an opaque
    500. Coercing to str here keeps the writers' string contract; a truly absent field
    stays None so the route's own "is required" check still fires a clean 400. A blank
    string collapses to None so a whitespace-only field reads as absent.

    ``keep_blank`` names the fields where blank is a REAL VALUE, not an absence. It exists
    for ``descricao_produto``: since the writer began preserving an omitted note (so an
    unrelated edit cannot erase it), ``None`` means "leave it alone" — and collapsing ``''``
    to ``None`` therefore made the researcher's note IMPOSSIBLE TO CLEAR through the UI,
    which sends exactly that when the ✎ field is emptied. The two meanings must stay
    distinct end to end: absent = keep, ``''`` = erase."""
    for k in keys:
        v = body.get(k)
        if v is None:
            continue
        s = str(v).strip()
        body[k] = s if (s or k in keep_blank) else None


@api.errorhandler(ValueError)
def _api_value_error(exc):
    """Client-input validation errors → HTTP 400 (not 500). The serving writers raise
    ValueError with a caller-facing reason (pt-BR for the catalog writers: a bad key, an
    over-length field, an invalid ciclo/banco, a missing PPM sidra_tabela). Surface that reason
    verbatim so the user can self-correct — a generic "check the fields" hides WHY. ValueError
    here is always our own validation; an arbitrary internal fault is an Exception → the 500
    handler, never this path — so the message is safe to return."""
    logger.info("Invalid input on %s: %s", request.path, exc)
    return jsonify(error=str(exc) or "Dados inválidos."), 400


@api.errorhandler(ChangeIdConflictError)
def _api_change_id_conflict(exc):
    """A reused idempotency change_id pointing at a DIFFERENT stored row → HTTP 409 Conflict
    (distinct from the ValueError→400 validation path). Surface the pt-BR reason so the client
    regenerates the change_id instead of silently receiving an unrelated prior row."""
    logger.info("change_id conflict on %s: %s", request.path, exc)
    return jsonify(error=str(exc) or "Conflito de idempotência (change_id)."), 409


@api.errorhandler(Exception)
def _api_error(exc):
    """Always emit parseable JSON from /api. Flask's default HTML 500 would make
    the SPA's fetch layer fail to parse and (without a client retry cap) loop;
    JSON keeps every error machine-readable. HTTP errors keep their status code."""
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description, code=exc.code), exc.code
    logger.exception("Unhandled error on %s", request.path)
    # End-user-facing (the SPA surfaces this string) → pt-BR.
    return jsonify(error="Erro interno do servidor. Tente novamente."), 500


def _ensure_attribute_editors_table() -> bool:
    """Self-heal the Console-managed attribute editor allowlist table.

    Create it idempotently on the first authorization check — mirroring how the
    append-only log writers self-heal their own tables — so the runbook's
    "auto-creates on first use" promise holds. Returns True when ensured, False on
    failure (BQ down / perms). Like the catalog twin: an empty read is trustworthy as
    "open mode" ONLY when we could confirm the table (ensured=True); if ensuring FAILED
    and the allowlist reads empty, the caller fails CLOSED instead of admitting everyone.
    """
    try:
        ensure_attribute_editors_table()
        return True
    except Exception:  # pragma: no cover - BQ unavailable / perms
        logger.warning("Could not ensure attribute editors allowlist table", exc_info=True)
        return False


def _ensure_banco_metadata_table() -> None:
    """Self-heal the Console-managed banco-metadata override table (best-effort).

    The override read (``seam.banco_metadata_overrides``) treats a missing table as
    "no overrides" (registry defaults stand), so an operator following the runbook's
    documented MERGE to flip a maturity would otherwise hit "table not found". Create
    it idempotently on the first source-meta read — like the attribute editors table — so the
    "auto-creates on first use" promise holds. Best-effort: a transient BQ/permission
    fault must never break the provenance read (an absent table is just no overrides).
    """
    try:
        ensure_banco_metadata_table()
    except Exception:  # pragma: no cover - BQ unavailable / perms; never block the read
        logger.warning("Could not ensure banco metadata override table", exc_info=True)


def _ensure_catalog_editors_table() -> bool:
    """Self-heal the Console-managed per-catalog editor allowlist.

    Returns True when the table exists / was ensured, False when ensuring FAILED
    (BQ down / perms). A False matters: the allowlist read treats an ABSENT table as
    "no allowlist → open mode", so if we could NOT confirm the table's state, an empty
    read is UNTRUSTWORTHY — the caller must fail CLOSED, not silently admit everyone
    (a perms misconfig that leaves the table uncreatable must not read as open mode).
    """
    try:
        ensure_catalog_editors_table()
        return True
    except Exception:  # pragma: no cover - BQ unavailable / perms
        logger.warning("Could not ensure catalog editors allowlist table", exc_info=True)
        return False


def _authorize_attribute_editor():
    """Resolve the IAP author and enforce the attribute editor allowlist (authorization).

    Returns ``(author, None)`` when authorized, else ``(None, (response, status))``:
    403 for a forged/invalid IAP assertion or a non-allowlisted author, 401 when
    no trustworthy identity is present at all. The effective allowlist is the
    UNION of the env var (``Settings.attribute_editors_allowed_emails``) and the
    Console-managed ``research_inputs.attribute_editors`` table; BOTH empty/absent (default)
    preserves the current "any IAP-authenticated caller may curate" behaviour.
    """
    try:
        author = current_author()
    except InvalidIapAssertionError as exc:
        # The message is either our own fail-closed misconfig hint ("set IAP_AUDIENCE")
        # or a google-auth verification reason. Both reach ONLY an IAP-authenticated
        # caller (no secret/token is ever echoed — the JWT itself is not), and the
        # IAP_AUDIENCE hint is a deliberately-surfaced operator deployment aid, so it is
        # returned verbatim by design (audit SEC-3: kept, info-level, no secret leak).
        return None, (jsonify(error=str(exc)), 403)
    except PermissionError as exc:  # MissingAuthorError (+ any other) → no identity
        return None, (jsonify(error=str(exc)), 401)
    # Auto-create the allowlist table on first use so the runbook's Console INSERT
    # path is real (the read below then finds an empty table → open mode).
    ensured = _ensure_attribute_editors_table()
    allowed = (
        set(get_settings().attribute_editors_allowed_emails_list) | seam.attribute_editor_emails()
    )
    if not allowed:
        # Open mode is trustworthy only if we could confirm the table (ensured=True);
        # a can't-create failure must fail CLOSED, not silently admit everyone.
        if not ensured:
            return None, (
                jsonify(
                    error="Lista de editores de atributos indisponível no momento. Tente novamente."
                ),
                503,
            )
        return author, None  # genuine open mode
    if author.lower() not in allowed:
        return None, (jsonify(error="Você não tem autorização para editar atributos."), 403)
    return author, None


def _catalog_editor_allowlist(resource: str) -> set[str]:
    """The effective editor allowlist for ``resource``: the UNION of the env override
    (``CATALOG_EDITORS_ALLOWED_EMAILS``) and the Console-managed
    ``research_inputs.catalog_editors`` table — exact parity with the attribute editor path.
    Empty (both absent) → open by default."""
    return set(get_settings().catalog_editors_allowed_emails_list) | seam.catalog_editor_emails(
        resource
    )


def _authorize_catalog_editor(resource: str):
    """Resolve the IAP author and enforce the PER-CATALOG editor allowlist
    (``research_inputs.catalog_editors`` scoped to ``resource``, UNIONed with the env
    override ``CATALOG_EDITORS_ALLOWED_EMAILS``) — each cadastro has its OWN list (the
    lead's decision). Same 401/403 contract as ``_authorize_attribute_editor``; an empty/absent
    allowlist preserves "any IAP-authenticated caller may edit"."""
    try:
        author = current_author()
    except InvalidIapAssertionError as exc:
        return None, (jsonify(error=str(exc)), 403)
    except PermissionError as exc:
        return None, (jsonify(error=str(exc)), 401)
    ensured = _ensure_catalog_editors_table()
    allowed = _catalog_editor_allowlist(resource)
    if not allowed:
        # Empty allowlist = "open mode" BY DESIGN — but only trustworthy if we could
        # confirm the table's state. If ensuring it FAILED (BQ/perms), an empty read
        # cannot be distinguished from "allowlist unavailable" → fail CLOSED rather
        # than admit everyone. (A transient read error already 503s above via the
        # propagating gateway read; this covers the absent-table-because-can't-create case.)
        if not ensured:
            # End-user-facing (shown in the SPA status banner) → pt-BR.
            return None, (
                jsonify(error="Lista de editores indisponível no momento. Tente novamente."),
                503,
            )
        return author, None  # genuine open mode (ensured empty table)
    if author.lower() not in allowed:
        return None, (
            jsonify(error="Você não tem autorização para editar este cadastro."),
            403,
        )
    return author, None


def _catalog_can_edit(resource: str) -> bool:
    """Whether the current IAP caller MAY edit this catalog — the same union the write
    path enforces (env override | ``catalog_editors`` table). Purely a UX affordance for
    the SPA (disable/hide controls); the POST handlers stay authoritative (they 403 on a
    stale ``true``). Best-effort: no trustworthy identity or a lookup fault → ``False``
    (hide the controls). An empty allowlist means open → any IAP caller returns ``True``."""
    try:
        author = current_author()
    except Exception:
        return False
    try:
        allowed = _catalog_editor_allowlist(resource)
    except Exception:
        return False
    return (not allowed) or (author.lower() in allowed)


@api.get("/me")
def me():
    """The session identity the dashboard attributes this user's writes to — the
    IAP-authenticated email (the cryptographically verified JWT in prod behind IAP;
    the ``DEV_AUTHOR`` fallback locally). Best-effort: returns
    ``{email: null, authenticated: false}`` when no trustworthy identity is present
    (e.g. local dev with no DEV_AUTHOR set) rather than erroring — the SPA just shows
    an anonymous state. This is display-only; every write still re-resolves the author
    server-side and is authoritative."""
    try:
        author = current_author()
    except Exception:
        return jsonify(email=None, authenticated=False)
    return jsonify(email=author, authenticated=True)


# ── catalog + provenance ──────────────────────────────────────────────────────


@api.get("/catalog")
def catalog():
    """Crosswalk commodity catalog (agrupamento_id → {name, family, pevs[], comex[], comtrade[]}).

    ``family`` (PEVS physical-unit family) lets the frontend family-gate the cross
    pickers so the export-coefficient / price-spread views offer only mass commodities."""
    return jsonify(seam.produto_catalog_with_family())


# ── Curadoria (catalog — what enters/exits the dashboard) ──────────────────────


@api.get("/catalog/entries")
def catalog_entries():
    """The current commodity catalog (latest-wins, active) — backs the admin editor.
    Optionally scoped to one banco (?banco=). Empty (not an error) before the catalog
    exists. Reading is open behind IAP; only WRITES require the editor allowlist."""
    banco = request.args.get("banco") or None
    payload = serializers.serialize_catalog_worklist(seam.catalog_worklist(banco))
    # UX affordance: tell the SPA whether to enable the edit controls. The write
    # endpoints stay authoritative (403 on a stale true), so this can never widen access.
    payload["can_edit"] = _catalog_can_edit(seam.PRODUTO_CATALOG_RESOURCE)
    # Which bancos a catalog edit actually STEERS (see seam.catalog_driven_bancos). The
    # editor used to promise "será buscado na próxima ingestão" for every banco, which is
    # false for COMEX/COMTRADE (scope comes from config, not the catalog) and false for
    # ALL of them when catalog_authoritative_ingestion is off.
    payload["catalog_driven_bancos"] = seam.catalog_driven_bancos()
    return jsonify(payload)


@api.get("/catalog/source-codes")
def catalog_source_codes():
    """The source's REAL product codes (+ names) for one banco (?banco=) — backs the add
    form's code autocomplete + the client-side "já existe na Gold?" advisory hint. Empty
    when the banco is unknown / its products table isn't built."""
    return jsonify(seam.source_codes(request.args.get("banco") or ""))


@api.get("/catalog/status")
def catalog_status():
    """Per-commodity Gold state (row count + reference-year span) for every cataloged
    (banco, code) — backs the catalog's status columns. Cheap (one cached aggregate per
    source with entries)."""
    return jsonify(seam.catalog_status())


@api.post("/catalog/entry")
def catalog_entry_upsert():
    """Upsert one commodity-catalog entry (the editable successor to the
    commodity_crosswalk seed). Author captured from the IAP header; 401/403 via the
    per-catalog editor allowlist. A bad key / over-length / invalid ciclo/banco /
    missing PPM sidra_tabela → 400."""
    author, err = _authorize_catalog_editor(seam.PRODUTO_CATALOG_RESOURCE)
    if err:
        return err
    body = _json_object()
    # Coerce the string fields to str so a numeric value sent as a JSON number
    # (the codes ARE numeric) doesn't AttributeError on ``.strip()`` / ``len()`` in the writer.
    _coerce_str_fields(
        body,
        "codigo_produto",
        "banco",
        "agrupamento",
        "agrupamento_id",
        "descricao_produto",
        "ciclo_de_vida",
        "ingestao",
        "visibilidade",
        "sidra_tabela",
        "change_id",
        # '' on the note means "erase it", not "absent" — see keep_blank.
        keep_blank=("descricao_produto",),
    )
    if not (body.get("codigo_produto") and body.get("banco")):
        return jsonify(error="codigo_produto e banco são obrigatórios (a chave do catálogo)."), 400
    logger.info(
        "catalog upsert by %s: %s/%s", author, body.get("banco"), body.get("codigo_produto")
    )
    return jsonify(seam.record_catalog_entry(body))


@api.post("/catalog/entry/remove")
def catalog_entry_remove():
    """Remove one commodity-catalog entry — appends an active=false TOMBSTONE
    (NON-destructive: the Gold data becomes an orphan, handled by the lifecycle, never
    auto-deleted). 401/403 via the per-catalog editor allowlist."""
    author, err = _authorize_catalog_editor(seam.PRODUTO_CATALOG_RESOURCE)
    if err:
        return err
    body = _json_object()
    _coerce_str_fields(body, "codigo_produto", "banco", "change_id")
    if not (body.get("codigo_produto") and body.get("banco")):
        return jsonify(error="codigo_produto e banco são obrigatórios (a chave do catálogo)."), 400
    logger.info(
        "catalog remove by %s: %s/%s", author, body.get("banco"), body.get("codigo_produto")
    )
    return jsonify(seam.remove_catalog_entry(body))


@api.get("/catalog/orphans")
def catalog_orphans():
    """Orphan commodities — removed from the catalog with Gold data still lingering —
    marked Descontinuado, each with a deletion warning. Read-only detection (open behind
    IAP); the physical purge is a SEPARATE human-gated, backup-first operator step (never
    automatic). Empty before any removal."""
    return jsonify(serializers.serialize_orphan_worklist(seam.orphan_worklist()))


@api.get("/catalog/groups")
def catalog_groups():
    """The first-class GROUPS (agrupamentos) registry — id, name and a live member count
    (0 = an empty group). Backs the group-management UI. Read is open behind IAP."""
    return jsonify(seam.group_worklist())


@api.post("/catalog/group")
def catalog_group_upsert():
    """Create (group_id omitted) or RENAME (group_id given) a group. Author from the IAP
    header; 401/403 via the per-catalog editor allowlist. A bad/duplicate name → 400."""
    author, err = _authorize_catalog_editor(seam.PRODUTO_CATALOG_RESOURCE)
    if err:
        return err
    body = _json_object()
    _coerce_str_fields(body, "group_name", "group_id", "change_id")
    if not body.get("group_name"):
        return jsonify(error="O nome do agrupamento é obrigatório."), 400
    logger.info("catalog group upsert by %s: %s", author, body.get("group_name"))
    return jsonify(seam.record_group(body))


@api.post("/catalog/group/remove")
def catalog_group_remove():
    """Delete (tombstone) a group — rejected while it still has active members. Author
    from the IAP header; 401/403 via the per-catalog editor allowlist; non-empty → 400."""
    author, err = _authorize_catalog_editor(seam.PRODUTO_CATALOG_RESOURCE)
    if err:
        return err
    body = _json_object()
    _coerce_str_fields(body, "group_id", "change_id")
    if not body.get("group_id"):
        return jsonify(error="group_id é obrigatório."), 400
    logger.info("catalog group remove by %s: %s", author, body.get("group_id"))
    return jsonify(seam.remove_group(body))


@api.get("/source-meta")
def source_meta():
    """Provenance row for a banco (backs the page-hero meta); {} if absent.

    Shaped by ``serialize_source_meta`` into native JSON (real coverage/counters +
    the last-refresh stamp), so the frontend renders live gold_source_metadata
    instead of frozen bancos.js literals.
    """
    _ensure_banco_metadata_table()
    raw = seam.source_meta(request.args.get("banco", ""))
    return jsonify(serializers.serialize_source_meta(raw))


# Cap the number of município codes a single /municipio-yearly request may carry.
# The legitimate IBGE municipal universe is ~5570; a small margin above it rejects a
# pathological IN-list (giant query/param payload) with a clean 400 while never
# blocking a real "all municípios in a sub-UF" selection. Mirrors _MAX_TABLE_FILTERS.
_MAX_MUNICIPIO_CODES = 5600

# Cap the number of product/UF codes any basket IN-list query param (`codes`/`states`)
# may carry. Real baskets are a few dozen products and ≤27 UFs, so this only rejects a
# pathological list; it makes every user-driven IN-list bounded symmetrically with
# _MAX_MUNICIPIO_CODES / _MAX_TABLE_FILTERS (SEC-1) — `codes` travels in the GET query
# string, so gunicorn's request-line limit already bounds it, but the explicit cap keeps
# the contract uniform regardless of transport.
_MAX_BASKET_CODES = 600


# ── raw table inspection ("Dados" perspective) ─────────────────────────────────

# Cap the number of filters a single request may apply (defense against a giant WHERE).
_MAX_TABLE_FILTERS = 5


def _parse_table_filters(raw: str | None) -> tuple:
    """Parse the JSON ``filters`` param into a tuple of ``(col, op, val)`` tuples (hashable
    for the cache key). A malformed filter → ValueError → HTTP 400. Rejects (not silently
    truncates) more than ``_MAX_TABLE_FILTERS`` filters, so the rows/count/CSV never
    under-filter behind an applied chip; the column allowlist + value binding happen in the
    SQL builder."""
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"filtro malformado: {exc}") from None
    if not isinstance(data, list):
        raise ValueError("filtro deve ser uma lista de {col, op, val}")
    if len(data) > _MAX_TABLE_FILTERS:
        raise ValueError(f"máximo de {_MAX_TABLE_FILTERS} filtros por consulta")
    out = []
    for f in data:
        if not isinstance(f, dict) or "col" not in f:
            raise ValueError("cada filtro precisa de 'col' (e opcionalmente 'op'/'val')")
        val = f.get("val")
        # Only a scalar (or null) is a valid filter value; a list/dict would bind oddly or
        # 500 in the SQL layer — reject it here as a clean 400.
        if val is not None and not isinstance(val, (str, int, float, bool)):
            raise ValueError("o valor do filtro deve ser texto, número ou booleano")
        out.append((str(f["col"]), str(f.get("op", "eq")), val))
    return tuple(out)


@api.get("/tables")
def tables():
    """Allowlisted tables a researcher may browse for a banco (the 'Dados' picker): its
    Gold table + the serving marts that feed its charts. ``[]`` for a non-live banco."""
    return jsonify(seam.inspectable_tables(request.args.get("banco", "")))


@api.get("/table")
def table():
    """One page of RAW rows for an allowlisted (banco, table) — paginated, optionally
    ordered + filtered. The (banco, table) pair + every order/filter COLUMN are validated
    server-side against the allowlist / the table's live schema (a bad one → 400); filter
    VALUES stay bound. ``limit`` is capped in the SQL builder; plain browsing uses the free
    tabledata.list path (no scan billed)."""
    page = seam.table_page(
        request.args.get("banco", ""),
        request.args.get("table", ""),
        limit=request.args.get("limit", 100, type=int),
        offset=request.args.get("offset", 0, type=int),
        order_by=request.args.get("order_by") or None,
        order_dir=request.args.get("order_dir", "asc"),
        filters=_parse_table_filters(request.args.get("filters")),
    )
    return jsonify(serializers.serialize_table_page(page))


# ── seed reference consultation (the "Referências" perspective) ────────────────


@api.get("/seeds")
def seeds():
    """Read-only seed reference tables a researcher may consult ('Referências') to
    confirm the values the pipeline relies on. Banco-agnostic (shared reference data)."""
    return jsonify(seam.seed_tables())


@api.get("/seed")
def seed():
    """One page of rows for a consultable seed reference table — the SAME grid contract
    as /api/table, but seed-scoped (the Silver reference tables) and READ-ONLY. The id +
    every order/filter COLUMN are validated server-side against the allowlist / the live
    schema; an unknown id → 400 (the gateway allowlist is the boundary)."""
    page = seam.seed_page(
        request.args.get("id", ""),
        limit=request.args.get("limit", 100, type=int),
        offset=request.args.get("offset", 0, type=int),
        order_by=request.args.get("order_by") or None,
        order_dir=request.args.get("order_dir", "asc"),
        filters=_parse_table_filters(request.args.get("filters")),
    )
    return jsonify(serializers.serialize_seed_page(page))


# ── per-banco snapshot ─────────────────────────────────────────────────────────


@api.get("/snapshot")
def snapshot():
    """Full per-banco BancoSnapshot for the chosen currency×correction. Year/basket/
    state filtering is client-side (the reused dataFilters.js narrows the small,
    pre-aggregated marts). The ONE server-side filter is ``flow`` (export/import):
    the trade snapshot is pre-aggregated OVER flow, so a direction must re-query —
    absent/``all`` sums every flow (the historical default). currency+correction pick
    the deflated value column server-side (the scientific core — see contract map
    §0.2)."""
    banco = request.args.get("banco", "")
    conv, err = _conversion_or_400()
    if err:
        return err
    flow, err = _flow_or_400(request.args.get("flow"))
    if err:
        return err
    customs, err = _customs_or_400(request.args.get("customs"))
    if err:
        return err
    market, err = _market_or_400(request.args.get("market"))
    if err:
        return err
    # COMTRADE country filters (país reporter / parceiro) — server-side like flow.
    # reporter is 3-state (absent → Brazil, "__all__" → world, list → IN); partner is a list.
    reporters = _reporters_param(request.args.get("reporters"))
    partners = _csv_param(request.args.get("partners"))
    summary: dict = {}
    if flow:
        summary["flow"] = flow
    if customs and customs != "all":
        summary["customs"] = customs
    if market and market != "all":
        summary["market"] = market
    if reporters is not None:
        summary["reporters"] = reporters
    if partners:
        summary["partners"] = partners
    return jsonify(serializers.serialize_snapshot(seam.snapshot(banco, conv, summary or None)))


@api.get("/product-uf")
def product_uf():
    """Real per-UF ranking for a single product (backs ViewProductProfile's
    'Onde X é produzido' bars, and the Rebanho per-UF map). currency+correction pick
    the deflated value column server-side, same as /snapshot; optional
    startDate/endDate scope the year window and ``states`` the UF filter, to match
    the view's own filter. { uf: [] } when the banco has no geo grain."""
    banco = request.args.get("banco", "")
    code = request.args.get("code", "")
    conv, err = _conversion_or_400()
    if err:
        return err
    start, end = request.args.get("startDate"), request.args.get("endDate")
    states = _csv_param(request.args.get("states"))
    summary: dict | None = None
    if start or end or states:
        summary = {"startDate": start, "endDate": end}
        if states:
            summary["states"] = states
    df = seam.product_uf_ranking(banco, code, conv, summary)
    return jsonify(serializers.serialize_product_uf(df))


@api.get("/geo-yearly")
def geo_yearly():
    """Basket-scoped per-(UF, year) cube (backs the geography-aware hero + map +
    series). currency+correction pick the deflated value column server-side, same as
    /snapshot; ``codes`` (comma-joined product codes; absent = all) pushes the active
    product basket down to the by-UF-yearly mart so the territorial split respects the
    selected products. The year window is left open (full history) — the client slices
    period + state; ``flow`` (export/import) re-queries server-side like /snapshot
    (absent/``all`` sums every flow). { ufYearly: [] } when the banco has no geo grain."""
    banco = request.args.get("banco", "")
    conv, err = _conversion_or_400()
    if err:
        return err
    codes = request.args.get("codes")
    flow, err = _flow_or_400(request.args.get("flow"))
    if err:
        return err
    summary: dict = {}
    if codes:
        summary["basket"] = _csv_param(codes)  # blank-strip + cap (SEC-1)
    if flow:
        summary["flow"] = flow
    df = seam.geo_yearly(banco, conv, summary or None)
    return jsonify(serializers.serialize_geo_yearly(df))


@api.get("/geo-mesh")
def geo_mesh():
    """The IBGE municipal territorial mesh (static, ~5570 rows): every município →
    UF + grande região + BOTH sub-UF divisions (classic mesorregião/microrregião,
    current região intermediária/imediata). Banco-agnostic — the SPA fetches it once
    to build the geography cascade's sub-UF + município option lists and the
    cityCode→ancestry map. { municipios: [] } if the dim isn't built."""
    return jsonify(serializers.serialize_geo_mesh(seam.geo_mesh()))


@api.get("/countries")
def countries():
    """Distinct país reporter + país parceiro universes for the COMTRADE filter pickers
    (código M49 + ISO-A3 + nome pt-BR). The SPA fetches it once (like /geo-mesh) to
    populate the two country multi-selects. { reporters: [], partners: [] } if the
    COMTRADE mart isn't built. Banco-agnostic — the SPA only calls it for un_comtrade."""
    return jsonify(serializers.serialize_countries(seam.comtrade_countries()))


def _city_codes_or_400() -> tuple[list[str], tuple | None]:
    """The município code set from the JSON body, or a 400 response.

    Shared by every município-grained reader: the cube (/municipio-yearly) and the
    per-product breakdown (/products-by-municipio) enforce the SAME contract, so the
    validation lives once. A NON-EMPTY list is required — the client only calls these
    once a narrowing resolves to a city set, so an absent one is a bug, not a request
    to scan the whole ~146k-row município grid."""
    body = _json_object()
    raw_codes = body.get("cityCodes")
    # Must be a LIST: a bare string would otherwise char-split into bogus single-char
    # codes (e.g. "3550308" → ['3','5',...]); a non-list is a clean 400, not a silent
    # mis-parse (mirrors _parse_table_filters' type discipline).
    if not isinstance(raw_codes, list):
        return [], (jsonify(error="cityCodes deve ser uma lista não vazia."), 400)
    city = [str(c) for c in raw_codes if c]  # drop blanks; codes bind as STRING
    if not city:
        return [], (jsonify(error="cityCodes (lista não vazia) é obrigatório."), 400)
    # Cap the IN-list so a pathological request can't build a giant query/param payload
    # (the maximum_bytes_billed guard bounds the SCAN, not the parse/param overhead).
    if len(city) > _MAX_MUNICIPIO_CODES:
        return [], (
            jsonify(error=f"cityCodes excede o limite de {_MAX_MUNICIPIO_CODES} municípios."),
            400,
        )
    return city, None


@api.post("/municipio-yearly")
def municipio_yearly():
    """Basket-scoped per-(município, year) cube — the FINEST geography grain, backing
    the live-município + sub-UF cascade (the client rolls it up to the selected level
    via /geo-mesh). **POST, not GET**: the resolved city set can be hundreds of codes,
    which would overflow a GET request line (gunicorn's default ~4 KB limit → 414), so
    ``cityCodes`` travels in the JSON body. A NON-EMPTY ``cityCodes`` is REQUIRED — the
    client only calls this once a sub-UF/município narrowing resolves to a city set, so
    an absent/empty one is a 400, and the backend never scans the full ~146k-row
    município grid. currency+correction pick the deflated value column server-side;
    ``codes`` (URL query) pushes the active product basket down, and ``y0``/``y1``
    (URL query, optional) bound the year window — the second cost control, and the
    one that matters for a whole-UF municipal choropleth, which needs ONE year over
    many cities rather than every year (unbounded over all 5570: 153.634 rows /
    16,9 MB / 28 s; one year: ~3.400 rows). Absent = the full history, unchanged.
    { municipioYearly: [] } when the banco has no município grain (COMEX/COMTRADE)."""
    banco = request.args.get("banco", "")
    conv, err = _conversion_or_400()
    if err:
        return err
    city, err = _city_codes_or_400()
    if err:
        return err
    codes = request.args.get("codes")
    summary: dict = {"cityCodes": city}
    if codes:
        summary["basket"] = _csv_param(codes)  # blank-strip + cap (SEC-1)
    # startDate/endDate is the shape _years_from_summary reads (it slices the leading
    # 4 digits, so a bare year works) — same contract as every other filtered reader.
    y0, y1 = request.args.get("y0"), request.args.get("y1")
    if y0:
        summary["startDate"] = y0
    if y1:
        summary["endDate"] = y1
    df = seam.geo_municipio_yearly(banco, conv, summary)
    return jsonify(serializers.serialize_municipio_yearly(df))


@api.post("/products-by-municipio")
def products_by_municipio():
    """Per-product ranking WITHIN the selected municípios — "o que este lugar produz",
    the território profile's município counterpart to /products-by-uf.

    The município cube (/municipio-yearly) GROUPs BY city and sums the products away,
    so it can draw a place's trajectory but can never name what is behind it. This
    fills exactly that gap, over the SAME city scope and value basis so the two agree.

    **POST, not GET**, and a non-empty ``cityCodes`` body is REQUIRED — identical
    contract to /municipio-yearly (see :func:`_city_codes_or_400`), for the identical
    reason: it reads Gold directly, so the city scope IS the cost control.
    ``{ products: [] }`` when the banco has no município grain (COMEX is UF-origin,
    COMTRADE international)."""
    banco = request.args.get("banco", "")
    conv, err = _conversion_or_400()
    if err:
        return err
    city, err = _city_codes_or_400()
    if err:
        return err
    summary: dict = {"cityCodes": city}
    codes = request.args.get("codes")
    if codes:
        summary["basket"] = _csv_param(codes)  # blank-strip + cap (SEC-1)
    # startDate/endDate is the shape _years_from_summary reads (it slices the leading
    # 4 digits, so a bare year works) — same contract as every other filtered reader.
    y0, y1 = request.args.get("y0"), request.args.get("y1")
    if y0:
        summary["startDate"] = y0
    if y1:
        summary["endDate"] = y1
    df = seam.products_by_municipio(banco, conv, summary)
    # Same shape as the per-UF breakdown, so the view reuses one renderer.
    return jsonify(serializers.serialize_products_by_uf(df))


@api.get("/products-by-uf")
def products_by_uf():
    """Per-product ranking WITHIN the selected UF(s) — the "Base de dados" per-UF
    product breakdown (inverse of /product-uf, which ranks UFs for ONE product).

    currency+correction pick the deflated value column server-side; codes/states/
    y0/y1 scope basket + UF + year window. ``{ products: [] }`` when no UF is
    selected or the banco has no geo grain (the view then shows a "selecione uma UF"
    hint)."""
    banco = request.args.get("banco", "")
    conv, err = _conversion_or_400()
    if err:
        return err
    df = seam.products_by_uf(banco, _filter_summary(), conv)
    return jsonify(serializers.serialize_products_by_uf(df))


@api.get("/productivity")
def productivity():
    """Área × rendimento for one crop (backs ViewProductivity, IBGE PAM only).

    `crop` picks the active crop (defaults to the first when absent). Yield (kg/ha)
    is recomputed server-side from production ÷ harvested area on the PAM mart;
    `null` when the banco lacks the `yield` capability. ``y0``/``y1`` scope the
    year window and ``states`` the UF filter (the product basket does NOT apply —
    the crop selector is this view's own product dimension).

    With ``states`` set, the payload's ``national`` block holds the SELECTED states'
    figures and echoes ``states`` back: yield is a ratio, so a subset's is a
    different number, and the view relabels rather than calling it national."""
    banco = request.args.get("banco", "")
    crop = request.args.get("crop") or None
    y0, y1 = request.args.get("y0"), request.args.get("y1")
    states = _csv_param(request.args.get("states"))
    summary: dict | None = None
    if y0 or y1 or states:
        summary = {"startDate": y0, "endDate": y1}
        if states:
            summary["states"] = states
    payload = seam.productivity(banco, crop, summary)
    return jsonify(serializers.serialize_productivity(payload))


# ── trade adapters (flow / partner / monthly) — COMEX/COMTRADE ─────────────────


def _csv_param(raw: str | None) -> list[str]:
    """Split a comma-joined query param into a list, dropping blanks.

    ``None`` (param absent) and ``''`` (cleared / all) both yield an empty list —
    i.e. no filter on that dimension. An over-long list is rejected with a 400
    (``_MAX_BASKET_CODES``) so every IN-list is bounded symmetrically (SEC-1)."""
    if not raw:
        return []
    items = [c for c in raw.split(",") if c]
    if len(items) > _MAX_BASKET_CODES:
        raise BadRequest(f"Lista de códigos excede o limite de {_MAX_BASKET_CODES}.")
    return items


def _reporters_param(raw: str | None) -> str | list[str] | None:
    """Parse the COMTRADE ``reporters`` query param into the seam summary value (3-state):
    ``None`` (absent → Brazil default), the ``"__all__"`` world sentinel verbatim, or a
    capped ISO-A3 list (an effectively-empty list also degrades to ``None`` = default)."""
    if not raw:
        return None
    if raw == "__all__":
        return "__all__"
    return _csv_param(raw) or None


def _filter_summary() -> dict | None:
    """Parse the active-filter query params into the seam's summary shape.

    The reused views pass the FilterMenu selection through the producers as URL
    params: ``codes`` (comma-joined product codes → basket), ``states``
    (comma-joined UF acronyms → states, the origin-UF filter the COMEX trade
    readers honour), ``y0``/``y1`` (the year window) and — for COMTRADE — ``reporters``
    (3-state país reporter) / ``partners`` (país parceiro list). The seam reads ``basket``
    + ``states`` + ``startDate``/``endDate`` + ``reporters``/``partners``; year strings are
    sliced to the leading 4 digits there, so a bare year suffices. Returns ``None`` when no
    filter param is present (the unfiltered default).
    """
    basket = _csv_param(request.args.get("codes"))
    states = _csv_param(request.args.get("states"))
    y0, y1 = request.args.get("y0"), request.args.get("y1")
    reporters = _reporters_param(request.args.get("reporters"))
    partners = _csv_param(request.args.get("partners"))
    summary = {
        key: value
        for key, value in (
            ("basket", basket),
            ("states", states),
            ("startDate", y0),
            ("endDate", y1),
            ("reporters", reporters),
            ("partners", partners),
        )
        if value
    }
    return summary or None


@api.get("/flow")
def flow():
    """Origin→destination links for the Sankey (None when the banco lacks `flow`).

    ``codes``/``states``/``y0``/``y1`` scope the basket + origin-UF + year window to
    match the view's active filters (the seam threads them into the gateway flow
    reader; ``states`` narrows the COMEX origin only — COMTRADE's origin is a
    reporter country, so the frontend surfaces it as not-applicable there)."""
    banco = request.args.get("banco", "")
    return jsonify(serializers.serialize_flow(seam.flow_data(banco, _filter_summary())))


_ALLOWED_PARTNER_METRICS = frozenset({"value", "weight", "price"})


@api.get("/partners")
def partners():
    """Partner ranking with export/import split (basket + origin-UF + year window
    via ``codes``/``states``/``y0``/``y1``; ``states`` applies to COMEX only).

    ``metric`` ∈ {value, weight, price} (default ``value``) ranks by Capital /
    Volume / Preço médio server-side, so the top-N is by the chosen dimension."""
    banco = request.args.get("banco", "")
    metric = request.args.get("metric", "value")
    if metric not in _ALLOWED_PARTNER_METRICS:
        return jsonify(error=f"métrica inválida: {metric!r}"), 400
    return jsonify(
        serializers.serialize_partner(seam.partner_data(banco, _filter_summary(), rank_by=metric))
    )


@api.get("/monthly")
def monthly():
    """Monthly seasonality, COMEX only (basket + year window via
    ``codes``/``y0``/``y1``). The seasonality mart collapses UF away, so the UF
    (``states``) filter does not apply here — the frontend surfaces that honestly."""
    banco = request.args.get("banco", "")
    return jsonify(serializers.serialize_monthly(seam.monthly_data(banco, _filter_summary())))


# ── cross-source comparable series ─────────────────────────────────────────────


@api.get("/cross/metric-refs")
def cross_metric_refs():
    """Every (banco, metric) the cross-source picker can offer."""
    return jsonify(seam.cross_metric_refs())


def _uf_codes() -> tuple[str, ...]:
    """Origin-UF acronyms from the ``states`` param (cross-source per-UF scoping).

    Empty = national (no UF filter). Only the UF-capable sides (IBGE PEVS, MDIC
    COMEX) honour it; COMTRADE-origin series ignore it (the view notes that)."""
    return tuple(_csv_param(request.args.get("states")))


@api.get("/cross/series")
def cross_series():
    """One comparable annual series for (banco, metric), in its display unit.
    ``states`` optionally narrows to origin UF(s) for the UF-capable bancos."""
    banco = request.args.get("banco", "")
    metric = request.args.get("metric", "")
    y0 = request.args.get("y0", type=int)
    y1 = request.args.get("y1", type=int)
    return jsonify(
        serializers.serialize_cross_series(seam.cross_series(banco, metric, y0, y1, _uf_codes()))
    )


# ── cross-source analytics (crosswalk-joined) ──────────────────────────────────


def _commodity() -> str | None:
    return request.args.get("commodity") or None


@api.get("/cross/export-coef")
def cross_export_coef():
    """``states`` optionally narrows the export coefficient to origin UF(s) — BOTH
    sides of the ratio (production and exports) and the aggregate, so the figure
    stays a real coefficient rather than a subset over a national denominator."""
    return jsonify(
        serializers.serialize_export_coef(seam.export_coefficient(_commodity(), _uf_codes()))
    )


@api.get("/cross/market-share")
def cross_market_share():
    return jsonify(serializers.serialize_market_share(seam.market_share(_commodity())))


@api.get("/cross/price-spread")
def cross_price_spread():
    """``states`` optionally narrows the porteira-vs-FOB spread to one origin UF(s)."""
    return jsonify(serializers.serialize_price_spread(seam.price_spread(_commodity(), _uf_codes())))


@api.get("/cross/mirror")
def cross_mirror():
    return jsonify(serializers.serialize_trade_mirror(seam.trade_mirror(_commodity())))


# ─── Feedback ("Reportar problema") ─────────────────────────────────────────────
def _peek_author():
    """Best-effort author for the per-author rate-limit key; None when no trustworthy
    identity is present (record_feedback then raises the real 401/403)."""
    try:
        return current_author()
    except Exception:  # fall through; record_feedback raises the real 401/403
        return None


@api.post("/feedback")
def feedback_submit():
    """Append one user feedback report (bug/dúvida/sugestão) and best-effort open a
    GitHub issue. ANY IAP-authenticated user may submit (no attribute editor allowlist); the
    author is captured server-side from IAP — there is no client-supplied identity.
    A short per-author cooldown debounces double-clicks/abuse (SEC-2). 400 on empty/
    over-length message or bad category; 401/403 on no/forged identity; 429 on cooldown."""
    body = _json_object()
    _coerce_str_fields(
        body,
        "category",
        "message",
        "url",
        "view",
        "banco",
        "app_version",
        "browser_info",
        "change_id",
    )
    cooldown = get_settings().feedback_cooldown_seconds
    author = _peek_author()
    rl_key = f"fb:cooldown:{author.lower()}" if author else None
    if rl_key and cooldown and cache.get(rl_key):
        return jsonify(error="Aguarde alguns segundos antes de enviar outro feedback."), 429
    try:
        result = record_feedback(
            category=body.get("category", "bug"),
            message=body.get("message", ""),
            headers=request.headers,
            url=body.get("url"),
            view=body.get("view"),
            banco=body.get("banco"),
            app_version=body.get("app_version"),
            browser_info=body.get("browser_info"),
            author=author,
            change_id=body.get("change_id"),
        )
    except FeedbackValidationError as exc:
        return jsonify(error=str(exc)), 400
    except InvalidIapAssertionError as exc:
        return jsonify(error=str(exc)), 403
    except PermissionError as exc:  # MissingAuthorError → no trustworthy identity
        return jsonify(error=str(exc)), 401
    if rl_key and cooldown:
        cache.set(rl_key, 1, timeout=cooldown)
    return jsonify(result)


# ─── Engenharia de Atributos endpoints ─────────────────────────────────────────
# Two derived-attribute analyses + TWO editors (per-code industrialization and the
# customs×flow market-nature matrix). Both are researcher-EDITABLE (gated by the
# `enable_curation` dbt var); each analysis reflects its editor after the next dbt build.
@api.get("/cross/value-added")
def cross_value_added():
    """``states`` optionally narrows the bruta×processada split to one origin UF(s)."""
    return jsonify(serializers.serialize_value_added(seam.value_added(_commodity(), _uf_codes())))


@api.get("/cross/market-nature")
def cross_market_nature():
    """COMTRADE value by economic purpose (consumo/processamento) — the edit-driven
    (customs procedure × flow) classification, summed from the serving mart."""
    return jsonify(serializers.serialize_market_nature(seam.market_nature(_commodity())))


# ── curation (read + write) ────────────────────────────────────────────────────


@api.get("/attributes/worklist")
def curation_worklist():
    """Gold DISTINCT codes ⟕ current industrialization levels (the editor worklist)."""
    return jsonify(seam.curation_worklist())


@api.post("/attributes/code-level")
def curation_code_level():
    """Append one per-code classification edit. Author captured from the IAP
    header (dev fallback per config); 401 (no identity) / 403 (invalid assertion
    or not an allowlisted attribute editor)."""
    author, err = _authorize_attribute_editor()
    if err:
        return err
    body = _json_object()
    _coerce_str_fields(body, "source", "code", "level", "change_id")
    source, code, level = body.get("source"), body.get("code"), body.get("level")
    change_id = body.get("change_id")
    if not (source and code and level):
        return jsonify(error="source, code e level são obrigatórios."), 400
    logger.info("curation write by %s: %s/%s → %s", author, source, code, level)
    return jsonify(seam.record_code_level(source, code, level, change_id))


@api.get("/attributes/flow-worklist")
def curation_flow_worklist():
    """The (customs procedure × flow) matrix — COMTRADE traded value ⟕ the current
    market mapping (the "Tipo de Mercado" editor's data)."""
    return jsonify(seam.flow_market_worklist())


@api.post("/attributes/flow-market")
def curation_flow_market():
    """Append one (customs_code, flow_code) → market edit (market='' clears the pair).
    Author captured from the IAP header (dev fallback per config); 401 (no identity) /
    403 (invalid assertion or not an allowlisted attribute editor)."""
    author, err = _authorize_attribute_editor()
    if err:
        return err
    body = _json_object()
    _coerce_str_fields(body, "customs_code", "flow_code", "market", "change_id")
    customs_code, flow_code = body.get("customs_code"), body.get("flow_code")
    market = body.get("market") or ""
    change_id = body.get("change_id")
    if not (customs_code and flow_code):
        return jsonify(error="customs_code e flow_code são obrigatórios."), 400
    logger.info("curation write by %s: %s×%s → %s", author, customs_code, flow_code, market)
    return jsonify(seam.record_flow_market(customs_code, flow_code, market, change_id))
