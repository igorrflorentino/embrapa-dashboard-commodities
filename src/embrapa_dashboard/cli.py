"""Embrapa commodities CLI — single entry point for local/manual orchestration."""

from __future__ import annotations

import getpass
import json
import logging
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import ModuleType

import typer
from google.cloud import bigquery
from rich.console import Console
from rich.table import Table

from embrapa_dashboard import (
    backup,
    discover,
    doctor,
    ingestion_heartbeat,
    monitor,
    observability,
    reconcile_check,
)
from embrapa_dashboard.bcb import currency as bcb_currency
from embrapa_dashboard.bcb import inflation as bcb_inflation
from embrapa_dashboard.comex import pipeline as comex_pipeline
from embrapa_dashboard.comtrade import pipeline as comtrade_pipeline
from embrapa_dashboard.comtrade.client import ComtradeQuotaError
from embrapa_dashboard.config import Settings, get_settings
from embrapa_dashboard.core import (
    ChunkOutcome,
    ChunkTracker,
    IngestPartialFailure,
    SourceTransientError,
    chunked_run,
    pipeline_run,
)
from embrapa_dashboard.gcp.clients import resolve_clients
from embrapa_dashboard.ibge import pam_pipeline, ppm_pipeline
from embrapa_dashboard.ibge import pipeline as ibge_pipeline
from embrapa_dashboard.ibge.client import recommended_chunk_years

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console(legacy_windows=False)
app = typer.Typer(no_args_is_help=True, add_completion=False, help="Embrapa commodities pipeline")

ingest_app = typer.Typer(no_args_is_help=True, help="Bronze-layer ingestion commands")
app.add_typer(ingest_app, name="ingest")

discover_app = typer.Typer(
    no_args_is_help=True,
    help="Auxiliary lookups — inspect IBGE / BCB before committing codes to .env",
)
app.add_typer(discover_app, name="discover")

editors_app = typer.Typer(
    no_args_is_help=True,
    help="Manage the per-catalog editor allowlist (Curadoria — research_inputs.catalog_editors)",
)
app.add_typer(editors_app, name="editors")

attribute_editors_app = typer.Typer(
    no_args_is_help=True,
    help="Engenharia de Atributos editor allowlist (research_inputs.attribute_editors)",
)
app.add_typer(attribute_editors_app, name="attribute-editors")


# ─── ingest registry ──────────────────────────────────────────────────────────
# ★ The single extension point for `ingest all`. Each @ingest_app.command()
# stays hand-maintained (observability and heterogeneous messages across sources).
# When adding a source: insert an IngestSpec here + an entry in
# doctor.SOURCE_CHECKS / doctor.BRONZE_TARGETS. See
# docs/adding_a_data_source.md.


@dataclass(frozen=True)
class IngestSpec:
    name: str  # subcommand ('ibge', 'bcb-inflation', ...)
    module: ModuleType  # module with .run(settings, **kwargs) -> str
    accepts_full: bool  # True when .run accepts full=bool (delta-aware pipelines)
    label: str  # label shown in `ingest all`
    in_all: bool = True  # False = only runnable via `ingest <name>` (outside the default batch)


# `module` attribute, not a function: spec.module.run(...) does the lookup at
# call time, keeping monkeypatch.setattr(cli.bcb_inflation, "run", ...)
# working (see tests/test_cli.py).
INGESTS: list[IngestSpec] = [
    IngestSpec("ibge", ibge_pipeline, accepts_full=True, label="IBGE PEVS"),
    # PAM is ANNUAL, slow-changing data (~1yr publication lag): kept OUT of the nightly
    # `ingest all` (in_all=False) so the daily cron stays fast — polling an annual source
    # 365×/year to catch one publication buys nothing. It is NOT unscheduled, though:
    # `embrapa-ingest-all-pam-monthly` (cron `0 4 2 * *`, from `make ingest-job-pam-schedule`)
    # is ENABLED and firing — verified 2026-08-28. Also on demand via `ingest ibge-pam`.
    IngestSpec("ibge-pam", pam_pipeline, accepts_full=True, label="IBGE PAM", in_all=False),
    # PPM (livestock) is the same kind of source as PAM: ANNUAL, slow-changing,
    # freshly-shipped — OUT of the nightly `ingest all` (in_all=False). Runs on
    # demand via `ingest ibge-ppm`; its own monthly cadence via schedule_ppm.sh.
    IngestSpec("ibge-ppm", ppm_pipeline, accepts_full=True, label="IBGE PPM", in_all=False),
    IngestSpec("bcb-inflation", bcb_inflation, accepts_full=True, label="BCB inflation"),
    IngestSpec("bcb-currency", bcb_currency, accepts_full=True, label="BCB FX"),
    IngestSpec("comex", comex_pipeline, accepts_full=True, label="MDIC COMEX"),
    # COMTRADE stays out of `ingest all`: it is key-gated (RuntimeError without a key) and
    # quota-gated/massive (252 reporters × years) — runs only via `ingest comtrade`.
    IngestSpec("comtrade", comtrade_pipeline, accepts_full=True, label="UN COMTRADE", in_all=False),
]


# ─── chunked-command presentation helpers ──────────────────────────────────────
# The CLI is presentation-only: the per-(flow, year)/(year, batch) loop and its
# continue-on-failure now live in each pipeline's run(); these helpers turn the
# ChunkOutcome stream that run() emits into console lines + the failure summary.
# The observability emit pair / chunks_ok-failed bookkeeping lives in
# core.chunked_run (the ChunkTracker yielded below).


def _is_transient_failure(exc: BaseException) -> bool:
    """True when a source-level failure is a known, self-healing upstream
    condition rather than a code bug or data-integrity problem.

    Covers both shapes a source-level ``except Exception`` sees: a direct
    ``SourceTransientError`` (single-chunk sources — IBGE PEVS, BCB inflation/FX
    — propagate their real exception unwrapped), and an ``IngestPartialFailure``
    (chunked sources — COMEX/COMTRADE — aggregate every chunk's outcome; it is
    transient only when every one of its chunks was). Used to decide the
    nightly job's exit code: 0 for "expected, resumes on its own", 1 for
    "needs a human". See ``ChunkOutcome.transient``.
    """
    if isinstance(exc, SourceTransientError):
        return True
    if isinstance(exc, IngestPartialFailure):
        return exc.all_transient
    return False


@contextmanager
def _tracked_run(name: str, *, params: dict | None = None):
    """`pipeline_run`, plus one heartbeat row recording that this ingest RAN.

    Every scheduled ingest goes through here, so a missing heartbeat in the expected
    window means the TRIGGER did not fire — the one thing neither the failure alert nor
    Bronze can tell you, because a delta run with nothing new writes nothing at all.
    The heartbeat never fails the ingest (see ingestion_heartbeat.record).
    """
    started = time.monotonic()
    try:
        with pipeline_run(name, params=params) as ctx:
            yield ctx
    except Exception as exc:
        ingestion_heartbeat.record(
            name, "failed", duration_s=round(time.monotonic() - started, 2), detail=str(exc)
        )
        raise
    else:
        ingestion_heartbeat.record(name, "ok", duration_s=round(time.monotonic() - started, 2))


def _echo_chunk_result(tracker: ChunkTracker, outcome: ChunkOutcome) -> None:
    """Print one finished chunk's result line, mirroring its status."""
    duration = tracker.last_duration_s
    cid = outcome.chunk_id
    if outcome.status == "loaded":
        console.print(f"  [green]✓[/green] {cid} → {outcome.destination} [dim]({duration}s)[/dim]")
    elif outcome.status == "skipped":
        console.print(f"  [dim]·[/dim] {cid} — {outcome.detail} [dim](skipped, {duration}s)[/dim]")
    else:
        tag = "[dim](transient)[/dim]" if outcome.transient else "[bold](unexpected)[/bold]"
        console.print(f"  [red]✗ {cid} failed:[/red] {outcome.detail[:200]} {tag}")


