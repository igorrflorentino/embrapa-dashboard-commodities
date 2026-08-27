// main.jsx — application entry. Order matters: bootstrap-globals sets window.React
// FIRST (the ui/ modules read React as a bare global at eval time), then the
// modules side-effect-import in dependency order (each assigns window.X). The data
// layer + analytical charts are NOT in ui/ — they live in src/data/* (API-backed)
// and src/charts/* (Plotly.js). History: PLANS/react_migration_contract_map.md §5.

import './bootstrap-globals'; // window.React/ReactDOM — must be first
import React, { useState, useEffect } from 'react';
import { resolveChipCoverage } from './data/chipCoverage';
import { subscribe as subscribeResource } from './data/resource';

// ── registries + utils ────────────────────────────────────────────────────────
import './ui/data.js'; // static registries (UF tiles, REGIONS, QUALITY_FLAGS, UNIT_FAMILIES) + pt-BR formatters
import './ui/bancos.js';
import './ui/views.js';
import './ui/filtersSchema.js';
import './ui/glossary.js';
import './ui/urlState.js';
import './ui/chipFmt.js';
import './ui/filterSummary.js';
import './ui/geoSelect.js';
import './ui/useGeoCascade.js';
import './ui/seriesUtils.js';
import './ui/dataFilters.js';
import './ui/csvExport.js';
import './ui/MetricConventions.jsx';

// ── data layer (NEW — API-backed, replaces the synthetic producers) ───────────
import './data/dataStore.js';
import './data/producers.js';
import './data/enrichment.js';
import './data/feedback.js'; // window.postFeedback — the "Enviar feedback" channel
import './ui/contracts.js'; // runtime contract-drift lint: audits live producers vs SNAPSHOT_CONTRACTS on load

// ── charts (NEW — Plotly for analytical charts; SVG ports for tile-map/donut) ─
import './charts/LineChart.jsx';
import './charts/MultiLineChart.jsx';
import './charts/StackedArea.jsx';
import './charts/BarChart.jsx';
import './charts/YoYBars.jsx';
import './charts/Heatmap.jsx';
import './charts/FlagBars.jsx';
import './charts/RegionBars.jsx';
import './charts/LorenzCurve.jsx';
import './charts/SankeyChart.jsx';
import './charts/MonthYearHeatmap.jsx';
import './charts/DualAxisLineChart.jsx';
import './charts/StackedPanels.jsx';
import './charts/MonthlyOverlay.jsx';
import './charts/LagBars.jsx';
import './charts/Donut.jsx'; // SVG port (categorical share)
import './charts/BrazilTileMap.jsx'; // SVG port (geographic tile grid)
import './charts/BrazilChoropleth.jsx'; // maplibre choropleth (real UF shapes)
import './charts/MunicipioChoropleth.jsx'; // maplibre choropleth (intra-UF município shapes)
import './charts/PreviewBanner.jsx'; // non-chart banner the preview/cross views use

// ── atoms + shell ─────────────────────────────────────────────────────────────
import './ui/Icon.jsx';
import './ui/Status.jsx';
import './ui/Sparkline.jsx';
import './ui/UnitFamily.jsx';
import './ui/Atoms.jsx';
import './ui/DataBoundary.jsx';
import './ui/Glossary.jsx';
import './ui/shChapters.js'; // window.SH_CHAPTERS — SH2 names for the product tree
import './ui/FilterMenu.jsx';
import './ui/FilterTriggerBar.jsx';
import './ui/FeedbackModal.jsx';
import './ui/AppShell.jsx';
import './ui/MainScreen.jsx';

