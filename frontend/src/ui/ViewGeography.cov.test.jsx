// ViewGeography.cov.test.jsx — render coverage for the territorial-distribution view.
// ViewGeography composes a wide set of window.* helpers (metric conventions, geo
// scalers) + chart widgets and branches heavily on the active metric (value / mass /
// volume / cabeças), the granularity scope (região / UF / município), and a handful of
// honest empty/partial states. Following the ViewFlows/ViewConcentration pattern, we
// stub every window.* dependency so each branch is exercised deterministically, then
// assert the view renders without crashing and that the relevant content surfaces.
//
// The view reads React hooks off the GLOBAL `React` (the prototype convention —
// `const { useState: useGeoState } = React` runs at import time), so we set
// globalThis.React / window.React BEFORE importing the view.

import * as React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/react';

// The click-a-UF-to-filter rule lives in geoSelect.js (shared with Visão geral and
// Qualidade) and self-registers on window, exactly as main.jsx loads it. Imported
// rather than stubbed so these tests exercise the REAL selection logic — including
// the sub-UF facet reset, which is the part that is easy to get wrong.
import './geoSelect.js';

// Captured props from the stubbed chart widgets, so we can assert what each branch fed.
let regionBarsProps, choroProps, tileMapProps, heatmapProps, barChartCalls, productsByUfCalls, muniMapProps;

function stubGlobals(filtered, opts = {}) {
  const {
    geoLevel = 'municipio',     // 'municipio' (IBGE) vs 'uf' (trade) → muniCapable
    baseCcy = 'BRL',
    meta = null,                // dataStore.meta(db) → partial-year calendar signal
    productsByUf = { products: [] },
  } = opts;

  window.applyFilters = () => filtered;
  window.DEFAULT_CONVENTIONS = { currency: 'BRL', correction: 'IPCA', autoScale: true };

  // Metric-convention helpers — identity-ish so the math stays predictable.
  window.canonCurrencyFor = () => baseCcy;
  window.convFactorFor = () => 1;          // valueMul = 1 * 1e6
  window.massQtyMul = () => 1e3;
  window.volumeQtyMul = () => 1e6;
  window.countQtyMul = () => 1e6;
  window.valueAxisLabel = () => 'R$';
  window.massAxisLabel = () => 't';
  window.volumeAxisLabel = () => 'm³';
  window.countAxisLabel = () => 'cab';
  window.geoLevelFor = () => geoLevel;
  window.isCanonicalUf = (uf) => ['PA', 'SP', 'MT'].includes(uf);
  window.UF_DATA = [
    { uf: 'PA', name: 'Pará', region: 'N' },
    { uf: 'SP', name: 'São Paulo', region: 'SE' },
    { uf: 'MT', name: 'Mato Grosso', region: 'CO' },
  ];
  window.REGIONS = [
    { id: 'N', label: 'Norte' }, { id: 'SE', label: 'Sudeste' }, { id: 'CO', label: 'Centro-Oeste' },
  ];

  // scaleSeries: pass through data + a stable label so the DOM is assertable.
  window.scaleSeries = (data, _max, _conv, _key, label) => ({ data: data || [], label });
  window.autoScaleNum = (v) => {
    const a = Math.abs(v || 0);
    if (a >= 1e9) return { factor: 1e9, suffix: 'bi' };
    if (a >= 1e6) return { factor: 1e6, suffix: 'mi' };
    if (a >= 1e3) return { factor: 1e3, suffix: 'mil' };
    return { factor: 1, suffix: '' };
  };
  window.scaleLabel = (unit, suffix) => (suffix ? `${unit} (${suffix})` : unit);

  window.dataStore = {
    get: () => ({}), // CONF-1: the heatmap no longer reads dataStore.get(db).ufYearly
    meta: () => meta,
  };
  window.productsByUf = (db, summary, conv) => {
    productsByUfCalls.push({ db, summary, conv });
    return productsByUf;
  };
  window.geoMesh = undefined;
  window.municipioYearly = undefined;
  window.openFilterMenu = vi.fn();
  window.patchFilter = vi.fn();

  // Composed widgets — capture props / render markers.
  window.UnitFamilyBanner = () => <div className="ufb" />;
  // The app always provides Icon (bootstrap-globals); a harness without it turns any
  // icon-bearing element into "Element type is invalid", which reads as a component
  // bug rather than a missing stub.
  window.Icon = ({ name }) => <span data-icon={name} />;
  window.SectionHeader = ({ overline, title, action }) => (
    <div className="sh">
      <span className="sh-ov">{overline}</span>
      <span className="sh-title">{title}</span>
      <span className="sh-action">{action}</span>
    </div>
  );
  window.RegionBars = (props) => { regionBarsProps = props; return <div className="regionbars" />; };
  window.MunicipioChoropleth = (props) => { muniMapProps = props; return <div className="munimap" />; };
  window.BrazilChoropleth = (props) => { choroProps = props; return <div className="choro" />; };
  window.BrazilTileMap = (props) => { tileMapProps = props; return <div className="tilemap" />; };
  window.Heatmap = (props) => { heatmapProps = props; return <div className="heatmap" />; };
  window.BarChart = (props) => { barChartCalls.push(props); return <div className="barchart" />; };
}

