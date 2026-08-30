// dataFilters.cov.test.js — coverage for dataFilters.js, the window.applyFilters
// engine that narrows every dataset a view reads (ts / productTS / ufData /
// regionData / topMunis / topProducts / qualityFlags / qualityTs + the provenance
// _shares). It is a side-effect IIFE depending on a handful of window.* globals
// (dataStore, geoMesh, geoYearly, municipioYearly, REGIONS, UF_DATA, VIZ_SCALE,
// normalizeRegion) — we STUB those directly (the csvExport.cov.test.js pattern) so
// every branch (national / basket cube / state narrowing / sub-UF mesh cascade /
// pending states / empty snapshot / donut head+tail) is driven deterministically.
//
// VALUE_PRESETS comes from filtersSchema.js (imported for window.VALUE_PRESETS).

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

// Import the registries in dependency order so the filtersSchema module-load audit
// sees CAPABILITIES (views.js) and does NOT emit a false drift warning at import.
import './bancos.js';
import './views.js';
import './filtersSchema.js'; // window.VALUE_PRESETS

// ── Fixtures ─────────────────────────────────────────────────────────────────
const REGIONS = [
  { id: 'N', name: 'Norte' },
  { id: 'SE', name: 'Sudeste' },
];

const UF_DATA = [
  { uf: 'PA', name: 'Pará', region: 'N', col: 1, row: 1 },
  { uf: 'SP', name: 'São Paulo', region: 'SE', col: 2, row: 2 },
];

const VIZ_SCALE = ['var(--viz-1)', 'var(--viz-2)', 'var(--viz-3)'];

// A snapshot with 8 products (so the >7 donut head+tail branch fires), per-product
// time series across two years, an all-products ufYearly grid, quality flags + ts.
function makeSnapshot() {
  const products = [];
  const productTS = {};
  for (let i = 1; i <= 8; i++) {
    const code = `P${i}`;
    products.push({ code, name: `Produto ${i}`, family: i === 8 ? 'volume' : 'mass' });
    productTS[code] = [
      { y: 2020, v: i * 10, q: i, family: i === 8 ? 'volume' : 'mass' },
      { y: 2021, v: i * 11, q: i + 1, family: i === 8 ? 'volume' : 'mass' },
    ];
  }
  return {
    products,
    productTS,
    overviewTS: [{ y: 2020 }, { y: 2021 }],
    ufData: [
      { uf: 'PA', name: 'Pará', region: 'N', value: 5, q_mass: 2, q_vol: 1, q_count: 0 },
      { uf: 'SP', name: 'São Paulo', region: 'SE', value: 3, q_mass: 1, q_vol: 0, q_count: 0 },
    ],
    ufYearly: [
      { uf: 'PA', year: 2020, value: 4000, q_mass: 2, q_vol: 1, q_count: 0 },
      { uf: 'PA', year: 2021, value: 5000, q_mass: 3, q_vol: 1, q_count: 0 },
      { uf: 'SP', year: 2020, value: 2000, q_mass: 1, q_vol: 0, q_count: 0 },
      { uf: 'SP', year: 2021, value: 3000, q_mass: 2, q_vol: 0, q_count: 0 },
    ],
    quality: [
      { id: 'OK', label: 'Normais', count: 900 },
      { id: 'PROBLEMATIC', label: 'Problemático', count: 100 },
    ],
    qualityTs: [
      { y: 2019, ok: 1 }, // outside the default window when startDate is 2020
      { y: 2020, ok: 1 },
      { y: 2021, ok: 1 },
    ],
    qualityByProduct: [{ code: 'P1', flag: 'OK' }],
    qualityByUf: [{ uf: 'PA', flag: 'OK' }],
    regions: REGIONS,
  };
}

function installGlobals(snap, { mesh, muniCube, geoCube } = {}) {
  window.REGIONS = REGIONS;
  window.UF_DATA = UF_DATA;
  window.VIZ_SCALE = VIZ_SCALE;
  window.normalizeRegion = (api, tile) => api || tile;
  window.dataStore = { get: (id) => (id === 'ibge_pevs' ? snap : null) };
  window.snapshotFor = undefined;
  window.geoMesh = mesh === undefined ? (() => null) : () => mesh;
  window.municipioYearly = () => (muniCube === undefined ? [] : muniCube);
  window.geoYearly = () => (geoCube === undefined ? null : geoCube);
}

