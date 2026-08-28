"""`IngestSpec.cadence_days` must match the cron in the script that creates the trigger.

These two live apart — the cadence is a Python field read by `doctor`'s heartbeat check,
the cron is a shell default in `deploy/ingestion/schedule*.sh` — and nothing recomputes
either from the other. If they drift, the check silently gets the wrong window: too wide
and a dead trigger goes unreported, too narrow and it cries wolf every cycle.

This bit already: the heartbeat check originally derived "daily" from `in_all`, which
stopped being true the moment the batch moved to weekly (2026-08-28). The window is a
fact about the SCHEDULER, so pin it to the scheduler's own file.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY = REPO / "deploy" / "ingestion"

# script → the sources it triggers. The batch script carries no args override, so it runs
# the image's CMD ["all"] — every source with in_all=True.
SCRIPTS = {
    "schedule.sh": None,  # the batch: resolved from INGESTS below
    "schedule_currency.sh": ["bcb-currency"],
    "schedule_pam.sh": ["ibge-pam"],
    "schedule_ppm.sh": ["ibge-ppm"],
    "schedule_comtrade.sh": ["comtrade"],
}


def _default_cron(script: str) -> str:
    """The CRON default the script falls back to when no env var overrides it."""
    text = (DEPLOY / script).read_text(encoding="utf-8")
    m = re.search(r'CRON="\$\{CRON:-([^}"]+)\}"', text) or re.search(
        r'CRON="\$\{[A-Z_]*SCHEDULE_CRON:-([^}"]+)\}"', text
    )
    assert m, f"{script}: no CRON default found"
    return m.group(1).strip()


def _cadence_days_from_cron(cron: str) -> int:
    """Days between firings, for the three shapes this repo uses."""
    _minute, _hour, dom, _month, dow = cron.split()
    if dom != "*":
        return 31  # a fixed day of the month
    if dow != "*":
        return 7  # a fixed weekday
    return 1  # every day


def _specs():
    from embrapa_dashboard.cli import INGESTS

    return {s.name: s for s in INGESTS}


def _expected_cadence() -> dict[str, int]:
    """Shortest interval any scheduler fires each source at.

    A source can have MORE than one trigger: `bcb-currency` has its own daily one AND
    rides the weekly batch. Its effective cadence is the shorter of the two — taking the
    batch's would let it go 7 days dark before the heartbeat check complained, when the
    daily trigger dying is exactly what we want to hear about within a day.
    """
    specs = _specs()
    out: dict[str, int] = {}
    for script, names in SCRIPTS.items():
        every = _cadence_days_from_cron(_default_cron(script))
        for name in names or [n for n, sp in specs.items() if sp.in_all]:
            out[name] = min(out.get(name, every), every)
    return out


def test_declared_cadence_matches_the_schedulers_that_fire_each_source() -> None:
    specs = _specs()
    expected = _expected_cadence()
    mismatched = [
        f"{name}: cadence_days={specs[name].cadence_days}, schedulers fire it every {days}d"
        for name, days in sorted(expected.items())
        if specs[name].cadence_days != days
    ]
    assert mismatched == []


def test_every_source_is_covered_by_some_scheduler() -> None:
    """A source with no trigger would sit silent forever and the heartbeat check, which
    only looks at sources it has SEEN, would never notice."""
    specs = _specs()
    triggered = {n for names in SCRIPTS.values() if names for n in names}
    triggered |= {n for n, s in specs.items() if s.in_all}
    assert sorted(set(specs) - triggered) == []
