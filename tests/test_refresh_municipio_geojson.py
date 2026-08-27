"""Unit tests for the vendored municipal-mesh generator
(``scripts/refresh_ibge_municipio_geojson.py``).

These files ARE the municipal choropleth — a silent shape change from IBGE (a renamed
property, a coordinate nesting the rounder walks wrong, a truncated response) would
ship a map that draws nothing, or worse, draws the wrong municípios, with no error
anywhere. The generator's guards are what turn each of those into a loud failure, so
they need coverage of their own; ``scripts/`` has none otherwise.

Loads the generator by path (``scripts/`` is not an importable package) and exercises
the pure helpers plus ``main()`` against a stubbed ``requests``. No network —
``main()`` is ``__main__``-guarded, so importing the module never fetches.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "refresh_ibge_municipio_geojson.py"
_spec = importlib.util.spec_from_file_location("refresh_ibge_municipio_geojson", _PATH)
assert _spec and _spec.loader
geo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(geo)


# ── Pure helpers ─────────────────────────────────────────────────────────────
def test_round_coords_walks_polygon_and_multipolygon_nesting():
    """GeoJSON nests one level deeper for MultiPolygon; the rounder must recurse on
    lists rather than assume a depth, or a MultiPolygon UF (most of them) would come
    out untouched — silently shipping the un-rounded, larger file."""
    poly = [[[-49.15453, -1.70187], [-49.1, -1.7]]]
    assert geo._round_coords(poly) == [[[-49.155, -1.702], [-49.1, -1.7]]]
    multi = [[[[-49.15453, -1.70187]]], [[[-48.00049, -16.04999]]]]
    assert geo._round_coords(multi) == [[[[-49.155, -1.702]]], [[[-48.0, -16.05]]]]
    # Non-float leaves (ints, strings) pass through untouched.
    assert geo._round_coords([1, "x", None]) == [1, "x", None]


def test_rings_flattens_both_geometry_types():
    poly = {"type": "Polygon", "coordinates": [["outer"], ["hole"]]}
    assert geo._rings(poly) == [["outer"], ["hole"]]
    multi = {"type": "MultiPolygon", "coordinates": [[["a"]], [["b"], ["c"]]]}
    assert geo._rings(multi) == [["a"], ["b"], ["c"]]
    assert geo._rings({"type": "Polygon"}) == []


def test_distinct_points_ignores_repeats_and_malformed_entries():
    # A closed ring repeats its first point last — that repeat must not count as a
    # distinct vertex, else a degenerate triangle would read as valid.
    assert geo._distinct_points([[0, 0], [1, 0], [0, 1], [0, 0]]) == 3
    assert geo._distinct_points([[0, 0], [0, 0]]) == 1
    assert geo._distinct_points([[0, 0], "junk", [5]]) == 1


# ── main(): the guards ───────────────────────────────────────────────────────
def _fc(*codes: str) -> dict:
    """A minimal but VALID FeatureCollection: one square polygon per código."""
    square = [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"codarea": c},
                "geometry": {"type": "Polygon", "coordinates": square},
            }
            for c in codes
        ],
    }


def _patch(monkeypatch, tmp_path, per_uf, ufs=("PA",), expected=None):
    """Point the generator at tmp_path and stub its fetch. `per_uf` maps UF → payload."""
    monkeypatch.setattr(geo, "OUT_DIR", tmp_path)
    monkeypatch.setattr(geo, "UFS", list(ufs))
    monkeypatch.setattr(geo, "EXPECTED_TOTAL", expected if expected is not None else 1)
    monkeypatch.setattr(geo, "_fetch", lambda uf: per_uf[uf])


def test_main_writes_one_compact_file_per_uf_keyed_on_codarea(monkeypatch, tmp_path):
    _patch(
        monkeypatch,
        tmp_path,
        {"PA": _fc("1500107"), "AC": _fc("1200013")},
        ufs=("PA", "AC"),
        expected=2,
    )
    geo.main()

    written = sorted(p.name for p in tmp_path.glob("*.json"))
    assert written == ["AC.json", "PA.json"]
    payload = json.loads((tmp_path / "PA.json").read_text(encoding="utf-8"))
    assert payload["type"] == "FeatureCollection"
    # Only the join key survives — the view resolves names from /api/geo-mesh.
    assert payload["features"][0]["properties"] == {"codarea": "1500107"}
    # Compact separators: whitespace would be ~20% of the bytes served.
    assert ", " not in (tmp_path / "PA.json").read_text(encoding="utf-8")


def test_main_rounds_coordinates_to_the_declared_precision(monkeypatch, tmp_path):
    fc = _fc("1500107")
    fc["features"][0]["geometry"]["coordinates"] = [
        [[-49.154531, -1.701872], [0.0, 0.0], [1.0, 1.0]]
    ]
    _patch(monkeypatch, tmp_path, {"PA": fc})
    geo.main()
    written = json.loads((tmp_path / "PA.json").read_text(encoding="utf-8"))
    assert written["features"][0]["geometry"]["coordinates"][0][0] == [-49.155, -1.702]


def test_main_refuses_an_empty_mesh(monkeypatch, tmp_path):
    """A UF that comes back with no features is a broken fetch, not a UF with no
    municípios — writing it would blank that state's map."""
    _patch(monkeypatch, tmp_path, {"PA": {"type": "FeatureCollection", "features": []}})
    with pytest.raises(SystemExit, match="no features"):
        geo.main()


