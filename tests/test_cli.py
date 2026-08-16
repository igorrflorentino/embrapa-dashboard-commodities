"""Tests for the Typer-based CLI dispatcher.

We mock the underlying pipeline calls; the goal is to confirm:
 1. each command parses its arguments correctly, and
 2. dispatches to the right function with the right values.

We do NOT exercise the real ingestion logic here — separate
test_ibge_pipeline / test_bcb_*_pipeline files cover that surface.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from embrapa_dashboard import cli
from embrapa_dashboard.config import Settings

runner = CliRunner()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gcp_project_id="test-project",
        gcs_bucket="test-bucket",
        ibge_start_year=2020,
        ibge_end_year=2020,
        ibge_product_codes="3405",
        bcb_inflation_series="433:IPCA",
        bcb_currency_series="3694:USD",
        _env_file=None,
    )  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _silence_observability(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect the event-log directory and stub `emit` so no JSONL is written."""
    monkeypatch.setenv("EMBRAPA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(
        cli.observability,
        "init_run",
        lambda pipeline: ("test-run-id", tmp_path / f"{pipeline}.jsonl"),
    )
    monkeypatch.setattr(cli.observability, "emit", lambda *a, **kw: None)


# ─── ingest ibge ─────────────────────────────────────────────────────────────
def test_ingest_ibge_dispatches_and_prints_destination(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    pipeline_run = MagicMock(return_value="proj.bronze_ibge.sidra_t289_raw")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.ibge_pipeline, "run", pipeline_run)

    result = runner.invoke(cli.app, ["ingest", "ibge"])

    assert result.exit_code == 0, result.output
    pipeline_run.assert_called_once_with(settings, full=False, from_raw=False)
    assert "IBGE bronze loaded" in result.output
    assert "proj.bronze_ibge.sidra_t289_raw" in result.output


def test_ingest_ibge_warns_when_pipeline_returns_empty(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """An empty return value means SIDRA had nothing — print a hint, not a crash."""
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.ibge_pipeline, "run", lambda s, full=False, from_raw=False: "")

    result = runner.invoke(cli.app, ["ingest", "ibge"])

    assert result.exit_code == 0
    assert "skipped" in result.output
    assert "IBGE_END_YEAR" in result.output


def test_ingest_ibge_propagates_pipeline_error(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    def boom(_settings: Settings, full: bool = False, from_raw: bool = False) -> str:
        raise RuntimeError("sidra exploded")

    monkeypatch.setattr(cli.ibge_pipeline, "run", boom)

    result = runner.invoke(cli.app, ["ingest", "ibge"])

    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)


# ─── ingest ibge-pam ─────────────────────────────────────────────────────────
def test_ingest_ibge_pam_dispatches_and_prints_destination(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """`ingest ibge-pam` dispatches to pam_pipeline.run with the delta defaults and
    surfaces the loaded destination (the PEVS sibling — this is the PAM source)."""
    pipeline_run = MagicMock(return_value="proj.bronze_ibge.sidra_t5457_raw")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.pam_pipeline, "run", pipeline_run)

    result = runner.invoke(cli.app, ["ingest", "ibge-pam"])

    assert result.exit_code == 0, result.output
    pipeline_run.assert_called_once_with(settings, full=False, from_raw=False)
    assert "IBGE PAM bronze loaded" in result.output
    assert "proj.bronze_ibge.sidra_t5457_raw" in result.output


def test_ingest_ibge_pam_full_flag_propagates(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    pipeline_run = MagicMock(return_value="proj.bronze_ibge.sidra_t5457_raw")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.pam_pipeline, "run", pipeline_run)

    result = runner.invoke(cli.app, ["ingest", "ibge-pam", "--full"])

    assert result.exit_code == 0, result.output
    pipeline_run.assert_called_once_with(settings, full=True, from_raw=False)


def test_ingest_ibge_pam_warns_when_pipeline_returns_empty(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """An empty return means SIDRA had nothing new — print a hint, not a crash."""
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.pam_pipeline, "run", lambda s, full=False, from_raw=False: "")

    result = runner.invoke(cli.app, ["ingest", "ibge-pam"])

    assert result.exit_code == 0
    assert "skipped" in result.output
    assert "PAM_END_YEAR" in result.output


# ─── ingest bcb-inflation ────────────────────────────────────────────────────
def test_ingest_bcb_inflation_delta_by_default(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    bcb_run = MagicMock(return_value="proj.bronze_bcb.inflation_series_raw")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.bcb_inflation, "run", bcb_run)

    result = runner.invoke(cli.app, ["ingest", "bcb-inflation"])

    assert result.exit_code == 0, result.output
    bcb_run.assert_called_once_with(settings, full=False, from_raw=False)
    assert "BCB inflation bronze loaded" in result.output


