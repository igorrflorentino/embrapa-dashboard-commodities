"""HTTP client for the UN Comtrade keyed JSON API.

One call returns annual bilateral trade for a *batch* of reporters across all
their partners (``partnerCode`` omitted) for the configured HS codes, flows and
years — the keyed endpoint accepts comma-lists for ``reporterCode`` / ``period``
/ ``cmdCode`` / ``flowCode`` but rejects the literal ``all`` for reporter, so the
pipeline enumerates reporters (from the public Reporters reference) and batches
them to stay under the per-call record cap.

The subscription key is sent **only** in the ``Ocp-Apim-Subscription-Key``
header — never in the URL or any log/error message — so it stays secret.
"""

from __future__ import annotations

import logging
import os
import time

import pandas as pd

from embrapa_dashboard import observability
from embrapa_dashboard.core import SourceTransientError
from embrapa_dashboard.core import http as core_http

logger = logging.getLogger(__name__)

REPORTERS_REF_URL = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
HS_REF_URL = "https://comtradeapi.un.org/files/v1/app/reference/HS.json"

# Hard wall-clock ceilings (a keyed call returns up to ~100k JSON rows).
REQUEST_TOTAL_DEADLINE_S: float = 180.0
PER_CALL_DEADLINE_S: float = 300.0

# Keyed free-tier per-call record cap. A call that returns exactly this many rows
# has almost certainly been TRUNCATED server-side — even a single dense reporter
# (e.g. Germany, chapter 44 at HS6 × 4 regimes) hits it — so fetch_chunk_adaptive
# splits and recurses until every actual call stays under it.
PER_CALL_ROW_CAP: int = 100_000

# Curated Bronze columns kept from the ~50-field API response (dimensions +
# measures). Everything STRING in Bronze; the raw archive keeps the full frame.
BRONZE_COLUMNS: list[str] = [
    "refYear",
    "period",
    "reporterCode",
    "flowCode",
    "partnerCode",
    "partner2Code",
    "cmdCode",
    "customsCode",
    "mosCode",
    "motCode",
    "qtyUnitCode",
    "qty",
    "altQtyUnitCode",
    "altQty",
    "netWgt",
    "grossWgt",
    "cifvalue",
    "fobvalue",
    "primaryValue",
]

# Integer-coded API dimensions among :data:`BRONZE_COLUMNS`. pandas floatifies a
# whole column when any row of the JSON response carries a null in it, so the
# ``astype("string")`` Bronze coercion would land ``motCode 0`` as ``'0.0'`` and
# ``qtyUnitCode -1`` as ``'-1.0'`` — values Silver's exact-string filters
# (``motCode = '0'``, the ``qtyUnitCode = '-1'`` dedup preference, …) silently
# fail to match. These columns are canonicalized back to plain integer strings
# before the Bronze write (see :func:`fetch_chunk`). ``cmdCode``/``customsCode``/
# ``flowCode`` are genuinely alphanumeric and the measures may carry decimals,
# so they are excluded.
INT_CODE_COLUMNS: list[str] = [
    "refYear",
    "period",
    "reporterCode",
    "partnerCode",
    "partner2Code",
    "mosCode",
    "motCode",
    "qtyUnitCode",
    "altQtyUnitCode",
]


class ComtradeRequestError(Exception):
    """Non-200 response from the UN Comtrade API (base class)."""


class ComtradeTransientError(ComtradeRequestError, SourceTransientError):
    """Transient (retryable) error: 5xx/408 (incl. short reference-file hiccups)."""


class ComtradeQuotaError(ComtradeRequestError):
    """The daily keyed-call quota is exhausted (HTTP 403 "Out of call volume quota",
    or a 429 whose Retry-After is long/absent — both on a keyed data call).

    Deliberately **not** a :class:`SourceTransientError`: the shared retry policy
    must not retry it. Retrying would only burn the (already spent) daily budget;
    the resumable two-phase raw zone means the right move is to stop and re-run
    later, which picks up exactly the un-archived chunks. The pipeline catches
    this to break its chunk loop early ("quota exhausted — re-run to resume").

    APIM answers 429 for *two* distinct conditions: the per-second/burst rate
    limit and the daily quota. Only the latter maps here — a keyed 429 carrying
    a short ``Retry-After`` (≤ :data:`RATE_LIMIT_RETRY_AFTER_MAX_S`) is the burst
    limiter and is raised as :class:`ComtradeTransientError` instead, so the
    retry policy backs off and re-attempts (see :func:`fetch_chunk`).

    Scoped to keyed *data* calls (:func:`fetch_chunk`); a 429 on the public,
    key-less reference files (:func:`list_reporters` / :func:`list_hs6_codes`) is
    a momentary rate limit and stays transient/retryable.
    """