def _make_chunk_handlers(
    tracker: ChunkTracker,
) -> tuple[Callable[[str], None], Callable[[ChunkOutcome], None]]:
    """Build the ``(on_chunk_start, on_chunk)`` callbacks a pipeline ``run`` drives.

    ``on_chunk_start`` emits ``chunk_start`` (via the tracker) and prints the
    ``[i/total] -> chunk_id`` heading; ``on_chunk`` emits ``chunk_end`` /
    ``chunk_error`` (via the tracker) and prints the result line.
    """

    def on_chunk_start(chunk_id: str) -> None:
        i = tracker.start_chunk(chunk_id)
        console.print(f"  [dim][{i}/{tracker.total}][/dim] [bold]-> {chunk_id}[/bold]")

    def on_chunk(outcome: ChunkOutcome) -> None:
        tracker.finish(outcome)
        _echo_chunk_result(tracker, outcome)

    return on_chunk_start, on_chunk


def _summarize_and_exit(
    tracker: ChunkTracker, *, label: str, success_msg: str, retry_hint: str = ""
) -> None:
    """Print the run's closing summary and pick the exit code from what failed.

    Shared tail of every chunked command so the failure listing and exit code
    are identical across sources; ``retry_hint`` carries the source-specific
    "how to re-run" line (empty to omit).

    Exit 0 when every failed chunk was ``transient`` (a marked
    ``SourceTransientError`` that already exhausted its retry budget — expected,
    self-healing on the next scheduled/resumed run): the Cloud Monitoring
    job-failure alert should not page for that. Exit 1 — same as before — when
    at least one failure was NOT transient, since that's a real bug or
    data-integrity problem a human needs to look at.
    """
    if tracker.chunks_failed:
        all_transient = tracker.all_failures_transient
        severity = "yellow" if all_transient else "red"
        qualifier = "(all transient — expected)" if all_transient else "(NOT all transient)"
        console.print(
            f"\n[{severity} bold]⚠ {len(tracker.chunks_failed)} {label} chunk(s) failed "
            f"{qualifier}; {len(tracker.chunks_ok)} succeeded[/{severity} bold]"
        )
        for chunk_id, err in tracker.chunks_failed:
            tag = (
                "[dim](transient)[/dim]"
                if chunk_id in tracker.chunks_failed_transient
                else "[bold](unexpected — investigate)[/bold]"
            )
            console.print(f"  [red]✗[/red] {chunk_id} — {err} {tag}")
        if retry_hint:
            console.print(retry_hint)
        if all_transient:
            console.print(
                "[dim]Every failure was a known transient upstream condition — "
                "no code bug detected, so exiting 0 (un-archived chunks resume on "
                "the next run).[/dim]"
            )
            raise typer.Exit(code=0)
        raise typer.Exit(code=1)
    console.print(success_msg)


@contextmanager
def _transient_aware_exit(label: str) -> Iterator[None]:
    """Single-shot twin of ``_summarize_and_exit``'s exit-code rule.

    The chunked commands (``ibge-batch``/``comex``/``comtrade``) and the
    multi-source ones (``all``/``reconcile``) already exit 0 when every failure
    was a known transient upstream condition. The single-shot commands had no
    such handling: the exception propagated raw, typer exited 1, and the Cloud
    Monitoring policy — which watches the JOB's ``result="failed"``, not the
    command's args — fired the same red "unexpected failure" page it fires for a
    real bug.

    That mattered in production: ``ibge-pam`` and ``ibge-ppm`` each have their own
    ENABLED monthly Cloud Scheduler trigger against that job, and both drive the
    same SIDRA client that raises ``SidraTransientError``. Wrap the pipeline call
    so a transient failure is reported clearly and exits 0 (the next scheduled run
    picks it up), while anything else propagates untouched — still exit 1, still a
    page, still a traceback.

    Enter this OUTSIDE ``pipeline_run`` so the run's event log still records the
    failure before the exit code is downgraded.
    """
    try:
        yield
    except Exception as exc:
        if not _is_transient_failure(exc):
            raise
        console.print(
            f"\n[yellow bold]⚠ {label} failed on a known transient upstream "
            f"condition (all transient — expected)[/yellow bold]"
        )
        console.print(f"  [red]✗[/red] {str(exc)[:200]} [dim](transient)[/dim]")
        console.print(
            "[dim]No code bug detected — exiting 0; the next scheduled run "
            "re-fetches this window (Bronze is append-only, ingestion is delta).[/dim]"
        )
        raise typer.Exit(code=0) from None


# ─── ingest ───────────────────────────────────────────────────────────────────
@ingest_app.command("ibge")
def ingest_ibge(
    full: bool = typer.Option(
        False,
        "--full",
        help="Re-fetch the whole IBGE_START_YEAR→END window (default is delta: recent years only).",
    ),
    from_raw: bool = typer.Option(
        False,
        "--from-raw",
        help="Rebuild Bronze from the archived raw SIDRA response(s), without re-querying SIDRA.",
    ),
) -> None:
    """Ingest IBGE PEVS into the configured Bronze table (extract→raw→bronze)."""
    settings = get_settings()
    with (
        _transient_aware_exit("IBGE PEVS"),
        _tracked_run(
            "ibge",
            params={
                "start_year": settings.ibge_start_year,
                "end_year": settings.ibge_end_year,
                "products": settings.product_codes,
                "full": full,
                "from_raw": from_raw,
            },
        ) as (_run_id, log_path),
    ):
        console.print(f"[dim]event log:[/dim] {log_path}")
        destination = ibge_pipeline.run(settings, full=full, from_raw=from_raw)
    if destination:
        console.print(f"[green]✓[/green] IBGE bronze loaded → {destination}")
    else:
        console.print(
            "[yellow]⚠ IBGE ingest skipped:[/yellow] SIDRA returned no new rows. "
            "On a delta run Bronze is likely already current; on --full, lower "
            "IBGE_END_YEAR in .env to the latest published year."
        )


@ingest_app.command("ibge-pam")
def ingest_ibge_pam(
    full: bool = typer.Option(
        False,
        "--full",
        help="Re-fetch the whole PAM_START_YEAR→END window (default is delta: recent years only).",
    ),
    from_raw: bool = typer.Option(
        False,
        "--from-raw",
        help="Rebuild Bronze from the archived raw SIDRA response(s), without re-querying SIDRA.",
    ),
) -> None:
    """Ingest IBGE PAM (Produção Agrícola Municipal) into Bronze (extract→raw→bronze)."""
    settings = get_settings()
    with (
        _transient_aware_exit("IBGE PAM"),
        _tracked_run(
            "ibge-pam",
            params={
                "start_year": settings.pam_start_year,
                "end_year": settings.pam_end_year,
                "products": settings.pam_product_codes_list,
                "full": full,
                "from_raw": from_raw,
            },
        ) as (_run_id, log_path),
    ):
        console.print(f"[dim]event log:[/dim] {log_path}")
        destination = pam_pipeline.run(settings, full=full, from_raw=from_raw)
    if destination:
        console.print(f"[green]✓[/green] IBGE PAM bronze loaded → {destination}")
    else:
        console.print(
            "[yellow]⚠ IBGE PAM ingest skipped:[/yellow] SIDRA returned no new rows. "
            "On a delta run Bronze is likely already current; on --full, lower "
            "PAM_END_YEAR in .env to the latest published year."
        )


