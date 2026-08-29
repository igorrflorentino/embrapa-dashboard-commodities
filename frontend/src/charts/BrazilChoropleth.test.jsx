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
    this.handlers = {};
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
    if (evt === 'load') { this.loadHandler = typeof a === 'function' ? a : b; return; }
    // Layer handlers were dropped here, which made the hover popup untestable — and the
    // popup is where a row's IDENTITY is shown, so nothing guarded it naming the wrong
    // subject. Keyed by `${event}:${layer}` so a test can fire one directly.
    if (typeof b === 'function') this.handlers[`${evt}:${a}`] = b;
    else if (typeof a === 'function') this.handlers[evt] = a;
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
let popupHtml = '';
const stubPopup = () => ({
  setLngLat() { return this; },
  setHTML(html) { popupHtml = html; return this; },
  addTo() { return this; },
  remove: noop,
});

beforeEach(async () => {
  vi.resetModules();
  calls = [];
  popupHtml = '';
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

// ── O popup nomeia o SUJEITO do número, não o polígono ──────────────────────
// A região não tem geometria própria: cada UF é pintada com o total da SUA região, e cinco
// blocos aparecem. Mas a linha continuava carregando a identidade da UF, então o hover lia
// "AM · Amazonas / 3,8 bi" quando 3,8 bi era o Norte inteiro — o rótulo nomeando um conjunto
// menor que o número. Quem monta a linha declara o que ela representa; o popup obedece.
describe('BrazilChoropleth — o popup nomeia o sujeito do valor', () => {
  const hover = async (rows, feature) => {
    fakeMap = new FakeMap();
    render(<BrazilChoropleth data={rows} valueKey="value" label="R$" />);
    await waitForMapInit();   // maplibre is lazy-imported; handlers exist only after this
    await fakeMap.fireLoad();
    await act(async () => {
      fakeMap.handlers['mousemove:uf-fill']({ features: [feature], lngLat: { lng: 0, lat: 0 } });
    });
    return popupHtml;
  };

  it('nomeia a REGIÃO quando a linha carrega o valor da região', async () => {
    const html = await hover(
      [{ uf: 'AM', name: 'Amazonas', region: 'N', value: 3.8e9,
         displayCode: 'N', displayName: 'Norte' }],
      { properties: { uf: 'AM', name: 'Amazonas' } },
    );
    expect(html).toContain('Norte');
    expect(html).not.toContain('Amazonas');   // o número não é do Amazonas
  });

  it('nomeia a UF quando a linha É da UF (modo estado, sem identidade declarada)', async () => {
    const html = await hover(
      [{ uf: 'AM', name: 'Amazonas', region: 'N', value: 1.2e9 }],
      { properties: { uf: 'AM', name: 'Amazonas' } },
    );
    expect(html).toContain('Amazonas');
    expect(html).toContain('AM');
  });

  it('nenhuma linha com identidade declarada pode exibir o nome do polígono', async () => {
    // A invariante, e não o caso: se a linha diz representar outra coisa, o nome da UF
    // subjacente NUNCA pode aparecer — é isso que enganava o leitor.
    const regioes = [['N', 'Norte'], ['NE', 'Nordeste'], ['CO', 'Centro-Oeste'],
                     ['SE', 'Sudeste'], ['S', 'Sul']];
    const ufs = [['AM', 'Amazonas'], ['BA', 'Bahia'], ['MT', 'Mato Grosso'],
                 ['SP', 'São Paulo'], ['RS', 'Rio Grande do Sul']];
    const falhas = [];
    for (const [i, [code, nome]] of regioes.entries()) {
      const [uf, ufNome] = ufs[i];
      const html = await hover(
        [{ uf, name: ufNome, region: code, value: 1e9, displayCode: code, displayName: nome }],
        { properties: { uf, name: ufNome } },
      );
      if (!html.includes(nome) || html.includes(ufNome)) falhas.push(`${code}: ${html}`);
      cleanup();
    }
    expect(falhas).toEqual([]);
  });
});

// Under a sub-UF recorte the popup's number is a FRACTION of the state it names. The
// chip and the ABNT citation say so for the panel; the popup is where ONE state's number
// is read on its own, so it has to say so there too.
describe('BrazilChoropleth — o popup declara o recorte sub-UF', () => {
  const hoverWith = async (props) => {
    fakeMap = new FakeMap();
    render(<BrazilChoropleth data={[{ uf: 'PA', name: 'Pará', value: 6.55e8 }]}
                             valueKey="value" label="R$" {...props} />);
    await waitForMapInit();
    await fakeMap.fireLoad();
    await act(async () => {
      fakeMap.handlers['mousemove:uf-fill'](
        { features: [{ properties: { uf: 'PA', name: 'Pará' } }], lngLat: { lng: 0, lat: 0 } });
    });
    return popupHtml;
  };

  it('acrescenta a linha do recorte quando há um', async () => {
    const html = await hoverWith({ recorte: 'Marajó (PA)' });
    expect(html).toContain('Pará');
    expect(html).toContain('recorte: Marajó (PA)');
  });

  it('não inventa a linha quando não há recorte', async () => {
    const html = await hoverWith({});
    expect(html).toContain('Pará');
    expect(html).not.toContain('recorte');
  });
});
