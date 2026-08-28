// _base.jsx — shared Plotly theme + lifecycle wrapper for every chart.
//
// Charts build their traces, then render <Plot traces=… layout=… />. The Plot
// component owns the imperative Plotly lifecycle (react/resize/purge) so each
// chart stays declarative. Theme colors come from the design-system CSS vars
// (resolved at runtime via getComputedStyle) so charts match the rest of the UI
// and follow any theme change. Researchers get zoom/pan/hover for free (Plotly).

import { useRef, useEffect, useState } from 'react';
import Plotly from './plotlyBundle';
import { magnitudeParts } from './magnitude.js';

const root = () => document.documentElement;

/** Resolve a CSS custom property to its computed value (with a fallback). */
export function cssVar(name, fallback = '') {
  if (typeof window === 'undefined') return fallback;
  const v = getComputedStyle(root()).getPropertyValue(name);
  return (v && v.trim()) || fallback;
}

/** Resolve a `var(--x)` reference (the registries store colors as `var(--viz-1)`)
 *  to a concrete color Plotly can use. Passes through literal colors. */
export function resolveColor(c, fallback = cssVar('--viz-1', '#1D4D7E')) {
  if (!c) return fallback;
  const m = /var\(\s*(--[\w-]+)\s*\)/.exec(c);
  return m ? cssVar(m[1], fallback) : c;
}

/** The categorical viz palette (--viz-1…--viz-8), resolved. */
export function vizPalette() {
  return Array.from({ length: 8 }, (_, i) => cssVar(`--viz-${i + 1}`, '#1D4D7E'));
}

/** Add an alpha channel to a color (for area fills). Handles #RGB/#RRGGBB and
 *  passes through rgb()/named colors by wrapping unsupported inputs as-is. */
