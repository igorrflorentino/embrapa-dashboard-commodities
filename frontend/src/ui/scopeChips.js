// scopeChips.js — the trade-axis filter labels (fluxo · regime · mercado · reporter ·
// parceiro), resolved ONCE for every surface that has to state the active recorte.
//
// These five resolvers lived inline in FilterTriggerBar, so the chip row was the only
// thing that could name them. The ABNT "consulta detalhada" reference — whose whole job
// is to describe the exact slice — had a scope list of its own that never mentioned
// them: a Brasil→China COMTRADE panel cited as "Produtos: Todos (89). Território: Não se
// aplica.", beside a permalink that carried rp=BRA&pt=CHN. The prose contradicted its
// own link by omission.
//
// Co-located here for the same reason filterSummary.js exists: two surfaces describing
// one selection from two copies of the rule is how they drift.
//
// Each entry is { label, narrowed } or null when the active banco does not expose that
// dimension at all. `narrowed` says whether the facet actually restricts — the chip row
// shows every dimension the banco has, while the citation states only what is defining
// or restricted (the rule it already applied to quality and value range).

(function () {
  // Both paths must land on the same label: the apply path publishes a ready label
  // (summary.fluxo / .regime / .mercado / .reporter / .parceiro), while a restored deep
  // link carries only the raw code and is resolved against the registry here.
  const resolve = (readyLabel, raw, opts, allLabel) => {
    if (readyLabel) return { label: readyLabel, narrowed: readyLabel !== allLabel };
    if (!raw || raw === 'all') return { label: allLabel, narrowed: false };
    return { label: (opts || []).find((o) => o.value === raw)?.label || raw, narrowed: true };
  };

  window.tradeScopeChips = function tradeScopeChips(summary, banco) {
    const s = summary || {};
    const id = banco && banco.id;
    const provides = (banco && banco.provides) || [];

    const flow = provides.includes('flow')
      ? resolve(s.fluxo, s.flow,
                (window.flowOptionsFor && id && window.flowOptionsFor(id)) || [],
                'Todos os fluxos')
      : null;

    const regimeOpts = (window.customsOptionsFor && id && window.customsOptionsFor(id)) || null;
    const regime = regimeOpts
      ? resolve(s.regime, s.customs, regimeOpts, 'Todos os regimes') : null;

    const marketOpts = (window.marketOptionsFor && id && window.marketOptionsFor(id)) || null;
    const mercado = marketOpts
      ? resolve(s.mercado, s.market, marketOpts, 'Todos os mercados') : null;

    const hasCountry = !!(window.hasCountryFilters && id && window.hasCountryFilters(id));
    const universe = hasCountry && window.comtradeCountries ? window.comtradeCountries() : null;
    const isoNameOf = (list) => (iso) =>
      (list ? (list.find((c) => c.iso === iso) || {}).name : null) || iso;

    // Reporter always NAMES a concrete scope — its default is Brasil, not "everyone" —
    // so it is never "unrestricted" the way the others can be, and a reference that
    // leaves it out describes a wider slice than the panel.
    const reporter = hasCountry
      ? { label: s.reporter || window.chipFmt.reporter(
            s.reporters ?? null,
            universe ? universe.reporters.length : 0,
            isoNameOf(universe && universe.reporters)),
          narrowed: true }
      : null;

    const parceiro = hasCountry
      ? (() => {
          const label = s.parceiro || window.chipFmt.partner(
            s.partners ?? null,
            universe ? universe.partners.length : 0,
            isoNameOf(universe && universe.partners));
          return { label, narrowed: !/^Todos\b/.test(label) };
        })()
      : null;

    return { flow, regime, mercado, reporter, parceiro };
  };
}());
