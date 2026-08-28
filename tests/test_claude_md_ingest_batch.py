"""What `ingest all` runs, as claimed in CLAUDE.md, must match `cli.INGESTS`.

CLAUDE.md is loaded into every session, so a wrong claim there steers everything after it.
It said `make ingest-all` covers "IBGE + both BCB series + COMEX (COMTRADE is key-gated,
excluded)" — naming ONE exclusion when there are THREE: `ibge-pam` and `ibge-ppm` are
`in_all=False` too (annual sources with their own cadence). Someone running it to "refresh
everything" would silently leave two of the six bancos stale.

The batch membership is a fact the code decides, so pin the doc to the code.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _excluded_in_code() -> set[str]:
    from embrapa_dashboard.cli import INGESTS

    return {spec.name for spec in INGESTS if not spec.in_all}


def _exclusion_note() -> str:
    """ONLY the `#` comment lines that follow the `make ingest-all` line.

    A wider window is worthless here: the very next line enumerates every ingest name
    (`ingest {ibge|ibge-pam|…}`), so a block-level search is satisfied by the enumeration
    and passes even with the exclusion note deleted — which is exactly what an injected
    regression proved before this was narrowed.
    """
    lines = (REPO / "CLAUDE.md").read_text(encoding="utf-8").split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith("make ingest-all"))
    note = []
    for ln in lines[start + 1 :]:
        if not ln.startswith("#"):
            break
        note.append(ln)
    return "\n".join(note)


def test_claude_md_names_every_source_excluded_from_ingest_all() -> None:
    note = _exclusion_note()
    assert note, "CLAUDE.md no longer carries an exclusion note under `make ingest-all`"
    missing = sorted(name for name in _excluded_in_code() if name not in note)
    assert missing == [], (
        f"CLAUDE.md's `ingest all` note omits {missing} — sources cli.INGESTS marks in_all=False. "
        f"A reader takes the batch for complete and leaves those sources stale."
    )