export function withAlpha(color, alpha = 0.12) {
  const c = resolveColor(color);
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(c);
  if (hex) {
    let h = hex[1];
    if (h.length === 3) h = h.split('').map((d) => d + d).join('');
    const n = parseInt(h, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }
  const rgb = /^rgb\((.+)\)$/i.exec(c);
  if (rgb) return `rgba(${rgb[1]}, ${alpha})`;
  return c;
}

/** pt-BR magnitude suffix for a value's order of magnitude, matching the app's
 *  number language (window.autoScaleNum → "bi"/"mi"/"mil"). Plotly's SI `~s`
 *  tickformat renders English/SI letters ("15G"/"3M"/"5k"), which clash with the
 *  "R$ bi"/"R$ mi" labels the rest of the dashboard uses — so a value axis showed
 *  "15G" on one card and "150" (bi) on another for the SAME R$ series (FINDING #9).
 *  This formats a tick value into the SAME pt-BR magnitude words, keeping every
 *  value axis consistent with the labels and with each other. */
export function ptBrMagnitude(v, digits = null) {
  // Shared bi/mi/mil ladder (magnitude.js) — same kernel as window.autoScaleNum, so the
  // value axis and the KPI cards can't drift (FINDING #9 / DEDUP-7).
  const { factor, suffix } = magnitudeParts(v);
  const scaled = v / factor;
  // Up to 1 decimal for readability; drop a trailing ",0". `digits` overrides that
  // default for callers that must keep NEARBY values distinguishable (colorbarAnchors);
  // omitted everywhere else, so the shared ladder is unchanged for every other caller.
  const txt = scaled.toLocaleString('pt-BR', {
    maximumFractionDigits: digits ?? (Math.abs(scaled) < 10 ? 1 : 0),
  });
  return suffix ? `${txt} ${suffix}` : txt;
}

/** A small set of "nice" axis ticks over [0, max], labelled in pt-BR magnitude
 *  words (ptBrMagnitude). Returns { tickvals, ticktext } for a Plotly y-axis so
 *  the value axis reads "15 bi / 10 bi / 5 bi" instead of the SI "15G / 10G / 5G"
 *  (FINDING #9). Falls back to null (let Plotly auto-tick) when max is not a
 *  usable positive number, so loading/empty charts are unaffected. */
export function ptBrValueTicks(max, count = 4) {
  if (!Number.isFinite(max) || max <= 0) return null;
  const raw = max / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const niceNorm = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  const step = niceNorm * mag;
  const tickvals = [];
  for (let v = 0; v <= max + step * 0.5; v += step) tickvals.push(v);
  if (tickvals.length < 2) return null;
  return { tickvals, ticktext: tickvals.map(ptBrMagnitude) };
}

/** Colorbar tick anchors: the LOW end, the midpoint and the HIGH end — always those
 *  three, always at 0%, 50% and 100% of the bar.
 *
 *  A colorbar is a LEGEND, not an axis, and the two want opposite things.
 *  `ptBrValueTicks` picks nice round steps and lets the axis extend past the data,
 *  which is right for an axis and wrong here: over a scale ending at ~134 mi it
 *  emitted 0 / 50 mi / 100 mi, so the labels sat at 0%, 37% and 75% of the bar and
 *  NOTHING marked the top. The reader's first question about a gradient is "what does
 *  the darkest colour mean?", and that was the one value the legend never showed.
 *
 *  Fixed anchors trade round numbers for answerable ones. Labels still go through
 *  ptBrMagnitude, so they read "134 mi" in the same ladder as every other figure.
 *  Returns null for a degenerate range (max <= min), leaving Plotly's own ticks. */
export function colorbarAnchors(min, max) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return null;
  const tickvals = [min, (min + max) / 2, max];
  // A NARROW range collapses all three anchors onto one magnitude label — a measured
  // [5 mi | 5 mi | 5 mi] for [5.000.000, 5.004.000]. Three identical numbers on a
  // gradient assert the scale is flat when it is not, so escalate precision until the
  // labels separate. Beyond 3 decimals the label stops being readable and says less
  // than Plotly's own ticks, so we hand the axis back (null ⇒ Plotly auto-ticks)
  // rather than print a precise-but-unreadable lie. Invariant, swept in
  // _base.colorbar.test.js: the result is null OR three DISTINCT labels — never a
  // repeated one.
  for (const digits of [null, 2, 3]) {
    const ticktext = tickvals.map((v) => ptBrMagnitude(v, digits));
    if (new Set(ticktext).size === tickvals.length) {
      return { tickmode: 'array', tickvals, ticktext };
    }
  }
  return null;
}

/** The value-axis tick props to spread onto ANY chart's y/x value axis, so every
 *  value axis in the app reads pt-BR magnitude words ("15 bi") instead of d3's SI
 *  letters ("15G") — the single contract that kills the "15G vs 15 bi" mismatch
 *  across cards (FINDING #9). Pass the series' max (the largest absolute value the
 *  axis must cover). When that yields nice pt-BR ticks we emit a fixed
 *  tickmode:'array'; otherwise we fall back to Plotly's `~s` so loading/empty/
 *  degenerate axes still tick. Spread the result over the axis object:
 *    yaxis: { title: …, rangemode: 'tozero', ...ptBrLinearAxis(ymax) }
 *  Keeping the SI fallback here (not at each call site) means a future card that
 *  feeds an absolute-magnitude series gets pt-BR ticks automatically. */
export function ptBrLinearAxis(max) {
  const ticks = ptBrValueTicks(max);
  return ticks
    ? { tickmode: 'array', tickvals: ticks.tickvals, ticktext: ticks.ticktext }
    : { tickformat: '~s' };
}

/** The max absolute value across a chart's series, for ptBrLinearAxis. Accepts a
 *  flat number list or rows + a value accessor. Non-finite/negative values are
 *  ignored; returns 0 for empty input (→ ptBrLinearAxis falls back to `~s`). */
export function seriesMax(rows, pick) {
  let m = 0;
  for (const r of rows || []) {
    const v = Number(pick ? pick(r) : r);
    if (Number.isFinite(v) && v > m) m = v;
  }
  return m;
}

