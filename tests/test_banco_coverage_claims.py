"""The declared coverage of a banco must match the data the pipeline can actually hold.

A `cobertura.years` label is a claim made to the researcher, and nothing recomputed it:
`un_comtrade` announced "1989 → presente" for months after the v1.13.0 totals-only
redesign moved the ingest floor to 2000 — eleven years the dashboard never had, in the
SPA registry, the backend registry, the metric ranges AND a stale override row.

Two things could not notice: the label is static, and the two registries were BOTH
wrong, so agreeing with each other proved nothing. What the label CAN be held to is the
configured ingest floor, which is the mechanism that decides the real start. Where a
banco has one, this pins the label to it; and it pins the SPA registry to the backend's,
so a future edit cannot fix one copy and leave the other.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BANCOS_JS = REPO / "frontend" / "src" / "ui" / "bancos.js"

# banco_id → the Settings field that floors its ingest window. Bancos absent here have
# no configured floor (PEVS discovers its own; SEFAZ NFe has no pipeline yet), so their
# label has nothing to be pinned against — deliberately out of scope rather than guessed.
FLOOR_FIELD = {
    "ibge_pam": "pam_start_year",
    "ibge_ppm": "ppm_start_year",
    "mdic_comex": "comex_start_year",
    "un_comtrade": "comtrade_start_year",
}


def _js_cobertura_years() -> dict[str, str]:
    """{banco_id: cobertura.years} as declared in the SPA registry.

    The metric ranges use `years: [a, b]`, so the quoted form only ever appears in a
    cobertura block — that is what makes this regex unambiguous.
    """
    src = BANCOS_JS.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for block in re.split(r"\n  \{\n    id:     '", src)[1:]:
        banco_id = block.split("'")[0]
        m = re.search(r"years:\s*'([^']+)'", block)
        if m:
            out[banco_id] = m.group(1)
    return out


def _label_start_year(label: str) -> int:
    m = re.match(r"\s*(\d{4})", label)
    assert m, f"coverage label does not start with a year: {label!r}"
    return int(m.group(1))


@pytest.mark.parametrize(("banco_id", "field"), sorted(FLOOR_FIELD.items()))
def test_backend_coverage_label_matches_configured_ingest_floor(
    banco_id: str, field: str, settings_factory
) -> None:
    from embrapa_dashboard.webapi.registries import banco_by_id

    floor = getattr(settings_factory(), field)
    label = (banco_by_id(banco_id).cobertura or {}).get("years", "")
    assert _label_start_year(label) == floor, (
        f"{banco_id}: cobertura says {label!r} but {field}={floor}. The label is a claim "
        f"to the researcher; the floor is what the ingest actually collects."
    )


@pytest.mark.parametrize(("banco_id", "field"), sorted(FLOOR_FIELD.items()))
def test_spa_coverage_label_matches_configured_ingest_floor(
    banco_id: str, field: str, settings_factory
) -> None:
    floor = getattr(settings_factory(), field)
    label = _js_cobertura_years()[banco_id]
    assert _label_start_year(label) == floor, f"{banco_id}: bancos.js says {label!r}, floor={floor}"


def test_spa_and_backend_registries_declare_the_same_coverage() -> None:
    """Fixing one copy and leaving the other is how a stale claim survives a correction."""
    from embrapa_dashboard.webapi.registries import BANCOS

    js = _js_cobertura_years()
    divergent = []
    for b in BANCOS:
        py_years = (b.cobertura or {}).get("years")
        js_years = js.get(b.id)
        if py_years and js_years and py_years != js_years:
            divergent.append(f"{b.id}: registries.py={py_years!r} bancos.js={js_years!r}")
    assert divergent == []


def test_no_metric_claims_data_older_than_its_banco_coverage() -> None:
    """A metric range wider than the banco's own coverage is the same claim, one level down —
    `exp_value`/`imp_value` both said 1989 under a cobertura that (correctly) said 2000."""
    src = BANCOS_JS.read_text(encoding="utf-8")
    offenders = []
    for block in re.split(r"\n  \{\n    id:     '", src)[1:]:
        banco_id = block.split("'")[0]
        cob = re.search(r"years:\s*'(\d{4})", block)
        if not cob:
            continue
        start = int(cob.group(1))
        for m in re.finditer(r"\{ id: '([^']+)'.*?years: \[(\d{4}), (\d{4})\]", block):
            if int(m.group(2)) < start:
                offenders.append(f"{banco_id}.{m.group(1)} starts {m.group(2)} < cobertura {start}")
    assert offenders == []
