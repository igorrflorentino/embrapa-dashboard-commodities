// data_contracts.cov.test.js — coverage for the three pure data-layer modules
// that back the dashboard's client-side seam: data.js (registries + pt-BR
// formatters + the unit-family conversion table + familiesInBasket), chipFmt.js
// (filter trigger-bar chip labels) and contracts.js (the runtime contract-lint).
//
// All three register on window.* via side-effect imports (no ES exports the
// views consume), so the pattern is: import the module, then read window.X.
// contracts.js additionally runs window.auditSnapshotContracts() against the
// live producers/bancos — we stub those globals to drive both the "all clean"
// and the "drift detected" branches of the lint.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// ──────────────────────────────────────────────────────────────────────
// data.js — registries + helpers + formatters
// ──────────────────────────────────────────────────────────────────────
describe('data.js — registries', () => {
  beforeEach(async () => {
    await import('./data.js');
  });

  it('PRODUCTS / UNIT_FAMILIES / REGIONS / UF_DATA / QUALITY_FLAGS are populated', () => {
    expect(window.PRODUCTS.length).toBeGreaterThan(0);
    expect(window.PRODUCTS.every((p) => p.code && p.name && p.family)).toBe(true);
    // the 5 displayable families + livestock count
    expect(Object.keys(window.UNIT_FAMILIES)).toEqual(
      expect.arrayContaining(['mass', 'volume', 'energia', 'count', 'area', 'rendimento']),
    );
    expect(window.REGIONS.map((r) => r.id)).toEqual(['N', 'NE', 'CO', 'SE', 'S']);
    expect(window.UF_DATA).toHaveLength(27); // 27 UFs
    expect(window.UF_DATA.every((u) => u.uf && u.region && Number.isInteger(u.col))).toBe(true);
    // the 11-value taxonomy (5 base + 4 outlier/problemático + 2 reserved inferred tiers)
    expect(window.QUALITY_FLAGS).toHaveLength(12); // 11 shared + AREA_INCONSISTENT (PAM-only)
    expect(window.QUALITY_FLAGS.find((f) => f.id === 'OK').label).toBe('Normais');
    // every flag now carries a plain-pt-BR legend description
    expect(window.QUALITY_FLAGS.every((f) => typeof f.desc === 'string' && f.desc.length > 0)).toBe(true);
    // the two reserved inferred tiers are flagged as such
    expect(window.QUALITY_FLAGS.filter((f) => f.reserved).map((f) => f.id)).toEqual([
      'INFERRED_QUANTITY',
      'INFERRED_VALUE',
    ]);
  });
});

describe('data.js — unit-family helpers', () => {
  beforeEach(async () => {
    await import('./data.js');
  });

  it('defaultUnitOf returns the family display unit, or "" for an unknown family', () => {
    expect(window.defaultUnitOf('mass')).toBe('t');
    expect(window.defaultUnitOf('volume')).toBe('m³');
    expect(window.defaultUnitOf('count')).toBe('un');
    expect(window.defaultUnitOf('nope')).toBe('');
  });

  it('unitToBase finds a unit factor, falls back to 1 for unknown family/unit', () => {
    expect(window.unitToBase('mass', 'kg')).toBe(0.001);
    expect(window.unitToBase('mass', '@')).toBe(0.015);
    expect(window.unitToBase('mass', 'nope')).toBe(1); // unit absent in family → 1
    expect(window.unitToBase('nope', 'kg')).toBe(1); // family absent → 1
  });

  it('convertUnit converts within a family and passes null through', () => {
    // 1000 kg → 1 t
    expect(window.convertUnit(1000, 'mass', 'kg', 't')).toBeCloseTo(1, 9);
    // 2 t → 2000 kg
    expect(window.convertUnit(2, 'mass', 't', 'kg')).toBeCloseTo(2000, 9);
    // identity
    expect(window.convertUnit(5, 'volume', 'm³', 'm³')).toBeCloseTo(5, 9);
    expect(window.convertUnit(null, 'mass', 'kg', 't')).toBeNull();
  });
});

