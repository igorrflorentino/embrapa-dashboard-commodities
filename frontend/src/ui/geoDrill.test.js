// geoDrill.test.js — the level derivation and the step-out ladder.
//
// The whole point of deriving the level is that an unreachable state stops existing:
// you cannot be in "município" without having entered a UF, which is what produced the
// old dead end (pick Município with nothing selected → a card telling you to go
// configure a filter). So the invariant worth pinning is not any single case — it is
// that every selection maps to exactly one level, and that stepping out always
// terminates at Brasil.

import { describe, expect, it } from 'vitest';

import {
  drillLevel, drillTrail, enterCity, enterRegion, enterUf, stepOut,
} from './geoDrill.js';

describe('drillLevel — where the selection puts you', () => {
  it('is Brasil when nothing narrows', () => {
    expect(drillLevel({})).toBe('region');
    expect(drillLevel(null)).toBe('region');
    expect(drillLevel({ states: [], regions: [], munis: [] })).toBe('region');
  });

  it('is UF level inside a region, and município level inside a UF', () => {
    expect(drillLevel({ regions: ['N'] })).toBe('uf');
    expect(drillLevel({ regions: ['N'], states: ['PA'] })).toBe('municipio');
    expect(drillLevel({ munis: ['1500107'] })).toBe('municipio');
  });

  it('stops at UF for a banco with no município grain', () => {
    // COMEX is origin-UF only; a state there is the end of the road, not a doorway.
    expect(drillLevel({ states: ['PA'] }, false)).toBe('uf');
    expect(drillLevel({ states: ['PA'] }, true)).toBe('municipio');
  });

  it('stays at UF level for SEVERAL states', () => {
    // The municipal mesh is per-UF, so there is nothing single to drill into. Showing
    // one of them, or silently picking one, would both be lies about the selection.
    expect(drillLevel({ states: ['PA', 'AM'] })).toBe('uf');
    expect(drillLevel({ states: ['PA', 'AM', 'MT'] })).toBe('uf');
  });

  it('never returns a level the selection cannot support', () => {
    // The property behind the dead end: sweep the shapes a filter can take and assert
    // município is reachable ONLY with a single UF or a single município.
    const shapes = [
      {}, { regions: ['N'] }, { states: ['PA'] }, { states: ['PA', 'AM'] },
      { munis: ['1500107'] }, { regions: ['N'], states: ['PA'] },
      { regions: ['N'], states: ['PA'], munis: ['1500107'] },
    ];
    for (const s of shapes) {
      const level = drillLevel(s, true);
      if (level === 'municipio') {
        const single = (s.states || []).length === 1 || (s.munis || []).length === 1;
        expect(`${JSON.stringify(s)}: ${single}`).toBe(`${JSON.stringify(s)}: true`);
      }
    }
  });
});

describe('stepOut — one level per gesture, always terminating', () => {
  it('drops the município first, keeping the UF it was found in', () => {
    expect(stepOut({ regions: ['N'], states: ['PA'], munis: ['1500107'] })).toEqual({ munis: null });
  });

  it('drops the UF next, keeping the region when we came through one', () => {
    const out = stepOut({ regions: ['N'], states: ['PA'] });
    expect(out.states).toBeNull();
    expect(out).not.toHaveProperty('regions');   // the region survives
  });

  it('clears the region too when the UF was reached directly', () => {
    const out = stepOut({ states: ['PA'] });
    expect(out.states).toBeNull();
    expect(out.regions).toBeNull();
  });

  it('returns null at Brasil — there is nothing above it', () => {
    expect(stepOut({})).toBeNull();
    expect(stepOut(null)).toBeNull();
  });

  it('always reaches Brasil in a finite number of steps', () => {
    // A ladder with a missing rung would trap the researcher at a level with no way
    // back except reloading the page.
    let s = { regions: ['N'], states: ['PA'], munis: ['1500107'] };
    let guard = 0;
    while (drillLevel(s) !== 'region' && guard < 10) {
      s = { ...s, ...stepOut(s) };
      guard += 1;
    }
    expect(drillLevel(s)).toBe('region');
    expect(guard).toBeLessThan(10);
  });
});