def test_main_refuses_a_non_municipio_codarea(monkeypatch, tmp_path):
    """The malhas API serves other levels from the same shape; asking for the wrong
    `intrarregiao` returns valid GeoJSON whose codarea is NOT a 7-digit city code.
    That must fail loudly rather than ship a map that joins on nothing."""
    _patch(monkeypatch, tmp_path, {"PA": _fc("15")})  # a UF code, not a município
    with pytest.raises(SystemExit, match="non-município codarea"):
        geo.main()


def test_main_refuses_a_polygon_that_collapsed_when_rounded(monkeypatch, tmp_path):
    """Rounding must never flatten a município to fewer than 3 distinct points —
    maplibre's geojson-vt worker has blanked the whole map on malformed geometry."""
    fc = _fc("1500107")
    # Three points that all round to the same coordinate at 3 decimals.
    fc["features"][0]["geometry"]["coordinates"] = [
        [[0.00001, 0.00001], [0.00002, 0.00002], [0.00003, 0.00003]]
    ]
    _patch(monkeypatch, tmp_path, {"PA": fc})
    with pytest.raises(SystemExit, match="collapsed"):
        geo.main()


def test_main_refuses_a_total_that_does_not_match_expected(monkeypatch, tmp_path):
    """A truncated response still parses as valid GeoJSON, so the only thing standing
    between it and a half-empty map is this total."""
    _patch(monkeypatch, tmp_path, {"PA": _fc("1500107")}, expected=5570)
    with pytest.raises(SystemExit, match="expected 5570"):
        geo.main()


# ── `--check`: "could not measure" must never read as "the mesh drifted" ─────
#
# The first scheduled run of geo-mesh-check failed because IBGE timed out from a
# GitHub runner. The workflow collapsed every non-zero exit into stale=true, so a
# network failure would have opened an issue announcing that IBGE changed the mesh.
# A quarterly false alarm trains everyone to ignore the one alert that matters, so
# the two outcomes carry distinct exit codes.


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_fetch_roster_retries_then_succeeds(monkeypatch):
    calls = []

    def flaky(url, **kwargs):
        calls.append(url)
        if len(calls) < 3:
            raise geo.requests.ConnectionError("boom")
        return _Resp([{"id": 1500107}])

    monkeypatch.setattr(geo.requests, "get", flaky)
    monkeypatch.setattr(geo.time, "sleep", lambda _s: None)  # no real backoff in tests

    assert geo._fetch_roster() == [{"id": 1500107}]
    assert len(calls) == 3  # two failures absorbed


def test_fetch_roster_returns_none_when_ibge_never_answers(monkeypatch):
    def always_fails(url, **kwargs):
        raise geo.requests.ConnectTimeout("timed out")

    monkeypatch.setattr(geo.requests, "get", always_fails)
    monkeypatch.setattr(geo.time, "sleep", lambda _s: None)

    # None, not an exception: the caller has to be able to tell this apart from drift.
    assert geo._fetch_roster() is None


def test_check_reports_unreachable_not_drift_when_ibge_is_down(monkeypatch, capsys):
    monkeypatch.setattr(geo, "_fetch_roster", lambda: None)

    code = geo.check()

    assert code == geo.EXIT_UNREACHABLE
    assert code != geo.EXIT_DRIFTED  # the whole point
    out = capsys.readouterr().out
    assert "não foi verificada" in out.lower()
    # It must NOT tell the reader to go refresh the mesh — nothing was measured.
    assert "make refresh-geo" not in out


def test_check_reports_in_sync_when_roster_matches(monkeypatch, capsys):
    monkeypatch.setattr(geo, "_fetch_roster", lambda: [{"id": "1500107"}])
    monkeypatch.setattr(geo, "vendored_codes", lambda: {"1500107"})

    assert geo.check() == geo.EXIT_IN_SYNC
    assert "em dia" in capsys.readouterr().out


def test_check_reports_drift_when_ibge_added_a_municipio(monkeypatch, capsys):
    monkeypatch.setattr(geo, "_fetch_roster", lambda: [{"id": "1500107"}, {"id": "1500108"}])
    monkeypatch.setattr(geo, "vendored_codes", lambda: {"1500107"})

    assert geo.check() == geo.EXIT_DRIFTED
    assert "1500108" in capsys.readouterr().out


def test_check_ignores_roster_only_codes_ibge_does_not_draw(monkeypatch, capsys):
    # IBGE lists the código but publishes no geometry — a known upstream mismatch,
    # not staleness on our side.
    only = next(iter(geo.ROSTER_ONLY))
    monkeypatch.setattr(geo, "_fetch_roster", lambda: [{"id": "1500107"}, {"id": only}])
    monkeypatch.setattr(geo, "vendored_codes", lambda: {"1500107"})

    assert geo.check() == geo.EXIT_IN_SYNC
    assert "conhecido" in capsys.readouterr().out
