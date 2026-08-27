// Heatmap.test.jsx — column alignment for RAGGED per-row series. The matrix x
// axis must be the UNION of every row's years (sorted), and each row's values
// indexed into that shared axis with null for gaps. Building x from rows[0] alone
// shifted a sparse row's cells onto the wrong year. plotlyBundle is mocked so we
// capture the (x, y, z) trace Heatmap hands to Plot.

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

const { reactState } = vi.hoisted(() => ({ reactState: { lastTraces: null, els: [] } }));

vi.mock('./plotlyBundle', () => ({
  default: {
    // `el` is recorded too: an orientation flip MUST land on a fresh element (see the
    // remount test below), and the element identity is the only honest evidence of that.
    react: (el, traces) => { reactState.lastTraces = traces; reactState.els.push(el); },
    purge: () => {},
    Plots: { resize: () => {} },
  },
}));

import Heatmap from './Heatmap.jsx';

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => { cleanup(); reactState.lastTraces = null; reactState.els = []; });

const trace = () => reactState.lastTraces?.[0];

describe('Heatmap ragged-row column alignment', () => {
  it('builds x from the UNION of years and indexes each row, gaps → null', () => {
    // Row B is missing 2019 → its 5 must land under 2020, NOT shift onto 2019.
    render(
      <Heatmap
        rows={[
          { id: 'PA', label: 'PA', values: [{ y: 2019, v: 1 }, { y: 2020, v: 2 }] },
          { id: 'SP', label: 'SP', values: [{ y: 2020, v: 5 }] },
        ]}
      />,
    );
    const t = trace();
    expect(t.x).toEqual([2019, 2020]);
    expect(t.y).toEqual(['PA', 'SP']);
    expect(t.z[0]).toEqual([1, 2]);
    expect(t.z[1]).toEqual([null, 5]); // 2019 gap → null; 5 stays under 2020
  });

  it('sorts the union axis chronologically regardless of row/value order', () => {
    render(
      <Heatmap
        rows={[
          { id: 'A', label: 'A', values: [{ y: 2021, v: 9 }, { y: 2019, v: 7 }] },
          { id: 'B', label: 'B', values: [{ y: 2020, v: 8 }] },
        ]}
      />,
    );
    const t = trace();
    expect(t.x).toEqual([2019, 2020, 2021]);
    expect(t.z[0]).toEqual([7, null, 9]); // A: 2019 & 2021 present, 2020 gap
    expect(t.z[1]).toEqual([null, 8, null]); // B: only 2020
  });

  it('renders an empty plot (no trace) when no row carries any year', () => {
    render(<Heatmap rows={[{ id: 'A', label: 'A', values: [] }]} />);
    expect(reactState.lastTraces).toEqual([]);
  });
});

// ── The colorbar has to fit the plot it lives in ─────────────────────────────
//
// The colorbar spans the PLOT's height. With one row the plot is ~68px, and a
// right-side unit title plus tick labels collided into an unreadable smudge — exactly
// what a single-UF selection produces, which is the most common narrowing there is.

describe('Heatmap — the colorbar adapts to a short plot', () => {
  const oneRow = [{ id: 'PA', label: 'PA · Pará', values: [{ y: 2019, v: 1 }, { y: 2020, v: 2 }] }];
  const manyRows = Array.from({ length: 8 }, (_, i) => ({
    id: `U${i}`, label: `U${i}`, values: [{ y: 2019, v: i + 1 }],
  }));

  it('goes HORIZONTAL when there are few rows — width is what a short plot has', () => {
    render(<Heatmap rows={oneRow} valueKey="v" valueLabel="R$" />);
    const cb = trace().colorbar;
    expect(cb.orientation).toBe('h');
    // Pinned to the CONTAINER's bottom, not to the plotting area: on a one-row heatmap
    // that area is ~16px tall, so a paper-relative offset moved the bar a few pixels and
    // dropped the unit onto the year labels.
    expect(cb.yref).toBe('container');
    expect(cb.yanchor).toBe('bottom');
  });

  it('stays vertical once the plot is tall enough to hold it', () => {
    render(<Heatmap rows={manyRows} valueKey="v" valueLabel="R$" />);
    // Declared EXPLICITLY, not left to Plotly's default: react() keeps an omitted
    // nested attribute at its previous value, so a key set in one branch and missing
    // from the other survives an orientation flip and places the bar half-stale.
    expect(trace().colorbar.orientation).toBe('v');
  });

  it('declares the same key set in both orientations', () => {
    render(<Heatmap rows={manyRows} valueKey="v" valueLabel="R$" />);
    const tall = Object.keys(trace().colorbar).sort();
    cleanup();
    render(<Heatmap rows={oneRow} valueKey="v" valueLabel="R$" />);
    expect(Object.keys(trace().colorbar).sort()).toEqual(tall);
  });

  it('spans the full extent in whichever direction has room', () => {
    render(<Heatmap rows={oneRow} valueKey="v" valueLabel="R$" />);
    expect(trace().colorbar.len).toBe(1);          // full plot WIDTH when horizontal
    cleanup();
    render(<Heatmap rows={manyRows} valueKey="v" valueLabel="R$" />);
    expect(trace().colorbar.len).toBe(1);          // full plot HEIGHT when vertical
  });

  it('keeps the pt-BR tick ladder in BOTH orientations', () => {
    // The whole point of the custom ticks is avoiding Plotly's English "14B" next to
    // the app's "14 bi"; an orientation switch must not quietly drop them.
    render(<Heatmap rows={oneRow} valueKey="v" valueLabel="R$" />);
    const short = trace().colorbar;
    cleanup();
    render(<Heatmap rows={manyRows} valueKey="v" valueLabel="R$" />);
    const tall = trace().colorbar;
    expect(short.tickmode).toBe(tall.tickmode);
  });

  it('does not touch the layout when the caller fixes the height itself', () => {
    // An explicit height means the caller sized the plot on purpose; second-guessing it
    // would move someone else's chart.
    render(<Heatmap rows={oneRow} valueKey="v" valueLabel="R$" height={400} />);
    expect(trace().colorbar.orientation).toBe('v');
  });
});