describe('enter* — drilling in always clears the levels below', () => {
  it('entering a region selects its UFs and drops every finer facet', () => {
    const p = enterRegion('N', ['PA', 'AM']);
    expect(p.regions).toEqual(['N']);
    expect(p.states).toEqual(['PA', 'AM']);
    for (const k of ['mesos', 'micros', 'inters', 'imediatas', 'munis']) {
      expect(`${k}:${p[k]}`).toBe(`${k}:null`);
    }
  });

  it('entering a UF drops the sub-UF facets that a stale session could carry', () => {
    const p = enterUf('PA');
    expect(p.states).toEqual(['PA']);
    expect(p.munis).toBeNull();
    expect(p.mesos).toBeNull();
  });

  it('entering a city touches only the município facet', () => {
    expect(enterCity('1500107')).toEqual({ munis: ['1500107'] });
    expect(enterCity(null)).toEqual({ munis: null });
  });
});

describe('drillTrail — the depth made visible', () => {
  it('reads Brasil → região → UF → município', () => {
    const t = drillTrail(
      { regions: ['N'], states: ['PA'], munis: ['1500107'] },
      { regionLabel: 'Norte', ufName: 'Pará', cityName: 'Abaetetuba' },
    );
    expect(t.map((c) => c.label)).toEqual(['Brasil', 'Norte', 'Pará', 'Abaetetuba']);
  });

  it('names a multi-state selection by its size rather than inventing a parent', () => {
    const t = drillTrail({ states: ['PA', 'AM'] });
    expect(t.map((c) => c.label)).toEqual(['Brasil', '2 UFs']);
  });

  it('is just Brasil when nothing narrows', () => {
    expect(drillTrail({}).map((c) => c.label)).toEqual(['Brasil']);
  });
});

// ── Carrying a selection ACROSS bancos ───────────────────────────────────────
//
// The geography filter is shared, so switching banco mid-drill carries the selection
// over. The level has to degrade to what the NEW banco can serve — the old segmented
// control had an explicit effect for this, and deriving the level dropped it.

describe('drillLevel — a selection that outlives its banco', () => {
  it('degrades a município facet to UF level on a banco with no município grain', () => {
    // Drill into a município on IBGE PEVS, then switch to MDIC COMEX (origin-UF only):
    // the munis facet survives the switch, and município is a grain COMEX cannot serve.
    expect(drillLevel({ states: ['PA'], munis: ['1500107'] }, false)).toBe('uf');
    expect(drillLevel({ munis: ['1500107'] }, false)).toBe('uf');
  });

  it('still honours it on a banco that HAS the grain', () => {
    expect(drillLevel({ states: ['PA'], munis: ['1500107'] }, true)).toBe('municipio');
  });

  it('never returns município for a banco without the grain, whatever the selection', () => {
    const shapes = [
      { munis: ['1500107'] }, { munis: ['1500107', '3550308'] },
      { states: ['PA'], munis: ['1500107'] },
      { regions: ['N'], states: ['PA'], munis: ['1500107'] },
      { states: ['PA'] }, { states: ['PA', 'AM'] }, { regions: ['N'] }, {},
    ];
    for (const s of shapes) {
      expect(`${JSON.stringify(s)}: ${drillLevel(s, false)}`)
        .not.toBe(`${JSON.stringify(s)}: municipio`);
    }
  });
});