@ingest_app.command("ibge-ppm")
def ingest_ibge_ppm(
    full: bool = typer.Option(
        False,
        "--full",
        help="Re-fetch the whole PPM_START_YEAR→END window (default is delta: recent years only).",
    ),
    from_raw: bool = typer.Option(
        False,
        "--from-raw",
        help="Rebuild Bronze from the archived raw SIDRA response(s), without re-querying SIDRA.",
    ),
) -> None:
    """Ingest IBGE PPM (Pesquisa da Pecuária Municipal) into Bronze (extract→raw→bronze).

    Ingests BOTH SIDRA tables: 3939 (efetivo dos rebanhos) + 74 (produção de origem animal).
    """
    settings = get_settings()
    with (
        _transient_aware_exit("IBGE PPM"),
        _tracked_run(
            "ibge-ppm",
            params={
                "start_year": settings.ppm_start_year,
                "end_year": settings.ppm_end_year,
                "herd_products": settings.ppm_herd_product_codes_list,
                "animal_products": settings.ppm_animal_product_codes_list,
                "full": full,
                "from_raw": from_raw,
            },
        ) as (_run_id, log_path),
    ):
        console.print(f"[dim]event log:[/dim] {log_path}")
        destination = ppm_pipeline.run(settings, full=full, from_raw=from_raw)
    if destination:
        console.print(f"[green]✓[/green] IBGE PPM bronze loaded → {destination}")
    else:
        console.print(
            "[yellow]⚠ IBGE PPM ingest skipped:[/yellow] SIDRA returned no new rows. "
            "On a delta run Bronze is likely already current; on --full, lower "
            "PPM_END_YEAR in .env to the latest published year."
        )


@ingest_app.command("bcb-inflation")
def ingest_bcb_inflation(
    full: bool = typer.Option(
        False,
        "--full",
        help="Force a full refetch from BCB_START_YEAR. Default is delta-from-last-load.",
    ),
    from_raw: bool = typer.Option(
        False,
        "--from-raw",
        help="Rebuild Bronze from the archived raw SGS trail, without re-fetching the API.",
    ),
) -> None:
    """Ingest configured BCB SGS inflation series (extract→raw→bronze)."""
    settings = get_settings()
    with (
        _transient_aware_exit("BCB inflation"),
        _tracked_run("bcb-inflation", params={"full": full, "from_raw": from_raw}) as (
            _run_id,
            log_path,
        ),
    ):
        console.print(f"[dim]event log:[/dim] {log_path}")
        destination = bcb_inflation.run(settings, full=full, from_raw=from_raw)
    if destination:
        console.print(f"[green]✓[/green] BCB inflation bronze loaded → {destination}")
    else:
        console.print("[dim]BCB inflation: nothing new since last ingest.[/dim]")


@ingest_app.command("bcb-currency")
def ingest_bcb_currency(
    full: bool = typer.Option(
        False,
        "--full",
        help="Force a full refetch from BCB_START_YEAR. Default is delta-from-last-load.",
    ),
    from_raw: bool = typer.Option(
        False,
        "--from-raw",
        help="Rebuild Bronze from the archived raw SGS trail, without re-fetching the API.",
    ),
) -> None:
    """Ingest configured BCB SGS FX series (extract→raw→bronze)."""
    settings = get_settings()
    with (
        _transient_aware_exit("BCB FX"),
        _tracked_run("bcb-currency", params={"full": full, "from_raw": from_raw}) as (
            _run_id,
            log_path,
        ),
    ):
        console.print(f"[dim]event log:[/dim] {log_path}")
        destination = bcb_currency.run(settings, full=full, from_raw=from_raw)
    if destination:
        console.print(f"[green]✓[/green] BCB currency bronze loaded → {destination}")
    else:
        console.print("[dim]BCB currency: nothing new since last ingest.[/dim]")


def _ibge_batch_ingest(settings: Settings, chunk_years: int | None) -> ChunkTracker:
    """Ingest the full IBGE window in year chunks (each a ``full=True`` load).

    Shared by ``ingest ibge-batch`` and ``ingest reconcile``. It owns the
    chunked loop + continue-on-failure and returns the populated ChunkTracker
    so each caller decides how to summarize/exit: ``ibge-batch`` exits non-zero
    on any failed chunk, whereas ``reconcile`` records the failure and moves on
    to the BCB/COMEX legs. Chunking (vs the single-shot ``ibge --full``) is what
    keeps the huge 1986→today SIDRA pull under the unattended slow-byte deadline.
    """
    if settings.ibge_start_year is None:
        raise typer.BadParameter("Set IBGE_START_YEAR in .env before running batch ingest.")

    n_products = len(settings.product_codes)
    if chunk_years is None:
        chunk_years = recommended_chunk_years(n_products)
        chunk_source = f"auto (for {n_products} product(s))"
    else:
        chunk_source = "manual override"

    # Snapshot originals before the loop — we mutate settings each iteration.
    range_start = settings.ibge_start_year
    range_end = settings.ibge_end_year

    # An inverted window yields zero chunks — the loop below would silently report
    # "All 0 batches complete" and exit 0 (and the reconcile leg would report the
    # IBGE PEVS leg green having re-ingested nothing). Fail loudly instead.
    if range_start > range_end:
        raise typer.BadParameter(
            f"IBGE_START_YEAR ({range_start}) is after IBGE_END_YEAR ({range_end}) — "
            "empty window, nothing to ingest."
        )

    chunks = list(range(range_start, range_end + 1, chunk_years))
    total = len(chunks)
    console.print(
        f"[bold]IBGE batch ingest:[/bold] {range_start}-{range_end} "
        f"in {total} chunk(s) of {chunk_years} year(s) [dim]({chunk_source})[/dim]"
    )

    # Build clients once; reuse across all chunks to avoid repeated auth.
    bq_client, storage_client = resolve_clients(settings)

    # ibge-batch drives its own per-chunk loop (each chunk is a year-range that
    # calls ibge_pipeline.run with full=True); chunked_run owns the event
    # scaffold + ok/failed bookkeeping, matching comex/comtrade.
    params = {
        "start_year": range_start,
        "end_year": range_end,
        "chunk_years": chunk_years,
        "products": settings.product_codes,
    }
    with chunked_run("ibge-batch", total=total, params=params) as tracker:
        console.print(f"[dim]event log:[/dim] {tracker.log_path}")
        console.print(
            "[dim]tip:[/dim] run [bold]uv run embrapa monitor[/bold] in another terminal "
            "to watch progress live"
        )
        for chunk_start in chunks:
            chunk_end = min(chunk_start + chunk_years - 1, range_end)
            chunk_id = f"{chunk_start}-{chunk_end}"
            chunk_settings = settings.model_copy(
                update={"ibge_start_year": chunk_start, "ibge_end_year": chunk_end}
            )
            i = tracker.start_chunk(chunk_id)
            console.print(f"  [dim][{i}/{total}][/dim] [bold]-> {chunk_id}[/bold]")
            try:
                destination = ibge_pipeline.run(
                    chunk_settings,
                    full=True,
                    storage_client=storage_client,
                    bq_client=bq_client,
                )
            except Exception as exc:
                # Continue-on-failure: a single hung chunk must not strand the
                # rest; the chunk_error event + summary point at the year ranges
                # that need a re-run. Mark a SourceTransientError as transient, exactly
                # like the comex/comtrade chunk runners do — a SIDRA connection drop on a
                # large window is THE transient failure this command exists to survive, so
                # without this the run would page a human for a condition that self-heals.
                outcome = ChunkOutcome(
                    chunk_id,
                    "failed",
                    detail=str(exc),
                    transient=isinstance(exc, SourceTransientError),
                )
            else:
                outcome = (
                    ChunkOutcome(chunk_id, "loaded", destination=destination)
                    if destination
                    else ChunkOutcome(chunk_id, "skipped", detail="SIDRA returned no rows")
                )
            tracker.finish(outcome)
            _echo_chunk_result(tracker, outcome)

    return tracker


