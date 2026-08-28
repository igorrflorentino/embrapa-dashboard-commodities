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
export function drillLevel(summary, muniCapable = true, subUfNarrowed = false) {
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
  // A sub-UF facet (mesorregião / microrregião / intermediária / imediata) describes a
  // grain BELOW the UF, so it belongs at município level — that is the whole point of
  // the vendored municipal meshes (PLANS/geo_subregions.md: "a sub-UF selection must
  // finally reach the MAP").
  //
  // It cannot be derived from `summary` alone: a facet key can be present while covering
  // its ENTIRE universe, which narrows nothing. dataFilters already resolves that into
  // `subUfActive`, so the caller passes the answer rather than this re-deriving it wrong.
  //
  // Missing this shipped a map that said "Brasil" over one mesorregião of Pará — and it
  // also drove the CSV export's grain, so the download matched the label, not the data.
  if (subUfNarrowed) return muniCapable ? 'municipio' : 'uf';
  if (states.length === 1) return muniCapable ? 'municipio' : 'uf';
  if (states.length > 1) return 'uf';
  if (regions.length >= 1) return 'uf';
  return 'region';
}

/** Whether the `states` sitting under a single selected region are just that region's
 *  own expansion — `enterRegion` writes BOTH keys, because a region reaches the data
 *  only THROUGH states (dataFilters.js: "cascade parents; their effect reaches the data
 *  through `states`") — rather than a narrowing the researcher chose INSIDE it.
 *
 *  One question, two consumers that must never disagree:
 *   • the trail has to SHOW a genuine narrowing, or it claims the whole region while the
 *     map plots part of it — the v1.33.2 under-reporting defect, one rung up. Measured:
 *     região Norte with only PA and AM selected rendered identically to all seven.
 *   • `stepOut` has to SKIP a mere expansion, or the first click on empty space clears
 *     `states` without changing the level OR the trail — a gesture that appears to do
 *     nothing. Measured on the most common path of all: click a region, click outside.
 *
 *  Keeping it in one function is the v1.33.2 lesson applied: two call sites deriving the
 *  same rule separately is how the trail and the level came to disagree in the first place.
 *
 *  `regionUfs` is the region's full UF list, which both callers already have. WITHOUT it
 *  we assume a narrowing — noisier ("7 UFs" under a region that IS those seven) but never
 *  dishonest and never silent, which is the right way for a missing argument to fail. */
export function isRegionExpansion(summary, regionUfs) {
  const s = summary || {};
  const regions = Array.isArray(s.regions) ? s.regions : [];
  const states = Array.isArray(s.states) ? s.states : [];
  if (regions.length !== 1 || states.length < 2) return false;
  if (!Array.isArray(regionUfs) || !regionUfs.length) return false;
  return regionUfs.every((u) => states.includes(u));
}

/** The trail from Brasil to the current selection, for a breadcrumb.
 *
 *  "Click outside to go back" is invisible until someone discovers it, and a map with
 *  no visible notion of depth leaves the researcher unsure whether they are looking at
 *  a country or a state. Each crumb is also the way back to that level. */
export function drillTrail(
  summary,
  { regionLabel, ufName, cityName, subUfLabel, regionUfs } = {},
  muniCapable = true,
) {
  const s = summary || {};
  const states = Array.isArray(s.states) ? s.states : [];
  const munis = Array.isArray(s.munis) ? s.munis : [];
  const regions = Array.isArray(s.regions) ? s.regions : [];
  const trail = [{ level: 'region', label: 'Brasil' }];
  if (regions.length === 1) {
    trail.push({ level: 'uf', label: regionLabel || regions[0], region: regions[0] });
    // A multi-UF narrowing INSIDE the region is a rung of its own and has to be visible.
    // Suppressing it (the `else if` below used to swallow it) made "Norte, only PA and AM"
    // render exactly like all seven UFs of Norte — the trail naming a set strictly larger
    // than the data, which is the no-invisible-filtering rule broken by the orientation
    // device itself. The region's own expansion is NOT such a rung and stays suppressed.
    if (states.length > 1 && !isRegionExpansion(s, regionUfs)) {
      trail.push({ level: 'uf', label: `${states.length} UFs`, ufs: true });
    }
  } else if (states.length > 1) {
    trail.push({ level: 'uf', label: `${states.length} UFs`, ufs: true });
  }
  if (states.length === 1) {
    trail.push({ level: 'municipio', label: ufName || states[0], uf: states[0] });
  }
  // The trail must not offer a level the banco cannot reach. A município facet survives
  // a banco switch, and on a UF-only banco (COMEX) drillLevel already degrades to 'uf' —
  // leaving the crumb behind showed a raw 7-digit code as the current level, and offered
  // a way "back" to somewhere the map never went.
  // A sub-UF narrowing sits between the UF and the município. Without a crumb the trail
  // stopped at "Brasil" (or at the UF) while the data underneath was one mesorregião —
  // the orientation device asserting the opposite of the truth.
  if (subUfLabel) trail.push({ level: 'municipio', label: subUfLabel, subUf: true });
  if (muniCapable) {
    if (munis.length === 1) {
      trail.push({ level: 'focus', label: cityName || String(munis[0]), muni: String(munis[0]) });
    } else if (munis.length > 1) {
      trail.push({ level: 'focus', label: `${munis.length} municípios` });
    }
  }
  return trail;
}

