// filterSummary.js — the pt-BR geographic-scope summary strings for FilterMenu.
//
// FilterMenu builds TWO geo summaries from the same selection: the live header
// line ("todo o território", lowercase) and the apply-time chip ("Todo o
// território", title case, used in the filter chip bar). Their wording differs,
// and so do their *partial* branches — the header keys on whether the banco is
// muni-SLICEABLE (a capability), the chip on whether the muni selection is FULL.
// They were buried in the 1101-line component as two inline ternary chains that
// had already drifted; co-locating them here (with a shared test) makes the
// difference explicit and keeps the two from silently diverging further.
//
// Pure string functions — no React, no window state — so they're unit-tested
// directly (filterSummary.test.js). Behaviour is preserved verbatim from the
// original inline logic.

const filterSummary = {
  // Live header line (FilterMenu.summary.geoTxt). Lowercase prose.
  geoHeaderText({
    hasGeo,
    nationsSize,
    nationsTotal,
    hasOnlyBR,
    regionsSize,
    regionsTotal,
    statesSize,
    statesTotal,
    munisSize,
    munisTotal,
    muniSliceable,
    subUf,
  }) {
    // A município count of 0 means "no município narrowing" (an emptied/cleared facet),
    // which dataFilters treats as NO constraint (shows all) — same as a full selection. So
    // 0 and full both count as muniFull, and neither renders a misleading "0 municípios".
    const muniNarrowed = muniSliceable && munisSize > 0 && munisSize < munisTotal;
    const muniFull = !muniNarrowed;
    if (!hasGeo) return 'sem recorte geográfico';
    // A sub-UF recorte (mesorregião / microrregião / região intermediária / imediata)
    // restricts the data to a FRACTION of one state, and it is invisible to every count
    // here: `statesSize` stays at its total because no UF was deselected. Without this
    // branch the summary answered "todo o território" / "Brasil · 27 UFs" for a
    // 16-município slice of the Pará — asserting the opposite of the active filter — and
    // the ABNT "consulta detalhada" reference quoted the chip verbatim, beside a
    // permalink that carried the recorte. The rule that a recorte must never be
    // described as WIDER than it is already existed for the territorial trail
    // (geoDrill.subUfLabel, v1.33.1) and for the menu's own "recorte ativo" badge; it
    // had simply never reached the two surfaces that leave the screen.
    if (subUf) return subUf;
    if (
      nationsSize === nationsTotal &&
      regionsSize === regionsTotal &&
      statesSize === statesTotal &&
      muniFull
    )
      return 'todo o território';
    if (hasOnlyBR && statesSize === statesTotal && muniFull) return 'Brasil · todos os estados';
    // FILT-4: this used to read "${statesSize} UF" unconditionally (never pluralized,
    // so 14 UFs still read "14 UF") and mention "todos os municípios" even at
    // statesSize=0 — contradicting the section summary's own "0 municípios" a few
    // lines below in FilterMenu, both built from this same file to prevent exactly
    // that drift. A município count only means something once at least one UF is
    // selected, so it's included only then — same guard the chip already applied.
    const ufLabel = `${statesSize} ${statesSize === 1 ? 'UF' : 'UFs'}`;
    if (muniSliceable && statesSize > 0) {
      const muniLabel = muniNarrowed
        ? `${munisSize} ${munisSize === 1 ? 'município' : 'municípios'}`
        : 'todos os municípios';
      return `${nationsSize} nação(ões), ${ufLabel}, ${muniLabel}`;
    }
    return `${nationsSize} nação(ões), ${ufLabel}`;
  },

  // Apply-time chip (FilterMenu.buildChipSummary.geoChip). Title case + counts.
  geoChipText({
    hasGeo,
    nationsSize,
    nationsTotal,
    hasOnlyBR,
    regionsSize,
    regionsTotal,
    statesSize,
    statesTotal,
    munisSize,
    munisTotal,
    muniSliceable,
    subUf,
  }) {
    // 0 municípios = an emptied/cleared facet = NO município narrowing (dataFilters shows
    // all), same as a full selection — so it counts as muniFull and never prints
    // "0 municípios" while the data shows every município.
    const muniNarrowed = muniSliceable && munisSize > 0 && munisSize < munisTotal;
    const muniFull = !muniNarrowed;
    if (!hasGeo) return 'Não se aplica';
    // A sub-UF recorte (mesorregião / microrregião / região intermediária / imediata)
    // restricts the data to a FRACTION of one state, and it is invisible to every count
    // here: `statesSize` stays at its total because no UF was deselected. Without this
    // branch the summary answered "todo o território" / "Brasil · 27 UFs" for a
    // 16-município slice of the Pará — asserting the opposite of the active filter — and
    // the ABNT "consulta detalhada" reference quoted the chip verbatim, beside a
    // permalink that carried the recorte. The rule that a recorte must never be
    // described as WIDER than it is already existed for the territorial trail
    // (geoDrill.subUfLabel, v1.33.1) and for the menu's own "recorte ativo" badge; it
    // had simply never reached the two surfaces that leave the screen.
    if (subUf) return subUf;
    if (hasOnlyBR && statesSize === statesTotal && muniFull) return `Brasil · ${statesTotal} UFs`;
    if (
      nationsSize === nationsTotal &&
      regionsSize === regionsTotal &&
      statesSize === statesTotal &&
      muniFull
    )
      return 'Todo o território';
    if (!muniFull)
      return `${statesSize} ${statesSize === 1 ? 'UF' : 'UFs'} · ${munisSize} ${munisSize === 1 ? 'município' : 'municípios'}`;
    return `${nationsSize} ${nationsSize === 1 ? 'nação' : 'nações'} · ${statesSize} ${statesSize === 1 ? 'UF' : 'UFs'}`;
  },
};

window.filterSummary = filterSummary;
export default filterSummary;