// ── views ─────────────────────────────────────────────────────────────────────
import './ui/ViewOverview.jsx';
import './ui/ViewValueVolume.jsx';
import './ui/ViewGeography.jsx';
import './ui/ViewConcentration.jsx';
import './ui/ViewQuality.jsx';
import './ui/ViewDados.jsx';
import './ui/ViewReferencias.jsx'; // read-only seed reference consultation ("Referências")
import './ui/ViewCadastroProdutos.jsx'; // Curadoria — the editable commodity catalog
import './ui/ViewProductProfile.jsx';
import './ui/ViewTerritoryProfile.jsx';
import './ui/ViewProductCompare.jsx';
import './ui/ViewRebanho.jsx';
import './ui/ViewProductivity.jsx';
import './ui/ViewSeasonality.jsx';
import './ui/ViewFlows.jsx';
import './ui/ViewPartners.jsx';
import './ui/ViewCrossSource.jsx';
import './ui/ViewsMultiSource.jsx';
import './ui/ViewsChain.jsx';
// Engenharia de Atributos: the industrialization editor (ViewCuration) + the two curated
// analyses (ViewCuratedAnalyses — Valor agregado editável, Finalidade econômica seed-driven).
import './ui/ViewCuration.jsx';
import './ui/ViewCuratedAnalyses.jsx';
import './ui/ViewAbout.jsx';
import './ui/ViewHealth.jsx';
import './ui/ViewComingSoon.jsx';
import './ui/ViewNotApplicable.jsx';
import './ui/ViewPerspectiveSoon.jsx';

// ── deep-link decode (the DECODER half of the urlState.js codec contract) ─────
function readStateFromURL() {
  const q = new URLSearchParams(location.search);
  if (!window.urlHasOwnState || !window.urlHasOwnState(q)) return null;
  const conv = { ...window.DEFAULT_CONVENTIONS };
  // Clamp the hydrated currency to the offered set (the CURRENCY_FX keys). A stale
  // shared/bookmarked URL may still carry a currency that is no longer offered;
  // an unknown currency would later
  // deref CURRENCY_FX[cur].symbol (undefined) and white-screen the view, so keep
  // the default instead.
  const cur = q.get('cur');
  if (cur && window.CURRENCY_FX && window.CURRENCY_FX[cur]) conv.currency = cur;
  if (q.get('corr')) conv.correction = q.get('corr');
  // Clamp an unservable currency × correction combo (USD × IGP-M/IGP-DI has no US$
  // deflated column, so it would render a real R$ value under a US$ symbol). The
  // strip disables these; a bookmarked deep link must not bypass that gate.
  if (window.clampConvention) Object.assign(conv, window.clampConvention(conv));
  if (q.get('mu') || q.get('vu')) {
    conv.units = { ...conv.units, mass: q.get('mu') || conv.units?.mass, volume: q.get('vu') || conv.units?.volume };
  }
  if (q.get('as') != null) conv.autoScale = q.get('as') === '1';
  const summary = {
    basket: window.urlDecodeArr(q, 'pb'),
    flags: window.urlDecodeArr(q, 'fl'),
    states: window.urlDecodeArr(q, 'st'),
    // Sub-UF / município geography (v1.5.2); absent → null = "all" (no narrowing).
    mesos: window.urlDecodeArr(q, 'me'),
    micros: window.urlDecodeArr(q, 'mc'),
    inters: window.urlDecodeArr(q, 'it'),
    imediatas: window.urlDecodeArr(q, 'im'),
    munis: window.urlDecodeArr(q, 'mn'),
    // Value-range is INTENTIONALLY non-backed (no row-level filter path): the
    // FilterMenu forces it to null on open, so a stale/hand-edited URL carrying
    // vmn/vmx must NOT restore a phantom range (which the ABNT citation would then
    // assert as a real "Faixa de valor"). Force null here, mirroring the menu.
    valueMin: null,
    valueMax: null,
    startDate: q.get('sd') || null,
    endDate: q.get('ed') || null,
    // Server-side flow filter (export/import); absent → all flows.
    flow: q.get('fx') || null,
    // Server-side customs-procedure filter (regime aduaneiro, COMTRADE); absent → all regimes.
    customs: q.get('cx') || null,
    // Server-side tipo-de-mercado filter (COMTRADE); absent → all purposes.
    market: q.get('mk') || null,
    // COMTRADE país reporter (3-state): 'ALL' → world sentinel, CSV → ISO array, absent → null
    // (Brazil default). País parceiro: standard array (null = all).
    reporters: q.get('rp') === 'ALL' ? '__all__' : window.urlDecodeArr(q, 'rp'),
    partners: window.urlDecodeArr(q, 'pt'),
  };
  let crossState = window.DEFAULT_CROSS_STATE;
  const xs = q.get('xs');
  if (xs) {
    crossState = {
      series: xs.split('|').filter(Boolean).map((s) => { const [b, m] = s.split(':'); return { b, m }; }),
      mode: q.get('xm') || 'base100',
      y0: window.urlDecodeNum(q, 'xy0'),
      y1: window.urlDecodeNum(q, 'xy1'),
    };
  }
  // Validate the deep-linked view id against the LIVE menu. An unknown / stale id (e.g.
  // ?v=curated_market_nature — a frozen, de-listed view — or a typo) must NOT resolve a
  // component: it would render with an empty title and the wrong banco's filter bar. Fall
  // back to the universal default instead.
  let view = q.get('v') || 'overview';
  if (window.viewById && !window.viewById(view)) view = 'overview';
  const isCross = !!(window.viewById && window.viewById(view)?.crossBanco);
  // Validate ?b (banco) like ?v: an unknown/stale id would silently resolve to a wrong banco
  // (bancoById falls back internally), so pin it to the default when it isn't a real banco.
  let database = q.get('b') || 'ibge_pevs';
  if (window.bancoById && !window.bancoById(database)) database = 'ibge_pevs';
  // Clamp the server-side trade filters (flow/customs/market) to the banco's OFFERED options,
  // mirroring the ?cur/?v/?b clamps: a stale/hand-edited URL carrying a value this banco doesn't
  // offer must not be sent to the API (a 400) nor paint a phantom filter chip. absent (null) =
  // all. (reporters/partners are country codes validated server-side against a universe that
  // loads asynchronously, so they can't be whitelisted here at parse time.)
  const _clampToOpts = (val, helper) => {
    if (val == null || !helper) return val; // absent, or helper not loaded → leave as-is
    const opts = helper(database);
    return opts && opts.some((o) => o.value === val) ? val : null;
  };
  summary.flow = _clampToOpts(summary.flow, window.flowOptionsFor);
  summary.customs = _clampToOpts(summary.customs, window.customsOptionsFor);
  summary.market = _clampToOpts(summary.market, window.marketOptionsFor);
  // Validate ?ip (info page): an unknown value renders the generic "Saúde do sistema" header
  // over an "em preparação" body. Only the known info pages are routable; else no info page.
  const _INFO_PAGES = new Set(['about', 'referencias', 'cadastro_produtos', 'health']);
  const ip = q.get('ip');
  const infoPage = ip && _INFO_PAGES.has(ip) ? ip : null;
  return {
    view,
    database,
    infoPage,
    conventions: conv,
    summary,
    crossState,
    mode: isCross ? 'multi' : 'single',
  };
}

