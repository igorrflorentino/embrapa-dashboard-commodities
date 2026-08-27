// producers.js — API-backed replacements for the prototype's synthetic data
// producers, keeping identical window.* names/signatures. The per-banco snapshot
// path lives in dataStore.js (gated by DataBoundary); this file covers the
// cross-source / analytics / curation producers + the data-blocked placeholders.
//
// Sync-over-async (contract map §3.1): the cross producers are SYNC for the
// reused views — they read the resource cache (get) and, if cold, kick off the
// fetch (ensure) + return a safe pending placeholder. A CrossBoundary (main.jsx)
// subscribes to resource changes and re-renders, so the view's next sync call
// gets real data. Trade adapters (flow/partner/monthly) have no endpoint yet;
// chain/lag are data-blocked — those return honest preview shells. (market-nature is
// edit-driven + real via the "Tipo de Mercado" matrix, see window.marketNatureAnalysis below.)

import { decorateUfRows } from './decorate';
import { ensure, errorOf, get } from './resource';

const API = '/api';
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v != null)).toString();

// ── active-filter → query-param plumbing (contract map §1, "filter params") ────
// The reused views pass the FilterMenu summary as the producers' last arg. These
// helpers turn it into the SUBSET of params each producer's grain can honour:
//   • basket    → `codes` (comma-joined product codes; absent = all)
//   • startDate / endDate → `y0` / `y1` (year window; absent = full coverage)
// A filter the producer's grain CANNOT apply (e.g. the FilterMenu product basket
// on ViewProductivity, whose crop is chosen by the view's own selector) is never
// silently dropped — the producer surfaces it via `notApplicable` so the view can
// render an honest pt-BR note (mirrors the contract's `incompatible`/`preview`).
const filterCodes = (summary) => {
  const b = summary && summary.basket;
  // null/undefined = "no product filter" (all); [] = "none selected". Join the
  // codes so the cache key + URL change with the selection; '' means all.
  return b == null ? undefined : b.join(',');
};
// Origin-UF (state) selection → the `states` param the COMEX trade readers honour.
// Same null-vs-empty rule as the basket: null/undefined = "no UF filter" (all);
// [] = "none selected" (sends `states=`, distinct from absent). The seam binds
// these as an IN UNNEST predicate on state_acronym (COMEX origin only).
const filterStates = (summary) => {
  const s = summary && summary.states;
  return s == null ? undefined : s.join(',');
};
const filterYear = (iso) => {
  if (!iso) return undefined;
  const y = parseInt(String(iso).slice(0, 4), 10);
  return Number.isFinite(y) ? y : undefined;
};
// Cache-key signature for a filtered producer: identical filters → identical key
// (cache hit); a changed window/basket/states → a NEW key so the gate refetches the
// scoped data instead of serving the first-loaded (unfiltered) snapshot forever.
const filterSig = (summary) => {
  const codes = filterCodes(summary) ?? '*';
  const states = filterStates(summary) ?? '*';
  const y0 = filterYear(summary && summary.startDate) ?? '';
  const y1 = filterYear(summary && summary.endDate) ?? '';
  return `${codes}|${states}|${y0}|${y1}`;
};
// COMTRADE país reporter / parceiro selection → query params + a cache-key fragment.
// reporter is 3-state: absent → undefined (Brazil default, omitted), '__all__' → world
// sentinel, list → CSV. partner: list → CSV, absent → undefined (all). Only un_comtrade
// carries these; other bancos' summaries lack them, so both resolve to undefined.
const filterReporters = (summary) => {
  const r = summary && summary.reporters;
  if (r === '__all__') return '__all__';
  return Array.isArray(r) && r.length ? r.join(',') : undefined;
};
const filterPartners = (summary) => {
  const p = summary && summary.partners;
  return Array.isArray(p) && p.length ? p.join(',') : undefined;
};
const countrySig = (summary) =>
  `${filterReporters(summary) ?? 'BR'}|${filterPartners(summary) ?? 'ALL'}`;
