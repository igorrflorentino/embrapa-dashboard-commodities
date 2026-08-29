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

let popupHtml = '';
const stubPopup = () => ({
  setLngLat() { return this; }, setHTML(html) { popupHtml = html; return this; },
  addTo() { return this; }, remove() {},
});

beforeEach(async () => {
  popupHtml = '';
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

// ── Tally invariants over the mesh × data space ──────────────────────────────
//
// The grey tally is an ACCOUNTING claim made to a researcher: "N municípios sem
// produção registrada". It is computed by subtracting what the data covers from what
// the mesh draws, and the two sets do not always agree — IBGE's Localidades roster
// lists at least one município (Boa Esperança do Norte/MT, created 2023) whose geometry
// the malhas API does not publish, so a município can carry data and have no polygon.
// Subtracting lengths blindly folded it into the grey count, over-claiming "sem
// produção" and, with enough of them, going negative.
//
// The per-case tests above sample two or three shapes of that overlap. These sweep it,
// because the failure mode is a wrong NUMBER on screen — the kind nobody notices.

describe('MunicipioChoropleth — tally invariants over mesh × data', () => {
  const codes = (n, from = 0) =>
    Array.from({ length: n }, (_, i) => String(1500107 + from + i));
  const rowsFor = (cs, value = 10e6) => cs.map((c) => ({ cityCode: c, city: `M${c}`, value }));
  const withMesh = (cs) => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(meshFC(...cs)) }));
  };
  // The tally as the researcher reads it: the number in the grey caption, or 0 when the
  // caption is absent (nothing grey to report).
  const greyCount = (container) => {
    const m = container.textContent.match(/(\d+)\s+municípios?\s+(?:sem produção|fora do recorte)/);
    return m ? Number(m[1]) : 0;
  };
  const noMeshCount = (container) => {
    const m = container.textContent.match(/(\d+)\s+municípios têm dado/);
    if (m) return Number(m[1]);
    return /tem dado no período mas o IBGE/.test(container.textContent) ? 1 : 0;
  };

  // A DISTINCT uf per case, deliberately: MESH_CACHE is module-level and keyed by UF, so
  // reusing "PA" across iterations serves the FIRST mesh to every later one — the loop
  // would then assert against data it is not actually rendering, and pass by accident.
  let ufSeq = 0;
  const render1 = async (props) => {
    const uf = `U${ufSeq++}`;
    const r = render(<MunicipioChoropleth uf={uf} valueKey="value" label="R$" {...props} />);
    await waitFor(() => expect(fakeMap.loadHandler).toBeTypeOf('function'));
    await fakeMap.fireLoad();
    return r;
  };

  it('never reports more greys than the mesh has polygons, nor fewer than zero', async () => {
    for (const meshN of [1, 3, 8]) {
      for (const dataN of [0, 1, 3, 8]) {
        const mesh = codes(meshN);
        withMesh(mesh);
        const { container, unmount } = await render1({ data: rowsFor(codes(dataN)) });
        const g = greyCount(container);
        expect(`mesh${meshN}/data${dataN}: ${g >= 0 && g <= meshN}`).toBe(`mesh${meshN}/data${dataN}: true`);
        unmount();
      }
    }
  });

  it('the greys and the drawn-with-data always add up to the mesh', async () => {
    // The accounting identity behind the sentence. If it ever fails, the number on
    // screen is describing a set that does not exist.
    for (const [meshN, dataN] of [[3, 0], [3, 1], [3, 3], [8, 2], [8, 8], [1, 1]]) {
      const mesh = codes(meshN);
      withMesh(mesh);
      const data = rowsFor(codes(dataN));
      const drawnWithData = data.filter((d) => mesh.includes(d.cityCode)).length;
      const { container, unmount } = await render1({ data });
      expect(`${meshN}/${dataN}: ${greyCount(container) + drawnWithData}`).toBe(`${meshN}/${dataN}: ${meshN}`);
      unmount();
    }
  });

  it('a município with data but NO polygon is reported apart, never folded into the greys', async () => {
    // The Boa Esperança case. Two of the three data rows are outside the mesh.
    const mesh = codes(3);                       // 1500107, 1500108, 1500109
    withMesh(mesh);
    const data = rowsFor([...mesh.slice(0, 1), '9999901', '9999902']);
    const { container } = await render1({ data });
    expect(noMeshCount(container)).toBe(2);
    // Mesh has 3 polygons, 1 of them has data ⇒ 2 grey. The two orphans must NOT inflate it.
    expect(greyCount(container)).toBe(2);
  });

  it('a zero value counts as grey, not as data', async () => {
    // `> 0` is the filter; a row that exists with no production is exactly what the
    // grey is FOR, and counting it as covered would understate the tally.
    const mesh = codes(3);
    withMesh(mesh);
    const { container } = await render1({ data: rowsFor(mesh, 0) });
    expect(greyCount(container)).toBe(3);
  });

  it('narrowed changes the WORDING and never the number', async () => {
    // With a sub-UF facet the greys are outside the selection, not unproductive —
    // a different claim about the same municípios.
    const mesh = codes(5);
    for (const narrowed of [false, true]) {
      withMesh(mesh);
      const { container, unmount } = await render1({ data: rowsFor(codes(2)), narrowed });
      expect(`${narrowed}: ${greyCount(container)}`).toBe(`${narrowed}: 3`);
      expect(container.textContent).toContain(narrowed ? 'fora do recorte' : 'sem produção registrada');
      expect(container.textContent).not.toContain(narrowed ? 'sem produção registrada' : 'fora do recorte');
      unmount();
    }
  });

  it('agrees in number: one município is singular, several are plural', async () => {
    for (const [meshN, dataN, singular] of [[1, 0, true], [2, 0, false], [4, 3, true]]) {
      withMesh(codes(meshN));
      const { container, unmount } = await render1({ data: rowsFor(codes(dataN)) });
      const txt = container.textContent;
      expect(`${meshN}/${dataN}: ${/\d+ município sem/.test(txt)}`).toBe(`${meshN}/${dataN}: ${singular}`);
      unmount();
    }
  });

  it('says nothing at all when every drawn município has data', async () => {
    // A caption reading "0 municípios sem produção" would be noise dressed as a finding.
    const mesh = codes(3);
    withMesh(mesh);
    const { container } = await render1({ data: rowsFor(mesh) });
    expect(container.textContent).not.toMatch(/sem produção|fora do recorte/);
  });
});

