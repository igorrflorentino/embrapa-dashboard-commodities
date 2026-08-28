// BrazilChoropleth — the paint path. Guards the first-load bug where the map stayed
// grey until the researcher changed a metric.
//
// maplibre needs WebGL, which jsdom has not, so the component would degrade to
// "Mapa indisponível" here. These tests substitute a FAKE map that reproduces the
// ORDERING that made the bug real: the API data lands BEFORE maplibre finishes loading,
// so the layer the paint effect needs does not exist yet when the data arrives.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, waitFor } from '@testing-library/react';

const DATA = [
  { uf: 'PA', name: 'Pará', value: 2907738239 },
  { uf: 'MT', name: 'Mato Grosso', value: 1200000000 },
];

let fakeMap;
let BrazilChoropleth;
let calls;      // ordered record of maplibre entry points the component touched
let workerUrl;

// Stand-in for maplibre's Map. 'load' is fired MANUALLY by each test so the ordering
// against the data effect is explicit; 'idle' fires on a later tick, as maplibre's does
// once the style has settled.
class FakeMap {
  constructor({ styleReady = true } = {}) {
    this.paintProps = {};
    this.layers = new Set();
    this.styleReady = styleReady;
    this.loadHandler = null;
    this.idleHandlers = 0;
    this.touchZoomRotate = { disableRotation() {} };
    this.scrollZoom = { disable() {} };
    this.filters = {};
  }
  isStyleLoaded() {
    return this.styleReady;
  }
  getLayer(id) {
    return this.layers.has(id) ? { id } : undefined;
  }
  setPaintProperty(layer, prop, value) {
    this.paintProps[`${layer}.${prop}`] = value;
  }
  setFilter(layer, filter) {
    this.filters[layer] = filter;
  }
  fitBounds() {}
  get fill() {
    return this.paintProps['uf-fill.fill-color'];
  }
  addSource() {}
  addLayer(spec) {
    this.layers.add(spec.id);
    if (spec.paint) this.paintProps[`${spec.id}.fill-color`] = spec.paint['fill-color'];
  }
  on(evt, a, b) {
    if (evt === 'load') this.loadHandler = typeof a === 'function' ? a : b;
  }
  once(evt, fn) {
    if (evt !== 'idle') return;
    this.idleHandlers += 1;
    setTimeout(() => {
      this.styleReady = true; // the style finished settling
      fn();
    }, 0);
  }
  fireLoad() {
    return act(async () => {
      this.loadHandler();
    });
  }
  addControl() {}
  getCanvas() {
    return { style: {} };
  }
  remove() {}
}

const noop = () => {};
const stubPopup = () => ({
  setLngLat() { return this; },
  setHTML() { return this; },
  addTo() { return this; },
  remove: noop,
});

beforeEach(async () => {
  vi.resetModules();
  calls = [];
  workerUrl = undefined;
  // The real worker is a 470 kB bundle; under jsdom we only need the URL string.
  vi.doMock('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url', () => ({
    default: '/assets/maplibre-gl-worker.js',
  }));
  // NAMED exports, no `default` — this mirrors maplibre 5+, which is pure ESM with no
  // default export. Mocking a `default` here would let a component that reads
  // `(await import(…)).default` pass the suite while breaking against the real library.
  vi.doMock('maplibre-gl', () => ({
    // Plain functions so `new maplibregl.Map(...)` constructs; returning an object from a
    // constructor hands back that object.
    Map: function Map() {
      calls.push('Map');
      return fakeMap;
    },
    Popup: function Popup() {
      return stubPopup();
    },
    NavigationControl: function NavigationControl() {},
    setWorkerUrl: (url) => {
      calls.push('setWorkerUrl');
      workerUrl = url;
    },
  }));
  ({ BrazilChoropleth } = await import('./BrazilChoropleth.jsx'));
});

afterEach(() => {
  cleanup();
  vi.doUnmock('maplibre-gl');
  vi.doUnmock('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url');
});

// maplibre is imported dynamically, so the map only exists a few microtasks in.
async function waitForMapInit() {
  await waitFor(() => expect(fakeMap.loadHandler).toBeTypeOf('function'));
}

describe('BrazilChoropleth — first paint', () => {
  it('colours the map when the data arrives before maplibre finishes loading', async () => {
    // THE BUG, in its real order: the API resolves first, so the paint effect runs while
    // 'uf-fill' does not exist yet and used to return silently — permanently. Then the
    // load handler painted from its own closure, frozen at the FIRST render, when data
    // was still empty ⇒ a flat no-data grey. Nothing re-ran paint afterwards, so the map
    // stayed grey until the researcher changed a metric, which re-fired the effect with
    // everything finally in place. That workaround was the only reason it ever coloured.
    fakeMap = new FakeMap();
    const { rerender } = render(<BrazilChoropleth data={[]} valueKey="value" label="R$" />);
    await waitForMapInit();

    rerender(<BrazilChoropleth data={DATA} valueKey="value" label="R$" />);
    expect(fakeMap.fill).toBeUndefined(); // no layer yet — nothing could have painted

    await fakeMap.fireLoad();

    await waitFor(() => {
      const fill = fakeMap.fill;
      expect(Array.isArray(fill)).toBe(true); // a data-driven `match`, not a flat colour
      expect(fill[0]).toBe('match');
      expect(fill).toContain('PA'); // …built from the CURRENT data, not the empty first render
    });
  });

  it('retries instead of giving up when the style is not ready yet', async () => {
    // The other half of the same bug: right after addSource/addLayer the style can still
    // be settling, so isStyleLoaded() is briefly false. Bailing on that made the miss
    // permanent; deferring to the map's 'idle' event lets it self-heal.
    fakeMap = new FakeMap({ styleReady: false });
    render(<BrazilChoropleth data={DATA} valueKey="value" label="R$" />);
    await waitForMapInit();
    await fakeMap.fireLoad();

    await waitFor(() => expect(Array.isArray(fakeMap.fill)).toBe(true));
    expect(fakeMap.idleHandlers).toBeGreaterThan(0); // it really did defer, not luck out
  });
});