// True when the active summary GENUINELY narrows the UF dimension — states present
// and a proper subset of the full UF universe (window.UF_DATA), or explicitly
// cleared ([]). The all-27-selected default (every UF checked) is NOT a narrowing,
// so it does not trigger the note. Used to surface an honest "não se aplica" note
// on the grains that cannot honour a UF filter (COMTRADE's country origin; the
// UF-less seasonality mart) — never for the unfiltered default.
const ufFilterActive = (summary) => {
  const s = summary && summary.states;
  if (s == null) return false; // dimension untouched (default = all)
  const total = (window.UF_DATA || []).length;
  return s.length === 0 || (total > 0 && s.length < total);
};
// Does this banco's flow/partner ORIGIN resolve to a Brazilian UF? COMEX origin is
// a UF (state_acronym, filterable); COMTRADE origin is a reporter country (no UF).
const bancoOriginIsUf = (bancoId) =>
  !!(window.bancoDim && window.bancoDim(bancoId, 'origin').kind === 'uf');

// pt-BR month labels — defined here (the seasonality view + MonthYearHeatmap read
// window.MONTH_LABELS).
window.MONTH_LABELS = window.MONTH_LABELS || [
  'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez',
];

// ── per-banco snapshot fallback (dataStore is the primary path) ───────────────
window.snapshotFor = function snapshotFor() {
  // Every live banco loads through dataStore.load → /api/snapshot. This fallback
  // (used by applyFilters only if the store isn't populated) returns null so the
  // caller degrades gracefully rather than fabricating data.
  return null;
};

// ── basket-scoped per-(UF, year) cube (geography-aware hero / map / series) ─────
// The /api/snapshot ufYearly is all-products (the client can slice it by state and
// year but NOT by product), so a product basket can't narrow the territorial split
// or the VALOR TOTAL hero. This producer pushes the active basket down to
// /api/geo-yearly, which returns the SAME (UF × year) shape narrowed to the chosen
// products; applyFilters then sums it over the selected states + period client-side,
// making the hero, choropleth and series respect state + product + period together.
//
// Keyed by banco + convention + basket ONLY (state/year are client-side slices), so
// panning the period or toggling a UF reuses the cached cube instead of refetching.
// The convention is read from the dataStore so the cube's value column matches the
// snapshot's byte-for-byte. Returns null until loaded (applyFilters falls back to the
// all-products ufYearly) or for a banco with no geo grain (COMTRADE).
window.geoYearly = function geoYearly(bancoId, summary) {
  const b = window.bancoById && window.bancoById(bancoId);
  if (!b || !(b.provides || []).includes('geo')) return null;
  const conv = window.dataStore && window.dataStore.conv
    ? window.dataStore.conv()
    : { currency: 'BRL', correction: 'IPCA' };
  // Flow (export/import) is a SERVER-SIDE filter (the trade marts are pre-aggregated
  // over flow), so it belongs in the cube's cache key + request exactly like the
  // snapshot's — without it a COMEX basket renders all-flows VALOR TOTAL/map while
  // the rest of the app is flow-filtered. 'all'/absent → omitted (sum every flow).
  const flow = window.dataStore && window.dataStore.flow ? window.dataStore.flow() : 'all';
  const flowParam = flow && flow !== 'all' ? flow : undefined;
  const codes = filterCodes(summary); // undefined = all products; comma list otherwise
  const key = `geoYearly:${bancoId}:${conv.currency}|${conv.correction}|${flow}:${codes ?? '*'}`;
  ensure(
    key,
    () => `${API}/geo-yearly?${qs({
      banco: bancoId,
      codes,
      currency: conv.currency,
      correction: conv.correction,
      flow: flowParam,
    })}`,
  );
  const data = get(key);
  return data && Array.isArray(data.ufYearly) ? data.ufYearly : null;
};