// ── Focusing one município hides the rest of the state ───────────────────────

describe('MunicipioChoropleth — focusCity', () => {
  it('filters both layers down to the focused município', async () => {
    render(<MunicipioChoropleth uf="PA" data={DATA} valueKey="value" label="R$"
                                focusCity="1500107" />);
    await waitFor(() => expect(fakeMap.loadHandler).toBeTypeOf('function'));
    await fakeMap.fireLoad();
    await waitFor(() => expect(fakeMap.filters['mun-fill']).toBeTruthy());
    for (const layer of ['mun-fill', 'mun-line']) {
      expect(fakeMap.filters[layer]).toEqual(['==', ['get', 'codarea'], '1500107']);
    }
  });

  it('brings the whole state back when the focus clears', async () => {
    render(<MunicipioChoropleth uf="PA" data={DATA} valueKey="value" label="R$" />);
    await waitFor(() => expect(fakeMap.loadHandler).toBeTypeOf('function'));
    await fakeMap.fireLoad();
    await waitFor(() => expect(fakeMap.paintProps['mun-fill.fill-color']).toBeTruthy());
    expect(fakeMap.filters['mun-fill']).toBeNull();
    expect(fakeMap.filters['mun-line']).toBeNull();
  });

  it('coerces a numeric code — the cube and the mesh disagree on type', async () => {
    // cityCode arrives as a string from /geo-mesh but a caller may hold a number; a
    // strict maplibre comparison against the wrong type silently matches nothing,
    // which looks exactly like "this município has no polygon".
    render(<MunicipioChoropleth uf="PA" data={DATA} valueKey="value" label="R$"
                                focusCity={1500107} />);
    await waitFor(() => expect(fakeMap.loadHandler).toBeTypeOf('function'));
    await fakeMap.fireLoad();
    await waitFor(() => expect(fakeMap.filters['mun-fill']).toBeTruthy());
    expect(fakeMap.filters['mun-fill'][2]).toBe('1500107');
  });
});

