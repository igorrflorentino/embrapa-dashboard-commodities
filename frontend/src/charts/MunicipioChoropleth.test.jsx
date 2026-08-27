// MunicipioChoropleth — the intra-UF municipal map. maplibre needs WebGL, which jsdom
// has not, so (like BrazilChoropleth.test.jsx) these substitute a FAKE map and assert
// the two things that actually broke in development and would break silently again:
//
//  1. the fill expression must key on `codarea`, NOT `uf`. fillColorExpression used to
//     hardcode 'uf', so the municipal map compiled a perfectly valid `match` that
//     matched nothing — every município fell through to the no-data grey, with no
//     error to explain it. A test asserting only "it painted" would still pass.
//  2. the grey tally must say WHY the municípios are grey. Under a sub-UF/município
//     facet they are outside the selection, not municípios without production.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, waitFor } from '@testing-library/react';

const SQUARE = [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]];
const meshFC = (...codes) => ({
  type: 'FeatureCollection',
  features: codes.map((c) => ({
    type: 'Feature', properties: { codarea: c },
    geometry: { type: 'Polygon', coordinates: SQUARE },
  })),
});

let fakeMap;
let MunicipioChoropleth;

class FakeMap {
  constructor() {
    this.paintProps = {};
    this.filters = {};
    this.layers = new Set();
    this.loadHandler = null;
    this.handlers = {};
    this.touchZoomRotate = { disableRotation() {} };
    this.scrollZoom = { disable: vi.fn() };
  }
  isStyleLoaded() { return true; }
  getLayer(id) { return this.layers.has(id) ? { id } : undefined; }
  setPaintProperty(l, p, v) { this.paintProps[`${l}.${p}`] = v; }
  setFilter(l, f) { this.filters[l] = f; }
  get fill() { return this.paintProps['mun-fill.fill-color']; }
  addSource() {}
  addLayer(spec) {
    this.layers.add(spec.id);
    if (spec.filter) this.filters[spec.id] = spec.filter;
  }
  on(evt, a, b) {
    if (evt === 'load') this.loadHandler = a;
    else if (typeof b === 'function') this.handlers[`${a}:${evt}`] = b;
  }
  once() {}
  addControl() {}
  getCanvas() { return { style: {} }; }
  remove() {}
  fireLoad() { return act(async () => { this.loadHandler(); }); }
  /** Drive a registered layer handler, e.g. click on 'mun-fill'. */
  fire(layer, evt, payload) {
    return act(async () => { this.handlers[`${layer}:${evt}`]?.(payload); });
  }
}

const stubPopup = () => ({
  setLngLat() { return this; }, setHTML() { return this; },
  addTo() { return this; }, remove() {},
});

beforeEach(async () => {
  vi.resetModules();
  fakeMap = new FakeMap();
  window.autoScaleNum = (v) => (Math.abs(v) >= 1e6 ? { factor: 1e6, suffix: 'mi' } : { factor: 1, suffix: '' });
  vi.doMock('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url', () => ({ default: '/w.js' }));
  vi.doMock('maplibre-gl', () => ({
    Map: function Map() { return fakeMap; },
    Popup: function Popup() { return stubPopup(); },
    NavigationControl: function NavigationControl() {},
    setWorkerUrl: () => {},
  }));
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(meshFC('1500107', '1500131', '1500206')) }),
  );
  ({ MunicipioChoropleth } = await import('./MunicipioChoropleth.jsx'));
});

afterEach(() => {
  cleanup();
  vi.doUnmock('maplibre-gl');
  vi.doUnmock('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url');
  delete window.autoScaleNum;
});

const DATA = [
  { cityCode: '1500107', city: 'Abaetetuba', value: 30e6 },
  { cityCode: '1500131', city: 'Abel Figueiredo', value: 10e6 },
];

async function renderMap(props = {}) {
  const r = render(
    <MunicipioChoropleth uf="PA" data={DATA} valueKey="value" label="R$" {...props} />,
  );
  await waitFor(() => expect(fakeMap.loadHandler).toBeTypeOf('function'));
  await fakeMap.fireLoad();
  return r;
}

describe('MunicipioChoropleth — paint', () => {
  it('keys the fill match on codarea (not uf) so the municípios actually colour', async () => {
    await renderMap();
    await waitFor(() => expect(Array.isArray(fakeMap.fill)).toBe(true));
    const fill = fakeMap.fill;
    expect(fill[0]).toBe('match');
    // THE regression: hardcoding ['get','uf'] here produced a valid expression that
    // matched nothing, painting the whole state no-data grey.
    expect(fill[1]).toEqual(['get', 'codarea']);
    expect(fill).toContain('1500107');
    expect(fill).toContain('1500131');
  });

  it('fetches the UF mesh once per UF and disables scroll zoom', async () => {
    await renderMap();
    expect(global.fetch).toHaveBeenCalledWith('/geo/municipios/PA.json');
    // Page scroll must win over map zoom (MAPA-1), same as the UF choropleth.
    expect(fakeMap.scrollZoom.disable).toHaveBeenCalled();
  });

  it('highlights the selected município and clears the highlight when none is set', async () => {
    const { rerender } = await renderMap({ selectedCity: '1500107' });
    await waitFor(() => expect(fakeMap.filters['mun-selected']).toEqual(['==', ['get', 'codarea'], '1500107']));
    rerender(<MunicipioChoropleth uf="PA" data={DATA} valueKey="value" label="R$" />);
    await waitFor(() => expect(fakeMap.filters['mun-selected']).toEqual(['==', ['get', 'codarea'], '__none__']));
  });

  it('reports a município click by its código', async () => {
    const onSelect = vi.fn();
    await renderMap({ onSelect });
    await fakeMap.fire('mun-fill', 'click', { features: [{ properties: { codarea: '1500206' } }] });
    expect(onSelect).toHaveBeenCalledWith('1500206');
  });
});

describe('MunicipioChoropleth — honest grey tally', () => {
  it('says "sem produção registrada" when nothing narrows the selection', async () => {
    const { container } = await renderMap();
    // 3 municípios in the mesh, 2 with a value → 1 grey.
    expect(container.textContent).toContain('1 município sem produção registrada');
  });

  it('says "fora do recorte" instead when a sub-UF/município facet is narrowing', async () => {
    // The greys are then EXCLUDED by the filter — calling them "sem produção" would
    // assert something the data never said.
    const { container } = await renderMap({ narrowed: true });
    expect(container.textContent).toContain('1 município fora do recorte');
    expect(container.textContent).not.toContain('sem produção registrada');
  });
});

describe('MunicipioChoropleth — degraded paths', () => {
  it('shows a pt-BR notice when the UF mesh cannot be fetched', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 404 }));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const { container } = render(
      <MunicipioChoropleth uf="ZZ" data={DATA} valueKey="value" label="R$" />,
    );
    await waitFor(() => expect(container.textContent).toContain('Malha municipal indisponível'));
  });

  it('shows a loading notice until the mesh lands', () => {
    let resolve;
    global.fetch = vi.fn(() => new Promise((r) => { resolve = r; }));
    const { container } = render(
      <MunicipioChoropleth uf="PA" data={DATA} valueKey="value" label="R$" />,
    );
    expect(container.textContent).toContain('Carregando a malha municipal');
    expect(resolve).toBeTypeOf('function'); // never resolved — the pending state is the assertion
  });
});
