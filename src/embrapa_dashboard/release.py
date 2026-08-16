"""The running version's RELEASE DATE, read from CHANGELOG.md.

``__version__`` already answers "which version is this?" from the installed package
metadata; this answers "when did it ship?". The two are surfaced together in the
dashboard's *Sobre* page, where a version with no date (or worse, next to an
unrelated date) reads as stale.

CHANGELOG.md is the single source of truth — the same file ``release.yml`` already
parses to compose a GitHub Release body — so the date cannot drift from the release
record. Nothing is generated at build time and nothing is hardcoded: a version whose
section is missing simply has no date, and every caller must render that absence
rather than invent one.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import embrapa_dashboard

# `## [1.24.6] - 2026-08-16` — the Keep a Changelog heading this project writes.
# The version is matched literally (re.escape) so `1.2.4` cannot match `1.2.4.1`.
_HEADING = "^## \\[{version}\\]\\s*-\\s*(\\d{{4}}-\\d{{2}}-\\d{{2}})\\s*$"


# Where CHANGELOG.md can live, in the order we trust it:
#   • the container image — Dockerfile copies it next to pyproject.toml at /app,
#     while the package itself is installed under /app/.venv/…, so a __file__-relative
#     walk would NOT find it there;
#   • a source checkout — src/embrapa_dashboard/release.py → repo root is parents[2].
def _candidates() -> list[Path]:
    return [
        Path.cwd() / "CHANGELOG.md",
        Path(__file__).resolve().parents[2] / "CHANGELOG.md",
    ]


def release_date(version: str | None = None) -> date | None:
    """The date ``version`` (default: the running one) was released, or None.

    None is a legitimate answer — an unreleased dev version, a CHANGELOG that has no
    section for it yet, or an install that does not ship the file. Callers render the
    absence; they must never substitute today's date, which would present an old build
    as fresh.
    """
    # Read __version__ off the module at CALL time, not via a from-import bound at import
    # time: the latter freezes whatever value the package had when this module first loaded,
    # so it can disagree with the appVersion shown beside it.
    wanted = version or embrapa_dashboard.__version__
    pattern = re.compile(_HEADING.format(version=re.escape(wanted)), re.MULTILINE)
    for path in _candidates():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = pattern.search(text)
        if match:
            try:
                return date.fromisoformat(match.group(1))
            except ValueError:
                # A malformed date in an otherwise-matching heading: treat the file as
                # unusable rather than guessing at the intended value.
                return None
    return None
