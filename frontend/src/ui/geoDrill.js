// geoDrill.js — the geography map as ONE drill-down surface instead of three modes.
//
// The granularity used to be a segmented control (Região | UF | Município), and picking
// "Município" with nothing narrowed produced a dead end: a card that explained you had
// to go configure a filter first. The map knew where you wanted to go and asked you to
// tell it again somewhere else.
//
// Here the level is not a setting — it is WHERE YOU ARE:
//
//     Brasil            → the five macrorregiões
//     inside a região   → that region's UFs
//     inside a UF       → that state's municípios
//     inside a município → that one município
//
// Clicking drills in, clicking empty space steps out. The +/- buttons stay pure
// magnification: they move the camera, never the grain.
//
// Drilling IS filtering, deliberately. The map click already narrowed the whole
// dashboard (geoSelect.js, v1.27.0) and every other card follows the geography filter;
// making navigation a second, parallel notion of "where" would let the map and the
// cards beside it disagree about what is being looked at.

/** The level the current selection puts you at.
 *
 *  `muniCapable` is the banco's finest grain: COMEX is origin-UF only, so a state
 *  there is the end of the road rather than a doorway to municípios. Several states
 *  selected at once (from the filter menu, not by clicking) sit at UF level — there is
 *  no single municipal mesh to drill into, and pretending otherwise would either show
 *  one state's cities or silently pick one. */
export function drillLevel(summary, muniCapable = true) {
  const s = summary || {};
  const states = Array.isArray(s.states) ? s.states : [];
  const munis = Array.isArray(s.munis) ? s.munis : [];
  const regions = Array.isArray(s.regions) ? s.regions : [];
  // ANY município selection sits at município level — not just a single one. A
  // multi-city facet (several municípios, possibly across UFs) is still a municipal
  // question; sending it back to 'region' would answer a different one.
  //
  // But only where the banco HAS that grain. The geography filter is shared, so a
  // município facet survives a banco switch: drilling into a city on IBGE PEVS and then
  // moving to MDIC COMEX (origin-UF only) used to leave COMEX at município level,
  // serving a grain it does not have. The segmented control had an explicit effect for
  // this; deriving the level dropped it, and this branch is where it belongs.
  if (munis.length >= 1) return muniCapable ? 'municipio' : 'uf';
  if (states.length === 1) return muniCapable ? 'municipio' : 'uf';
  if (states.length > 1) return 'uf';
  if (regions.length >= 1) return 'uf';
  return 'region';
}

/** The trail from Brasil to the current selection, for a breadcrumb.
 *
 *  "Click outside to go back" is invisible until someone discovers it, and a map with
 *  no visible notion of depth leaves the researcher unsure whether they are looking at
 *  a country or a state. Each crumb is also the way back to that level. */
export function drillTrail(summary, { regionLabel, ufName, cityName } = {}, muniCapable = true) {
  const s = summary || {};
  const states = Array.isArray(s.states) ? s.states : [];
  const munis = Array.isArray(s.munis) ? s.munis : [];
  const regions = Array.isArray(s.regions) ? s.regions : [];
  const trail = [{ level: 'region', label: 'Brasil' }];
  if (regions.length === 1) {
    trail.push({ level: 'uf', label: regionLabel || regions[0], region: regions[0] });
  } else if (states.length > 1) {
    trail.push({ level: 'uf', label: `${states.length} UFs` });
  }
  if (states.length === 1) {
    trail.push({ level: 'municipio', label: ufName || states[0], uf: states[0] });
  }
  // The trail must not offer a level the banco cannot reach. A município facet survives
  // a banco switch, and on a UF-only banco (COMEX) drillLevel already degrades to 'uf' —
  // leaving the crumb behind showed a raw 7-digit code as the current level, and offered
  // a way "back" to somewhere the map never went.
  if (muniCapable) {
    if (munis.length === 1) {
      trail.push({ level: 'focus', label: cityName || String(munis[0]), muni: String(munis[0]) });
    } else if (munis.length > 1) {
      trail.push({ level: 'focus', label: `${munis.length} municípios` });
    }
  }
  return trail;
}

/** The filter patch that ENTERS a level. Every step also clears the facets below it,
 *  so a narrowing left over from a previous session can never silently intersect with
 *  a click the researcher just made (the rule geoSelect.js established). */
export function enterRegion(regionId, ufsOfRegion) {
  return {
    regions: regionId ? [regionId] : null,
    states: regionId && ufsOfRegion && ufsOfRegion.length ? ufsOfRegion : null,
    nations: null, mesos: null, micros: null, inters: null, imediatas: null, munis: null,
  };
}

export function enterUf(uf) {
  return {
    states: uf ? [uf] : null,
    mesos: null, micros: null, inters: null, imediatas: null, munis: null,
  };
}

export function enterCity(code) {
  return { munis: code ? [String(code)] : null };
}

/** The patch that steps OUT one level from wherever the selection is.
 *
 *  Exactly one level per gesture: dropping straight to Brasil from a município would
 *  discard the state the researcher drilled through, which they did not ask to leave. */
export function stepOut(summary) {
  const s = summary || {};
  const states = Array.isArray(s.states) ? s.states : [];
  const munis = Array.isArray(s.munis) ? s.munis : [];
  const regions = Array.isArray(s.regions) ? s.regions : [];
  if (munis.length) return { munis: null };
  if (states.length) {
    // Back to the region that contains it when we came through one; else to Brasil.
    return regions.length
      ? { states: null, mesos: null, micros: null, inters: null, imediatas: null, munis: null }
      : { states: null, regions: null, mesos: null, micros: null, inters: null, imediatas: null, munis: null };
  }
  if (regions.length) return { regions: null, states: null };
  return null; // already at Brasil — nothing above to step out to
}

if (typeof window !== 'undefined') {
  Object.assign(window, { drillLevel, drillTrail, enterRegion, enterUf, enterCity, stepOut });
}
