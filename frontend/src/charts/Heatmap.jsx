// Heatmap — Plotly year (x) × category (y) color matrix. Same name + props as
// the prototype's SVG Heatmap, so the reused views render <window.Heatmap/>
// unchanged — now with zoom/pan/hover (the point of the Plotly migration).
//   rows: [{ id, label, values: [{ y, v }] }]

import { Plot, baseLayout, ptBrValueTicks, resolveColor, yearAxis } from './_base';

// The design-system heat ramp (--heat-1…--heat-7), resolved to concrete colors
// and mapped onto a Plotly colorscale (normalized stops 0→1).
function heatColorscale() {
  const stops = Array.from({ length: 7 }, (_, i) =>
    resolveColor(`var(--heat-${i + 1})`, '#1D4D7E'),
  );
  return stops.map((c, i) => [i / (stops.length - 1), c]);
}

function Heatmap({ rows = [], valueKey = 'v', valueLabel = '', height }) {
  // x = a SINGLE sorted year axis built from the UNION of every row's years.
  // Building x from rows[0] alone (and z from each row's own array) misaligns
  // columns whenever the rows are ragged — a UF missing an early year would have
  // every cell shifted one column left onto the wrong year label. Indexing each
  // row's values into this shared axis (gaps → null) is correct for sparse
  // per-row coverage (common for trade bancos where a UF lacks early years).
  const yearSet = new Set();
  for (const r of rows) for (const d of r.values || []) yearSet.add(d.y);
  const x = [...yearSet].sort((a, b) => a - b);

  // No rows (e.g. all UFs filtered out) or no year anywhere → empty plot.
  if (!rows.length || !x.length) {
    return <Plot traces={[]} layout={baseLayout()} height={height || 120} />;
  }

  const y = rows.map((r) => r.label);
  const z = rows.map((r) => {
    const byYear = new Map((r.values || []).map((d) => [d.y, d[valueKey] ?? null]));
    return x.map((yr) => (byYear.has(yr) ? byYear.get(yr) : null));
  });

  // MAPA-5: the colorbar used Plotly's default SI tick format ("14B"/"12B"/"8B"),
  // the SAME English-letter mismatch ptBrLinearAxis already fixes on every OTHER
  // value axis in the app ("15G" next to "15 bi" for the same R$ series — FINDING
  // #9) — it just never reached this ONE colorbar. Reuses the identical pt-BR
  // magnitude ladder; falls back to Plotly's own ticks when the data can't
  // support "nice" ones (ptBrValueTicks returns null for that — see _base.jsx).
  const zMax = Math.max(0, ...z.flat().filter((v) => v != null));
  const zTicks = ptBrValueTicks(zMax);

  const traces = [
    {
      type: 'heatmap',
      x,
      y,
      z,
      colorscale: heatColorscale(),
      showscale: true,
      // Sparse/ragged rows set missing cells to null (drawn as gaps). Suppress hover on
      // those gaps so a null cell doesn't pop a tooltip with a blank "%{z:,.2f}" value.
      hoverongaps: false,
      colorbar: {
        title: { text: valueLabel, side: 'right', font: { size: 11 } },
        thickness: 12,
        ...(zTicks ? { tickmode: 'array', tickvals: zTicks.tickvals, ticktext: zTicks.ticktext } : {}),
      },
      hovertemplate: `<b>%{y}</b> · %{x}<br>%{z:,.2f} ${valueLabel}<extra></extra>`,
    },
  ];

  const layout = baseLayout({
    margin: { l: 120, r: 16, t: 8, b: 36 },
    hovermode: 'closest',
    // x = a LINEAR year axis (not category): the years are contiguous integers, so a
    // numeric axis renders the heatmap cells identically (centred on each year, width
    // 1) while letting yearAxis() THIN the labels to fit the width — a category axis
    // pinned all ~39 years and crushed them into "198619871988…" on a wide card
    // (audit AXIS-2). yearAxis = integer ticks, Plotly auto-density by width.
    xaxis: yearAxis(),
    yaxis: { type: 'category', autorange: 'reversed', automargin: true },
  });

  // Fall back to a row-count-aware height when none is supplied.
  return <Plot traces={traces} layout={layout} height={height || 22 + rows.length * 24 + 22} />;
}

window.Heatmap = Heatmap;
export default Heatmap;