class ComtradeTruncationError(ComtradeRequestError):
    """A single (reporter, flow, cmd) call still hit the per-call row cap.

    The adaptive splitter has nothing left to split (reporters/flows/cmd are all
    singletons) yet the call came back at :data:`PER_CALL_ROW_CAP` — only a
    partner-dimension split would help, which the keyed endpoint can't express.
    Rather than silently archive a TRUNCATED chunk (which the resume logic would
    then treat as complete forever), the fetch raises this so the chunk is left
    un-archived and a later run re-attempts it. Non-transient: an immediate retry
    of the identical call would truncate identically.
    """


def _emit_retry(retry_state):  # type: ignore[no-untyped-def]
    """Tenacity ``before_sleep`` hook: surface retries in ``embrapa monitor``."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    observability.emit(
        "retry",
        series="comtrade",
        window="",
        attempt=retry_state.attempt_number,
        reason=str(exc)[:200] if exc else "?",
    )
    logger.warning("Retrying Comtrade call attempt=%d: %s", retry_state.attempt_number, exc)


# A keyed 429 with ``Retry-After`` at or under this many seconds is APIM's
# per-second/burst rate limiter (transient — back off and retry); above it (or
# with no header at all) it is treated as the daily quota (stop the run). The
# daily quota replenishes at 00:00 UTC (21:00 BRT) — MEASURED, see
# docs/comtrade_world_backfill.md — so the two regimes are far apart.
RATE_LIMIT_RETRY_AFTER_MAX_S: float = 120.0

# Minimum spacing between consecutive keyed data calls (client-side throttle).
# The chunk loop and the adaptive splitter otherwise fire calls back-to-back —
# past-year chunks with little data return in milliseconds — easily tripping
# APIM's per-second burst limit. Operator knob: the COMTRADE_INTER_CALL_DELAY_S
# env var (seconds; 0 disables). Read once at import; tests override the module
# attribute directly.
INTER_CALL_DELAY_S: float = float(os.environ.get("COMTRADE_INTER_CALL_DELAY_S", "1.0"))

_last_keyed_call_monotonic: float = 0.0


def _throttle_keyed_call() -> None:
    """Sleep just enough to keep :data:`INTER_CALL_DELAY_S` between keyed calls."""
    global _last_keyed_call_monotonic
    if INTER_CALL_DELAY_S > 0:
        wait_s = INTER_CALL_DELAY_S - (time.monotonic() - _last_keyed_call_monotonic)
        if wait_s > 0:
            time.sleep(wait_s)
    _last_keyed_call_monotonic = time.monotonic()


def _retry_after_seconds(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header in its delta-seconds form (what APIM sends).

    Returns ``None`` when the header is absent or unparseable (the HTTP-date
    form is not used by the Comtrade gateway) — the caller then falls back to
    the conservative daily-quota classification.
    """
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


@core_http.http_retry_policy(
    transient_exc=ComtradeTransientError,
    deadline_s=PER_CALL_DEADLINE_S,
    max_attempts=4,
    before_sleep=_emit_retry,
)
def list_reporters() -> list[str]:
    """All real reporter M49 codes (excluding group aggregates), from the public
    Reporters reference (no key needed). The keyed endpoint needs explicit codes
    since it rejects ``reporterCode=all``. Transient hiccups (5xx/408/429, a
    slow-byte hang) are retried under the shared policy — a momentary blip on
    this reference must not crash the whole run before any chunk executes."""
    response = core_http.get_drained(
        REPORTERS_REF_URL,
        total_deadline_s=REQUEST_TOTAL_DEADLINE_S,
        transient_exc=ComtradeTransientError,
        context="Comtrade Reporters reference",
    )
    try:
        if response.status_code != 200:
            raise ComtradeTransientError(f"HTTP {response.status_code} for Reporters reference")
        results = response.json().get("results", [])
    finally:
        response.close()
    # Tolerate a schema-drifted reference row: a missing reporterCode is skipped
    # (not a KeyError that would abort the whole run before any chunk executes).
    return [
        str(r["reporterCode"])
        for r in results
        if not r.get("isGroup") and r.get("reporterCode") is not None
    ]


