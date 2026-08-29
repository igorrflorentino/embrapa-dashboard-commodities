// dataFilters.test.js — applyFilters (ui/dataFilters.js) is the single seam
// the geo/value views read filtered datasets through. These lock the F1.5 fix:
// a product basket must NOT fabricate the per-UF / per-region territorial split
// by scaling every state uniformly by selected/all (there is no per-product × UF
// grain in the snapshot). The real state totals must pass through unchanged and
// the honest `notFilteredByBasket` flag must be raised so the views can say so.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { decorateSnapshot } from './decorate.js';

// Several describe blocks below stub window.geoMesh/municipioYearly inside
// individual `it`s without resetting them afterwards — harmless as long as
// nothing in a LATER describe block's tests happens to wake the sub-UF cascade.
// applyFilters now also engages that cascade for a single selected UF (EST-5: a
// município ranking shouldn't require first narrowing to a mesorregião), so a
// leaked GEO_MESH/municipioYearly stub from an earlier block can silently steer a
// later `states: ['PA']` test through the (unrelated) mesh-rollup path instead of
// the plain state filter it means to exercise. Reset both after every test so
// each one only ever sees the stubs it sets itself.
afterEach(() => {
  delete window.geoMesh;
  delete window.municipioYearly;
});

// applyFilters reads the active banco's snapshot from window.dataStore.get and a
// few registry globals. Stub the minimum so the IIFE runs in isolation (no full
// UI boot). Each test reloads the module so the IIFE re-binds window.applyFilters.
const SNAP = {
  products: [
    { code: 'A', name: 'Açaí', unit: 't', family: 'mass' },
    { code: 'B', name: 'Babaçu', unit: 't', family: 'mass' },
    { code: 'C', name: 'Carnaúba', unit: 't', family: 'mass' },
  ],
  productTS: {
    A: [{ y: 2020, v: 30, q: 3, family: 'mass' }, { y: 2021, v: 33, q: 3.3, family: 'mass' }],
    B: [{ y: 2020, v: 20, q: 2, family: 'mass' }, { y: 2021, v: 22, q: 2.2, family: 'mass' }],
    C: [{ y: 2020, v: 10, q: 1, family: 'mass' }, { y: 2021, v: 11, q: 1.1, family: 'mass' }],
  },
  overviewTS: [{ y: 2020, v: 0.06 }, { y: 2021, v: 0.066 }],
  ufData: [
    { uf: 'PA', name: 'Pará', region: 'N', value: 100, q_mass: 50, q_vol: 0 },
    { uf: 'RS', name: 'Rio Grande do Sul', region: 'S', value: 40, q_mass: 20, q_vol: 0 },
  ],
  // Per-(UF, year) history backing the heatmap AND the map's true-year derivation.
  // ufData above is the latest-year scope (2021 here); ufYearly carries both years.
  ufYearly: [
    { year: 2020, uf: 'PA', name: 'Pará', region: 'N', value: 90, q_mass: 45, q_vol: 0 },
    { year: 2021, uf: 'PA', name: 'Pará', region: 'N', value: 100, q_mass: 50, q_vol: 0 },
    { year: 2020, uf: 'RS', name: 'Rio Grande do Sul', region: 'S', value: 36, q_mass: 18, q_vol: 0 },
    { year: 2021, uf: 'RS', name: 'Rio Grande do Sul', region: 'S', value: 40, q_mass: 20, q_vol: 0 },
  ],
  quality: [{ id: 'OK', count: 9 }],
  qualityTs: [],
  topMunis: [],
  regions: [{ id: 'N' }, { id: 'S' }],
};

async function loadApplyFilters() {
  vi.resetModules();
  window.dataStore = { get: () => SNAP };
  window.REGIONS = SNAP.regions;
  window.VIZ_SCALE = ['var(--viz-1)'];
  window.VALUE_PRESETS = [];
  window.MUNI_PICKER_NAMES = new Set();
  window.snapshotFor = () => null;
  await import('../ui/dataFilters.js');
  return window.applyFilters;
}

