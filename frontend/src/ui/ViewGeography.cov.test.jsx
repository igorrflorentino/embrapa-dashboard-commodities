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

// The REAL drill module, not a stub: it is pure and dependency-free, and a stubbed
// level derivation would let the view and the test disagree about where the researcher
// is — the exact class of divergence that shipped bugs earlier today.
import './geoDrill.js';
import { cleanup, fireEvent, render } from '@testing-library/react';

// The click-a-UF-to-filter rule lives in geoSelect.js (shared with Visão geral and
// Qualidade) and self-registers on window, exactly as main.jsx loads it. Imported
// rather than stubbed so these tests exercise the REAL selection logic — including
// the sub-UF facet reset, which is the part that is easy to get wrong.
import './geoSelect.js';

// Captured props from the stubbed chart widgets, so we can assert what each branch fed.
let choroProps, tileMapProps, heatmapProps, barChartCalls, productsByUfCalls, muniMapProps, regionBarsProps;

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
  choroProps = tileMapProps = heatmapProps = muniMapProps = regionBarsProps = undefined;
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
// The granularity is no longer a control — it is derived from the selection (geoDrill).
// These say, in the test's own words, WHERE the view is: nothing selected is Brasil (the
// região level), a region puts you among its UFs, one UF puts you among its municípios.
const AT_REGIAO = {};
const AT_UF = { regions: ['N'] };
const atMunicipio = (uf = 'PA') => ({ states: [uf] });

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
  it('opens at Brasil — the região level — with no filter configured', () => {
    // The default used to be UF, chosen by a segmented control that also offered a
    // Município option leading nowhere. Now the view opens at the top of the trail
    // and the researcher drills DOWN by clicking, so there is no unreachable state
    // to explain away.
    stubGlobals(fullFixture({
      ufData: [
        { uf: 'PA', region: 'N', value: 75, q_mass: 30, q_vol: 8, q_count: 12, real: true },
        { uf: 'SP', region: 'SE', value: 25, q_mass: 10, q_vol: 4, q_count: 6, real: true },
      ],
    }));
    const { container } = render(
      <ViewGeography
        families={['mass', 'volume']}
        summary={{}}
        database="ibge_pevs"
        conventions={{ currency: 'BRL', correction: 'IPCA', autoScale: true }}
      />
    );
    expect(container.textContent).toContain('Distribuição por região');
    // The trail is the new orientation device, and it starts at Brasil.
    expect(container.querySelector('.geo-trail').textContent).toBe('Brasil');
    // Region map over UF geometry: each UF painted with ITS region's total.
    expect(choroProps).toBeTruthy();
    expect(choroProps.data.map((u) => u.uf)).toEqual(['PA', 'SP']);
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
    render(<ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: true }} />);
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
    render(<ViewGeography families={['mass']} summary={AT_UF} database="mdic_comex" conventions={{ autoScale: true }} />);
    expect(choroProps.data.map((u) => u.uf)).toEqual(['PA', 'SP']); // ND dropped
    expect(choroProps.data.some((u) => u.uf === 'ND')).toBe(false);
  });

  it('switching the metric to massa rescales the maps by the mass multiplier', () => {
    stubGlobals(fullFixture());
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: true }} />
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
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    const blocos = [...container.querySelectorAll('.seg-opt')].find((b) => b.textContent === 'Blocos');
    fireEvent.click(blocos);
    expect(tileMapProps).toBeTruthy();
    expect(tileMapProps.data.length).toBe(2);
  });

  it('the "Região" granularity renders RegionBars once, WITHOUT the redundant ranking/soma cards (EST-2)', () => {
    stubGlobals(fullFixture());
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_REGIAO} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    // The região level opens as a MAP (the Barras toggle is one click away, covered
    // separately); what EST-2 is about is the DUPLICATION below it.
    expect(choroProps).toBeTruthy();
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
    render(
      <ViewGeography families={['mass']} summary={atMunicipio()} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
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
      <ViewGeography families={['mass']} summary={{ munis: ['1500140', '3548500'] }}
                     database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    expect(muniMapProps).toBeUndefined();
    expect(container.querySelector('.muni-list')).toBeTruthy();
    expect(container.textContent).toContain('Belém');
    expect(container.textContent).toContain('Santos');
  });

  it('the município granularity the município level is UNREACHABLE without a UF — the old dead end is gone', () => {
    // This used to assert a card that told the researcher to go configure a filter.
    // With the level derived from the selection, "município with nothing selected" is
    // not a state the view can be in, so the card has nothing to explain.
    stubGlobals(fullFixture({ topMunis: [], muniYearlySeries: [] }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_REGIAO} database="ibge_pevs" conventions={{ autoScale: true }} />,
    );
    expect(container.textContent).not.toContain('recortar a geografia');
    expect(container.textContent).toContain('Distribuição por região');
  });
});