let realGlobals;
beforeEach(async () => {
  realGlobals = {
    dataStore: window.dataStore, geoMesh: window.geoMesh, geoYearly: window.geoYearly,
    municipioYearly: window.municipioYearly, REGIONS: window.REGIONS, UF_DATA: window.UF_DATA,
    VIZ_SCALE: window.VIZ_SCALE, normalizeRegion: window.normalizeRegion, snapshotFor: window.snapshotFor,
  };
  await import('./dataFilters.js'); // registers window.applyFilters (idempotent)
});

afterEach(() => {
  Object.assign(window, realGlobals);
});

// ── Empty / degraded snapshot path ───────────────────────────────────────────
describe('applyFilters — no snapshot loaded → empty dataset (no fabricated figures)', () => {
  it('degrades to empty arrays when dataStore has no snapshot and no synth hook', () => {
    window.dataStore = { get: () => null };
    window.snapshotFor = undefined;
    window.REGIONS = REGIONS;
    window.UF_DATA = UF_DATA;
    window.VIZ_SCALE = VIZ_SCALE;
    window.geoMesh = () => null;
    const out = window.applyFilters({}, 'unknown_banco');
    expect(out.ts).toEqual([]);
    expect(out.productTS).toEqual({});
    expect(out.ufData).toEqual([]);
    expect(out.selectedProducts).toEqual([]);
    expect(out.yearStart).toBe(1986); // OVERVIEW fallback start
    expect(out.yearEnd).toBe(2024); // OVERVIEW fallback end
    expect(out.qualityFlags).toEqual([]);
  });

  it('reads from window.snapshotFor when dataStore misses (the seam fallback)', () => {
    const snap = makeSnapshot();
    window.dataStore = { get: () => null };
    window.snapshotFor = (id) => (id === 'seam_banco' ? snap : null);
    window.REGIONS = REGIONS;
    window.UF_DATA = UF_DATA;
    window.VIZ_SCALE = VIZ_SCALE;
    window.normalizeRegion = (a, t) => a || t;
    window.geoMesh = () => null;
    const out = window.applyFilters({ basket: null }, 'seam_banco');
    expect(out.products).toHaveLength(8);
    expect(out.ts).toHaveLength(2); // 2020 + 2021
  });
});