// Mesh + município cube fixtures: 3 PA municípios across 2 mesorregiões. A meso
// filter must narrow the per-UF total to only that meso's municípios (rolled up to
// UF × year via the mesh) — the sub-UF geography feature.
const GEO_MESH = [
  { cityCode: '1', cityName: 'Cidade 1', uf: 'PA', region: 'N',
    meso: { code: 'M1', name: 'Meso 1' }, micro: { code: 'mi1', name: 'Mic 1' },
    intermediaria: { code: 'I1', name: 'Int 1' }, imediata: { code: 'im1', name: 'Ime 1' } },
  { cityCode: '2', cityName: 'Cidade 2', uf: 'PA', region: 'N',
    meso: { code: 'M1', name: 'Meso 1' }, micro: { code: 'mi2', name: 'Mic 2' },
    intermediaria: { code: 'I1', name: 'Int 1' }, imediata: { code: 'im2', name: 'Ime 2' } },
  { cityCode: '3', cityName: 'Cidade 3', uf: 'PA', region: 'N',
    meso: { code: 'M2', name: 'Meso 2' }, micro: { code: 'mi3', name: 'Mic 3' },
    intermediaria: { code: 'I2', name: 'Int 2' }, imediata: { code: 'im3', name: 'Ime 3' } },
];
const MUNI_CUBE = [
  { year: 2021, cityCode: '1', uf: 'PA', value: 60, q_mass: 30, q_vol: 0, q_count: 0 },
  { year: 2021, cityCode: '2', uf: 'PA', value: 30, q_mass: 15, q_vol: 0, q_count: 0 },
  { year: 2021, cityCode: '3', uf: 'PA', value: 10, q_mass: 5, q_vol: 0, q_count: 0 },
];

describe('applyFilters — sub-UF (mesorregião) narrowing rolls the município cube up by UF', () => {
  beforeEach(() => { delete window.applyFilters; delete window.geoMesh; delete window.municipioYearly; });

  it('sums only the selected mesorregião’s municípios into the per-UF total', async () => {
    const applyFilters = await loadApplyFilters();
    window.geoMesh = () => GEO_MESH;
    window.municipioYearly = () => MUNI_CUBE;
    // Meso M1 = cidades 1 + 2 (value 60 + 30 = 90); cidade 3 (M2, value 10) excluded.
    const f = applyFilters({ mesos: ['M1'] }, 'ibge_pevs');
    const pa = f.ufData.find((u) => u.uf === 'PA');
    expect(pa.value).toBe(90); // NOT the all-meso 100 — the M2 município is dropped
  });

  it('builds topMunis from the cube, ranked, named via the mesh (GEO-1)', async () => {
    const applyFilters = await loadApplyFilters();
    window.geoMesh = () => GEO_MESH;
    window.municipioYearly = () => MUNI_CUBE;
    // Meso M1 = cidades 1 (60) + 2 (30); cidade 3 (M2) excluded. Ranked desc, named.
    const f = applyFilters({ mesos: ['M1'] }, 'ibge_pevs');
    expect(f.topMunis.map((m) => [m.city, m.value])).toEqual([
      ['Cidade 1', 60],
      ['Cidade 2', 30],
    ]);
  });

  it('topMunis is empty without a sub-UF narrowing (no always-empty legacy path)', async () => {
    const applyFilters = await loadApplyFilters();
    window.geoMesh = () => GEO_MESH;
    window.municipioYearly = () => MUNI_CUBE;
    const f = applyFilters({}, 'ibge_pevs'); // no geo narrowing → cube not fetched
    expect(f.topMunis).toEqual([]);
  });

  it('holds at a loading state while the município cube has not landed', async () => {
    const applyFilters = await loadApplyFilters();
    window.geoMesh = () => GEO_MESH;
    window.municipioYearly = () => null; // fetch pending
    const f = applyFilters({ mesos: ['M1'] }, 'ibge_pevs');
    expect(f.geoComboPending).toBe(true);
  });

  it('loaded-but-EMPTY cube reads as honest empty — not stuck-loading, not all-UF (audit B)', async () => {
    const applyFilters = await loadApplyFilters();
    window.geoMesh = () => GEO_MESH;
    window.municipioYearly = () => []; // fetched, zero rows (the meso produces none of the basket)
    const f = applyFilters({ mesos: ['M1'] }, 'ibge_pevs');
    expect(f.geoComboPending).toBe(false); // loaded-empty is NOT pending (no eternal spinner)
    expect(f.ufData).toEqual([]); // empty selection → empty map, NOT the all-UF fallback
  });
});