// ── IBGE municipal mesh universe (sub-UF + município cascade) ──────────────────
// One-shot fetch of every município → UF + grande região + BOTH sub-UF divisions
// (classic meso/micro, 2017 intermediária/imediata). Banco-agnostic + static, so it
// has no convention/basket in its key — fetched once and cached. Backs the geo
// cascade's sub-UF + município option lists AND the cityCode→ancestry map that
// dataFilters uses to roll the município cube up to the selected level. Returns the
// municipios array (or null until the fetch lands).
window.geoMesh = function geoMesh() {
  const key = 'geoMesh';
  ensure(key, () => `${API}/geo-mesh`);
  const data = get(key);
  return data && Array.isArray(data.municipios) ? data.municipios : null;
};

// COMTRADE país reporter + país parceiro universes (código M49 + ISO-A3 + nome pt-BR).
// Banco-agnostic + static (one DISTINCT over the mart), so no convention/basket in its key —
// fetched once and cached, like geoMesh. Backs the two country multi-selects in the filter
// menu. Returns { reporters, partners } (arrays of {code, iso, name}) or null until it lands.
window.comtradeCountries = function comtradeCountries() {
  const key = 'comtradeCountries';
  ensure(key, () => `${API}/countries?banco=un_comtrade`);
  const data = get(key);
  return data && Array.isArray(data.reporters) ? data : null;
};