@ingest_app.command("ibge-batch")
def ingest_ibge_batch(
    chunk_years: int | None = typer.Option(
        None,
        "--chunk-years",
        "-c",
        help=(
            "Years per batch. If omitted, auto-computed from the number of "
            "products in IBGE_PRODUCT_CODES so every state response stays "
            "under SIDRA's cell limit with a safety margin."
        ),
        min=1,  # 0 → empty range (silent no-op); negative → ValueError. Reject both.
    ),
) -> None:
    """Ingest IBGE PEVS in year-chunked batches to avoid IBGE connection drops.

    For historical windows (>10 years), the IBGE API occasionally closes
    large connections mid-transfer. This command splits the full window
    defined by IBGE_START_YEAR / IBGE_END_YEAR into chunks and runs them
    sequentially, each as a separate Bronze load (WRITE_APPEND).

    Chunk size auto-scales with the number of products: more products means
    smaller chunks (since SIDRA's cell limit is fixed per request).
    """
    settings = get_settings()
    tracker = _ibge_batch_ingest(settings, chunk_years)
    _summarize_and_exit(
        tracker,
        label="IBGE",
        success_msg=f"\n[green bold]✓ All {tracker.total} batches complete[/green bold]",
        retry_hint=(
            "\n[dim]Re-run failed chunks individually with:[/dim]\n"
            "  IBGE_START_YEAR=<start> IBGE_END_YEAR=<end> uv run embrapa ingest ibge"
        ),
    )


@ingest_app.command("comex")
def ingest_comex(
    full: bool = typer.Option(
        False,
        "--full",
        help="Force re-download of every (flow, year) file, ignoring the ETag "
        "freshness check. Default re-downloads only files the source changed.",
    ),
    from_raw: bool = typer.Option(
        False,
        "--from-raw",
        help="Skip the download phase entirely and rebuild Bronze from the raw "
        "Parquet already in GCS — re-filter / apply new products without internet.",
    ),
) -> None:
    """Ingest MDIC Comex Stat flows (export + import) via the two-phase raw zone.

    Per (flow, year): Phase 1 archives the verbatim CSV→Parquet to the GCS raw
    zone (only when the source ETag changed), Phase 2 filters it to the
    configured NCMs and loads Bronze. Emits a chunk per (flow, year) for live
    `embrapa monitor` progress.
    """
    settings = get_settings()
    bq_client, storage_client = resolve_clients(settings)
    total = len(comex_pipeline.all_chunks(settings))
    mode = "from-raw" if from_raw else ("full" if full else "delta")
    params = {"full": full, "from_raw": from_raw, "flows": settings.comex_flows_list}

    # The (flow, year) loop + continue-on-failure live in comex_pipeline.run; the
    # CLI only presents it. chunked_run owns the event scaffold; run() drives the
    # tracker via the start/finish callbacks.
    with chunked_run("comex", total=total, params=params) as tracker:
        console.print(f"[dim]event log:[/dim] {tracker.log_path}")
        console.print(f"[bold]COMEX ingest:[/bold] {total} chunk(s) [dim]({mode})[/dim]")
        on_chunk_start, on_chunk = _make_chunk_handlers(tracker)
        comex_pipeline.run(
            settings,
            full=full,
            from_raw=from_raw,
            storage_client=storage_client,
            bq_client=bq_client,
            on_chunk_start=on_chunk_start,
            on_chunk=on_chunk,
        )

    _summarize_and_exit(
        tracker,
        label="COMEX",
        success_msg=f"\n[green bold]✓ All {total} COMEX chunk(s) complete[/green bold]",
    )


@ingest_app.command("comtrade")
def ingest_comtrade(
    full: bool = typer.Option(
        False, "--full", help="Re-fetch every (year, reporter-batch) chunk, ignoring resume."
    ),
    from_raw: bool = typer.Option(
        False,
        "--from-raw",
        help="Rebuild Bronze from the archived raw chunks, without calling the API.",
    ),
) -> None:
    """Ingest UN Comtrade global flows into Bronze, chunked by (year, reporter-batch).

    Resumable: a re-run fetches only chunks not yet archived (+ the latest year).
    If the daily API quota runs out mid-run, stop and re-run later — no lost work.
    """
    settings = get_settings()
    if not settings.comtrade_api_key:
        console.print(
            "[red]COMTRADE_API_KEY is empty.[/red] Set it in .env "
            "(free key from comtradedeveloper.un.org)."
        )
        raise typer.Exit(code=1)
    bq_client, storage_client = resolve_clients(settings)
    # Resolve reporters once (here, for the header count) — run() resolves them
    # again from the same resolve_reporters(), so the two never drift.
    reporters = comtrade_pipeline.resolve_reporters(settings)
    total = len(comtrade_pipeline.plan_chunks(settings, reporters))
    mode = "from-raw" if from_raw else ("full" if full else "resume")

    # The (year, reporter-batch) loop, continue-on-failure, and stop-on-quota all
    # live in comtrade_pipeline.run; the CLI presents the ChunkOutcome stream.
    quota_hit = False
    with chunked_run("comtrade", total=total) as tracker:
        console.print(f"[dim]event log:[/dim] {tracker.log_path}")
        console.print(
            f"[bold]COMTRADE ingest:[/bold] {total} chunk(s) "
            f"[dim]({mode}, {len(reporters)} reporters)[/dim]"
        )
        on_chunk_start, on_chunk = _make_chunk_handlers(tracker)
        try:
            comtrade_pipeline.run(
                settings,
                full=full,
                from_raw=from_raw,
                storage_client=storage_client,
                bq_client=bq_client,
                on_chunk_start=on_chunk_start,
                on_chunk=on_chunk,
            )
        except ComtradeQuotaError as exc:
            # Daily quota exhausted mid-run — stop cleanly; re-running resumes
            # from the un-archived chunks. (pipeline_end still emits on __exit__.)
            quota_hit = True
            console.print(
                f"\n[yellow bold]⚠ COMTRADE quota exhausted[/yellow bold] [dim]({exc})[/dim]\n"
                "[dim]Re-run to resume — archived chunks are skipped.[/dim]"
            )

    if quota_hit:
        # Daily quota exhaustion is EXPECTED and self-healing: the next scheduled run
        # resumes from the un-archived chunks (no data lost), so it is NOT a job
        # failure. Exit 0 so the Cloud Monitoring job-failure alert stops paging on
        # every backfill day — UNLESS a genuine (non-transient) chunk also failed,
        # which must still alert.
        if tracker.chunks_failed:
            for chunk_id, err in tracker.chunks_failed:
                tag = (
                    "[dim](transient)[/dim]"
                    if chunk_id in tracker.chunks_failed_transient
                    else "[bold](unexpected — investigate)[/bold]"
                )
                console.print(f"  [red]✗[/red] {chunk_id} — {err} {tag}")
            if tracker.all_failures_transient:
                console.print(
                    "[dim]Every failed chunk was itself transient (alongside the quota "
                    "exhaustion) — no code bug detected, exiting 0.[/dim]"
                )
                raise typer.Exit(code=0)
            raise typer.Exit(code=1)
        console.print(
            f"[dim]Quota-limited run: {len(tracker.chunks_ok)} chunk(s) archived; "
            "resume on the next scheduled run.[/dim]"
        )
        raise typer.Exit(code=0)
    _summarize_and_exit(
        tracker,
        label="COMTRADE",
        success_msg=f"\n[green bold]✓ All {total} COMTRADE chunk(s) complete[/green bold]",
        retry_hint="[dim](quota? rate limit? re-run to resume — archived chunks are skipped)[/dim]",
    )


