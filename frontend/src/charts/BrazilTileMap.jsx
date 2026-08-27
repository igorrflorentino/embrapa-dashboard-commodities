// BrazilTileMap — choropleth on a 9-row UF tile grid. Kept as SVG: a bespoke
// geographic tile layout with per-cell labels + a heat-bucket scale that Plotly
// can't match and that doesn't benefit from zoom/pan. Faithful port of the
// prototype's component. Same name + props (incl. onSelect for drill-down).
//   data: [{ uf, col, row, region, [valueKey] }]  (col/row decorated client-side)
//
// Classification comes from choroplethScale.js, shared with the two maplibre maps,
// so every territorial view in the app bins the same numbers the same way.

import { quantileIndexer, quantileThresholds } from './choroplethScale';

function BrazilTileMap({ data = [], valueKey = 'value', label = 'R$ mi', height = 420, onSelect, selectedUf, compact = true }) {
  const COLS = 8;
  const ROWS = 9;
  const CELL_W = 60;
  const CELL_H = 56;
  const GAP = 4;
  const W = COLS * (CELL_W + GAP);
  const H = ROWS * (CELL_H + GAP);

  // Only rows with valid tile coords render. A trade banco's per-UF rows can carry
  // non-state pseudo-origins (ND/EX/ZN…) that have no col/row in the UF registry —
  // positioning them at `undefined * cell` emitted NaN x/y SVG attributes (the
  // console flooded with "Received NaN for the `x`/`y` attribute"). Drop them so
  // the tile grid never produces NaN coordinates (FINDING #4/#5).
  const rows = (Array.isArray(data) ? data : []).filter(
    (d) => Number.isFinite(d.col) && Number.isFinite(d.row),
  );

  const vals = rows.map((d) => d[valueKey] || 0);

  const STOPS = [
    'var(--heat-1)', 'var(--heat-2)', 'var(--heat-3)', 'var(--heat-4)',
    'var(--heat-5)', 'var(--heat-6)', 'var(--heat-7)',
  ];
  // QUANTILE, the same rule BrazilChoropleth/MunicipioChoropleth use. This used to
  // be a linear (v-min)/(max-min) split, which collapses on concentrated series:
  // measured on the real PEVS 2024 per-UF valor, **21 of the 25 producing states
  // landed in the single lightest bucket** and 4 of these 7 stops were never used.
  //
  // It also made the Geografia view contradict itself once the choropleth moved to
  // quantile (v1.25.0): "Mapa" and "Blocos" are a toggle over the SAME numbers, so
  // flipping between them silently reclassified the data. This component backs FIVE
  // other views too (Visão geral, Rebanho, Produtividade, Qualidade, cruzadas), so
  // the linear split was the classification most of the app was actually reading.
  const indexer = quantileIndexer(vals, STOPS.length);
  const thresholds = quantileThresholds(indexer, STOPS);
  const positives = indexer.ranked;
  const min = positives.length ? positives[0] : 0;
  const max = positives.length ? positives[positives.length - 1] : 0;
  const level = (v) => indexer.indexOf(v);
  const color = (v) => {
    const i = level(v);
    return i < 0 ? 'var(--heat-0)' : STOPS[i];
  };
  const textColor = (v) => {
    const i = level(v);
    return i < 0 ? 'var(--fg-3)' : i >= 4 ? '#fff' : 'var(--fg-1)';
  };
  // Per-VALUE compact magnitude (e.g. 2_900_918_362 → "2,9 bi", 384_329_590 → "384 mi",
  // 938_274 → "938 mil") so each cell uses its OWN magnitude — a small UF is never rounded to
  // "0" by a single global factor, and a big one never overflows the 60px cell. Reuses the
  // shared magnitude kernel (autoScaleNum = magnitudeParts). `compact=false` keeps the full
  // integer (for metrics like kg/ha yield that fit and where the exact figure matters).
  const fmtTile = (v) => {
    if (compact && window.autoScaleNum && Math.abs(v) >= 1000) {
      const mp = window.autoScaleNum(v);
      const scaled = v / mp.factor;
      const txt = scaled.toLocaleString('pt-BR', { maximumFractionDigits: Math.abs(scaled) < 10 ? 1 : 0 });
      return mp.suffix ? `${txt} ${mp.suffix}` : txt;
    }
    return v.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
  };
  const REGION_BG = {
    N: 'color-mix(in srgb, var(--viz-2) 10%, transparent)',
    NE: 'color-mix(in srgb, var(--viz-3) 10%, transparent)',
    CO: 'color-mix(in srgb, var(--viz-6) 10%, transparent)',
    SE: 'color-mix(in srgb, var(--viz-1) 10%, transparent)',
    S: 'color-mix(in srgb, var(--viz-9) 10%, transparent)',
  };

  return (
    <div className="bmap-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="bmap" preserveAspectRatio="xMidYMid meet">
        {rows.map((d) => {
          const x = d.col * (CELL_W + GAP);
          const y = d.row * (CELL_H + GAP);
          const v = d[valueKey] || 0;
          const selected = selectedUf && d.uf === selectedUf;
          return (
            <g
              key={d.uf}
              className="bmap-cell"
              style={onSelect ? { cursor: 'pointer' } : undefined}
              onClick={onSelect ? () => onSelect(d) : undefined}
            >
              <rect
                x={x}
                y={y}
                width={CELL_W}
                height={CELL_H}
                rx="6"
                fill={color(v)}
                stroke={selected ? 'var(--embrapa-green-darker)' : REGION_BG[d.region]}
                strokeWidth={selected ? 3 : 2}
              />
              <text
                x={x + CELL_W / 2}
                y={y + 22}
                textAnchor="middle"
                style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, fill: textColor(v) }}
              >
                {d.uf}
              </text>
              <text
                x={x + CELL_W / 2}
                y={y + 40}
                textAnchor="middle"
                style={{ fontFamily: 'var(--font-body)', fontSize: 10.5, fill: textColor(v), opacity: 0.85 }}
              >
                {v ? fmtTile(v) : '—'}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="bmap-legend">
        <span className="caption">{label}</span>
        <div className="bmap-scale">
          {STOPS.map((c, i) => (
            <span
              key={i}
              style={{ background: c, opacity: thresholds[i] ? 1 : 0.35 }}
              // Each bucket says the range it actually covers, matching the
              // choropleth's legend; an empty bucket is dimmed rather than given an
              // invented range.
              title={thresholds[i]
                ? `${fmtTile(thresholds[i].min)} – ${fmtTile(thresholds[i].max)}`
                : 'nenhuma UF nesta faixa'}
            ></span>
          ))}
        </div>
        <span className="caption tnum">
          {fmtTile(min)} – {fmtTile(max)}
        </span>
      </div>
    </div>
  );
}

window.BrazilTileMap = BrazilTileMap;
export default BrazilTileMap;