describe('applyFilters — no fabricated geographic split under a basket (F1.5)', () => {
  beforeEach(() => {
    // clean any prior window.applyFilters binding
    delete window.applyFilters;
  });

  it('serves the REAL per-UF totals unchanged when a basket narrows products', async () => {
    const applyFilters = await loadApplyFilters();
    // 1 of 3 products selected — the OLD code scaled every UF by 1/3.
    const f = applyFilters({ basket: ['A'] }, 'ibge_pevs');

    const pa = f.ufData.find((u) => u.uf === 'PA');
    // value/q_mass are the REAL state totals, NOT 100/3 ≈ 33.3.
    expect(pa.value).toBe(100);
    expect(pa.q_mass).toBe(50);
    expect(f.notFilteredByBasket).toBe(true); // honest flag raised
  });

  it('does NOT raise the flag when all products are selected (no narrowing)', async () => {
    const applyFilters = await loadApplyFilters();
    const f = applyFilters({ basket: ['A', 'B', 'C'] }, 'ibge_pevs');
    expect(f.notFilteredByBasket).toBe(false);
    expect(f.ufData.find((u) => u.uf === 'PA').value).toBe(100);
  });

  it('does NOT raise the flag when no basket filter is applied', async () => {
    const applyFilters = await loadApplyFilters();
    const f = applyFilters({}, 'ibge_pevs');
    expect(f.notFilteredByBasket).toBe(false);
  });

  it('still applies the exact STATE filter (real narrowing) on ufData', async () => {
    const applyFilters = await loadApplyFilters();
    const f = applyFilters({ states: ['PA'] }, 'ibge_pevs');
    expect(f.ufData.map((u) => u.uf)).toEqual(['PA']); // RS dropped
    expect(f.ufData[0].value).toBe(100); // unscaled
  });

  it('region totals derive from the REAL (unscaled) ufData', async () => {
    const applyFilters = await loadApplyFilters();
    const f = applyFilters({ basket: ['A'] }, 'ibge_pevs');
    const north = f.regionData.find((r) => r.id === 'N');
    expect(north.value).toBe(100); // = PA total, not PA/3
  });
});

describe('applyFilters — map year follows the DATA, not yearEnd (FINDING #1)', () => {
  beforeEach(() => { delete window.applyFilters; });

  it('derives ufLatestYear from the max UF year IN the window (not yearEnd)', async () => {
    const applyFilters = await loadApplyFilters();
    // endDate runs to 2025 but the latest UF rows stop at 2021 → the map's year is
    // the DATA year (2021), flagged partial because it falls short of yearEnd.
    const f = applyFilters({ startDate: '2020-01-01', endDate: '2025-01-01' }, 'ibge_pevs');
    expect(f.ufLatestYear).toBe(2021);
    expect(f.ufYearPartial).toBe(true);
    expect(f.yearEnd).toBe(2025); // yearEnd is untouched — only the MAP label changes
  });

  it('is not partial when the window end coincides with the latest UF year', async () => {
    const applyFilters = await loadApplyFilters();
    const f = applyFilters({ startDate: '2020-01-01', endDate: '2021-12-01' }, 'ibge_pevs');
    expect(f.ufLatestYear).toBe(2021);
    expect(f.ufYearPartial).toBe(false);
  });

  it('respects the window: a window ending in 2020 yields the 2020 map year', async () => {
    const applyFilters = await loadApplyFilters();
    const f = applyFilters({ startDate: '2020-01-01', endDate: '2020-12-01' }, 'ibge_pevs');
    expect(f.ufLatestYear).toBe(2020);
    expect(f.ufYearPartial).toBe(false);
  });

  it('falls back to yearEnd (never partial) when ufYearly is absent', async () => {
    vi.resetModules();
    delete window.applyFilters;
    // A snapshot without ufYearly (synthetic / older payload).
    const noYearly = { ...SNAP };
    delete noYearly.ufYearly;
    window.dataStore = { get: () => noYearly };
    window.REGIONS = SNAP.regions;
    window.VIZ_SCALE = ['var(--viz-1)'];
    window.VALUE_PRESETS = [];
    window.MUNI_PICKER_NAMES = new Set();
    window.snapshotFor = () => null;
    await import('../ui/dataFilters.js');
    const f = window.applyFilters({ startDate: '2020-01-01', endDate: '2025-01-01' }, 'ibge_pevs');
    expect(f.ufLatestYear).toBe(f.yearEnd); // 2025
    expect(f.ufYearPartial).toBe(false); // no data to prove a shortfall → don't cry partial
  });
});