describe('ViewGeography — gating and honest-note branches', () => {
  it('a UF-only banco stops AT the UF level — a state there is not a doorway', () => {
    // COMEX is origin-UF only. Selecting a state must not drill into municípios it has
    // no data for; the trail simply ends there.
    stubGlobals(fullFixture(), { geoLevel: 'uf' });
    const { container } = render(
      <ViewGeography families={['mass']} summary={atMunicipio()} database="mdic_comex" conventions={{ autoScale: true }} />,
    );
    expect(container.textContent).toContain('Distribuição por UF');
    expect(container.textContent).not.toContain('Distribuição por município');
  });

  it('shows the basket note when the territorial split is not basket-filtered', () => {
    stubGlobals(fullFixture({ notFilteredByBasket: true }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: true }} />
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
      <ViewGeography families={['mass', 'volume']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: true }} />
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
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    expect(container.textContent).toContain('(parcial)');
    expect(container.textContent).toContain('o último ano com dados por UF');
  });

  it('flags the map year as "(parcial)" from the calendar-incomplete latest year', () => {
    stubGlobals(fullFixture({ ufLatestYear: 2024 }), {
      meta: { latest: { yearComplete: false, completeYear: 2023 } },
    });
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: true }} />
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
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: true }} />
    );
    expect(container.textContent).toContain('Estado produtor');
    expect(container.textContent).not.toContain('Maiores estados produtores');
  });
});

describe('ViewGeography — empty geo + products-by-UF base table', () => {
  it('renders an honest empty-state instead of a blank Heatmap when there is no history', () => {
    stubGlobals(fullFixture({ ufYearlySeries: [] }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: true }} />
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
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: false }} />
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
    render(
      <ViewGeography families={['mass']} summary={AT_REGIAO} database="ibge_pevs"
                     conventions={{ autoScale: true }} />,
    );
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
      <ViewGeography families={['mass']} summary={AT_REGIAO} database="ibge_pevs"
                     conventions={{ autoScale: true }} />,
    );
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
    render(
      <ViewGeography families={['mass']} summary={AT_REGIAO} database="ibge_pevs"
                     conventions={{ autoScale: true }} />,
    );
    choroProps.onSelect('PA');
    const arg = patch.mock.calls.at(-1)[0];
    expect(arg.regions).toEqual(['N']);
    expect(arg.states).toContain('PA');
    // A region click must also drop any leftover sub-UF narrowing, same as a UF click.
    expect(arg.munis).toBeNull();
  });
});

// ── The trail's crumbs have to actually go somewhere ─────────────────────────

