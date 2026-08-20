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
  vi.doMock('maplibre-gl', () => ({
    default: {
      // Plain functions so `new maplibregl.Map(...)` constructs; returning an object
      // from a constructor hands back that object.
      Map: function Map() {
        return fakeMap;
      },
      Popup: function Popup() {
        return stubPopup();
      },
      NavigationControl: function NavigationControl() {},
    },
  }));
  ({ BrazilChoropleth } = await import('./BrazilChoropleth.jsx'));
});

afterEach(() => {
  cleanup();
  vi.doUnmock('maplibre-gl');
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