let ViewGeography;

beforeEach(async () => {
  regionBarsProps = choroProps = tileMapProps = heatmapProps = muniMapProps = undefined;
  barChartCalls = [];
  productsByUfCalls = [];
  globalThis.React = React;
  window.React = React;
  await import('./ViewGeography.jsx'); // registers window.ViewGeography
  ViewGeography = window.ViewGeography;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.geoMesh;
  delete window.municipioYearly;
  delete window.openFilterMenu;
  delete window.patchFilter;
  delete window.UF_DATA;
  delete window.REGIONS;
});

// A real per-(UF, year) history for the heatmap. CONF-1: the view reads THIS field
// on `filtered` (applyFilters' own basket/state-aware grid), not
// dataStore.get(db).ufYearly — the always-all-products snapshot field that used to
// silently diverge from the map/ranking once a basket cube had loaded.
const UF_YEARLY = [
  { uf: 'PA', name: 'Pará', year: 2019, value: 60, q_mass: 24, q_vol: 6, q_count: 10 },
  { uf: 'PA', name: 'Pará', year: 2020, value: 75, q_mass: 30, q_vol: 8, q_count: 12 },
  { uf: 'SP', name: 'São Paulo', year: 2019, value: 20, q_mass: 8, q_vol: 3, q_count: 5 },
  { uf: 'SP', name: 'São Paulo', year: 2020, value: 25, q_mass: 10, q_vol: 4, q_count: 6 },
];

// A representative snapshot: two UFs, two regions, two top municípios, plus the real
// (UF × year) heatmap history. Carries value + mass + volume + count so the metric
// toggle has every dimension available.
function fullFixture(overrides = {}) {
  return {
    ufData: [
      { uf: 'PA', value: 75, q_mass: 30, q_vol: 8, q_count: 12, real: true },
      { uf: 'SP', value: 25, q_mass: 10, q_vol: 4, q_count: 6, real: true },
    ],
    regionData: [
      { id: 'N',  label: 'Norte',   value: 75, q_mass: 30, q_vol: 8, q_count: 12 },
      { id: 'SE', label: 'Sudeste', value: 25, q_mass: 10, q_vol: 4, q_count: 6 },
    ],
    topMunis: [
      { city: 'Belém', uf: 'PA', product: '', value: 40, q_mass: 16, q_vol: 5, q_count: 7 },
      { city: 'Santos', uf: 'SP', product: '', value: 12, q_mass: 6, q_vol: 2, q_count: 3 },
    ],
    yearStart: 2018,
    yearEnd: 2020,
    ufLatestYear: 2020,
    ufYearPartial: false,
    notFilteredByBasket: false,
    ufYearlySeries: UF_YEARLY,
    muniYearlySeries: [],
    subUfActive: false,
    subUfLoaded: false,
    ...overrides,
  };
}