// ── filter chips: the FilterTriggerBar reads display strings (summary.products,
// .period, …). FilterMenu.onApply emits them, but the initial/URL-restored
// summary only has raw arrays — compute the chips from applyFilters + the
// registries (chipFmt is the shared formatter the FilterMenu also uses). ───────
function withChips(summary, database, conventions) {
  const s = summary || {};
  if (s.products && s.period) return s; // already carries chips (from FilterMenu)
  const f = window.applyFilters ? window.applyFilters(s, database) : null;
  if (!f || !window.chipFmt) return s;
  const conv = conventions || window.DEFAULT_CONVENTIONS || {};
  const sym = ((window.CURRENCY_FX || {})[conv.currency] || { symbol: 'R$' }).symbol;
  const flagsAll = window.QUALITY_FLAGS || [];
  const labelOf = (id) => (flagsAll.find((q) => q.id === id) || {}).label || id;
  // Banco-aware chip coverage when the snapshot hasn't loaded yet (FINDING #2).
  // applyFilters falls back to the PEVS synthetic globals (12 products, 1986–2024)
  // until the active banco's snapshot lands, so on first load / banco switch the
  // chips would show the cross-source catalog count + the PEVS year span for EVERY
  // banco (e.g. COMEX showed "Todos (12) · 1986–2024" instead of its real
  // "Todos (5) · 1997–2026"). resolveChipCoverage reads the ACTIVE banco's own
  // metadata (live /api/source-meta coverage, else the banco registry prov) in that
  // window. The dataStore-subscribe effect re-renders this once either resolves.
  const snapLoaded = !!(window.dataStore && window.dataStore.get && window.dataStore.get(database));
  const meta = (!snapLoaded && window.dataStore && window.dataStore.meta)
    ? window.dataStore.meta(database) : null;
  const { total, yearStart, yearEnd } = resolveChipCoverage({
    snapLoaded,
    applied: f,
    meta,
    hasDateSel: !!(s.startDate || s.endDate),
  });
  // Clamp the hydrated basket to the active banco's LOADED product universe. A shared/
  // bookmarked link may carry a code the Curadoria later hid/discontinued (or a code from a
  // different banco); the data layer already intersects it away, so counting the RAW basket
  // would show a phantom "1 de N" chip over charts that actually render all products. Clamp
  // only once the real snapshot is loaded (else f.products is the PEVS synthetic fallback);
  // an empty result → null = "Todos", matching what the data layer actually displays.
  let basket = s.basket || null;
  if (snapLoaded && basket) {
    const universe = new Set((f.products || []).map((p) => p.code));
    basket = basket.filter((c) => universe.has(c));
    if (!basket.length) basket = null;
  }
  const firstName =
    basket && basket.length === 1
      ? ((f.products || []).find((p) => p.code === basket[0]) || {}).name
      : null;
  // Count REAL Brazilian UFs only (FINDING #4): a trade banco's ufDataFull
  // includes non-state pseudo-origins (ND/EX/ZN…) that must not inflate the geo
  // chip to "32 UFs". Prefer the backend's per-row `real` flag, falling back to
  // the canonical 27-UF registry membership; cap at 27.
  const ufDataFull = f.ufDataFull || [];
  const isRealUf = (u) => (u.real != null ? u.real : (window.isCanonicalUf ? window.isCanonicalUf(u.uf) : true));
  const realUfCount = ufDataFull.filter(isRealUf).length;
  const ufTotal = Math.min(27, realUfCount || 27);
  const hasGeo = ufDataFull.length > 0;
  // Geo chip via the SAME formatter the FilterMenu uses on apply
  // (filterSummary.geoChipText), so a URL-restored summary shows the identical chip
  // — including a município/sub-UF narrowing — instead of chipFmt.geoStates, which
  // only counted UFs and silently dropped the município scope (M3). nations/regions
  // don't travel in the URL, so they default to the menu's restore defaults
  // (BR only, all regions); the município universe comes from the IBGE mesh (0 until
  // it lands — the chip corrects on the resource re-render).
  const meshLen = (window.geoMesh && (window.geoMesh() || []).length) || 0;
  const muniSliceable =
    hasGeo && meshLen > 0 &&
    (!window.geoLevelFor || window.geoLevelFor(database) === 'municipio');
  const geoChip = window.filterSummary
    ? window.filterSummary.geoChipText({
        hasGeo,
        nationsSize: 1, nationsTotal: 1, hasOnlyBR: true,
        regionsSize: 5, regionsTotal: 5,
        statesSize: s.states ? s.states.length : 27, statesTotal: 27,
        munisSize: s.munis ? s.munis.length : meshLen, munisTotal: meshLen,
        muniSliceable,
      })
    : window.chipFmt.geoStates(s.states ? s.states.length : null, ufTotal, hasGeo);
  return {
    ...s,
    products: window.chipFmt.products(basket ? basket.length : null, total, firstName),
    period: window.chipFmt.period(yearStart, yearEnd),
    valueRange: window.chipFmt.valueRange(s.valueMin, s.valueMax, sym),
    geo: geoChip,
    quality: window.chipFmt.quality(s.flags || null, flagsAll.length, labelOf),
  };
}

