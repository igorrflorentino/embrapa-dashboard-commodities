// Heatmap.test.jsx — column alignment for RAGGED per-row series. The matrix x
// axis must be the UNION of every row's years (sorted), and each row's values
// indexed into that shared axis with null for gaps. Building x from rows[0] alone
// shifted a sparse row's cells onto the wrong year. plotlyBundle is mocked so we
// capture the (x, y, z) trace Heatmap hands to Plot.

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

const { reactState } = vi.hoisted(() => ({ reactState: { lastTraces: null } }));

vi.mock('./plotlyBundle', () => ({
  default: {
    react: (_el, traces) => { reactState.lastTraces = traces; },
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

afterEach(() => { cleanup(); reactState.lastTraces = null; });

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
    expect(cb.y).toBeLessThan(0);        // below the plot, not beside it
  });

  it('stays vertical once the plot is tall enough to hold it', () => {
    render(<Heatmap rows={manyRows} valueKey="v" valueLabel="R$" />);
    expect(trace().colorbar.orientation).toBeUndefined();  // Plotly's vertical default
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
    expect(trace().colorbar.orientation).toBeUndefined();
  });
});
