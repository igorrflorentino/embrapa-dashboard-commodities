// choroplethScale.js — the pure classification logic shared by EVERY territorial
// map in the app (BrazilChoropleth, MunicipioChoropleth, BrazilTileMap), split out
// so it can be unit-tested without importing maplibre-gl (WebGL, no jsdom).

// Sequential light->dark green ramp (quantized buckets); zero / no-data UFs get a
// neutral gray so "absent" reads differently from "low".
export const RAMP = ['#e8f3ec', '#bfe0cb', '#8fcaa6', '#5bb381', '#2f9460', '#16713f'];
export const NODATA = '#eef0ef';

/** A QUANTILE bucket assigner over `values`, into `bucketCount` bins.
 *
 *  Why quantile and not a share of the max: the territorial series this app draws
 *  are violently concentrated, and a linear ramp collapses on them. Measured on the
 *  real PEVS 2024 per-UF valor — 25 states with production — a linear split put
 *  **21-23 of them in the single lightest bucket** and left 3 of the bins unused,
 *  because one or two states own the maximum and everyone else is a rounding error
 *  against it. Quantile bins by equal COUNT instead of equal VALUE, so every bucket
 *  carries a comparable share of the units and the map actually discriminates.
 *
 *  Non-positive values are excluded from the computation and report index -1: a
 *  state with no production is not "the smallest producer", it is absent, and the
 *  caller paints it with its no-data colour.
 *
 *  Returns `{ indexOf(value), ranked, count }`. `indexOf` is O(1) (ranks are indexed
 *  up front) because the município map runs it over ~5570 values.
 */
export function quantileIndexer(values, bucketCount) {
  const positive = (values || [])
    .map((v) => Number(v))
    .filter((v) => Number.isFinite(v) && v > 0)
    .sort((a, b) => a - b);
  const n = positive.length;
  // Ties must land in the SAME bucket (equal value → equal colour), so only the
  // first occurrence of a value claims a rank.
  const rankByValue = new Map();
  positive.forEach((v, i) => { if (!rankByValue.has(v)) rankByValue.set(v, i); });

  // Below one unit per bucket a straight rank/n split degenerates: with n=1 it puts
  // rank 0 at position 0/1 = 0 — the LIGHTEST bucket — for a value that is at once
  // the smallest AND the largest. A single UF selected via the map's own
  // click-to-filter would then always paint as "barely there" whatever its
  // magnitude. Below the bucket count, spread the n values over the TOP n buckets
  // (darkest = most significant). At n === bucketCount both formulas agree exactly,
  // so nothing jumps when the selection crosses that threshold.
  const bucketOf = (rank) =>
    n <= bucketCount
      ? bucketCount - n + rank
      : Math.min(bucketCount - 1, Math.floor((rank / n) * bucketCount));

  const indexOf = (value) => {
    const v = Number(value);
    if (!Number.isFinite(v) || v <= 0 || !n) return -1;
    const rank = rankByValue.get(v);
    return rank == null ? -1 : bucketOf(rank);
  };
  return { indexOf, bucketOf, ranked: positive, count: n };
}

/** `[{ color, min, max } | null]` per bucket — the legend. A bucket nobody landed
 *  in is null, so a legend can dim it instead of inventing a range for it. */
export function quantileThresholds(indexer, ramp = RAMP) {
  const { ranked, bucketOf } = indexer;
  return ramp.map((color, i) => {
    const inBucket = ranked.filter((_, rank) => bucketOf(rank) === i);
    return inBucket.length ? { color, min: inBucket[0], max: inBucket[inBucket.length - 1] } : null;
  });
}

/** {uf -> bucket color} using quantile bins (see quantileIndexer). `uf` is whatever
 *  key the caller's rows carry — the 2-letter sigla for the UF map, the 7-digit
 *  city code for the município map.
 *
 *  Returns { byUf, thresholds } so the caller can both paint and draw a legend. */
export function ufColorScaleQuantile(data, valueKey, ramp = RAMP, nodata = NODATA) {
  const rows = Array.isArray(data) ? data : [];
  const indexer = quantileIndexer(rows.map((d) => d[valueKey]), ramp.length);
  const byUf = {};
  for (const d of rows) {
    if (!d.uf) continue;
    const i = indexer.indexOf(d[valueKey]);
    byUf[d.uf] = i < 0 ? nodata : ramp[i];
  }
  return { byUf, thresholds: quantileThresholds(indexer, ramp) };
}

/** A maplibre data-driven `match` expression on a feature property, or a constant
 *  fallback color when there's nothing to color.
 *
 *  `property` is the GeoJSON property the keys of `byUf` match against. It defaults
 *  to `'uf'` (the UF mesh's 2-letter sigla); the municipal meshes vendored from IBGE
 *  key on `'codarea'` (the 7-digit city code) instead. This used to be hardcoded to
 *  `'uf'`, so the municipal choropleth compiled a perfectly valid expression that
 *  matched *nothing* — every município fell through to the fallback and the whole
 *  state painted no-data grey, with no error anywhere to explain it.
 *
 *  Hardened (FINDING #5): only well-formed [string uf → string color] pairs are
 *  emitted. A `null`/`undefined`/non-string label or color injected into a
 *  maplibre `match` makes the expression compiler dereference `.length` on a
 *  missing operand and throw "Cannot read properties of undefined (reading
 *  'length')" — which blanks the map without tripping the WebGL fallback. Any
 *  bad pair is dropped; if nothing valid remains we return the constant fallback
 *  so maplibre always receives a valid paint value. */
export function fillColorExpression(byUf, fallback = NODATA, property = 'uf') {
  const pairs = [];
  for (const [uf, color] of Object.entries(byUf || {})) {
    if (typeof uf === 'string' && uf && typeof color === 'string' && color) {
      pairs.push(uf, color);
    }
  }
  if (!pairs.length) return fallback;
  return ['match', ['get', property], ...pairs, fallback];
}
