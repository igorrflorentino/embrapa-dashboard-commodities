"""Unit tests for embrapa_dashboard.release — the running version's release date.

The value is rendered beside the version in the dashboard's *Sobre* page, so the
contract that matters is: return the REAL date or nothing at all. Every "cannot
determine" path must yield None, never a plausible-looking substitute — a fabricated
date would present an old build as freshly released.
"""

from __future__ import annotations

import pathlib
from datetime import date

from embrapa_dashboard import release

_CHANGELOG = """# Changelog

---

## [1.24.6] - 2026-08-16

### Fixed
- something

## [1.24.5] - 2026-08-15

### Changed
- something older
"""


def _write(tmp_path, monkeypatch, text=_CHANGELOG):
    """Write a CHANGELOG fixture AND pin the lookup to it.

    Pinning is not optional: _candidates() also probes the repo root, so a fixture that
    merely writes into tmp_path still falls through to the project's REAL CHANGELOG when
    the fixture has no match — which silently turned the literal-match test green against
    the wrong file the moment that version was actually released.
    """
    path = tmp_path / "CHANGELOG.md"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(release, "_candidates", lambda: [path])


def test_reads_the_date_of_the_requested_version(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch)
    assert release.release_date("1.24.6") == date(2026, 8, 16)
    # Not just the topmost section — an older version resolves to ITS own date.
    assert release.release_date("1.24.5") == date(2026, 8, 15)


def test_unreleased_version_has_no_date(tmp_path, monkeypatch):
    """A version with no CHANGELOG section (a dev build between releases) → None."""
    _write(tmp_path, monkeypatch)
    assert release.release_date("9.9.9") is None


def test_version_is_matched_literally_not_as_a_regex(tmp_path, monkeypatch):
    """`1.24.6` must not match via the regex dot-wildcard (e.g. `1a24b6`), and a prefix
    must not match a longer version — both would report the WRONG release's date."""
    _write(tmp_path, monkeypatch, "## [1x24x6] - 2020-01-01\n\n## [1.24.60] - 2019-01-01\n")
    assert release.release_date("1.24.6") is None


def test_missing_changelog_yields_none(tmp_path, monkeypatch):
    """The file absent from an install → None, never a raise: the Sobre page degrades to
    showing the version alone, and a provenance read must not 500 over a cosmetic field."""
    monkeypatch.setattr(release, "_candidates", lambda: [tmp_path / "CHANGELOG.md"])  # empty dir
    assert release.release_date("1.24.6") is None


def test_malformed_date_yields_none_rather_than_a_guess(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, "## [1.24.6] - 2026-13-99\n")
    assert release.release_date("1.24.6") is None


def test_defaults_to_the_installed_version(tmp_path, monkeypatch):
    """Called with no argument it resolves __version__ — the same value appVersion shows,
    so the pair on screen can never describe two different releases."""
    from embrapa_dashboard import __version__

    _write(tmp_path, monkeypatch, f"## [{__version__}] - 2026-08-16\n")
    assert release.release_date() == date(2026, 8, 16)


def test_the_real_changelog_dates_the_shipped_version():
    """Against the REPO's actual files: the shipped version must carry a CHANGELOG date.

    This is the guard that the release checklist was followed — a version bumped in
    pyproject.toml without its CHANGELOG section would ship a dateless Sobre page.

    Reads the version from pyproject.toml rather than ``__version__``: that IS the
    definition of "the version being shipped", and it is immune to the importlib.reload
    another test in this suite performs on the package global (which otherwise makes this
    assertion pass or fail depending on test ORDER).
    """
    import tomllib

    root = pathlib.Path(__file__).resolve().parents[1]
    shipped = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert release.release_date(shipped) is not None, (
        f"CHANGELOG.md has no '## [{shipped}] - YYYY-MM-DD' section — "
        "add one when bumping the version in pyproject.toml."
    )
