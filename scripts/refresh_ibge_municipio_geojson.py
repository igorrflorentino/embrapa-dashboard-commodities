"""Regenerate the vendored per-UF municipal GeoJSON meshes for the Geografia map.

The choropleth can only NARROW below the UF if it has municipal geometry. The
sibling script :mod:`refresh_ibge_municipio_mesh` fetches the código→ancestry
*table* (which município belongs to which mesorregião/…); this one fetches the
*shapes*, so a sub-UF selection finally changes what the map draws instead of
shading the whole state (``PLANS/geo_subregions.md``, step 7).

ONE FILE PER UF, not one for Brazil. The whole-country municipal mesh is ~3.6 MB
(836 KB gzipped) — heavier than maplibre itself — and 5570 polygons at country
zoom are 2-3px smudges, so the view only ever loads a UF at a time (~7-69 KB
gzipped each). Vendored rather than fetched from IBGE at runtime: the map is
deliberately basemap-less so it works offline, and a runtime dependency on an
external host would give that up (plus a CSP entry and an availability risk) for
data that changes a couple of times a decade.

``qualidade=minima`` is IBGE's own generalization. The next level up quadruples
the payload (PA: 56 KB → 214 KB gzipped) for detail invisible at state zoom.
Coordinates are then rounded to 3 decimals (~110 m, matching the UF mesh already
in ``frontend/src/charts/brazilUfGeo.js``), which is lossless for this use and
saves a further ~17%. Rounding is safe for shared borders: adjacent municípios
carry the *same* input coordinates, so both sides round identically and no
slivers open between them.

Each feature keeps IBGE's ``codarea`` property — the 7-digit city code, which is
already the join key everywhere in this project (``dim_geo_municipio.city_code``,
``/api/geo-mesh``'s ``cityCode``, the ``/api/municipio-yearly`` cube). No mapping
table is needed on either side.

    uv run python scripts/refresh_ibge_municipio_geojson.py

Writes ``frontend/public/geo/municipios/<UF>.json`` (27 files, ~2.9 MB total).
Vite copies ``frontend/public/**`` verbatim into ``dist``, which Flask serves as
static files, so they land at ``/geo/municipios/<UF>.json`` with no route.

Uses ``requests`` (a core dep) because the host gzip-encodes the response.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

# v3 of the malhas API takes `intrarregiao`, which returns the UF subdivided into
# its municípios (v2 could only return the UF outline itself).
URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
    "?formato=application/vnd.geo+json&intrarregiao=municipio&qualidade=minima"
)
OUT_DIR = Path(__file__).resolve().parents[1] / "frontend" / "public" / "geo" / "municipios"

# The 27 federative units (26 states + DF), matching the UF registry the map joins on.
UFS = [
    "AC",
    "AL",
    "AP",
    "AM",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MT",
    "MS",
    "MG",
    "PA",
    "PB",
    "PR",
    "PE",
    "PI",
    "RJ",
    "RN",
    "RS",
    "RO",
    "RR",
    "SC",
    "SP",
    "SE",
    "TO",
]

# IBGE's own município count per the Localidades API (~5570). A partial fetch that
# still returns valid JSON would silently shrink the map, so the total is asserted.
EXPECTED_TOTAL = 5570
COORD_PRECISION = 3


def _round_coords(node: object) -> object:
    """Round every coordinate in an arbitrarily nested GeoJSON coordinate array.

    GeoJSON nests differently per geometry type (Polygon: ring→point→number;
    MultiPolygon: one level deeper), so recurse on lists rather than assuming depth.
    """
    if isinstance(node, list):
        return [_round_coords(x) for x in node]
    if isinstance(node, float):
        return round(node, COORD_PRECISION)
    return node


def _distinct_points(ring: list) -> int:
    return len({(p[0], p[1]) for p in ring if isinstance(p, list) and len(p) >= 2})


def _rings(geometry: dict) -> list:
    """Every polygon ring in a Polygon or MultiPolygon, flattened one level."""
    coords = geometry.get("coordinates") or []
    if geometry.get("type") == "Polygon":
        return list(coords)
    return [ring for poly in coords for ring in poly]


def _fetch(uf: str) -> dict:
    resp = requests.get(URL.format(uf=uf), timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    written = 0

    for uf in UFS:
        payload = _fetch(uf)
        features = payload.get("features") or []
        if not features:
            raise SystemExit(f"{uf}: IBGE returned no features — refusing to write an empty mesh.")

        for feat in features:
            code = str((feat.get("properties") or {}).get("codarea", ""))
            if not code.isdigit() or len(code) != 7:
                raise SystemExit(f"{uf}: feature with a non-município codarea {code!r}.")
            geom = feat.get("geometry") or {}
            geom["coordinates"] = _round_coords(geom.get("coordinates"))
            # A ring flattened to fewer than 3 distinct points is a degenerate polygon;
            # maplibre's geojson-vt worker has blanked the whole map on malformed
            # geometry before (see geoSanitize.js), so fail loudly here instead.
            for ring in _rings(geom):
                if _distinct_points(ring) < 3:
                    raise SystemExit(
                        f"{uf}: município {code} collapsed to < 3 points when rounded."
                    )
            # Drop everything except the join key — IBGE ships no name here, and the
            # view already resolves cityCode→name from the cached /api/geo-mesh.
            feat["properties"] = {"codarea": code}

        out = OUT_DIR / f"{uf}.json"
        # Compact separators: this is a machine-read asset, not a file anyone diffs
        # by eye, and the whitespace would be ~20% of the bytes served.
        out.write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": features},
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        total += len(features)
        written += 1
        print(f"{uf}: {len(features):>3} municípios · {out.stat().st_size // 1024:>3} KB")

    if total != EXPECTED_TOTAL:
        raise SystemExit(
            f"Wrote {total} municípios across {written} UFs, expected {EXPECTED_TOTAL}. "
            "IBGE may have changed the mesh (a new município is legitimate — bump "
            "EXPECTED_TOTAL); a shortfall usually means a truncated response."
        )
    print(f"\nWrote {total} municípios across {written} UFs to {OUT_DIR}")


if __name__ == "__main__":
    main()