describe('data.js — familiesInBasket (banco-aware)', () => {
  beforeEach(async () => {
    await import('./data.js');
  });

  afterEach(() => {
    delete window.dataStore;
    delete window.snapshotFor;
  });

  it('null product filter → every (known) family present in the PEVS fallback list', () => {
    delete window.dataStore;
    delete window.snapshotFor;
    const fams = window.familiesInBasket(null, 'ibge_pevs');
    expect(fams).toContain('mass');
    expect(fams).toContain('volume');
    // de-duplicated
    expect(new Set(fams).size).toBe(fams.length);
  });

  it('explicit empty selection → zero families (nothing to measure)', () => {
    expect(window.familiesInBasket([], 'ibge_pevs')).toEqual([]);
  });

  it('an explicit code list maps to its families, dropping unknown families', () => {
    // 49215 = Madeira em tora (volume), 49101 = Castanha (mass)
    const fams = window.familiesInBasket(['49215', '49101'], null);
    expect(fams.sort()).toEqual(['mass', 'volume']);
  });

  it('resolves the active banco snapshot via dataStore.get when present', () => {
    window.dataStore = {
      get: (id) =>
        id === 'comex'
          ? { products: [{ code: 'A', family: 'mass' }, { code: 'B', family: 'desconhecida' }] }
          : null,
    };
    // null filter → families from the snapshot, with the 'desconhecida' sentinel dropped
    expect(window.familiesInBasket(null, 'comex')).toEqual(['mass']);
  });

  it('falls back to window.snapshotFor when dataStore has no entry', () => {
    delete window.dataStore;
    window.snapshotFor = (id) =>
      id === 'x' ? { products: [{ code: 'Z', family: 'volume' }] } : null;
    expect(window.familiesInBasket(['Z'], 'x')).toEqual(['volume']);
  });
});

describe('data.js — formatters', () => {
  beforeEach(async () => {
    await import('./data.js');
  });

  it('fmtBRL ladders bi / mi / mil and falls through to a plain pt-BR number', () => {
    expect(window.fmtBRL(null)).toBe('—');
    expect(window.fmtBRL(2.5e9)).toBe('R$ 2,50 bi');
    expect(window.fmtBRL(3.4e6)).toBe('R$ 3,4 mi');
    expect(window.fmtBRL(7e3)).toBe('R$ 7 mil');
    expect(window.fmtBRL(500)).toContain('R$');
  });

  it('fmtNum appends an optional unit and handles null', () => {
    expect(window.fmtNum(null)).toBe('—');
    expect(window.fmtNum(1000)).toBe((1000).toLocaleString('pt-BR'));
    expect(window.fmtNum(1000, 't')).toBe((1000).toLocaleString('pt-BR') + ' t');
  });

  it('fmtPct multiplies a fraction by 100, with configurable digits', () => {
    expect(window.fmtPct(null)).toBe('—');
    expect(window.fmtPct(0.123)).toBe('12,3%');
    expect(window.fmtPct(0.5, 0)).toBe('50%');
  });

  it('fmtSigned prefixes + for non-negative, with custom suffix', () => {
    expect(window.fmtSigned(null)).toBe('—');
    expect(window.fmtSigned(0.5)).toBe('+0,5%');
    expect(window.fmtSigned(-0.5)).toBe('-0,5%');
    expect(window.fmtSigned(2, 0, ' pp')).toBe('+2 pp');
  });

  it('numBR / pctBR honour a fixed-decimal count and null', () => {
    expect(window.numBR(null)).toBe('—');
    expect(window.numBR(1234.5, 1)).toBe((1234.5).toLocaleString('pt-BR', { maximumFractionDigits: 1, minimumFractionDigits: 1 }));
    // Was '—%' until v1.29.2 — a characterization test that locked in the wart rather
    // than questioning it, three lines below the sibling assertion that fmtSigned(null)
    // is a bare '—'. A dash with a unit glued on reads as a value, not as absence.
    expect(window.pctBR(null)).toBe('—');
    expect(window.pctBR(12.34, 1)).toBe(window.numBR(12.34, 1) + '%');
  });

  it('fmtRows compacts to mi / mil for big counts', () => {
    expect(window.fmtRows(2.3e6)).toBe('2,3 mi');
    expect(window.fmtRows(5000)).toBe('5 mil');
    expect(window.fmtRows(42)).toBe((42).toLocaleString('pt-BR'));
  });
});