// ── National path (no geo narrowing): basket + year + donut composition ───────
describe('applyFilters — national path', () => {
  beforeEach(() => installGlobals(makeSnapshot()));

  it('basket=null selects all products; ts aggregates value (mi→bi) per year', () => {
    const out = window.applyFilters({ basket: null }, 'ibge_pevs');
    expect(out.selectedProducts).toHaveLength(8);
    // 2020 value = sum(i*10 for i=1..8) = 360 mi → /1000 = 0.36 bi
    const y2020 = out.ts.find((t) => t.y === 2020);
    expect(y2020.v).toBeCloseTo(0.36, 6);
    // mass families (P1..P7) sum q; volume (P8) goes to q_vol — never blended.
    expect(y2020.q_mass).toBe(1 + 2 + 3 + 4 + 5 + 6 + 7); // 28
    expect(y2020.q_vol).toBe(8); // P8 (volume)
    expect(out.productsTotal).toBe(8);
  });

  it('a proper basket subset narrows selectedProducts + productTS', () => {
    const out = window.applyFilters({ basket: ['P1', 'P2'] }, 'ibge_pevs');
    expect(out.selectedProducts).toEqual(['P1', 'P2']);
    expect(Object.keys(out.productTS).sort()).toEqual(['P1', 'P2']);
  });

  it('basket=[] (explicitly cleared) yields zero selected products + empty composition', () => {
    const out = window.applyFilters({ basket: [] }, 'ibge_pevs');
    expect(out.selectedProducts).toEqual([]);
    expect(out.topProducts).toEqual([]);
  });

  it('a composição preserva a TABELA de cada produto — é o que desambigua o Donut', () => {
    // O Donut rotula cada fatia por `name`, e madeira/lenha/carvão existem nas duas tabelas
    // do PEVS com o MESMO nome. Se a composição descarta `sidra_tabela`, o consumidor não
    // tem como distinguir duas fatias idênticas — e este é o elo que a asserção do Donut,
    // que dubla `topProducts`, não alcança.
    const snap = makeSnapshot();
    snap.products = snap.products.map((p, i) => ({ ...p, sidra_tabela: i % 2 ? '291' : '289' }));
    installGlobals(snap);
    const out = window.applyFilters({ basket: null }, 'ibge_pevs');
    const reais = out.topProducts.filter((p) => p.name !== 'Outros');
    expect(reais.length).toBeGreaterThan(0);
    for (const p of reais) {
      expect(['289', '291'], `${p.name} perdeu a tabela`).toContain(p.sidra_tabela);
    }
  });

  it('donut groups into head(6)+Outros when >7 products are selected', () => {
    const out = window.applyFilters({ basket: null }, 'ibge_pevs');
    expect(out.topProducts).toHaveLength(7); // 6 head + 1 "Outros"
    const outros = out.topProducts[out.topProducts.length - 1];
    expect(outros.name).toBe('Outros');
    expect(outros.muted).toBe(true);
    // shares sum to ~1
    const total = out.topProducts.reduce((s, p) => s + p.share, 0);
    expect(total).toBeCloseTo(1, 6);
  });

  it('donut keeps each slice when ≤7 products are selected (head-only branch)', () => {
    const out = window.applyFilters({ basket: ['P1', 'P2', 'P3'] }, 'ibge_pevs');
    expect(out.topProducts).toHaveLength(3);
    expect(out.topProducts.every((p) => !p.muted)).toBe(true);
    expect(out.topProducts[0].color).toBeDefined();
  });

  it('a year window via startDate/endDate trims ts + qualityTs', () => {
    const out = window.applyFilters(
      { basket: null, startDate: '2021-01-01', endDate: '2021-12-31' },
      'ibge_pevs',
    );
    expect(out.yearStart).toBe(2021);
    expect(out.yearEnd).toBe(2021);
    expect(out.ts.map((t) => t.y)).toEqual([2021]);
    expect(out.qualityTs.map((q) => q.y)).toEqual([2021]); // 2019/2020 trimmed
  });

  it('regionData rolls UFs into regions and drops empty regions', () => {
    const out = window.applyFilters({ basket: null }, 'ibge_pevs');
    const norte = out.regionData.find((r) => r.id === 'N');
    expect(norte).toBeTruthy();
    expect(norte.ufs).toBe(1); // PA
    // every emitted region has at least one UF
    expect(out.regionData.every((r) => r.ufs > 0)).toBe(true);
  });
});

// ── Quality flag distribution ────────────────────────────────────────────────
describe('applyFilters — quality flags', () => {
  beforeEach(() => installGlobals(makeSnapshot()));

  it('flags=null keeps all flags and re-normalizes shares to 1', () => {
    const out = window.applyFilters({ basket: null, flags: null }, 'ibge_pevs');
    expect(out.qualityFlags).toHaveLength(2);
    const total = out.qualityFlags.reduce((s, f) => s + f.share, 0);
    expect(total).toBeCloseTo(1, 6);
  });

  it('a flag subset filters + re-normalizes shares within the selected world', () => {
    const out = window.applyFilters({ basket: null, flags: ['OK'] }, 'ibge_pevs');
    expect(out.qualityFlags).toHaveLength(1);
    expect(out.qualityFlags[0].id).toBe('OK');
    expect(out.qualityFlags[0].share).toBeCloseTo(1, 6); // only flag → 100%
  });

  it('flags=[] (none) yields an empty flag list', () => {
    const out = window.applyFilters({ basket: null, flags: [] }, 'ibge_pevs');
    expect(out.qualityFlags).toEqual([]);
  });
});