@core_http.http_retry_policy(
    transient_exc=ComtradeTransientError,
    deadline_s=PER_CALL_DEADLINE_S,
    max_attempts=4,
    before_sleep=_emit_retry,
)
def list_hs6_codes(scope_codes: list[str]) -> list[str]:
    """Every 6-digit HS leaf under the given scope codes (e.g. ``['0801', '44']``
    → all ``0801xx`` + ``44xxxx`` subheadings), from the public HS reference.

    Comtrade returns data only at the *requested* code level — asking for ``0801``
    yields the HS4 aggregate, not its children — so to ingest at HS6 the pipeline
    must enumerate the leaves. Returns them sorted. Transient fetch failures
    (5xx/408/429, an empty reference body) are retried under the shared policy;
    the no-leaves configuration error below is permanent and is not.

    Raises rather than falling back to the (HS4) scope codes: an empty reference is
    treated as a transient fetch failure, and a non-empty reference with no HS6
    descendants of the scope is a configuration error. Silently returning the
    scope codes would request HS4 aggregates — the exact wrong-granularity /
    double-count failure HS6 exists to avoid."""
    response = core_http.get_drained(
        HS_REF_URL,
        total_deadline_s=REQUEST_TOTAL_DEADLINE_S,
        transient_exc=ComtradeTransientError,
        context="Comtrade HS reference",
    )
    try:
        if response.status_code != 200:
            raise ComtradeTransientError(f"HTTP {response.status_code} for HS reference")
        results = response.json().get("results", [])
    finally:
        response.close()

    if not results:
        # 200 with an empty body — an API hiccup or schema drift; retryable.
        raise ComtradeTransientError("HS reference returned no results")
    # Tolerate a schema-drifted reference row: an entry missing its id is skipped
    # (not a KeyError that would abort the whole run before any chunk executes).
    leaves = sorted(
        str(entry["id"])
        for entry in results
        if entry.get("aggrLevel") == 6
        and entry.get("id") is not None
        and any(str(entry["id"]).startswith(s) for s in scope_codes)
    )
    if not leaves:
        raise ComtradeRequestError(
            f"No HS6 leaves under scope {scope_codes} in the HS reference "
            "— check COMTRADE_CMD_CODES."
        )
    return leaves