// ── error boundary: a single view/component throwing must not blank the whole
// app (the prototype had none — real, sparser data exposes edge cases). Shows a
// recoverable message inside the content area; the shell stays usable. ─────────
class ViewErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Surface the error + component stack to the console so a view's render
    // failure is diagnosable, instead of being silently swallowed by
    // getDerivedStateFromError (which only sets state for the fallback UI).
    console.error('ViewErrorBoundary caught a render error:', error, info?.componentStack);
  }

  componentDidUpdate(prev) {
    // Reset the error when navigating to a different view/banco.
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="card subtle" style={{ margin: 24 }}>
          <div className="overline">Erro ao renderizar a perspectiva</div>
          <p className="caption" style={{ padding: '8px 4px' }}>
            {String(this.state.error?.message || this.state.error)}
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}

// ── DataBoundary gate: load the active banco's snapshot (async) and block the
// per-banco data views on it. Info pages + cross-banco views don't need the
// active snapshot, so they render immediately. ───────────────────────────────
function DataGate({ database, infoPage, view, children }) {
  const d = window.useBancoData(database); // hook (DataBoundary.jsx) — loads + subscribes
  const banco = window.bancoById && window.bancoById(database);
  const vm = window.viewById && window.viewById(view);
  const isBancoView = !infoPage && !(vm && vm.crossBanco) && !!banco;

  // Maturity (live/soon) is the single source of truth from BigQuery, delivered by
  // /api/source-meta. Until it resolves for this banco, whether the view shows real
  // data or the "Em breve" placeholder is unknown — so wait on the loader instead of
  // flashing the wrong state. useBancoData() already kicks the source-meta fetch
  // alongside the snapshot; this just holds the gate (and the subscribe effect below
  // re-renders once it lands).
  if (isBancoView && window.dataStore && !window.dataStore.hasMeta(database)) {
    return <window.DataLoading banco={banco} />;
  }

  const needsData = isBancoView && banco.status === 'live';
  if (needsData) {
    if (d.status === 'loading' || d.status === 'idle') return <window.DataLoading banco={banco} />;
    if (d.status === 'error') {
      return <window.DataError banco={banco} message={d.error} onRetry={d.reload} />;
    }
  }
  return (
    <>
      {needsData && d.stale && (
        <window.FreshnessBanner banco={banco} latestAt={d.latestAt} onReload={d.reload} />
      )}
      {children}
    </>
  );
}

