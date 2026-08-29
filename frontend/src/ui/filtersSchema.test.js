// filtersSchema.test.js — locks the capability-gating contract that makes the
// FilterMenu show ONLY the dims the active banco can actually filter on.
//
// The registries are side-effect modules that populate window.*; import them in
// dependency order: bancos (BANCOS/bancoById/isMonetaryBanco) → views
// (CAPABILITIES) → filtersSchema (FILTER_SCHEMAS + dimAppliesTo/bancoFilterDims/
// flowOptionsFor + the drift lint).

import { describe, expect, it, vi } from 'vitest';

import './bancos.js';
import './views.js';
import './filtersSchema.js';

describe('dimAppliesTo — capability crossing (requires × provides)', () => {
  it('a universal dim (requires:null) applies to every banco', () => {
    const periodo = { id: 'periodo', requires: null };
    expect(window.dimAppliesTo('ibge_pevs', periodo)).toBe(true);
    expect(window.dimAppliesTo('un_comtrade', periodo)).toBe(true);
  });

  it('a geo dim applies only to bancos that provide geo', () => {
    const geo = { id: 'geografia', requires: 'geo' };
    expect(window.dimAppliesTo('ibge_pevs', geo)).toBe(true); // provides geo
    expect(window.dimAppliesTo('mdic_comex', geo)).toBe(true); // provides geo (uf)
    expect(window.dimAppliesTo('un_comtrade', geo)).toBe(false); // country-only, no geo
  });

  it('a flow dim applies only to trade bancos that provide flow', () => {
    const flow = { id: 'fluxo', requires: 'flow' };
    expect(window.dimAppliesTo('mdic_comex', flow)).toBe(true);
    expect(window.dimAppliesTo('un_comtrade', flow)).toBe(true);
    expect(window.dimAppliesTo('ibge_pevs', flow)).toBe(false); // production, no flow
  });
});

describe('bancoFilterDims — only backed AND applicable dims (everything else hidden)', () => {
  const ids = (banco) => window.bancoFilterDims(banco).map((d) => d.id);

  it('PEVS: the production dims, in order — with `origem` since the survey has two halves', () => {
    // `origem` (extração nativa | silvicultura plantada) joined in 2026-08-29 when the
    // t291 half was ingested. It sits right after produtos on purpose: it changes WHAT a
    // number covers, so it belongs beside the product choice rather than buried below the
    // period. See PLANS/silvicultura_source.md.
    // `nivel` (industrialização) entrou em 2026-08-29: era a única dimensão que o
    // dashboard classificava mas não deixava filtrar — o eixo existia no editor e na view
    // "Valor agregado", e não no menu.
    expect(ids('ibge_pevs')).toEqual([
      'produtos', 'nivel', 'origem', 'periodo', 'geografia', 'qualidade',
    ]);
  });

  it('COMEX: keeps fluxo (now backed) + ncm + uf_origem; hides data-blocked pais/via/valor', () => {
    const got = ids('mdic_comex');
    expect(got).toEqual(expect.arrayContaining(['periodo', 'ncm', 'fluxo', 'uf_origem']));
    expect(got).not.toContain('pais'); // backed:false → hidden
    expect(got).not.toContain('via'); // backed:false → hidden
    expect(got).not.toContain('valor'); // backed:false → hidden
  });

  it('COMTRADE: keeps flow + hs6 + país reporter/parceiro (now backed); hides valor; no geo dim', () => {
    const got = ids('un_comtrade');
    // reporter/partner are now server-side FILTERS (backed:true, serverParam reporters/partners).
    expect(got).toEqual(expect.arrayContaining(['periodo', 'hs6', 'flow', 'reporter', 'partner']));
    expect(got).not.toContain('valor'); // backed:false → still hidden
    expect(got.some((id) => /geo/.test(id))).toBe(false);
  });

  it('SEFAZ (not yet backed): every dim hidden until the source is ingested', () => {
    expect(ids('sefaz_nf')).toEqual([]);
  });
});

describe('isMonetaryBanco — gates the currency/correction conventions', () => {
  it('every current banco is monetary', () => {
    ['ibge_pevs', 'ibge_pam', 'ibge_ppm', 'mdic_comex', 'un_comtrade', 'sefaz_nf'].forEach((id) =>
      expect(window.isMonetaryBanco(id)).toBe(true),
    );
  });

  it('a physical-only banco (no baseCurrency, no currency metric) is NOT monetary', () => {
    expect(window.isMonetaryBanco({ id: 'x', metrics: [{ family: 'mass' }] })).toBe(false);
  });
});

describe('flowOptionsFor — server-side flow universe', () => {
  it('returns the direction options for trade bancos, null for production bancos', () => {
    expect(window.flowOptionsFor('mdic_comex').map((o) => o.value)).toContain('export');
    // TOTALS-ONLY (2026-07): COMTRADE ingests only the two direction totals (export/import).
    // The sub-flows (re-export/re-import) are subsets of X/M — no longer ingested nor offered.
    const comtradeFlows = window.flowOptionsFor('un_comtrade').map((o) => o.value);
    expect(comtradeFlows).toEqual(['all', 'export', 'import']);
    expect(comtradeFlows).not.toContain('re-export');
    expect(window.flowOptionsFor('ibge_pevs')).toBeNull();
  });
});

describe('customsOptionsFor — server-side regime (customs procedure) universe', () => {
  it('is FROZEN (2026-07): null for every banco under the totals-only base', () => {
    // Totals-only ingests only customsCode=C00, so customs_code is a constant → the
    // "Regime aduaneiro" filter is hidden (FilterMenu gates on non-null options).
    expect(window.customsOptionsFor('un_comtrade')).toBeNull();
    expect(window.customsOptionsFor('mdic_comex')).toBeNull(); // COMEX has no customs_code
    expect(window.customsOptionsFor('ibge_pevs')).toBeNull();
  });
});

describe('marketOptionsFor — server-side tipo-de-mercado universe', () => {
  it('is FROZEN (2026-07): null for every banco (Tipo de mercado hidden)', () => {
    // Needs the customs-procedure detail the totals-only base no longer carries.
    expect(window.marketOptionsFor('un_comtrade')).toBeNull();
    expect(window.marketOptionsFor('mdic_comex')).toBeNull(); // no market_nature
    expect(window.marketOptionsFor('ibge_pevs')).toBeNull();
  });
});

describe('auditFilterSchemaCoverage — the shipped schema has no drift', () => {
  it('does not warn: every requires is a known capability and flow dims have options', () => {
    window.__filterSchemaAudited = false; // reset the once-per-run guard
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    window.auditFilterSchemaCoverage();
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
