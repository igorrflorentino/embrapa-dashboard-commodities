// useGeoCascade.test.js — the geo cascade extracted from FilterMenu. Drives the
// hook via renderHook with plain fixtures (no window globals): deselecting a
// parent must prune its now-ineligible children from the selection Sets, so the
// applied filter always matches the visible cascade.

import { act, renderHook } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';

import React from 'react';

import useGeoCascade from './useGeoCascade.js';

// The ui hook reads React as a bare global (window.React in the real boot).
beforeAll(() => {
  globalThis.React = React;
});

// Two BR regions (N, SE) + one foreign region (EU/nation XX), with a state +
// município under each, so we can exercise nation→region→state→município pruning.
const UNIVERSES = {
  regionsUniverse: [
    { id: 'N', nation: 'BR' },
    { id: 'SE', nation: 'BR' },
    { id: 'EU', nation: 'XX' },
  ],
  statesUniverse: [
    { uf: 'PA', region: 'N' },
    { uf: 'SP', region: 'SE' },
    { uf: 'XX', region: 'EU' },
  ],
  munisUniverse: [
    { code: '1', uf: 'PA' },
    { code: '2', uf: 'SP' },
    { code: '3', uf: 'XX' },
  ],
};

const sorted = (set) => [...set].sort();

describe('useGeoCascade', () => {
  it('defaults to nations={BR} and prunes the foreign branch on mount', () => {
    const { result } = renderHook(() => useGeoCascade(UNIVERSES));
    // nations default = BR only.
    expect(sorted(result.current.nations)).toEqual(['BR']);
    // The EU region (nation XX) and its state/município are pruned because their
    // nation isn't selected — the cascade settles after the mount effects.
    expect(sorted(result.current.regions)).toEqual(['N', 'SE']);
    expect(sorted(result.current.states)).toEqual(['PA', 'SP']);
    expect(sorted(result.current.munis)).toEqual(['1', '2']);
  });

  it('deselecting all nations cascades to empty regions/states/municípios', () => {
    const { result } = renderHook(() => useGeoCascade(UNIVERSES));
    act(() => result.current.setNations(new Set()));
    expect(sorted(result.current.regions)).toEqual([]);
    expect(sorted(result.current.states)).toEqual([]);
    expect(sorted(result.current.munis)).toEqual([]);
  });

  it('deselecting a region prunes only that region’s states + municípios', () => {
    const { result } = renderHook(() => useGeoCascade(UNIVERSES));
    // From the settled {N, SE}, drop SE → only N's state (PA) + município (1) remain.
    act(() => result.current.setRegions(new Set(['N'])));
    expect(sorted(result.current.regions)).toEqual(['N']);
    expect(sorted(result.current.states)).toEqual(['PA']);
    expect(sorted(result.current.munis)).toEqual(['1']);
  });

  it('eligibility lists reflect the current selection (gating children by parent)', () => {
    const { result } = renderHook(() => useGeoCascade(UNIVERSES));
    expect(result.current.eligibleRegions.map((r) => r.id).sort()).toEqual(['N', 'SE']);
    act(() => result.current.setRegions(new Set(['N'])));
    expect(result.current.eligibleStates.map((s) => s.uf)).toEqual(['PA']);
    expect(result.current.eligibleMunis.map((m) => m.code)).toEqual(['1']);
  });
});

// Mesh fixture exercising the TWO parallel sub-UF divisions + the post-classic
// município (blank meso/micro). All BR, regions N (PA) + SE (SP).
const MESH = {
  regionsUniverse: [
    { id: 'N', nation: 'BR' },
    { id: 'SE', nation: 'BR' },
  ],
  statesUniverse: [
    { uf: 'PA', region: 'N' },
    { uf: 'SP', region: 'SE' },
  ],
  munisUniverse: [
    { code: '1', uf: 'PA', meso: 'M1', micro: 'mi1', intermediaria: 'I1', imediata: 'im1' },
    { code: '2', uf: 'PA', meso: 'M1', micro: 'mi2', intermediaria: 'I1', imediata: 'im2' },
    { code: '3', uf: 'PA', meso: 'M2', micro: 'mi3', intermediaria: 'I2', imediata: 'im3' },
    { code: '4', uf: 'SP', meso: 'M3', micro: 'mi4', intermediaria: 'I3', imediata: 'im4' },
    // post-classic município: NO classic meso/micro, only the 2017 branch.
    { code: '5', uf: 'PA', meso: '', micro: '', intermediaria: 'I2', imediata: 'im3' },
  ],
};

