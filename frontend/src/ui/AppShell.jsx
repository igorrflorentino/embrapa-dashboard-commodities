// AppShell — institutional chrome: header band, sidebar, breadcrumb, footer tríade.
//
// Two-axis navigation:
//   • sidebar  → selects the data source ("Banco de dados") + info pages
//   • topnav   → selects the analytical view (perspective) of the active banco

// Restore the user's saved sidebar width BEFORE first paint (sets the
// --sidebar-w custom property the .body grid reads). Runs once at import.
try {
  const _savedSbW = localStorage.getItem('embrapa:sidebarW');
  if (_savedSbW) document.documentElement.style.setProperty('--sidebar-w', _savedSbW);
} catch { /* localStorage unavailable — keep the CSS default (260px) */ }

// a11y: make a non-<button> clickable element behave like a button for keyboard +
// screen-reader users. The sidebar items are styled <div>s (kept that way for the
// design-system layout), so spread this onto each to add role/tabindex + an
// Enter/Space key handler that mirrors the onClick — without changing the DOM/CSS.
function clickable(onActivate) {
  return {
    role: 'button',
    tabIndex: 0,
    onClick: onActivate,
    onKeyDown: (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onActivate();
      }
    },
  };
}

// Draggable handle on the sidebar's right edge: lets the researcher widen/narrow
// the sidebar within a sensible range (no fixed width). Persists to localStorage;
// double-click resets to the default. Drives the same --sidebar-w the grid reads.
const SIDEBAR_MIN_W = 200;
const SIDEBAR_MAX_W = 460;
const SIDEBAR_DEFAULT_W = '260px';
function SidebarResizer() {
  const beginResize = (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const root = document.documentElement;
    const startW = parseInt(getComputedStyle(root).getPropertyValue('--sidebar-w'), 10) || 260;
    document.body.classList.add('sb-resizing');
    const onMove = (ev) => {
      const w = Math.min(SIDEBAR_MAX_W, Math.max(SIDEBAR_MIN_W, startW + (ev.clientX - startX)));
      root.style.setProperty('--sidebar-w', w + 'px');
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.classList.remove('sb-resizing');
      try {
        localStorage.setItem('embrapa:sidebarW',
          getComputedStyle(document.documentElement).getPropertyValue('--sidebar-w').trim());
      } catch { /* ignore persistence failure */ }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };
  const reset = () => {
    document.documentElement.style.setProperty('--sidebar-w', SIDEBAR_DEFAULT_W);
    try { localStorage.setItem('embrapa:sidebarW', SIDEBAR_DEFAULT_W); } catch { /* ignore */ }
  };
  return (
    <div className="sidebar-resizer" role="separator" aria-orientation="vertical"
         title="Arraste para ajustar a largura · duplo clique para o padrão"
         onPointerDown={beginResize} onDoubleClick={reset} />
  );
}

function AppShell({
  children,
  view, setView,
  database, setDatabase,
  infoPage, setInfoPage,
  summary,
  conventions,
  crossState,
  mode = 'single', setMode,
}) {
  const [citeOpen, setCiteOpen] = React.useState(false);
  // Which reference detail level the modal shows. Defaults to 'query' — the level the
  // modal produced before there was a choice — so anyone who opens it and copies gets
  // what they got yesterday; the two shorter levels are opt-in.
  const [citeLevel, setCiteLevel] = React.useState('query');
  const [shared,   setShared]   = React.useState(false);
  const [navOpen,  setNavOpen]  = React.useState(false);
  const [sideNavOpen, setSideNavOpen] = React.useState(false); // mobile (≤768px) sidebar drawer
  const [reportOpen, setReportOpen] = React.useState(false);
  const [utilOpen, setUtilOpen] = React.useState(false); // mobile (≤768px) "⋯" overflow menu for the util actions
  // Optional prefill (view/category/message) for a CONTEXTUAL feedback open (e.g. the
  // Referências "report a value" action); null = the generic "Enviar feedback" button.
  const [reportPrefill, setReportPrefill] = React.useState(null);

  // The IAP-authenticated session identity, surfaced in the topbar so the researcher
  // sees WHO the dashboard attributes their edits to. Best-effort GET /api/me; null =
  // anonymous (local dev with no DEV_AUTHOR). Display-only — writes re-check server-side.
  const [sessionUser, setSessionUser] = React.useState(null);
  React.useEffect(() => {
    if (typeof fetch !== 'function') return undefined;
    let alive = true;
    fetch('/api/me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive && d) setSessionUser(d); })
      .catch(() => { /* anonymous — leave null */ });
    return () => { alive = false; };
  }, []);

  // a11y: Escape closes the citation modal (mirrors its backdrop click + Fechar).
  React.useEffect(() => {
    if (!citeOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setCiteOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [citeOpen]);

  // a11y: Escape closes the mobile sidebar drawer (mirrors its backdrop + nav-item tap).
  React.useEffect(() => {
    if (!sideNavOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setSideNavOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [sideNavOpen]);

  // a11y: Escape closes the mobile util overflow menu (mirrors its scrim tap).
  React.useEffect(() => {
    if (!utilOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setUtilOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [utilOpen]);

  const groups = window.VIEW_GROUPS || [];
  const activeView = window.viewById ? window.viewById(view) : null;
  const activeGroup = activeView?.group;

  const isMulti = mode === 'multi';
  // A view belongs to the multi-fonte mode iff it operates across bancos.
  const inMode = (v) => isMulti ? !!v.crossBanco : !v.crossBanco;
  // Topnav lists only the perspectives that belong to the active mode.
  const visibleGroups = groups
    .map(g => ({ ...g, views: g.views.filter(inMode) }))
    .filter(g => g.views.length);
  // Which bancos are "in play" for the active multi-fonte perspective —
  // the picker view reflects the chosen series; the analytical views
  // declare fixed `sources`. The sidebar uses this as an indicator.
  const crossSeries = (crossState && crossState.series) || [];
  const onCrossPicker = activeView?.id === 'cross_source';
  const includedBancos = new Set(
    onCrossPicker ? crossSeries.map(s => s.b) : (activeView?.sources || [])
  );
  const seriesCountByBanco = onCrossPicker
    ? crossSeries.reduce((m, s) => { m[s.b] = (m[s.b] || 0) + 1; return m; }, {})
    : {};

  const bancos = window.visibleBancos ? window.visibleBancos() : (window.BANCOS || []);
  const bancoMeta = window.bancoById ? window.bancoById(database) : null;

  const pickView = (id) => {
    setView(id);
    if (setInfoPage) setInfoPage(null);
    setNavOpen(false);
  };

  const onBanco = (id) => {
    setDatabase(id);
    if (setInfoPage) setInfoPage(null);
  };
  const onInfo = (id) => {
    if (setInfoPage) setInfoPage(id);
  };

  const onInfoPage = !!infoPage;

  // ── Citation + share helpers ─────────────────────────────────────────
  const VIEW_LABEL = window.viewLabel
    ? Object.fromEntries((window.VIEW_GROUPS || []).flatMap(g => g.views.map(v => [v.id, v.label])))
    : {};
  const activeBanco = (window.bancoById && window.bancoById(database)) || null;
  const bancoCiteLabel = activeBanco
    ? `${activeBanco.short} · ${activeBanco.label.replace(/^[^·]+·\s*/, '')}`
    : database;
  const today = new Date();
  // ABNT NBR 6023:2025 access date: "13 jun. 2026" (abbreviated month + period;
  // "maio" is NOT abbreviated). toLocaleDateString's "13 de junho de 2026" is
  // non-compliant, so build it explicitly.
  const _mesAbnt = ['jan.', 'fev.', 'mar.', 'abr.', 'maio', 'jun.', 'jul.', 'ago.', 'set.', 'out.', 'nov.', 'dez.'];
  const accessedOn = `${today.getDate()} ${_mesAbnt[today.getMonth()]} ${today.getFullYear()}`;
  // Editora year — derive from the current date so the reference never rots.
  const editoraYear = today.getFullYear();
  // Recorte temporal: the ACTIVE banco's LIVE coverage \u2014 its snapshot overviewTS
  // span first (window.dataStore.get), then the /api/source-meta coverage
  // (meta().coverage), then '\u2014'. NEVER window.OVERVIEW_TS, which is the synthetic
  // seed frozen identically for every banco (audit #23).
  const _ovTs = (window.dataStore && window.dataStore.get && window.dataStore.get(database)?.overviewTS) || [];
  const _cov = (window.dataStore && window.dataStore.meta && window.dataStore.meta(database)?.coverage) || null;
  const _yStart = _ovTs[0]?.y ?? _cov?.yearStart ?? '\u2014';
  const _yEnd   = _ovTs[_ovTs.length - 1]?.y ?? _cov?.yearEnd ?? '\u2014';
  const period = summary && (summary.startDate || summary.endDate)
    ? `${String(summary.startDate || _yStart).slice(0,4)}\u2013${String(summary.endDate || _yEnd).slice(0,4)}`
    : `${_yStart}\u2013${_yEnd}`;
  const convLabel = conventions
    ? `${conventions.currency} \u00b7 ${conventions.correction} \u00b7 ${conventions.units?.mass} \u00b7 ${conventions.units?.volume}`
    : 'BRL \u00b7 IPCA \u00b7 t \u00b7 m\u00b3';

  const activeView2 = window.viewById ? window.viewById(view) : null;
  const isCrossView = !!(activeView2 && activeView2.crossBanco);

  // Human label for the cross-source selection (used in citation + chips).
  const crossLabel = () => {
    const ser = (crossState && crossState.series) || [];
    const parts = ser.map(r => {
      const b = window.bancoById ? window.bancoById(r.b) : null;
      const m = window.metricById ? window.metricById(r.b, r.m) : null;
      return b && m ? `${m.label} (${b.short})` : `${r.b}:${r.m}`;
    });
    return parts.join(' × ');
  };
  // The analytical cross perspectives have fixed sources; only the picker
  // view ('cross_source') is described by the chosen series.
  const isPickerCite = activeView2?.id === 'cross_source';
  const crossSourcesLabel = (activeView2?.sources || [])
    .map(id => window.bancoById ? window.bancoById(id)?.short : id).filter(Boolean).join(' · ');

  // Permalink that reproduces the EXACT panel state \u2014 the ABNT "Dispon\u00edvel em:".
  // Same codec as onShare (urlState.js); extracted so the citation and the Share
  // button can't drift. Returns null before the codec has loaded (degrade clean).
  const buildPermalink = () => {
    if (!window.urlEncodeState || !window.buildUrlState) return null;
    // Same encoder as the address-bar write-back (main.jsx) — one source of truth for
    // the wire format, so the shared/ABNT URL and a plain reload encode the SAME state
    // identically (previously this permalink serialized the sub-UF/município keys but
    // the write-back did not → the two "permalinks" disagreed; H1). Município cap +
    // the value-range omission both live in buildUrlState now.
    const state = window.buildUrlState({
      view, database, infoPage, conventions, summary, crossState, isCross: isCrossView,
    });
    return `${location.origin}${location.pathname}?${window.urlEncodeState(state)}`;
  };
  const _permalink = buildPermalink();
  const dispoStr = _permalink ? `Dispon\u00edvel em: ${_permalink}. ` : '';

  // Data-scope fragments for the single-banco cite \u2014 so the reference names EXACTLY
  // what is on screen (products, UFs, quality, value range) and never over-claims a
  // filtered panel as if it were the full dataset. The chip strings are already
  // computed by the shell (withChips); restricted-only dims (quality/value) are
  // included only when an actual filter is set.
  const scopeBits = [];
  if (summary?.products) scopeBits.push(`Produtos: ${summary.products}`);
  if (summary?.geo) scopeBits.push(`UFs: ${summary.geo}`);
  if (summary?.flags && summary.flags.length && summary.quality) scopeBits.push(`Qualidade: ${summary.quality}`);
  if ((summary?.valueMin != null || summary?.valueMax != null) && summary.valueRange) scopeBits.push(`Faixa de valor: ${summary.valueRange}`);
  const scopeStr = scopeBits.length ? `${scopeBits.join('. ')}. ` : '';

  // ── Reference detail levels (ABNT NBR 6023:2025) ──────────────────────────
  // The reference used to be one fixed string that concatenated the banco AND every
  // active filter. That is the right citation for "I analysed exactly this slice", and
  // the wrong one for "I used this tool" — a researcher citing the dashboard in a
  // methods section does not want the reader's eye to travel through a UF list.
  //
  //   'tool'   the dashboard itself: no banco, no filters
  //   'banco'  the dashboard and the data source it was read from
  //   'query'  the exact consulted slice — the previous behaviour, unchanged
  //
  // Shared head/tail so the three levels can only differ where they are meant to.
  const CITE_AUTHOR = 'EMPRESA BRASILEIRA DE PESQUISA AGROPECU\u00c1RIA (EMBRAPA).';
  const CITE_TITLE = 'Dashboard de an\u00e1lise hist\u00f3rica de produtos agr\u00edcolas';
  const citeTail = `Bras\u00edlia, DF: Embrapa, ${editoraYear}. ${dispoStr}Acesso em: ${accessedOn}.`;
  // The data source at the 'banco' level. A cross perspective has no single banco, so
  // it names the sources it actually crosses — omitting them would make the middle
  // level identical to the general one and quietly drop what the panel is built on.
  const citeSourceName = isCrossView
    ? (crossSourcesLabel || (isPickerCite ? crossLabel() : ''))
    : (activeBanco?.short || database);

  const citation = isCrossView
    ? (isPickerCite
        ? `EMPRESA BRASILEIRA DE PESQUISA AGROPECU\u00c1RIA (EMBRAPA). ` +
          `Dashboard de An\u00e1lise Hist\u00f3rica de Produtos Agr\u00edcolas \u2014 Cruzamento entre fontes \u2014 ` +
          `${crossLabel()}. Recorte: ${period}. Conven\u00e7\u00f5es m\u00e9tricas: ${convLabel}. ` +
          `Bras\u00edlia, DF: Embrapa, ${editoraYear}. ${dispoStr}Acesso em: ${accessedOn}.`
        : `EMPRESA BRASILEIRA DE PESQUISA AGROPECU\u00c1RIA (EMBRAPA). ` +
          `Dashboard de An\u00e1lise Hist\u00f3rica de Produtos Agr\u00edcolas \u2014 An\u00e1lise cruzada \u2014 ` +
          `${VIEW_LABEL[view] || view}${crossSourcesLabel ? ` (fontes: ${crossSourcesLabel})` : ''}. ` +
          `Recorte: ${period}. Conven\u00e7\u00f5es m\u00e9tricas: ${convLabel}. ` +
          `Bras\u00edlia, DF: Embrapa, ${editoraYear}. ${dispoStr}Acesso em: ${accessedOn}.`)
    : `EMPRESA BRASILEIRA DE PESQUISA AGROPECU\u00c1RIA (EMBRAPA). ` +
      `Dashboard de An\u00e1lise Hist\u00f3rica de Produtos Agr\u00edcolas \u2014 ` +
      `${bancoCiteLabel} \u2014 ${VIEW_LABEL[view] || view}. ` +
      `Recorte: ${period}. ${scopeStr}Conven\u00e7\u00f5es m\u00e9tricas: ${convLabel}. ` +
      `Bras\u00edlia, DF: Embrapa, ${editoraYear}. ${dispoStr}Acesso em: ${accessedOn}.`;

  const citationTool = `${CITE_AUTHOR} ${CITE_TITLE}. ${citeTail}`;
  const citationBanco = citeSourceName
    ? `${CITE_AUTHOR} ${CITE_TITLE}: ${citeSourceName}. ${citeTail}`
    : citationTool;
  const CITE_LEVELS = [
    { id: 'tool', label: 'Ferramenta geral', text: citationTool,
      hint: 'Cita o dashboard como ferramenta \u2014 sem banco e sem filtros.' },
    { id: 'banco', label: 'Por banco de dados', text: citationBanco,
      hint: 'Acrescenta a fonte de dados consultada.' },
    { id: 'query', label: 'Consulta detalhada', text: citation,
      hint: 'Descreve o recorte exato: banco, per\u00edodo, produtos, UFs e conven\u00e7\u00f5es.' },
  ];
  const activeCite = CITE_LEVELS.find((l) => l.id === citeLevel) || CITE_LEVELS[2];

  // ABNT NBR 10520:2023 in-text citation (chamada autor-data) \u2014 what you insert in
  // the running text, complementary to the 6023 reference above (10520 = the call,
  // 6023 = the full entry).
  //
  // The entity is rendered in ALL CAPS by project decision. This file previously
  // carried the opposite ("(Embrapa, ...)"), justified by 10520:2023's initial-capital
  // rule for authors; the caps form was requested for consistency with the reference
  // head and with Embrapa's own house style, and is what ships.
  const inTextCite = `(EMBRAPA, ${editoraYear})`;

  const onCite = () => setCiteOpen(true);
  const onReport = () => { setReportPrefill(null); setReportOpen(true); };
  // Expose a global so any view can open the feedback dialog PREFILLED (the Referências
  // "report a value" loop). The prefill merges into the modal's context, where message/
  // category/view override the auto-captured ones.
  React.useEffect(() => {
    window.openFeedback = (prefill) => { setReportPrefill(prefill || null); setReportOpen(true); };
    return () => { if (window.openFeedback) { delete window.openFeedback; } };
  }, []);
  const onShare = async () => {
    // Reuse the SAME permalink builder the citation uses (buildPermalink, above) —
    // one codec path, so the Share URL and the cite's "Disponível em:" can't drift.
    // Degrades to a no-op before urlState.js has loaded (buildPermalink → null).
    const url = buildPermalink();
    if (!url) return;
    try { await navigator.clipboard.writeText(url); } catch {}
    setShared(true);
    setTimeout(() => setShared(false), 1800);
  };
  const onCopyCite = async () => {
    // The SELECTED level, not the detailed one: the button under a chosen radio has to
    // copy what the box above it shows.
    try { await navigator.clipboard.writeText(activeCite.text); } catch {}
  };
  const onCopyInText = async () => {
    try { await navigator.clipboard.writeText(inTextCite); } catch {}
  };

  // The single/multi mode toggle — lives in the sidebar at every width (it belongs with
  // data selection: it decides whether the list below is one banco or the cross-source
  // set). It used to sit in the topbar on desktop; moved to the sidebar for a calmer top
  // bar, matching where it already sat on mobile.
  const modeButtons = (
    <>
      <button role="tab" aria-selected={!isMulti}
        className={'mode-opt ' + (!isMulti ? 'on' : '')}
        onClick={() => setMode && setMode('single')}
        title="Analisar um banco de dados por vez">
        <window.Icon name="database" size={15}/>
        <span>Banco único</span>
      </button>
      <button role="tab" aria-selected={isMulti}
        className={'mode-opt ' + (isMulti ? 'on' : '')}
        onClick={() => setMode && setMode('multi')}
        title="Cruzar séries de bancos diferentes no mesmo eixo de tempo">
        <window.Icon name="hub" size={15}/>
        <span>Multi-fonte</span>
      </button>
    </>
  );

  return (
    <div className="shell">
      <header className="topbar">
        <button className="topbar-hamburger" type="button" aria-label="Abrir/fechar menu lateral"
          aria-expanded={sideNavOpen} onClick={() => setSideNavOpen((o) => !o)}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <button className="brand brand-btn" onClick={() => { if (setInfoPage) setInfoPage('about'); }} title="Voltar para Sobre o dashboard">
          <img src="assets/logo-embrapa-white-cropped.png" alt="Embrapa" className="brand-logo"/>
        </button>
        <div className="sep"></div>
        <div className="product-name">Análise histórica de produtos agrícolas</div>

        <nav className="topnav">
          <button
            className={'topnav-trigger ' + (navOpen ? 'open' : '') + (onInfoPage ? '' : ' has-active')}
            onClick={() => setNavOpen(o => !o)}
            aria-haspopup="true"
            aria-expanded={navOpen}>
            <span className="topnav-trigger-l">
              {onInfoPage ? (
                <span className="topnav-trigger-view">Selecionar perspectiva</span>
              ) : (
                <>
                  <span className="topnav-trigger-grp">{activeGroup?.label || 'Perspectiva'}</span>
                  <span className="topnav-trigger-view">{activeView?.label || 'Visão geral'}</span>
                </>
              )}
            </span>
            <window.Icon name="expand_more" size={18}/>
          </button>

          {navOpen && (
            <>
              <div className="topnav-scrim" onClick={() => setNavOpen(false)}></div>
              <div className={'topnav-menu' + (isMulti ? ' narrow' : '')} role="menu">
                <div className="topnav-menu-bar">
                  <span className="topnav-menu-scope">
                    {isMulti
                      ? <>Perspectivas <strong>multi-fonte</strong> · entre bancos</>
                      : <>Perspectivas para <strong>{bancoMeta ? bancoMeta.short : 'banco'}</strong></>}
                  </span>
                  <span className="topnav-menu-legend">
                    <span className="tnl-item"><span className="tnl-dot ok"></span>Disponível</span>
                    {!isMulti && <span className="tnl-item"><span className="tnl-dot soon"></span>Em breve</span>}
                    {!isMulti && <span className="tnl-item"><span className="tnl-dot na"></span>Não se aplica</span>}
                    {isMulti && <span className="tnl-item"><span className="tnl-dot na"></span>Indisponível</span>}
                  </span>
                </div>
                <div className="topnav-menu-grid">
                  {visibleGroups.map(g => (
                    <div key={g.id} className="topnav-grp">
                      <div className="topnav-grp-head">
                        <span className="topnav-grp-label">{g.label}</span>
                        <span className="topnav-grp-hint">{g.hint}</span>
                      </div>
                      {g.views.map(v => {
                        // Single-banco views gate on requires×provides (viewAppliesTo);
                        // cross perspectives on crossViewApplies (data-blocked / source-
                        // availability / ≥2 comparable series) — see views.js.
                        const isCrossOpt = !!v.crossBanco;
                        const cross = isCrossOpt && window.crossViewApplies ? window.crossViewApplies(v.id) : null;
                        const compat = !isCrossOpt && window.viewAppliesTo
                          ? window.viewAppliesTo(v.id, database)
                          : { applies: true, missing: [] };
                        const applies = isCrossOpt ? (cross ? cross.usable : true) : compat.applies;
                        const supporters = (!isCrossOpt && !applies && window.bancosSupporting)
                          ? window.bancosSupporting(v.id)
                          : [];
                        const state = !applies
                          ? (isCrossOpt && cross ? cross.state : 'na')
                          : (v.status === 'soon' ? 'soon' : 'ok');
                        // 'preview' (data-blocked) reuses the 'na' grey visual; the badge text
                        // is what differs ('Demonstração' vs 'Indisponível'/'Não se aplica').
                        const visualState = state === 'preview' ? 'na' : state;
                        // Cross perspectives that aren't usable are DISABLED (non-clickable) —
                        // the user can't pick what they can't use. Single-mode 'na' stays
                        // clickable (it routes to an explainer naming the supporting bancos).
                        const disabled = isCrossOpt && !applies;
                        const tooltip = isCrossOpt
                          ? (applies ? v.desc : cross.reason)
                          : (!applies ? `Requer ${window.missingCapsLabel(compat.missing)} — não disponível em ${bancoMeta?.short || 'este banco'}` : v.desc);
                        return (
                          <button
                            key={v.id}
                            className={'topnav-opt state-' + visualState + (!onInfoPage && view === v.id ? ' active' : '')}
                            disabled={disabled}
                            onClick={() => { if (!disabled) pickView(v.id); }}
                            role="menuitem"
                            title={tooltip}>
                            <span className="topnav-opt-top">
                              <span className={'topnav-opt-dot ' + visualState}></span>
                              <span className="topnav-opt-label">{v.label}</span>
                              {v.crossBanco && <span className="topnav-opt-tag cross">multi-fonte</span>}
                              {state === 'soon'    && <span className="topnav-opt-tag soon">Em breve</span>}
                              {state === 'preview' && <span className="topnav-opt-tag na">Demonstração</span>}
                              {state === 'na'      && <span className="topnav-opt-tag na">{isCrossOpt ? 'Indisponível' : 'Não se aplica'}</span>}
                            </span>
                            {!isCrossOpt && !applies && supporters.length > 0 && (
                              <span className="topnav-opt-supporters">
                                disponível em {supporters.map(b => b.short).join(' · ')}
                              </span>
                            )}
                            {isCrossOpt && !applies && cross.reason && (
                              <span className="topnav-opt-supporters">{cross.reason}</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </nav>

        <div className="util">
          <button className="util-action" onClick={onCite} title="Citar este painel no estado atual">
            <window.Icon name="format_quote" size={16}/>
            <span>Citar painel</span>
          </button>
          <button className="util-action" onClick={onShare} title="Copiar URL com o estado atual (filtros, view, convenções)">
            <window.Icon name="link" size={16}/>
            <span>{shared ? 'URL copiada' : 'Compartilhar'}</span>
          </button>
          <button className="util-action" onClick={onReport} title="Relate um problema, tire uma dúvida ou envie uma sugestão">
            <window.Icon name="feedback" size={16}/>
            <span>Enviar feedback</span>
          </button>

          {/* Mobile (≤768px): the three actions above are hidden and collapse into this
              single "⋯" overflow menu, so the bar isn't crammed (FINDING: phone topbar). */}
          <div className="util-overflow">
            <button className="util-more" type="button" aria-haspopup="true" aria-expanded={utilOpen}
              aria-label="Mais ações" onClick={() => setUtilOpen((o) => !o)}>
              <window.Icon name="more_vert" size={20}/>
            </button>
            {utilOpen && (
              <>
                <div className="util-scrim" onClick={() => setUtilOpen(false)}></div>
                <div className="util-menu" role="menu">
                  <button role="menuitem" className="util-menu-item" onClick={() => { setUtilOpen(false); onCite(); }}>
                    <window.Icon name="format_quote" size={18}/><span>Citar painel</span>
                  </button>
                  <button role="menuitem" className="util-menu-item" onClick={() => { setUtilOpen(false); onShare(); }}>
                    <window.Icon name="link" size={18}/><span>{shared ? 'URL copiada' : 'Compartilhar'}</span>
                  </button>
                  <button role="menuitem" className="util-menu-item" onClick={() => { setUtilOpen(false); onReport(); }}>
                    <window.Icon name="feedback" size={18}/><span>Enviar feedback</span>
                  </button>
                </div>
              </>
            )}
          </div>

        </div>
      </header>

      <div className={'body' + (sideNavOpen ? ' nav-open' : '')}>
        {sideNavOpen && (
          <div className="sidebar-backdrop" onClick={() => setSideNavOpen(false)} aria-hidden="true" />
        )}
        <aside className="sidebar" onClick={(e) => { if (e.target.closest('.side-item')) setSideNavOpen(false); }}>
          {/* The single/multi mode toggle — it belongs with data selection (it decides
              whether the list below is one banco or the cross-source set). Shown at every
              width; on mobile it sits at the top of the drawer. */}
          <div className="side-mode-switch" role="tablist" aria-label="Modo de análise">{modeButtons}</div>
          <div className="side-section">{isMulti ? 'Fontes no cruzamento' : 'Banco de dados'}</div>
          {isMulti ? (
            <>
              <div className="side-hint">
                {onCrossPicker
                  ? <>Reflete as séries montadas no painel. Edite as fontes em <strong>Montagem do cruzamento</strong>.</>
                  : <>Fontes combinadas por esta perspectiva.</>}
              </div>
              <div className="side-srclist" role="list">
                {bancos.map(b => {
                  const incl = includedBancos.has(b.id);
                  return (
                    <div key={b.id} role="listitem"
                         className={'side-src ' + (incl ? 'incl' : 'excl')}
                         title={incl
                           ? `${seriesCountByBanco[b.id] || ''} ${b.short} no cruzamento`.trim()
                           : `${b.short} fora do cruzamento atual`}>
                      <span className="side-src-dot"></span>
                      <span className="side-src-name">{b.short}</span>
                      {/* Included: show the series-count (or "incluída") badge. The maturity tag
                          ALWAYS renders after it, so a selected banco never hides its maturity —
                          both margin-left:auto, so the count absorbs the free space and the
                          maturity tag stays in the same far-right column for every row. */}
                      {incl && (seriesCountByBanco[b.id]
                        ? <span className="side-src-count tnum" title={`${seriesCountByBanco[b.id]} série(s)`}>{seriesCountByBanco[b.id]}</span>
                        : <span className="side-src-in">incluída</span>)}
                      <window.MaturityTag banco={b} size="sm" />
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            bancos.map(b => {
              const active = database === b.id;
              return (
              <div key={b.id}
                   className={'side-item ' + (active ? (onInfoPage ? 'selected' : 'active') : '')}
                   {...clickable(() => onBanco(b.id))}
                   title={b.label}>
                <window.UsageDot active={active} />
                <span className="side-item-l">{b.short}</span>
                <window.MaturityTag banco={b} size="sm" />
              </div>
              );
            })
          )}

          {/* LIVE: Curadoria — the researcher-editable commodity catalog (what enters/exits
              the dashboard). Backend-gated by the research_inputs.catalog_editors allowlist; the
              orphan→Descontinuado lifecycle + human-gated purge live server-side. This is the only
              UI entry point for the live catalog editor, so keep it OUT of the FROZEN block below. */}
          <div className="side-section">Curadoria</div>
          <div className={'side-item ' + (infoPage === 'cadastro_produtos' ? 'active' : '')}
               {...clickable(() => onInfo('cadastro_produtos'))}>
            <window.Icon name="inventory_2"/>Cadastro de produtos
          </div>

          {/* Engenharia de Atributos — the per-code industrialization editor (gated by the
              `enable_curation` dbt var); accepts ?ip=enrich_industrial (?ip=curation is the
              legacy alias), so any stale deep link resolves rather than 404s.
              FROZEN (2026-07): the "Tipo de Mercado" (customs × flow market-nature) matrix
              is hidden — the totals-only COMTRADE base (customsCode=C00) carries no
              customs-procedure detail to classify. Scaffold (route, component, store) kept;
              a stale ?ip=enrich_market degrades to the generic "em preparação" fallback.
              See the frozen-feature memo. */}
          <div className="side-section">Engenharia de atributos</div>
          <div className={'side-item ' + (infoPage === 'enrich_industrial' || infoPage === 'curation' ? 'active' : '')}
               {...clickable(() => onInfo('enrich_industrial'))}>
            <window.Icon name="factory"/>Nível de industrialização
          </div>
          {/* FROZEN — see the section comment above.
          <div className={'side-item ' + (infoPage === 'enrich_market' ? 'active' : '')}
               {...clickable(() => onInfo('enrich_market'))}>
            <window.Icon name="storefront"/>Tipo de Mercado
          </div>
          */}

          <div className="side-section">Informações</div>
          <div className={'side-item ' + (infoPage === 'about' ? 'active' : '')}
               {...clickable(() => onInfo('about'))}>
            <window.Icon name="info"/>Sobre o dashboard
          </div>
          <div className={'side-item ' + (infoPage === 'glossary' ? 'active' : '')}
               {...clickable(() => onInfo('glossary'))}>
            <window.Icon name="menu_book"/>Glossário global
          </div>
          <div className={'side-item ' + (infoPage === 'referencias' ? 'active' : '')}
               {...clickable(() => onInfo('referencias'))}>
            <window.Icon name="table_chart"/>Tabelas de referência
          </div>
          <div className={'side-item ' + (infoPage === 'health' ? 'active' : '')}
               {...clickable(() => onInfo('health'))}>
            <window.Icon name="pulse"/>Saúde do sistema
          </div>

          {/* Session identity — the IAP-authenticated user. Non-interactive indicator,
              anchored below Informações so the researcher always sees who the dashboard
              considers the current user (edits are attributed to this email). */}
          {sessionUser && sessionUser.email && (
            <div className="side-user" title={`Sessão autenticada via IAP como ${sessionUser.email}`}>
              <window.Icon name="person" size={16}/>
              <span className="side-user-email">{sessionUser.email}</span>
            </div>
          )}
          <SidebarResizer />
        </aside>

        <main className="content">
          {children}
        </main>
      </div>

      {citeOpen && (
        <div className="cite-backdrop" onClick={() => setCiteOpen(false)}>
          <div className="cite-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="cite-title">
            <header className="cite-head">
              <div>
                <div className="overline">Citação acadêmica</div>
                <h2 id="cite-title">Citar painel</h2>
                <p className="caption">
                  Do painel exatamente como exibido — banco, perspectiva, recorte temporal,
                  produtos, UFs, filtros e convenções métricas — com o link permanente que
                  reproduz a seleção. A <strong>citação no texto</strong> segue a ABNT NBR
                  10520:2023; a <strong>referência</strong> completa segue a ABNT NBR 6023:2025.
                </p>
              </div>
              <button className="fm-close" onClick={() => setCiteOpen(false)} aria-label="Fechar">
                <window.Icon name="close" size={18}/>
              </button>
            </header>
            <div className="cite-body">
              <div className="cite-block">
                <div className="cite-block-head">
                  <span className="overline">Citação no texto · ABNT NBR 10520:2023</span>
                  <button className="cite-copy-mini" onClick={onCopyInText} aria-label="Copiar citação no texto">
                    <window.Icon name="content_copy" size={13}/> Copiar
                  </button>
                </div>
                <pre className="cite-text cite-text-inline">{inTextCite}</pre>
                <p className="caption cite-hint">Formato autor-data, para inserir no corpo do texto.</p>
              </div>
              <div className="cite-block">
                <div className="cite-block-head">
                  <span className="overline">Referência · ABNT NBR 6023:2025</span>
                  <button className="cite-copy-mini" onClick={onCopyCite} aria-label="Copiar referência">
                    <window.Icon name="content_copy" size={13}/> Copiar
                  </button>
                </div>
                {/* Detail level. A radiogroup rather than a segmented control: these are
                    three readings of the same reference, and a radio says "pick one of
                    these" where a toggle would suggest a view switch. */}
                <div className="cite-levels" role="radiogroup" aria-label="Nível de detalhe da referência">
                  {CITE_LEVELS.map((lv) => (
                    <label key={lv.id} className={'cite-level ' + (citeLevel === lv.id ? 'on' : '')}>
                      <input
                        type="radio"
                        name="cite-level"
                        value={lv.id}
                        checked={citeLevel === lv.id}
                        onChange={() => setCiteLevel(lv.id)}
                      />
                      <span>{lv.label}</span>
                    </label>
                  ))}
                </div>
                <pre className="cite-text">{activeCite.text}</pre>
                <p className="caption cite-hint">{activeCite.hint} Para a lista de referências ao final do trabalho.</p>
              </div>
              <div className="cite-actions">
                <button className="btn-secondary" onClick={() => setCiteOpen(false)}>Fechar</button>
                <button className="btn-primary" onClick={onCopyCite}>
                  <window.Icon name="content_copy" size={14}/> Copiar referência
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <window.FeedbackModal
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        context={{ url: buildPermalink(), view, banco: database, ...(reportPrefill || {}) }}
      />

      <footer className="footer">
        <img src="assets/triade-horizontal-black.png" alt="Embrapa · Ministério da Agricultura e Pecuária · Governo do Brasil" className="triade"/>
        <div className="foot-meta">
          <div>© Empresa Brasileira de Pesquisa Agropecuária</div>
          <div className="caption">Ministério da Agricultura e Pecuária</div>
          <div className="caption"><a href="https://www.embrapa.br" target="_blank" rel="noopener noreferrer">www.embrapa.br</a> &nbsp;·&nbsp; <a href="https://www.embrapa.br/fale-conosco/sac" target="_blank" rel="noopener noreferrer">Serviço de Atendimento ao Cidadão (SAC)</a></div>
        </div>
        {/* Dev-team credit — distinct from the institutional Embrapa block above: who
            builds/maintains THIS dashboard (as opposed to the research institution), so a
            researcher hitting a bug or a data question can reach the maintainer directly
            without digging through "Sobre o dashboard". Mirrors the same contact email
            already shown there (ViewAbout's "Contato técnico"), kept in sync manually. */}
        <div className="foot-meta foot-meta-team">
          <div>Desenvolvimento e manutenção</div>
          <div className="caption">Equipe de engenharia de dados do dashboard</div>
          <div className="caption">
            <a href="mailto:igor.lopes@embrapa.br">Contato técnico</a>
            &nbsp;·&nbsp;
            <a href="https://github.com/igorrflorentino/embrapa-dashboard-produtos-agricolas" target="_blank" rel="noopener noreferrer">Código-fonte no GitHub</a>
          </div>
        </div>
      </footer>
    </div>
  );
}

window.AppShell = AppShell;