describe('ViewGeography — smoke + main branches', () => {
  it('renders the default (value · UF) view with the choropleth and the real heatmap', () => {
    stubGlobals(fullFixture());
    const { container } = render(
      <ViewGeography
        families={['mass', 'volume']}
        summary={{}}
        database="ibge_pevs"
        conventions={{ currency: 'BRL', correction: 'IPCA', autoScale: true }}
      />
    );
    // Default scope = UF, default ufViz = map → choropleth gets the scaled UF rows.
    expect(choroProps).toBeTruthy();
    expect(choroProps.data.map((u) => u.uf)).toEqual(['PA', 'SP']);
    // value × valueMul (1e6) → PA 75 → 75e6
    expect(choroProps.data.find((u) => u.uf === 'PA').value).toBe(75e6);
    // Heatmap built from filtered.ufYearlySeries (two states kept).
    expect(heatmapProps).toBeTruthy();
    expect(heatmapProps.rows.length).toBe(2);
    // Metric segment offers Valor + the two quantity dims present in this basket.
    expect(container.textContent).toContain('Valor');
    expect(container.textContent).toContain('Quantidade (massa)');
    expect(container.textContent).toContain('Quantidade (volume)');
  });

  // CONF-1: the heatmap used to read dataStore.get(db).ufYearly directly — ALWAYS
  // all-products — instead of the basket-aware grid the map/ranking already used
  // once their cube loaded. Proven here by making the two sources DISAGREE: if the
  // heatmap read the (now-empty) dataStore mock, it would render 0 rows.
  it('CONF-1: the heatmap reads filtered.ufYearlySeries, not dataStore.get(db).ufYearly', () => {
    stubGlobals(fullFixture({ ufYearlySeries: UF_YEARLY }));
    window.dataStore.get = () => ({ ufYearly: [] }); // a stale/decoy snapshot field
    render(<ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />);
    expect(heatmapProps.rows.length).toBe(2); // came from ufYearlySeries, not the decoy
  });

  // CONF-3: a non-state pseudo-origin (a trade banco's ND/EX/ZN…) must never inflate
  // the map's shared scale, the Top-N ranking, or the heatmap's UF keep-set — mirrors
  // the SAME isRealUf guard ViewOverview/ViewConcentration already apply.
  it('CONF-3: excludes a non-real pseudo-UF row from the map/ranking/heatmap', () => {
    const fx = fullFixture({
      ufData: [
        { uf: 'PA', value: 75, q_mass: 30, q_vol: 8, q_count: 12, real: true },
        { uf: 'SP', value: 25, q_mass: 10, q_vol: 4, q_count: 6, real: true },
        { uf: 'ND', value: 9999, q_mass: 0, q_vol: 0, q_count: 0, real: false },
      ],
    });
    stubGlobals(fx);
    render(<ViewGeography families={['mass']} summary={{}} database="mdic_comex" conventions={{ autoScale: true }} />);
    expect(choroProps.data.map((u) => u.uf)).toEqual(['PA', 'SP']); // ND dropped
    expect(choroProps.data.some((u) => u.uf === 'ND')).toBe(false);
  });

  it('switching the metric to massa rescales the maps by the mass multiplier', () => {
    stubGlobals(fullFixture());
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    const massBtn = [...container.querySelectorAll('.seg-opt')].find((b) => b.textContent.includes('massa'));
    expect(massBtn).toBeTruthy();
    fireEvent.click(massBtn);
    // q_mass × massMul (1e3): PA 30 → 30000.
    expect(choroProps.data.find((u) => u.uf === 'PA').q_mass).toBe(30000);
  });

  it('the "Blocos" toggle swaps the choropleth for the SVG tile map', () => {
    stubGlobals(fullFixture());
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    const blocos = [...container.querySelectorAll('.seg-opt')].find((b) => b.textContent === 'Blocos');
    fireEvent.click(blocos);
    expect(tileMapProps).toBeTruthy();
    expect(tileMapProps.data.length).toBe(2);
  });

  it('the "Região" granularity renders RegionBars once, WITHOUT the redundant ranking/soma cards (EST-2)', () => {
    stubGlobals(fullFixture());
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    const regiaoBtn = [...container.querySelectorAll('.seg-opt')].find((b) => b.textContent === 'Região');
    fireEvent.click(regiaoBtn);
    expect(regionBarsProps).toBeTruthy();
    // EST-2: scope=região used to ALSO render "Soma por região" below — the SAME
    // chart, same data, a second time on one screen. That card (and the UF-ranking
    // card, equally redundant with the top card in this scope) must be gone.
    expect(container.textContent).not.toContain('Soma por região');
    expect(container.textContent).not.toContain('Top 10');
  });

  // EST-4: the point of the vendored municipal meshes — a sub-UF selection must finally
  // reach the MAP. Before, narrowing to a mesorregião left the UF choropleth shading the
  // whole state, so the recorte was invisible.
  it('the "Município" granularity draws the municipal choropleth when the rows resolve to ONE UF', () => {
    stubGlobals(fullFixture({
      topMunis: [
        { cityCode: '1500107', city: 'Abaetetuba', uf: 'PA', value: 40 },
        { cityCode: '1500131', city: 'Abel Figueiredo', uf: 'PA', value: 12 },
      ],
      subUfActive: true, subUfLoaded: true,
    }), { geoLevel: 'municipio' });
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    fireEvent.click([...container.querySelectorAll('.seg-opt')].find((b) => b.textContent === 'Município'));
    expect(muniMapProps).toBeTruthy();
    expect(muniMapProps.uf).toBe('PA');
    expect(muniMapProps.data.map((m) => m.cityCode)).toEqual(['1500107', '1500131']);
    // A sub-UF facet is narrowing → the un-shaded municípios are OUTSIDE the selection,
    // not municípios without production, and the map must say so.
    expect(muniMapProps.narrowed).toBe(true);
  });

  it('the "Município" granularity lists the top municípios when rows exist', () => {
    // Belém/PA + Santos/SP straddle two states, and the vendored geometry is one file
    // per UF — there is no single mesh to load, so the ranking (grain-correct at any
    // breadth) is what renders.
    stubGlobals(fullFixture(), { geoLevel: 'municipio' });
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    const muniBtn = [...container.querySelectorAll('.seg-opt')].find((b) => b.textContent === 'Município');
    expect(muniBtn).toBeTruthy();
    fireEvent.click(muniBtn);
    expect(muniMapProps).toBeUndefined();
    expect(container.querySelector('.muni-list')).toBeTruthy();
    expect(container.textContent).toContain('Belém');
    expect(container.textContent).toContain('Santos');
  });

  it('the município granularity shows the recorte-a-geografia note + an "abrir filtro" button when there are no rows (EST-5)', () => {
    stubGlobals(fullFixture({ topMunis: [] }), { geoLevel: 'municipio' });
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    const muniBtn = [...container.querySelectorAll('.seg-opt')].find((b) => b.textContent === 'Município');
    fireEvent.click(muniBtn);
    expect(container.querySelector('.muni-list')).toBeFalsy();
    expect(container.textContent).toContain('recortar a geografia');
    // EST-5: the empty state used to be a dead-end paragraph — now a button straight
    // into the filter modal, via the SAME global bridge patchFilter/openFilterMenu use.
    const cta = container.querySelector('.geo-empty-cta button');
    expect(cta).toBeTruthy();
    fireEvent.click(cta);
    expect(window.openFilterMenu).toHaveBeenCalledTimes(1);
  });
});