def test_ingest_bcb_inflation_full_flag_propagates(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    bcb_run = MagicMock(return_value="proj.bronze_bcb.inflation_series_raw")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.bcb_inflation, "run", bcb_run)

    result = runner.invoke(cli.app, ["ingest", "bcb-inflation", "--full"])

    assert result.exit_code == 0, result.output
    bcb_run.assert_called_once_with(settings, full=True, from_raw=False)


def test_ingest_bcb_inflation_empty_returns_friendly_message(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.bcb_inflation, "run", lambda s, full, from_raw=False: "")

    result = runner.invoke(cli.app, ["ingest", "bcb-inflation"])

    assert result.exit_code == 0
    assert "nothing new" in result.output


# ─── ingest bcb-currency ─────────────────────────────────────────────────────
def test_ingest_bcb_currency_delta_by_default(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    bcb_run = MagicMock(return_value="proj.bronze_bcb.currency_series_raw")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.bcb_currency, "run", bcb_run)

    result = runner.invoke(cli.app, ["ingest", "bcb-currency"])

    assert result.exit_code == 0, result.output
    bcb_run.assert_called_once_with(settings, full=False, from_raw=False)


def test_ingest_bcb_currency_full_flag_propagates(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    bcb_run = MagicMock(return_value="proj.bronze_bcb.currency_series_raw")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.bcb_currency, "run", bcb_run)

    result = runner.invoke(cli.app, ["ingest", "bcb-currency", "--full"])

    assert result.exit_code == 0, result.output
    bcb_run.assert_called_once_with(settings, full=True, from_raw=False)


