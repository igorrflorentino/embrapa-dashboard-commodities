// Heatmap — Plotly year (x) × category (y) color matrix. Same name + props as
// the prototype's SVG Heatmap, so the reused views render <window.Heatmap/>
// unchanged — now with zoom/pan/hover (the point of the Plotly migration).
//   rows: [{ id, label, values: [{ y, v }] }]

import { Plot, baseLayout, colorbarAnchors, resolveColor, yearAxis } from './_base';

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

  // The colour scale's REAL ends, pinned explicitly onto the trace below. Left to
  // Plotly they are inferred from the data and the legend can only guess at them; set
  // here, the bar's ends and its labels provably describe the same numbers.
  //
  // Labels keep going through the pt-BR magnitude ladder (MAPA-5 / FINDING #9): this
  // colorbar is the one place that used to show Plotly's SI letters, so "14B" sat next
  // to "14 bi" for the same R$ series. colorbarAnchors formats with ptBrMagnitude, and
  // returns null for a degenerate range, leaving Plotly's own ticks.
  const zVals = z.flat().filter((v) => v != null);
  const zMin = zVals.length ? Math.min(...zVals) : 0;
  const zMax = zVals.length ? Math.max(...zVals) : 0;
  const zTicks = colorbarAnchors(zMin, zMax);
  // Row-count-aware height, and whether that leaves the vertical colorbar enough room.
  // Three rows at 24px + chrome is about where a right-side title stops fitting.
  const autoHeight = 22 + rows.length * 24 + 22;
  const shortPlot = !height && rows.length <= 3;

  const traces = [
    {
      type: 'heatmap',
      x,
      y,
      z,
      colorscale: heatColorscale(),
      showscale: true,
      zmin: zMin,
      zmax: zMax,
      // Sparse/ragged rows set missing cells to null (drawn as gaps). Suppress hover on
      // those gaps so a null cell doesn't pop a tooltip with a blank "%{z:,.2f}" value.
      hoverongaps: false,
      // The colorbar spans the PLOT's height, so on a short plot it has nowhere to put a
      // right-side title AND its ticks: with a single row (a one-UF selection) the plot
      // is ~68px and the unit collided with the values into an unreadable smudge.
      // Below the threshold the bar goes HORIZONTAL, under the plot, where width is the
      // one thing a one-row heatmap has plenty of.
      // Both branches declare the SAME keys. Plotly.react leaves an omitted nested
      // attribute at its previous value, so a key present in one branch and absent from
      // the other would survive an orientation flip and place the bar by half-stale
      // geometry.
      colorbar: {
        // Full span in the direction that has room: the height of the plot when
        // vertical, the width of it when horizontal. A stubby bar floating in a wide
        // card reads as a leftover, not as the key to the colours.
        len: 1,
        lenmode: 'fraction',
        thickness: 12,
        thicknessmode: 'pixels',
        // The unit label, placed where it cannot be mistaken for a value.
        //   vertical   → above the bar. Beside it, Plotly rotates the text 90°, which
        //                landed "R$" sideways in the middle of the gradient, between two
        //                tick labels, reading as if it were one of them.
        //   horizontal → 'bottom'. Counter-intuitive, and measured rather than assumed:
        //                it renders the unit just ABOVE the bar (title 72-85px, bar
        //                92-104px), clear of both the year labels above and the tick
        //                labels below. 'top' is measured from the colorbar GROUP, which
        //                on a container-anchored bar stretches up into the plot, so it
        //                drew "R$" over the heatmap band itself at y=10.
        title: {
          text: valueLabel,
          side: shortPlot ? 'bottom' : 'top',
          font: { size: 11 },
        },
        outlinewidth: 0,
        ticks: 'outside',
        ticklen: 4,
        tickfont: { size: 10 },
        ...(zTicks || {}),
        // Horizontal: x/len stay on 'paper' so the bar spans exactly the heatmap band,
        // but y is anchored to the CONTAINER. A paper-relative y is a fraction of the
        // PLOTTING AREA, which on a one-row heatmap is ~16px tall — so y:-0.42 moved the
        // bar 7px, straight into the year labels, and the unit landed on top of "2005".
        // Against the container the placement is the same handful of pixels from the
        // card's bottom edge no matter how short the band above it is.
        ...(shortPlot
          ? {
              orientation: 'h',
              x: 0.5, xanchor: 'center', xref: 'paper',
              y: 0, yanchor: 'bottom', yref: 'container',
            }
          : {
              orientation: 'v',
              x: 1.02, xanchor: 'left', xref: 'paper',
              y: 0.5, yanchor: 'middle', yref: 'paper',
            }),
      },
      hovertemplate: `<b>%{y}</b> · %{x}<br>%{z:,.2f} ${valueLabel}<extra></extra>`,
    },
  ];

  const layout = baseLayout({
    // A horizontal colorbar lives BELOW the plot, so it needs bottom room the
    // vertical one never did.
    // Room for the colorbar in whichever direction it sits: to the right when
    // vertical (bar + tick labels + the unit above it), below when horizontal. Too
    // tight and Plotly clips the labels, which is how a legend stops being one.
    margin: { l: 120, r: shortPlot ? 16 : 92, t: shortPlot ? 8 : 22, b: shortPlot ? 108 : 36 },
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
  // The extra height on a short plot is the horizontal colorbar's strip, not taller
  // cells — the data band keeps its 24px row.
  //
  // The `key` forces a REMOUNT when the orientation flips, and it is load-bearing.
  // Plotly.react reuses the existing `.colorbar` SVG group across an orientation change:
  // gd.data and gd._fullData both end up correct (orientation 'v', x 1.02, len 1) while
  // the drawn group keeps the HORIZONTAL geometry — measured at x=309 w=297 inside a
  // 937px plot, i.e. a bar stranded across the middle of the heatmap. Selecting a UF and
  // then deselecting it walked straight into that. Remounting gives Plotly a clean
  // element, which is the only reliable way to make it lay the bar out again; the flip
  // only happens on a deliberate selection change, so the cost is one re-plot.
  return (
    <Plot
      key={shortPlot ? 'cb-h' : 'cb-v'}
      traces={traces}
      layout={layout}
      height={height || (shortPlot ? autoHeight + 64 : autoHeight)}
    />
  );
}

window.Heatmap = Heatmap;
export default Heatmap;