/** X-axis config for an ANNUAL (year) series: integer year labels whose COUNT
 *  thins to fit the rendered container width instead of pinning every year.
 *
 *  Why this exists: the previous call sites set `dtick: 'auto'`, which is INVALID
 *  for a linear axis — Plotly coerced it to `dtick: 1` (tickmode 'linear'), forcing
 *  a label on EVERY one of the ~39 years regardless of width. In a half-width
 *  (grid-2) card those 39 labels crushed into an unreadable vertical smear.
 *
 *  Leaving dtick/nticks UNSET restores tickmode 'auto' (the default): Plotly picks
 *  "nice" round years (1990, 2000…) and scales the tick COUNT to the axis pixel
 *  length — fewer ticks on a narrow card, more on a wide one — re-thinning on every
 *  resize. `tickformat: 'd'` keeps the labels integer years. Spread `over` last so
 *  subplot panels can add `showticklabels` / `matches` etc.:
 *    xaxis: yearAxis()                              // single chart
 *    xaxis: yearAxis({ showticklabels: false })     // stacked-panel row */
export function yearAxis(over = {}) {
  return { tickformat: 'd', ...over };
}

/** Base layout shared by all charts — transparent bg, DS fonts/colors, light
 *  grid, tight margins. Pass overrides (axis titles, legend, height handled by
 *  the wrapper div). */
export function baseLayout(over = {}) {
  const ink = cssVar('--pres-gray-700', '#3D3D3D');
  const grid = cssVar('--pres-gray-200', '#ECECEC');
  const family = cssVar('--font-body', "system-ui, -apple-system, sans-serif");
  const axis = {
    gridcolor: grid,
    linecolor: grid,
    zeroline: false,
    tickfont: { size: 11 },
    automargin: true,
  };
  return {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family, size: 12, color: ink },
    margin: { l: 56, r: 16, t: 8, b: 36 },
    hovermode: 'x unified',
    // SOLID hover tooltip — Plotly's per-trace default hoverlabel bgcolor is
    // inconsistent (a 10%-alpha fill leaks through for area lines, a bar gets
    // rgba(0,0,0,0)) so the unified box read as TRANSPARENT and the chart bled
    // through the text, hurting readability (audit HOVER-1). Pin an opaque surface
    // + subtle border + dark ink so EVERY chart's tooltip is legible. `over` can
    // still replace it wholesale.
    hoverlabel: {
      bgcolor: cssVar('--bg-surface', '#ffffff'),
      bordercolor: cssVar('--pres-gray-300', '#CFD4CF'),
      font: { family, size: 12, color: ink },
    },
    showlegend: false,
    colorway: vizPalette(),
    ...over,
    xaxis: { ...axis, ...(over.xaxis || {}) },
    yaxis: { ...axis, ...(over.yaxis || {}) },
  };
}

/** Interaction defaults — pt-BR number locale, slim modebar on hover, pan/zoom
 *  enabled (the whole point of moving to Plotly). */
export const baseConfig = {
  displaylogo: false,
  responsive: true,
  locale: 'pt-BR',
  // Touch devices have no hover, so a hover-only modebar (zoom / pan / reset / download)
  // is unreachable on a phone — the whole point of the Plotly migration. Show it
  // persistently on coarse pointers; keep the slim hover-reveal on desktop.
  displayModeBar:
    typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(pointer: coarse)').matches
      ? true
      : 'hover',
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines'],
};

/** Declarative Plotly host: draws on every render (Plotly.react diffs cheaply),
 *  resizes with its container, purges on unmount. */