describe('applyFilters — ufDataFull is the ALL-TIME UF universe (heads-up #1)', () => {
  beforeEach(() => { delete window.applyFilters; });

  it('counts every UF seen across years, not just the latest year', async () => {
    vi.resetModules();
    delete window.applyFilters;
    // A sparse-trade scenario: the LATEST year (2021, = ufData scope) has ONE UF,
    // but an earlier year had a second. The denominator must reflect both.
    const sparse = {
      ...SNAP,
      ufData: [{ uf: 'PA', name: 'Pará', region: 'N', value: 100, q_mass: 50, q_vol: 0 }],
      ufYearly: [
        { year: 2020, uf: 'PA', name: 'Pará', region: 'N', value: 90, q_mass: 45, q_vol: 0 },
        { year: 2020, uf: 'RS', name: 'Rio Grande do Sul', region: 'S', value: 36, q_mass: 18, q_vol: 0 },
        { year: 2021, uf: 'PA', name: 'Pará', region: 'N', value: 100, q_mass: 50, q_vol: 0 },
      ],
    };
    window.dataStore = { get: () => sparse };
    window.REGIONS = SNAP.regions;
    window.VIZ_SCALE = ['var(--viz-1)'];
    window.VALUE_PRESETS = [];
    window.MUNI_PICKER_NAMES = new Set();
    window.snapshotFor = () => null;
    await import('../ui/dataFilters.js');
    const f = window.applyFilters({ startDate: '2020-01-01', endDate: '2021-12-01' }, 'ibge_pevs');
    // ufData (latest year) has 1 UF, but the all-time universe has 2 (PA + RS).
    expect(f.ufData.length).toBe(1);
    expect(f.ufDataFull.map((u) => u.uf).sort()).toEqual(['PA', 'RS']);
  });

  it('falls back to the latest-year UF list when ufYearly is absent', async () => {
    const applyFilters = await loadApplyFilters();
    const noYearly = { ...SNAP };
    delete noYearly.ufYearly;
    window.dataStore = { get: () => noYearly };
    const f = applyFilters({}, 'ibge_pevs');
    expect(f.ufDataFull.map((u) => u.uf).sort()).toEqual(['PA', 'RS']);
  });
});

describe('applyFilters — geography-aware series (state filter reaches the hero)', () => {
  beforeEach(() => { delete window.applyFilters; delete window.geoYearly; });

  it('a STATE narrowing derives the series from the selected UFs, not the national curve', async () => {
    const applyFilters = await loadApplyFilters();
    // No basket → no cube; the state slice reads the all-products ufYearly grid.
    const f = applyFilters({ states: ['PA'] }, 'ibge_pevs');
    const t2020 = f.ts.find((d) => d.y === 2020);
    const t2021 = f.ts.find((d) => d.y === 2021);
    // PA-only: ufYearly PA value 90/100 (mi) → ts.v in bi (÷1000); q_mass = PA's 45/50.
    expect(t2020.v).toBeCloseTo(0.09); // 90 / 1000, NOT the national 60/1000
    expect(t2021.v).toBeCloseTo(0.1); // 100 / 1000
    expect(t2020.q_mass).toBe(45);
    expect(t2021.q_mass).toBe(50);
  });

  it('all-states selected is NOT a narrowing → keeps the national per-product series', async () => {
    const applyFilters = await loadApplyFilters();
    // window.UF_DATA absent → universe defaults to 27; 2 selected < 27 would narrow,
    // so to assert the no-narrowing path we declare the full 2-UF universe here.
    window.UF_DATA = [{ uf: 'PA' }, { uf: 'RS' }];
    const f = applyFilters({ states: ['PA', 'RS'] }, 'ibge_pevs');
    const t2020 = f.ts.find((d) => d.y === 2020);
    expect(t2020.v).toBeCloseTo(0.06); // national A+B+C = 60/1000, untouched
    delete window.UF_DATA;
  });
});