describe('drillTrail — never offers a level the banco cannot reach', () => {
  it('drops the município crumb on a UF-only banco', () => {
    // The facet survives a banco switch and drillLevel already degrades to 'uf'. Leaving
    // the crumb showed a raw 7-digit code as the CURRENT level and offered a way back to
    // somewhere the map never went.
    const t = drillTrail({ states: ['PA'], munis: ['1500107'] }, { ufName: 'Pará' }, false);
    expect(t.map((c) => c.label)).toEqual(['Brasil', 'Pará']);
  });

  it('keeps it where the grain exists', () => {
    const t = drillTrail({ states: ['PA'], munis: ['1500107'] },
                         { ufName: 'Pará', cityName: 'Abaetetuba' }, true);
    expect(t.map((c) => c.label)).toEqual(['Brasil', 'Pará', 'Abaetetuba']);
  });

  it('the trail never runs deeper than the level', () => {
    // The two must agree: a crumb past the current level is a promise the map cannot keep.
    const depth = { region: 1, uf: 2, municipio: 3, focus: 4 };
    for (const cap of [true, false]) {
      for (const s of [{}, { regions: ['N'] }, { states: ['PA'] },
                       { states: ['PA'], munis: ['1500107'] }, { munis: ['1500107'] }]) {
        const level = drillLevel(s, cap);
        const deepest = drillTrail(s, {}, cap).at(-1).level;
        const ok = depth[deepest] <= depth[level] + 1;
        expect(`${cap}/${JSON.stringify(s)}: ${ok}`).toBe(`${cap}/${JSON.stringify(s)}: true`);
      }
    }
  });
});

// ── Sub-UF facets are a level, not an invisible narrowing ────────────────────
//
// mesorregião / microrregião / intermediária / imediata sit BELOW the UF. Deriving the
// level from `summary` alone missed them entirely: a mesorregião of Pará produced a map
// captioned "Distribuição por região" under a trail reading "Brasil" — the orientation
// device asserting the opposite of the data — and it drove the CSV export's grain too,
// so the download matched the label rather than the rows.
//
// It cannot be read off `summary`: a facet key can be present while covering its whole
// universe, which narrows nothing. Only dataFilters knows the universe, so the caller
// passes `subUfActive` and this trusts it.

describe('drillLevel — a sub-UF facet is município level', () => {
  it('reaches município grain even with no UF selected', () => {
    expect(drillLevel({ mesos: ['1504'] }, true, true)).toBe('municipio');
    expect(drillLevel({ inters: ['1502'] }, true, true)).toBe('municipio');
  });

  it('ignores a facet key that narrows nothing', () => {
    // Present but covering its whole universe ⇒ subUfActive false ⇒ still Brasil.
    expect(drillLevel({ mesos: ['1504'] }, true, false)).toBe('region');
  });

  it('still stops at UF for a banco without the grain', () => {
    expect(drillLevel({ mesos: ['1504'] }, false, true)).toBe('uf');
  });

  it('a UF plus a sub-UF facet stays at município level', () => {
    expect(drillLevel({ states: ['PA'], mesos: ['1504'] }, true, true)).toBe('municipio');
  });
});

describe('drillTrail — the sub-UF narrowing gets a crumb', () => {
  it('names it instead of stopping at Brasil', () => {
    const t = drillTrail({ mesos: ['1504'] }, { subUfLabel: 'Nordeste Paraense' });
    expect(t.map((c) => c.label)).toEqual(['Brasil', 'Nordeste Paraense']);
  });

  it('sits between the UF and the município', () => {
    const t = drillTrail(
      { states: ['PA'], mesos: ['1504'], munis: ['1500107'] },
      { ufName: 'Pará', subUfLabel: 'Nordeste Paraense', cityName: 'Abaetetuba' },
    );
    expect(t.map((c) => c.label)).toEqual(['Brasil', 'Pará', 'Nordeste Paraense', 'Abaetetuba']);
  });
});

describe('stepOut — the sub-UF rung', () => {
  it('clears the facets before touching the UF', () => {
    // Stepping past them straight to the UF would discard a narrowing the researcher
    // never asked to leave.
    const out = stepOut({ states: ['PA'], mesos: ['1504'] });
    expect(out).toEqual({ mesos: null });
    expect(out).not.toHaveProperty('states');
  });

  it('still terminates at Brasil through the extra rung', () => {
    let s = { regions: ['N'], states: ['PA'], mesos: ['1504'], munis: ['1500107'] };
    let guard = 0;
    while (drillLevel(s, true, (s.mesos || []).length > 0) !== 'region' && guard < 10) {
      s = { ...s, ...stepOut(s) };
      guard += 1;
    }
    expect(drillLevel(s, true, (s.mesos || []).length > 0)).toBe('region');
    expect(guard).toBeLessThan(10);
  });
});

