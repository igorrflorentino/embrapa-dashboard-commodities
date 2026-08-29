// dataFilters.js — applies the active filter selection to every dataset
// used by the views, so charts/KPIs ONLY show rows that match.
//
// Input shape (from FilterMenu.onApply):
//   { basket:    string[]  // product codes;  null = all · [] = none
//   , flags:     string[]  // quality flags;   null = all · [] = none
//   , states:    string[]  // UF codes;        null = all · [] = none
//   , munis:     string[]  // município codes (cascade); narrows the município cube
//                          //   (and thus the cube-ranked topMunis), code-keyed
//   , nations, regions     // cascade parents; their effect reaches the data
//                          //   through `states` (deselecting prunes states)
//   , startDate, endDate   // 'YYYY-MM-01'
//   , valueMin, valueMax   // row-level value filter (banco base currency)
//   }
//
// Output: { ts, productTS, ufData, regionData, topMunis, topProducts,
//           qualityFlags, qualityTs, selectedProducts, yearStart, yearEnd,
//           notFilteredByBasket, _shares }

(function () {
  const yearOf = (iso) => iso ? parseInt(iso.slice(0, 4), 10) : null;

  // Heuristic share of rows that pass the row-level value filter.
  // Used only to scale the "Linhas" provenance counter; not data display.
  // The thresholds + shares come from the shared window.VALUE_PRESETS
  // (filtersSchema.js). There is no real backend COUNT for a value threshold yet,
  // so rather than assert a fabricated filtered count we leave the "Linhas" counter
  // at the unfiltered total (share 1.00) for every value-threshold — presets AND a
  // custom range alike — until a real /api count exists.
  function valueShareForRange(min, max) {
    if (min == null && max == null) return 1.00;
    if (min === 0 && max == null)   return 1.00;
    const preset = (window.VALUE_PRESETS || []).find(p => p.min === min && p.max === max);
    if (preset) return preset.rowShare;
    return 1.00; // custom range — no fabricated share (was 0.66)
  }

  // ── Sub-UF / município geography facets (the IBGE mesh cascade) ─────────────
  // The FilterMenu emits five CODE arrays — mesos/micros (classic division) +
  // inters/imediatas (2017 division) + munis. A facet CONSTRAINS the data only when
  // it is a PROPER, NON-EMPTY subset of its universe: null, [] (a cascade-emptied
  // child — selecting a parent after "Limpar" leaves children empty), and the full
  // selection ALL mean "no constraint". This both avoids fetching the heavy município
  // cube when nothing is narrowed AND keeps a parent-only narrowing (e.g. one
  // mesorregião, children untouched/empty) correct. Needs the mesh for the per-level
  // universe sizes.
  const GEO_FACET_KEYS = ['mesos', 'micros', 'inters', 'imediatas', 'munis'];
  const _facetCode = {
    mesos: (m) => (m.meso && m.meso.code) || '',
    micros: (m) => (m.micro && m.micro.code) || '',
    inters: (m) => (m.intermediaria && m.intermediaria.code) || '',
    imediatas: (m) => (m.imediata && m.imediata.code) || '',
    munis: (m) => m.cityCode,
  };
  function geoFacetSets(summary, mesh) {
    const sets = {};
    const constrained = {};
    const universe = {};
    if (mesh) {
      for (const k of GEO_FACET_KEYS) {
        const u = new Set();
        for (const m of mesh) { const c = _facetCode[k](m); if (c) u.add(c); }
        universe[k] = u.size;
      }
    }
    let active = false;
    for (const k of GEO_FACET_KEYS) {
      const arr = summary[k];
      sets[k] = arr == null ? null : new Set(arr);
      const c = !!(mesh && sets[k] && sets[k].size > 0 && sets[k].size < (universe[k] || Infinity));
      constrained[k] = c;
      if (c) active = true;
    }
    return { sets, constrained, active };
  }
  // A município passes a facet iff that facet does NOT constrain, or its code is in
  // the selection. A blank code ('' — e.g. a post-classic município has no classic
  // meso/micro) is never in the set, so a NARROWING classic facet correctly excludes
  // it (it genuinely belongs to no mesorregião); it stays filterable by the 2017
  // levels it does have, and is unaffected when a facet isn't narrowing.
  function muniPassesFacets(anc, gf) {
    const ok = (k, code) => !gf.constrained[k] || gf.sets[k].has(code);
    return ok('mesos', (anc.meso && anc.meso.code) || '')
      && ok('micros', (anc.micro && anc.micro.code) || '')
      && ok('inters', (anc.intermediaria && anc.intermediaria.code) || '')
      && ok('imediatas', (anc.imediata && anc.imediata.code) || '')
      && (!gf.constrained.munis || gf.sets.munis.has(anc.cityCode));
  }
  // Roll the município cube up to (UF, year), summing ONLY the municípios that clear
  // every active facet (resolved via the mesh cityCode→ancestry). Output rows are
  // shape-identical to the UF cube (window.geoYearly), so they slot straight into the
  // existing geoSource / ufData / sumStates logic — the map stays a UF choropleth,
  // narrowed to the selected sub-UF groups.
  function rollupMuniCubeToUf(muniCube, mesh, gf) {
    const anc = {};
    for (const m of mesh) anc[m.cityCode] = m;
    const byUfYear = new Map();
    for (const r of muniCube) {
      const a = anc[r.cityCode];
      if (!a || !muniPassesFacets(a, gf)) continue;
      const key = `${r.uf}|${r.year}`;
      let row = byUfYear.get(key);
      if (!row) { row = { uf: r.uf, year: r.year, value: 0, q_mass: 0, q_vol: 0, q_count: 0 }; byUfYear.set(key, row); }
      row.value += r.value || 0;
      row.q_mass += r.q_mass || 0;
      row.q_vol += r.q_vol || 0;
      row.q_count += r.q_count || 0;
    }
    return [...byUfYear.values()];
  }

  window.applyFilters = function (summary, bancoId) {
    summary = summary || {};

    // ── Resolve the in-memory snapshot for the active banco ────────────
    // Banco-aware seam: when a bancoId is given and its snapshot is loaded,
    // read from it. Every call site passes the active bancoId; the snapshot is
    // the single data source (src/data/dataStore.js → /api/snapshot).
    const fromStore = (bancoId && window.dataStore && window.dataStore.get)
      ? window.dataStore.get(bancoId) : null;
    // Optional per-banco fallback hook (window.snapshotFor) — returns null today,
    // kept as a seam for a future pre-load source.
    const fromSynth = (!fromStore && bancoId && window.snapshotFor)
      ? window.snapshotFor(bancoId) : null;
    // No snapshot loaded yet (or it errored): degrade to an EMPTY dataset so the
    // views render blank rather than fabricated figures. (The prototype used to
    // fall back to synthetic PEVS globals here; those were removed with the move
    // to the API-backed snapshot — see src/data/.)
    const snap = fromStore || fromSynth || {
      products: [], productTS: {}, overviewTS: [], ufData: [], ufYearly: [],
      quality: [], qualityTs: [], topMunis: [], regions: window.REGIONS || [],
      qualityByProduct: [], qualityByUf: [],
    };
    const PRODUCTS_T   = snap.products   || [];
    const PRODUCT_TS_T = snap.productTS  || {};
    const OVERVIEW_T   = snap.overviewTS || [];
    const UF_DATA_T    = snap.ufData     || [];
    const QUALITY_T    = snap.quality    || [];
    const QUALITY_TS_T = snap.qualityTs  || [];
    const REGIONS_T    = snap.regions    || window.REGIONS || [];

    const allProducts = PRODUCTS_T.map(p => p.code);
    // Distinguish "no product filter applied" (basket == null → all) from
    // "explicitly cleared" (basket == [] → none). Zero always means none.
    const basket = summary.basket == null ? allProducts : summary.basket;
    const selectedProducts = basket.filter(c => allProducts.includes(c));

    const yearStart = yearOf(summary.startDate) || (OVERVIEW_T[0] && OVERVIEW_T[0].y) || 1986;
    const yearEnd   = yearOf(summary.endDate)   || (OVERVIEW_T[OVERVIEW_T.length - 1] && OVERVIEW_T[OVERVIEW_T.length - 1].y) || 2024;

    // Same null-vs-empty rule as the basket: undefined/null = "no filter"
    // (all); an explicit empty array = "none selected" (zero rows). An empty
    // Set is truthy, so the `!set ||` / `set ?` guards downstream correctly
    // resolve null→all and empty-Set→none.
    const flagSet  = summary.flags  == null ? null : new Set(summary.flags);
    const stateSet = summary.states == null ? null : new Set(summary.states);

    // ── Geography-aware aggregation (product × UF × year) ──────────────
    // The national per-product series (PRODUCT_TS_T) can honour a product basket
    // and a year window, but NOT a state filter (it has no UF grain). The snapshot's
    // ufYearly carries (UF × year) but is ALL-products (so it can honour state + year
    // but not a basket). To make VALOR TOTAL / the choropleth / the series respect
    // state + product + period TOGETHER, we pull a basket-scoped (UF × year) cube on
    // demand (window.geoYearly → /api/geo-yearly) and aggregate it client-side.
    const hasGeoData = UF_DATA_T.length > 0;
    const ufYearlyAll = Array.isArray(snap.ufYearly) ? snap.ufYearly : [];
    // A basket genuinely narrows products only when a proper, non-empty subset is
    // selected (null = all; [] = none → handled by the empty-series path below).
    const basketActive =
      hasGeoData && summary.basket != null &&
      selectedProducts.length > 0 && selectedProducts.length < allProducts.length;
    // A state filter genuinely narrows only below the canonical 27-UF universe (the
    // all-selected default is NOT a narrowing). Summing the (UF × year) grid over a
    // proper subset is the only case where it diverges from the national series.
    const _ufUniverse = (window.UF_DATA || []).length || 27;
    const stateNarrowing =
      hasGeoData && stateSet != null &&
      (stateSet.size === 0 || stateSet.size < _ufUniverse);
    // Sub-UF / município narrowing (the IBGE mesh cascade): when the user picks
    // specific meso/micro/intermediária/imediata/município groups, the UF cube is too
    // coarse — pull the município cube (basket-scoped, /api/municipio-yearly) and roll
    // it up to (UF, year) over ONLY the municípios passing every active facet (via the
    // mesh). The result is UF-yearly rows, so it flows through the SAME series/map
    // logic below; the map stays a UF choropleth, narrowed to the chosen sub-UF groups.
    // Fetch the mesh up front (cheap, cached) so geoFacetSets can size each facet's
    // universe and decide whether it genuinely narrows (proper non-empty subset).
    // Only a NON-EMPTY facet array is a real narrowing that needs the heavy IBGE mesh:
    // null (all) and [] (a cascade-emptied child) both mean "no constraint" (see above),
    // so a trade banco — whose hidden cascade stays at full selection (→ null) — never
    // triggers a wasted ~5570-row mesh fetch (DATA-2).
    const _hasGeoKeys = GEO_FACET_KEYS.some((k) => Array.isArray(summary[k]) && summary[k].length);
    const mesh = (_hasGeoKeys && window.geoMesh) ? window.geoMesh() : null;
    // A real sub-UF narrowing was requested but the mesh hasn't landed yet: treat the
    // geography as PENDING (below) so the views show loading rather than the un-narrowed
    // all-UF grid for that transient (GEO-2). Mitigated by main.jsx warming the mesh at
    // startup, so this is usually already false by the time a filter is applied.
    const subUfMeshPending = _hasGeoKeys && !mesh;
    const geoFacets = geoFacetSets(summary, mesh);
    // Resolve the active sub-UF/município selection to its município code set (via the
    // mesh) and pass it to the cube, so the Gold scan covers only those cities.
    const narrowedCities = (geoFacets.active && mesh)
      ? mesh.filter((m) => muniPassesFacets(m, geoFacets)).map((m) => m.cityCode)
      : null;
    // A sub-UF/município narrowing is active once the mesh is loaded AND a facet narrows.
    const subUfActive = narrowedCities != null;
    // The município cube is TRI-STATE: null = fetch in flight; [] = loaded-but-empty
    // (zero cities pass the facets, or those cities produce none of the basket); [...] =
    // rows. We MUST distinguish loaded-empty from not-loaded so an empty selection shows
    // an honest "no data" instead of an eternal spinner — and NEVER falls back to the
    // all-UF grid (which would display data the selection explicitly excludes).
    const muniCube = subUfActive
      ? (narrowedCities.length && window.municipioYearly
          ? window.municipioYearly(bancoId, summary, narrowedCities)
          : []) // zero cities pass → determinately empty, not a pending fetch
      : null;
    const subUfLoaded = subUfActive && muniCube != null; // [] counts as loaded
    const subUfCube = (subUfLoaded && mesh) ? rollupMuniCubeToUf(muniCube, mesh, geoFacets) : null;
    // The basket-scoped (UF × year) cube (null until the fetch lands, or for a non-geo
    // banco). Only fetched when a basket is active — a state-only narrowing reads the
    // all-products ufYearly already in the snapshot (no extra round-trip).
    const basketGeoCube = (basketActive && window.geoYearly)
      ? window.geoYearly(bancoId, summary) : null;
    // Precedence: a sub-UF narrowing OWNS the geo grid (its rollup once loaded — even
    // when empty); else the basket cube; else the snapshot's all-products grid.
    const geoCube = subUfActive ? subUfCube : basketGeoCube;
    const useCube = subUfActive ? subUfLoaded : !!(geoCube && geoCube.length);
    // Pending ONLY while the cube fetch is in flight (null) — NOT when it loaded empty.
    const subUfPending = hasGeoData && subUfActive && !subUfLoaded;
    // The (UF × year) source for the geo-derived series/map. A sub-UF narrowing reads its
    // own rollup (rows, or [] when empty/pending) — never the all-UF fallback; else the
    // basket cube when ready, else the snapshot's all-products grid.
    const geoSource = subUfActive ? (subUfCube || []) : (useCube ? geoCube : ufYearlyAll);
    // When narrowing states, restrict to the selected UFs; with no narrowing sum the
    // WHOLE grid (incl. COMEX non-state pseudo-origins) so the national total matches
    // PRODUCT_TS_T exactly (those pseudo-origins are not selectable UFs).
    const sumStates = (rows, y) => {
      let v = 0, qMass = 0, qVol = 0, qCount = 0;
      for (const r of rows) {
        if (r.year !== y) continue;
        if (stateNarrowing && !stateSet.has(r.uf)) continue;
        v += (r.value || 0) / 1000;     // ufYearly value is mi → ts.v is bi
        qMass += (r.q_mass || 0);        // already mil t
        qVol  += (r.q_vol  || 0);        // already mi m³
        qCount += (r.q_count || 0);      // already mi un (livestock head / eggs)
      }
      return { v, q_mass: qMass, q_vol: qVol, q_count: qCount };
    };
    // Engage the geo-derived series only when it adds correctness the national series
    // can't: a real state narrowing, OR a basket whose territorial cube has loaded —
    // and only when the (UF × year) grid actually carries rows (a snapshot without
    // ufYearly falls back to the national series rather than zeroing it out).
    // For a sub-UF narrowing, ALWAYS use the cube-derived series once loaded — even if
    // it sums to zero (an empty selection must read as zero, not the national curve).
    const geoDerivedTs = hasGeoData && (
      (subUfActive && subUfLoaded) ||
      (!subUfActive && geoSource.length > 0 && (stateNarrowing || useCube))
    );

    // ── Aggregated time series ────────────────────────────────────────
    const allYears = OVERVIEW_T.map(d => d.y).filter(y => y >= yearStart && y <= yearEnd);
    const ts = allYears.map(y => {
      if (geoDerivedTs) {
        const g = sumStates(geoSource, y);
        return { y, v: g.v, q: g.q_mass, q_mass: g.q_mass, q_vol: g.q_vol, q_count: g.q_count };
      }
      // National path (no state narrowing): per-product series, basket + year aware.
      let v = 0, qMass = 0, qVol = 0, qCount = 0;
      selectedProducts.forEach(code => {
        const series = PRODUCT_TS_T[code];
        if (!series) return;
        const pt = series.find(p => p.y === y);
        if (!pt) return;
        v += pt.v / 1000;                    // productTS.v is mi → ts.v is bi
        if (pt.family === 'mass')   qMass += pt.q;
        if (pt.family === 'volume') qVol  += pt.q;
        if (pt.family === 'count')  qCount += pt.q;  // head/eggs — never blended with mass/vol
      });
      return { y, v, q: qMass, q_mass: qMass, q_vol: qVol, q_count: qCount };
    });

    // ── Per-product time series, restricted to basket + window ───────
    const productTS = {};
    selectedProducts.forEach(code => {
      const series = PRODUCT_TS_T[code];
      if (!series) return;
      productTS[code] = series.filter(d => d.y >= yearStart && d.y <= yearEnd);
    });

    // ── UF / region / municipio data ─────────────────────────────────────
    // Per-UF rows for the choropleth + ranking, restricted by the state filter and —
    // when the basket's (UF × year) cube has loaded (useCube) — by the product basket
    // too, so the map reflects the SELECTED products. Until that cube lands (or when
    // no basket is active) the map shows the snapshot's latest-year per-UF totals
    // (all products), narrowed by state. State filtering is always exact.
    // `notFilteredByBasket` stays true ONLY while a basket is active but its cube has
    // not loaded — the geo views render an honest pt-BR note for that transient. The
    // old code faked a basket × UF split by scaling every UF uniformly by selected/all
    // (fabricated geography); the cube is the REAL product × UF × year grain instead.
    const notFilteredByBasket = hasGeoData && basketActive && !useCube;
    // The ONE combination the client cannot aggregate faithfully: BOTH a product
    // basket AND a UF subset, before the product×UF×year cube has loaded. The
    // national per-product series has no UF grain; the all-products UF grid has no
    // basket grain — so the geo-derived `ts` here would sum ALL products over the
    // selected UFs, SILENTLY dropping the basket from VALOR TOTAL / YoY / acumulada.
    // We refuse to show that wrong number: flag it so the view holds the value at a
    // loading state until the cube resolves (then it computes the exact selection),
    // instead of reporting a figure that disregards the user's product filter.
    const geoComboPending =
      (hasGeoData && basketActive && stateNarrowing && !useCube) ||
      subUfPending ||
      (hasGeoData && subUfMeshPending);

    // Tile-grid (col/row) join for cube-derived UF rows: the snapshot's ufData is
    // already decorated (decorate.js), but cube rows come straight from the serializer,
    // so attach col/row/name/region from the UF registry (mirrors decorateUfRows).
    const _ufTiles = {};
    (window.UF_DATA || []).forEach(u => { _ufTiles[u.uf] = u; });
    const _normRegion = window.normalizeRegion || ((api, tile) => api || tile);
    const _decorateUf = (rows) => rows.map(r => {
      const t = _ufTiles[r.uf] || {};
      // Normalize region to the canonical CODE — same as decorateUfRows — so the
      // cube-derived ufData matches the regionData groupBy (`u.region === r.id`).
      return { ...r, col: r.col ?? t.col, row: r.row ?? t.row,
               region: _normRegion(r.region, t.region), name: r.name || t.name };
    });

    // The per-(UF, year) grid backing the map + its TRUE data year: the basket cube
    // when loaded, else the snapshot's all-products grid. The map's data year is the
    // max reference_year present IN the window (NOT yearEnd) — if the endDate runs past
    // the last year with UF rows (future/partial trade year), labelling with yearEnd
    // would lie. Falls back to yearEnd when the grid is empty (synthetic/older payloads).
    const ufYearly = geoSource;
    const ufYearsInWindow = ufYearly
      .map(r => r.year)
      .filter(y => typeof y === 'number' && y >= yearStart && y <= yearEnd);
    const ufLatestYear = ufYearsInWindow.length ? Math.max(...ufYearsInWindow) : yearEnd;
    // A sub-UF narrowing reads the cube even while pending/empty (geoCube=null → []),
    // so the map shows loading/empty rather than the all-UF snapshot it excludes.
    const _ufRowsWhere = (keep) => (subUfActive || useCube)
      ? _decorateUf(
          (geoCube || [])
            .filter(r => r.year === ufLatestYear)
            .filter(u => keep(u.uf))
            .map(r => ({ uf: r.uf, name: r.name, region: r.region,
                         value: r.value, q_mass: r.q_mass, q_vol: r.q_vol, q_count: r.q_count })),
        )
      : UF_DATA_T
          .filter(u => keep(u.uf))
          .map(u => ({ ...u }));
    const ufData = _ufRowsWhere(uf => !stateSet || stateSet.has(uf));
    // The same rows with the STATE filter lifted — the honest denominator for the
    // "parcial" mark on region totals below. Deliberately the IDENTICAL path (same year,
    // same basket, same sub-UF scope), so the count it yields means exactly "what this
    // would show if you cleared the UF filter" and nothing else. No extra work when
    // there is no filter to lift.
    const ufDataNoStateFilter = stateSet ? _ufRowsWhere(() => true) : ufData;
    // The map year is "partial" when it falls SHORT of the requested window end — the
    // researcher asked through yearEnd but the latest UF data stops earlier (newer year
    // not yet in Gold, or an in-progress year). Lets the geo views annotate honestly.
    const ufYearPartial = hasGeoData && ufLatestYear < yearEnd;

    // The "UFs cobertas" denominator (ViewOverview/MainScreen) must be the banco's
    // ALL-TIME UF universe, not just the latest year's UFs. ufData is latest-year-
    // scoped (see above), so using it as the denominator would, on a SPARSE trade
    // year (fewer states reporting), under-count the universe. ufYearly spans every
    // covered year, so its distinct UF set IS the all-time universe — first row per
    // UF carries name/region/real for the real-UF tally. Fall back to the latest-year
    // ufData when ufYearly is absent (synthetic / older payloads). Counts are capped
    // at 27 downstream, so this only ever CORRECTS an under-count, never inflates.
    // Always derived from the ALL-products grid (ufYearlyAll), never the basket cube —
    // the denominator is the banco's FULL territorial universe, so it stays "/27"
    // rather than shrinking to the subset of UFs that happen to grow the basket.
    const ufUniverse = (() => {
      if (!ufYearlyAll.length) return UF_DATA_T;
      const seen = new Map();
      ufYearlyAll.forEach(r => { if (!seen.has(r.uf)) seen.set(r.uf, r); });
      return Array.from(seen.values());
    })();

    // productShare is NO LONGER used to scale displayed UF/region/heatmap values
    // (that fabricated geography — see above). It survives only as an ESTIMATED
    // multiplier for the hero "Linhas" provenance counter (MainScreen), where an
    // approximate row count is acceptable and clearly labelled as a selection size.
    const productShare = allProducts.length ? (selectedProducts.length / allProducts.length) : 0;

    // region totals derived from the REAL (state-filtered) ufData
    //
    // A row here NAMES a whole region but SUMS only the UFs that survived the filter:
    // with the Pará selected, `{ id: 'N', label: 'Norte' }` carries the PARÁ's number.
    // Summing only what is filtered is correct (never show data outside the filter) —
    // presenting it under the region's bare name is not. That is the same wrong-subject
    // defect as labelling a region's value with a UF's name (v1.33.25), one grain up.
    // So each row also carries WHAT IT IS MADE OF, and the views spell it out.
    const regionData = REGIONS_T.map(r => {
      const ufs = ufData.filter(u => u.region === r.id);
      const unfiltered = ufDataNoStateFilter.filter(u => u.region === r.id);
      return {
        ...r,
        value:  ufs.reduce((s, u) => s + u.value,  0),
        q_mass: ufs.reduce((s, u) => s + u.q_mass, 0),
        q_vol:  ufs.reduce((s, u) => s + u.q_vol,  0),
        q_count: ufs.reduce((s, u) => s + (u.q_count || 0), 0),  // head/eggs — herd geo
        ufs:    ufs.length,
        // How many UFs this region WOULD carry without the state filter, and whether the
        // sum is therefore a fraction of the region it is named after.
        ufsTotal: unfiltered.length,
        partial:  ufs.length < unfiltered.length,
        // The UFs actually summed, biggest first (name tie-break keeps it deterministic
        // for a value-less banco, where every value is 0 — the livestock herd).
        ufNames: ufs.slice()
          .sort((a, b) => (b.value || 0) - (a.value || 0)
                       || String(a.name || a.uf).localeCompare(String(b.name || b.uf), 'pt-BR'))
          .map(u => u.name || u.uf),
      };
    }).filter(r => r.ufs > 0);

    // top municipios — ranked from the REAL basket-scoped município cube
    // (window.municipioYearly), latest year in window, cityCode→name via the mesh.
    // The cube is fetched only when a sub-UF/município narrowing is active, so without
    // a narrowing the list is empty and the Geografia view shows an honest empty-state
    // (prompting a sub-UF/município filter) rather than a silently blank panel. This
    // replaces the legacy name-keyed snapshot.topMunis path, which had no backend
    // producer (always []) and a dead muniNames filter. Values are already at the
    // município grain and per-family scaled identically to ufData (value mi, q_mass
    // mil t, q_vol mi m³, q_count mi un), so they slot into the same valueKey/mul.
    let topMunis = [];
    if (subUfLoaded && mesh && Array.isArray(muniCube) && muniCube.length) {
      const meshByCode = {};
      for (const m of mesh) meshByCode[m.cityCode] = m;
      const muniYears = muniCube
        .map(r => r.year)
        .filter(y => typeof y === 'number' && y >= yearStart && y <= yearEnd);
      const muniLatest = muniYears.length ? Math.max(...muniYears) : null;
      if (muniLatest != null) {
        topMunis = muniCube
          .filter(r => r.year === muniLatest)
          .filter(r => !stateSet || stateSet.has(r.uf))
          // Apply the same facet filter as the UF rollup — robust even if the cube
          // returns cities beyond the narrowed set (it shouldn't, but don't trust it).
          .filter(r => { const a = meshByCode[r.cityCode]; return a && muniPassesFacets(a, geoFacets); })
          .map(r => ({
            // cityCode is the IBGE 7-digit code — the join key for the municipal
            // choropleth (it matches `codarea` in the vendored per-UF meshes).
            cityCode: r.cityCode,
            city: (meshByCode[r.cityCode] || {}).cityName || r.cityCode,
            uf: r.uf,
            product: '',  // the cube is basket-aggregated (no per-product split here)
            value: r.value, q_mass: r.q_mass, q_vol: r.q_vol, q_count: r.q_count,
          }))
          .sort((a, b) => (b.value || 0) - (a.value || 0));
        // NOT truncated here. This used to .slice(0, 100), which is a DISPLAY cap
        // living in the engine — and once the municipal choropleth started drawing
        // from these rows it turned into a data error: every município past rank 100
        // had no row to match, so the map painted it as "sem produção registrada"
        // and counted it in the grey tally (PA: 144 municípios → a false "44 sem
        // produção"). The view caps the RANKING it lists; the map needs them all.
      }
    }

    // ── Top products composition (donut / share) ─────────────────────
    // Take last endpoint from per-product TS, keep only basket products.
    const compositionRaw = selectedProducts
      .map(code => {
        const prod = PRODUCTS_T.find(p => p.code === code);
        const series = PRODUCT_TS_T[code];
        if (!prod || !series) return null;
        const lastInWindow = series.filter(d => d.y >= yearStart && d.y <= yearEnd).slice(-1)[0];
        if (!lastInWindow) return null;
        return { name: prod.name, value: lastInWindow.v };
      })
      .filter(Boolean)
      .sort((a, b) => b.value - a.value);
    const compTotal = compositionRaw.reduce((s, p) => s + p.value, 0) || 1;
    const COLORS = [...window.VIZ_SCALE, 'var(--pres-gray-300)', 'var(--pres-gray-400)'];
    let topProducts;
    if (compositionRaw.length <= 7) {
      topProducts = compositionRaw.map((p, i) => ({
        ...p, share: p.value / compTotal, color: COLORS[i % COLORS.length],
      }));
    } else {
      const head = compositionRaw.slice(0, 6);
      const tail = compositionRaw.slice(6);
      const tailVal = tail.reduce((s, p) => s + p.value, 0);
      topProducts = [
        ...head.map((p, i) => ({ ...p, share: p.value / compTotal, color: COLORS[i] })),
        { name: 'Outros', value: tailVal, share: tailVal / compTotal,
          color: 'var(--pres-gray-200)', muted: true },
      ];
    }

    // ── Quality flag distribution ─────────────────────────────────────
    const qualityFlagsAll = QUALITY_T;
    const filteredFlags = flagSet
      ? qualityFlagsAll.filter(f => flagSet.has(f.id))
      : qualityFlagsAll;
    // re-normalize shares to selected flags' world
    const flagTotal = filteredFlags.reduce((s, f) => s + f.count, 0) || 1;
    const qualityFlags = filteredFlags.map(f => ({ ...f, share: f.count / flagTotal }));

    // quality time series — pass-through, optionally trim to window
    const qualityTs = QUALITY_TS_T.filter(d => d.y >= yearStart && d.y <= yearEnd);

    // ── Row counter (for hero "SELEÇÃO ATIVA · Linhas") ────────────────
    const valueShare = valueShareForRange(summary.valueMin, summary.valueMax);
    const flagShare  = flagSet
      ? filteredFlags.reduce((s, f) => s + f.share, 0)
      : 1;
    // yearShare = fraction of the banco's COVERED years that fall in the window. Base it
    // on the COUNT of covered years in-window over the total covered count — never the
    // window SPAN (yearEnd-yearStart+1) over the count, which a gap-y annual series makes
    // >1 (M1). Clamp for safety.
    const _yearsInWindow = (OVERVIEW_T || []).filter(d => d.y >= yearStart && d.y <= yearEnd).length;
    const yearShare = Math.min(1, _yearsInWindow / ((OVERVIEW_T && OVERVIEW_T.length) || 39));
    // stateShare = selected UFs over the banco's REAL UF universe. Numerator and
    // denominator must share a universe: count only real UFs (a trade banco's ufData
    // carries non-state pseudo-origins ND/EX/ZN that must not shrink the denominator),
    // and clamp at 1 so a mismatch never yields >100% (M1). stateSet is null when the
    // selection is full (applyAndClose normalizes full→null) → "no narrowing" → 1.
    const _realUfCount = ((UF_DATA_T || []).filter(u => u.real !== false).length) || 27;
    const stateShare = stateSet ? Math.min(1, stateSet.size / _realUfCount) : 1;

    return {
      ts, productTS, ufData, regionData, topMunis, topProducts,
      qualityFlags, qualityTs, selectedProducts,
      yearStart, yearEnd,
      // The choropleth/tile map's TRUE data year (max UF year within the window),
      // and whether it stops short of the requested yearEnd. The geo views label the
      // map with `ufLatestYear` (not `yearEnd`) and annotate `ufYearPartial` so the
      // year shown always matches the data plotted (FINDING #1).
      ufLatestYear, ufYearPartial,
      // Banco-aware metadata so product/quality views read the ACTIVE banco's
      // dimensions instead of reaching into the PEVS globals (window.PRODUCTS …):
      products:        PRODUCTS_T,                 // active banco product list
      productsTotal:   allProducts.length,
      allProductTS:    PRODUCT_TS_T,               // full (unfiltered) per-product series
      // The banco's ALL-TIME UF universe (distinct UFs across every covered year),
      // not just the latest year's — so the "UFs cobertas" denominator never under-
      // counts on a sparse trade year. Falls back to the latest-year UF list when
      // ufYearly is absent. [] when the banco has no geography.
      ufDataFull:      ufUniverse,
      qualityByProduct: snap.qualityByProduct || [],
      qualityByUf:     snap.qualityByUf || [],
      // Honest flag for the geo views: true when a product basket is active but
      // the per-UF/region/heatmap totals are NOT narrowed by it (no per-product ×
      // UF grain in the snapshot). The views render a pt-BR note instead of
      // silently showing all-products territorial figures under a basket chip.
      notFilteredByBasket,
      // True while VALOR TOTAL/YoY/série cannot honour basket × UF simultaneously
      // (the product×UF cube is still loading) — the view shows a loading state
      // instead of a basket-dropped value. See geoComboPending above.
      geoComboPending,
      // The FULL (UF × year) grid — every year, not just ufLatestYear — already
      // scoped by basket + state + sub-UF narrowing exactly like `ufData` above (it
      // IS `ufData`'s own source, pre-slice). CONF-1: the Geografia heatmap used to
      // read the snapshot's always-all-products `ufYearly` directly instead of this,
      // so a basket that had already narrowed the map/ranking (once its cube loaded)
      // left the heatmap silently showing every product's total — a 3.4x divergence
      // measured for a single-product PEVS basket, with no on-screen warning once
      // `notFilteredByBasket` had cleared. Rows may omit `name`/`region` (the
      // município rollup doesn't carry them); resolve labels from the UF registry.
      ufYearlySeries: ufYearly,
      // The RAW basket-scoped (município × year) cube — every year, every município
      // that cleared the active sub-UF facets — for a município-scope temporal view.
      // [] both when no sub-UF narrowing is active and while the fetch is pending;
      // `subUfActive`/`subUfLoaded` distinguish "not narrowed" from "narrowed, still
      // loading" so the view can render the right empty/loading state instead of
      // guessing from an empty array alone.
      muniYearlySeries: (subUfLoaded && Array.isArray(muniCube)) ? muniCube : [],
      subUfActive, subUfLoaded,
      // The active sub-UF recorte, named. Every UF row above carries a FRACTION of its
      // state when this is set — the state's own value never appears — so a surface that
      // prints a UF name beside a number has to say so where the number is. The chip and
      // the citation state it for the panel; a map popup and a card need it locally, or
      // the reader takes "Pará · R$ 655 mi" for the Pará. Null when nothing narrows.
      recorte: (subUfActive && window.subUfChipText)
        ? window.subUfChipText(summary, mesh || [])
        : null,
      // The município code set the active sub-UF/município facets resolve to (null when
      // no facet narrows). Exported because a view that lets the researcher FOCUS on one
      // território has to offer only territories the filter actually allows — otherwise
      // it profiles a place the filter excluded, which is the no-invisible-filtering
      // violation in its purest form.
      scopedCityCodes: narrowedCities,
      _shares: { productShare, valueShare, flagShare, yearShare, stateShare },
    };
  };
})();
