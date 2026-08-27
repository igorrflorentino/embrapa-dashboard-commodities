// filterSummary.test.js — locks the geo-scope summary strings extracted out of
// FilterMenu's two inline ternary chains. These pin the EXACT pt-BR wording (and
// the deliberate header-vs-chip differences) so the two summaries can't silently
// drift again. Behaviour is the verbatim original logic.

import { describe, expect, it } from 'vitest';

import filterSummary from './filterSummary.js';

const { geoHeaderText, geoChipText } = filterSummary;

// A fully-selected Brasil-wide cube: 3 nations all chosen, 5 regions, 27 UFs,
// 10/10 municípios, muni-sliceable. Override fields per case.
const ALL = {
  hasGeo: true,
  nationsSize: 3,
  nationsTotal: 3,
  hasOnlyBR: false,
  regionsSize: 5,
  regionsTotal: 5,
  statesSize: 27,
  statesTotal: 27,
  munisSize: 10,
  munisTotal: 10,
  muniSliceable: true,
};
const BRASIL_ALL = { ...ALL, nationsSize: 1, hasOnlyBR: true };

describe('geoHeaderText (live header line, lowercase)', () => {
  it('no geo → sem recorte', () => {
    expect(geoHeaderText({ ...ALL, hasGeo: false })).toBe('sem recorte geográfico');
  });
  it('everything selected → todo o território', () => {
    expect(geoHeaderText(ALL)).toBe('todo o território');
  });
  it('only Brasil, all UFs, all munis → Brasil · todos os estados', () => {
    expect(geoHeaderText(BRASIL_ALL)).toBe('Brasil · todos os estados');
  });
  it('partial + muni-sliceable → counts incl. municípios, pluralised', () => {
    expect(
      geoHeaderText({ ...ALL, nationsSize: 1, statesSize: 5, munisSize: 3 }),
    ).toBe('1 nação(ões), 5 UFs, 3 municípios');
    expect(
      geoHeaderText({ ...ALL, nationsSize: 1, statesSize: 1, munisSize: 1 }),
    ).toBe('1 nação(ões), 1 UF, 1 município');
    // all munis selected within a partial UF set → "todos os municípios"
    expect(geoHeaderText({ ...ALL, nationsSize: 1, statesSize: 5, munisSize: 10 })).toBe(
      '1 nação(ões), 5 UFs, todos os municípios',
    );
  });
  it('partial + NOT muni-sliceable → no município segment, pluralised', () => {
    expect(
      geoHeaderText({ ...ALL, nationsSize: 2, statesSize: 5, muniSliceable: false }),
    ).toBe('2 nação(ões), 5 UFs');
  });
  it('cleared municípios (0) = no narrowing → "todos os", never "0 municípios"', () => {
    // dataFilters treats an emptied geo facet as NO constraint (shows all), so the summary
    // must say "todos os municípios" — not "0 municípios" while every município is shown.
    expect(geoHeaderText({ ...ALL, nationsSize: 1, statesSize: 5, munisSize: 0 })).toBe(
      '1 nação(ões), 5 UFs, todos os municípios',
    );
    // everything else full + munis cleared → still the whole territory
    expect(geoHeaderText({ ...ALL, munisSize: 0 })).toBe('todo o território');
  });
  // FILT-4: with zero UFs selected, the header used to still claim "todos os
  // municípios" — contradicting the section summary's own "0 municípios" built from
  // the very same selection a few lines below in FilterMenu. No UF selected means no
  // município segment at all, matching what geoChipText already did.
  it('zero UFs selected → no município segment (never "todos os municípios")', () => {
    expect(geoHeaderText({ ...ALL, nationsSize: 1, statesSize: 0, munisSize: 0 })).toBe(
      '1 nação(ões), 0 UFs',
    );
  });
});

describe('geoChipText (apply-time chip, title case)', () => {
  it('no geo → Não se aplica', () => {
    expect(geoChipText({ ...ALL, hasGeo: false })).toBe('Não se aplica');
  });
  it('only Brasil, all UFs → Brasil · N UFs (statesTotal)', () => {
    expect(geoChipText(BRASIL_ALL)).toBe('Brasil · 27 UFs');
  });
  it('everything selected → Todo o território', () => {
    expect(geoChipText(ALL)).toBe('Todo o território');
  });
  it('partial muni selection (not full) → UFs · municípios, pluralised', () => {
    expect(geoChipText({ ...ALL, nationsSize: 1, statesSize: 5, munisSize: 3 })).toBe(
      '5 UFs · 3 municípios',
    );
    expect(geoChipText({ ...ALL, nationsSize: 1, statesSize: 1, munisSize: 1 })).toBe(
      '1 UF · 1 município',
    );
  });
  it('muni full but not all-territory → nações · UFs, pluralised', () => {
    expect(geoChipText({ ...ALL, nationsSize: 2, statesSize: 5 })).toBe('2 nações · 5 UFs');
    expect(geoChipText({ ...ALL, nationsSize: 1, statesSize: 1 })).toBe('1 nação · 1 UF');
  });
  it('cleared municípios (0) = no narrowing → never "0 municípios" in the chip', () => {
    expect(geoChipText({ ...ALL, nationsSize: 2, statesSize: 5, munisSize: 0 })).toBe(
      '2 nações · 5 UFs',
    );
  });
});
