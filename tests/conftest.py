"""Shared pytest fixtures.

Centralizes the one isolation hazard several suites repeat by hand: ``Settings``
reads ``.env`` at repo root (``config.Settings.model_config env_file=".env"``),
and the documented dev setup (``cp .env.example .env``) puts a real one there. A
test that constructs ``Settings(...)`` without ``_env_file=None`` therefore reads
whatever the developer happens to have in ``.env`` / their shell, which makes
default-dependent assertions flaky. ``settings_factory`` builds an isolated
``Settings`` (``_env_file=None``) so new tests can opt in without re-deriving the
trick.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def settings_factory():
    """Return a builder for env-isolated ``Settings`` (never reads ``.env``)."""
    from embrapa_dashboard.config import Settings

    def _build(**overrides):
        overrides.setdefault("gcp_project_id", "test-project")
        return Settings(_env_file=None, **overrides)

    return _build


@pytest.fixture(autouse=True)
def _no_real_heartbeat_writes(monkeypatch):
    """No test may write an ingest heartbeat to the real warehouse.

    `_tracked_run` (cli.py) records one heartbeat per ingest run, so every test that
    exercises an ingest command reaches `ingestion_heartbeat.record` — which, with a
    developer's ADC present, happily INSERTed into production `research_inputs`. It did:
    a full `pytest` run left ~a dozen rows there, all `duration_s=0.0`, which then made
    `doctor` report "every scheduled ingest ran" off the back of the test suite.

    Patching `_bq_client` (not `record`) is deliberate: it neutralises only the path that
    resolves a REAL client, so `record`'s own logic still runs and stays testable — the
    heartbeat tests inject their own client and are untouched by this.
    """
    from unittest.mock import MagicMock

    from embrapa_dashboard import ingestion_heartbeat

    monkeypatch.setattr(ingestion_heartbeat, "_bq_client", lambda *a, **k: MagicMock())
