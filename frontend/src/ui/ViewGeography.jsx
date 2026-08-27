// ViewGeography — territorial distribution of production, value and volume.
// All scales come from the global metric conventions (props.conventions).

const { useState: useGeoState, useMemo: useGeoMemo, useEffect: useGeoEffect } = React;

// A row counts as a real Brazilian UF when the backend's own `real` flag says so;
// falls back to the canonical 27-UF registry for a row that predates the flag.
// Mirrors the SAME guard ViewOverview/ViewConcentration already apply — without
// it a trade banco's non-state pseudo-origin (ND/EX/ZN…) inflates the map's shared
// scale, the Top-N ranking and the heatmap's max, and shows up nowhere on the
// choropleth (no matching polygon) or the "Soma por região" card (no region) —
// so it silently distorted the OTHER cards while being invisible on its own.
function isRealUfRow(u) {
  return u.real != null ? u.real : (window.isCanonicalUf ? window.isCanonicalUf(u.uf) : true);
}
// uf → região / uf → nome from the static tile registry — used to label/group
// rows from a source that doesn't carry them itself (the sub-UF município
// rollup's (uf, year) rows have neither; see dataFilters.js rollupMuniCubeToUf).
function ufRegionMap() {
  const idx = {};
  (window.UF_DATA || []).forEach((u) => { idx[u.uf] = u.region; });
  return idx;
}
function ufNameMap() {
  const idx = {};
  (window.UF_DATA || []).forEach((u) => { idx[u.uf] = u.name; });
  return idx;
}
const pl = (n, singular, plural) => (n === 1 ? singular : plural);

// Rank a raw (município × ano) cube at its latest in-window year into the SAME
// shape dataFilters.js's own topMunis produces. Used ONLY by the single-UF
// fallback below — a view-local supplement, not a change to the shared cascade
// (see the comment at singleUf/localMuniCube for why it stays local).
function rankMunisFromCube(cube, mesh, yearStart, yearEnd) {
  if (!Array.isArray(cube) || !cube.length) return [];
  const nameByCode = {};
  (mesh || []).forEach((m) => { nameByCode[m.cityCode] = m.cityName; });
  const years = cube.map((r) => r.year).filter((y) => y >= yearStart && y <= yearEnd);
  if (!years.length) return [];
  const latest = Math.max(...years);
  return cube
    .filter((r) => r.year === latest)
    .map((r) => ({
      // cityCode is what the municipal choropleth joins on (IBGE's `codarea`);
      // `city` stays the display name.
      cityCode: r.cityCode,
      city: nameByCode[r.cityCode] || r.cityCode, uf: r.uf, product: '',
      value: r.value, q_mass: r.q_mass, q_vol: r.q_vol, q_count: r.q_count,
    }))
    .sort((a, b) => (b.value || 0) - (a.value || 0));
}
// How many municípios the RANKING lists. Display-only: the map always draws every
// município that has a row, or the ones past the cut would read as "sem produção".
const MUNI_LIST_CAP = 100;
// Per-value compact magnitude (e.g. 113_008_308 → "113,0 mi") — the SAME rule the
// choropleth popup and tile map already apply per-cell, reused here so the
// município ranking stops showing raw, unscaled figures ("113.008.308,7 R$")
// while every other geo card shows a compact one ("PA · 2,9 bi").
function fmtCompact(v) {
  if (window.autoScaleNum && Math.abs(v) >= 1000) {
    const mp = window.autoScaleNum(v);
    const scaled = v / mp.factor;
    const txt = scaled.toLocaleString('pt-BR', { maximumFractionDigits: Math.abs(scaled) < 10 ? 1 : 0 });
    return mp.suffix ? `${txt} ${mp.suffix}` : txt;
  }
  return (v || 0).toLocaleString('pt-BR', { maximumFractionDigits: 0 });
}

