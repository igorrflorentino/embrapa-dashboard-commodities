"""Tests for the UN Comtrade keyed JSON client (HTTP fully mocked, offline).

Pins the live-validated contract (2026-05-30): keyed GET to ``/C/A/HS`` with
comma-list query params, the subscription key carried **only** in the
``Ocp-Apim-Subscription-Key`` header (never the URL/log), ``partnerCode`` omitted
so every partner returns, and a string-typed frame reindexed to BRONZE_COLUMNS.
"""

from __future__ import annotations

import re

import pandas as pd
import pytest
import responses
import tenacity

from embrapa_dashboard.comtrade import client

BASE_URL = "https://comtradeapi.un.org/data/v1/get"
API_KEY = "secret-key-123"


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero the keyed-call throttle so the suite never sleeps between calls."""
    monkeypatch.setattr(client, "INTER_CALL_DELAY_S", 0.0)


# A trimmed two-row API payload (only some of the ~50 fields present, to exercise
# the reindex that fills missing BRONZE_COLUMNS with NA).
DATA_PAYLOAD = {
    "data": [
        {
            "refYear": 2022,
            "period": 2022,
            "reporterCode": 76,
            "flowCode": "X",
            "partnerCode": 0,
            "cmdCode": "0801",
            "qty": 1234,
            "netWgt": 1230,
            "primaryValue": 98765,
        },
        {
            "refYear": 2022,
            "period": 2022,
            "reporterCode": 76,
            "flowCode": "M",
            "partnerCode": 842,
            "cmdCode": "44",
            "qtyUnitCode": -1,  # chapter-44 imports often omit quantity
            "qty": None,
            "primaryValue": 4321,
        },
    ]
}

REPORTERS_PAYLOAD = {
    "results": [
        {"reporterCode": "76", "text": "Brazil", "isGroup": False},
        {"reporterCode": "842", "text": "USA", "isGroup": False},
        {"reporterCode": "0", "text": "World", "isGroup": True},  # aggregate → dropped
        {"reporterCode": "841", "text": "USA (before 1981)", "isGroup": False},
    ]
}


# ─── list_reporters ──────────────────────────────────────────────────────────
@responses.activate
def test_list_reporters_excludes_groups() -> None:
    responses.add(responses.GET, client.REPORTERS_REF_URL, json=REPORTERS_PAYLOAD, status=200)
    codes = client.list_reporters()
    assert codes == ["76", "842", "841"]  # group code 0 dropped, all stringified


@responses.activate
def test_list_reporters_raises_transient_on_5xx() -> None:
    responses.add(responses.GET, client.REPORTERS_REF_URL, status=503)
    with pytest.raises(client.ComtradeTransientError):
        client.list_reporters.__wrapped__()  # type: ignore[attr-defined]


def test_reference_fetches_are_wrapped_in_retry_policy() -> None:
    """The docstrings promise transient reference hiccups are retried — pin the
    wiring so a momentary 5xx/429 on a reference can't crash the whole run
    before any chunk executes (resolve_reporters runs ahead of the chunk loop)."""
    assert client.list_reporters.retry.before_sleep is client._emit_retry  # type: ignore[attr-defined]
    assert client.list_hs6_codes.retry.before_sleep is client._emit_retry  # type: ignore[attr-defined]


@responses.activate
def test_list_reporters_retries_transient_blip_then_succeeds() -> None:
    """One momentary 503 on the Reporters reference must be retried, not crash."""
    responses.add(responses.GET, client.REPORTERS_REF_URL, status=503)
    responses.add(responses.GET, client.REPORTERS_REF_URL, json=REPORTERS_PAYLOAD, status=200)
    # retry_with(wait=0) keeps the test instant without mutating the shared policy.
    codes = client.list_reporters.retry_with(wait=tenacity.wait_fixed(0))()  # type: ignore[attr-defined]
    assert codes == ["76", "842", "841"]
    assert len(responses.calls) == 2


@responses.activate
def test_list_reporters_skips_schema_drifted_row_without_reporter_code() -> None:
    """A reference row missing reporterCode must be SKIPPED, not crash the whole
    run with a non-retryable KeyError before any chunk executes."""
    drifted = {
        "results": [
            {"reporterCode": "76", "text": "Brazil", "isGroup": False},
            {"text": "no code here", "isGroup": False},  # schema drift → skipped
            {"reporterCode": "842", "text": "USA", "isGroup": False},
        ]
    }
    responses.add(responses.GET, client.REPORTERS_REF_URL, json=drifted, status=200)
    codes = client.list_reporters()
    assert codes == ["76", "842"]  # the keyless row is dropped, no KeyError


# ─── list_hs6_codes ──────────────────────────────────────────────────────────
HS_PAYLOAD = {
    "results": [
        {"id": "0801", "aggrLevel": 4},
        {"id": "080122", "aggrLevel": 6},
        {"id": "080121", "aggrLevel": 6},
        {"id": "44", "aggrLevel": 2},
        {"id": "4407", "aggrLevel": 4},
        {"id": "440710", "aggrLevel": 6},
        {"id": "09", "aggrLevel": 2},  # out of scope
        {"id": "090111", "aggrLevel": 6},  # out of scope
    ]
}


@responses.activate
def test_list_hs6_codes_returns_sorted_scope_leaves_only() -> None:
    responses.add(responses.GET, client.HS_REF_URL, json=HS_PAYLOAD, status=200)
    out = client.list_hs6_codes(["0801", "44"])
    # only aggrLevel-6 ids under the scope, sorted; HS2/HS4 parents and out-of-scope excluded.
    assert out == ["080121", "080122", "440710"]


@responses.activate
def test_list_hs6_codes_raises_transient_on_empty_reference() -> None:
    # 200 with no results → do NOT silently fall back to HS4 scope codes (that would
    # request wrong-granularity aggregates); treat as a retryable fetch failure.
    responses.add(responses.GET, client.HS_REF_URL, json={"results": []}, status=200)
    with pytest.raises(client.ComtradeTransientError):
        client.list_hs6_codes.__wrapped__(["0801", "44"])  # type: ignore[attr-defined]


@responses.activate
def test_list_hs6_codes_raises_permanent_when_scope_has_no_leaves() -> None:
    # Non-empty reference but the scope matches no HS6 leaf → config error, not transient.
    responses.add(responses.GET, client.HS_REF_URL, json=HS_PAYLOAD, status=200)
    with pytest.raises(client.ComtradeRequestError):
        client.list_hs6_codes(["999999"])


@responses.activate
def test_list_hs6_codes_skips_schema_drifted_row_without_id() -> None:
    """An aggrLevel-6 reference row missing its id must be SKIPPED, not crash the
    whole run with a non-retryable KeyError before any chunk executes."""
    drifted = {
        "results": [
            {"id": "080121", "aggrLevel": 6},
            {"aggrLevel": 6},  # schema drift: no id → skipped, no KeyError
            {"id": "080122", "aggrLevel": 6},
        ]
    }
    responses.add(responses.GET, client.HS_REF_URL, json=drifted, status=200)
    out = client.list_hs6_codes(["0801"])
    assert out == ["080121", "080122"]  # the id-less row is dropped


# ─── fetch_chunk ─────────────────────────────────────────────────────────────
@responses.activate
def test_fetch_chunk_returns_string_frame_reindexed_to_bronze_columns() -> None:
    responses.add(
        responses.GET, re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"), json=DATA_PAYLOAD, status=200
    )
    df = client.fetch_chunk(
        BASE_URL,
        API_KEY,
        reporters=["76"],
        years=[2022],
        cmd_codes=["0801", "44"],
        flows=["X", "M"],
    )
    assert list(df.columns) == client.BRONZE_COLUMNS
    assert len(df) == 2
    assert df["primaryValue"].tolist() == ["98765", "4321"]
    # Columns absent from the sparse payload are present as NA, not missing.
    assert "customsCode" in df.columns
    assert df["customsCode"].isna().all()
    assert str(df["primaryValue"].dtype) == "string"


@responses.activate
def test_fetch_chunk_sends_key_in_header_only_never_in_url() -> None:
    responses.add(
        responses.GET, re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"), json=DATA_PAYLOAD, status=200
    )
    client.fetch_chunk(
        BASE_URL, API_KEY, reporters=["76", "842"], years=[2022], cmd_codes=["0801"], flows=["X"]
    )
    req = responses.calls[0].request
    assert req.headers["Ocp-Apim-Subscription-Key"] == API_KEY
    assert API_KEY not in req.url  # secret never leaks into the URL/logs


@responses.activate
def test_fetch_chunk_builds_comma_lists_and_omits_partner_code() -> None:
    responses.add(
        responses.GET, re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"), json=DATA_PAYLOAD, status=200
    )
    client.fetch_chunk(
        BASE_URL,
        API_KEY,
        reporters=["76", "842"],
        years=[2022, 2023],
        cmd_codes=["0801", "44"],
        flows=["X", "M"],
    )
    url = responses.calls[0].request.url
    assert "reporterCode=76,842" in url
    assert "period=2022,2023" in url
    assert "cmdCode=0801,44" in url
    assert "flowCode=X,M" in url
    assert "partnerCode" not in url  # omitted → every partner (bilateral matrix)
    assert "customsCode" not in url  # omitted when customs_code=="" (pull every regime)


@responses.activate
def test_fetch_chunk_adds_customs_code_filter_when_set() -> None:
    """The totals-only pull passes customs_code="C00" → customsCode=C00 in the URL, so
    only the "todos os regimes / total" aggregate is downloaded (no per-regime breakdowns)."""
    responses.add(
        responses.GET, re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"), json=DATA_PAYLOAD, status=200
    )
    client.fetch_chunk(
        BASE_URL,
        API_KEY,
        reporters=["76"],
        years=[2023],
        cmd_codes=["0801"],
        flows=["X", "M"],
        customs_code="C00",
    )
    assert "customsCode=C00" in responses.calls[0].request.url


@responses.activate
def test_fetch_chunk_empty_data_returns_empty_bronze_frame() -> None:
    responses.add(
        responses.GET, re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"), json={"data": []}, status=200
    )
    df = client.fetch_chunk(
        BASE_URL, API_KEY, reporters=["76"], years=[2022], cmd_codes=["0801"], flows=["X"]
    )
    assert df.empty
    assert list(df.columns) == client.BRONZE_COLUMNS


@responses.activate
def test_fetch_chunk_raises_permanent_on_400() -> None:
    responses.add(responses.GET, re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"), status=400)
    with pytest.raises(client.ComtradeRequestError) as exc:
        client.fetch_chunk.__wrapped__(  # type: ignore[attr-defined]
            BASE_URL, API_KEY, reporters=["76"], years=[2022], cmd_codes=["0801"], flows=["X"]
        )
    assert not isinstance(exc.value, client.ComtradeTransientError)  # 400 not retried


@responses.activate
def test_fetch_chunk_raises_quota_error_on_429() -> None:
    """A keyed-call 429 with no Retry-After means the daily quota is spent →
    ComtradeQuotaError, and it is deliberately NOT a transient/retryable error
    (the pipeline stops on it and the user re-runs later to resume)."""
    responses.add(responses.GET, re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"), status=429)
    with pytest.raises(client.ComtradeQuotaError) as exc:
        client.fetch_chunk.__wrapped__(  # type: ignore[attr-defined]
            BASE_URL, API_KEY, reporters=["76"], years=[2022], cmd_codes=["0801"], flows=["X"]
        )
    assert not isinstance(exc.value, client.ComtradeTransientError)  # not retried
    assert "re-run to resume" in str(exc.value)


@responses.activate
def test_fetch_chunk_429_with_short_retry_after_is_transient_rate_limit() -> None:
    """APIM also answers 429 for its per-second burst limiter (short Retry-After).
    That is NOT daily-quota exhaustion: it must be transient/retryable so an
    unattended run backs off instead of aborting with a bogus 'quota exhausted'."""
    responses.add(
        responses.GET,
        re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"),
        status=429,
        headers={"Retry-After": "2"},
    )
    with pytest.raises(client.ComtradeTransientError) as exc:
        client.fetch_chunk.__wrapped__(  # type: ignore[attr-defined]
            BASE_URL, API_KEY, reporters=["76"], years=[2022], cmd_codes=["0801"], flows=["X"]
        )
    assert "rate limited" in str(exc.value)


@responses.activate
def test_fetch_chunk_429_with_long_retry_after_is_quota() -> None:
    """A Retry-After on the scale of hours is the daily quota replenishing —
    classified as quota exhaustion (stop the run), not a retryable rate limit."""
    responses.add(
        responses.GET,
        re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"),
        status=429,
        headers={"Retry-After": "43200"},
    )
    with pytest.raises(client.ComtradeQuotaError):
        client.fetch_chunk.__wrapped__(  # type: ignore[attr-defined]
            BASE_URL, API_KEY, reporters=["76"], years=[2022], cmd_codes=["0801"], flows=["X"]
        )


@responses.activate
def test_fetch_chunk_canonicalizes_floatified_integer_codes() -> None:
    """A JSON null anywhere in an integer-coded column floatifies the whole column
    (motCode 0 → '0.0', qtyUnitCode -1 → '-1.0'); Silver's exact-string filters
    (motCode = '0', the qtyUnitCode = '-1' dedup preference) would then silently
    drop every row of the response. Codes must land as plain integer strings."""
    payload = {
        "data": [
            {
                "refYear": 2022,
                "reporterCode": 76,
                "motCode": 0,
                "mosCode": 0,
                "partner2Code": 0,
                "qtyUnitCode": -1,
                "customsCode": "C00",
                "primaryValue": 10.5,
            },
            {
                "refYear": 2022,
                "reporterCode": 76,
                "motCode": None,
                "mosCode": None,
                "partner2Code": None,
                "qtyUnitCode": None,
                "customsCode": "C00",
                "primaryValue": 1.25,
            },
        ]
    }
    responses.add(
        responses.GET, re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"), json=payload, status=200
    )
    df = client.fetch_chunk(
        BASE_URL, API_KEY, reporters=["76"], years=[2022], cmd_codes=["0801"], flows=["X"]
    )
    assert df["motCode"].iloc[0] == "0"  # not '0.0'
    assert df["mosCode"].iloc[0] == "0"
    assert df["partner2Code"].iloc[0] == "0"
    assert df["qtyUnitCode"].iloc[0] == "-1"  # not '-1.0'
    assert pd.isna(df["motCode"].iloc[1])  # a genuine null stays NA
    assert df["customsCode"].iloc[0] == "C00"  # alphanumeric codes untouched
    assert df["primaryValue"].iloc[0] == "10.5"  # measures keep decimals


# ─── client-side throttle between keyed calls ─────────────────────────────────
def test_throttle_spaces_consecutive_keyed_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(client, "INTER_CALL_DELAY_S", 5.0)
    monkeypatch.setattr(client.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(client, "_last_keyed_call_monotonic", client.time.monotonic())
    client._throttle_keyed_call()
    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 5.0


def test_throttle_disabled_when_delay_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(client, "INTER_CALL_DELAY_S", 0.0)
    monkeypatch.setattr(client.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(client, "_last_keyed_call_monotonic", client.time.monotonic())
    client._throttle_keyed_call()
    assert sleeps == []


# ─── fetch_chunk_adaptive (recursive split on the per-call cap) ───────────────
def _frame(n: int) -> pd.DataFrame:
    return pd.DataFrame({c: ["x"] * n for c in client.BRONZE_COLUMNS}, dtype="string")


def test_fetch_chunk_adaptive_splits_reporters_until_under_cap(monkeypatch) -> None:
    """A capped multi-reporter call is split by reporter until each leaf call is
    under the cap; the leaves are concatenated into the complete frame."""
    seen: list[tuple[str, ...]] = []
    customs_seen: set[str] = set()

    def fake_fetch(base, key, *, reporters, years, cmd_codes, flows, customs_code=""):
        seen.append(tuple(reporters))
        customs_seen.add(customs_code)
        # >1 reporter saturates the cap (forces a split); a lone reporter is small.
        return _frame(client.PER_CALL_ROW_CAP if len(reporters) > 1 else 10)

    monkeypatch.setattr(client, "fetch_chunk", fake_fetch)
    df = client.fetch_chunk_adaptive(
        "u",
        "k",
        reporters=["1", "2", "3", "4"],
        years=[2023],
        cmd_codes=["0801"],
        flows=["X"],
        customs_code="C00",
    )
    assert len(df) == 40  # 4 single-reporter leaves × 10 rows
    assert ("1", "2", "3", "4") in seen  # the initial capped call
    assert ("1",) in seen and ("4",) in seen  # split down to single reporters
    # customsCode is a single fixed value, threaded unchanged through every split.
    assert customs_seen == {"C00"}


def test_fetch_chunk_adaptive_falls_back_to_flows_then_cmd(monkeypatch) -> None:
    """With a single dense reporter, the split moves on to flows, then cmd codes."""
    leaf_dims: list[tuple[int, int]] = []

    def fake_fetch(base, key, *, reporters, years, cmd_codes, flows, customs_code=""):
        # Stay capped until BOTH flows and cmd are down to one each.
        if len(flows) > 1 or len(cmd_codes) > 1:
            return _frame(client.PER_CALL_ROW_CAP)
        leaf_dims.append((len(flows), len(cmd_codes)))
        return _frame(5)

    monkeypatch.setattr(client, "fetch_chunk", fake_fetch)
    df = client.fetch_chunk_adaptive(
        "u", "k", reporters=["1"], years=[2023], cmd_codes=["a", "b"], flows=["X", "M"]
    )
    # 2 flows × 2 cmd = 4 leaves, each (1 flow, 1 cmd), 5 rows → 20 total.
    assert len(df) == 20
    assert leaf_dims == [(1, 1)] * 4


def test_fetch_chunk_adaptive_raises_truncation_when_singleton_still_caps(monkeypatch) -> None:
    """An indivisible (single reporter/flow/cmd) call that STILL returns the cap
    cannot be split further; rather than silently archive a truncated chunk, it
    emits a ``truncated`` event and raises ComtradeTruncationError so the chunk is
    left un-archived for a later run to re-attempt."""
    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        client.observability, "emit", lambda event, **fields: emitted.append((event, fields))
    )
    # Every call is at the cap, even the indivisible leaf.
    monkeypatch.setattr(client, "fetch_chunk", lambda *a, **k: _frame(client.PER_CALL_ROW_CAP))
    with pytest.raises(client.ComtradeTruncationError):
        client.fetch_chunk_adaptive(
            "u", "k", reporters=["1"], years=[2023], cmd_codes=["a"], flows=["X"]
        )
    assert any(event == "truncated" for event, _ in emitted)
    # Not a transient error → the pipeline records it as a chunk failure, no retry.
    assert not issubclass(client.ComtradeTruncationError, client.ComtradeTransientError)


@responses.activate
def test_fetch_chunk_403_out_of_call_volume_is_quota_not_a_bug() -> None:
    """UN Comtrade signals the DAILY volume quota with 403, not 429.

    Observed in a real backfill (2026-08-18): 508 chunks landed, then every call returned
    403 {"message": "Out of call volume quota. Quota will be replenished in 19:07:31."}.
    Classified as a plain request error, the run exited 1 and paged a human for the
    textbook expected, self-healing, already-resumable condition — the exact alert noise
    ComtradeQuotaError exists to prevent."""
    responses.add(
        responses.GET,
        re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"),
        status=403,
        json={
            "statusCode": 403,
            "message": "Out of call volume quota. Quota will be replenished in 19:07:31.",
        },
    )
    with pytest.raises(client.ComtradeQuotaError) as exc:
        client.fetch_chunk.__wrapped__(  # type: ignore[attr-defined]
            BASE_URL, API_KEY, reporters=["76"], years=[2022], cmd_codes=["0801"], flows=["X"]
        )
    assert not isinstance(exc.value, client.ComtradeTransientError)  # never retried
    assert "re-run to resume" in str(exc.value)
    assert "call volume quota" in str(exc.value).lower()


@responses.activate
def test_fetch_chunk_403_for_a_bad_key_still_pages() -> None:
    """Matched on the MESSAGE, not the status: a 403 from a revoked/invalid subscription is
    a real failure a human must see, and must NOT be laundered into 'quota — resume later',
    which would silently stall ingestion forever."""
    responses.add(
        responses.GET,
        re.compile(rf"{re.escape(BASE_URL)}/C/A/HS.*"),
        status=403,
        json={"statusCode": 403, "message": "Access denied due to invalid subscription key."},
    )
    with pytest.raises(client.ComtradeRequestError) as exc:
        client.fetch_chunk.__wrapped__(  # type: ignore[attr-defined]
            BASE_URL, API_KEY, reporters=["76"], years=[2022], cmd_codes=["0801"], flows=["X"]
        )
    assert not isinstance(exc.value, client.ComtradeQuotaError)
    assert "invalid subscription key" in str(exc.value)