describe('useGeoCascade — dual sub-UF divisions', () => {
  it('offers both divisions, blanks excluded from the option lists', () => {
    const { result } = renderHook(() => useGeoCascade(MESH));
    expect(sorted(result.current.eligibleMesos)).toEqual(['M1', 'M2', 'M3']); // no '' option
    expect(sorted(result.current.eligibleMicros)).toEqual(['mi1', 'mi2', 'mi3', 'mi4']);
    expect(sorted(result.current.eligibleInters)).toEqual(['I1', 'I2', 'I3']);
    expect(sorted(result.current.eligibleImediatas)).toEqual(['im1', 'im2', 'im3', 'im4']);
    expect(sorted(result.current.eligibleMunis.map((m) => m.code))).toEqual(['1', '2', '3', '4', '5']);
  });

  it('deselecting a mesorregião prunes its microrregiões + municípios (classic branch)', () => {
    const { result } = renderHook(() => useGeoCascade(MESH));
    act(() => result.current.setMesos(new Set(['M2', 'M3']))); // drop M1 (munis 1,2)
    expect(sorted(result.current.eligibleMicros)).toEqual(['mi3', 'mi4']); // mi1/mi2 gone
    // muni 5 has a BLANK meso → unconstrained by the meso facet → stays.
    expect(sorted(result.current.eligibleMunis.map((m) => m.code))).toEqual(['3', '4', '5']);
    expect(sorted(result.current.munis)).toEqual(['3', '4', '5']); // selection pruned to match
  });

  it('the two divisions are INDEPENDENT — a meso change leaves imediatas untouched', () => {
    const { result } = renderHook(() => useGeoCascade(MESH));
    act(() => result.current.setMesos(new Set(['M2']))); // classic-branch change
    expect(sorted(result.current.eligibleImediatas)).toEqual(['im1', 'im2', 'im3', 'im4']);
  });

  it('the 2017 branch filters the blank-meso município that the classic branch cannot', () => {
    const { result } = renderHook(() => useGeoCascade(MESH));
    act(() => result.current.setInters(new Set(['I2']))); // keep only intermediária I2
    // munis with inter I2 = {3, 5}; muni 5 (blank meso) is reachable HERE.
    expect(sorted(result.current.eligibleMunis.map((m) => m.code))).toEqual(['3', '5']);
    expect(sorted(result.current.eligibleImediatas)).toEqual(['im3']); // only I2's imediata
  });

  it('re-selecting a parent after "Limpar" REFILLS the following children', () => {
    const { result } = renderHook(() => useGeoCascade(MESH));
    // "Limpar" the mesorregião column → FILT-3: an emptied facet means "no
    // constraint" (the same reading dataFilters.js's muniPassesFacets/`ok` already
    // gives an empty facet) — so microrregiões must stay at its FULL universe, not
    // collapse to 0. Before this fix, `passes()` read "0 selected" as "nothing
    // passes", so clearing Mesorregiões cascaded Microrregiões/Municípios to a
    // false "0 eligible" even though the filter that would actually be APPLIED
    // (an empty mesos array) treats it as fully unconstrained.
    act(() => result.current.setMesos(new Set()));
    expect(sorted(result.current.micros)).toEqual(['mi1', 'mi2', 'mi3', 'mi4']);
    // Now pick ONE mesorregião → its microrregiões must NARROW to just M1's (still
    // "following" the parent, from the full set down to the subset) — the "Limpar
    // + escolher um" UX fix this test originally locked in.
    act(() => result.current.setMesos(new Set(['M1'])));
    expect(sorted(result.current.micros)).toEqual(['mi1', 'mi2']); // M1's micros restored
    // The multi-parent município leaf also refills (via the prev-eligible "following"
    // ref, after the micro parent settles): M1's municípios 1 + 2 are back.
    expect(result.current.munis.has('1') && result.current.munis.has('2')).toBe(true);
  });

  it('FILT-3: an emptied facet is unconstrained, not "nothing eligible" (both parallel divisions)', () => {
    const { result } = renderHook(() => useGeoCascade(MESH));
    act(() => result.current.setMesos(new Set()));
    // Microrregiões (same classic branch) stays at its full universe…
    expect(sorted(result.current.eligibleMicros)).toEqual(['mi1', 'mi2', 'mi3', 'mi4']);
    // …and município (the shared leaf) is unaffected by the now-unconstrained meso
    // facet — still gated only by the (untouched) 2017 branch + states.
    expect(sorted(result.current.eligibleMunis.map((m) => m.code))).toEqual(['1', '2', '3', '4', '5']);
    act(() => result.current.setInters(new Set()));
    expect(sorted(result.current.eligibleImediatas)).toEqual(['im1', 'im2', 'im3', 'im4']);
  });

  it('clearing a level DIRECTLY does not refill it (the user choice stands)', () => {
    const { result } = renderHook(() => useGeoCascade(MESH));
    // Clearing micros directly does not change micros' OWN eligibility, so the
    // reconcile effect never refills it — the empty selection is respected.
    act(() => result.current.setMicros(new Set()));
    expect(sorted(result.current.micros)).toEqual([]);
  });

  it('deselecting a UF prunes both divisions under it', () => {
    const { result } = renderHook(() => useGeoCascade(MESH));
    act(() => result.current.setStates(new Set(['SP']))); // drop PA
    expect(sorted(result.current.eligibleMesos)).toEqual(['M3']);
    expect(sorted(result.current.eligibleInters)).toEqual(['I3']);
    expect(sorted(result.current.eligibleMunis.map((m) => m.code))).toEqual(['4']);
  });
});
