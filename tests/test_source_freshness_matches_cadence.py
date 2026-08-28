"""A source's dbt freshness window must fit the cadence its scheduler actually fires at.

These drift silently and in the WORST direction: a window tighter than the cadence warns
on every healthy day, and an operator who sees a daily warning stops reading warnings.

It nearly happened here. `bronze_ibge.sidra_raw` and `bronze_bcb.inflation_raw` carried
`warn_after: 2d / error_after: 7d` with the comment "Nightly delta ingest" — correct until
the batch moved to weekly (2026-08-28), after which 2 days would trip every day and 7 days
would error just before each healthy run.

The rule: warn must exceed the cadence, and error must exceed one full missed cycle.
COMEX is exempt — its ETag means `ingestion_timestamp` tracks DATA updates, not pipeline
health, so its window is the publish cadence (30d/60d) by design, not the trigger's.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SOURCES = REPO / "dbt" / "models" / "_sources.yml"

# dbt source table → the ingest spec whose cadence governs it.
GOVERNED_BY = {
    ("bronze_ibge", "sidra_raw"): "ibge",
    ("bronze_pam", "sidra_raw"): "ibge-pam",
    ("bronze_bcb", "inflation_raw"): "bcb-inflation",
    ("bronze_bcb", "currency_raw"): "bcb-currency",
}
# ingestion_timestamp tracks DATA here, not the pipeline — window is the publish cadence.
EXEMPT = {("bronze_comex", "comex_flows_raw"), ("bronze_comtrade", "comtrade_flows_raw")}


def _windows() -> dict[tuple[str, str], tuple[int | None, int | None]]:
    doc = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    out = {}
    for src in doc.get("sources", []):
        for tbl in src.get("tables", []):
            fresh = (tbl.get("config") or {}).get("freshness") or {}
            warn = (fresh.get("warn_after") or {}).get("count")
            err = (fresh.get("error_after") or {}).get("count")
            out[(src["name"], tbl["name"])] = (warn, err)
    return out


def _cadence(name: str) -> int:
    from embrapa_dashboard.cli import INGESTS

    return next(s.cadence_days for s in INGESTS if s.name == name)


@pytest.mark.parametrize(("key", "spec_name"), sorted(GOVERNED_BY.items()))
def test_freshness_window_is_wider_than_the_ingest_cadence(key, spec_name: str) -> None:
    warn, err = _windows()[key]
    cadence = _cadence(spec_name)
    assert warn is not None, f"{key}: no warn_after declared"
    assert warn > cadence, (
        f"{key}: warn_after={warn}d but {spec_name} only runs every {cadence}d — this warns "
        f"on healthy days, which is how operators learn to ignore warnings."
    )
    # `error_after` is OPTIONAL by design: the monthly sources are warn-only on purpose,
    # because whether their trigger fired is answered precisely by doctor's Ingest
    # heartbeat check rather than by a freshness threshold. Where one IS set, it must
    # survive a fully missed cycle — otherwise it fails the build on a single hiccup.
    if err is not None:
        assert err > cadence * 2, (
            f"{key}: error_after={err}d must survive one fully missed cycle of {cadence}d."
        )


def test_exempt_sources_are_still_declared_and_still_exempt() -> None:
    """If an exempt source ever gains a trigger-driven timestamp, this list must be revisited."""
    windows = _windows()
    for key in EXEMPT:
        warn, _err = windows[key]
        assert warn, f"{key}: exempt from the cadence rule but must still declare a window"
        assert warn >= 30, f"{key}: exempt window should track the PUBLISH cadence, not days"