// ── Crossing the orientation threshold must REMOUNT the plot ─────────────────
//
// Plotly.react reuses the existing `.colorbar` SVG group across an orientation change.
// gd.data AND gd._fullData both end up correct (orientation 'v', x 1.02, len 1) while
// the DRAWN group keeps the horizontal geometry — measured live at x=309 w=297 inside a
// 937px plot, a bar stranded across the middle of the heatmap. Selecting a UF and then
// deselecting it walked into exactly that, which is how it was reported.
//
// The fix is a React `key` on <Plot>, so the flip gives Plotly a clean element. The
// element identity is the only honest evidence, so that is what this asserts.

describe('Heatmap — an orientation flip gets a fresh plot element', () => {
  const rowsFor = (n) => Array.from({ length: n }, (_, i) => ({
    id: `U${i}`, label: `U${i}`, values: [{ y: 2019, v: i + 1 }, { y: 2020, v: i + 2 }],
  }));

  it('remounts when going from many rows to one, and back', () => {
    const { rerender } = render(<Heatmap rows={rowsFor(8)} valueKey="v" valueLabel="R$" />);
    const tall = reactState.els.at(-1);

    rerender(<Heatmap rows={rowsFor(1)} valueKey="v" valueLabel="R$" />);
    const short = reactState.els.at(-1);
    expect(short).not.toBe(tall);          // horizontal bar drawn on a clean element

    rerender(<Heatmap rows={rowsFor(8)} valueKey="v" valueLabel="R$" />);
    const backToTall = reactState.els.at(-1);
    // The return trip is the one that was broken: without a remount the vertical bar
    // inherited the horizontal geometry and landed mid-plot.
    expect(backToTall).not.toBe(short);
  });

  it('does NOT remount for a row change that stays on the same side of the threshold', () => {
    // A remount is a full re-plot; paying for it on every ordinary data change would
    // trade one bug for a jank.
    const { rerender } = render(<Heatmap rows={rowsFor(8)} valueKey="v" valueLabel="R$" />);
    const first = reactState.els.at(-1);
    rerender(<Heatmap rows={rowsFor(12)} valueKey="v" valueLabel="R$" />);
    expect(reactState.els.at(-1)).toBe(first);
  });
});

// ── The legend must answer "what does the darkest colour mean?" ──────────────
//
// The old ticks were nice ROUND values over the data range, which is right for an axis
// and wrong for a legend: on a scale ending at ~134 mi they emitted 0 / 50 mi / 100 mi,
// landing at 0%, 37% and 75% of the bar with NOTHING marking the top — the one value a
// reader most wants from a gradient.

describe('Heatmap — colorbar anchors', () => {
  const rows = [{
    id: 'PA', label: 'PA',
    values: [{ y: 2019, v: 20e6 }, { y: 2020, v: 134e6 }, { y: 2021, v: 60e6 }],
  }];

  it('anchors at the low end, the midpoint and the high end — always those three', () => {
    render(<Heatmap rows={rows} valueKey="v" valueLabel="R$" />);
    const cb = trace().colorbar;
    expect(cb.tickvals).toEqual([20e6, 77e6, 134e6]);
    // Labels stay on the pt-BR ladder, so the legend and the KPI cards read alike.
    expect(cb.ticktext).toEqual(['20 mi', '77 mi', '134 mi']);
  });

  it('pins zmin/zmax so the bar ENDS and its labels describe the same numbers', () => {
    render(<Heatmap rows={rows} valueKey="v" valueLabel="R$" />);
    const t = trace();
    expect(t.zmin).toBe(20e6);
    expect(t.zmax).toBe(134e6);
    expect(t.colorbar.tickvals[0]).toBe(t.zmin);
    expect(t.colorbar.tickvals.at(-1)).toBe(t.zmax);
  });

  it('places the unit where it cannot be read as a value, per orientation', () => {
    // Vertical: above the bar. Beside it, Plotly rotates the title 90° and "R$" landed
    // sideways in the gradient, between two tick labels, looking like one of them.
    const tall = Array.from({ length: 8 }, (_, i) => ({
      id: `U${i}`, label: `U${i}`, values: [{ y: 2019, v: i + 1 }],
    }));
    render(<Heatmap rows={tall} valueKey="v" valueLabel="R$" />);
    expect(trace().colorbar.title).toEqual({ text: 'R$', side: 'top', font: { size: 11 } });
    cleanup();
    // Horizontal: 'bottom', which measurement (not intuition) shows renders the unit
    // just above the bar, clear of the year labels and the tick labels. 'top' is
    // measured from the colorbar GROUP, which on a container-anchored bar stretches up
    // into the plot — it drew "R$" over the heatmap band itself.
    render(<Heatmap rows={rows} valueKey="v" valueLabel="R$" />);
    expect(trace().colorbar.title.side).toBe('bottom');
  });

  it('falls back to Plotly ticks on a degenerate (single-value) scale', () => {
    // Every cell equal ⇒ there is no range to anchor; inventing three identical labels
    // would dress a non-existent gradient up as a scale.
    render(<Heatmap rows={[{ id: 'X', label: 'X', values: [{ y: 2019, v: 5 }, { y: 2020, v: 5 }] }]}
                    valueKey="v" valueLabel="R$" />);
    expect(trace().colorbar.tickvals).toBeUndefined();
  });
});