function ViewGeography({ families, conventions, summary, database }) {
  const conv     = conventions || window.DEFAULT_CONVENTIONS;
  // UF_DATA.value is in the banco's OWN base currency (mi) internally — scale by
  // 1e6 to absolute, then convert base→display through the base-aware factor.
  // For a USD-native banco (COMEX/Comtrade) the plain convFactor would leave a
  // US$ magnitude under R$ once the display switches to BRL; base=BRL (PEVS/
  // SEFAZ) routes through convFactor verbatim, so that path is unchanged.
  // UF_DATA.q_mass is in mil t internally; UF_DATA.q_vol is in mi m³.
  const baseCcy  = window.canonCurrencyFor ? window.canonCurrencyFor(database) : 'BRL';
  const valueMul = window.convFactorFor(baseCcy, conv) * 1e6;  // mi → absolute, base-aware
  const massMul  = window.massQtyMul(conv);   // 1e3 (t) or 1e6 (kg)
  const volMul   = window.volumeQtyMul(conv); // 1e6 (m³) or 1e9 (L)
  const countMul = window.countQtyMul(conv);  // 1e6 — internal mi un → cabeças/un
  const valueUnitLabel = window.valueAxisLabel(conv); // "R$" / "US$" / etc.
  const massUnitLabel  = window.massAxisLabel(conv);  // "t" or "kg"
  const volUnitLabel   = window.volumeAxisLabel(conv);// "m³" or "L"
  const countUnitLabel = window.countAxisLabel(conv); // "un" / "cab" / …

  const filtered = window.applyFilters(summary || {}, database);
  // The per-UF maps/bars are scoped to the latest UF year IN the window, which can
  // fall short of yearEnd (future/partial endDate). Label them with the data's OWN
  // year so the caption never diverges from what's plotted (FINDING #1).
  const mapYear     = filtered.ufLatestYear != null ? filtered.ufLatestYear : filtered.yearEnd;
  // "(parcial)" when the UF data lags the window end (ufYearPartial) OR the map year
  // is the calendar-incomplete latest year (a monthly banco's current year — the same
  // FINDING #3 signal the Overview uses), so the map is as honest as the time series.
  const geoLatest   = (window.dataStore && window.dataStore.meta)
    ? (window.dataStore.meta(database) || {}).latest : null;
  const mapYearCalPartial = !!geoLatest && geoLatest.yearComplete === false &&
    (geoLatest.completeYear == null || mapYear > geoLatest.completeYear);
  const mapPartial  = filtered.ufYearPartial || mapYearCalPartial;
  const mapYearTag  = mapPartial ? `${mapYear} (parcial)` : `${mapYear}`;

  const [dim, setDim]     = useGeoState('value');
  const [scope, setScope] = useGeoState('uf');
  // The "Município" granularity is only meaningful for a banco with a município grain
  // (IBGE production). For UF-only trade bancos (COMEX/Comtrade) the button is hidden
  // so it never presents an always-empty panel. Defensive fallback: assume capable if
  // the helper is unavailable.
  const muniCapable = window.geoLevelFor ? window.geoLevelFor(database) === 'municipio' : true;
  useGeoEffect(() => {
    if (!muniCapable && scope === 'municipio') setScope('uf');
  }, [muniCapable, scope]);
  const [ufViz, setUfViz] = useGeoState('map'); // 'map' = maplibre choropleth, 'tiles' = SVG tile-grid

  const massFamily = families.includes('mass');
  const volFamily  = families.includes('volume');
  const countFamily = families.includes('count'); // PPM livestock head/eggs

  // CONF-3: exclude non-state pseudo-origins (a trade banco's ND/EX/ZN…) BEFORE
  // anything derives from ufData — the map/blocks, the shared auto-scale factor,
  // the Top-N ranking and the heatmap's UF keep-set all read `scaledUFs`, so
  // filtering once here keeps every one of them consistent with the choropleth
  // (which already drops them silently — no polygon matches) and with the
  // "Soma por região" card (which already excludes them — no region matches).
  const realUfData = useGeoMemo(
    () => (filtered.ufData || []).filter(isRealUfRow),
    [filtered],
  );

  // A quantity dimension is only offered when the per-UF rows actually CARRY it —
  // gating on the basket family alone (the old behaviour) offered a toggle that
  // rendered an all-zero map for a banco whose per-UF reader returns no quantity.
  // We require both the family AND at least one non-zero per-UF value.
  const hasUfQty = (key) => realUfData.some(u => (u[key] || 0) > 0);
  const massAvail = massFamily && hasUfQty('q_mass');
  const volAvail  = volFamily  && hasUfQty('q_vol');
  const countAvail = countFamily && hasUfQty('q_count');
  // The family is in the basket but the per-UF grain has no quantity → tell the
  // researcher honestly instead of silently dropping the toggle or showing zeros.
  const massUnavailNote = massFamily && !massAvail;
  const volUnavailNote  = volFamily  && !volAvail;
  // Value is the universal measure for a MONETARY banco, but a value-LESS stock (the
  // livestock herd) has all-zero per-UF value — gate it on a non-zero value so the herd
  // defaults to its cabeças map instead of an all-zero "Valor" map. Monetary bancos
  // always have value, so they are unaffected.
  const valueAvail = hasUfQty('value');

  // Dimensions with active unit label
  const dims = [
    { id: 'value',  label: 'Valor',               key: 'value',   unit: valueUnitLabel, mul: valueMul, available: valueAvail },
    { id: 'mass',   label: 'Quantidade (massa)',  key: 'q_mass',  unit: massUnitLabel,  mul: massMul,  available: massAvail },
    { id: 'volume', label: 'Quantidade (volume)', key: 'q_vol',   unit: volUnitLabel,   mul: volMul,   available: volAvail },
    { id: 'count',  label: 'Quantidade (cabeças)',key: 'q_count', unit: countUnitLabel, mul: countMul, available: countAvail },
  ].filter(d => d.available);
  // Never render zero dimensions (activeDim would be undefined): fall back to value.
  if (!dims.length) dims.push({ id: 'value', label: 'Valor', key: 'value', unit: valueUnitLabel, mul: valueMul, available: true });

  // If the active dimension is no longer available (e.g. the basket changed
  // from a mixed cesta to mass-only), reset to the first available one.
  // Done in an effect — never call setState during render.
  useGeoEffect(() => {
    if (!dims.find(d => d.id === dim)) setDim(dims[0].id);
  }, [dim, massAvail, volAvail, countAvail, valueAvail]);
  const activeDim = dims.find(d => d.id === dim) || dims[0];
  const valueKey  = activeDim.key;
  const unit      = activeDim.unit;
  const mul       = activeDim.mul;

  // ---- Map-click ↔ filter bridge (state selection from the map itself) ------
  // Extracted to geoSelect.js so the other territorial maps (Visão geral, Qualidade)
  // apply the identical rule instead of each re-deriving it — including the part
  // that is easy to get wrong: selecting a UF also RESETS the sub-UF/região/nação
  // facets, so a stale narrowing can't silently intersect with a click the
  // researcher made on the map.
  const selectedSingleUf = window.selectedSingleUf(summary);
  const handleUfClick = window.ufClickHandler(summary);
  const handleTileSelect = window.tileSelectHandler(summary);

  // EST-5: município scope shouldn't require first drilling into a mesorregião to
  // be useful. When exactly one UF is selected and dataFilters' OWN sub-UF cascade
  // isn't already narrowing (filtered.subUfActive), fetch that UF's município
  // ranking directly here — a view-LOCAL supplement, same pattern as productsByUf
  // below. An earlier version tried this inside applyFilters itself (extending the
  // shared cascade to trigger on a single selected state); it worked for Geografia
  // but also put every OTHER perspective into a loading state whenever a single UF
  // was selected and the IBGE mesh hadn't warmed yet (a dataFilters.cov.test.js
  // regression caught it). Kept local, it can only ever affect this view.
  const wantMuniFallback = scope === 'municipio' && !!selectedSingleUf && !filtered.subUfActive;
  // The mesh is needed for the FALLBACK's city set AND, in both município paths, to
  // resolve cityCode→name for the map popup and the heatmap's row labels. Gating it
  // on wantMuniFallback alone left the sub-UF path (an explicit meso/município facet)
  // without names, so those rows read as bare 7-digit codes. It is a cached, shared
  // resource — asking for it whenever the município scope is open costs nothing.
  const mesh = (scope === 'municipio' && window.geoMesh) ? window.geoMesh() : null;
  const ufCityCodes = useGeoMemo(
    () => (mesh ? mesh.filter((m) => m.uf === selectedSingleUf).map((m) => m.cityCode) : null),
    [mesh, selectedSingleUf],
  );
  // Scoped to the researcher's OWN period window rather than the full 1986→ history:
  // the cube feeds the map (one year) and the heatmap (which already discards years
  // outside the window), so anything beyond it is fetched and thrown away. Worst case
  // measured unbounded — MG, 853 municípios — is 21.468 rows / 2,3 MB / 4,5 s.
  const localMuniCube = (wantMuniFallback && ufCityCodes && ufCityCodes.length && window.municipioYearly)
    ? window.municipioYearly(database, summary, ufCityCodes, [filtered.yearStart, filtered.yearEnd])
    : null; // null = pending fetch (or not wanted); [] = loaded-empty; [...] = rows
  const localMuniLoading = wantMuniFallback && !!(ufCityCodes && ufCityCodes.length) && localMuniCube == null;
  const localMuniRows = useGeoMemo(
    () => rankMunisFromCube(localMuniCube, mesh, filtered.yearStart, filtered.yearEnd),
    [localMuniCube, mesh, filtered.yearStart, filtered.yearEnd],
  );
  // dataFilters' own sub-UF cube (an explicit meso/micro/… facet) always wins when
  // it has rows; the single-UF fallback only fills in when that path is empty.
  const activeMuniRows = filtered.topMunis.length ? filtered.topMunis : localMuniRows;

  // ---- Municipal choropleth (EST-4: the sub-UF filter finally reaches the map) ---
  // The vendored geometry is ONE FILE PER UF, so the map can only draw when the
  // active selection resolves to a single state — either because one UF is selected,
  // or because every município that survived the sub-UF facets happens to sit in one
  // (the common case: a mesorregião belongs to exactly one UF). Anything broader
  // (two UFs' mesorregiões, or no geographic narrowing at all) keeps the ranking,
  // which is correct at any breadth. Loading the whole-country mesh instead would be
  // ~836 KB gzipped for 5570 polygons that are 2-3px smudges at that zoom.
  const muniMapUf = useGeoMemo(() => {
    if (selectedSingleUf) return selectedSingleUf;
    const ufs = new Set(activeMuniRows.map((m) => m.uf).filter(Boolean));
    return ufs.size === 1 ? [...ufs][0] : null;
  }, [selectedSingleUf, activeMuniRows]);
  const [muniViz, setMuniViz] = useGeoState('map'); // 'map' = choropleth municipal, 'list' = ranking
  // Clicking a município narrows the filter to it, the same bridge the UF map uses.
  // Clicking the selected one again clears just the município facet (the UF/sub-UF
  // narrowing that got us here stays — the researcher didn't ask to leave it).
  const selectedSingleCity = Array.isArray(summary && summary.munis) && summary.munis.length === 1
    ? summary.munis[0] : null;
  const handleCityClick = (code) => {
    if (!code || !window.patchFilter) return;
    window.patchFilter({ munis: selectedSingleCity === code ? null : [code] });
  };
  // What the "Ver raio-x" shortcut would open, named so the button is a promise rather
  // than a leap. Empty when nothing is narrowed: the profile then opens on its own
  // default and the button should not claim otherwise.
  const xrayScope = selectedSingleCity
    ? ((mesh || []).find((m) => String(m.cityCode) === String(selectedSingleCity)) || {}).cityName
      || null
    : (selectedSingleUf || null);
  const muniVizToggle = (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
      <div className="seg" role="group" aria-label="Visualização por município">
        <button className={'seg-opt ' + (muniViz === 'map' ? 'on' : '')} aria-pressed={muniViz === 'map'} onClick={() => setMuniViz('map')}>Mapa</button>
        <button className={'seg-opt ' + (muniViz === 'list' ? 'on' : '')} aria-pressed={muniViz === 'list'} onClick={() => setMuniViz('list')}>Ranking</button>
      </div>
    </div>
  );

  // CONF-4: "Exportar CSV" lives in the topbar (main.jsx), built from
  // {view, database, summary, conventions} — it has no way to see this view's OWN
  // local scope/município-fallback state (React state that never leaves this
  // component). Mirroring both here, the same bridge pattern as patchFilter, lets
  // csvExport.js's 'geo' case export whatever granularity is ACTUALLY on screen
  // instead of always the per-UF table regardless of the Granularidade control.
  useGeoEffect(() => {
    window.geoExportScope = scope;
    window.geoExportMunis = activeMuniRows;
    return () => { delete window.geoExportScope; delete window.geoExportMunis; };
  }, [scope, activeMuniRows]);

  // Scale geo datasets according to active dimension's multiplier
  const scaledUFs = useGeoMemo(
    () => realUfData.map(u => ({ ...u, [valueKey]: u[valueKey] * mul })),
    [valueKey, mul, realUfData]
  );
  const scaledRegions = useGeoMemo(
    () => filtered.regionData.map(r => ({ ...r, [valueKey]: r[valueKey] * mul })),
    [valueKey, mul, filtered]
  );
  const scaledMunis = useGeoMemo(
    () => activeMuniRows.map(m => ({ ...m, [valueKey]: (m[valueKey] || 0) * mul })),
    [valueKey, mul, activeMuniRows]
  );

  // Heatmap: ano × (UF | região | município), matching the active Granularidade —
  // EST-1: this used to always aggregate by UF regardless of scope, so choosing
  // "Região" changed the map above but left "the same year-value" repeated a THIRD
  // time here at the wrong grain. Every branch reads REAL per-(…, year) Gold
  // history — never a basket-rescaled fabrication (see the F1.5 note this file
  // used to carry): a basket only narrows once its (grain × year) cube has
  // actually loaded (filtered.ufYearlySeries / muniYearlySeries already encode
  // that — see dataFilters.js), so there is nothing left to re-derive here.
  //
  // CONF-1: the UF branch used to read `dataStore.get(database).ufYearly` directly
  // — ALWAYS all-products — instead of `filtered.ufYearlySeries`, the basket-aware
  // grid the map/ranking above already use once their cube loads. A one-product
  // PEVS basket measured a 3.4× divergence between the map (correct) and this
  // heatmap (silently wrong) with no on-screen warning once the basket note had
  // cleared. Reading the SAME source the map reads makes the two agree by
  // construction — there is only one (UF × year) grid in this view now.
  const heatRows = useGeoMemo(() => {
    const yearStart = filtered.yearStart, yearEnd = filtered.yearEnd;

    if (scope === 'uf') {
      const yearly = Array.isArray(filtered.ufYearlySeries) ? filtered.ufYearlySeries : [];
      if (!yearly.length) return [];
      const keepUf = new Set(scaledUFs.map(u => u.uf)); // real-UF + state-filtered already
      const order = scaledUFs.slice().sort((a, b) => b[valueKey] - a[valueKey]).slice(0, 12).map(u => u.uf);
      const names = ufNameMap();
      const byUf = {};
      yearly.forEach(r => {
        if (!keepUf.has(r.uf)) return;
        if (r.year < yearStart || r.year > yearEnd) return;
        const row = byUf[r.uf] || (byUf[r.uf] = { values: [] });
        row.values.push({ y: r.year, v: (r[valueKey] || 0) * mul });
      });
      return order.filter(uf => byUf[uf]).map(uf => ({
        id: uf,
        label: `${uf} · ${names[uf] || byUf[uf].name || uf}`,
        values: byUf[uf].values.slice().sort((a, b) => a.y - b.y),
      }));
    }

    // Ranked by each row's value AT THE reference year (filtered.ufLatestYear) —
    // the SAME year (and thus the SAME ranking) the "Distribuição" card and its
    // list/map above use, matching the 'uf' branch's own convention (which ranks
    // scaledUFs the same way). Ranking by the all-years SUM instead would silently
    // disagree with "top" everywhere else on this screen means (a município that
    // led every year until fading in mapYear would out-rank this year's actual
    // leader here, while the card above shows the opposite order).
    const latestYear = filtered.ufLatestYear;

    if (scope === 'region') {
      const yearly = Array.isArray(filtered.ufYearlySeries) ? filtered.ufYearlySeries : [];
      if (!yearly.length) return [];
      const keepUf = new Set(scaledUFs.map(u => u.uf));
      const regionOf = ufRegionMap();
      const regionLabel = {};
      (window.REGIONS || []).forEach(r => { regionLabel[r.id] = r.label || r.id; });
      const byRegion = {};
      yearly.forEach(r => {
        if (!keepUf.has(r.uf)) return;
        if (r.year < yearStart || r.year > yearEnd) return;
        const reg = regionOf[r.uf];
        if (!reg) return;
        const row = byRegion[reg] || (byRegion[reg] = { values: new Map() });
        row.values.set(r.year, (row.values.get(r.year) || 0) + (r[valueKey] || 0) * mul);
      });
      return Object.keys(byRegion).map(id => {
        const values = [...byRegion[id].values.entries()].map(([y, v]) => ({ y, v })).sort((a, b) => a.y - b.y);
        return { id, label: regionLabel[id] || id, rankValue: byRegion[id].values.get(latestYear) || 0, values };
      }).sort((a, b) => b.rankValue - a.rankValue);
    }

    // scope === 'municipio' — either dataFilters' own sub-UF cube (an explicit
    // facet) or the single-UF fallback above; never the plain UF grid (that would
    // be the exact "same vector at the wrong grain" problem this fix removes).
    const cube = (filtered.subUfActive && filtered.subUfLoaded && filtered.muniYearlySeries.length)
      ? filtered.muniYearlySeries
      : localMuniCube;
    if (!Array.isArray(cube) || !cube.length) return [];
    const names = {};
    (mesh || []).forEach(m => { names[m.cityCode] = m.cityName; });
    const byCity = {};
    cube.forEach(r => {
      if (r.year < yearStart || r.year > yearEnd) return;
      const row = byCity[r.cityCode] || (byCity[r.cityCode] = { values: new Map(), uf: r.uf });
      row.values.set(r.year, (row.values.get(r.year) || 0) + (r[valueKey] || 0) * mul);
    });
    return Object.keys(byCity).map(code => {
      const values = [...byCity[code].values.entries()].map(([y, v]) => ({ y, v })).sort((a, b) => a.y - b.y);
      return {
        id: code, label: `${names[code] || code} · ${byCity[code].uf}`,
        rankValue: byCity[code].values.get(latestYear) || 0, values,
      };
    }).sort((a, b) => b.rankValue - a.rankValue).slice(0, 12);
  }, [scope, valueKey, mul, scaledUFs, filtered, mesh, localMuniCube]);

  const top10ufs = scaledUFs.slice().sort((a, b) => b[valueKey] - a[valueKey]).slice(0, 10);

  // ---- Auto-scale all geo datasets to a shared factor (when ON) -----
  const sharedMax = Math.max(...scaledUFs.map(u => u[valueKey] || 0));
  const ufScaled    = window.scaleSeries(scaledUFs,    sharedMax, conv, valueKey, unit);
  const regScaled   = window.scaleSeries(scaledRegions, Math.max(...scaledRegions.map(r => r[valueKey] || 0)), conv, valueKey, unit);
  const top10Scaled = window.scaleSeries(top10ufs,     sharedMax, conv, valueKey, unit);
  const heatMax     = Math.max(...heatRows.flatMap(r => r.values.map(v => v.v)));
  const heatScaled  = (() => {
    if (!conv.autoScale) return { rows: heatRows, label: unit };
    const { factor, suffix } = window.autoScaleNum(heatMax);
    if (!suffix) return { rows: heatRows, label: unit };
    const label = window.scaleLabel(unit, suffix);  // shared grammar (DEDUP-9)
    return {
      rows: heatRows.map(r => ({
        ...r,
        values: r.values.map(v => ({ ...v, v: v.v / factor })),
      })),
      label,
    };
  })();
  const displayUnit = ufScaled.label;

  // EST-1/MAPA-4: the top card + heatmap titles follow the SAME grain as the
  // Granularidade control, instead of the fixed "UF"/"mapa de calor" wording that
  // used to sit above a region-bars chart or a município list unchanged.
  const scopeNoun = scope === 'region' ? 'região' : scope === 'municipio' ? 'município' : 'UF';
  const distTitle =
    scope === 'region' ? 'Distribuição por região' :
    scope === 'uf'     ? 'Distribuição por UF' :
                         'Distribuição por município';
  const distKind = scope === 'uf' ? 'Mapa' : 'Distribuição';
  const heatCountTag =
    heatScaled.rows.length === 0 ? '' :
    heatScaled.rows.length === 1 ? `(1 ${scopeNoun})` :
    scope === 'region' ? `(${heatScaled.rows.length} ${pl(heatScaled.rows.length, 'região', 'regiões')})` :
    `(${heatScaled.rows.length} maiores)`;
  // EST-2: a ranking card duplicating the grain the top card ALREADY shows (region
  // bars again for scope=região; the município list again for scope=município) used
  // to render unconditionally — the SAME chart, same data, twice on one screen for
  // região. Show the UF ranking only in UF scope; "Soma por região" stays useful in
  // every OTHER scope (a different grain: national region totals vs. the active
  // UF/município narrowing), so it's suppressed ONLY when scope IS região itself.
  const showRankingCard = scope === 'uf';
  const showRegionSumCard = scope !== 'region';
  const ufRankTitle = `${pl(top10ufs.length, 'Estado produtor', 'Maiores estados produtores')} · ${mapYearTag}`;

  return (
    <>
      <window.UnitFamilyBanner families={families} />

      {filtered.notFilteredByBasket && (
        <div className="card subtle" style={{ marginBottom: 12 }}>
          <p className="caption" style={{ padding: '10px 12px' }}>
            A distribuição territorial reflete <strong>todos os produtos</strong> do banco —
            a cesta selecionada não recorta o mapa por UF/região (não há grão produto × UF nesta
            agregação). Para a distribuição de um produto específico, use a perspectiva
            <strong> Perfil do produto</strong>.
          </p>
        </div>
      )}
      {(massUnavailNote || volUnavailNote) && (
        <div className="card subtle" style={{ marginBottom: 12 }}>
          <p className="caption" style={{ padding: '10px 12px' }}>
            {massUnavailNote && volUnavailNote
              ? 'As quantidades por UF (massa e volume) ainda não estão disponíveis nesta fonte — apenas o valor é exibido no mapa.'
              : massUnavailNote
                ? 'A quantidade por UF (massa) ainda não está disponível nesta fonte — apenas o valor é exibido no mapa.'
                : 'A quantidade por UF (volume) ainda não está disponível nesta fonte — apenas o valor é exibido no mapa.'}
          </p>
        </div>
      )}
      {activeDim.id === 'count' && (
        <div className="card subtle" style={{ marginBottom: 12 }}>
          <p className="caption" style={{ padding: '10px 12px' }}>
            O mapa de <strong>cabeças</strong> soma os produtos de contagem selecionados; cabeças
            <strong> não são comparáveis entre espécies</strong>. Filtre por uma única espécie para um
            mapa limpo, ou use a perspectiva <strong>Rebanho</strong> (mapa por espécie).
          </p>
        </div>
      )}

      <div className="geo-controls">
        <div className="geo-control-grp">
          <span className="overline">Métrica</span>
          <div className="seg" role="group" aria-label="Métrica">
            {dims.map(d => (
              <button key={d.id}
                      className={'seg-opt ' + (dim === d.id ? 'on' : '')}
                      aria-pressed={dim === d.id}
                      onClick={() => setDim(d.id)}>
                {d.label}
              </button>
            ))}
          </div>
        </div>
        <div className="geo-control-grp">
          <span className="overline">Granularidade</span>
          <div className="seg" role="group" aria-label="Granularidade">
            <button className={'seg-opt ' + (scope === 'region' ? 'on' : '')} aria-pressed={scope === 'region'} onClick={() => setScope('region')}>Região</button>
            <button className={'seg-opt ' + (scope === 'uf' ? 'on' : '')} aria-pressed={scope === 'uf'} onClick={() => setScope('uf')}>UF</button>
            {muniCapable && (
              <button className={'seg-opt ' + (scope === 'municipio' ? 'on' : '')} aria-pressed={scope === 'municipio'} onClick={() => setScope('municipio')}>Município</button>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <window.SectionHeader
          overline={`${distKind} · ${activeDim.label} · ${displayUnit} · ${mapYearTag}`}
          title={distTitle}
          // Geografia and Perfil do território are two halves of one question: this view
          // shows how the activity spreads ACROSS places, that one what happens INSIDE a
          // place. The shortcut makes the pair discoverable without touching the map's
          // click, which stays a cheap reversible filter toggle. It carries no place of
          // its own — the profile reads the SAME geography filter this view writes, so
          // whatever is selected here is what opens there.
          action={window.goToView ? (
            <button
              className="seg-opt"
              onClick={() => window.goToView('territory_profile')}
              title={xrayScope
                ? `Abrir o perfil de ${xrayScope} em Perfil do território`
                : 'Abrir Perfil do território'}
            >
              Ver raio-x{xrayScope ? ` de ${xrayScope}` : ''}
            </button>
          ) : null}
        />
        {scope === 'region' && <window.RegionBars data={regScaled.data} valueKey={valueKey} label={regScaled.label} height={280} />}
        {scope === 'uf' && (
          <>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
              <div className="seg" role="group" aria-label="Visualização do mapa">
                <button className={'seg-opt ' + (ufViz === 'map' ? 'on' : '')} aria-pressed={ufViz === 'map'} onClick={() => setUfViz('map')}>Mapa</button>
                <button className={'seg-opt ' + (ufViz === 'tiles' ? 'on' : '')} aria-pressed={ufViz === 'tiles'} onClick={() => setUfViz('tiles')}>Blocos</button>
              </div>
            </div>
            {/* The UF maps get the RAW (unscaled) per-UF values + just the currency symbol:
                each cell/popup is formatted with its OWN compact magnitude (e.g. "2,9 bi",
                "384 mi", "3,0 mi"), so small UFs never round to "0" (the global-factor
                auto-scale problem) and big ones never overflow the cell. Clicking a UF
                filters the whole dashboard to it (click again to clear). */}
            {ufViz === 'map'
              ? <window.BrazilChoropleth data={scaledUFs} valueKey={valueKey} label={valueUnitLabel} onSelect={handleUfClick} selectedUf={selectedSingleUf} />
              : <window.BrazilTileMap data={scaledUFs} valueKey={valueKey} label={valueUnitLabel} onSelect={handleTileSelect} selectedUf={selectedSingleUf} />}
            {filtered.ufYearPartial && (
              <p className="caption" style={{ padding: '8px 4px 0' }}>
                <strong>{mapYear} (parcial):</strong> o último ano com dados por UF disponíveis fica
                antes do fim do período selecionado ({filtered.yearEnd}). O mapa mostra {mapYear},
                o ano mais recente com cobertura territorial.
              </p>
            )}
          </>
        )}
        {scope === 'municipio' && (() => {
          const rows = scaledMunis
            .filter(m => valueKey === 'value' || (m[valueKey] != null && m[valueKey] > 0));
          if (!rows.length) {
            if (localMuniLoading) {
              return (
                <p className="caption" style={{ padding: '12px' }}>
                  Carregando municípios de <strong>{selectedSingleUf}</strong>…
                </p>
              );
            }
            return (
              <div className="geo-empty-cta">
                <p className="caption">
                  A lista por município aparece ao <strong>recortar a geografia</strong> — selecione
                  uma UF, uma mesorregião/microrregião, região intermediária/imediata ou municípios
                  específicos no filtro.
                </p>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => window.openFilterMenu && window.openFilterMenu()}
                >
                  Abrir filtro de geografia
                </button>
              </div>
            );
          }
          const max = Math.max(...rows.map(x => x[valueKey] || 0)) || 1;
          const listRows = rows.slice(0, MUNI_LIST_CAP);
          const list = (
            <div className="muni-list">
              {listRows.map((m, i) => {
                const v = m[valueKey] || 0;
                return (
                  <div key={(m.cityCode || m.city) + m.uf} className="muni-row">
                    <span className="muni-rank tnum">#{i + 1}</span>
                    <span className="muni-name">{m.city}</span>
                    <span className="muni-uf">{m.uf}</span>
                    <div className="muni-bar"><div style={{ width: ((v / max) * 100).toFixed(1) + '%', background: 'var(--viz-2)' }}></div></div>
                    <span className="muni-val tnum">{fmtCompact(v)}</span>
                  </div>
                );
              })}
            </div>
          );
          // The municipal choropleth is a per-UF asset, so it can only draw when the
          // selection resolves to exactly ONE state (a meso filter spanning two UFs,
          // or no UF at all, has no single mesh to load). Falls back to the ranking,
          // which is grain-correct either way.
          if (muniMapUf && muniViz === 'map') {
            return (
              <>
                {muniVizToggle}
                <window.MunicipioChoropleth
                  uf={muniMapUf}
                  data={rows}
                  valueKey={valueKey}
                  label={valueUnitLabel}
                  selectedCity={selectedSingleCity}
                  onSelect={handleCityClick}
                  // With a sub-UF/município facet active the un-shaded municípios are
                  // OUTSIDE the selection, not municípios without production.
                  narrowed={filtered.subUfActive}
                />
              </>
            );
          }
          return muniMapUf ? <>{muniVizToggle}{list}</> : list;
        })()}
      </div>

      <div className="card">
        <window.SectionHeader
          overline={`Evolução temporal · ${activeDim.label} (${heatScaled.label})`}
          title={`Mapa de calor · ano × ${scopeNoun} ${heatCountTag}`.trim()}
        />
        {heatScaled.rows.length
          ? <window.Heatmap rows={heatScaled.rows} valueKey="v" valueLabel={heatScaled.label} />
          : (
            <p className="caption" style={{ padding: '12px' }}>
              {scope === 'municipio' && !localMuniLoading
                ? <>A evolução por município aparece ao <strong>recortar a geografia</strong> — selecione
                    uma UF ou um recorte sub-UF no filtro.</>
                : scope === 'municipio' && localMuniLoading
                  ? <>Carregando o histórico de <strong>{selectedSingleUf}</strong>…</>
                  : 'Sem histórico anual disponível para o recorte atual.'}
            </p>
          )}
      </div>

      {(showRankingCard || showRegionSumCard) && (
        <div className="grid-2">
          {showRankingCard && (
            <div className="card">
              <window.SectionHeader
                overline={`Top 10 · ${activeDim.label}`}
                title={ufRankTitle}
                action={<span className="caption">{activeDim.label} ({top10Scaled.label})</span>}
              />
              <window.BarChart data={top10Scaled.data} valueKey={valueKey} color="var(--viz-2)" height={320} />
            </div>
          )}
          {showRegionSumCard && (
            <div className="card">
              <window.SectionHeader
                overline={`${activeDim.label} · ${mapYearTag}`}
                title="Soma por região"
                action={<span className="caption">{regScaled.data.length} {pl(regScaled.data.length, 'macrorregião', 'macrorregiões')} · {regScaled.label}</span>}
              />
              <window.RegionBars data={regScaled.data} valueKey={valueKey} label={regScaled.label} height={320} />
            </div>
          )}
        </div>
      )}

      {/* Base de dados — products ranked WITHIN the selected UF(s), for the SAME
          data-year the rest of this view shows (CONF-2: this card used to sum the
          ENTIRE 1986–2024 window regardless of what year the map/ranking above were
          showing — "PA · 2024 → R$ 2,9 bi" next to "Madeira em tora → R$ 136 bi" on
          the same screen). The inverse of "onde X é produzido": here a state is
          fixed and the products are ranked. Only shown when a UF is selected (the
          per-(product × UF) grain the rest of this view lacks comes from the
          dedicated /api/products-by-uf reader). */}
      {summary && Array.isArray(summary.states) && summary.states.length > 0 && (() => {
        const pbuSummary = { ...summary, startDate: `${mapYear}-01-01`, endDate: `${mapYear}-12-01` };
        const pbu = window.productsByUf(database, pbuSummary, conv);
        const rows = (pbu.products || [])
          .map(p => ({ ...p, [valueKey]: (p[valueKey] || 0) * mul }))
          .filter(r => (r[valueKey] || 0) > 0)
          .sort((a, b) => b[valueKey] - a[valueKey])
          .slice(0, 20);
        // A failed /api/products-by-uf fetch leaves products:[] → rows empty; surface the error
        // instead of silently rendering nothing (would read as "este estado não tem produtos").
        if (!rows.length) return pbu.loadError ? <window.LoadErrorNote error={pbu.loadError} /> : null;
        const scaled = window.scaleSeries(rows, Math.max(...rows.map(r => r[valueKey] || 0)), conv, valueKey, unit);
        const estadoLabel = pl(summary.states.length, 'Produtos do estado', 'Produtos dos estados');
        return (
          <div className="card">
            <window.SectionHeader
              overline={`Base de dados · ${activeDim.label} · ${scaled.label} · ${mapYearTag}`}
              title={`${estadoLabel} (${summary.states.join(', ')})`}
              action={<span className="caption">{rows.length} produtos · ranking por {activeDim.label.toLowerCase()}</span>}
            />
            <window.BarChart data={scaled.data} valueKey={valueKey} color="var(--viz-2)" height={Math.max(240, rows.length * 26)} />
          </div>
        );
      })()}
    </>
  );
}

window.ViewGeography = ViewGeography;