/** The trail's name for the ACTIVE sub-UF narrowing — every facet of it.
 *
 *  The two IBGE sub-UF divisions are PARALLEL and do not nest (classic meso→micro, 2017
 *  intermediária→imediata), and a município must clear EVERY active facet, so the
 *  effective recorte is their INTERSECTION. Naming only the first one found — which is
 *  what shipped in v1.33.1 — described a strictly larger set than the data: a reader
 *  seeing "Nordeste Paraense" concluded that was the recorte, when it was actually
 *  Nordeste Paraense ∩ Belém.
 *
 *  The rule never under-reports: one narrowing is named, two are named together, and
 *  beyond that the count stands in — a count is vaguer than a name but it cannot claim
 *  a recorte is wider than it is.
 *
 *  `mesh` resolves a facet code to its name; an unresolvable code falls back to the code
 *  itself, which is still honest about how many narrowings are in play. */
export function subUfLabel(summary, mesh) {
  const s = summary || {};
  const KEYS = [
    ['mesos', 'meso'], ['micros', 'micro'],
    ['inters', 'intermediaria'], ['imediatas', 'imediata'],
  ];
  const picked = [];
  for (const [key, meshKey] of KEYS) {
    const sel = Array.isArray(s[key]) ? s[key] : [];
    for (const code of sel) picked.push({ meshKey, code: String(code) });
  }
  if (!picked.length) return null;
  const nameOf = ({ meshKey, code }) => {
    const hit = (mesh || []).find(
      (m) => m[meshKey] && String(m[meshKey].code) === code,
    );
    return (hit && hit[meshKey] && hit[meshKey].name) || code;
  };
  if (picked.length === 1) return nameOf(picked[0]);
  if (picked.length === 2) return `${nameOf(picked[0])} · ${nameOf(picked[1])}`;
  return `${picked.length} recortes`;
}

/** How many sub-UF narrowings are in play — the number the trail must account for.
 *  Exported so a test can hold the label to it without re-deriving the rule. */
export function subUfCount(summary) {
  const s = summary || {};
  return ['mesos', 'micros', 'inters', 'imediatas'].reduce(
    (n, k) => n + (Array.isArray(s[k]) ? s[k].length : 0), 0,
  );
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
export function stepOut(summary, regionUfs) {
  const s = summary || {};
  const states = Array.isArray(s.states) ? s.states : [];
  const munis = Array.isArray(s.munis) ? s.munis : [];
  const regions = Array.isArray(s.regions) ? s.regions : [];
  if (munis.length) return { munis: null };
  // Sub-UF facets sit between the município and the UF, so they are the next rung down
  // from the top — stepping past them straight to the UF would discard a narrowing the
  // researcher never asked to leave.
  const subUf = ['mesos', 'micros', 'inters', 'imediatas'].filter(
    (k) => Array.isArray(s[k]) && s[k].length,
  );
  if (subUf.length) return Object.fromEntries(subUf.map((k) => [k, null]));
  if (states.length) {
    // The region's own expansion is not a rung the researcher stepped onto, so clearing
    // it alone changes neither the level nor the trail — a click that looks broken.
    // Step past it in one gesture, which is what "out of this region" means.
    if (isRegionExpansion(s, regionUfs)) {
      return {
        regions: null, states: null, nations: null,
        mesos: null, micros: null, inters: null, imediatas: null, munis: null,
      };
    }
    // Back to the region that contains it when we came through one; else to Brasil.
    return regions.length
      ? { states: null, mesos: null, micros: null, inters: null, imediatas: null, munis: null }
      : { states: null, regions: null, mesos: null, micros: null, inters: null, imediatas: null, munis: null };
  }
  if (regions.length) return { regions: null, states: null };
  return null; // already at Brasil — nothing above to step out to
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    drillLevel, drillTrail, enterRegion, enterUf, enterCity, stepOut,
    subUfLabel, subUfCount, isRegionExpansion,
  });
}