@core_http.http_retry_policy(
    transient_exc=ComtradeTransientError,
    deadline_s=PER_CALL_DEADLINE_S,
    max_attempts=4,
    before_sleep=_emit_retry,
)
def fetch_chunk(
    base_url: str,
    api_key: str,
    *,
    reporters: list[str],
    years: list[int],
    cmd_codes: list[str],
    flows: list[str],
    customs_code: str = "",
) -> pd.DataFrame:
    """One keyed call: annual bilateral trade for ``reporters`` × all partners,
    over ``years`` × ``cmd_codes`` × ``flows``. Returns a string-typed DataFrame
    of :data:`BRONZE_COLUMNS` (empty frame if the API returned no rows).

    ``partnerCode`` is omitted on purpose → every partner (the bilateral matrix,
    incl. ``0`` = World). The key goes in the header only.

    ``customs_code`` (UN Comtrade customsCode) restricts the pull to a single
    customs-procedure code — the totals-only design passes ``"C00"`` so only the
    "todos os regimes / total" aggregate is downloaded (no per-regime breakdowns).
    Empty ⇒ the filter is omitted (every customsCode, the pre-2026-07 behaviour).
    """
    # Client-side throttle: keep a minimum gap between keyed calls so bursts of
    # fast (small/past-year) chunks don't trip APIM's per-second rate limit.
    _throttle_keyed_call()
    params = {
        "reporterCode": ",".join(reporters),
        "period": ",".join(str(y) for y in years),
        "cmdCode": ",".join(cmd_codes),
        "flowCode": ",".join(flows),
    }
    if customs_code:
        params["customsCode"] = customs_code
    url = f"{base_url.rstrip('/')}/C/A/HS?" + "&".join(f"{k}={v}" for k, v in params.items())
    headers = {**core_http.DEFAULT_HEADERS, "Ocp-Apim-Subscription-Key": api_key}
    # context omits the key and the (long) reporter list — just the shape.
    context = f"Comtrade {years} flows={flows} reporters={len(reporters)}"
    response = core_http.get_drained(
        url,
        total_deadline_s=REQUEST_TOTAL_DEADLINE_S,
        transient_exc=ComtradeTransientError,
        context=context,
        headers=headers,
    )
    try:
        if response.status_code != 200:
            msg = f"HTTP {response.status_code} for {context}"
            if response.status_code == 429:
                # APIM answers 429 for both the per-second burst limiter and the
                # daily quota; a short Retry-After disambiguates the former —
                # transient, so the shared policy backs off and re-attempts.
                #
                # CONSERVATIVE classification when the header is ABSENT (or long):
                # treat it as the daily quota and STOP. This trades a small,
                # self-healing cost (a header-less *burst* 429 — if APIM ever omits
                # the header on a burst — would end the run early; the next
                # scheduled run resumes from the un-archived chunks with NO data
                # loss) for the safe default of never burning the whole daily
                # keyed-call budget retrying an exhausted quota. The two-phase raw
                # zone makes either case fully resumable, so erring toward "stop and
                # resume" is correct for an unattended batch job. (If a header-less
                # burst is ever observed in practice, switch this to a bounded
                # transient retry before escalating to quota.)
                retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                if retry_after is not None and retry_after <= RATE_LIMIT_RETRY_AFTER_MAX_S:
                    raise ComtradeTransientError(
                        f"rate limited (Retry-After={retry_after:g}s): {msg}"
                    )
                # Daily keyed-call quota (long or absent Retry-After) — stop, don't
                # retry (see ComtradeQuotaError); the next run resumes, no data lost.
                raise ComtradeQuotaError(f"quota exhausted ({msg}) — re-run to resume")
            if response.status_code == 403:
                # The DAILY call-volume quota answers 403, NOT 429 — observed in a real
                # backfill (2026-08-18): 508 chunks landed, then every call returned
                #   {"statusCode":403,"message":"Out of call volume quota. Quota will be
                #    replenished in 19:07:31."}
                # Without this the run died as an "unexpected" ComtradeRequestError and
                # exited 1, paging a human for the textbook expected, self-healing,
                # already-resumable condition ComtradeQuotaError exists to handle.
                #
                # Matched on the message, not the status: a 403 from a revoked/invalid key
                # is a REAL failure and must keep paging, so it falls through below.
                detail = ""
                try:
                    detail = str(response.json().get("message", ""))
                except ValueError:
                    detail = (response.text or "")[:200]
                if "call volume quota" in detail.lower():
                    raise ComtradeQuotaError(
                        f"quota exhausted ({msg}: {detail}) — re-run to resume"
                    )
                raise ComtradeRequestError(f"{msg}: {detail}" if detail else msg)
            if response.status_code in core_http.RETRYABLE_STATUS_CODES:
                raise ComtradeTransientError(msg)
            raise ComtradeRequestError(msg)
        rows = response.json().get("data", [])
    finally:
        response.close()
    if not rows:
        return pd.DataFrame(columns=BRONZE_COLUMNS)
    frame = pd.DataFrame(rows)
    # Keep the curated columns, all as strings (Bronze convention); missing
    # columns (a sparse response) are added as NA via reindex.
    frame = frame.reindex(columns=BRONZE_COLUMNS).astype("string")
    # Canonicalize the integer-coded dimensions (see INT_CODE_COLUMNS): a JSON
    # null anywhere in such a column floatifies it, landing '0.0'/'-1.0' strings
    # that Silver's exact-match filters would silently drop from Gold.
    for col in INT_CODE_COLUMNS:
        frame[col] = frame[col].str.replace(r"^(-?\d+)\.0$", r"\1", regex=True)
    return frame


