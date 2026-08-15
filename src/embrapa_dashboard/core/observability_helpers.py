"""Shared observability lifecycle for ingest pipelines.

The CLI layer (not the pipeline modules) owns the event lifecycle so the
pipelines stay pure and testable. Two helpers live here:

* :func:`pipeline_run` — wraps a *single-chunk* ingest (IBGE, BCB inflation, BCB
  currency, and future single-shot sources) in the exact event sequence one
  sweep emits, so every such command shares one code path and shows up
  identically in ``embrapa monitor``.

* :func:`chunked_run` — the per-chunk observability scaffold (``chunks_ok`` /
  ``chunks_failed`` bookkeeping, the ``chunk_start`` / ``chunk_end`` /
  ``chunk_error`` emit pair, per-chunk timing, and the ``pipeline_end``
  summary) factored out of the three multi-chunk commands (``ingest comex``,
  ``ingest comtrade``, ``ingest ibge-batch``). The command body stays thin: it
  drives a loop (or delegates the loop to ``pipeline.run(on_chunk=...)``) and
  reports each chunk through the yielded :class:`ChunkTracker`.

Two small value types are shared between the pipeline modules and the CLI so a
pipeline can describe a chunk's fate without importing typer/console:

* :class:`ChunkOutcome` — what happened to one chunk (loaded / skipped / failed).
* :class:`IngestPartialFailure` — raised by ``pipeline.run`` when it owns the
  loop (no live ``on_chunk`` consumer, e.g. ``ingest all``) and at least one
  chunk failed, so a source-level handler can collect it.

Single-chunk event sequence emitted by :func:`pipeline_run`:

    pipeline_start ─► chunk_start ─► [ your work runs here ]
                                        │
                          success ──────┤────► chunk_end + pipeline_end(ok=1)
                          exception ────┘────► chunk_error + pipeline_end(failed=1)  (re-raised)
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from embrapa_dashboard import observability

ChunkStatus = Literal["loaded", "skipped", "failed"]


@dataclass(frozen=True)
class ChunkOutcome:
    """The fate of a single chunk, reported by a pipeline to its driver.

    ``status``:
        * ``"loaded"``  — Phase 2 ran and appended to Bronze (``destination`` set).
        * ``"skipped"`` — nothing to do (source unchanged, no products, empty
          fetch, or a legitimate current-year 404). ``detail`` says which.
        * ``"failed"``  — the chunk raised; ``detail`` carries the error text.

    ``transient`` (only meaningful when ``status == "failed"``): the chunk raised
    a :class:`~embrapa_dashboard.core.exceptions.SourceTransientError` (a retryable
    upstream-API failure that already exhausted the tenacity retry budget) rather
    than a code bug or a data-integrity problem. Lets the CLI's exit-code /
    alerting decision tell "expected, self-healing on the next scheduled run"
    apart from "needs a human" without parsing error text.

    Kept free of timing/console so a pipeline can build it without importing the
    CLI; the :class:`ChunkTracker` measures duration and renders it.
    """

    chunk_id: str
    status: ChunkStatus
    destination: str = ""
    detail: str = ""
    transient: bool = False


class IngestPartialFailure(Exception):
    """At least one chunk failed while ``pipeline.run`` owned the loop.

    Raised only when ``run`` has no live ``on_chunk`` consumer to forward
    failures to (e.g. ``ingest all`` calls ``run`` bare). The CLI's multi-chunk
    commands pass an ``on_chunk`` callback and decide their own exit code, so
    they never see this — they read the tracker's collected failures instead.

    ``failures`` is the list of ``(chunk_id, error_text)`` that failed.
    ``all_transient`` is True when every failed chunk was a marked
    :class:`~embrapa_dashboard.core.exceptions.SourceTransientError` (see
    :class:`ChunkOutcome`) — the source-level handler uses it to tell an
    expected, self-healing degradation apart from a real bug.
    """

    def __init__(self, failures: list[tuple[str, str]], *, all_transient: bool = False) -> None:
        self.failures = failures
        self.all_transient = all_transient
        joined = "; ".join(f"{cid}: {err}" for cid, err in failures)
        super().__init__(f"{len(failures)} chunk(s) failed: {joined}")


def run_chunks(
    chunks: Iterable[tuple[str, Callable[[], ChunkOutcome]]],
    *,
    on_chunk_start: Callable[[str], None] | None = None,
    on_chunk: Callable[[ChunkOutcome], None] | None = None,
) -> str:
    """Drive an iterable of ``(chunk_id, process)`` units with continue-on-failure.

    The shared run-loop for the chunked pipelines (COMEX, COMTRADE), so the
    continue-on-failure + aggregate-and-raise contract lives in ONE place instead
    of being copied per source. Each ``process`` is a zero-arg callable returning a
    :class:`ChunkOutcome` (it has already captured its own per-chunk args + clients);
    it must not raise — pipelines wrap their per-chunk work so a transient error
    becomes a ``failed`` outcome, letting the loop move on instead of stranding the
    rest. ``on_chunk_start(chunk_id)`` fires before each chunk; ``on_chunk(outcome)``
    after. Returns the last non-empty ``destination``.

    With **no** ``on_chunk`` consumer (e.g. ``ingest all`` calls ``run`` bare), any
    failure raises :class:`IngestPartialFailure` at the end so a source-level handler
    collects them; with a consumer, returns normally and the caller decides the exit
    code from the outcomes it saw.
    """
    last_destination = ""
    failures: list[tuple[str, str]] = []
    all_transient = True
    for chunk_id, process in chunks:
        if on_chunk_start is not None:
            on_chunk_start(chunk_id)
        outcome = process()
        if outcome.status == "failed":
            failures.append((chunk_id, outcome.detail[:200]))
            all_transient = all_transient and outcome.transient
        elif outcome.destination:
            last_destination = outcome.destination
        if on_chunk is not None:
            on_chunk(outcome)
    if failures and on_chunk is None:
        raise IngestPartialFailure(failures, all_transient=all_transient)
    return last_destination


@contextmanager
def pipeline_run(name: str, *, params: dict | None = None) -> Iterator[tuple[str, Path]]:
    """Wrap a single-chunk ingest in the standard observability event sequence.

    Yields ``(run_id, log_path)`` so the caller can surface the log location.
    On any exception the helper emits ``chunk_error`` + ``pipeline_end`` and
    re-raises, so callers keep their own error handling / exit codes.

    Usage::

        with pipeline_run("bcb-inflation", params={"full": full}) as (run_id, log_path):
            console.print(f"event log: {log_path}")
            destination = bcb_inflation.run(settings, full=full)
        # destination is in scope here; only reached on success
    """
    run_id, log_path = observability.init_run(name)
    observability.emit(
        "pipeline_start",
        pipeline=name,
        run_id=run_id,
        chunks_total=1,
        params=params or {},
    )
    observability.emit("chunk_start", chunk_id=name, chunk_n=1, chunk_total=1)
    started = time.monotonic()
    try:
        yield run_id, log_path
    except Exception as exc:
        observability.emit("chunk_error", chunk_id=name, error=str(exc)[:300])
        observability.emit(
            "pipeline_end",
            duration_s=round(time.monotonic() - started, 2),
            chunks_ok=0,
            chunks_failed=1,
        )
        raise
    else:
        duration = round(time.monotonic() - started, 2)
        observability.emit("chunk_end", chunk_id=name, duration_s=duration)
        observability.emit(
            "pipeline_end",
            duration_s=duration,
            chunks_ok=1,
            chunks_failed=0,
        )


@dataclass
class ChunkTracker:
    """Per-chunk observability bookkeeping shared by every multi-chunk command.

    Holds ``chunks_ok`` / ``chunks_failed``, emits the ``chunk_start`` /
    ``chunk_end`` / ``chunk_error`` events with per-chunk timing, and is read
    back by the command after the loop to print its source-specific summary and
    pick an exit code. Created and finalized by :func:`chunked_run`.

    Two usage shapes:
        * Manual loop (``ingest ibge-batch``): call :meth:`start_chunk` before the
          work and :meth:`finish` with a :class:`ChunkOutcome` after.
        * Delegated loop (``ingest comex`` / ``ingest comtrade`` via
          ``pipeline.run``): pass :meth:`start_chunk` as ``on_chunk_start`` and
          :meth:`finish` as ``on_chunk`` — ``run`` drives them.
    """

    total: int
    log_path: Path | None = None
    chunks_ok: list[str] = field(default_factory=list)
    chunks_failed: list[tuple[str, str]] = field(default_factory=list)
    # chunk_ids from chunks_failed whose ChunkOutcome was marked transient — lets
    # the command decide "all failures were expected/self-healing" without
    # re-parsing error text. See ChunkOutcome.transient.
    chunks_failed_transient: list[str] = field(default_factory=list)
    _n: int = 0
    _chunk_started: float = 0.0

    def start_chunk(self, chunk_id: str) -> int:
        """Emit ``chunk_start`` for the next chunk and start its timer.

        Returns the 1-based chunk index, handy for ``[i/total]`` console lines.
        """
        self._n += 1
        self._chunk_started = time.monotonic()
        observability.emit(
            "chunk_start", chunk_id=chunk_id, chunk_n=self._n, chunk_total=self.total
        )
        return self._n

    def finish(self, outcome: ChunkOutcome) -> None:
        """Emit ``chunk_end`` / ``chunk_error`` for a just-finished chunk and tally it."""
        duration = round(time.monotonic() - self._chunk_started, 2)
        if outcome.status == "failed":
            observability.emit(
                "chunk_error",
                chunk_id=outcome.chunk_id,
                chunk_n=self._n,
                chunk_total=self.total,
                duration_s=duration,
                error=outcome.detail[:300],
            )
            self.chunks_failed.append((outcome.chunk_id, outcome.detail[:200]))
            if outcome.transient:
                self.chunks_failed_transient.append(outcome.chunk_id)
        else:
            observability.emit(
                "chunk_end",
                chunk_id=outcome.chunk_id,
                chunk_n=self._n,
                chunk_total=self.total,
                duration_s=duration,
                destination=outcome.destination,
            )
            self.chunks_ok.append(outcome.chunk_id)

    @property
    def last_duration_s(self) -> float:
        """Seconds the most recently finished chunk took (for console echo)."""
        return round(time.monotonic() - self._chunk_started, 2)

    @property
    def all_failures_transient(self) -> bool:
        """True when there's at least one failure and every one of them was
        transient (expected, self-healing on the next scheduled run)."""
        return bool(self.chunks_failed) and len(self.chunks_failed_transient) == len(
            self.chunks_failed
        )


@contextmanager
def chunked_run(name: str, *, total: int, params: dict | None = None) -> Iterator[ChunkTracker]:
    """Wrap a multi-chunk ingest command in the standard event lifecycle.

    Inits the run, emits ``pipeline_start`` (with ``chunks_total``), yields a
    :class:`ChunkTracker` the command reports each chunk through, then emits
    ``pipeline_end`` with the final ok/failed counts on exit.

    The command keeps ownership of its source-specific console summary and exit
    code: after the ``with`` block it inspects ``tracker.chunks_failed`` and
    raises ``typer.Exit`` itself. This helper never prints and never exits — it
    only owns the event scaffold (the part that was copy-pasted three times).

    ``tracker.log_path`` carries the JSONL path so the command can print the
    ``event log:`` line without re-querying ``observability``.
    """
    run_id, log_path = observability.init_run(name)
    tracker = ChunkTracker(total=total, log_path=log_path)
    observability.emit(
        "pipeline_start",
        pipeline=name,
        run_id=run_id,
        chunks_total=total,
        params=params or {},
    )
    started = time.monotonic()
    try:
        yield tracker
    finally:
        observability.emit(
            "pipeline_end",
            duration_s=round(time.monotonic() - started, 2),
            chunks_ok=len(tracker.chunks_ok),
            chunks_failed=len(tracker.chunks_failed),
        )
