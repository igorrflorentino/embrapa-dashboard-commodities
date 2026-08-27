// MonthYearHeatmap — Plotly heatmap of 12 months (x) × years (y). Same name +
// props as the prototype's SVG version, so the reused views render
// <window.MonthYearHeatmap/> unchanged — now with zoom/pan/hover.
//   matrix: { [year]: number[12] }

import { Plot, baseLayout, colorbarAnchors, cssVar, resolveColor } from './_base';

// Default month labels if the global isn't set (matches the prototype's pt-BR).
const FALLBACK_MONTHS = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

function MonthYearHeatmap({ matrix = {}, years = [], unit = '', height, formatValue = null }) {
  const months = (typeof window !== 'undefined' && window.MONTH_LABELS) || FALLBACK_MONTHS;
  // Rows sorted descending so the most recent year sits at the top (as the SVG).
  const rows = years.slice().sort((a, b) => b - a);

  // Guard empty/degenerate input — render an empty Plot rather than throwing.
  if (!rows.length) {
    return <Plot traces={[]} layout={baseLayout()} height={height || 240} />;
  }

  // z[yearIdx] = matrix[year] (one row of 12 monthly values per year).
  const z = rows.map((y) => matrix[y] || []);

  // Per-cell hover text via a caller-supplied formatter so the magnitude shows:
  // the serializer pre-scales monthly values to millions, so the raw "%{z}" with a
  // bare unit would read e.g. 2.07 instead of "2,07 mi US$". Default = value+unit.
  const fmtVal = formatValue || ((v) =>
    `${(Number(v) || 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`);
  const customdata = z.map((row) => row.map(fmtVal));

  // Heat ramp from the design-system --heat-1…--heat-7 stops, resolved for Plotly.
  const stops = Array.from({ length: 7 }, (_, i) => resolveColor(`var(--heat-${i + 1})`));
  const colorscale = stops.map((c, i) => [i / (stops.length - 1), c]);

  // Same legend treatment as the geography heatmap — this one had the two defects that
  // one was reported for: the unit rotated 90° into the middle of the gradient
  // (side:'right'), and no anchors, so the ends of the scale were never labelled and the
  // ticks fell back to Plotly's English SI letters ("14B" beside the app's "14 bi").
  const zFlat = z.flat().filter((v) => v != null && Number.isFinite(v));
  const zMin = zFlat.length ? Math.min(...zFlat) : 0;
  const zMax = zFlat.length ? Math.max(...zFlat) : 0;
  const zTicks = colorbarAnchors(zMin, zMax);

  const traces = [
    {
      type: 'heatmap',
      x: months,
      y: rows,
      z,
      colorscale,
      customdata,
      showscale: true,
      zmin: zMin,
      zmax: zMax,
      colorbar: {
        len: 1,
        lenmode: 'fraction',
        thickness: 12,
        thicknessmode: 'pixels',
        title: { text: unit, side: 'top', font: { size: 11 } },
        outlinewidth: 0,
        ticks: 'outside',
        ticklen: 4,
        tickfont: { size: 10 },
        ...(zTicks || {}),
      },
      hovertemplate: '%{x}/%{y}: %{customdata}<extra></extra>',
      xgap: 1,
      ygap: 3,
    },
  ];

  const layout = baseLayout({
    // Right margin holds the bar, its tick labels and the unit above them.
    margin: { l: 56, r: 92, t: 30, b: 28 },
    hovermode: 'closest',
    xaxis: { side: 'top', type: 'category', fixedrange: true },
    yaxis: {
      title: { text: 'Ano', font: { size: 11 }, standoff: 8 },
      type: 'category',
      autorange: 'reversed', // keep descending order top→bottom (rows already sorted desc)
      gridcolor: cssVar('--pres-gray-200', '#ECECEC'),
    },
  });

  return <Plot traces={traces} layout={layout} height={height || 240} />;
}

window.MonthYearHeatmap = MonthYearHeatmap;
export default MonthYearHeatmap;