describe('applyFilters — regionData groups on decorated region CODES (M7)', () => {
  beforeEach(() => { delete window.applyFilters; });

  // regionData groups ufData by `region === r.id` (a 2-letter code). decorate.js
  // normalizes an API display-name region ("Norte") to its code BEFORE applyFilters
  // reads the snapshot — without that, RegionBars would empty. This locks the join.
  it('populates regionData when the API ufData carries display-NAME regions', async () => {
    const applyFilters = await loadApplyFilters();
    // The registries decorateSnapshot reads to normalize regions + fill tiles.
    window.UF_DATA = [
      { uf: 'PA', col: 4, row: 1, region: 'N', name: 'Pará' },
      { uf: 'RS', col: 3, row: 8, region: 'S', name: 'Rio Grande do Sul' },
    ];
    window.REGIONS = [
      { id: 'N', label: 'Norte' },
      { id: 'S', label: 'Sul' },
    ];
    // An API snapshot whose ufData regions arrive as DISPLAY NAMES (the M7 trigger).
    const decorated = decorateSnapshot({
      ufData: [
        { uf: 'PA', value: 100, q_mass: 50, q_vol: 0, region: 'Norte' },
        { uf: 'RS', value: 40, q_mass: 20, q_vol: 0, region: 'Sul' },
      ],
      regions: [{ id: 'N' }, { id: 'S' }],
    });
    // decorate must have rewritten the display names to codes.
    expect(decorated.ufData.map((u) => u.region).sort()).toEqual(['N', 'S']);

    window.dataStore = { get: () => ({ ...SNAP, ufData: decorated.ufData }) };
    const f = applyFilters({}, 'ibge_pevs');
    const north = f.regionData.find((r) => r.id === 'N');
    const south = f.regionData.find((r) => r.id === 'S');
    expect(north).toBeTruthy(); // would be undefined if region stayed "Norte"
    expect(north.value).toBe(100);
    expect(south.value).toBe(40);
  });
});

describe('applyFilters — basket-scoped (UF × year) cube drives the territorial split', () => {
  beforeEach(() => { delete window.applyFilters; delete window.geoYearly; });

  const CUBE = [
    { year: 2020, uf: 'PA', name: 'Pará', region: 'N', value: 50, q_mass: 25, q_vol: 0 },
    { year: 2021, uf: 'PA', name: 'Pará', region: 'N', value: 55, q_mass: 27, q_vol: 0 },
    { year: 2020, uf: 'RS', name: 'Rio Grande do Sul', region: 'S', value: 8, q_mass: 4, q_vol: 0 },
    { year: 2021, uf: 'RS', name: 'Rio Grande do Sul', region: 'S', value: 9, q_mass: 4.5, q_vol: 0 },
  ];

  it('uses the cube (not the all-products snapshot) and CLEARS the honest note', async () => {
    const applyFilters = await loadApplyFilters();
    window.geoYearly = () => CUBE; // basket cube loaded
    const f = applyFilters({ basket: ['A'] }, 'ibge_pevs');
    // Map reflects the basket cube's latest year (PA 2021 = 55), NOT the snapshot's 100.
    expect(f.ufData.find((u) => u.uf === 'PA').value).toBe(55);
    expect(f.notFilteredByBasket).toBe(false); // cube loaded → note cleared
    // No state filter → basket national = sum of ALL cube UFs per year.
    expect(f.ts.find((d) => d.y === 2021).v).toBeCloseTo((55 + 9) / 1000);
  });

  it('combines the cube with a state filter (true product × UF)', async () => {
    const applyFilters = await loadApplyFilters();
    window.geoYearly = () => CUBE;
    const f = applyFilters({ basket: ['A'], states: ['PA'] }, 'ibge_pevs');
    expect(f.ufData.map((u) => u.uf)).toEqual(['PA']); // RS dropped
    expect(f.ts.find((d) => d.y === 2021).v).toBeCloseTo(55 / 1000); // PA-only, basket cube
    expect(f.notFilteredByBasket).toBe(false);
  });

  it('keeps the honest note while the cube is still loading (geoYearly → null)', async () => {
    const applyFilters = await loadApplyFilters();
    window.geoYearly = () => null; // fetch pending
    const f = applyFilters({ basket: ['A'] }, 'ibge_pevs');
    expect(f.notFilteredByBasket).toBe(true); // not yet basket-aware → still honest
    expect(f.ufData.find((u) => u.uf === 'PA').value).toBe(100); // snapshot all-products
  });
});