// ── root: holds the app state the prototype's Dashboard component held ─────────
function Dashboard() {
  // Fresh open (no deep-link state in the URL) lands on the "Sobre" info page —
  // a calm, non-data entry point — instead of a banco's Visão geral. A deep link
  // (shared/bookmarked URL with its own state) is honoured as-is.
  const initial = readStateFromURL() || { infoPage: 'about' };
  const [view, setView] = useState(initial.view || 'overview');
  const [database, setDatabase] = useState(initial.database || 'ibge_pevs');
  const [infoPage, setInfoPage] = useState(initial.infoPage ?? null);
  const [summary, setSummary] = useState(initial.summary || {});
  const [conventions, setConventions] = useState(initial.conventions || window.DEFAULT_CONVENTIONS);
  const [crossState, setCrossState] = useState(initial.crossState || window.DEFAULT_CROSS_STATE);
  const [mode, setMode] = useState(initial.mode || 'single');
  const [filterOpen, setFilterOpen] = useState(false);
  // Lifted above DataGate for the same reason as filterOpen: every conventions onChange
  // re-triggers a snapshot load, and DataGate swaps its children (MetricConventions
  // included) for a loading placeholder while that's in flight — local state inside the
  // component would be wiped on every single toggle, closing the panel after each click.
  const [metricsExpanded, setMetricsExpanded] = useState(false);
  const [, forceTick] = useState(0);

  // Conventions → data layer bridge: currency/correction pick the deflated value
  // column server-side, so a change re-fetches the snapshot (contract map §0.2).
  useEffect(() => {
    if (window.dataStore?.setConventions) window.dataStore.setConventions(conventions);
  }, [conventions]);

  // Filter bridge for a view to request a filter change (or open the filter modal)
  // WITHOUT a callback threaded through MainScreen's per-view props — those are the
  // SAME props every OTHER perspective also renders through, so adding one there for
  // a single view's interaction (Geografia's click-a-UF-to-filter, and its "abrir
  // filtro" button on the município empty state) would touch a contract ~20 other
  // views share. `setSummary`/`setFilterOpen` are React setState setters, which
  // React guarantees are referentially stable across renders, so registering once
  // here is enough — this always calls into the CURRENT state, never a stale one.
  useEffect(() => {
    window.patchFilter = (patch) => setSummary((s) => ({ ...s, ...patch }));
    window.openFilterMenu = () => setFilterOpen(true);
    // Perspective-to-perspective navigation, for the one case where two views are
    // halves of the same question: Geografia shows how the activity spreads ACROSS
    // territories and offers "Ver raio-x" to open the selected place in Perfil do
    // território, which shows what happens INSIDE it. Registered here for the same
    // reason as the two above — `setView` is a stable setState setter, and threading a
    // navigation prop through the shared view contract would touch ~20 other views for
    // one interaction.
    window.goToView = (id) => setView(id);
    return () => {
      delete window.patchFilter; delete window.openFilterMenu; delete window.goToView;
    };
  }, []);

  // Flow → data layer bridge: fluxo (export/import) is the ONE server-side FILTER
  // (the trade snapshot is pre-aggregated over flow), so a direction change re-fetches
  // — unlike the client-side product/geo/quality filters that narrow the loaded
  // snapshot. Absent/'all' sums every flow (production bancos never set it).
  useEffect(() => {
    if (window.dataStore?.setFlow) window.dataStore.setFlow(summary.flow || 'all');
  }, [summary.flow]);

  // Regime → data layer bridge: the customs procedure (regime aduaneiro) is the SECOND
  // server-side filter for COMTRADE (the snapshot is pre-aggregated over customs_code),
  // so a regime change re-fetches. Absent/'all' sums every regime (the total).
  useEffect(() => {
    if (window.dataStore?.setCustoms) window.dataStore.setCustoms(summary.customs || 'all');
  }, [summary.customs]);

  // Market → data layer bridge: the tipo de mercado is the THIRD server-side filter for
  // COMTRADE (the snapshot is pre-aggregated over market_nature), so a change re-fetches.
  useEffect(() => {
    if (window.dataStore?.setMarket) window.dataStore.setMarket(summary.market || 'all');
  }, [summary.market]);

  // Country → data layer bridges: país reporter / parceiro are server-side filters for
  // COMTRADE (the snapshot is pre-aggregated over reporter/partner), so a change re-fetches.
  // reporter: null=Brasil (default), '__all__'=mundo, array=IN-list. partner: null=todos, array.
  useEffect(() => {
    if (window.dataStore?.setReporters) window.dataStore.setReporters(summary.reporters ?? null);
  }, [summary.reporters]);
  useEffect(() => {
    if (window.dataStore?.setPartners) window.dataStore.setPartners(summary.partners ?? null);
  }, [summary.partners]);

  // Banco switch (changeDatabase): the prototype's bancos.js/MetricConventions doc
  // promised two resets the React port had dropped. Without them a banco switch
  // left BOTH the previous banco's filter basket and display currency in place:
  //   1. F1.3 — the stale basket intersects the new banco's product universe to
  //      [] → every chart renders zero, while the trigger bar still shows the old
  //      banco's chips. Reset the filter summary so the new banco starts unfiltered.
  //   2. F1.4 — default the display currency to the banco's OWN base currency
  //      (canonCurrencyFor: USD for the USD-native trade bancos, R$ for production).
  //      This is now a sensible DEFAULT, not a correctness crutch: the BFF serves a
  //      trade snapshot in whatever currency is requested (the real BRL/USD/EUR Gold
  //      column), so switching back to R$ shows the REAL R$ figure — no longer the
  //      raw USD under an R$ label. Correction/units/auto-scale carry over.
  const databaseRef = React.useRef(database);
  databaseRef.current = database;
  const changeDatabase = React.useCallback((nextId) => {
    if (nextId === databaseRef.current) return; // re-selection: no reset
    setSummary({}); // F1.3: drop the previous banco's basket/period/value/geo
    const base = window.canonCurrencyFor ? window.canonCurrencyFor(nextId) : 'BRL';
    // Default to the banco's base currency, then clamp: a USD-base banco inherits the
    // unservable USD × IGP-M/IGP-DI combo if the previous banco left that correction
    // active, so snap the correction back to IPCA in the same update.
    setConventions((c) => {
      const next = c && c.currency === base ? c : { ...c, currency: base };
      return window.clampConvention ? window.clampConvention(next) : next;
    }); // F1.4
    setDatabase(nextId);
    // Always land on Visão geral on a banco switch: the simplest, predictable rule
    // (no "this perspective doesn't apply to the new banco" dead-ends), and it
    // exits any open info page (Sobre/Glossário/Saúde) back into the data.
    setView('overview');
    setInfoPage(null);
  }, []);

  // Mode switch (single ↔ multi) always loads a consistent default perspective so
  // the change is visually unmistakable: multi → the general cross view
  // (cross_source), single → Visão geral. Guards a no-op click on the active mode.
  const modeRef = React.useRef(mode);
  modeRef.current = mode;
  const changeMode = React.useCallback((nextMode) => {
    if (nextMode === modeRef.current) return;
    setMode(nextMode);
    setInfoPage(null);
    setView(nextMode === 'multi' ? 'cross_source' : 'overview');
  }, []);

  // Sync-over-async gate (contract map §3.1): the cross/curation producers are
  // synchronous cache reads that kick off a fetch on a miss. Re-render the tree
  // when any resource resolves so the view's next sync read sees real data.
  useEffect(() => subscribeResource(() => forceTick((t) => t + 1)), []);

  // Re-render when the dataStore changes (snapshot or /api/source-meta resolves)
  // so the filter chips recompute from the ACTIVE banco's real values on first
  // load / banco switch (FINDING #2) — withChips reads dataStore.meta() / get(),
  // which only become truthy once those async fetches land. Without this, the
  // chip would sit on the PEVS synthetic default until a filter-apply re-rendered.
  useEffect(
    () => (window.dataStore && window.dataStore.subscribe
      ? window.dataStore.subscribe(() => forceTick((t) => t + 1))
      : undefined),
    [],
  );

  // Eager-load the live maturity/coverage (/api/source-meta) for EVERY visible
  // banco at startup, so the sidebar / Sobre / Saúde maturity tags reflect the
  // BigQuery source of truth immediately — not only the active banco. The
  // dataStore.subscribe effect above re-renders as each resolves; loadMeta dedupes.
  useEffect(() => {
    const all = window.visibleBancos ? window.visibleBancos() : (window.BANCOS || []);
    all.forEach((b) => window.dataStore && window.dataStore.loadMeta && window.dataStore.loadMeta(b.id));
    // Warm the IBGE municipal mesh (the sub-UF + município cascade universe) once at
    // startup so the geography filter's new levels are populated before first open.
    if (window.geoMesh) window.geoMesh();
  }, []);

  // URL write-back: mirror the app state into the query string (replaceState, no
  // history clutter) so reload + copy-paste preserve view/banco/filters/
  // conventions/cross. Uses the SAME codec (urlState.js) the share button +
  // readStateFromURL use, so the encoder/decoder can't drift on the wire format.
  useEffect(() => {
    if (!window.urlEncodeState || !window.buildUrlState) return;
    const isCross = !!(window.viewById && window.viewById(view)?.crossBanco);
    // Same encoder as the Compartilhar/ABNT permalink (urlState.buildUrlState) —
    // so the address-bar URL and the shared URL can never encode the SAME state
    // differently (the H1 drift, where the write-back dropped me/mc/it/im/mn).
    const qs = window.urlEncodeState(
      window.buildUrlState({ view, database, infoPage, conventions, summary, crossState, isCross }),
    );
    window.history.replaceState(null, '', qs ? `${location.pathname}?${qs}` : location.pathname);
  }, [view, database, infoPage, summary, conventions, crossState]);

  // The filter bar/menu apply only to per-banco DATA views (not info pages or
  // the cross-banco perspectives, which have no single-banco filter surface).
  const vm = window.viewById ? window.viewById(view) : null;
  const banco = window.bancoById ? window.bancoById(database) : null;
  const isDataView = !infoPage && !(vm && vm.crossBanco) && !!banco;
  const displaySummary = isDataView ? withChips(summary, database, conventions) : summary;

  // The filter + conventions bars, passed DOWN to MainScreen as a slot instead of being
  // rendered here as siblings ABOVE it. Rendered above, they put two blocks of controls
  // ahead of the page's own <h1> — the ONLY heading on the page — so heading navigation
  // (a primary screen-reader mode) and the tab order both reached the controls before any
  // statement of which page you were on. MainScreen now places them directly under its
  // page-hero. The wiring/state stays HERE; MainScreen only decides placement. The render
  // conditions are unchanged, so the set of screens showing them is identical.
  const viewControls = (
    <>
      {isDataView && window.FilterTriggerBar && (
        <window.FilterTriggerBar
          summary={displaySummary}
          onOpen={() => setFilterOpen(true)}
          onExport={() =>
            window.exportActiveTableCSV &&
            window.exportActiveTableCSV({ view, database, summary, conventions })
          }
          live={banco.status === 'live'}
          banco={banco}
          view={view}
        />
      )}
      {/* Convenções métricas strip: the ONLY UI path to change currency ×
          correction × display units. It was imported for its window.* helpers
          but never rendered, so the scientific currency/correction column
          selection was unreachable except by hand-editing the URL (which then
          hit the F1.1 deadlock). onChange feeds setConventions → the useEffect
          bridge → dataStore.setConventions (the single {currency, correction}
          setter), which now re-triggers the snapshot load. Live data views only. */}
      {isDataView && banco.status === 'live' && window.MetricConventions && (
        <window.MetricConventions
          banco={banco}
          value={conventions || window.DEFAULT_CONVENTIONS}
          onChange={setConventions}
          families={window.familiesInBasket
            ? window.familiesInBasket(summary.basket, database)
            : undefined}
          expanded={metricsExpanded}
          onToggleExpanded={() => setMetricsExpanded((e) => !e)}
        />
      )}
    </>
  );

  return (
    <window.AppShell
      view={view}
      setView={setView}
      database={database}
      setDatabase={changeDatabase}
      infoPage={infoPage}
      setInfoPage={setInfoPage}
      summary={displaySummary}
      conventions={conventions}
      crossState={crossState}
      mode={mode}
      setMode={changeMode}
    >
      <DataGate database={database} infoPage={infoPage} view={view}>
        <ViewErrorBoundary resetKey={`${view}|${database}|${infoPage}`}>
          <window.MainScreen
            filters={summary}
            view={view}
            database={database}
            infoPage={infoPage}
            basket={summary.basket}
            conventions={conventions}
            setDatabase={changeDatabase}
            crossState={crossState}
            setCrossState={setCrossState}
            controls={viewControls}
          />
        </ViewErrorBoundary>
      </DataGate>

      {/* Mount only WHEN OPEN: the menu initializes its product set from
          dataStore.get(banco) at mount, so it must mount after the snapshot has
          loaded (else it captures the synthetic fallback codes → applies an empty
          basket). Opening after the view rendered guarantees real data. */}
      {filterOpen && window.FilterMenu && (
        <window.FilterMenu
          // Key on the banco so a banco switch remounts the menu with the new
          // banco's product/UF/município universe instead of reusing the prior
          // one's seeded state (the menu seeds once per mount). Robustness even
          // though the conditional mount above already gives a fresh menu per open.
          key={database}
          open
          banco={database}
          value={summary}
          onClose={() => setFilterOpen(false)}
          onApply={(s) => {
            setSummary(s);
            setFilterOpen(false);
          }}
        />
      )}
    </window.AppShell>
  );
}

// Reuse the root across HMR re-evaluations of this module (calling createRoot
// twice on the same container warns). In prod this simply runs once.
const _container = document.getElementById('root');
window.__embrapaRoot = window.__embrapaRoot || window.ReactDOM.createRoot(_container);
window.__embrapaRoot.render(
  <React.StrictMode>
    <Dashboard />
  </React.StrictMode>
);