describe('ViewGeography — navigating back up the trail', () => {
  afterEach(() => { delete window.patchFilter; });

  const deep = { regions: ['N'], states: ['PA'] };
  const universe = [
    { uf: 'PA', region: 'N', value: 75, q_mass: 30, q_vol: 8, q_count: 12, real: true },
    { uf: 'AM', region: 'N', value: 20, q_mass: 8, q_vol: 2, q_count: 3, real: true },
    { uf: 'SP', region: 'SE', value: 25, q_mass: 10, q_vol: 4, q_count: 6, real: true },
  ];

  it('the região crumb re-enters the region with ALL its UFs, not just the selected one', () => {
    // ufsOfRegion used to read the CURRENT (already-narrowed) UF rows, so from inside
    // Brasil › Norte › Pará the Norte "contained" exactly one state. Re-entering with
    // states:['PA'] is still município level: the trail did not move and the click read
    // as dead. The region's membership must come from the UF universe.
    const patch = vi.fn();
    stubGlobals(fullFixture({
      ufData: [{ uf: 'PA', region: 'N', value: 75, q_mass: 30, q_vol: 8, q_count: 12, real: true }],
      ufDataFull: universe,
    }));
    window.patchFilter = patch;
    const { container } = render(
      <ViewGeography families={['mass']} summary={deep} database="ibge_pevs" conventions={{ autoScale: true }} />,
    );
    const norte = [...container.querySelectorAll('.geo-crumb')].find((b) => b.textContent === 'Norte');
    expect(norte).toBeTruthy();
    fireEvent.click(norte);
    const arg = patch.mock.calls.at(-1)[0];
    expect(arg.regions).toEqual(['N']);
    expect(arg.states.sort()).toEqual(['AM', 'PA']);   // the whole region, not the survivor
    expect(arg.munis).toBeNull();
  });

  it('the Brasil crumb clears every geography facet', () => {
    const patch = vi.fn();
    stubGlobals(fullFixture({ ufDataFull: universe }));
    window.patchFilter = patch;
    const { container } = render(
      <ViewGeography families={['mass']} summary={deep} database="ibge_pevs" conventions={{ autoScale: true }} />,
    );
    fireEvent.click([...container.querySelectorAll('.geo-crumb')].find((b) => b.textContent === 'Brasil'));
    const arg = patch.mock.calls.at(-1)[0];
    for (const k of ['regions', 'states', 'munis', 'mesos', 'micros', 'inters', 'imediatas']) {
      expect(`${k}:${arg[k]}`).toBe(`${k}:null`);
    }
  });

  it('the current level is not a link — it is where you already are', () => {
    stubGlobals(fullFixture({ ufDataFull: universe }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={deep} database="ibge_pevs" conventions={{ autoScale: true }} />,
    );
    const crumbs = [...container.querySelectorAll('.geo-crumb')];
    expect(crumbs.at(-1).disabled).toBe(true);
    expect(crumbs.slice(0, -1).every((b) => !b.disabled)).toBe(true);
  });
});

describe('ViewGeography — the loading notice names what is being waited on', () => {
  it('announces the município while ITS history loads, not the state', () => {
    // Clicking a município sets a sub-UF facet, which is exactly what the old guard
    // (`!subUfActive`) excluded — so the one gesture the drill-down made most common
    // was the one that loaded in silence.
    stubGlobals(fullFixture({
      subUfActive: true, subUfLoaded: false, muniYearlySeries: [], topMunis: [],
    }), { geoLevel: 'municipio' });
    window.geoMesh = () => [{ cityCode: '1500107', cityName: 'Abaetetuba', uf: 'PA' }];
    const { container } = render(
      <ViewGeography families={['mass']} summary={{ states: ['PA'], munis: ['1500107'] }}
                     database="ibge_pevs" conventions={{ autoScale: true }} />,
    );
    expect(container.textContent).toContain('Abaetetuba');
    expect(container.textContent).toMatch(/Carregando/);
  });
});

// ---------------------------------------------------------------------------
// "Soma por região" names a REGION but sums only the UFs that survived the filter.
// With the Pará selected it wrote "Norte" over the PARÁ's number — while the UF
// ranking beside it called that same number "Pará". Two names, one number, and the
// researcher has no way to tell which is the subject. Same wrong-subject defect as
// v1.33.25 (a UF's name over a region's value), one grain up.
//
// It reached the screen as a ONE-BAR bar chart, which is also the wrong form: bar
// length only means something against other bars, so a lone bar always fills the
// plot and encodes nothing — the only real datum sits on the axis.
// ---------------------------------------------------------------------------
describe('ViewGeography — "Soma por região" must name what it actually summed', () => {
  const oneRegion = (over = {}) => fullFixture({
    regionData: [{ id: 'N', label: 'Norte', value: 75, q_mass: 30, q_vol: 8, q_count: 12,
                   ufs: 1, ufsTotal: 7, partial: true, ufNames: ['Pará'], ...over }],
  });

  it('com uma região só, mostra o VALOR legível em vez de uma barra sozinha', () => {
    stubGlobals(oneRegion());
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: false }} />
    );
    expect(container.textContent).toContain('Soma por região');
    // A single bar is not a chart — the card must not draw one.
    expect(container.querySelector('.regionbars')).toBeNull();
    // ...and the number must be readable without squinting at an axis. Currency reads
    // as a PREFIX — the magnitude comes from the value itself, not from the axis.
    expect(container.querySelector('.kpi-val').textContent).toBe('R$ 75 mi');
  });

  it('unidade física fica como SUFIXO ("30 mil t"), não como prefixo de moeda', () => {
    // A value-less banco (the livestock herd is the real case) drops the Valor
    // dimension entirely, so the card falls to a physical unit.
    stubGlobals(fullFixture({
      ufData: [{ uf: 'PA', value: 0, q_mass: 30, q_vol: 0, q_count: 0, real: true }],
      regionData: [{ id: 'N', label: 'Norte', value: 0, q_mass: 30, q_vol: 0, q_count: 0,
                     ufs: 1, ufsTotal: 7, partial: true, ufNames: ['Pará'] }],
    }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: false }} />
    );
    expect(container.querySelector('.kpi-val').textContent).toBe('30 mil t');
  });

  it('diz que a soma é PARCIAL e nomeia as UFs que entraram — nunca "Norte" puro', () => {
    stubGlobals(oneRegion());
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: false }} />
    );
    const sub = container.querySelector('.kpi-sub').textContent;
    expect(sub).toContain('parcial');
    expect(sub).toContain('1 de 7 UFs');
    expect(sub).toContain('Pará');   // WHAT the number is, spelled out
  });

  it('quando a região está inteira, não inventa um aviso de parcialidade', () => {
    stubGlobals(oneRegion({ ufs: 7, ufsTotal: 7, partial: false,
                            ufNames: ['Pará', 'Amazonas', 'Acre', 'Rondônia'] }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: false }} />
    );
    const sub = container.querySelector('.kpi-sub').textContent;
    expect(sub).not.toContain('parcial');
    expect(sub).toContain('soma de 7 UFs');
    // A long list is truncated, but the count above it stays exact.
    expect(sub).toContain('e mais 1');
  });

  it('com duas ou mais regiões as barras voltam — e só a parcial leva a marca', () => {
    stubGlobals(fullFixture({
      regionData: [
        { id: 'N',  label: 'Norte',   value: 75, q_mass: 30, q_vol: 8, q_count: 12,
          ufs: 1, ufsTotal: 7, partial: true,  ufNames: ['Pará'] },
        { id: 'SE', label: 'Sudeste', value: 25, q_mass: 10, q_vol: 4, q_count: 6,
          ufs: 4, ufsTotal: 4, partial: false, ufNames: ['São Paulo'] },
      ],
    }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: false }} />
    );
    expect(container.querySelector('.regionbars')).toBeTruthy();
    const labels = regionBarsProps.data.map((r) => r.label);
    expect(labels).toEqual(['Norte (parcial)', 'Sudeste']);
  });

  // The invariant, swept: no region row may reach a chart or a stat under its bare
  // name while carrying only part of itself.
  it('INVARIANTE: nenhuma região parcial aparece com o nome pelado', () => {
    const partials = [
      { id: 'N',  label: 'Norte',   value: 75, q_mass: 30, q_vol: 8, q_count: 12,
        ufs: 1, ufsTotal: 7, partial: true, ufNames: ['Pará'] },
      { id: 'SE', label: 'Sudeste', value: 25, q_mass: 10, q_vol: 4, q_count: 6,
        ufs: 2, ufsTotal: 4, partial: true, ufNames: ['São Paulo', 'Minas Gerais'] },
    ];
    stubGlobals(fullFixture({ regionData: partials }));
    const { container } = render(
      <ViewGeography families={['mass']} summary={AT_UF} database="ibge_pevs" conventions={{ autoScale: false }} />
    );
    regionBarsProps.data.forEach((r, i) => {
      expect(r.label).not.toBe(partials[i].label);      // never the bare region name
      expect(r.label).toContain('parcial');
    });
    expect(container).toBeTruthy();
  });
});