describe('MunicipioChoropleth — the tally goes quiet when one município is focused', () => {
  it('does not claim greys that are no longer drawn', async () => {
    // Focusing HIDES the others rather than greying them. "143 municípios fora do
    // recorte — em cinza" would then describe a map that is not on screen — the tally
    // is an accounting claim, and it has to be about what the researcher can see.
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(meshFC('1500107', '1500131', '1500206')) }));
    const { container } = render(
      <MunicipioChoropleth uf="PA" data={DATA} valueKey="value" label="R$" focusCity="1500107" />,
    );
    await waitFor(() => expect(fakeMap.loadHandler).toBeTypeOf('function'));
    await fakeMap.fireLoad();
    expect(container.textContent).not.toMatch(/em cinza/);
  });

  it('still reports them when the whole state is on screen', async () => {
    // The guard must be the FOCUS, not a blanket silence: with the state drawn, the
    // grey municípios are visible and the count is the honest thing to say.
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(meshFC('1500107', '1500131', '1500206')) }));
    const { container } = render(
      <MunicipioChoropleth uf="PA" data={DATA} valueKey="value" label="R$" />,
    );
    await waitFor(() => expect(fakeMap.loadHandler).toBeTypeOf('function'));
    await fakeMap.fireLoad();
    expect(container.textContent).toMatch(/em cinza/);
  });
});

// ── O texto do popup ────────────────────────────────────────────────────────
// Não havia asserção nenhuma sobre o que o hover ESCREVE — o stub descartava o HTML. Foi
// exatamente essa ausência que deixou o mapa do Brasil exibir "AM · Amazonas" ao lado do
// valor do Norte inteiro por semanas (v1.33.25). Aqui o dado não mistura grão (a linha é do
// município e o valor é dele), então o que se prende é justamente isso: o nome exibido é o
// do polígono sob o cursor, e o número é o daquele município.
describe('MunicipioChoropleth — o popup nomeia o município do próprio polígono', () => {
  const hover = async (cityCode, props = {}) => {
    await renderMap(props);
    await fakeMap.fire('mun-fill', 'mousemove', {
      features: [{ properties: { codarea: cityCode } }], lngLat: { lng: 0, lat: 0 },
    });
    return popupHtml;
  };

  it('mostra o nome e o valor do município sob o cursor', async () => {
    const html = await hover('1500107');
    expect(html).toContain('Abaetetuba');
    expect(html).not.toContain('Abel Figueiredo');   // o vizinho não pode aparecer
    expect(html).toMatch(/30\s*mi/);
  });

  it('cada município mostra o SEU valor, nunca o do outro', async () => {
    // A invariante, varrida: para cada linha, o popup daquele polígono tem de trazer o
    // nome dela e nenhum outro nome do conjunto.
    const falhas = [];
    for (const alvo of DATA) {
      const html = await hover(alvo.cityCode);
      const outros = DATA.filter((d) => d.cityCode !== alvo.cityCode).map((d) => d.city);
      if (!html.includes(alvo.city)) falhas.push(`${alvo.city}: não se nomeia`);
      for (const o of outros) if (html.includes(o)) falhas.push(`${alvo.city}: mostra ${o}`);
      cleanup();
    }
    expect(falhas).toEqual([]);
  });

  it('um município sem linha diz "sem produção registrada", não um traço mudo', async () => {
    const html = await hover('9999999');
    expect(html).toContain('sem produção registrada');
    expect(html).not.toMatch(/\bmi\b|\bbi\b/);   // nenhum número atribuído a ele
  });
});
