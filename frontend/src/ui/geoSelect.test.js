// geoSelect.test.js — the click-a-UF-to-filter rule, now shared by Geografia, Visão
// geral and Qualidade. It was inline in one view; three call sites make the subtle
// part worth pinning: selecting a UF must also RESET the sub-UF/região/nação facets,
// or a narrowing left over from a previous session (or a shared deep link) silently
// intersects with the click and shows the researcher less than the state they asked
// for — a wrong number with no visible cause.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { selectedSingleUf, tileSelectHandler, ufClickHandler } from './geoSelect.js';

afterEach(() => { delete window.patchFilter; });

describe('selectedSingleUf', () => {
  it('is the UF only when it is the SOLE state filter', () => {
    expect(selectedSingleUf({ states: ['PA'] })).toBe('PA');
    expect(selectedSingleUf({ states: ['PA', 'SP'] })).toBeNull();
    expect(selectedSingleUf({ states: [] })).toBeNull();
    expect(selectedSingleUf({ states: null })).toBeNull();
    expect(selectedSingleUf({})).toBeNull();
    expect(selectedSingleUf(null)).toBeNull();
  });
});

describe('ufClickHandler', () => {
  it('selects the clicked UF and clears every sub-UF/região/nação facet', () => {
    const patch = vi.fn();
    window.patchFilter = patch;
    ufClickHandler({ states: null, mesos: ['1506'], munis: ['1500107'] })('PA');
    expect(patch).toHaveBeenCalledWith({
      states: ['PA'],
      regions: null, nations: null,
      mesos: null, micros: null, inters: null, imediatas: null, munis: null,
    });
  });

  it('clicking the already-selected UF clears the state filter (toggle off)', () => {
    const patch = vi.fn();
    window.patchFilter = patch;
    ufClickHandler({ states: ['PA'] })('PA');
    expect(patch).toHaveBeenCalledWith(expect.objectContaining({ states: null }));
  });

  it('switching to a DIFFERENT UF selects it rather than clearing', () => {
    const patch = vi.fn();
    window.patchFilter = patch;
    ufClickHandler({ states: ['PA'] })('SP');
    expect(patch).toHaveBeenCalledWith(expect.objectContaining({ states: ['SP'] }));
  });

  it('ignores a falsy UF (a click that hit no feature)', () => {
    const patch = vi.fn();
    window.patchFilter = patch;
    ufClickHandler({})(undefined);
    ufClickHandler({})('');
    expect(patch).not.toHaveBeenCalled();
  });

  it('returns null with no bridge, so a caller can hand it straight to onSelect', () => {
    // An inert map beats a crash: `onSelect={null}` renders a non-clickable map.
    expect(ufClickHandler({ states: ['PA'] })).toBeNull();
  });
});

describe('tileSelectHandler', () => {
  it('unwraps the tile ROW that BrazilTileMap hands its handler', () => {
    const patch = vi.fn();
    window.patchFilter = patch;
    tileSelectHandler({})({ uf: 'MT', col: 3, row: 5, value: 42 });
    expect(patch).toHaveBeenCalledWith(expect.objectContaining({ states: ['MT'] }));
  });

  it('survives a row with no uf, and stays null with no bridge', () => {
    const patch = vi.fn();
    window.patchFilter = patch;
    tileSelectHandler({})({});
    tileSelectHandler({})(null);
    expect(patch).not.toHaveBeenCalled();
    delete window.patchFilter;
    expect(tileSelectHandler({})).toBeNull();
  });
});
