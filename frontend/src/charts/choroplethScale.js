// choroplethScale.js — the pure color logic behind BrazilChoropleth, split out so
// it can be unit-tested without importing maplibre-gl (WebGL, no jsdom).

// Sequential light->dark green ramp (quantized buckets); zero / no-data UFs get a
// neutral gray so "absent" reads differently from "low".
export const RAMP = ['#e8f3ec', '#bfe0cb', '#8fcaa6', '#5bb381', '#2f9460', '#16713f'];
export const NODATA = '#eef0ef';

/** {uf -> bucket color} for the data, on a 0..max linear scale quantized into
 *  `ramp`. Zero / missing values map to `nodata`. Returns { byUf, max }. */
export function ufColorScale(data, valueKey, ramp = RAMP, nodata = NODATA) {
  const rows = Array.isArray(data) ? data : [];
  const max = Math.max(1, ...rows.map((d) => Number(d[valueKey]) || 0));
  const byUf = {};
  for (const d of rows) {
    if (!d.uf) continue;
    const v = Number(d[valueKey]) || 0;
    if (v <= 0) {
      byUf[d.uf] = nodata;
      continue;
    }
    const t = Math.min(1, v / max); // linear share of the max
    const idx = Math.min(ramp.length - 1, Math.floor(t * (ramp.length - 1) + 1e-9));
    byUf[d.uf] = ramp[idx];
  }
  return { byUf, max };
}

/** {uf -> bucket color} using QUANTILE bins instead of a linear share of the max.
 *
 *  MAPA-3: the linear scale above collapses whenever the distribution is
 *  concentrated — PEVS 2024's real per-UF valor measured 23 of 27 states landing
 *  in the SAME lightest bucket (3 of 6 buckets never used at all), because one or
 *  two states dominate the max and everyone else is a tiny share of it. Quantile
 *  bins the SAME values into equal-COUNT groups instead of equal-VALUE ranges, so
 *  every bucket gets a comparable share of states — the same measured
 *  distribution spread across all 6 buckets, 4-5 UFs each. Zero/missing values
 *  still map to `nodata` and are excluded from the quantile computation (a state
 *  with no production isn't "the smallest positive producer", it's absent).
 *
 *  Returns { byUf, thresholds }: thresholds[i] is `{ color, min, max }` for each
 *  ramp bucket that got at least one UF (null for an empty one), so a legend can
 *  say what each color actually means instead of shading with no scale shown. */
export function ufColorScaleQuantile(data, valueKey, ramp = RAMP, nodata = NODATA) {
  const rows = Array.isArray(data) ? data : [];
  const positive = rows
    .map((d) => ({ uf: d.uf, v: Number(d[valueKey]) || 0 }))
    .filter((d) => d.uf && d.v > 0)
    .sort((a, b) => a.v - b.v);
  const byUf = {};
  for (const d of rows) {
    if (d.uf && !(Number(d[valueKey]) > 0)) byUf[d.uf] = nodata;
  }
  if (!positive.length) return { byUf, thresholds: ramp.map(() => null) };
  const n = positive.length;
  // Below one UF per bucket, a straight rank/n split degenerates: with n=1 it puts
  // rank 0 at position 0/1=0 — the LIGHTEST bucket — for the state's ONLY value,
  // which is simultaneously its smallest AND its largest. A single UF selected via
  // the map's own click-to-filter (or any narrow state filter) would then always
  // paint as "barely there" regardless of magnitude. Below the bucket count, spread
  // the n values across the TOP n buckets instead (darkest = most significant) —
  // continuous with the plain quantile split at n===ramp.length (both formulas
  // agree exactly there), so there's no visible jump crossing the threshold.
  const bucketOf = (rank) =>
    n <= ramp.length ? ramp.length - n + rank : Math.min(ramp.length - 1, Math.floor((rank / n) * ramp.length));
  positive.forEach((d, rank) => { byUf[d.uf] = ramp[bucketOf(rank)]; });
  const thresholds = ramp.map((color, i) => {
    const inBucket = positive.filter((_, rank) => bucketOf(rank) === i);
    return inBucket.length ? { color, min: inBucket[0].v, max: inBucket[inBucket.length - 1].v } : null;
  });
  return { byUf, thresholds };
}

/** A maplibre data-driven `match` expression on the `uf` feature property, or a
 *  constant fallback color when there's nothing to color.
 *
 *  Hardened (FINDING #5): only well-formed [string uf → string color] pairs are
 *  emitted. A `null`/`undefined`/non-string label or color injected into a
 *  maplibre `match` makes the expression compiler dereference `.length` on a
 *  missing operand and throw "Cannot read properties of undefined (reading
 *  'length')" — which blanks the map without tripping the WebGL fallback. Any
 *  bad pair is dropped; if nothing valid remains we return the constant fallback
 *  so maplibre always receives a valid paint value. */
export function fillColorExpression(byUf, fallback = NODATA) {
  const pairs = [];
  for (const [uf, color] of Object.entries(byUf || {})) {
    if (typeof uf === 'string' && uf && typeof color === 'string' && color) {
      pairs.push(uf, color);
    }
  }
  if (!pairs.length) return fallback;
  return ['match', ['get', 'uf'], ...pairs, fallback];
}