// ──────────────────────────────────────────────────────────────────────
// chipFmt.js — filter trigger-bar chip labels
// ──────────────────────────────────────────────────────────────────────
describe('chipFmt.js — fmtCompactValue', () => {
  beforeEach(async () => {
    await import('./chipFmt.js');
  });

  it('null → em-dash', () => {
    expect(window.fmtCompactValue(null)).toBe('—');
  });

  it('below 1e3 → plain pt-BR number with the symbol, no suffix', () => {
    expect(window.fmtCompactValue(500)).toBe('R$ ' + (500).toLocaleString('pt-BR'));
  });

  it('bi / mi → 1 decimal, mil → 0 decimal', () => {
    expect(window.fmtCompactValue(1.23e9)).toBe('R$ 1,2 bi');
    expect(window.fmtCompactValue(3.4e8, 'US$')).toBe('US$ 340,0 mi');
    expect(window.fmtCompactValue(7.8e3)).toBe('R$ 8 mil');
  });

  it('is negative-safe (sign prefix preserved through the ladder)', () => {
    expect(window.fmtCompactValue(-1.5e6)).toBe('-R$ 1,5 mi');
  });
});

describe('chipFmt.js — chipFmt object', () => {
  beforeEach(async () => {
    await import('./chipFmt.js');
  });

  it('products: null=all, 0=none, full=all, single=name, partial=count', () => {
    const c = window.chipFmt;
    expect(c.products(null, 12)).toBe('Todos (12)');
    expect(c.products(0, 12)).toBe('Nenhum');
    expect(c.products(12, 12)).toBe('Todos (12)');
    expect(c.products(1, 12, 'Açaí')).toBe('Açaí');
    expect(c.products(1, 12)).toBe('1 de 12'); // no firstName
    expect(c.products(3, 12)).toBe('3 de 12');
  });

  it('period renders an en-dash year range', () => {
    expect(window.chipFmt.period(1986, 2024)).toBe('1986–2024');
  });

  it('não formata mais uma faixa de valor — a dimensão foi removida', () => {
    // Formatava um campo que nada preenchia; o único leitor era a citação ABNT, que
    // declararia um recorte nunca aplicado aos dados se os campos voltassem a existir.
    expect(window.chipFmt.valueRange).toBeUndefined();
  });

  it('quality: null=all, empty=none, full=all, head-of-2 (+overflow)', () => {
    const c = window.chipFmt;
    const labelOf = (id) => `L:${id}`;
    expect(c.quality(null, 9)).toBe('Todas (9)');
    expect(c.quality([], 9)).toBe('Nenhuma');
    expect(c.quality(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i'], 9, labelOf)).toBe('Todas (9)');
    expect(c.quality(['a', 'b'], 9, labelOf)).toBe('L:a · L:b');
    expect(c.quality(['a', 'b', 'c', 'd'], 9, labelOf)).toBe('L:a · L:b +2');
  });

  it('geoStates: no-geo, full = Brasil, partial = N UFs (pluralised)', () => {
    const c = window.chipFmt;
    expect(c.geoStates(5, 27, false)).toBe('Não se aplica');
    expect(c.geoStates(0, 27, true)).toBe('Brasil · 27 UFs'); // 0/null → all
    expect(c.geoStates(27, 27, true)).toBe('Brasil · 27 UFs');
    expect(c.geoStates(1, 27, true)).toBe('1 UF');
    expect(c.geoStates(5, 27, true)).toBe('5 UFs');
  });
});

// ──────────────────────────────────────────────────────────────────────
// contracts.js — SNAPSHOT_CONTRACTS registry + auditSnapshotContracts lint
// ──────────────────────────────────────────────────────────────────────
describe('contracts.js — SNAPSHOT_CONTRACTS registry', () => {
  beforeEach(async () => {
    await import('./contracts.js');
  });

  it('exposes the per-banco and global producer registries', () => {
    const C = window.SNAPSHOT_CONTRACTS;
    expect(Object.keys(C.perBanco)).toEqual(
      expect.arrayContaining(['snapshot', 'flow', 'partner', 'monthly', 'productivity']),
    );
    expect(Object.keys(C.global)).toEqual(
      expect.arrayContaining([
        'crossSeries',
        'exportCoefficient',
        'marketShare',
        'priceSpread',
        'tradeMirror',
        'chainBalance',
        'harvestShipmentLag',
        'valueAddedAnalysis',
        'marketNatureAnalysis',
      ]),
    );
    // every entry carries a typedef + required-keys array
    Object.values(C.perBanco).forEach((s) => {
      expect(typeof s.typedef).toBe('string');
      expect(Array.isArray(s.required)).toBe(true);
    });
  });
});

describe('contracts.js — auditSnapshotContracts (runtime drift lint)', () => {
  // The audit guards itself with window.__contractsAudited (run-once). Each test
  // resets that flag and stubs the bancos + producers it iterates so we drive the
  // clean / drift / throws / appliesTo branches deterministically.
  let warn;

  beforeEach(async () => {
    await import('./contracts.js');
    warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    warn.mockRestore();
    // clear the run-once latch and any stubbed producers between cases
    delete window.__contractsAudited;
    [
      'visibleBancos', 'BANCOS', 'snapshotFor', 'flowData', 'partnerData', 'monthlyData',
      'productivityData', 'crossSeries', 'exportCoefficient', 'marketShare', 'priceSpread',
      'tradeMirror', 'chainBalance', 'harvestShipmentLag', 'valueAddedAnalysis',
      'marketNatureAnalysis',
    ].forEach((k) => delete window[k]);
  });

  function fullSnapshot() {
    return {
      products: [], productTS: {}, overviewTS: [], quality: [],
      ufData: [{ uf: 'PA' }],
    };
  }

  it('does NOT warn when every producer returns a complete shape', () => {
    window.BANCOS = [{ id: 'geoBanco', provides: ['geo'] }];
    // per-banco producers
    window.snapshotFor = () => fullSnapshot();
    // flow/partner/monthly/productivity don't apply (banco has no flow/partner/...),
    // so appliesTo gates them out → never produced.
    // global producers all return their full required keys:
    window.crossSeries = () => ({
      banco: 'b', metric: 'm', key: 'b:m', label: 'L', unit: 'u', family: 'mass',
      preview: true, coverage: [0, 1], points: [],
    });
    window.exportCoefficient = () => ({ preview: true, unit: 'u', byUf: [], national: {}, timeseries: [] });
    window.marketShare = () => ({ preview: true, unit: 'u', series: [], byProduct: [] });
    window.priceSpread = () => ({ preview: true, unit: 'u', series: [] });
    window.tradeMirror = () => ({ preview: true, unit: 'u', series: [], discrepancy: [] });
    window.chainBalance = () => ({
      preview: true, unit: 'u', year: 2024, produced: 1, exported: 1, internal: 1, domestic: 1,
      expFrac: 1, intFrac: 0, domFrac: 0, worldShare: 0, worldTotal: 1, exportUsd: 1, sankey: {},
    });
    window.harvestShipmentLag = () => ({
      preview: true, months: [], production: [], shipments: [], peakHarvest: 0, peakShip: 0,
      lagMonths: 0, corrAtLag: 0, lagProfile: [],
    });
    window.valueAddedAnalysis = () => ({ preview: true, years: [], byLevel: {}, byLevelWeight: {}, series: [] });
    window.marketNatureAnalysis = () => ({ preview: true, years: [], series: [], latest: {} });
    // crossSeries' producer needs a banco with metrics; visibleBancos drives that.
    window.visibleBancos = () => [{ id: 'geoBanco', provides: ['geo'], metrics: [{ id: 'm0' }] }];

    window.auditSnapshotContracts();
    expect(warn).not.toHaveBeenCalled();
  });

  it('WARNS listing the missing key when a producer drops a contracted field', () => {
    window.visibleBancos = () => [{ id: 'geoBanco', provides: ['geo'] }];
    // snapshot missing `quality` AND ufData empty (banco provides geo → extra check fires)
    window.snapshotFor = () => ({ products: [], productTS: {}, overviewTS: [], ufData: [] });
    window.auditSnapshotContracts();
    expect(warn).toHaveBeenCalledTimes(1);
    const msg = warn.mock.calls[0][0];
    expect(msg).toContain('shape drift detected');
    expect(msg).toContain('missing `quality`');
    expect(msg).toContain('ufData vazio'); // the geo `extra` check
  });

  it('records a producer that THROWS instead of crashing the lint', () => {
    window.visibleBancos = () => [{ id: 'b', provides: [] }];
    window.snapshotFor = () => { throw new Error('boom'); };
    window.auditSnapshotContracts();
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain('threw: boom');
  });

  it('skips a producer that returns null (banco does not serve it yet)', () => {
    window.visibleBancos = () => [{ id: 'b', provides: [] }];
    window.snapshotFor = () => null; // PEVS-style: served from data.js, not snapshotFor
    // all globals absent → produce() returns null → skipped
    window.auditSnapshotContracts();
    expect(warn).not.toHaveBeenCalled();
  });

  it('applies per-banco flow/partner/monthly/productivity only to bancos that declare the capability', () => {
    window.visibleBancos = () => [{ id: 'trade', provides: ['flow', 'partner', 'monthly', 'yield'] }];
    window.snapshotFor = () => null; // skip the snapshot producer
    // each capability producer returns an INCOMPLETE shape → must be flagged because appliesTo passes
    window.flowData = () => ({ preview: true }); // missing unit/originLabel/...
    window.partnerData = () => ({ preview: true }); // missing flowLabel/unit/partners
    window.monthlyData = () => ({ preview: true }); // missing many keys
    window.productivityData = () => ({ preview: true }); // missing many keys
    window.auditSnapshotContracts();
    expect(warn).toHaveBeenCalledTimes(1);
    const msg = warn.mock.calls[0][0];
    expect(msg).toContain('flow(trade)');
    expect(msg).toContain('partner(trade)');
    expect(msg).toContain('monthly(trade)');
    expect(msg).toContain('productivity(trade)');
  });

  it('is run-once: a second invocation is a no-op even if shapes changed', () => {
    window.visibleBancos = () => [{ id: 'b', provides: [] }];
    window.snapshotFor = () => null;
    window.auditSnapshotContracts(); // sets __contractsAudited
    expect(warn).not.toHaveBeenCalled();
    // now introduce drift, but the latch blocks a re-run
    window.snapshotFor = () => ({ products: [] }); // missing 3 keys
    window.auditSnapshotContracts();
    expect(warn).not.toHaveBeenCalled();
  });

  it('a global producer that throws is captured (not fatal)', () => {
    window.visibleBancos = () => [];
    window.exportCoefficient = () => { throw new Error('ec-fail'); };
    window.auditSnapshotContracts();
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain('exportCoefficient threw: ec-fail');
  });
});