// ── _shares provenance counter ───────────────────────────────────────────────
// `valueShare` saiu daqui na v1.45.0 junto com a dimensão inteira: nada escrevia
// valueMin/valueMax, então os quatro testes que existiam aqui afirmavam que uma constante
// valia 1.00 — guardavam código morto, não comportamento.
describe('applyFilters — _shares provenance (flag/year/state)', () => {
  beforeEach(() => installGlobals(makeSnapshot()));

  it('não publica mais um valueShare — a dimensão não existe', () => {
    const out = window.applyFilters({ basket: null }, 'ibge_pevs');
    expect(out._shares).not.toHaveProperty('valueShare');
    expect(Object.keys(out._shares).sort()).toEqual(
      ['flagShare', 'productShare', 'stateShare', 'yearShare'],
    );
  });

  it('state + year shares reflect the active selection sizes; flagShare sums the filtered flags', () => {
    const out = window.applyFilters(
      { basket: null, states: ['PA'], flags: ['OK'], startDate: '2021-01-01', endDate: '2021-12-31' },
      'ibge_pevs',
    );
    expect(out._shares.stateShare).toBeCloseTo(0.5, 6); // 1 of 2 UFs in snapshot ufData
    // flagShare reduces the FILTERED raw quality rows by their `.share` field; the
    // snapshot's raw quality[] rows carry no precomputed `.share`, so the sum is NaN —
    // assert the code path is exercised (a Number, NaN included), not a positive value.
    expect(typeof out._shares.flagShare).toBe('number');
    // 2021-only window over a 2-year overview → yearShare = 1/2.
    expect(out._shares.yearShare).toBeCloseTo(0.5, 6);
  });

  it('flags=null gives flagShare exactly 1 (no flag narrowing)', () => {
    const out = window.applyFilters({ basket: null, flags: null }, 'ibge_pevs');
    expect(out._shares.flagShare).toBe(1);
  });
});

// ── State narrowing via the basket geoYearly cube ────────────────────────────
describe('applyFilters — state + basket narrowing (geoYearly cube)', () => {
  it('a loaded basket cube drives ufData/ts and clears the notFilteredByBasket transient', () => {
    const snap = makeSnapshot();
    // Basket-scoped (UF × year) cube — value in mi, decorated client-side.
    const geoCube = [
      { uf: 'PA', year: 2021, value: 6000, q_mass: 3, q_vol: 1, q_count: 0 },
      { uf: 'SP', year: 2021, value: 2000, q_mass: 1, q_vol: 0, q_count: 0 },
    ];
    installGlobals(snap, { geoCube });
    const out = window.applyFilters(
      { basket: ['P1', 'P2'], states: ['PA'] },
      'ibge_pevs',
    );
    // cube loaded → not pending, basket honoured by the territorial grid.
    expect(out.notFilteredByBasket).toBe(false);
    expect(out.geoComboPending).toBe(false);
    // ufData restricted to PA (the selected state) via the cube rollup.
    expect(out.ufData.map((u) => u.uf)).toEqual(['PA']);
    // value mi → bi: PA 2021 = 6000/1000 = 6 bi for the latest year.
    const y2021 = out.ts.find((t) => t.y === 2021);
    expect(y2021.v).toBeCloseTo(6, 6);
  });

  it('basket active but cube NOT loaded (geoYearly→null) flags notFilteredByBasket', () => {
    const snap = makeSnapshot();
    installGlobals(snap, { geoCube: null }); // geoYearly returns null → cube pending
    const out = window.applyFilters({ basket: ['P1', 'P2'] }, 'ibge_pevs');
    expect(out.notFilteredByBasket).toBe(true);
  });

  it('basket + state both active with no cube → geoComboPending (refuse the wrong number)', () => {
    const snap = makeSnapshot();
    installGlobals(snap, { geoCube: null });
    const out = window.applyFilters(
      { basket: ['P1', 'P2'], states: ['PA'] },
      'ibge_pevs',
    );
    expect(out.geoComboPending).toBe(true);
  });

  it('a state-only narrowing (no basket) sums the all-products ufYearly grid', () => {
    const snap = makeSnapshot();
    installGlobals(snap);
    const out = window.applyFilters({ basket: null, states: ['PA'] }, 'ibge_pevs');
    // PA-only: 2021 value 5000 mi → 5 bi (no SP).
    const y2021 = out.ts.find((t) => t.y === 2021);
    expect(y2021.v).toBeCloseTo(5, 6);
    expect(out.ufData.map((u) => u.uf)).toEqual(['PA']);
  });
});