export function Plot({ traces, layout, config, height = 240, style, className, onClick }) {
  const ref = useRef(null);
  const [failed, setFailed] = useState(false);

  // Keep the latest onClick in a ref so the once-bound plotly_click listener
  // always calls the CURRENT handler (which closes over the current data),
  // never the stale first-render one — and we avoid re-attaching the Plotly
  // listener whenever onClick/data change.
  // The write lives in an effect (no dep array ⇒ after EVERY render) rather than
  // in the render body, which mutates a ref mid-render (react-hooks/refs). Nothing
  // is lost: the ref is only ever read from a user click, which cannot happen
  // before React has flushed this effect.
  const onClickRef = useRef(onClick);
  useEffect(() => {
    onClickRef.current = onClick;
  });

  // No dep array ON PURPOSE: this effect redraws on every render so Plotly.react
  // diffs against the latest traces/layout/config (see the doc comment above).
  // Listing deps would be redundant with the every-render contract, not a fix.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    try {
      Plotly.react(el, traces || [], layout || baseLayout(), { ...baseConfig, ...config });
      // A good render recovers from a prior failure. This is a setState inside an
      // effect, but NOT the cascading kind the rule targets: it is guarded by
      // `failed`, so it fires at most once per recovery and the very next pass sees
      // `failed === false` and does nothing. It also isn't derived state — it records
      // the outcome of an imperative call into an external system (Plotly), which is
      // exactly what an effect is for. Restructuring to satisfy the rule would mean
      // toggling the overlay outside React, which is worse.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (failed) setFailed(false);
    } catch (err) {
      // A malformed trace/layout must NOT crash the whole view (it would bubble to
      // ViewErrorBoundary and blank the screen). Degrade THIS chart to an inline
      // fallback; the rest of the perspective stays alive and interactive.
      console.error('[chart] Plotly render failed:', err);
      try {
        Plotly.purge(el);
      } catch {
        /* best effort — the element may already be unusable */
      }
      setFailed(true);
    }
  });

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    // Bind once with a stable trampoline that reads the LATEST handler from the
    // ref, so changing onClick/data never leaves a stale closure bound (and we
    // don't re-attach on every render). A no-op when no onClick is set.
    const handler = (e) => { const fn = onClickRef.current; if (fn) fn(e); };
    el.on?.('plotly_click', handler);
    const ro = new ResizeObserver(() => {
      // Plotly.Plots.resize REJECTS A PROMISE when the div is hidden — verified in
      // plotly.js/src/plots/plots.js:
      //
      //     plots.resize = function(gd) {
      //         var p = new Promise(function(resolve, reject) {
      //             if(!gd || Lib.isHidden(gd)) {
      //                 reject(new Error('Resize must be passed a displayed plot div…
      //
      // The synchronous try/catch below cannot see that rejection, so it escapes as an
      // unhandled "Uncaught (in promise)". A ResizeObserver fires precisely when an
      // element collapses — a perspective torn down, a card hidden — so the reject path
      // is reachable in normal use.
      //
      // Two guards, because neither alone is enough:
      //   the isHidden mirror skips the call Plotly would refuse (Lib.isHidden is
      //   `getComputedStyle(gd).display` empty or 'none'), and the .catch closes the
      //   race where the element is hidden BETWEEN this check and Plotly's own.
      if (!el.isConnected) return;
      const display = el.ownerDocument?.defaultView?.getComputedStyle(el)?.display;
      if (!display || display === 'none') return;
      try {
        const done = Plotly.Plots.resize(el);
        if (done && typeof done.catch === 'function') done.catch(() => {});
      } catch {
        /* element detached mid-resize — ignore */
      }
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      el.removeListener?.('plotly_click', handler);
      Plotly.purge(el);
    };
     
  }, []);

  return (
    <div className={className} style={{ position: 'relative', width: '100%', height, ...style }}>
      <div ref={ref} style={{ width: '100%', height: '100%' }} />
      {failed && (
        <div
          role="status"
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            textAlign: 'center',
            padding: '0 12px',
          }}
        >
          <span className="caption" style={{ color: 'var(--fg-3)' }}>
            Não foi possível renderizar este gráfico.
          </span>
        </div>
      )}
    </div>
  );
}