describe('BrazilChoropleth — maplibre worker wiring', () => {
  it('points maplibre at the bundled worker BEFORE constructing the map', async () => {
    // maplibre spins up its worker pool on the first `new Map()`, so a setWorkerUrl that
    // lands afterwards is ignored and the library falls back to guessing the URL from its
    // own import.meta.url — the guess that resolves to an asset Vite never emitted, leaving
    // the worker dead, every source unloaded, and the map permanently blank.
    fakeMap = new FakeMap();
    render(<BrazilChoropleth data={DATA} valueKey="value" label="R$" />);
    await waitForMapInit();

    expect(calls).toEqual(['setWorkerUrl', 'Map']);
    expect(workerUrl).toBeTruthy();
  });
});

// ── seamless: hiding the UF divisions inside a group ─────────────────────────
//
// The região grain paints every UF with its macrorregião's total, so the state lines
// inside a block contradict the unit of analysis. `seamless` paints the outline in each
// state's own fill colour: a border between two states of the same region disappears,
// and the step between regions stays exactly where the colours already change. No
// boundary is invented — one is hidden only where both sides are the same colour.

describe('BrazilChoropleth — seamless outlines', () => {
  const rows = [
    { uf: 'PA', value: 10 }, { uf: 'AM', value: 10 }, { uf: 'SP', value: 3 },
  ];
  const lineColor = () => fakeMap.paintProps['uf-line.line-color'];

  it('paints the outline with the FILL expression instead of white', async () => {
    fakeMap = new FakeMap();
    render(<BrazilChoropleth data={rows} valueKey="value" label="R$" seamless />);
    await waitForMapInit();
    await fakeMap.fireLoad();
    await waitFor(() => expect(Array.isArray(fakeMap.fill)).toBe(true));
    // Same match expression on both layers ⇒ a border between two same-coloured states
    // is drawn in that colour, i.e. it vanishes.
    expect(lineColor()).toEqual(fakeMap.fill);
  });

  it('keeps the white seam by default — the UF grain still needs its divisions', async () => {
    fakeMap = new FakeMap();
    render(<BrazilChoropleth data={rows} valueKey="value" label="R$" />);
    await waitForMapInit();
    await fakeMap.fireLoad();
    await waitFor(() => expect(Array.isArray(fakeMap.fill)).toBe(true));
    expect(lineColor()).toBe('#ffffff');
  });
});

// ── Drilling in hides the rest of the country ────────────────────────────────
//
// At a given level the map answers "what is inside here". Leaving the neighbours drawn
// invites reading them as part of the answer — and at região level they carry another
// region's colour entirely, so a greyed-out neighbour would be actively misleading.

describe('BrazilChoropleth — focusUfs', () => {
  const rows = [{ uf: 'PA', value: 10 }, { uf: 'AM', value: 6 }, { uf: 'SP', value: 3 }];

  it('filters BOTH the fill and the outline to the focused UFs', async () => {
    fakeMap = new FakeMap();
    render(<BrazilChoropleth data={rows} valueKey="value" label="R$" focusUfs={['PA', 'AM']} />);
    await waitForMapInit();
    await fakeMap.fireLoad();
    await waitFor(() => expect(fakeMap.filters['uf-fill']).toBeTruthy());
    // The outline too: filtering only the fill would leave the neighbours' borders
    // floating over an empty map.
    for (const layer of ['uf-fill', 'uf-line']) {
      expect(fakeMap.filters[layer]).toEqual(['in', ['get', 'uf'], ['literal', ['PA', 'AM']]]);
    }
  });

  it('clears the filter when nothing is focused, so the country comes back', async () => {
    fakeMap = new FakeMap();
    render(<BrazilChoropleth data={rows} valueKey="value" label="R$" />);
    await waitForMapInit();
    await fakeMap.fireLoad();
    await waitFor(() => expect(Array.isArray(fakeMap.fill)).toBe(true));
    expect(fakeMap.filters['uf-fill']).toBeNull();
    expect(fakeMap.filters['uf-line']).toBeNull();
  });

  it('treats an empty focus list as no focus, not as an empty map', async () => {
    // A selection that resolves to zero UFs must not blank the map — that reads as a
    // broken render rather than as "nothing matched".
    fakeMap = new FakeMap();
    render(<BrazilChoropleth data={rows} valueKey="value" label="R$" focusUfs={[]} />);
    await waitForMapInit();
    await fakeMap.fireLoad();
    await waitFor(() => expect(Array.isArray(fakeMap.fill)).toBe(true));
    expect(fakeMap.filters['uf-fill']).toBeNull();
  });
});