def fetch_chunk_adaptive(
    base_url: str,
    api_key: str,
    *,
    reporters: list[str],
    years: list[int],
    cmd_codes: list[str],
    flows: list[str],
    customs_code: str = "",
) -> pd.DataFrame:
    """:func:`fetch_chunk` that guarantees completeness despite the per-call cap.

    A single keyed call silently truncates at :data:`PER_CALL_ROW_CAP` rows — and
    a lone dense reporter (Germany, chapter 44 at HS6 × 4 regimes) already hits it,
    so no fixed batch size is safe. When a call comes back at the cap, the largest
    divisible request dimension is split in half — reporters, then flows, then
    cmd codes — and the halves are fetched (recursively) and concatenated, so every
    real API call stays under the cap.

    A single (reporter, flow, cmd) that *still* caps cannot be split further (only
    a partner split would help, which the keyed endpoint can't express). Rather
    than return the truncated frame and let it be archived as if complete, this
    emits a ``truncated`` event and raises :class:`ComtradeTruncationError` so the
    chunk is left un-archived for a later run to re-attempt (not expected within
    the 0801+44 scope).

    PRECONDITION — ``years`` must be a single year: the splitter divides only
    reporters → flows → cmd_codes, NOT years (sync_raw always calls per-year, so a
    year split would never help). If a future caller passed a multi-year list and a
    single (reporter, flow, cmd, multi-year) call hit the cap, it would raise a FALSE
    ComtradeTruncationError ("un-splittable") even though splitting by year would
    resolve it. This unconditional check pins the invariant so that change can't silently
    lose data — a plain ``assert`` would be stripped under ``python -O`` (COMTRADE-1)."""
    if len(years) != 1:
        raise ValueError(
            "fetch_chunk_adaptive splits reporters/flows/cmd_codes but NOT years; pass a "
            f"single year (got {years!r}) or add 'years' to the split dimensions first."
        )
    df = fetch_chunk(
        base_url,
        api_key,
        reporters=reporters,
        years=years,
        cmd_codes=cmd_codes,
        flows=flows,
        customs_code=customs_code,
    )
    # Strict `<`: a result of EXACTLY PER_CALL_ROW_CAP rows is treated as truncated. The API
    # exposes no count/hasMore field, so a genuinely-complete leaf of exactly the cap is
    # indistinguishable from a truncated page by row count alone — and below it would re-raise
    # ComtradeTruncationError (never archiving). This off-by-one is vanishingly unlikely within
    # the 0801+44 scope (a single reporter/flow/cmd/year hitting exactly 100_000 rows), and the
    # conservative direction: better to retry than to silently archive a truncated chunk.
    if len(df) < PER_CALL_ROW_CAP:
        return df

    for name, seq in (("reporters", reporters), ("flows", flows), ("cmd_codes", cmd_codes)):
        if len(seq) > 1:
            mid = len(seq) // 2
            kwargs = {
                "reporters": reporters,
                "years": years,
                "cmd_codes": cmd_codes,
                "flows": flows,
                # customsCode is a single fixed value (not a split dimension) — it
                # rides through every recursive half unchanged.
                "customs_code": customs_code,
            }
            kwargs[name] = seq[:mid]
            left = fetch_chunk_adaptive(base_url, api_key, **kwargs)
            kwargs[name] = seq[mid:]
            right = fetch_chunk_adaptive(base_url, api_key, **kwargs)
            return pd.concat([left, right], ignore_index=True)

    observability.emit(
        "truncated",
        series="comtrade",
        reporters=",".join(reporters),
        flows=",".join(flows),
        cmd_codes=",".join(cmd_codes),
        years=",".join(str(y) for y in years),
        row_cap=PER_CALL_ROW_CAP,
    )
    logger.error(
        "Comtrade call still at the %d-row cap for a single reporter/flow/cmd "
        "(reporters=%s flows=%s cmd=%s) — refusing to archive a TRUNCATED chunk; "
        "it will be retried on the next run.",
        PER_CALL_ROW_CAP,
        reporters,
        flows,
        cmd_codes,
    )
    raise ComtradeTruncationError(
        f"truncated at {PER_CALL_ROW_CAP} rows for reporters={reporters} "
        f"flows={flows} cmd={cmd_codes}"
    )