describe('ViewGeography — gating and honest-note branches', () => {
  it('hides the Município button for a UF-only trade banco (geoLevel=uf)', () => {
    stubGlobals(fullFixture(), { geoLevel: 'uf' });
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="mdic_comex" conventions={{ autoScale: true }} />
    );
    const labels = [...container.querySelectorAll('.seg-opt')].map((b) => b.textContent);
    expect(labels).not.toContain('Município');
    expect(labels).toContain('UF');
    expect(labels).toContain('Região');
  });

  it('shows the basket note when the territorial split is not basket-filtered', () => {
    stubGlobals(fullFixture({ notFilteredByBasket: true }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    expect(container.textContent).toContain('todos os produtos');
  });

  it('shows the mass-unavailable note when the family is in the basket but per-UF has no mass', () => {
    // mass family present, but every per-UF q_mass is 0 → massAvail false → note shown,
    // and the metric segment falls back to Valor only.
    const fx = fullFixture({
      ufData: [
        { uf: 'PA', value: 75, q_mass: 0, q_vol: 0, q_count: 0, real: true },
        { uf: 'SP', value: 25, q_mass: 0, q_vol: 0, q_count: 0, real: true },
      ],
    });
    stubGlobals(fx);
    const { container } = render(
      <ViewGeography families={['mass', 'volume']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    // Both mass + volume families present but all-zero per UF → the combined plural note.
    expect(container.textContent).toContain('ainda não estão disponíveis');
    // Only Valor remains in the metric segment.
    expect(container.textContent).not.toContain('Quantidade (massa)');
  });

  it('shows the cabeças cross-species caveat when the active dim is count', () => {
    const fx = fullFixture({
      ufData: [
        { uf: 'MT', value: 0, q_mass: 0, q_vol: 0, q_count: 200, real: true },
        { uf: 'SP', value: 0, q_mass: 0, q_vol: 0, q_count: 50, real: true },
      ],
      regionData: [
        { id: 'CO', label: 'Centro-Oeste', value: 0, q_count: 200 },
        { id: 'SE', label: 'Sudeste', value: 0, q_count: 50 },
      ],
      topMunis: [],
      ufYearlySeries: [],
    });
    stubGlobals(fx, { geoLevel: 'municipio' });
    const { container } = render(
      <ViewGeography families={['count']} summary={{}} database="ibge_ppm" conventions={{ autoScale: true }} />
    );
    // value is all-zero → valueAvail false; count is the only available dim → active.
    expect(container.textContent).toContain('cabeças');
    expect(container.textContent).toContain('Rebanho');
  });

  it('renders the ufYearPartial caption and "(parcial)" tag when the UF year lags the window', () => {
    stubGlobals(fullFixture({ ufYearPartial: true, ufLatestYear: 2019, yearEnd: 2020 }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    expect(container.textContent).toContain('(parcial)');
    expect(container.textContent).toContain('o último ano com dados por UF');
  });

  it('flags the map year as "(parcial)" from the calendar-incomplete latest year', () => {
    stubGlobals(fullFixture({ ufLatestYear: 2024 }), {
      meta: { latest: { yearComplete: false, completeYear: 2023 } },
    });
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    expect(container.textContent).toContain('2024 (parcial)');
  });

  it('EST-6: singles out "Estado produtor" (no "maiores") when only one UF ranks', () => {
    const fx = fullFixture({
      ufData: [{ uf: 'PA', value: 75, q_mass: 30, q_vol: 8, q_count: 12, real: true }],
      regionData: [{ id: 'N', label: 'Norte', value: 75, q_mass: 30, q_vol: 8, q_count: 12 }],
    });
    stubGlobals(fx);
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    expect(container.textContent).toContain('Estado produtor');
    expect(container.textContent).not.toContain('Maiores estados produtores');
  });
});

describe('ViewGeography — empty geo + products-by-UF base table', () => {
  it('renders an honest empty-state instead of a blank Heatmap when there is no history', () => {
    stubGlobals(fullFixture({ ufYearlySeries: [] }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    // Empty history → no window.Heatmap call at all (an honest caption instead of an
    // empty chart), but the rest of the view still mounts.
    expect(heatmapProps).toBeUndefined();
    expect(container.textContent).toContain('Sem histórico anual disponível');
    expect(container.querySelector('.choro')).toBeTruthy();
  });

  it('renders the per-state products card when summary.states is selected', () => {
    stubGlobals(fullFixture(), {
      productsByUf: {
        products: [
          { code: 'P1', name: 'Açaí', value: 40 },
          { code: 'P2', name: 'Castanha', value: 12 },
        ],
      },
    });
    const { container } = render(
      <ViewGeography
        families={['mass']}
        summary={{ states: ['PA'] }}
        database="ibge_pevs"
        conventions={{ autoScale: true }}
      />
    );
    expect(container.textContent).toContain('Produtos do estado');
    expect(container.textContent).toContain('PA');
    // The per-state products card adds a BarChart on top of the Top-10 + region bars.
    expect(barChartCalls.length).toBeGreaterThanOrEqual(1);
  });

  // CONF-2: this card used to sum the ENTIRE window regardless of what year the
  // map/ranking above were showing. It must now ask productsByUf for the SAME
  // single data-year (ufLatestYear) the rest of the view is scoped to.
  it('CONF-2: restricts "Produtos do estado" to the map\'s data-year (ufLatestYear), not the whole window', () => {
    stubGlobals(fullFixture({ ufLatestYear: 2019, yearStart: 2010, yearEnd: 2024 }), {
      productsByUf: { products: [{ code: 'P1', name: 'Açaí', value: 40 }] },
    });
    render(
      <ViewGeography
        families={['mass']}
        summary={{ states: ['PA'], startDate: '2010-01-01', endDate: '2024-12-01' }}
        database="ibge_pevs"
        conventions={{ autoScale: true }}
      />
    );
    expect(productsByUfCalls.length).toBe(1);
    const { summary } = productsByUfCalls[0];
    expect(summary.startDate).toBe('2019-01-01');
    expect(summary.endDate).toBe('2019-12-01');
  });

  it('omits the per-state products card when productsByUf returns nothing', () => {
    stubGlobals(fullFixture(), { productsByUf: { products: [] } });
    const { container } = render(
      <ViewGeography
        families={['mass']}
        summary={{ states: ['PA'] }}
        database="ibge_pevs"
        conventions={{ autoScale: true }}
      />
    );
    expect(container.textContent).not.toContain('Produtos do estado');
  });

  it('honors autoScale=false on the heatmap (rows passed through unscaled)', () => {
    stubGlobals(fullFixture());
    render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs" conventions={{ autoScale: false }} />
    );
    // autoScale off → heatScaled returns the raw rows + the bare unit label.
    expect(heatmapProps.rows.length).toBe(2);
  });
});

// ── "Ver raio-x": the bridge to Perfil do território ─────────────────────────
//
// Geografia shows how the activity spreads ACROSS territories; Perfil do território
// shows what happens INSIDE one. The shortcut makes that pair discoverable WITHOUT
// touching the map's click, which stays a cheap reversible filter toggle — navigation
// and filtering must not share a gesture.

describe('ViewGeography — the Perfil do território shortcut', () => {
  afterEach(() => { delete window.goToView; });

  it('names the território it would open, so the button is a promise not a leap', () => {
    stubGlobals(fullFixture({ ufYearlySeries: UF_YEARLY }));
    window.goToView = vi.fn();
    const { container } = render(
      <ViewGeography families={['mass']} summary={{ states: ['PA'] }}
                     database="ibge_pevs" conventions={{ autoScale: true }} />,
    );
    const btn = [...container.querySelectorAll('button')].find((b) => /raio-x/i.test(b.textContent));
    expect(btn.textContent).toContain('PA');
    btn.click();
    expect(window.goToView).toHaveBeenCalledWith('territory_profile');
  });

  it('stays unnamed when nothing is narrowed — it must not claim a place it lacks', () => {
    stubGlobals(fullFixture({ ufYearlySeries: UF_YEARLY }));
    window.goToView = vi.fn();
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}}
                     database="ibge_pevs" conventions={{ autoScale: true }} />,
    );
    const btn = [...container.querySelectorAll('button')].find((b) => /raio-x/i.test(b.textContent));
    // The profile will open on its own default; promising a specific place would lie.
    expect(btn.textContent.trim()).toBe('Ver raio-x');
  });

  it('renders nothing when there is no navigation bridge, instead of a dead button', () => {
    stubGlobals(fullFixture({ ufYearlySeries: UF_YEARLY }));
    delete window.goToView;
    const { container } = render(
      <ViewGeography families={['mass']} summary={{ states: ['PA'] }}
                     database="ibge_pevs" conventions={{ autoScale: true }} />,
    );
    expect([...container.querySelectorAll('button')].some((b) => /raio-x/i.test(b.textContent)))
      .toBe(false);
  });
});

// ── Região: a map, like the other two grains ─────────────────────────────────
//
// Região had bars where UF and município had maps, so the COARSEST grain was the only
// one you could not see on a map. A macrorregião is exactly a union of UFs, so the
// region choropleth paints every UF with ITS REGION's total over geometry already
// shipped — no região polygons to vendor, and one basis shared with the bars.

describe('ViewGeography — the região map', () => {
  // `region` on each UF row is what the real app's _decorateUf fills in; the shared
  // fixture omits it, so the region map (which joins UF → region) needs it stated.
  const regionFixture = () => fullFixture({
    ufYearlySeries: UF_YEARLY,
    ufData: [
      { uf: 'PA', region: 'N', value: 75, q_mass: 30, q_vol: 8, q_count: 12, real: true },
      { uf: 'AM', region: 'N', value: 20, q_mass: 8, q_vol: 2, q_count: 3, real: true },
      { uf: 'SP', region: 'SE', value: 25, q_mass: 10, q_vol: 4, q_count: 6, real: true },
    ],
    regionData: [
      { id: 'N', label: 'Norte', value: 95, q_mass: 38, q_vol: 10, q_count: 15, ufs: 2 },
      { id: 'SE', label: 'Sudeste', value: 25, q_mass: 10, q_vol: 4, q_count: 6, ufs: 1 },
    ],
  });

  it('paints every UF with its REGION total, so the five regions read as blocks', () => {
    stubGlobals(regionFixture());
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs"
                     conventions={{ autoScale: true }} />,
    );
    fireEvent.click([...container.querySelectorAll('button')].find((b) => b.textContent === 'Região'));
    // Every UF of a region carries the SAME value — that is what makes it a region map
    // rather than a UF map with region labels.
    const byUf = Object.fromEntries(choroProps.data.map((d) => [d.uf, d[choroProps.valueKey]]));
    // PA and AM are both Norte, so they must carry the SAME value — that is what makes
    // this a region map rather than a UF map wearing region labels.
    expect(byUf.PA).toBe(byUf.AM);
    expect(byUf.PA).not.toBe(byUf.SP);
  });

  it('offers Barras too — five blocks rank worse than five bars', () => {
    stubGlobals(regionFixture());
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs"
                     conventions={{ autoScale: true }} />,
    );
    fireEvent.click([...container.querySelectorAll('button')].find((b) => b.textContent === 'Região'));
    expect(container.querySelector('[aria-label="Visualização da região"]')).toBeTruthy();
    fireEvent.click([...container.querySelectorAll('button')].find((b) => b.textContent === 'Barras'));
    expect(container.querySelector('.region-bars, .regionbars')).toBeTruthy();
  });

  it('clicking a region narrows to ITS UFs, not just the cascade parent', () => {
    // `regions` alone is a cascade parent (it steers the filter MENU); `states` is what
    // reaches the data. Setting only the former would move the chip and nothing else.
    stubGlobals(regionFixture());     // stubGlobals installs its own patchFilter mock…
    const patch = vi.fn();
    window.patchFilter = patch;       // …so ours has to land AFTER it
    const { container } = render(
      <ViewGeography families={['mass']} summary={{}} database="ibge_pevs"
                     conventions={{ autoScale: true }} />,
    );
    fireEvent.click([...container.querySelectorAll('button')].find((b) => b.textContent === 'Região'));
    choroProps.onSelect('PA');
    const arg = patch.mock.calls.at(-1)[0];
    expect(arg.regions).toEqual(['N']);
    expect(arg.states).toContain('PA');
    // A region click must also drop any leftover sub-UF narrowing, same as a UF click.
    expect(arg.munis).toBeNull();
  });
});
