"""A test path named in a doc or a skill must be a file that exists.

Docs and skills are read as instructions — a developer (or an agent loading the skill)
runs what they name. `.claude/skills/lint-and-test/SKILL.md` listed `tests/test_seam.py`,
`test_serializers.py`, `test_format.py`, `test_registries.py` and
`test_cache_resilience.py` long after all five were renamed with a `test_webapi_` prefix,
so following it produced "file not found" five times.

Test paths are the subset worth pinning automatically: they are unambiguous (no
human-vocabulary false positives, unlike a glossary term or a filter's `column:` label),
and renaming a test file is exactly the routine act that leaves the reference behind.

CHANGELOG.md is excluded on purpose — it records what was true at each release, so a path
that has since been renamed or deleted is CORRECT there, not stale.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# A literal test path in prose/backticks. Globs (`test_comex_*.py`) are covered separately.
CITED = re.compile(r"tests/(test_[a-z0-9_]+\.py)")
GLOB_CITED = re.compile(r"tests/(test_[a-z0-9_]*\*[a-z0-9_.]*\.py)")


def _docs() -> list[Path]:
    patterns = ("*.md", "docs/*.md", "PLANS/*.md", ".claude/skills/*/*.md")
    return [p for pat in patterns for p in REPO.glob(pat) if p.name != "CHANGELOG.md"]


def test_every_cited_test_file_exists() -> None:
    tests_dir = REPO / "tests"
    missing = []
    for doc in _docs():
        text = doc.read_text(encoding="utf-8")
        for name in sorted(set(CITED.findall(text))):
            if not (tests_dir / name).exists():
                missing.append(f"{doc.relative_to(REPO)} → tests/{name}")
    assert missing == []


def test_every_cited_test_glob_matches_something() -> None:
    """`tests/test_comex_*.py` is a promise that the family exists; an empty match means the
    family was renamed away and the doc still points at it."""
    tests_dir = REPO / "tests"
    empty = []
    for doc in _docs():
        for pattern in sorted(set(GLOB_CITED.findall(doc.read_text(encoding="utf-8")))):
            if not list(tests_dir.glob(pattern)):
                empty.append(f"{doc.relative_to(REPO)} → tests/{pattern}")
    assert empty == []