@ingest_app.command("all")
def ingest_all(
    full: bool = typer.Option(
        False,
        "--full",
        help="Force full refetch on delta-aware pipelines (whole windows, not just the delta).",
    ),
) -> None:
    """Run every registered Bronze pipeline sequentially in INGESTS order.

    Continue-on-failure at the *source* level, mirroring the per-chunk policy
    inside each pipeline: a source that raises (a hard error, or an aggregated
    ``IngestPartialFailure`` from its own chunk loop) is recorded and the next
    source still runs. The blind nightly cron thus never aborts the whole batch
    on one source's transient trouble.

    Exit code reflects WHAT failed, not just THAT something failed: if every
    failure was a marked ``SourceTransientError`` (an upstream API hiccup that
    already exhausted its retry budget — expected, and self-healing on the next
    scheduled delta run), exit 0 so the Cloud Monitoring job-failure alert
    doesn't page for a condition that needs no human action. Exit 1 — a real
    alert — only when at least one failure was NOT transient (a code bug,
    permission/schema error, or other unexpected condition).
    """
    settings = get_settings()
    failures: list[tuple[str, str, bool]] = []
    for spec in INGESTS:
        if not spec.in_all:
            continue
        console.print(f"[bold]→ {spec.label}[/bold]")
        kwargs = {"full": full} if spec.accepts_full else {}
        # Wrap each pipeline in the same observability lifecycle the individual
        # `ingest <source>` commands use, so `ingest all` shows up in
        # `embrapa monitor` and a mid-batch failure leaves a chunk_error in the
        # event log instead of running completely silent.
        try:
            with _tracked_run(spec.name, params=kwargs) as (_run_id, log_path):
                console.print(f"[dim]event log:[/dim] {log_path}")
                spec.module.run(settings, **kwargs)
        except Exception as exc:
            transient = _is_transient_failure(exc)
            failures.append((spec.label, str(exc)[:200], transient))
            tag = "transient — expected" if transient else "unexpected — investigate"
            console.print(f"[red]✗ {spec.label} failed:[/red] {str(exc)[:200]} [dim]({tag})[/dim]")

    if failures:
        all_transient = all(transient for _, _, transient in failures)
        severity = "yellow" if all_transient else "red"
        qualifier = "(all transient — expected)" if all_transient else "(NOT all transient)"
        console.print(
            f"\n[{severity} bold]⚠ {len(failures)} source(s) failed {qualifier}[/{severity} bold]"
        )
        for label, err, transient in failures:
            tag = "[dim](transient)[/dim]" if transient else "[bold](unexpected)[/bold]"
            console.print(f"  [red]✗[/red] {label} — {err} {tag}")
        if all_transient:
            console.print(
                "[dim]Every failed source hit a known transient upstream condition — "
                "no code bug detected, so exiting 0 (self-healing on the next scheduled "
                "delta run).[/dim]"
            )
            raise typer.Exit(code=0)
        raise typer.Exit(code=1)
    console.print("[green bold]✓ All Bronze pipelines completed[/green bold]")


@ingest_app.command("reconcile")
def ingest_reconcile(
    chunk_years: int | None = typer.Option(
        None,
        "--chunk-years",
        "-c",
        help="IBGE years per batch (see `ingest ibge-batch`). Omit to auto-size to the cell limit.",
        min=1,  # reject 0 (silent no-op) / negative (ValueError) — same as ibge-batch.
    ),
) -> None:
    """Full re-download of every delta/ETag source — the deliberate escape hatch.

    Unlike the nightly delta (which only revisits a recent window), reconcile
    IGNORES each source's delta/ETag short-circuit and re-fetches the WHOLE
    configured history. That is what catches an upstream CORRECTION to an old
    year — e.g. IBGE revising a 1999 PEVS value — which the delta would never
    re-query, and it also force-unsticks a source frozen for any reason.

    Per source: IBGE PEVS runs year-CHUNKED (like `ibge-batch`, so the huge
    1986→today SIDRA pull survives an unattended slow-byte deadline); BCB
    inflation/FX, COMEX, and the out-of-`all` annual SIDRA sources PAM/PPM run with
    `--full` (single-shot, deadline-resilient since the #148 dynamic SIDRA timeout),
    so an old-year revision to PAM/PPM is caught too. COMTRADE is excluded
    (key-gated), exactly like `ingest all`. Continue-on-failure at the source level.

    Bronze only — run `dbt build` afterward to propagate the refreshed Bronze to
    Silver/Gold (`make reconcile` chains both). The incremental Silver is
    year-agnostic (it re-scans whatever Bronze years got a newer
    ingestion_timestamp, of any age), so a plain `dbt build` carries an old-year
    revision all the way to Gold — no `--full-refresh` needed.
    """
    settings = get_settings()
    failures: list[tuple[str, str, bool]] = []

    failures.extend(_reconcile_ibge(settings, chunk_years))
    failures.extend(_reconcile_full_sources(settings))

    if failures:
        _report_source_failures(failures)
        if all(transient for _, _, transient in failures):
            console.print(
                "[dim]Every failed source hit a known transient upstream condition — "
                "no code bug detected, so exiting 0.[/dim]"
            )
            raise typer.Exit(code=0)
        raise typer.Exit(code=1)
    console.print("[green bold]✓ Reconcile complete — every source fully re-ingested[/green bold]")
    console.print(
        "[dim]Next:[/dim] run [bold]dbt build[/bold] to propagate any revisions to Silver/Gold "
        "[dim](`make reconcile` chains it for you)[/dim]."
    )


def _reconcile_ibge(settings: Settings, chunk_years: int | None) -> list[tuple[str, str, bool]]:
    """IBGE phase of reconcile: chunked full window (not the single-shot
    ``ibge --full``) so the huge 1986→today SIDRA pull survives the unattended
    slow-byte deadline. A BadParameter (IBGE_START_YEAR unset) is a real
    misconfig — let it abort. Returns the source-level failures it collected."""
    console.print("[bold]→ IBGE PEVS[/bold] [dim](chunked full window)[/dim]")
    try:
        tracker = _ibge_batch_ingest(settings, chunk_years)
    except typer.BadParameter:
        raise
    except Exception as exc:
        console.print(f"[red]✗ IBGE PEVS failed:[/red] {str(exc)[:200]}")
        return [("IBGE PEVS", str(exc)[:200], _is_transient_failure(exc))]
    if tracker.chunks_failed:
        return [
            (
                "IBGE PEVS",
                f"{len(tracker.chunks_failed)} chunk(s) failed",
                tracker.all_failures_transient,
            )
        ]
    return []


