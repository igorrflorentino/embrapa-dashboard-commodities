// _base.test.jsx — the Plot wrapper's error boundary. A malformed trace must
// degrade to an inline fallback for THAT chart, not throw out of the effect and
// blank the whole perspective (ViewErrorBoundary). plotlyBundle is mocked so we
// drive Plotly.react to succeed or throw on demand; ResizeObserver is stubbed
// (jsdom has none).

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

// vi.hoisted so the mock factory can reach this mutable impl (vi.mock is hoisted
// above imports). Each test swaps reactState.impl to choose success/throw.
const { reactState } = vi.hoisted(() => ({ reactState: { impl: () => {} } }));
// Plots.resize is recorded and its return value is swappable, so the ResizeObserver
// guard (and the rejection handling) can be driven deliberately.
const { resizeState } = vi.hoisted(() => ({
  resizeState: { calls: [], ret: () => undefined },
}));

// Stand-in for Plotly's graph-div event API: real Plotly augments the element
// with .on/.removeListener/.emit. The default impl wires a tiny listener
// registry onto the element so click-rebinding can be exercised; tests that
// only care about the error boundary swap reactState.impl to a no-op/throw.
vi.mock('./plotlyBundle', () => ({
  default: {
    react: (...args) => reactState.impl(...args),
    purge: () => {},
    Plots: {
      resize: (el) => { resizeState.calls.push(el); return resizeState.ret(); },
    },
  },
}));

// Equip an element with the minimal Plotly event surface used by Plot.
function wirePlotlyEvents(el) {
  if (el.__listeners) return; // idempotent across re-renders
  el.__listeners = {};
  el.on = (evt, fn) => { (el.__listeners[evt] ||= []).push(fn); };
  el.removeListener = (evt, fn) => {
    el.__listeners[evt] = (el.__listeners[evt] || []).filter((f) => f !== fn);
  };
  el.__emit = (evt, payload) => (el.__listeners[evt] || []).forEach((f) => f(payload));
}

import { Plot, baseLayout, ptBrLinearAxis, ptBrMagnitude, ptBrValueTicks, seriesMax, yearAxis } from './_base.jsx';