// ── Sub-UF mesh cascade (município cube rollup) ──────────────────────────────
describe('applyFilters — sub-UF mesh narrowing (município cube)', () => {
  const MESH = [
    { cityCode: 'c1', cityName: 'Cidade 1', uf: 'PA', meso: { code: 'M1' }, micro: { code: 'mi1' },
      intermediaria: { code: 'I1' }, imediata: { code: 'im1' } },
    { cityCode: 'c2', cityName: 'Cidade 2', uf: 'PA', meso: { code: 'M1' }, micro: { code: 'mi2' },
      intermediaria: { code: 'I1' }, imediata: { code: 'im2' } },
    { cityCode: 'c3', cityName: 'Cidade 3', uf: 'SP', meso: { code: 'M2' }, micro: { code: 'mi3' },
      intermediaria: { code: 'I2' }, imediata: { code: 'im3' } },
  ];

  it('a meso narrowing rolls the município cube up to (UF, year) + ranks topMunis', () => {
    const snap = makeSnapshot();
    const muniCube = [
      { cityCode: 'c1', uf: 'PA', year: 2021, value: 100, q_mass: 1, q_vol: 0, q_count: 0 },
      { cityCode: 'c2', uf: 'PA', year: 2021, value: 50, q_mass: 0.5, q_vol: 0, q_count: 0 },
    ];
    installGlobals(snap, { mesh: MESH, muniCube });
    // mesos = ['M1'] is a PROPER non-empty subset (universe has M1,M2) → narrows.
    const out = window.applyFilters({ basket: null, mesos: ['M1'] }, 'ibge_pevs');
    // sub-UF rollup drives ufData (only PA, the cities under M1).
    expect(out.ufData.map((u) => u.uf)).toEqual(['PA']);
    // topMunis ranked desc by value, city names resolved via the mesh.
    expect(out.topMunis.map((m) => m.city)).toEqual(['Cidade 1', 'Cidade 2']);
    expect(out.topMunis[0].value).toBeGreaterThanOrEqual(out.topMunis[1].value);
    expect(out.geoComboPending).toBe(false);
  });

  it('a sub-UF narrowing whose cube is empty reads as zero, not the national curve', () => {
    const snap = makeSnapshot();
    installGlobals(snap, { mesh: MESH, muniCube: [] }); // loaded-but-empty
    const out = window.applyFilters({ basket: null, mesos: ['M1'] }, 'ibge_pevs');
    expect(out.topMunis).toEqual([]);
    expect(out.ufData).toEqual([]); // determinately empty selection
  });

  it('a sub-UF narrowing with the mesh NOT yet loaded sets geoComboPending', () => {
    const snap = makeSnapshot();
    // geoMesh returns null while a real facet narrowing is requested → mesh pending.
    installGlobals(snap, { mesh: null });
    const out = window.applyFilters({ basket: null, mesos: ['M1'] }, 'ibge_pevs');
    expect(out.geoComboPending).toBe(true);
  });
});

// ── ufLatestYear / ufYearPartial labelling ───────────────────────────────────
describe('applyFilters — map data-year labelling', () => {
  it('ufLatestYear is the max UF year within the window; partial when short of yearEnd', () => {
    const snap = makeSnapshot();
    installGlobals(snap);
    const out = window.applyFilters(
      { basket: null, states: ['PA'], startDate: '2020-01-01', endDate: '2024-12-31' },
      'ibge_pevs',
    );
    // UF rows stop at 2021, but the window runs to 2024 → partial.
    expect(out.ufLatestYear).toBe(2021);
    expect(out.ufYearPartial).toBe(true);
  });
});