def _reconcile_full_sources(settings: Settings) -> list[tuple[str, str, bool]]:
    """Full phase for every non-PEVS, non-COMTRADE source: ``--full`` re-fetches
    each one's whole configured window. Covers BCB inflation/FX, COMEX **and** the
    out-of-``all`` annual SIDRA sources PAM/PPM — so reconcile catches an old-year
    revision to them (their nightly-absent + monthly-delta paths never would).
    Skips IBGE PEVS (already done, chunked) and COMTRADE (key-gated). Gate on
    accepts_full so a future non-delta source wouldn't trip on an unexpected full=
    kwarg. NOTE: a full PPM pull is heavier (1974→ both SIDRA tables); on a
    memory-constrained reconcile Job, bump the Job memory as for the PPM backfill."""
    failures: list[tuple[str, str, bool]] = []
    for spec in INGESTS:
        # Reconcile re-fetches every delta/ETag source FULLY — including the
        # out-of-`all` annual SIDRA sources PAM/PPM, so an upstream CORRECTION to an
        # old PAM/PPM year is caught too (the nightly delta + their monthly
        # schedulers never re-query it). Skip only `ibge` (already done year-chunked
        # above) and `comtrade` (key-gated, excluded exactly like `ingest all`).
        if spec.name in {"ibge", "comtrade"}:
            continue
        kwargs = {"full": True} if spec.accepts_full else {}
        console.print(f"[bold]→ {spec.label}[/bold] [dim](full)[/dim]")
        try:
            with _tracked_run(spec.name, params=kwargs) as (_run_id, log_path):
                console.print(f"[dim]event log:[/dim] {log_path}")
                spec.module.run(settings, **kwargs)
        except Exception as exc:
            transient = _is_transient_failure(exc)
            failures.append((spec.label, str(exc)[:200], transient))
            tag = "transient — expected" if transient else "unexpected — investigate"
            console.print(f"[red]✗ {spec.label} failed:[/red] {str(exc)[:200]} [dim]({tag})[/dim]")
    return failures


def _report_source_failures(failures: list[tuple[str, str, bool]]) -> None:
    """Print the aggregated source-level failure summary (shared by the batch
    commands). The caller decides the exit code from each entry's transient flag."""
    all_transient = all(transient for _, _, transient in failures)
    severity = "yellow" if all_transient else "red"
    qualifier = "(all transient — expected)" if all_transient else "(NOT all transient)"
    console.print(
        f"\n[{severity} bold]⚠ {len(failures)} source(s) failed {qualifier}[/{severity} bold]"
    )
    for label, err, transient in failures:
        tag = "[dim](transient)[/dim]" if transient else "[bold](unexpected)[/bold]"
        console.print(f"  [red]✗[/red] {label} — {err} {tag}")