beforeAll(() => {
  // Capture the callback so a resize can be SIMULATED — jsdom has no layout, so the
  // real observer would never fire and the guard under test would never run.
  globalThis.__roCallbacks = [];
  globalThis.ResizeObserver = class {
    constructor(cb) { globalThis.__roCallbacks.push(cb); }
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => cleanup());

const FALLBACK = /Não foi possível renderizar este gráfico/;

describe('Plot error boundary', () => {
  it('renders the chart host and no fallback when Plotly succeeds', () => {
    const ok = vi.fn();
    reactState.impl = ok;

    render(<Plot traces={[{ x: [1, 2], y: [3, 4] }]} />);

    expect(ok).toHaveBeenCalled();
    expect(screen.queryByText(FALLBACK)).toBeNull();
  });

  it('shows an inline fallback when Plotly.react throws (the view survives)', async () => {
    reactState.impl = () => {
      throw new Error('malformed trace');
    };

    render(<Plot traces={[{ bogus: true }]} />);

    // The throw is caught in the effect → fallback rendered, no error propagates.
    expect(await screen.findByText(FALLBACK)).toBeTruthy();
  });
});

describe('Plot click handler rebinding', () => {
  // Regression: the plotly_click listener is bound once on mount. It must call
  // the CURRENT onClick (which closes over the current data) — not the stale
  // first-render one — when the parent re-renders with a new handler/data.
  it('invokes the latest onClick after the prop changes, not the first one', () => {
    reactState.impl = (el) => wirePlotlyEvents(el);

    const first = vi.fn();
    const second = vi.fn();
    const { container, rerender } = render(
      <Plot traces={[{ x: [1], y: [1] }]} onClick={first} />,
    );
    // The chart host is the inner div the ref attaches to — it's the element
    // Plotly.react was called with, so it carries the wired .on/.emit surface.
    const host = [...container.querySelectorAll('div')].find((d) => typeof d.__emit === 'function');
    expect(host, 'chart host should have the Plotly event surface wired').toBeTruthy();

    host.__emit('plotly_click', { points: [{ x: 1 }] });
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();

    // Re-render with a different handler (as a parent would when data changes).
    rerender(<Plot traces={[{ x: [2], y: [2] }]} onClick={second} />);
    host.__emit('plotly_click', { points: [{ x: 2 }] });

    // The latest handler fires; the stale one is NOT called again.
    expect(second).toHaveBeenCalledTimes(1);
    expect(first).toHaveBeenCalledTimes(1);
  });
});

describe('ptBrMagnitude / ptBrValueTicks (FINDING #9)', () => {
  // The value axis must read pt-BR magnitude words ("15 bi") to match the
  // dashboard's "R$ bi/mi/mil" labels, never the SI letters ("15G") d3-format's
  // `~s` emits — that mismatch made the SAME R$ series read "15G" on one card and
  // "150"(bi) on another.
  it('labels magnitudes in pt-BR words, not SI letters', () => {
    expect(ptBrMagnitude(15e9)).toBe('15 bi');
    expect(ptBrMagnitude(3.4e6)).toBe('3,4 mi');
    expect(ptBrMagnitude(5000)).toBe('5 mil');
    expect(ptBrMagnitude(150)).toBe('150');
    // No SI letters leak through.
    expect(ptBrMagnitude(15e9)).not.toMatch(/[GMk]/);
  });

  it('builds nice ascending ticks with pt-BR labels over [0, max]', () => {
    const t = ptBrValueTicks(15e9);
    expect(t.tickvals[0]).toBe(0);
    // Strictly ascending.
    for (let i = 1; i < t.tickvals.length; i++) {
      expect(t.tickvals[i]).toBeGreaterThan(t.tickvals[i - 1]);
    }
    // Top tick covers the data max, labelled in "bi".
    expect(t.tickvals[t.tickvals.length - 1]).toBeGreaterThanOrEqual(15e9);
    expect(t.ticktext.some((s) => s.includes('bi'))).toBe(true);
    expect(t.ticktext.join(' ')).not.toMatch(/[GMk]/);
  });

  it('returns null for a non-positive / unusable max (let Plotly auto-tick)', () => {
    expect(ptBrValueTicks(0)).toBe(null);
    expect(ptBrValueTicks(-5)).toBe(null);
    expect(ptBrValueTicks(NaN)).toBe(null);
  });
});

describe('ptBrLinearAxis / seriesMax (FINDING #9 — shared across charts)', () => {
  // The single value-axis contract every chart spreads. For an absolute-magnitude
  // series it emits FIXED pt-BR array ticks (no SI letter can leak); for an
  // unusable max it falls back to Plotly's `~s` so loading/empty axes still tick.
  it('emits pt-BR array ticks (never `~s`) for an absolute-magnitude max', () => {
    const ax = ptBrLinearAxis(15e9);
    expect(ax.tickmode).toBe('array');
    expect(ax.tickformat).toBeUndefined(); // no SI fallback when array ticks apply
    expect(ax.ticktext.some((s) => s.includes('bi'))).toBe(true);
    expect(ax.ticktext.join(' ')).not.toMatch(/[GMk]/);
  });

  it('falls back to the SI `~s` tickformat for a non-positive / unusable max', () => {
    for (const bad of [0, -5, NaN, undefined]) {
      const ax = ptBrLinearAxis(bad);
      expect(ax).toEqual({ tickformat: '~s' });
    }
  });

  it('seriesMax reads the max absolute value from numbers or rows', () => {
    expect(seriesMax([1, 9, 4])).toBe(9);
    expect(seriesMax([{ v: 2 }, { v: 7 }, { v: 3 }], (d) => d.v)).toBe(7);
    // Non-finite / negative are ignored; empty → 0 (→ ptBrLinearAxis falls back).
    expect(seriesMax([{ v: NaN }, { v: -5 }], (d) => d.v)).toBe(0);
    expect(seriesMax([])).toBe(0);
    expect(seriesMax(null)).toBe(0);
  });
});

describe('yearAxis (width-adaptive year x-axis — audit AXIS-1)', () => {
  // The shared annual x-axis contract. It must NOT pin a tick on every year: it
  // leaves dtick/nticks UNSET so Plotly's tickmode 'auto' scales the tick count to
  // the rendered width (the old `dtick:'auto'` coerced to dtick:1 → all ~39 years
  // crushed in a narrow card). Integer year labels via tickformat 'd'.
  it('emits integer year ticks with NO dtick/nticks (lets Plotly thin by width)', () => {
    const ax = yearAxis();
    expect(ax.tickformat).toBe('d');
    expect(ax.dtick).toBeUndefined();
    expect(ax.nticks).toBeUndefined();
    expect(ax.tickmode).toBeUndefined(); // unset → Plotly defaults to 'auto'
  });

  it('spreads caller overrides last (subplot panels add showticklabels / matches)', () => {
    const ax = yearAxis({ showticklabels: false, matches: 'x' });
    expect(ax.tickformat).toBe('d');
    expect(ax.showticklabels).toBe(false);
    expect(ax.matches).toBe('x');
    expect(ax.dtick).toBeUndefined();
  });
});

describe('baseLayout hover tooltip (audit HOVER-1 — solid, never transparent)', () => {
  // Every chart's tooltip must have an OPAQUE background so the chart never bleeds
  // through the text. jsdom has no CSS vars, so cssVar falls back to the literal
  // '#ffffff' — the assertion proves the contract regardless of theme resolution.
  it('pins an opaque hoverlabel bgcolor + border + font', () => {
    const lay = baseLayout();
    expect(lay.hoverlabel).toBeDefined();
    expect(lay.hoverlabel.bgcolor).toBe('#ffffff'); // cssVar fallback in jsdom
    expect(lay.hoverlabel.bgcolor).not.toMatch(/rgba?\([^)]*,\s*0\s*\)/); // not transparent
    expect(lay.hoverlabel.bordercolor).toBeTruthy();
    expect(lay.hoverlabel.font).toBeDefined();
  });

  it('lets a caller override the whole layout hoverlabel via `over`', () => {
    const lay = baseLayout({ hoverlabel: { bgcolor: '#222' } });
    expect(lay.hoverlabel.bgcolor).toBe('#222');
  });
});

// ── The ResizeObserver must not fire a resize Plotly will refuse ─────────────
//
// Plotly.Plots.resize REJECTS A PROMISE when the div is hidden — from
// plotly.js/src/plots/plots.js:
//
//     plots.resize = function(gd) {
//         var p = new Promise(function(resolve, reject) {
//             if(!gd || Lib.isHidden(gd)) {
//                 reject(new Error('Resize must be passed a displayed plot div element.'));
//
// A synchronous try/catch around the call cannot see that rejection, so it escapes as
// an "Uncaught (in promise)". A ResizeObserver fires exactly when an element collapses
// — a perspective torn down, a card hidden — so the reject path is reachable in normal
// use, and the console it pollutes is the cheapest regression detector the project has.

describe('Plot — the resize guard', () => {
  const fireResize = () => globalThis.__roCallbacks.forEach((cb) => cb());

  beforeEach(() => {
    globalThis.__roCallbacks = [];
    resizeState.calls = [];
    resizeState.ret = () => undefined;
    reactState.impl = (el) => wirePlotlyEvents(el);
  });

  it('resizes a displayed plot', () => {
    render(<Plot traces={[]} layout={{}} />);
    fireResize();
    expect(resizeState.calls).toHaveLength(1);
  });

  it('skips a HIDDEN plot — mirroring Plotly\'s own Lib.isHidden', () => {
    // Lib.isHidden is `getComputedStyle(gd).display` empty or 'none'; skipping exactly
    // that means never issuing the call Plotly is going to refuse.
    // Set it on the OBSERVED div itself: jsdom's getComputedStyle does not cascade an
    // ancestor's display, and the guard reads the same element Plotly would.
    // firstChild.firstChild is the REF'D div. `querySelector('div > div')` matches the
    // outer wrapper first (container is itself a div), so it hid the wrong element.
    const { container } = render(<Plot traces={[]} layout={{}} />);
    container.firstChild.firstChild.style.display = 'none';
    fireResize();
    expect(resizeState.calls).toHaveLength(0);
  });

  it('skips a DISCONNECTED plot', () => {
    const { container, unmount } = render(<Plot traces={[]} layout={{}} />);
    const el = container.firstChild.firstChild;
    unmount();
    expect(el.isConnected).toBe(false);
    fireResize();
    expect(resizeState.calls).toHaveLength(0);
  });

  it('attaches a rejection handler, so a refused resize cannot escape', () => {
    // THE point of the fix: the pre-existing try/catch is synchronous and can never
    // catch a rejected promise. Without a .catch the refusal surfaces as an unhandled
    // rejection in every browser console.
    const caught = vi.fn();
    resizeState.ret = () => ({ catch: caught });
    render(<Plot traces={[]} layout={{}} />);
    fireResize();
    expect(caught).toHaveBeenCalled();
  });

  it('survives a resize implementation that throws synchronously', () => {
    resizeState.ret = () => { throw new Error('detached mid-resize'); };
    render(<Plot traces={[]} layout={{}} />);
    expect(() => fireResize()).not.toThrow();
  });
});