// ── The trail must account for EVERY active narrowing ────────────────────────
//
// This sweep exists because "add another case" is what produced two bugs in a row:
// v1.33.1 (the level ignored sub-UF facets entirely) and then the label naming only the
// FIRST facet it found. Both had the same shape — the orientation device describing a
// strictly larger set than the data.
//
// The trail stopped being decoration when the granularity control was removed in
// v1.32.0: it is now the ONLY place the researcher reads where they are, so its
// correctness is load-bearing. The property, not the cases, is what protects it.

import { subUfCount, subUfLabel } from './geoDrill.js';

describe('subUfLabel — never describes a wider recorte than the data', () => {
  const MESH = [
    { cityCode: '1', uf: 'PA', meso: { code: '1504', name: 'Nordeste Paraense' },
      micro: { code: '15012', name: 'Cametá' },
      intermediaria: { code: '1501', name: 'Belém' },
      imediata: { code: '150001', name: 'Abaetetuba' } },
  ];

  it('names a single narrowing', () => {
    expect(subUfLabel({ mesos: ['1504'] }, MESH)).toBe('Nordeste Paraense');
    expect(subUfLabel({ inters: ['1501'] }, MESH)).toBe('Belém');
  });

  it('names BOTH when the two parallel divisions narrow at once', () => {
    // The divisions do not nest and a município must clear every active facet, so the
    // effective recorte is their INTERSECTION. Naming one described a larger set.
    expect(subUfLabel({ mesos: ['1504'], inters: ['1501'] }, MESH))
      .toBe('Nordeste Paraense · Belém');
  });

  it('falls back to a count past two — vaguer, but never wider', () => {
    const l = subUfLabel({ mesos: ['1504'], micros: ['15012'], inters: ['1501'] }, MESH);
    expect(l).toBe('3 recortes');
  });

  it('is null when nothing narrows', () => {
    expect(subUfLabel({}, MESH)).toBeNull();
    expect(subUfLabel({ mesos: [] }, MESH)).toBeNull();
  });

  it('falls back to the code when the mesh cannot resolve it', () => {
    // Still honest about HOW MANY narrowings are in play, which is the property.
    expect(subUfLabel({ mesos: ['9999'] }, MESH)).toBe('9999');
  });

  // THE invariant. Sweep every combination of the four facets and assert the label
  // accounts for all of them: a single narrowing may be named, but two or more must
  // never render as one name.
  it('accounts for every active facet, across all 16 combinations', () => {
    const KEYS = ['mesos', 'micros', 'inters', 'imediatas'];
    const CODES = { mesos: '1504', micros: '15012', inters: '1501', imediatas: '150001' };
    const NAMES = ['Nordeste Paraense', 'Cametá', 'Belém', 'Abaetetuba'];
    for (let bits = 0; bits < 16; bits += 1) {
      const s = {};
      KEYS.forEach((k, i) => { if (bits & (1 << i)) s[k] = [CODES[k]]; });
      const n = subUfCount(s);
      const label = subUfLabel(s, MESH);
      if (n === 0) {
        expect(`${bits}: ${label}`).toBe(`${bits}: null`);
        continue;
      }
      // A label naming exactly ONE known place while two or more narrow is the bug.
      const namesOne = NAMES.includes(label);
      expect(`${bits}/n=${n}: ${namesOne && n > 1 ? 'UNDER-REPORTS' : 'ok'}`)
        .toBe(`${bits}/n=${n}: ok`);
      // And every label must be non-empty — a silent trail is how "Brasil" ended up
      // over one mesorregião of Pará.
      expect(`${bits}: ${!!label}`).toBe(`${bits}: true`);
    }
  });
});