// ---------------------------------------------------------------------------
// A region row NAMES a region but SUMS only the UFs that survived the state filter.
// Select the Pará and `{ id: 'N', label: 'Norte' }` carries the PARÁ's number — which
// the Geografia view then printed as "Soma por região → Norte", beside a UF ranking
// calling that same number "Pará". Summing only what is filtered is right; presenting
// it under the region's bare name is the wrong-subject defect of v1.33.25, one grain
// up. The row must therefore carry what it is made of, so a card can say so.
// ---------------------------------------------------------------------------
describe('applyFilters — regionData declares WHAT it summed (parcialidade)', () => {
  // Two NORTE states, so filtering to one leaves the region genuinely partial.
  const SNAP_2N = {
    products: [{ code: 'A', name: 'Açaí', unit: 't', family: 'mass' }],
    productTS: { A: [{ y: 2021, v: 33, q: 3.3, family: 'mass' }] },
    overviewTS: [{ y: 2021, v: 0.066 }],
    ufData: [
      { uf: 'PA', name: 'Pará', region: 'N', value: 100, q_mass: 50, q_vol: 0 },
      { uf: 'AM', name: 'Amazonas', region: 'N', value: 55, q_mass: 25, q_vol: 0 },
      { uf: 'RS', name: 'Rio Grande do Sul', region: 'S', value: 40, q_mass: 20, q_vol: 0 },
    ],
    ufYearly: [
      { year: 2021, uf: 'PA', name: 'Pará', region: 'N', value: 100, q_mass: 50, q_vol: 0 },
      { year: 2021, uf: 'AM', name: 'Amazonas', region: 'N', value: 55, q_mass: 25, q_vol: 0 },
      { year: 2021, uf: 'RS', name: 'Rio Grande do Sul', region: 'S', value: 40, q_mass: 20, q_vol: 0 },
    ],
    quality: [{ id: 'OK', count: 9 }], qualityTs: [], topMunis: [],
    regions: [{ id: 'N', label: 'Norte' }, { id: 'S', label: 'Sul' }],
  };

  async function load2N() {
    vi.resetModules();
    window.dataStore = { get: () => SNAP_2N };
    window.REGIONS = SNAP_2N.regions;
    window.VIZ_SCALE = ['var(--viz-1)'];
    window.VALUE_PRESETS = [];
    window.MUNI_PICKER_NAMES = new Set();
    window.snapshotFor = () => null;
    await import('../ui/dataFilters.js');
    return window.applyFilters;
  }

  beforeEach(() => { delete window.applyFilters; });

  it('sem filtro, o Norte é o Norte inteiro e NÃO é marcado como parcial', async () => {
    const applyFilters = await load2N();
    const n = applyFilters({}, 'ibge_pevs').regionData.find((r) => r.id === 'N');
    expect(n.value).toBe(155);          // 100 + 55
    expect(n.ufs).toBe(2);
    expect(n.ufsTotal).toBe(2);
    expect(n.partial).toBe(false);
  });

  it('filtrando um estado, o valor é o DAQUELE estado — e a linha diz isso', async () => {
    const applyFilters = await load2N();
    const f = applyFilters({ states: ['PA'] }, 'ibge_pevs');
    const n = f.regionData.find((r) => r.id === 'N');
    // O número continua sendo só o do filtro (a regra de nunca exibir dado fora dele)...
    expect(n.value).toBe(100);
    expect(n.value).toBe(f.ufData.find((u) => u.uf === 'PA').value);
    // ...mas agora a linha declara que 100 NÃO é o Norte.
    expect(n.partial).toBe(true);
    expect(n.ufs).toBe(1);
    expect(n.ufsTotal).toBe(2);         // o denominador é o MESMO caminho, sem o filtro
    expect(n.ufNames).toEqual(['Pará']);
  });

  it('nomeia as UFs somadas, maior primeiro, para a lista truncada não mentir', async () => {
    const applyFilters = await load2N();
    const n = applyFilters({ states: ['PA', 'AM'] }, 'ibge_pevs').regionData.find((r) => r.id === 'N');
    expect(n.ufNames).toEqual(['Pará', 'Amazonas']);   // 100 antes de 55
    expect(n.partial).toBe(false);      // as duas UFs do Norte estão presentes
  });

  it('o denominador é o do BANCO, não a geografia — não inventa UFs sem dado', async () => {
    // O Sul tem 3 UFs no Brasil, mas só o RS existe neste banco. Selecioná-lo NÃO
    // torna o Sul parcial: nada foi escondido do usuário.
    const applyFilters = await load2N();
    const s = applyFilters({ states: ['RS'] }, 'ibge_pevs').regionData.find((r) => r.id === 'S');
    expect(s.ufsTotal).toBe(1);
    expect(s.partial).toBe(false);
  });
});
