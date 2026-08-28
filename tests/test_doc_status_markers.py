"""A document that describes a PAST state has to say so, at the top.

Audit reports and feature plans read like work queues. `docs/audits/` holds point-in-time
reports on versions long superseded (v1.5.2, v1.6.0, specific PRs) — five of the eight
carried no marker, so nothing on the page distinguished "findings we already fixed" from
"findings still open". `PLANS/comtrade_flows_regimes_market.md` opened with
"**Objetivo.** Habilitar…" and no status at all, while CLAUDE.md says that feature is
FROZEN and "do NOT treat it as activatable".

Both hazards are the same one this repo keeps hitting: a document asserting a state the
project has moved past. Here the fix is cheap and mechanical — require the marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HEAD_LINES = 10  # a marker below this is not "at the top" for a reader who skims

# The vocabulary this repo actually uses to declare a document's state. The rule is
# "declares its state", not "uses the word Status" — two plans lead with a SUPERSEDED
# banner and put the historical Status line under it, which reads BETTER, not worse.
MARKERS = (
    "STATUS",
    "HISTÓRICO",
    "HISTORICAL",
    "SUPERSEDED",
    "CONGELADO",
    "FROZEN",
    "DONE",
    "COMPLETE",
    "IMPLEMENTED",
)

AUDITS = sorted((REPO / "docs" / "audits").glob("*.md"))
# README.md is the index of the directory, not a plan.
PLANS = sorted(p for p in (REPO / "PLANS").glob("*.md") if p.name != "README.md")


def _head(path: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8").split("\n")[:HEAD_LINES])


@pytest.mark.parametrize("doc", AUDITS, ids=lambda p: p.name)
def test_audit_report_declares_itself_historical(doc: Path) -> None:
    head = _head(doc).upper()
    assert any(m in head for m in MARKERS), (
        f"{doc.name}: an audit report needs a marker in its first {HEAD_LINES} lines saying it "
        f"is a point-in-time record, or a reader takes its findings for open work."
    )


@pytest.mark.parametrize("doc", PLANS, ids=lambda p: p.name)
def test_plan_declares_a_status(doc: Path) -> None:
    head = _head(doc).upper()
    assert any(m in head for m in MARKERS), (
        f"{doc.name}: a plan must declare its state in its first {HEAD_LINES} lines "
        f"({' / '.join(MARKERS)}), or a reader cannot tell a design record from a backlog."
    )
