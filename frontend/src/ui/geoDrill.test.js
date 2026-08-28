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