# ─── discover ─────────────────────────────────────────────────────────────────
@discover_app.command("ibge-products")
def discover_ibge_products(
    keywords: str = typer.Option(..., "--keywords", "-k", help="Comma-separated keywords"),
    table_id: str = typer.Option("289", "--table-id", "-t"),
) -> None:
    """Search SIDRA classifications for products matching free-text keywords."""
    needles = [k.strip() for k in keywords.split(",") if k.strip()]
    matches = discover.search_ibge_products(table_id, needles)
    if not matches:
        console.print(f"[yellow]No products in table {table_id} matched {needles}[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title=f"IBGE table {table_id} — products matching {needles}")
    table.add_column("Classification", style="dim")
    table.add_column("Code", style="cyan")
    table.add_column("Name")
    for m in matches:
        table.add_row(m.classification_id, m.code, m.name)
    console.print(table)
    console.print(
        f"\n[dim]Suggested .env value:[/dim] IBGE_PRODUCT_CODES={','.join(m.code for m in matches)}"
    )


@discover_app.command("ibge-periods")
def discover_ibge_periods(
    table_id: str = typer.Option("289", "--table-id", "-t"),
) -> None:
    """List every year for which the SIDRA table has data."""
    years = discover.list_ibge_periods(table_id)
    if not years:
        console.print(f"[yellow]Table {table_id} returned no periods.[/yellow]")
        raise typer.Exit(code=1)
    console.print(f"[bold]Table {table_id}[/bold] — {len(years)} years available")
    console.print(f"  First: [green]{years[0]}[/green]   Last: [green]{years[-1]}[/green]")
    console.print(
        f"[dim]Suggested .env:[/dim] IBGE_START_YEAR={years[0]} IBGE_END_YEAR={years[-1]}"
    )


@discover_app.command("bcb-series")
def discover_bcb_series(
    code: str = typer.Argument(..., help="SGS series code (e.g. 433)"),
    n: int = typer.Option(
        5,
        "--last",
        "-n",
        help="Number of latest observations to fetch",
        min=1,  # reject 0 / negative — same min constraint as chunk-years.
    ),
) -> None:
    """Validate an SGS code by printing the most recent N observations."""
    sample = discover.sample_bcb_series(code, n=n)
    if not sample.sample:
        console.print(f"[yellow]Series {code} returned no data.[/yellow]")
        raise typer.Exit(code=1)
    console.print(f"[bold]SGS series {code}[/bold] — last {len(sample.sample)} observations")
    console.print(json.dumps(sample.sample, indent=2, ensure_ascii=False))


# ─── monitor ──────────────────────────────────────────────────────────────────
@app.command("monitor")
def monitor_cmd(
    log_path: Path | None = typer.Argument(  # noqa: B008
        None,
        help="Path to a JSONL event log. Defaults to the most recent one.",
    ),
    pipeline: str | None = typer.Option(
        None,
        "--pipeline",
        "-p",
        help="Filter latest-log lookup to a pipeline name (e.g. 'ibge', 'ibge-batch').",
    ),
    no_follow: bool = typer.Option(
        False, "--no-follow", help="Render once over a finished log and exit."
    ),
    list_logs: bool = typer.Option(
        False, "--list", help="List available run logs sorted newest first, then exit."
    ),
) -> None:
    """Live progress dashboard for an ongoing or finished ingest run.

    Examples:
        embrapa monitor                              # tail latest run
        embrapa monitor --pipeline ibge-batch        # tail latest batch run
        embrapa monitor ~/.embrapa/logs/ibge-XXX.jsonl
        embrapa monitor --list                       # show available runs
    """
    if list_logs:
        paths = observability.list_log_paths()
        if not paths:
            console.print(f"[dim]No event logs in {observability.log_dir()}[/dim]")
            return
        table = Table(title="Run logs (newest first)")
        table.add_column("Modified", style="dim")
        table.add_column("Size", justify="right", style="dim")
        table.add_column("Path")
        for p in paths[:30]:
            stat = p.stat()
            mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
            size_kb = f"{stat.st_size / 1024:.1f} KB"
            table.add_row(mtime, size_kb, str(p))
        console.print(table)
        return

    target = log_path or observability.latest_log_path(pipeline)
    if target is None:
        console.print(
            f"[yellow]No event logs found in {observability.log_dir()}.[/yellow]\n"
            "[dim]Run an ingest first, or pass a path explicitly.[/dim]"
        )
        raise typer.Exit(code=1)
    console.print(f"[dim]Watching:[/dim] {target}")
    monitor.run(target, follow=not no_follow, console=console)


# ─── doctor ───────────────────────────────────────────────────────────────────
@app.command("doctor")
def doctor_cmd() -> None:
    """Quick health-check before running an ingest. ~10 seconds.

    Validates: .env parsing (incl. the PAM/COMEX/COMTRADE mappings), the Gold
    inflation pivot codes, the currency-series and PAM-variable code drift,
    ADC credentials, BigQuery / GCS reachability, source connectivity (IBGE
    SIDRA, IBGE PAM, IBGE PPM, BCB SGS, COMEX, COMTRADE), whether Bronze tables
    and serving marts exist yet, and Gold-backup freshness.

    Exits 1 if any check fails. Bronze-tables and serving-marts checks are
    informational (never fail); Gold-backup freshness FAILS when no complete
    snapshot exists — run `make dbt-build-prod-with-backup` once — and only
    warns when the latest snapshot is older than BACKUP_STALENESS_DAYS.
    """
    results = doctor.run_all()
    table = Table(title="embrapa doctor", show_lines=False)
    table.add_column("", width=3)
    table.add_column("Check", style="bold")
    table.add_column("Detail")
    failed = 0
    for r in results:
        mark = "[green]✓[/green]" if r.ok else "[red]✗[/red]"
        if not r.ok:
            failed += 1
        table.add_row(mark, r.name, r.detail)
    console.print(table)
    if failed:
        console.print(f"[red bold]{failed} check(s) failed[/red bold]")
        raise typer.Exit(code=1)
    console.print("[green bold]All checks passed[/green bold]")


# ─── backup ───────────────────────────────────────────────────────────────────
@app.command("backup-gold")
def backup_gold() -> None:
    """Snapshot prod Gold tables to GCS as Parquet (manual cold-storage).

    Lands at ``gs://${GCS_BUCKET}/backups/run=<ts>/<table>/<table>-*.parquet``.
    GCS lifecycle (versioning + Nearline/Coldline/Archive transitions) handles
    long-term retention without extra config.

    Run after a successful ``make dbt-build-prod`` you want to preserve.
    """
    settings = get_settings()
    run_id, uris = backup.run(settings)
    console.print(f"[green]✓[/green] Gold backup complete  [dim]run_id={run_id}[/dim]")
    for uri in uris:
        console.print(f"  → {uri}")


@app.command("reconcile-check")
def reconcile_check_cmd(
    years: str = typer.Option(
        "2015,2019,2022", help="Comma-separated OLD years to sample for IBGE PEVS"
    ),
    uf: str = typer.Option("15", help="2-digit UF code for the IBGE sample (default: Pará)"),
    cutoff: str = typer.Option(
        "", help="ISO date; BCB points older than this are checked (default: Jan 1 last year)"
    ),
) -> None:
    """Answer the monthly "do we need a `reconcile`?" question with evidence.

    IBGE/BCB ingestion is DELTA, so a correction the source publishes to an OLD year is
    never re-queried by the nightly run. This compares what the sources serve TODAY
    against what Bronze holds, for data old enough that the delta window never touches it.

    Reads only — it never writes, ingests or fixes anything. A non-zero divergence count
    is the cue to run `embrapa ingest reconcile`.

    Exits 1 when anything diverged, so a workflow can gate on it.
    """
    settings = get_settings()
    client = bigquery.Client(project=settings.gcp_project_id)
    sample_years = tuple(int(y) for y in years.split(",") if y.strip())
    # Default cutoff: Jan 1 of LAST year — BCB rewinds a year-granular overlap, so
    # anything before that is outside what the nightly ever re-fetches.
    horizon = cutoff or f"{date.today().year - 1}-01-01"

    console.print(
        f"[bold]Reconcile check[/bold] [dim]— IBGE anos {years} (UF {uf}) · "
        f"BCB anterior a {horizon}[/dim]\n"
    )
    checks = [reconcile_check.check_ibge_pevs(client, settings, sample_years, uf)]
    for code, label, table in (
        (settings.bcb_inflation_series_ipca_code, "BCB IPCA", "inflation_series_raw"),
        ("1", "BCB PTAX USD", "currency_series_raw"),
    ):
        checks.append(
            reconcile_check.check_bcb_series(client, settings, code, label, table, horizon)
        )

    table_out = Table(show_header=True, header_style="bold")
    for col in ("", "Fonte", "Escopo", "Comparados", "Divergentes", "Só-fonte", "Só-bronze"):
        table_out.add_column(col)
    for c in checks:
        table_out.add_row(
            "[green]✓[/green]" if c.clean else "[red]✗[/red]",
            c.source,
            c.detail,
            f"{c.compared:,}".replace(",", "."),
            str(c.diverged),
            str(c.only_source),
            str(c.only_bronze),
        )
    console.print(table_out)

    for c in checks:
        for sample in c.samples:
            console.print(f"  [yellow]·[/yellow] {c.source} {sample}")

    total = sum(c.compared for c in checks)
    dirty = [c for c in checks if not c.clean]
    if dirty:
        console.print(
            f"\n[red]Revisão detectada[/red] em {len(dirty)} fonte(s) — "
            f"rode [bold]embrapa ingest reconcile[/bold], depois um dbt build."
        )
        raise typer.Exit(code=1)
    console.print(
        f"\n[green]✓[/green] {total:,}".replace(",", ".")
        + " pontos conferidos, nenhuma revisão — reconcile não é necessário."
    )


# ─── dbt passthrough ──────────────────────────────────────────────────────────
@app.command("dbt")
def dbt_passthrough(
    args: list[str] = typer.Argument(None, help="Arguments forwarded to dbt"),  # noqa: B008
) -> None:
    """Forward arbitrary args to `dbt` from inside the dbt/ project dir."""
    dbt_dir = Path(__file__).resolve().parents[2] / "dbt"
    # Use the venv's interpreter so we never resolve a system `dbt` that
    # might be on PATH with a different version.
    cmd = [sys.executable, "-m", "dbt.cli.main", *(args or ["--help"])]
    console.print(f"[dim]$ {' '.join(cmd)} (cwd={dbt_dir})[/dim]")
    result = subprocess.run(cmd, cwd=dbt_dir, check=False)
    raise typer.Exit(result.returncode)


# ─── Curadoria lifecycle (orphans → Descontinuado → human-gated purge) ──────────
def _with_webapp_context(fn):
    """Run a serving-layer op inside the webapi app context — the flask-caching cache
    must be bound for the memoized reads. Requires the ``webapi`` extra (flask)."""
    try:
        from embrapa_dashboard.webapi.app import app as webapp
    except ModuleNotFoundError as exc:  # pragma: no cover - extra not installed
        console.print(
            "[red]✗[/red] requires the webapi extra — run with "
            "[cyan]uv run --extra webapi embrapa …[/cyan]"
        )
        raise typer.Exit(1) from exc
    with webapp.app_context():
        return fn()


@app.command("mark-orphans")
def mark_orphans_cmd() -> None:
    """Detect orphan commodities (removed from the catalog, Gold data lingering) and
    auto-mark them Descontinuado — idempotent, NON-destructive. Run on the ops cadence
    (e.g. after the daily dbt build). Requires the `webapi` extra."""
    from embrapa_dashboard.serving.catalog_lifecycle import auto_mark_orphans

    res = _with_webapp_context(auto_mark_orphans)
    console.print(
        f"[green]✓[/green] orphans: detected={res['detected']} "
        f"newly_marked={res['newly_marked']} already_marked={res['already_marked']}"
    )


def _operator_identity() -> str:
    """Best-effort OS login name for the purge audit row, so the terminal 'purged'
    lifecycle event names a real operator instead of an anonymous default. Namespaced
    (parallel to the ``system:`` auto-mark author and the IAP editor emails); falls back
    to ``operator:unknown`` when the environment exposes no username."""
    try:
        user = getpass.getuser()
    except Exception:  # getpass.getuser raises when no username can be resolved
        user = ""
    return f"operator:{user}" if user else "operator:unknown"


@app.command("purge-orphan")
def purge_orphan_cmd(
    banco: str = typer.Option(..., help="Source token / banco (pevs, comex, comtrade, pam, ppm)"),
    code: str = typer.Option(
        ..., help="The codigo_produto of the orphan (the exact Gold code purged)"
    ),
    mark_purged: bool = typer.Option(
        False, "--mark-purged", help="Record a 'purged' event AFTER you ran the DELETEs."
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Print the DELETEs even without a fresh Gold backup (NOT recommended).",
    ),
    author: str | None = typer.Option(
        None, help="Who is purging (for the audit row). Defaults to the OS login user."
    ),
) -> None:
    """HUMAN-GATED purge of a Descontinuado orphan's Gold data. By default only PRINTS the
    backup-gated plan (the scoped DELETEs to run yourself — the project hands destructive
    deletes to a human; the agent never runs `bq rm`). After running them, re-run with
    --mark-purged to record the terminal audit event. Requires the `webapi` extra."""
    from embrapa_dashboard.serving.catalog_lifecycle import (
        mark_purged as _mark_purged,
    )
    from embrapa_dashboard.serving.catalog_lifecycle import (
        purge_plan,
    )

    if mark_purged:
        operator = author or _operator_identity()
        try:
            res = _with_webapp_context(lambda: _mark_purged(banco, code, edited_by=operator))
        except ValueError as exc:
            # A not-Descontinuado / re-added code raises — surface it cleanly, not a traceback.
            console.print(f"[red]✗[/red] {exc}")
            raise typer.Exit(1) from exc
        verb = "already recorded" if res.get("deduped") else "recorded"
        console.print(f"[green]✓[/green] purge {verb}: {banco}:{code} → purged (by {operator})")
        return

    try:
        plan = _with_webapp_context(lambda: purge_plan(banco, code))
    except ValueError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[bold]Purge plan[/bold] — {banco}:{code} (exact code)")
    # Backup-FIRST is a hard gate, not a warning: without a fresh Gold snapshot the DELETEs
    # are not even printed (the project's rollback posture), unless the operator opts in with
    # --force. This closes the "printed anyway" gap where an operator could copy the DELETEs
    # with no restore point.
    if not plan["backup_ok"] and not force:
        console.print(f"  [red]backup MISSING/STALE[/red] — {plan['backup_msg']}")
        console.print(
            "  [red]Refusing to print the DELETEs without a fresh Gold backup.[/red] "
            "Run `make dbt-build-prod-with-backup` first, or pass --force to override."
        )
        raise typer.Exit(1)
    if plan["backup_ok"]:
        console.print(f"  [green]backup OK[/green] — {plan['backup_msg']}")
    else:
        console.print(f"  [yellow]backup MISSING/STALE (forced)[/yellow] — {plan['backup_msg']}")
    console.print("\n  Run manually (after confirming the backup):")
    for stmt in plan["statements"]:
        console.print(f"    [cyan]{stmt}[/cyan]")
    console.print(
        "\n  [yellow]Note:[/yellow] Gold is rebuilt from Bronze by dbt. For the purge to be "
        "PERMANENT you must ALSO: (1) delete the matching Bronze rows; (2) rebuild the affected "
        "Silver models with --full-refresh (silver_ibge_pevs / silver_comtrade_flows are "
        "incremental and otherwise retain the rows); (3) drop the product from the ingestion "
        "scope (config.py or the catalog). Otherwise the data returns on the next dbt build, "
        "while the lifecycle stays 'purged' — a silent divergence."
    )
    console.print(
        f"\n  After running, record it: "
        f"[cyan]embrapa purge-orphan --banco {banco} --code {code} --mark-purged[/cyan]"
    )


# ─── authorization allowlists (Curadoria editors + Engenharia attribute editors) ───────
# The no-Console alternative to hand-editing the research_inputs allowlist tables.


@editors_app.command("add")
def editors_add(
    email: str = typer.Option(..., help="Email to authorize as a catalog editor."),
    resource: str = typer.Option("produto_catalog", help="Catalog resource id."),
    added_by: str | None = typer.Option(
        None, help="Who is granting (audit). Defaults to the OS login user."
    ),
) -> None:
    """Authorize an editor of the Curadoria catalog. Requires the `webapi` extra."""
    from embrapa_dashboard.serving.curation import add_catalog_editor

    granter = added_by or _operator_identity()
    e = _with_webapp_context(lambda: add_catalog_editor(resource, email, added_by=granter))
    console.print(f"[green]✓[/green] editor authorized: {e} on {resource} (by {granter})")


@editors_app.command("remove")
def editors_remove(
    email: str = typer.Option(..., help="Email to de-authorize."),
    resource: str = typer.Option("produto_catalog", help="Catalog resource id."),
) -> None:
    """De-authorize a catalog editor. Requires the `webapi` extra."""
    from embrapa_dashboard.serving.curation import remove_catalog_editor

    n = _with_webapp_context(lambda: remove_catalog_editor(resource, email))
    console.print(f"[green]✓[/green] removed {n} row(s) for {email.strip().lower()} on {resource}")


@attribute_editors_app.command("add")
def attribute_editors_add(
    email: str = typer.Option(..., help="Email to authorize as an attribute editor."),
    added_by: str | None = typer.Option(
        None, help="Who is granting (audit). Defaults to the OS login user."
    ),
) -> None:
    """Authorize an attribute editor (Engenharia de atributos). Requires the `webapi` extra."""
    from embrapa_dashboard.serving.research_inputs import add_attribute_editor

    granter = added_by or _operator_identity()
    e = _with_webapp_context(lambda: add_attribute_editor(email, added_by=granter))
    console.print(f"[green]✓[/green] attribute editor authorized: {e} (by {granter})")


@attribute_editors_app.command("remove")
def attribute_editors_remove(
    email: str = typer.Option(..., help="Email to de-authorize."),
) -> None:
    """De-authorize an attribute editor. Requires the `webapi` extra."""
    from embrapa_dashboard.serving.research_inputs import remove_attribute_editor

    n = _with_webapp_context(lambda: remove_attribute_editor(email))
    console.print(f"[green]✓[/green] removed {n} row(s) for {email.strip().lower()}")


@app.command("catalog-seed-from-env")
def catalog_seed_from_env_cmd(
    author: str = typer.Option("system:catalog-seed", help="Audit author for the seeded rows."),
    agrupamento_default: str | None = typer.Option(
        None, help="agrupamento for codes not yet cataloged (defaults to the code itself)."
    ),
) -> None:
    """Seed the Curadoria catalog with the current IBGE *_PRODUCT_CODES env codes so the
    catalog-driven ingestion resolver reproduces them exactly — the cutover backfill for
    CATALOG_AUTHORITATIVE_INGESTION. Idempotent (a re-run is a no-op). PPM codes are tagged
    with their sidra_tabela (herd/animal). Requires the `webapi` extra."""
    from embrapa_dashboard.serving.curation import seed_catalog_from_env
    from embrapa_dashboard.serving.iap import IAP_EMAIL_HEADER

    headers = {IAP_EMAIL_HEADER: f"accounts.google.com:{author}"}
    res = _with_webapp_context(
        lambda: seed_catalog_from_env(headers, agrupamento_default=agrupamento_default)
    )
    console.print(
        f"[green]✓[/green] catalog seeded from env: seeded={res['seeded']} "
        f"skipped(already)={res['skipped']}"
    )


@app.command("flow-market-seed")
def flow_market_seed_cmd(
    author: str = typer.Option("system:flow-market-seed", help="Audit author for the seeded rows."),
) -> None:
    """Backfill the (customs procedure × flow) market-nature log from the retired
    comtrade_market_nature seed's 25 pairs — the cutover for reverting market-nature to the
    editable matrix. Idempotent (a pair already set to the same market is skipped). Run
    against prod BEFORE the dbt build so serving_comtrade_annual.market_nature stays
    populated. Requires the `webapi` extra."""
    from embrapa_dashboard.serving.attribute_engineering import seed_flow_market_from_seed
    from embrapa_dashboard.serving.iap import IAP_EMAIL_HEADER

    headers = {IAP_EMAIL_HEADER: f"accounts.google.com:{author}"}
    res = _with_webapp_context(lambda: seed_flow_market_from_seed(headers))
    console.print(
        f"[green]✓[/green] flow-market seeded: seeded={res['seeded']} "
        f"skipped(already)={res['skipped']} of {res['total']}"
    )


if __name__ == "__main__":
    app()
