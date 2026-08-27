// geoSelect.js — click-a-UF-to-filter, shared by every view that draws a territorial
// map (Geografia, Visão geral, Rebanho, Produtividade, Qualidade, cruzadas).
//
// The behaviour first shipped inline in ViewGeography (v1.25.0). Every OTHER map in
// the app stayed inert: the researcher could see that one state dominates and still
// had to open the filter modal and hunt through a checkbox list to act on it. Since
// they all render the same BrazilTileMap over the same `summary.states` filter, the
// handler belongs in one place rather than copied into five view files.
//
// Applies through window.patchFilter, the bridge main.jsx registers (the component
// that owns the applied filter's setState). Views call window.* helpers at render
// time, so this is exposed the same way rather than imported.

/** The UF currently selected as a SOLE state filter, or null. Drives both the
 *  toggle-off behaviour and the map's own highlight. */
export function selectedSingleUf(summary) {
  const states = summary && summary.states;
  return Array.isArray(states) && states.length === 1 ? states[0] : null;
}

/** A click handler for a UF map: selects that state, or clears it when it is already
 *  the sole selection (click again to undo).
 *
 *  Selecting also RESETS every sub-UF/região/nação facet. The researcher clicked a
 *  state on a map — they did not go through the cascade — so a narrowing left over
 *  from a previous session (or a shared deep link) must not silently intersect with
 *  the click and quietly show them less than the state they just asked for.
 *
 *  Returns null when there is no bridge to apply through, so a caller can pass the
 *  result straight to `onSelect` and get an inert map instead of a crash.
 */
export function ufClickHandler(summary) {
  if (typeof window === 'undefined' || !window.patchFilter) return null;
  const current = selectedSingleUf(summary);
  return (uf) => {
    if (!uf) return;
    const cleared = {
      regions: null, nations: null,
      mesos: null, micros: null, inters: null, imediatas: null, munis: null,
    };
    window.patchFilter(current === uf ? { states: null, ...cleared } : { states: [uf], ...cleared });
  };
}

/** BrazilTileMap hands its handler the whole row; unwrap to the sigla. */
export function tileSelectHandler(summary) {
  const onUf = ufClickHandler(summary);
  return onUf ? (row) => onUf(row && row.uf) : null;
}

if (typeof window !== 'undefined') {
  window.selectedSingleUf = selectedSingleUf;
  window.ufClickHandler = ufClickHandler;
  window.tileSelectHandler = tileSelectHandler;
}