// Basket-scoped per-(município, year) cube — the FINEST geography grain. Mirrors
// window.geoYearly (keyed by banco + convention + basket), but at município grain so
// the client can roll it up to whichever sub-UF level is active (via geoMesh). No
// flow (production bancos have none). Returns null until loaded; an empty array for a
// banco with no município grain (COMEX/COMTRADE → the BFF returns []).
// `years` (optional) narrows the cube to a closed [y0, y1] window. The city set is
// the primary cost control, but it stops helping exactly where the municipal
// choropleth needs it most: a whole-UF map is ONE year over hundreds of cities. Left
// out, that request pulls every year (measured over all 5570: 153.634 rows / 16,9 MB
// / 28 s, against ~3.400 rows for a single year). Absent = full history, so the
// existing sub-UF callers — which DO want the whole series for the heatmap — are
// unchanged. It is part of the cache key, so the one-year map and the full-history
// heatmap coexist instead of evicting each other.
window.municipioYearly = function municipioYearly(bancoId, summary, cityCodes, years) {
  const b = window.bancoById && window.bancoById(bancoId);
  if (!b || !(b.provides || []).includes('geo')) return null;
  const conv = window.dataStore && window.dataStore.conv
    ? window.dataStore.conv()
    : { currency: 'BRL', correction: 'IPCA' };
  const codes = filterCodes(summary); // undefined = all products; comma list otherwise
  // INVARIANT (DATA-4): flow is deliberately omitted from the key AND the request below
  // because the município cube is only ever reached for a geo banco (the `provides` guard
  // above), and the geo (IBGE production) bancos have NO flow dimension. If a flow-bearing
  // source ever gains a município grain, ADD flow to BOTH the key and the request here —
  // otherwise this would silently serve all-flows totals under a flow-filtered app (the
  // exact bug window.geoYearly's flow-key prevents).
  // cityCodes = the município code set of the active sub-UF/município selection
  // (resolved client-side from the mesh), scoping the Gold scan to those cities. The
  // cube is ALWAYS city-scoped — with no city set there is nothing to fetch.
  if (!cityCodes || !cityCodes.length) return null;
  // The set can be hundreds of codes, so POST it in the body — a GET query string
  // would overflow gunicorn's request-line limit (~4 KB → HTTP 414) for a broad sub-UF
  // selection. The cache key still carries the full list (an in-memory Map key, not a
  // URL → no length limit), so distinct selections never collide.
  const y0 = years && years[0] != null ? years[0] : undefined;
  const y1 = years && years[1] != null ? years[1] : undefined;
  const key = `municipioYearly:${bancoId}:${conv.currency}|${conv.correction}:${codes ?? '*'}:${y0 ?? '*'}-${y1 ?? '*'}:${cityCodes.join(',')}`;
  ensure(key, () => [
    `${API}/municipio-yearly?${qs({
      banco: bancoId,
      codes,
      currency: conv.currency,
      correction: conv.correction,
      y0,
      y1,
    })}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cityCodes }) },
  ]);
  const data = get(key);
  return data && Array.isArray(data.municipioYearly) ? data.municipioYearly : null;
};

// ── cross-source comparable series ────────────────────────────────────────────
window.crossSeries = function crossSeries(bancoId, metricId, opts = {}) {
  const { y0, y1, states } = opts;
  // states = origin-UF array (cross-source per-UF scoping); undefined/empty = national.
  // Only the UF-capable bancos (IBGE PEVS, MDIC COMEX) honour it server-side.
  const st = states && states.length ? states.join(',') : undefined;
  const key = `cross:series:${bancoId}:${metricId}:${y0 ?? ''}:${y1 ?? ''}:${st ?? ''}`;
  ensure(key, () => `${API}/cross/series?${qs({ banco: bancoId, metric: metricId, y0, y1, states: st })}`);
  // bancoMeta/metricMeta are registry objects (bancos.js) joined client-side —
  // the contract (SeriesResult) carries them, and the view reads bancoMeta.short.
  const bancoMeta = window.bancoById ? window.bancoById(bancoId) : null;
  const metricMeta = window.metricById ? window.metricById(bancoId, metricId) : null;
  const data = get(key);
  if (data) return { ...data, bancoMeta, metricMeta };
  return {
    banco: bancoId,
    metric: metricId,
    key: `${bancoId}:${metricId}`,
    bancoMeta,
    metricMeta,
    label: (metricMeta && metricMeta.label) || '',
    unit: '',
    family: (metricMeta && metricMeta.family) || '',
    preview: false, // real data, just loading — not a demo (no PreviewBanner)
    loadError: errorOf(key), // a settled fetch failure → the view shows LoadErrorNote, not "no overlap"
    coverage: (metricMeta && metricMeta.years) || [0, 0],
    points: [],
  };
};

// Comparable window = intersection of the selected metrics' native coverage
// (read client-side from the banco registry — no fetch needed).
window.crossCommonWindow = function crossCommonWindow(refs = []) {
  const covs = refs
    .map((r) => {
      const b = window.bancoById && window.bancoById(r.b || r.banco);
      const m = b && (b.metrics || []).find((x) => x.id === (r.m || r.metric));
      return m && m.years;
    })
    .filter(Boolean);
  if (!covs.length) {
    // No metric coverage in the selection — derive the window from the registry's
    // full metric span (never a stale hardcoded year). Empty registry → current
    // year, so the arithmetic below stays valid.
    const all = (window.BANCOS || []).flatMap((b) => (b.metrics || []).map((m) => m.years)).filter(Boolean);
    if (!all.length) { const y = new Date().getFullYear(); return { y0: y, y1: y, union: [y, y] }; }
    const lo = Math.min(...all.map((c) => c[0]));
    const hi = Math.max(...all.map((c) => c[1]));
    return { y0: lo, y1: hi, union: [lo, hi] };
  }
  const y0 = Math.max(...covs.map((c) => c[0]));
  const y1 = Math.min(...covs.map((c) => c[1]));
  const union = [Math.min(...covs.map((c) => c[0])), Math.max(...covs.map((c) => c[1]))];
  return y0 <= y1 ? { y0, y1, union } : { y0: union[0], y1: union[1], union };
};

// ── crosswalk commodity catalog (the multi-source pickers' option universe) ───
// The cross/* analytics are keyed by the crosswalk agrupamento_id SLUG (not a PEVS
// product code), so their commodity picker must offer slugs. /api/catalog returns
// { agrupamento_id -> {id, name, pevs[], comex[], comtrade[]} }; we flatten it to a
// sorted [{ code: <slug>, name }] list (sync-over-async like the analytics below —
// reads the cache, kicks the fetch on a miss, returns [] until it lands).
// PEVS physical-unit family normalized pt-BR -> the English keys the views use
// (METRIC_FAMILIES / dataFilters key on 'mass'/'volume'). null = no single PEVS
// family (mixed, or a COMEX/COMTRADE-only commodity) -> family-gated pickers skip it.
const CATALOG_FAMILY_JS = { massa: 'mass', volume: 'volume' };
window.agrupamentoCatalog = function agrupamentoCatalog() {
  const key = 'cross:catalog';
  ensure(key, () => `${API}/catalog`);
  const data = get(key);
  if (!data) return [];
  return Object.values(data)
    .map((c) => ({
      code: c.id,
      name: c.name,
      family: c.family ? CATALOG_FAMILY_JS[c.family] || c.family : null,
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
};

// ── cross-source analytics (crosswalk-joined) ─────────────────────────────────
const crossAnalytic = (name, path, shell) =>
  function (agrupamentoId, states) {
    // states = origin-UF array (per-UF scoping for price-spread / value-added);
    // undefined/empty = national. The COMEX/PEVS sides honour it server-side.
    const st = states && states.length ? states.join(',') : undefined;
    const key = `cross:${name}:${agrupamentoId || '*'}:${st ?? ''}`;
    ensure(key, () => `${API}/cross/${path}?${qs({ commodity: agrupamentoId, states: st })}`);
    // A settled fetch failure carries loadError so the view shows LoadErrorNote instead
    // of rendering the empty shell as a legitimate "nenhum dado" result.
    return get(key) || { ...shell, loadError: errorOf(key) };
  };

// Loading shells use preview:false — the data IS real, just not arrived yet (so
// no "demonstração" banner flashes). Empty arrays render empty charts until the
// resource resolves and the gate re-renders with real data.

// Export coefficient feeds data.byUf straight into BrazilTileMap, which positions
// each tile by col/row — coords the /api deliberately omits (the views own UF_DATA).
// Like productivityData.byUF and snapshot.ufData, the rows MUST be decorated here
// or every tile lands at undefined·64 = NaN and the 27-UF map renders blank. Wrap
// the raw crossAnalytic producer so the decoration is applied to BOTH the resolved
// payload and the loading shell (no-op on []), keeping the contract's `byUf` key.
const _exportCoefRaw = crossAnalytic('export-coef', 'export-coef', {
  preview: false, unit: 'mil t', byUf: [], national: {}, timeseries: [], states: [],
});
// `states` scopes BOTH sides of the ratio server-side (PEVS production AND COMEX
// exports) — narrowing only one would divide a state's output by the whole
// country's exports and silently deflate the coefficient.
window.exportCoefficient = function exportCoefficient(agrupamentoId, states) {
  const data = _exportCoefRaw(agrupamentoId, states);
  return { ...data, byUf: decorateUfRows(data.byUf) };
};
window.marketShare = crossAnalytic('market-share', 'market-share', {
  preview: false, unit: 'US$ bi', series: [], byProduct: [],
});
window.priceSpread = crossAnalytic('price-spread', 'price-spread', {
  preview: false, unit: 'US$/kg', series: [],
});
window.tradeMirror = crossAnalytic('mirror', 'mirror', {
  preview: false, unit: 'US$ bi', series: [], discrepancy: [],
});
window.valueAddedAnalysis = crossAnalytic('value-added', 'value-added', {
  preview: false, years: [], levels: [],
  byLevel: {}, byLevelWeight: {}, byLevelPrice: {},
  series: [], premium: 0, predominant: null, nCodes: 0,
});

// ── data-blocked producers (no upstream source — honest preview shells) ───────
// chainBalance needs SEFAZ inter-UF flows; harvestShipmentLag needs MONTHLY PEVS
// (annual-only). The views render their blocked-source banner.
window.chainBalance = function chainBalance(_code, year) {
  return {
    preview: true, unit: 'mil t', year: year || 2024, produced: 0, exported: 0, internal: 0,
    domestic: 0, expFrac: 0, intFrac: 0, domFrac: 0, worldShare: 0, worldTotal: 0, exportUsd: 0,
    sankey: { nodes: [], links: [] },
  };
};
window.harvestShipmentLag = function harvestShipmentLag() {
  return {
    preview: true, months: [], production: [], shipments: [], peakHarvest: 0, peakShip: 0,
    lagMonths: 0, corrAtLag: 0, lagProfile: [],
  };
};
// market-nature is EDIT-DRIVEN: COMTRADE value summed by the economic purpose
// (consumo/processamento) the researcher assigns to each (customs procedure × flow) pair in
// the "Tipo de Mercado" matrix (dim_flow_market_scd2), carried as serving_comtrade_annual.
// market_nature. Empty series when the recorte has no classified pair — the view guards
// that with an honest empty state (no synthetic fallback).
window.marketNatureAnalysis = crossAnalytic('market-nature', 'market-nature', {
  preview: false, years: [], series: [], latest: {},
});

// ── trade adapters (flow / partner / monthly) — resource-backed, COMEX/COMTRADE ─
// The banco's dimension labels (originLabel/destLabel/flowLabel) come from the
// registry (bancoDim) client-side; the API supplies the data.
// The origin-UF (`states`) filter narrows the COMEX flow/partner readers; for a
// country-origin banco (COMTRADE) it cannot apply, so the producer drops the param
// and surfaces an honest `notApplicable.states` note (mirrors productivityData's
// basket handling) instead of sending a filter the grain would ignore.
const ufNote = (bancoId, summary, applies) =>
  ufFilterActive(summary) && !applies
    ? { states: 'O filtro de UF de origem não se aplica a este banco — a origem é um país, não uma UF.' }
    : undefined;

window.flowData = function flowData(bancoId, summary) {
  const codes = filterCodes(summary);
  const y0 = filterYear(summary && summary.startDate);
  const y1 = filterYear(summary && summary.endDate);
  const applies = bancoOriginIsUf(bancoId);
  // Only send the UF filter where the origin is a Brazilian UF (COMEX); for a
  // country origin it is not-applicable, so omit it (and note it below).
  const states = applies ? filterStates(summary) : undefined;
  const notApplicable = ufNote(bancoId, summary, applies);
  const key = `trade:flow:${bancoId}:${filterSig(summary)}:${countrySig(summary)}`;
  ensure(key, () =>
    `${API}/flow?${qs({
      banco: bancoId, codes, states, y0, y1,
      reporters: filterReporters(summary), partners: filterPartners(summary),
    })}`);
  const data = get(key);
  const dim = (d) => (window.bancoDim ? window.bancoDim(bancoId, d) : {});
  const labels = {
    originLabel: dim('origin').label || 'Origem',
    destLabel: dim('dest').label || 'Destino',
  };
  return data
    ? { ...data, ...labels, notApplicable }
    : { preview: false, unit: 'US$', ...labels, notApplicable, nodes: [], links: [], loadError: errorOf(key) };
};
window.partnerData = function partnerData(bancoId, summary, metric) {
  const codes = filterCodes(summary);
  const y0 = filterYear(summary && summary.startDate);
  const y1 = filterYear(summary && summary.endDate);
  const applies = bancoOriginIsUf(bancoId);
  const states = applies ? filterStates(summary) : undefined;
  const notApplicable = ufNote(bancoId, summary, applies);
  // metric ∈ value|weight|price → the server-side ranking dimension (Capital /
  // Volume / Preço médio). It is part of the cache key so switching the metric
  // re-ranks server-side rather than re-sorting a value-ranked page (which would
  // drop niche high-price buyers — see serving/sql.trade_by_partner).
  const m = metric || 'value';
  const key = `trade:partners:${bancoId}:${m}:${filterSig(summary)}:${countrySig(summary)}`;
  ensure(key, () =>
    `${API}/partners?${qs({
      banco: bancoId, codes, states, y0, y1, metric: m,
      reporters: filterReporters(summary), partners: filterPartners(summary),
    })}`);
  const data = get(key);
  const flowLabel = (window.bancoDim && window.bancoDim(bancoId, 'partner').label) || 'Parceiro';
  return data
    ? { ...data, flowLabel, notApplicable }
    : { preview: false, flowLabel, unit: 'US$', notApplicable, partners: [], loadError: errorOf(key) };
};
// Per-product ranking WITHIN the selected UF(s) — the "Base de dados" per-UF
// product breakdown (inverse of ViewProductProfile's "onde X é produzido"). The
// backend returns [] unless a UF is selected; currency/correction pick the
// deflated value column server-side (same as /snapshot), so the conv is part of
// the cache key.
window.productsByUf = function productsByUf(bancoId, summary, conv) {
  const codes = filterCodes(summary);
  const states = filterStates(summary);
  const y0 = filterYear(summary && summary.startDate);
  const y1 = filterYear(summary && summary.endDate);
  const currency = conv && conv.currency;
  const correction = conv && conv.correction;
  const key = `pbu:${bancoId}:${filterSig(summary)}:${currency || ''}:${correction || ''}`;
  ensure(key, () => `${API}/products-by-uf?${qs({ banco: bancoId, codes, states, y0, y1, currency, correction })}`);
  return get(key) || { products: [], loadError: errorOf(key) };
};
window.monthlyData = function monthlyData(bancoId, summary) {
  const codes = filterCodes(summary);
  const states = filterStates(summary);
  const y0 = filterYear(summary && summary.startDate);
  const y1 = filterYear(summary && summary.endDate);
  // The seasonality mart now KEEPS state_acronym in its grain (P6), so the UF
  // (`states`) filter narrows the seasonal profile to one origin state — send it.
  const key = `trade:monthly:${bancoId}:${filterSig(summary)}`;
  ensure(key, () => `${API}/monthly?${qs({ banco: bancoId, codes, states, y0, y1 })}`);
  const data = get(key);
  return data
    ? { ...data }
    : {
        preview: false,
        loadError: errorOf(key),
        unit: 'US$',
        weightUnit: 'mil t',
        years: [],
        months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        matrix: {},
        // 12 zeros (not []) so the view's peak/low/amplitude math survives the
        // loading render; real values replace it when the fetch resolves.
        monthlyAvg: new Array(12).fill(0),
        weightMatrix: {},
        weightMonthlyAvg: new Array(12).fill(0),
        series: [],
      };
};
// PAM área × rendimento (backs ViewProductivity). Resource-backed: fetches the
// real /api/productivity (production ÷ harvested area → yield kg/ha, server-side)
// for the selected crop. The router only renders this view for a yield-capable
// banco (IBGE PAM), so the empty shell below is just the brief loading frame —
// the view renders empty charts until the resource resolves with real data.
window.productivityData = function productivityData(bancoId, crop, summary) {
  // Period (year window) scopes the yield/area series + the latest-year geography.
  // The FilterMenu product BASKET does NOT apply here: this view picks its own crop
  // (the chip selector above), so a basket selection cannot narrow it — surface
  // that honestly via `notApplicable` instead of silently ignoring it.
  const y0 = filterYear(summary && summary.startDate);
  const y1 = filterYear(summary && summary.endDate);
  const states = filterStates(summary);
  const basketActive = !!(summary && summary.basket != null);
  const notApplicable = basketActive
    ? { basket: 'A cesta de produtos não se aplica aqui — escolha a lavoura no seletor acima.' }
    : undefined;
  // `states` DOES apply here (unlike the basket): the PAM mart is UF-grained. It is
  // part of the key because it changes the numbers — yield is a ratio, so the
  // "national" series returned is the SELECTED states' series, and the view relabels
  // it from the `states` the payload echoes back.
  const key = `productivity:${bancoId}:${crop || 'default'}:${y0 ?? ''}|${y1 ?? ''}|${states ?? '*'}`;
  ensure(
    key,
    () => `${API}/productivity?${qs({ banco: bancoId, crop: crop || undefined, y0, y1, states })}`,
  );
  const data = get(key);
  if (!data) {
    return {
      preview: false,
      loadError: errorOf(key),
      notApplicable,
      crop: { code: '', name: '' },
      crops: [],
      yieldUnit: 'kg/ha',
      areaUnit: 'ha',
      series: [],
      national: { yieldCagr: 0 },
      states: [],
      byUF: [],
    };
  }
  // The per-UF tile map needs col/row tile coords the /api omits — decorate from
  // the UF_DATA registry, exactly like the snapshot's ufData (decorate.js).
  return { ...data, notApplicable, byUF: decorateUfRows(data.byUF) };
};