# ─── ingest ibge-batch ───────────────────────────────────────────────────────
def test_ingest_ibge_batch_auto_chunk_iterates_full_window(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """No --chunk-years: chunk_years is auto-computed; the pipeline is invoked once per chunk."""
    settings.ibge_start_year = 2010
    settings.ibge_end_year = 2014
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    # Force a known chunk size (1 year) so we know exactly how many calls happen.
    monkeypatch.setattr(cli, "recommended_chunk_years", lambda n_products: 1)
    monkeypatch.setattr(cli, "resolve_clients", lambda s: (MagicMock(), MagicMock()))

    pipeline_run = MagicMock(return_value="proj.bronze_ibge.sidra_t289_raw")
    monkeypatch.setattr(cli.ibge_pipeline, "run", pipeline_run)

    result = runner.invoke(cli.app, ["ingest", "ibge-batch"])

    assert result.exit_code == 0, result.output
    # 5 years, chunk_years=1 → 5 chunks → 5 pipeline runs.
    assert pipeline_run.call_count == 5
    # Each call must have received a chunked Settings, not the full window.
    chunk_years = [
        (c.args[0].ibge_start_year, c.args[0].ibge_end_year) for c in pipeline_run.call_args_list
    ]
    assert chunk_years == [(2010, 2010), (2011, 2011), (2012, 2012), (2013, 2013), (2014, 2014)]


def test_ingest_ibge_batch_manual_chunk_size_overrides_auto(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    settings.ibge_start_year = 2010
    settings.ibge_end_year = 2013  # 4 years total
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    auto = MagicMock(return_value=999)  # should NOT be called when --chunk-years given.
    monkeypatch.setattr(cli, "recommended_chunk_years", auto)
    monkeypatch.setattr(cli, "resolve_clients", lambda s: (MagicMock(), MagicMock()))

    pipeline_run = MagicMock(return_value="proj.bronze_ibge.sidra_t289_raw")
    monkeypatch.setattr(cli.ibge_pipeline, "run", pipeline_run)

    result = runner.invoke(cli.app, ["ingest", "ibge-batch", "--chunk-years", "2"])

    assert result.exit_code == 0, result.output
    auto.assert_not_called()
    # 4 years / 2 = 2 chunks.
    assert pipeline_run.call_count == 2


def test_ingest_ibge_batch_raises_when_start_year_unset(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    settings.ibge_start_year = None
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    result = runner.invoke(cli.app, ["ingest", "ibge-batch"])

    assert result.exit_code != 0
    assert "IBGE_START_YEAR" in result.output


def test_ingest_ibge_batch_continues_after_chunk_failure(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A single failed chunk must not strand the rest. Exit 1, but every chunk ran."""
    settings.ibge_start_year = 2010
    settings.ibge_end_year = 2012
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "recommended_chunk_years", lambda n_products: 1)
    monkeypatch.setattr(cli, "resolve_clients", lambda s: (MagicMock(), MagicMock()))

    call_log: list[int] = []

    def flaky(chunk_settings: Settings, **kwargs: object) -> str:
        call_log.append(chunk_settings.ibge_start_year)
        if chunk_settings.ibge_start_year == 2011:
            raise RuntimeError("network blip")
        return "proj.bronze_ibge.sidra_t289_raw"

    monkeypatch.setattr(cli.ibge_pipeline, "run", flaky)

    result = runner.invoke(cli.app, ["ingest", "ibge-batch"])

    # Continue-on-failure: every chunk attempted.
    assert call_log == [2010, 2011, 2012]
    # But exit code reports the failure so CI/cron can react.
    assert result.exit_code == 1
    assert "2011 failed" in result.output or "2011-2011 failed" in result.output


def test_ingest_ibge_batch_exits_zero_when_every_failure_is_transient(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A purely TRANSIENT chunk failure must not page a human.

    A SIDRA connection drop on a large year window is the failure this command exists to
    survive — it self-heals on the next run. The chunk runner marks it transient, so the
    summary exits 0 and the Cloud Monitoring job-failure alert stays quiet. (Contrast with
    the RuntimeError test above, which is NOT transient and still exits 1.)"""
    from embrapa_dashboard.ibge.client import SidraTransientError

    settings.ibge_start_year = 2010
    settings.ibge_end_year = 2012
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "recommended_chunk_years", lambda n_products: 1)
    monkeypatch.setattr(cli, "resolve_clients", lambda s: (MagicMock(), MagicMock()))

    def flaky(chunk_settings: Settings, **kwargs: object) -> str:
        if chunk_settings.ibge_start_year == 2011:
            raise SidraTransientError("HTTP 503 for SIDRA")
        return "proj.bronze_ibge.sidra_t289_raw"

    monkeypatch.setattr(cli.ibge_pipeline, "run", flaky)

    result = runner.invoke(cli.app, ["ingest", "ibge-batch"])

    assert result.exit_code == 0, result.output
    assert "transient" in result.output


_SINGLE_SHOT_INGESTS = [
    ("ibge", "ibge_pipeline", "sidra"),
    ("ibge-pam", "pam_pipeline", "sidra"),
    ("ibge-ppm", "ppm_pipeline", "sidra"),
    ("bcb-inflation", "bcb_inflation", "bcb"),
    ("bcb-currency", "bcb_currency", "bcb"),
]


def _transient_error(kind: str) -> Exception:
    """The real per-source transient class, so a broken class hierarchy fails the test."""
    if kind == "sidra":
        from embrapa_dashboard.ibge.client import SidraTransientError

        return SidraTransientError("HTTP 503 for SIDRA")
    from embrapa_dashboard.bcb.client import BcbTransientError

    return BcbTransientError("HTTP 503 for BCB SGS")


@pytest.mark.parametrize(("command", "module", "kind"), _SINGLE_SHOT_INGESTS)
def test_single_shot_ingest_exits_zero_when_the_failure_is_transient(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, command: str, module: str, kind: str
) -> None:
    """The single-shot commands must honour the same exit-code rule as the chunked ones.

    ``ibge-pam`` and ``ibge-ppm`` each have their own ENABLED monthly Cloud Scheduler
    trigger against the ingestion job, and the alert policy watches the JOB's
    ``result="failed"`` — not the command's args. Before this, a transient SIDRA blip on
    the 2nd/3rd of the month paged a human with the same red "unexpected failure" mail a
    real bug produces."""
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    def boom(*_args: object, **_kwargs: object) -> str:
        raise _transient_error(kind)

    monkeypatch.setattr(getattr(cli, module), "run", boom)

    result = runner.invoke(cli.app, ["ingest", command])

    assert result.exit_code == 0, result.output
    assert "transient" in result.output


@pytest.mark.parametrize(("command", "module", "kind"), _SINGLE_SHOT_INGESTS)
def test_single_shot_ingest_still_exits_nonzero_on_a_real_bug(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, command: str, module: str, kind: str
) -> None:
    """Only a MARKED transient failure is downgraded — anything else still pages, with its
    traceback intact (the wrapper re-raises untouched rather than swallowing)."""
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    def boom(*_args: object, **_kwargs: object) -> str:
        raise ValueError("a real bug")

    monkeypatch.setattr(getattr(cli, module), "run", boom)

    result = runner.invoke(cli.app, ["ingest", command])

    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)


def test_ingest_ibge_batch_exits_one_when_any_failure_is_not_transient(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """One non-transient failure alongside a transient one must still alert."""
    from embrapa_dashboard.ibge.client import SidraTransientError

    settings.ibge_start_year = 2010
    settings.ibge_end_year = 2012
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "recommended_chunk_years", lambda n_products: 1)
    monkeypatch.setattr(cli, "resolve_clients", lambda s: (MagicMock(), MagicMock()))

    def flaky(chunk_settings: Settings, **kwargs: object) -> str:
        if chunk_settings.ibge_start_year == 2010:
            raise SidraTransientError("HTTP 503 for SIDRA")
        if chunk_settings.ibge_start_year == 2011:
            raise ValueError("a real bug")  # not a SourceTransientError
        return "proj.bronze_ibge.sidra_t289_raw"

    monkeypatch.setattr(cli.ibge_pipeline, "run", flaky)

    result = runner.invoke(cli.app, ["ingest", "ibge-batch"])

    assert result.exit_code == 1, result.output


# ─── ingest comtrade ──────────────────────────────────────────────────────────
def _wire_comtrade(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Settings:
    """Common stubs for the comtrade ingest command (no GCP, explicit reporters so
    the keyless Reporters lookup is skipped)."""
    settings.comtrade_api_key = "k"
    settings.comtrade_reporters = "76,842"  # explicit list → no list_reporters() call
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "resolve_clients", lambda s: (MagicMock(), MagicMock()))
    monkeypatch.setattr(cli.comtrade_pipeline, "ensure_destination", lambda s, c: "p.d.t")
    monkeypatch.setattr(cli.comtrade_pipeline, "bronze_one", lambda *a, **k: "p.d.t")
    return settings


def test_ingest_comtrade_exits_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    settings.comtrade_api_key = ""
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    result = runner.invoke(cli.app, ["ingest", "comtrade"])

    assert result.exit_code == 1
    assert "COMTRADE_API_KEY is empty" in result.output


def test_ingest_comtrade_happy_path_reports_complete(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    _wire_comtrade(monkeypatch, settings)
    settings.comtrade_start_year = 2023
    settings.comtrade_end_year = 2023  # 1 year × 1 batch (2 reporters) = 1 chunk
    monkeypatch.setattr(cli.comtrade_pipeline, "sync_raw", lambda *a, **k: True)

    result = runner.invoke(cli.app, ["ingest", "comtrade"])

    assert result.exit_code == 0, result.output
    assert "All 1 COMTRADE chunk(s) complete" in result.output


def test_ingest_comtrade_continues_after_chunk_failure(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A failed chunk (e.g. quota) must not strand the rest. Exit 1, every chunk tried."""
    _wire_comtrade(monkeypatch, settings)
    settings.comtrade_start_year = 2022
    settings.comtrade_end_year = 2023  # 2 years × 1 batch = 2 chunks
    seen_years: list[int] = []

    def flaky(_s: Settings, year: int, _batch: object, **kwargs: object) -> bool:
        seen_years.append(year)
        if year == 2022:
            raise RuntimeError("daily quota hit")
        return True

    monkeypatch.setattr(cli.comtrade_pipeline, "sync_raw", flaky)

    result = runner.invoke(cli.app, ["ingest", "comtrade"])

    assert seen_years == [2022, 2023]  # the 2022 failure did not stop 2023
    assert result.exit_code == 1
    assert "failed" in result.output


def test_ingest_comtrade_quota_exhausted_reports_and_exits(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A quota error mid-run surfaces a clean 'quota exhausted — re-run to resume'
    message and exits 0 — daily quota exhaustion is EXPECTED and self-healing (the
    next scheduled run resumes from the un-archived chunks), so it must NOT trip the
    Cloud Run job-failure alert. A genuine (non-quota) chunk failure still exits 1."""
    from embrapa_dashboard.comtrade.client import ComtradeQuotaError

    _wire_comtrade(monkeypatch, settings)
    settings.comtrade_start_year = 2022
    settings.comtrade_end_year = 2023

    def quota(_s: Settings, year: int, _batch: object, **kwargs: object) -> bool:
        raise ComtradeQuotaError("quota exhausted — re-run to resume")

    monkeypatch.setattr(cli.comtrade_pipeline, "sync_raw", quota)

    result = runner.invoke(cli.app, ["ingest", "comtrade"])

    assert result.exit_code == 0, result.output
    assert "quota exhausted" in result.output
    assert "re-run to resume" in result.output


def test_ingest_comtrade_from_raw_skips_api(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """`--from-raw` rebuilds Bronze from archived raw — it must NOT call sync_raw."""
    _wire_comtrade(monkeypatch, settings)
    settings.comtrade_start_year = 2023
    settings.comtrade_end_year = 2023
    sync = MagicMock()
    monkeypatch.setattr(cli.comtrade_pipeline, "sync_raw", sync)
    monkeypatch.setattr(cli.comtrade_pipeline, "has_raw", lambda *a, **k: True)

    result = runner.invoke(cli.app, ["ingest", "comtrade", "--from-raw"])

    assert result.exit_code == 0, result.output
    sync.assert_not_called()


# ─── ingest comex ─────────────────────────────────────────────────────────────
def _wire_comex(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, chunks: list[tuple[str, int]]
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "resolve_clients", lambda s: (MagicMock(), MagicMock()))
    monkeypatch.setattr(cli.comex_pipeline, "ensure_destination", lambda s, c: "p.d.t")
    monkeypatch.setattr(cli.comex_pipeline, "all_chunks", lambda s: chunks)
    monkeypatch.setattr(cli.comex_pipeline, "bronze_one", lambda *a, **k: "p.d.t")


def test_ingest_comex_happy_path_reports_complete(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    _wire_comex(monkeypatch, settings, [("export", 2023)])
    monkeypatch.setattr(cli.comex_pipeline, "sync_raw", lambda *a, **k: True)

    result = runner.invoke(cli.app, ["ingest", "comex"])

    assert result.exit_code == 0, result.output
    assert "All 1 COMEX chunk(s) complete" in result.output


def test_ingest_comex_continues_after_chunk_failure(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    _wire_comex(monkeypatch, settings, [("export", 2022), ("export", 2023)])
    seen: list[tuple[str, int]] = []

    def flaky(_s: Settings, flow: str, year: int, **kwargs: object) -> bool:
        seen.append((flow, year))
        if year == 2022:
            raise RuntimeError("source 503")
        return True

    monkeypatch.setattr(cli.comex_pipeline, "sync_raw", flaky)

    result = runner.invoke(cli.app, ["ingest", "comex"])

    assert seen == [("export", 2022), ("export", 2023)]  # failure didn't strand the rest
    assert result.exit_code == 1
    assert "failed" in result.output


def test_ingest_comex_from_raw_skips_download(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    _wire_comex(monkeypatch, settings, [("export", 2023)])
    sync = MagicMock()
    monkeypatch.setattr(cli.comex_pipeline, "sync_raw", sync)
    monkeypatch.setattr(cli.comex_pipeline, "has_raw", lambda *a, **k: True)

    result = runner.invoke(cli.app, ["ingest", "comex", "--from-raw"])

    assert result.exit_code == 0, result.output
    sync.assert_not_called()


# ─── ingest all ──────────────────────────────────────────────────────────────
def test_ingest_all_runs_every_pipeline_in_order(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    order: list[str] = []
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.ibge_pipeline, "run", lambda s, full: order.append("ibge") or "")
    monkeypatch.setattr(
        cli.bcb_inflation, "run", lambda s, full: order.append(f"inflation-{full}") or ""
    )
    monkeypatch.setattr(
        cli.bcb_currency, "run", lambda s, full: order.append(f"currency-{full}") or ""
    )
    monkeypatch.setattr(
        cli.comex_pipeline, "run", lambda s, full: order.append(f"comex-{full}") or ""
    )

    result = runner.invoke(cli.app, ["ingest", "all"])

    assert result.exit_code == 0, result.output
    assert order == ["ibge", "inflation-False", "currency-False", "comex-False"]


def test_ingest_all_full_flag_propagates_to_delta_pipelines(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """`--full` cascades to every delta-aware pipeline — IBGE included now."""
    seen_full: list[bool] = []
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.ibge_pipeline, "run", lambda s, full: seen_full.append(full) or "")
    monkeypatch.setattr(cli.bcb_inflation, "run", lambda s, full: seen_full.append(full) or "")
    monkeypatch.setattr(cli.bcb_currency, "run", lambda s, full: seen_full.append(full) or "")
    monkeypatch.setattr(cli.comex_pipeline, "run", lambda s, full: seen_full.append(full) or "")

    result = runner.invoke(cli.app, ["ingest", "all", "--full"])

    assert result.exit_code == 0, result.output
    assert seen_full == [True, True, True, True]


def test_ingest_all_wraps_each_pipeline_in_observability(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """`ingest all` must open an event log per pipeline (via pipeline_run), so the
    batch is visible in `embrapa monitor` like the individual ingest commands —
    not run silently with no event log as it did before."""
    init_calls: list[str] = []
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.ibge_pipeline, "run", lambda s, full: "")
    monkeypatch.setattr(cli.bcb_inflation, "run", lambda s, full: "")
    monkeypatch.setattr(cli.bcb_currency, "run", lambda s, full: "")
    monkeypatch.setattr(cli.comex_pipeline, "run", lambda s, full: "")
    monkeypatch.setattr(
        cli.observability,
        "init_run",
        lambda pipeline: init_calls.append(pipeline) or ("rid", Path(f"{pipeline}.jsonl")),
    )

    result = runner.invoke(cli.app, ["ingest", "all"])

    assert result.exit_code == 0, result.output
    # One event log opened per registered pipeline, in INGESTS order.
    assert init_calls == ["ibge", "bcb-inflation", "bcb-currency", "comex"]


def test_ingest_all_continues_after_a_source_fails(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A source that raises (here BCB inflation) must not abort the batch: the
    remaining sources still run, and the command exits non-zero to flag it."""
    ran: list[str] = []
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.ibge_pipeline, "run", lambda s, full: ran.append("ibge") or "")

    def boom(_s: Settings, full: bool) -> str:
        ran.append("inflation")
        raise RuntimeError("BCB 503")

    monkeypatch.setattr(cli.bcb_inflation, "run", boom)
    monkeypatch.setattr(cli.bcb_currency, "run", lambda s, full: ran.append("currency") or "")
    monkeypatch.setattr(cli.comex_pipeline, "run", lambda s, full: ran.append("comex") or "")

    result = runner.invoke(cli.app, ["ingest", "all"])

    # Every source attempted despite the inflation failure.
    assert ran == ["ibge", "inflation", "currency", "comex"]
    assert result.exit_code == 1
    assert "1 source(s) failed" in result.output
    assert "BCB inflation" in result.output  # the failed source's label


def test_ingest_all_aborts_cleanly_listing_partial_chunk_failure(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """When a pipeline raises IngestPartialFailure (its own chunk loop had a
    failure), `ingest all` records it as a source failure and exits 1."""
    from embrapa_dashboard.core import IngestPartialFailure

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.ibge_pipeline, "run", lambda s, full: "")
    monkeypatch.setattr(cli.bcb_inflation, "run", lambda s, full: "")
    monkeypatch.setattr(cli.bcb_currency, "run", lambda s, full: "")

    def comex_partial(_s: Settings, full: bool) -> str:
        raise IngestPartialFailure([("EXP_2026", "HTTP 503")])

    monkeypatch.setattr(cli.comex_pipeline, "run", comex_partial)

    result = runner.invoke(cli.app, ["ingest", "all"])

    assert result.exit_code == 1
    assert "MDIC COMEX" in result.output


# ─── ingest reconcile ────────────────────────────────────────────────────────
def _wire_reconcile(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    """Stub GCP + chunk sizing so reconcile's IBGE batch leg runs offline (1-year chunks)."""
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "recommended_chunk_years", lambda n_products: 1)
    monkeypatch.setattr(cli, "resolve_clients", lambda s: (MagicMock(), MagicMock()))


def test_ingest_reconcile_chunks_ibge_and_fulls_bcb_comex(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """IBGE PEVS runs year-CHUNKED (full per chunk); PAM/PPM + BCB×2 + COMEX run once
    with full=True (PAM/PPM are out of `all` but reconcile still catches their old-year
    revisions); COMTRADE (out of `all`, key-gated) is never touched."""
    settings.ibge_start_year = 2010
    settings.ibge_end_year = 2012  # 3 chunks at chunk_years=1
    _wire_reconcile(monkeypatch, settings)

    ibge_chunks: list[tuple[int, int]] = []
    monkeypatch.setattr(
        cli.ibge_pipeline,
        "run",
        lambda s, **kw: ibge_chunks.append((s.ibge_start_year, s.ibge_end_year)) or "dest",
    )
    full_seen: list[str] = []
    monkeypatch.setattr(
        cli.pam_pipeline, "run", lambda s, full: full_seen.append(f"pam-{full}") or ""
    )
    monkeypatch.setattr(
        cli.ppm_pipeline, "run", lambda s, full: full_seen.append(f"ppm-{full}") or ""
    )
    monkeypatch.setattr(
        cli.bcb_inflation, "run", lambda s, full: full_seen.append(f"inflation-{full}") or ""
    )
    monkeypatch.setattr(
        cli.bcb_currency, "run", lambda s, full: full_seen.append(f"currency-{full}") or ""
    )
    monkeypatch.setattr(
        cli.comex_pipeline, "run", lambda s, full: full_seen.append(f"comex-{full}") or ""
    )
    comtrade = MagicMock()
    monkeypatch.setattr(cli.comtrade_pipeline, "run", comtrade)

    result = runner.invoke(cli.app, ["ingest", "reconcile"])

    assert result.exit_code == 0, result.output
    # IBGE PEVS: one full=True load per year chunk (2010, 2011, 2012).
    assert ibge_chunks == [(2010, 2010), (2011, 2011), (2012, 2012)]
    # PAM/PPM (out of `all`) + BCB + COMEX: each once, forced full, in INGESTS order —
    # reconcile catches old-year revisions to PAM/PPM too.
    assert full_seen == ["pam-True", "ppm-True", "inflation-True", "currency-True", "comex-True"]
    # COMTRADE is key-gated / out of `all` — reconcile never re-ingests it.
    comtrade.assert_not_called()


def test_ingest_reconcile_continues_after_a_source_fails(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A BCB failure must not strand COMEX: every source still runs, exit is non-zero."""
    settings.ibge_start_year = 2010
    settings.ibge_end_year = 2010
    _wire_reconcile(monkeypatch, settings)

    ran: list[str] = []
    monkeypatch.setattr(cli.ibge_pipeline, "run", lambda s, **kw: ran.append("ibge") or "dest")
    monkeypatch.setattr(cli.pam_pipeline, "run", lambda s, full: ran.append("pam") or "")
    monkeypatch.setattr(cli.ppm_pipeline, "run", lambda s, full: ran.append("ppm") or "")

    def boom(_s: Settings, full: bool) -> str:
        ran.append("inflation")
        raise RuntimeError("BCB 503")

    monkeypatch.setattr(cli.bcb_inflation, "run", boom)
    monkeypatch.setattr(cli.bcb_currency, "run", lambda s, full: ran.append("currency") or "")
    monkeypatch.setattr(cli.comex_pipeline, "run", lambda s, full: ran.append("comex") or "")

    result = runner.invoke(cli.app, ["ingest", "reconcile"])

    assert ran == ["ibge", "pam", "ppm", "inflation", "currency", "comex"]
    assert result.exit_code == 1
    assert "1 source(s) failed" in result.output
    assert "BCB inflation" in result.output


def test_ingest_reconcile_records_ibge_chunk_failure_but_runs_rest(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A failed IBGE chunk is recorded as an IBGE source failure (exit 1), yet the
    BCB + COMEX legs still run — the chunk loop never raises out of the IBGE leg."""
    settings.ibge_start_year = 2010
    settings.ibge_end_year = 2011  # 2 chunks
    _wire_reconcile(monkeypatch, settings)

    def flaky(s: Settings, **kw: object) -> str:
        if s.ibge_start_year == 2011:
            raise RuntimeError("network blip")
        return "dest"

    monkeypatch.setattr(cli.ibge_pipeline, "run", flaky)
    ran_other: list[str] = []
    monkeypatch.setattr(cli.pam_pipeline, "run", lambda s, full: ran_other.append("pam") or "")
    monkeypatch.setattr(cli.ppm_pipeline, "run", lambda s, full: ran_other.append("ppm") or "")
    monkeypatch.setattr(
        cli.bcb_inflation, "run", lambda s, full: ran_other.append("inflation") or ""
    )
    monkeypatch.setattr(cli.bcb_currency, "run", lambda s, full: ran_other.append("currency") or "")
    monkeypatch.setattr(cli.comex_pipeline, "run", lambda s, full: ran_other.append("comex") or "")

    result = runner.invoke(cli.app, ["ingest", "reconcile"])

    assert result.exit_code == 1
    assert "IBGE PEVS" in result.output  # the failed leg is named in the summary
    # Continue-on-failure across sources: PAM/PPM + BCB + COMEX still ran.
    assert ran_other == ["pam", "ppm", "inflation", "currency", "comex"]


def test_ingest_reconcile_raises_when_ibge_start_year_unset(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """IBGE_START_YEAR unset is a real misconfig (the full window has no floor) —
    reconcile aborts cleanly rather than silently skipping history."""
    settings.ibge_start_year = None
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    result = runner.invoke(cli.app, ["ingest", "reconcile"])

    assert result.exit_code != 0
    assert "IBGE_START_YEAR" in result.output


# ─── discover ────────────────────────────────────────────────────────────────
def test_discover_ibge_products_prints_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    from embrapa_dashboard.discover import ProductMatch

    def fake_search(table_id: str, needles: list[str]) -> list[ProductMatch]:
        assert table_id == "289"
        assert needles == ["castanha", "madeira"]
        return [
            ProductMatch(code="3405", name="Castanha-do-pará", classification_id="193"),
            ProductMatch(code="3435", name="Madeira em tora", classification_id="193"),
        ]

    monkeypatch.setattr(cli.discover, "search_ibge_products", fake_search)

    result = runner.invoke(cli.app, ["discover", "ibge-products", "--keywords", "castanha,madeira"])

    assert result.exit_code == 0, result.output
    assert "3405" in result.output
    assert "3435" in result.output
    # Suggested .env line should include both codes.
    assert "IBGE_PRODUCT_CODES=3405,3435" in result.output


def test_discover_ibge_products_exits_1_when_no_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.discover, "search_ibge_products", lambda *_a: [])

    result = runner.invoke(cli.app, ["discover", "ibge-products", "--keywords", "nada"])

    assert result.exit_code == 1


def test_discover_bcb_series_prints_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    from embrapa_dashboard.discover import BcbSeriesSample

    monkeypatch.setattr(
        cli.discover,
        "sample_bcb_series",
        lambda code, n: BcbSeriesSample(
            code=code, sample=[{"data": "01/01/2025", "valor": "0.16"}]
        ),
    )

    result = runner.invoke(cli.app, ["discover", "bcb-series", "433", "--last", "1"])

    assert result.exit_code == 0, result.output
    assert "SGS series 433" in result.output
    assert "0.16" in result.output


def test_discover_bcb_series_empty_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    from embrapa_dashboard.discover import BcbSeriesSample

    monkeypatch.setattr(
        cli.discover,
        "sample_bcb_series",
        lambda code, n: BcbSeriesSample(code=code, sample=[]),
    )

    result = runner.invoke(cli.app, ["discover", "bcb-series", "999"])

    assert result.exit_code == 1


def test_discover_bcb_series_rejects_non_positive_last(monkeypatch: pytest.MonkeyPatch) -> None:
    # --last has min=1 (same as the chunk-years options); 0 / negative must be
    # rejected by the CLI as a usage error before any fetch happens.
    called = False

    def _spy(code: str, n: int) -> object:
        nonlocal called
        called = True
        raise AssertionError("sample_bcb_series must not run for an invalid --last")

    monkeypatch.setattr(cli.discover, "sample_bcb_series", _spy)

    result = runner.invoke(cli.app, ["discover", "bcb-series", "433", "--last", "0"])

    assert result.exit_code == 2
    assert called is False


# ─── monitor ─────────────────────────────────────────────────────────────────
def test_monitor_list_flag_shows_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.observability, "list_log_paths", lambda: [])
    monkeypatch.setattr(cli.observability, "log_dir", lambda: Path("/tmp/logs"))

    result = runner.invoke(cli.app, ["monitor", "--list"])

    assert result.exit_code == 0
    assert "No event logs" in result.output


def test_monitor_no_logs_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.observability, "latest_log_path", lambda pipeline: None)
    monkeypatch.setattr(cli.observability, "log_dir", lambda: Path("/tmp/logs"))

    result = runner.invoke(cli.app, ["monitor"])

    assert result.exit_code == 1
    assert "No event logs" in result.output


def test_monitor_dispatches_to_monitor_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log = tmp_path / "ibge-XYZ.jsonl"
    log.write_text('{"event":"pipeline_start"}\n', encoding="utf-8")
    captured: dict = {}

    def fake_run(target, follow, console):  # type: ignore[no-untyped-def]
        captured["target"] = target
        captured["follow"] = follow

    monkeypatch.setattr(cli.monitor, "run", fake_run)

    result = runner.invoke(cli.app, ["monitor", str(log), "--no-follow"])

    assert result.exit_code == 0, result.output
    assert captured["target"] == log
    assert captured["follow"] is False


# ─── doctor ──────────────────────────────────────────────────────────────────
def test_doctor_all_passing_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    from embrapa_dashboard.doctor import CheckResult

    monkeypatch.setattr(
        cli.doctor,
        "run_all",
        lambda: [CheckResult(name="a", ok=True, detail="ok")],
    )

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "All checks passed" in result.output


def test_doctor_failure_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    from embrapa_dashboard.doctor import CheckResult

    monkeypatch.setattr(
        cli.doctor,
        "run_all",
        lambda: [
            CheckResult(name="a", ok=True, detail="ok"),
            CheckResult(name="b", ok=False, detail="broken"),
        ],
    )

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 1
    assert "check(s) failed" in result.output


# ─── backup-gold ─────────────────────────────────────────────────────────────
def test_backup_gold_calls_backup_run_with_settings(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    backup_run = MagicMock(return_value=("2026-05-25T00-00-00Z", ["gs://b/backups/x.parquet"]))
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.backup, "run", backup_run)

    result = runner.invoke(cli.app, ["backup-gold"])

    assert result.exit_code == 0, result.output
    backup_run.assert_called_once_with(settings)
    assert "Gold backup complete" in result.output
    assert "gs://b/backups/x.parquet" in result.output


# ─── dbt passthrough ─────────────────────────────────────────────────────────
def test_dbt_passthrough_invokes_dbt_module(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_run(cmd, cwd, check):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return MagicMock(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    # `--` separator stops typer from trying to parse `--select` as its own option.
    result = runner.invoke(cli.app, ["dbt", "--", "build", "--select", "silver"])

    assert result.exit_code == 0, result.output
    # First two items: <python> -m dbt.cli.main
    assert captured["cmd"][1:3] == ["-m", "dbt.cli.main"]
    # Trailing args forwarded verbatim.
    assert captured["cmd"][-3:] == ["build", "--select", "silver"]
    # CWD must point at the dbt project directory.
    assert captured["cwd"].name == "dbt"


def test_dbt_passthrough_no_args_defaults_to_help(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_run(cmd, cwd, check):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        return MagicMock(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = runner.invoke(cli.app, ["dbt"])

    assert result.exit_code == 0
    assert captured["cmd"][-1] == "--help"


def test_dbt_passthrough_propagates_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: MagicMock(returncode=2))

    result = runner.invoke(cli.app, ["dbt", "compile"])

    assert result.exit_code == 2
