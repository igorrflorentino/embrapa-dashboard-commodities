// FilterMenu.jsx — v3
// Expanded filter modal adapted from the updated sketch to the
// Embrapa Commodities Design System.
//
// Sections (live banco): products, period & value range, geography,
// quality, + a read-only list of the banco's remaining declared dimensions.
//   • Inline search input inside every multi-select header
//   • "Geografia" section is BANCO-ADAPTIVE: the cascade depth follows the
//     banco's geoLevel — Nações → Regiões → Estados → Municípios for
//     município-level bancos, dropping the Municípios column for UF-level
//     bancos, and the whole section is hidden when the banco has no geo.
//   • Product label, value-filter currency symbol/column and the value
//     shortcuts all come from the active banco (schema + baseCurrency), so
//     COMEX shows "Produto · NCM/SH" + US$, Comtrade "Produto · HS6", etc.
//   • The modal is capped to the viewport as a flex column — fixed header +
//     scrolling body (.fm-body) + pinned footer — so "Aplicar" stays in view;
//     long product lists get a roomy, viewport-responsive height (.fm-grid-scroll)
//   • Each multi-select has its own bulk actions row
//
// Selection cascades downward: unchecking "Norte" PRUNES its 7 states
// (and their municipalities) from the selection — so the applied filter
// always matches the visible cascade; checking "Pará" makes Pará's
// municipalities the only ones eligible in Municípios. Re-checking a
// parent leaves its children UNSELECTED (re-pick them, or use
// "Selecionar tudo") — enforced by the cascade-pruning effects below.

const { useState, useMemo } = React;

// --- Domain data ---------------------------------------------------
// The product list is now resolved PER BANCO inside the component (see `PRODS`),
// from the active banco's snapshot — so there is no module-level PEVS copy.

// Quality flags derive from the single source of truth (window.QUALITY_FLAGS
// in data.js) so the labels shown here, in the chip bar and in the Qualidade
// view never drift apart. The raw flag token (data_quality_flag) is still
// surfaced verbatim alongside each pt-BR label.
// Period bounds derive from the ACTIVE banco's live time series — resolved
// PER BANCO inside the component (see `yearBounds`/`quickRanges` below), never
// from a module-level snapshot read at import time (which froze to whichever
// banco loaded first and to the synthetic 1986/2024 fallback). Switching banco
// now shifts the date bounds + quick-ranges. The pair below is only the
// last-resort fallback used when no snapshot exists yet for the banco.
const YEAR_START_FALLBACK = 1986;
const YEAR_END_FALLBACK   = 2024;

// ISO-A3 of the COMTRADE "home" reporter (Brazil) — the reporter picker's default single
// selection. Mirrors settings.comtrade_brazil_iso on the backend (absent reporters ⇒ Brazil).
const BRAZIL_ISO = 'BRA';

// Compute the [start, end] year span from a banco snapshot's overview series,
// falling back to the synthetic span when the snapshot is absent/empty.
function bancoYearBounds(snap) {
  const ts = (snap && snap.overviewTS) || null;
  if (!ts || ts.length === 0) return [YEAR_START_FALLBACK, YEAR_END_FALLBACK];
  return [ts[0]?.y || YEAR_START_FALLBACK, ts[ts.length - 1]?.y || YEAR_END_FALLBACK];
}

// Derive the quick-range presets from a [start, end] span (never hardcode the
// span) so changing the source dataset shifts the chips + date bounds with it.
function buildQuickRanges(yearStart, yearEnd) {
  return [
    { id: 'all',  label: 'Tudo',    start: `${yearStart}-01`,   end: `${yearEnd}-12` },
    { id: '30a',  label: '30 anos', start: `${yearEnd - 29}-01`, end: `${yearEnd}-12` },
    { id: '20a',  label: '20 anos', start: `${yearEnd - 19}-01`, end: `${yearEnd}-12` },
    { id: '10a',  label: '10 anos', start: `${yearEnd - 9}-01`,  end: `${yearEnd}-12` },
    { id: '5a',   label: '5 anos',  start: `${yearEnd - 4}-01`,  end: `${yearEnd}-12` },
  ];
}

const QUALITY_CHIP = {
  OK: 'ok', MISSING_VALUE: 'warn', MISSING_QUANTITY: 'info',
  MISSING_WEIGHT: 'warn', INCOMPLETE: 'muted',
};
const QUALITY = (window.QUALITY_FLAGS || []).map(f => ({
  flag: f.id,
  label: f.label,
  chip: QUALITY_CHIP[f.id] || 'muted',
}));
const qualityLabelOf = (id) => {
  const f = QUALITY.find(x => x.flag === id);
  return f ? f.label : id;
};

// Nations — the geo-cascade is consumed ONLY by domestic datasets (ibge_pevs,
// ibge_pam, sefaz_nf): PEVS/PAM are Brazilian *production* (Gold carries only
// uf/municipio — no destination country) and NFe is internal inter-UF flow. So
// the only real nação is Brasil. The earlier list also carried 11 foreign
// "export destinations" (China, EUA, …) — a prototype fabrication that mapped to
// NO column in any geo-cascade banco: adding one was a silent no-op, selecting
// only one zeroed the whole map. International partners are a REAL dimension only
// for COMEX/COMTRADE, which expose them via their own `pais`/`partner`
// multi-search dims, not this cascade. Kept as a list so the cascade rendering
// and "all selected" checks stay unchanged.
const NATIONS = [
  { iso: 'BR', name: 'Brasil', role: 'produtor' },
];

// Brazil's 5 macro-regions. Linked to BR nation.
const FM_REGIONS = [
  { id: 'N',  name: 'Norte',        nation: 'BR' },
  { id: 'NE', name: 'Nordeste',     nation: 'BR' },
  { id: 'CO', name: 'Centro-Oeste', nation: 'BR' },
  { id: 'SE', name: 'Sudeste',      nation: 'BR' },
  { id: 'S',  name: 'Sul',          nation: 'BR' },
];

// Brazil's 27 states (UFs), linked to their region.
const STATES = [
  { uf: 'AC', name: 'Acre',                region: 'N'  },
  { uf: 'AP', name: 'Amapá',               region: 'N'  },
  { uf: 'AM', name: 'Amazonas',            region: 'N'  },
  { uf: 'PA', name: 'Pará',                region: 'N'  },
  { uf: 'RO', name: 'Rondônia',            region: 'N'  },
  { uf: 'RR', name: 'Roraima',             region: 'N'  },
  { uf: 'TO', name: 'Tocantins',           region: 'N'  },
  { uf: 'AL', name: 'Alagoas',             region: 'NE' },
  { uf: 'BA', name: 'Bahia',               region: 'NE' },
  { uf: 'CE', name: 'Ceará',               region: 'NE' },
  { uf: 'MA', name: 'Maranhão',            region: 'NE' },
  { uf: 'PB', name: 'Paraíba',             region: 'NE' },
  { uf: 'PE', name: 'Pernambuco',          region: 'NE' },
  { uf: 'PI', name: 'Piauí',               region: 'NE' },
  { uf: 'RN', name: 'Rio Grande do Norte', region: 'NE' },
  { uf: 'SE', name: 'Sergipe',             region: 'NE' },
  { uf: 'DF', name: 'Distrito Federal',    region: 'CO' },
  { uf: 'GO', name: 'Goiás',               region: 'CO' },
  { uf: 'MT', name: 'Mato Grosso',         region: 'CO' },
  { uf: 'MS', name: 'Mato Grosso do Sul',  region: 'CO' },
  { uf: 'ES', name: 'Espírito Santo',      region: 'SE' },
  { uf: 'MG', name: 'Minas Gerais',        region: 'SE' },
  { uf: 'RJ', name: 'Rio de Janeiro',      region: 'SE' },
  { uf: 'SP', name: 'São Paulo',           region: 'SE' },
  { uf: 'PR', name: 'Paraná',              region: 'S'  },
  { uf: 'RS', name: 'Rio Grande do Sul',   region: 'S'  },
  { uf: 'SC', name: 'Santa Catarina',      region: 'S'  },
];

// The município universe is now the IBGE territorial mesh (/api/geo-mesh, via
// window.geoMesh) — real, code-keyed, ~5570 municípios with their full sub-UF
// ancestry — resolved inside the component (see `MUNIS`). The old frozen 40-row
// MUNI_SAMPLE and the name-keyed window.MUNI_PICKER_NAMES path were removed with
// the gated, snapshot-topMunis approach they served.

// ----- icons ------------------------------------------------------
const I = {
  filter: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 5h18l-7 9v6l-4-2v-4z"/>
    </svg>
  ),
  close: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 6l12 12M18 6L6 18"/>
    </svg>
  ),
  arrow: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14M13 6l6 6-6 6"/>
    </svg>
  ),
  pencil: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 20h4l10-10-4-4L4 16zM14 6l4 4"/>
    </svg>
  ),
  search: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="6"/><path d="M20 20l-4-4"/>
    </svg>
  ),
  cascade: (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 6h8M8 12h6M8 18h4M4 6v.01M4 12v.01M4 18v.01"/>
    </svg>
  ),
};

// ----- inline search input ----------------------------------------
function SearchInput({ value, onChange, placeholder }) {
  return (
    <span className="fm-search">
      <span className="fm-search-icn">{I.search}</span>
      <input
        type="text"
        value={value}
        aria-label={placeholder || 'Buscar'}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder || 'Buscar…'}
      />
      {value && (
        <button className="fm-search-clear" onClick={() => onChange('')} aria-label="Limpar busca">
          ×
        </button>
      )}
    </span>
  );
}

// ----- bulk actions row -------------------------------------------
// Rows comfortably visible in a scrollable list before the bulk-action reach becomes
// non-obvious (the list viewport shows ~9–10 rows); past this we annotate the reach.
const BULK_REACH_HINT_AT = 12;

function BulkActions({ all, none, invert, selectedCount, totalCount, compact }) {
  return (
    <div className={'fm-bulk' + (compact ? ' compact' : '')}>
      <button type="button" onClick={all} disabled={selectedCount === totalCount}>
        Selecionar tudo
      </button>
      <span className="sep-dot" aria-hidden="true"></span>
      <button type="button" onClick={none} disabled={selectedCount === 0}>
        Limpar
      </button>
      <span className="sep-dot" aria-hidden="true"></span>
      <button type="button" onClick={invert}>
        Inverter
      </button>
      {/* The bulk actions operate on the WHOLE search-filtered set, which may extend
          past the scroll viewport. Announce the reach whenever the list scrolls, so
          "Selecionar tudo" over items off-screen is never a surprise (L7). */}
      {totalCount > BULK_REACH_HINT_AT && (
        <span className="fm-bulk-reach">afeta {totalCount}</span>
      )}
    </div>
  );
}

// ----- product tree (multi-tree dims: NCM / HS by SH prefix) ------
// COMEX/Comtrade "products" are hierarchical customs codes: an 8-digit NCM (or 6-digit
// HS6) whose LEADING DIGITS are the hierarchy — SH2 (capítulo) ▸ SH4 (posição) ▸ SH6
// (subposição) ▸ NCM8. Rather than a flat list of 100–200 codes, group them into an
// expandable tree by prefix. Crucially the tree is a pure VIEW over the SAME flat
// `products` Set of LEAF codes the grid uses, so apply / URL / the serving `ncm_code IN
// (...)` filter are ALL untouched: toggling a parent just adds/removes its descendant
// leaf codes, and a parent checkbox is TRI-STATE (on / off / indeterminate) derived from
// how many of its leaves are selected.
const SH_CUTS = [2, 4, 6]; // prefix lengths SHORTER than the code become parent levels

function buildProductTree(prods, cuts = SH_CUTS) {
  const byId = new Map();
  const roots = [];
  const ensure = (id, depth, isLeaf, product) => {
    let n = byId.get(id);
    if (!n) {
      n = { id, code: id, depth, isLeaf, name: product ? product.name : null, children: [], leafCodes: [] };
      byId.set(id, n);
    }
    return n;
  };
  for (const p of prods) {
    const code = String(p.code);
    const prefixes = cuts.filter((c) => c < code.length).map((c) => code.slice(0, c));
    let parent = null;
    prefixes.forEach((pref, i) => {
      const node = ensure(pref, i + 1, false, null);
      if (i === 0) { if (!roots.includes(node)) roots.push(node); }
      else if (!parent.children.includes(node)) parent.children.push(node);
      node.leafCodes.push(code);
      parent = node;
    });
    const leaf = ensure(code, prefixes.length + 1, true, p);
    leaf.leafCodes = [code];
    if (parent) { if (!parent.children.includes(leaf)) parent.children.push(leaf); }
    else if (!roots.includes(leaf)) roots.push(leaf); // code shorter than the first cut → top-level leaf
  }
  const sortRec = (ns) => { ns.sort((a, b) => a.code.localeCompare(b.code)); ns.forEach((n) => sortRec(n.children)); };
  sortRec(roots);
  return roots;
}

function ProductTree({ nodes, selected, setProducts, search }) {
  const [expanded, setExpanded] = useState(() => new Set());
  const q = (search || '').trim().toLowerCase();
  // SH2 chapter names (shChapters.js) label the top-level parent nodes readably; deeper
  // parents (SH4/SH6) stay bare codes. Leaves already carry their own description.
  const SH = window.SH_CHAPTERS || {};
  const nodeLabel = (n) => {
    if (n.isLeaf) return n.name || n.code;
    const name = n.code.length === 2 ? SH[n.code] : null;
    return name ? `${n.code} · ${name}` : n.code;
  };

  // Leaf codes matching the search (null = no search → everything visible). A parent is
  // shown iff at least one descendant leaf matches; searching force-expands those branches.
  const matches = useMemo(() => {
    if (!q) return null;
    const s = new Set();
    const walk = (ns) => ns.forEach((n) => {
      if (n.isLeaf) {
        if (n.code.includes(q) || (n.name || '').toLowerCase().includes(q)) s.add(n.code);
      } else walk(n.children);
    });
    walk(nodes);
    return s;
  }, [q, nodes]);

  const toggleExpand = (id) =>
    setExpanded((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const setLeaves = (codes, on) =>
    setProducts((prev) => {
      const next = new Set(prev);
      if (on) codes.forEach((c) => next.add(c)); else codes.forEach((c) => next.delete(c));
      return next;
    });
  // Tri-state: 'on' = every leaf selected, 'off' = none, 'partial' = some.
  const stateOf = (node) => {
    let on = 0;
    for (const c of node.leafCodes) if (selected.has(c)) on += 1;
    if (on === 0) return 'off';
    if (on === node.leafCodes.length) return 'on';
    return 'partial';
  };

  const rows = [];
  const isOpen = (n) => (q ? true : expanded.has(n.id));
  const render = (ns) => {
    for (const n of ns) {
      if (matches && !n.leafCodes.some((c) => matches.has(c))) continue;
      const st = stateOf(n);
      rows.push(
        <div key={n.id} className="fm-tree-row" style={{ paddingLeft: `${(n.depth - 1) * 18}px` }}>
          {n.isLeaf ? (
            <span className="fm-tree-tog spacer" aria-hidden="true" />
          ) : (
            <button type="button" className="fm-tree-tog" aria-expanded={isOpen(n)}
                    aria-label={isOpen(n) ? `Recolher ${n.code}` : `Expandir ${n.code}`}
                    onClick={() => toggleExpand(n.id)}>
              {isOpen(n) ? '▾' : '▸'}
            </button>
          )}
          <label className={'fm-check tree' + (st === 'on' ? ' is-on' : '') + (st === 'partial' ? ' is-partial' : '')}>
            <input type="checkbox" checked={st === 'on'}
                   ref={(el) => { if (el) el.indeterminate = st === 'partial'; }}
                   onChange={() => setLeaves(n.isLeaf ? [n.code] : n.leafCodes, st !== 'on')} />
            <span className="fm-name" title={nodeLabel(n)}>{nodeLabel(n)}</span>
            <span className="fm-code">{n.isLeaf ? n.code : `${n.leafCodes.length}`}</span>
          </label>
        </div>,
      );
      if (!n.isLeaf && isOpen(n)) render(n.children);
    }
  };
  render(nodes);

  if (rows.length === 0) {
    return <div className="fm-empty-grid">Nenhum produto corresponde a “{search}”.</div>;
  }
  return <div className="fm-tree">{rows}</div>;
}

// ----- reusable column for the geography cascade -----------------
function GeoColumn({
  title, items, keyAttr, displayAttr, getMeta,
  selected, setSelected,
  search, setSearch,
  disabledReason, emptyAllNote,
}) {
  const filtered = useMemo(() => {
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter(x =>
      x[displayAttr].toLowerCase().includes(q) ||
      (x[keyAttr] && String(x[keyAttr]).toLowerCase().includes(q))
    );
  }, [items, search, displayAttr, keyAttr]);

  const toggle = (val) => {
    const next = new Set(selected);
    next.has(val) ? next.delete(val) : next.add(val);
    setSelected(next);
  };

  // Bulk actions operate on the SEARCH-FILTERED ("visible") items, so e.g.
  // searching "Pa" then "Limpar" only clears matches — never the whole Set.
  // With no search, `filtered` === items, so behaviour is unchanged.
  const visKeys = filtered.map(x => x[keyAttr]);
  const visSet  = new Set(visKeys);
  const allOn   = () => setSelected(new Set([...selected, ...visKeys]));
  const allOff  = () => setSelected(new Set([...selected].filter(k => !visSet.has(k))));
  const allInv  = () => { const n = new Set(selected); visKeys.forEach(k => n.has(k) ? n.delete(k) : n.add(k)); setSelected(n); };

  return (
    <div className="fm-geo-col">
      <div className="fm-geo-col-head">
        <span className="fm-geo-title">{title}</span>
        <span className="fm-geo-count">
          <strong>{selected.size}</strong>/{items.length}
        </span>
      </div>

      <SearchInput
        value={search}
        onChange={setSearch}
        placeholder={`Buscar em ${title.toLowerCase()}…`}
      />

      <div className="fm-geo-list">
        {disabledReason && (
          <div className="fm-geo-empty">
            <span className="fm-cascade-icn">{I.cascade}</span>
            {disabledReason}
          </div>
        )}
        {!disabledReason && emptyAllNote && selected.size === 0 && (
          <div className="fm-geo-allnote">{emptyAllNote}</div>
        )}
        {!disabledReason && filtered.length === 0 && (
          <div className="fm-geo-empty">Nenhum resultado.</div>
        )}
        {!disabledReason && filtered.slice(0, GEO_RENDER_CAP).map(item => {
          const on = selected.has(item[keyAttr]);
          const meta = getMeta ? getMeta(item) : null;
          return (
            <label key={item[keyAttr]} className={'fm-check geo' + (on ? ' is-on' : '')}>
              <input type="checkbox" checked={on}
                     onChange={() => toggle(item[keyAttr])}/>
              <span className="fm-name">{item[displayAttr]}</span>
              {meta && <span className="fm-code">{meta}</span>}
            </label>
          );
        })}
        {!disabledReason && filtered.length > GEO_RENDER_CAP && (
          <div className="fm-geo-allnote">
            Mostrando {GEO_RENDER_CAP} de {filtered.length} — refine a busca para ver os demais
            (as ações em massa abaixo afetam todos os {filtered.length}).
          </div>
        )}
      </div>

      <BulkActions
        all={allOn}
        none={allOff}
        invert={allInv}
        selectedCount={visKeys.filter(k => selected.has(k)).length}
        totalCount={filtered.length}
        compact={true}
      />
    </div>
  );
}

// ==================================================================
// Controlled component:
//   <FilterMenu open banco="ibge_pevs" onClose onApply />
// The menu is SCOPED to the active banco (chosen in the sidebar):
//   • live banco  → full functional filter sections
//   • soon banco  → read-only preview of its planned filter dimensions
// A sub-UF facet narrows the data only as a PROPER subset of its universe; a full
// selection means "no narrowing" → emit null so dataFilters skips it and the share
// URL omits it (instead of serializing every código). namesObj is the per-level
// {code: name} map whose key count IS the universe size.
const _geoArr = (set, namesObj) =>
  set.size >= Object.keys(namesObj).length ? null : [...set];

// Cap how many geo checkboxes render at once. The município column's universe is ~5570;
// rendering them all on first open is jank/memory the list rarely needs (RVC-5). Bulk
// actions still operate on the full search-filtered set — only the visible DOM is capped,
// and a note nudges the user to search to narrow further.
const GEO_RENDER_CAP = 300;

// onApply receives a display-summary object the trigger row can render as
// chips. `value` is the currently-APPLIED raw filter (basket/flags/states/…);
// the panel seeds itself from it each time it opens, so it always mirrors
// what's live (incl. a shared deep-link) instead of silently resetting to all.
function FilterMenu({ open = false, banco = 'ibge_pevs', value, onClose, onApply }) {
  const close = () => { if (typeof onClose === 'function') onClose(); };
  const modalRef = React.useRef(null);
  const lastFocusRef = React.useRef(null);
  // a11y: Escape closes the modal (mirrors the backdrop click). Listener is bound
  // only while the modal is open and torn down on close/unmount.
  React.useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape' && typeof onClose === 'function') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // a11y: focus management for the modal dialog (M2). On open, remember the element
  // that had focus (the trigger) and move focus into the panel; while open, TRAP Tab
  // so keyboard/screen-reader focus can't escape behind the backdrop; on close, restore
  // focus to the trigger. Without this the dialog was announced (role/aria-modal) but
  // keyboard focus stayed on the page underneath.
  React.useEffect(() => {
    if (!open) return undefined;
    const modal = modalRef.current;
    if (!modal) return undefined;
    lastFocusRef.current = document.activeElement;
    const focusables = () =>
      [...modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )].filter((el) => !el.disabled && el.offsetParent !== null);
    // Initial focus: first focusable control, else the panel itself.
    const first = focusables()[0];
    (first || modal).focus();
    const onKeyDown = (e) => {
      if (e.key !== 'Tab') return;
      const els = focusables();
      if (els.length === 0) { e.preventDefault(); return; }
      const firstEl = els[0], lastEl = els[els.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus(); }
      else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus(); }
    };
    modal.addEventListener('keydown', onKeyDown);
    return () => {
      modal.removeEventListener('keydown', onKeyDown);
      const prev = lastFocusRef.current;
      if (prev && typeof prev.focus === 'function') prev.focus();
    };
  }, [open]);

  const bancoMeta = window.bancoById ? window.bancoById(banco) : null;
  const schema    = window.filterSchemaFor ? window.filterSchemaFor(banco) : null;
  const isLive    = bancoMeta ? bancoMeta.status === 'live' : true;
  const hasGeo    = !!(bancoMeta && bancoMeta.provides && bancoMeta.provides.includes('geo'));
  // Capability gates — every section is now dynamic: it renders ONLY when the active
  // banco provides the dimension (so the user never sees an option it can't use).
  const provides    = (bancoMeta && bancoMeta.provides) || [];
  const hasProduct  = provides.includes('product');
  const hasQuality  = provides.includes('quality');
  const hasFlow     = provides.includes('flow');
  const flowOptions = (hasFlow && window.flowOptionsFor) ? window.flowOptionsFor(banco) : null;
  // Regime aduaneiro (customs procedure) — a SECOND server-side trade filter, gated on the
  // banco actually carrying customs_code (only COMTRADE → window.customsOptionsFor non-null),
  // not on a capability flag. Mirrors the flow control.
  const regimeOptions = window.customsOptionsFor ? window.customsOptionsFor(banco) : null;
  const hasRegime     = !!regimeOptions;
  // Tipo de mercado (consumo/processamento) — a THIRD server-side trade filter, gated on
  // the banco carrying market_nature (only COMTRADE → marketOptionsFor non-null).
  const marketOptions = window.marketOptionsFor ? window.marketOptionsFor(banco) : null;
  const hasMarket     = !!marketOptions;
  // País reporter / parceiro (COMTRADE only) — two country multi-selects backed by the
  // /api/countries universe (NOT a static OPTIONS map like flow/regime/market). Reading
  // window.comtradeCountries() kicks the one-shot fetch; main.jsx's resource subscription
  // re-renders once it lands. `countriesReady` gates the seed + apply (like the geo mesh).
  const hasCountries = !!(window.hasCountryFilters && window.hasCountryFilters(banco));
  const countries = hasCountries && window.comtradeCountries ? window.comtradeCountries() : null;
  const reporterUniverse = (countries && countries.reporters) || [];
  const partnerUniverse = (countries && countries.partners) || [];
  const countriesReady = !hasCountries || !!countries;
  const isoNameOf = (universe) => (iso) => (universe.find(c => c.iso === iso) || {}).name || iso;

  // ── Per-banco descriptors so the live menu is CORRECT for each banco
  // (no longer always PEVS): currency symbol/column, geo granularity, the
  // product dimension's label, and the banco-specific dimensions not yet
  // covered by the functional sections (surfaced read-only below).
  const geoLevel  = window.geoLevelFor ? window.geoLevelFor(banco) : (hasGeo ? 'municipio' : null);
  const showMunis = geoLevel === 'municipio';
  const dims      = (schema && schema.dims) || [];
  const prodDim   = dims.find(d => d.type === 'products' || d.type === 'multi-tree');
  const prodLabel = (prodDim && prodDim.label) || `Produtos · ${bancoMeta ? bancoMeta.short : 'PEVS'}`;
  // The menu renders ONLY what the active banco can filter on: each section below is
  // capability-gated (hasProduct/hasGeo/hasQuality/hasFlow), so a dim the banco
  // doesn't provide, or one declared-but-not-backed (via/CFOP/CNAE/partner — summed
  // away in Silver), simply never appears. `fluxo` is the one banco-specific dim
  // wired functional (server-side); see window.bancoFilterDims for the contract.

  // Active banco's product universe (NOT the hardcoded PEVS list) so the picker
  // shows the right commodities/codes per banco (NCM for COMEX, HS6 for
  // Comtrade, …). For PEVS this equals window.PRODUCTS → behavior unchanged.
  const PRODS = useMemo(() => {
    const snap = (window.dataStore && window.dataStore.get && window.dataStore.get(banco))
              || (window.snapshotFor && window.snapshotFor(banco)) || null;
    return ((snap && snap.products) || window.PRODUCTS || [])
      .map(p => ({ code: p.code, name: p.name, unit: p.unit, family: p.family }));
  }, [banco]);

  // A `multi-tree` product dim (COMEX NCM, Comtrade HS6) renders the picker as an
  // expandable SH-prefix tree instead of the flat grid; PEVS/PAM/PPM ('products') stay
  // flat. The tree is derived purely from the flat PRODS by code-prefix (no backend).
  const isTreeProducts = !!(prodDim && prodDim.type === 'multi-tree');
  const productTree = useMemo(
    () => (isTreeProducts ? buildProductTree(PRODS) : null), [isTreeProducts, PRODS]);

  // Município + sub-UF universe — the IBGE territorial mesh (/api/geo-mesh, via
  // window.geoMesh). Every município → its 7-digit city_code + UF + grande região +
  // BOTH sub-UF divisions (classic mesorregião/microrregião, 2017 região
  // intermediária/imediata). This makes município a REAL, code-keyed filter (the old
  // path was name-keyed off the snapshot's topMunis and gated off in prod) and feeds
  // the four sub-UF cascade levels. A UF-origin banco (geoLevel !== 'municipio', e.g.
  // COMEX) has no city_code, so the mesh is not loaded and only nação ▸ região ▸ UF
  // render. The mesh is static + cached; main.jsx's resource subscription re-renders
  // this menu once it lands, so the first open may briefly show empty sub-UF columns.
  const mesh = (showMunis && window.geoMesh) ? window.geoMesh() : null;
  const { MUNIS, mesoNames, microNames, interNames, imediataNames } = useMemo(() => {
    const meso = {}, micro = {}, inter = {}, imediata = {};
    const list = (mesh || []).map(m => {
      const mc = (m.meso && m.meso.code) || '';
      const cc = (m.micro && m.micro.code) || '';
      const ic = (m.intermediaria && m.intermediaria.code) || '';
      const ec = (m.imediata && m.imediata.code) || '';
      if (mc) meso[mc] = m.meso.name;
      if (cc) micro[cc] = m.micro.name;
      if (ic) inter[ic] = m.intermediaria.name;
      if (ec) imediata[ec] = m.imediata.name;
      return { code: m.cityCode, name: m.cityName, uf: m.uf,
               meso: mc, micro: cc, intermediaria: ic, imediata: ec };
    });
    return { MUNIS: list, mesoNames: meso, microNames: micro, interNames: inter, imediataNames: imediata };
  }, [mesh]);

  // município is LIVE once the mesh has loaded (it carries the full ~5570 universe);
  // until then (or for a UF-origin banco) the columns are gated.
  const muniUniverseLive = MUNIS.length > 0;
  const muniSliceable = showMunis && muniUniverseLive;

  // Period bounds + quick-ranges from the ACTIVE banco's snapshot (same source as
  // PRODS), so switching banco shifts the date min/max and the quick-range chips
  // instead of staying frozen to whichever banco loaded first at import time.
  const [yearStart, yearEnd] = useMemo(() => {
    const snap = (window.dataStore && window.dataStore.get && window.dataStore.get(banco))
              || (window.snapshotFor && window.snapshotFor(banco)) || null;
    return bancoYearBounds(snap);
  }, [banco]);
  const QUICK_RANGES = useMemo(() => buildQuickRanges(yearStart, yearEnd), [yearStart, yearEnd]);

  // multi-selects (Sets)
  const [products, setProducts] = useState(new Set(PRODS.map(p => p.code)));
  const [flags,    setFlags]    = useState(new Set(QUALITY.map(f => f.flag)));
  // Geo selection (nations → regions → states → municípios) + cascade pruning +
  // eligibility live in a dedicated, unit-tested hook (useGeoCascade.js). Defaults:
  // nations = {BR} only; regions/states/municípios = all of the banco's universe.
  const {
    nations,  setNations,
    regions,  setRegions,
    states,   setStates,
    mesos,    setMesos,
    micros,   setMicros,
    inters,   setInters,
    imediatas, setImediatas,
    munis,    setMunis,
    eligibleRegions, eligibleStates,
    eligibleMesos, eligibleMicros, eligibleInters, eligibleImediatas,
    eligibleMunis,
  } = window.useGeoCascade({ regionsUniverse: FM_REGIONS, statesUniverse: STATES, munisUniverse: MUNIS });

  // The four sub-UF levels arrive from the engine as arrays of CODES; GeoColumn
  // wants {code, name} items, so decorate each with its mesh name (falling back to
  // the code). Memoized on the eligible list + the name map.
  const mesoItems = useMemo(
    () => eligibleMesos.map(c => ({ code: c, name: mesoNames[c] || c })), [eligibleMesos, mesoNames]);
  const microItems = useMemo(
    () => eligibleMicros.map(c => ({ code: c, name: microNames[c] || c })), [eligibleMicros, microNames]);
  const interItems = useMemo(
    () => eligibleInters.map(c => ({ code: c, name: interNames[c] || c })), [eligibleInters, interNames]);
  const imediataItems = useMemo(
    () => eligibleImediatas.map(c => ({ code: c, name: imediataNames[c] || c })), [eligibleImediatas, imediataNames]);

  // FILT-1: the sub-UF disclosure is collapsed by default; the geo-seed effect
  // below sets this explicitly (true/false) from the APPLIED filter each time the
  // menu opens, so a shared/deep-linked sub-UF selection is never hidden.
  const [subUfExpanded, setSubUfExpanded] = useState(false);
  // A facet counts as narrowing the SAME way dataFilters.js does: a PROPER,
  // NON-EMPTY subset of its universe (0 selected = a cascade-emptied child = no
  // constraint, same as "all"). Drives the "recorte ativo" badge on the collapsed
  // toggle, so collapsing the panel never hides an active narrowing silently.
  const isNarrowingFacet = (size, total) => size > 0 && size < total;
  const subUfNarrowing =
    isNarrowingFacet(mesos.size, Object.keys(mesoNames).length) ||
    isNarrowingFacet(micros.size, Object.keys(microNames).length) ||
    isNarrowingFacet(inters.size, Object.keys(interNames).length) ||
    isNarrowingFacet(imediatas.size, Object.keys(imediataNames).length) ||
    isNarrowingFacet(munis.size, MUNIS.length);

  // search strings, one per multi-select
  const [qProducts, setQProducts] = useState('');
  const [qFlags,    setQFlags]    = useState('');
  const [qNations,  setQNations]  = useState('');
  const [qRegions,  setQRegions]  = useState('');
  const [qStates,   setQStates]   = useState('');
  const [qMesos,    setQMesos]    = useState('');
  const [qMicros,   setQMicros]   = useState('');
  const [qInters,   setQInters]   = useState('');
  const [qImediatas, setQImediatas] = useState('');
  const [qMunis,    setQMunis]    = useState('');

  // period — seeded from the active banco's bounds (the open-effect below
  // re-seeds from the applied filter / banco bounds each time the panel opens).
  const [quickRange, setQuickRange] = useState('all');
  const [startDate,  setStartDate]  = useState(`${yearStart}-01`);
  const [endDate,    setEndDate]    = useState(`${yearEnd}-12`);

  // (The per-row value-range filter was removed: it has no backend filter path, so its
  // state/chip/normalization was vestigial plumbing that misled the next reader into
  // thinking "Faixa de valor" was activatable — N1. VALUE_PRESETS/valueShareForRange
  // stay in filtersSchema/dataFilters only where the "Linhas" counter still reads them.)

  // Fluxo (export/import) — a SERVER-SIDE filter: the trade snapshot is pre-aggregated
  // over flow, so picking a direction re-fetches (the data layer's setFlow bridge).
  // 'all' = every flow. Only trade bancos (hasFlow) render the control.
  const [flow, setFlow] = useState((value && value.flow) || 'all');
  // Regime aduaneiro (server-side, COMTRADE only). 'all' = every regime (the total).
  const [customs, setCustoms] = useState((value && value.customs) || 'all');
  // Tipo de mercado (server-side, COMTRADE only). 'all' = every purpose.
  const [market, setMarket] = useState((value && value.market) || 'all');
  // País reporter / parceiro (server-side, COMTRADE only) — Sets of ISO-A3 codes. reporter
  // default = {Brasil}; partner default = all. Seeded on open (guarded on the country universe
  // having loaded, like the geo seed) — the initial values here are just pre-seed placeholders.
  const [reporters, setReporters] = useState(() => new Set([BRAZIL_ISO]));
  const [partners,  setPartners]  = useState(() => new Set());
  const [qReporters, setQReporters] = useState('');
  const [qPartners,  setQPartners]  = useState('');

  // (eligibility memos + cascade-pruning effects now live in useGeoCascade above)

  // Seed the NON-geo panel state from the currently-APPLIED filter each time the menu
  // opens, so it mirrors the live state (a shared deep-link, or a prior apply) instead
  // of its hardcoded defaults. The GEO seed is a SEPARATE effect (below) because its
  // universe — the IBGE mesh — loads asynchronously.
  const wasOpen = React.useRef(false);
  const geoSeeded = React.useRef(false);
  const countriesSeeded = React.useRef(false);
  React.useEffect(() => {
    if (open && !wasOpen.current) {
      const v = value || {};
      setProducts(v.basket  != null ? new Set(v.basket)  : new Set(PRODS.map(p => p.code)));
      setFlags(   v.flags   != null ? new Set(v.flags)   : new Set(QUALITY.map(f => f.flag)));
      setNations( v.nations != null ? new Set(v.nations) : new Set(['BR']));
      // States travel in the deep-link; regions/nations do NOT. Seed states from the
      // applied filter, then DERIVE the region checkboxes from that subset — mark a
      // region whenever it contributes at least one selected UF — so the cascade no
      // longer shows every region checked over a partial state selection (L6). Using
      // "≥1 UF" (not "all UFs") keeps every restored UF ELIGIBLE, so the cascade's own
      // state-pruning never drops one.
      const seededStates = v.states != null ? new Set(v.states) : new Set(STATES.map(s => s.uf));
      setStates(seededStates);
      if (v.regions != null) {
        setRegions(new Set(v.regions));
      } else if (v.states != null) {
        const byRegion = {};
        STATES.forEach(s => { (byRegion[s.region] = byRegion[s.region] || []).push(s.uf); });
        setRegions(new Set(FM_REGIONS.filter(r => (byRegion[r.id] || []).some(uf => seededStates.has(uf))).map(r => r.id)));
      } else {
        setRegions(new Set(FM_REGIONS.map(r => r.id)));
      }
      const sd = v.startDate || `${yearStart}-01`;
      const ed = v.endDate   || `${yearEnd}-12`;
      setStartDate(sd); setEndDate(ed);
      setQuickRange((sd === `${yearStart}-01` && ed === `${yearEnd}-12`) ? 'all' : null);
      setFlow(v.flow || 'all');
      setCustoms(v.customs || 'all');
      setMarket(v.market || 'all');
      geoSeeded.current = false; // let the geo effect (re)seed once the mesh is ready
      countriesSeeded.current = false; // ditto for the country universe (COMTRADE)
    }
    wasOpen.current = open;
    // Intentionally keyed ONLY on `open`: this re-syncs the DRAFT filter state from
    // props each time the menu opens, so the user's in-progress edits are not
    // clobbered by unrelated prop changes (value/year/basket) while it is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // GEO seed — kept SEPARATE because the sub-UF/município universe is the IBGE mesh, an
  // async resource independent of the snapshot. Seeding the geo Sets before the mesh
  // lands would seed them from an EMPTY universe; the cascade would then prune a
  // deep-linked município subset and refill it to "all", so Apply emits null="all" and
  // silently discards the shared filter (H2). Gate the seed on geo-readiness and run it
  // exactly ONCE per open. This effect is registered AFTER useGeoCascade, so it wins the
  // effect-flush against the cascade's reconcile (its write is the last one applied).
  const geoReady = !showMunis || muniUniverseLive;
  React.useEffect(() => {
    if (!open || geoSeeded.current || !geoReady) return;
    geoSeeded.current = true;
    const v = value || {};
    setMesos(    v.mesos     != null ? new Set(v.mesos)     : new Set(Object.keys(mesoNames)));
    setMicros(   v.micros    != null ? new Set(v.micros)    : new Set(Object.keys(microNames)));
    setInters(   v.inters    != null ? new Set(v.inters)    : new Set(Object.keys(interNames)));
    setImediatas(v.imediatas != null ? new Set(v.imediatas) : new Set(Object.keys(imediataNames)));
    setMunis(    v.munis     != null ? new Set(v.munis)     : new Set(MUNIS.map(m => m.code)));
    // Auto-expand the disclosure when the filter being restored already narrows a
    // sub-UF facet — collapsed-by-default must never mean "silently discarded".
    setSubUfExpanded(
      v.mesos != null || v.micros != null || v.inters != null || v.imediatas != null || v.munis != null,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, geoReady]);

  // COUNTRY seed — like the geo seed, the reporter/partner universe (/api/countries) is an
  // async resource, so seed once it has loaded. reporter: '__all__' → all reporters (world),
  // array → that set, absent → {Brasil}. partner: array → that set, absent → all partners.
  React.useEffect(() => {
    if (!open || countriesSeeded.current || !countriesReady) return;
    countriesSeeded.current = true;
    const v = value || {};
    const allRep = new Set(reporterUniverse.map(c => c.iso));
    const allPar = new Set(partnerUniverse.map(c => c.iso));
    setReporters(
      v.reporters === '__all__' ? allRep
        : Array.isArray(v.reporters) && v.reporters.length ? new Set(v.reporters)
          : new Set([BRAZIL_ISO]));
    setPartners(Array.isArray(v.partners) ? new Set(v.partners) : allPar);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, countriesReady]);

  // products / flags filtered by search
  const filteredProducts = useMemo(() => {
    if (!qProducts) return PRODS;
    const q = qProducts.toLowerCase();
    return PRODS.filter(p =>
      p.name.toLowerCase().includes(q) || p.code.includes(q)
    );
  }, [qProducts, PRODS]);
  const filteredFlags = useMemo(() => {
    if (!qFlags) return QUALITY;
    const q = qFlags.toLowerCase();
    return QUALITY.filter(f => f.flag.toLowerCase().includes(q) || f.label.toLowerCase().includes(q));
  }, [qFlags]);

  // helpers
  const toggleIn = (set, val) => {
    const next = new Set(set);
    next.has(val) ? next.delete(val) : next.add(val);
    return next;
  };

  // quick range
  const applyQuick = (id) => {
    const r = QUICK_RANGES.find(x => x.id === id);
    if (!r) return;
    setQuickRange(id);
    setStartDate(r.start);
    setEndDate(r.end);
  };
  const onDateChange = (which, v) => {
    // Defense in depth: the inputs' min/max already constrain the native
    // picker, but a typed/programmatic value could invert the range. Clamp so
    // start ≤ end always holds (no "2020–2000").
    if (which === 'start') {
      setStartDate(v);
      if (v > endDate) setEndDate(v);
    } else {
      setEndDate(v);
      if (v < startDate) setStartDate(v);
    }
    setQuickRange(null);
  };

  // summary
  const summary = useMemo(() => {
    const prodTxt = products.size === PRODS.length
      ? `${PRODS.length} produtos (todos)`
      : `${products.size} de ${PRODS.length} produtos`;
    const period = `${formatMonth(startDate)}–${formatMonth(endDate)}`;
    const geoTxt = window.filterSummary.geoHeaderText({
      hasGeo,
      nationsSize: nations.size,
      nationsTotal: NATIONS.length,
      hasOnlyBR: nations.size === 1 && nations.has('BR'),
      regionsSize: regions.size,
      regionsTotal: FM_REGIONS.length,
      statesSize: states.size,
      statesTotal: STATES.length,
      munisSize: munis.size,
      munisTotal: MUNIS.length,
      muniSliceable,
    });
    return { prodTxt, period, geoTxt };
  }, [products, startDate, endDate, nations, regions, states, munis, hasGeo, muniSliceable, MUNIS, PRODS.length]);

  // chip-bar summary published on apply (display strings only)
  const buildChipSummary = () => {
    const prodChip = window.chipFmt.products(
      products.size, PRODS.length, (PRODS.find(p => products.has(p.code)) || {}).name);
    // Period chip is YEAR–YEAR in both the apply AND the URL-restore path (withChips
    // uses chipFmt.period), because the underlying filter is year-granular — showing
    // MM/AAAA here made the chip change shape between apply and reload (L1).
    const periodChip = window.chipFmt.period(startDate.slice(0, 4), endDate.slice(0, 4));
    const geoChip = window.filterSummary.geoChipText({
      hasGeo,
      nationsSize: nations.size,
      nationsTotal: NATIONS.length,
      hasOnlyBR: nations.size === 1 && nations.has('BR'),
      regionsSize: regions.size,
      regionsTotal: FM_REGIONS.length,
      statesSize: states.size,
      statesTotal: STATES.length,
      munisSize: munis.size,
      munisTotal: MUNIS.length,
      muniSliceable,
    });
    const qualityChip = window.chipFmt.quality([...flags], QUALITY.length, qualityLabelOf);
    // Guard on flowOptions too (not just hasFlow): a banco could declare provides:['flow']
    // before its FLOW_OPTIONS entry exists — then flowOptions is null and .find would
    // throw (L3). Mirrors the section's own `hasFlow && flowOptions` gate.
    const fluxoChip = (hasFlow && flowOptions)
      ? (flow === 'all' ? 'Todos os fluxos' : ((flowOptions.find(o => o.value === flow) || {}).label || flow))
      : null;
    const regimeChip = (hasRegime && regimeOptions)
      ? (customs === 'all' ? 'Todos os regimes' : ((regimeOptions.find(o => o.value === customs) || {}).label || customs))
      : null;
    const marketChip = (hasMarket && marketOptions)
      ? (market === 'all' ? 'Todos os mercados' : ((marketOptions.find(o => o.value === market) || {}).label || market))
      : null;
    const reporterChip = (hasCountries && countriesReady)
      ? window.chipFmt.reporter([...reporters], reporterUniverse.length, isoNameOf(reporterUniverse))
      : null;
    const partnerChip = (hasCountries && countriesReady)
      ? window.chipFmt.partner([...partners], partnerUniverse.length, isoNameOf(partnerUniverse))
      : null;
    return { products: prodChip, period: periodChip, geo: geoChip, quality: qualityChip, fluxo: fluxoChip, regime: regimeChip, mercado: marketChip, reporter: reporterChip, parceiro: partnerChip };
  };

  const applyAndClose = () => {
    // Normalize a FULL selection to null = "no narrowing" for EVERY list dimension
    // (dataFilters + the URL codec treat null and the full set identically). This keeps
    // the share URL small (no dumping the whole product catalog / 27-UF list), makes
    // "touched-but-full" behave exactly like "untouched", and fixes both the stateShare
    // >1 counter and the COMEX pseudo-origin drop that a full 27-UF array triggered (L2)
    // — matching the null-when-full rule the geo levels already used.
    const fullOrNull = (set, size) => (set.size >= size ? null : [...set]);
    // If the IBGE mesh is not live yet, the local geo Sets can't be trusted (the cascade
    // may have refilled a deep-linked subset to "all"); preserve the incoming value's geo
    // selection verbatim so Apply never silently widens it (H2 belt-and-suspenders).
    const v = value || {};
    // País reporter (COMTRADE) 3-state encoder: {Brasil}/empty → undefined (Brazil default,
    // byte-identical); the FULL universe → '__all__' (world total); else the ISO list. Preserve
    // the incoming value until the country universe loaded (mirrors the geo belt-and-suspenders).
    const reporterOut = (() => {
      if (!countriesReady) return v.reporters ?? undefined;
      if (reporters.size === 0) return undefined;
      if (reporters.size >= reporterUniverse.length) return '__all__';
      if (reporters.size === 1 && reporters.has(BRAZIL_ISO)) return undefined;
      return [...reporters];
    })();
    // País parceiro: empty OR full → null (all); else the ISO list.
    const partnerOut = !countriesReady
      ? (v.partners ?? null)
      : (partners.size === 0 || partners.size >= partnerUniverse.length) ? null : [...partners];
    if (typeof onApply === 'function') {
      onApply({
        ...buildChipSummary(),
        basket:    fullOrNull(products, PRODS.length),
        flags:     fullOrNull(flags, QUALITY.length),
        nations:   [...nations],
        regions:   [...regions],
        states:    fullOrNull(states, STATES.length),
        // The four sub-UF levels (two parallel IBGE divisions) + município, all
        // CODE-keyed off the mesh — dataFilters rolls the município cube up to the
        // active level via /api/geo-mesh. A FULL selection emits null = "all".
        mesos:     geoReady ? _geoArr(mesos, mesoNames)         : (v.mesos ?? null),
        micros:    geoReady ? _geoArr(micros, microNames)       : (v.micros ?? null),
        inters:    geoReady ? _geoArr(inters, interNames)       : (v.inters ?? null),
        imediatas: geoReady ? _geoArr(imediatas, imediataNames) : (v.imediatas ?? null),
        munis:     geoReady ? (munis.size >= MUNIS.length ? null : [...munis]) : (v.munis ?? null),
        startDate, endDate,
        // Fluxo (server-side): omitted when 'all' so the summary/URL stay clean and
        // the data-layer bridge reads it as "every flow" (the default).
        flow: flow !== 'all' ? flow : undefined,
        // Regime aduaneiro (server-side, COMTRADE): omitted when 'all' = every regime.
        customs: customs !== 'all' ? customs : undefined,
        // Tipo de mercado (server-side, COMTRADE): omitted when 'all' = every purpose.
        market: market !== 'all' ? market : undefined,
        // País reporter / parceiro (server-side, COMTRADE) — see the encoders above.
        reporters: reporterOut,
        partners: partnerOut,
      });
    }
    close();
  };

  // restore defaults
  const restoreDefaults = () => {
    setProducts(new Set(PRODS.map(p => p.code)));
    setFlags(new Set(QUALITY.map(f => f.flag)));
    setNations(new Set(['BR']));
    setRegions(new Set(FM_REGIONS.map(r => r.id)));
    setStates(new Set(STATES.map(s => s.uf)));
    setMesos(new Set(Object.keys(mesoNames)));
    setMicros(new Set(Object.keys(microNames)));
    setInters(new Set(Object.keys(interNames)));
    setImediatas(new Set(Object.keys(imediataNames)));
    setMunis(new Set(MUNIS.map(m => m.code)));
    applyQuick('all');
    setFlow('all');
    setCustoms('all');
    setMarket('all');
    setReporters(new Set([BRAZIL_ISO]));
    setPartners(new Set(partnerUniverse.map(c => c.iso)));
    [setQProducts, setQFlags, setQNations, setQRegions, setQStates,
     setQMesos, setQMicros, setQInters, setQImediatas, setQMunis,
     setQReporters, setQPartners].forEach(fn => fn(''));
  };

  if (!open) return null;

  return (
    <div className="fm-backdrop" onClick={close}>
      <div ref={modalRef} tabIndex={-1} className="fm-modal wide" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="fm-title">
        {/* HEADER */}
            <header className="fm-head">
              <div className="fm-head-text">
                <span className="fm-head-over">
                  Filtros · {bancoMeta ? bancoMeta.short : 'Banco'}
                  {schema && <span className="fm-head-table"> · <code>{(window.dataStore && window.dataStore.meta(bancoMeta?.id || banco).table) || window.bancoTable(banco)}</code></span>}
                </span>
                <span id="fm-title" className="fm-title">
                  {isLive ? 'Editar filtros' : 'Dimensões filtráveis'}
                </span>
                <span className="fm-summary" role="status" aria-live="polite">
                  {isLive
                    ? <><strong>{summary.prodTxt}</strong> · {summary.period} · {summary.geoTxt}</>
                    : <>Pré-visualização · este banco será habilitado em <strong>{bancoMeta?.maturityDate || 'breve'}</strong></>}
                </span>
              </div>
              <button className="fm-close" onClick={close} aria-label="Fechar">
                {I.close}
              </button>
            </header>

            {!isLive ? (
              <FilterPreview schema={schema} banco={bancoMeta} onClose={close} />
            ) : (
            <>
            <div className="fm-body">

            {/* ─── 01 · COMMODITIES (gated on the `product` capability) ─────── */}
            {hasProduct && (
            <section className="fm-section">
              <div className="fm-section-head">
                <div className="fm-section-head-l">
                  <span className="fm-section-label"><span className="fm-section-num">01</span>{prodLabel}</span>
                  <SearchInput value={qProducts} onChange={setQProducts} placeholder="Buscar produto ou código…"/>
                </div>
                <span className="fm-section-meta">
                  <strong>{products.size}</strong> de {PRODS.length} selecionados
                </span>
              </div>

              {/* Surface the product dim's hint in the LIVE menu too (it used to appear
                  only in the "soon" preview), so a hierarchical code dim like NCM/HS6
                  documents its SH2▸SH4▸SH6 structure where the researcher actually
                  picks — instead of the flat grid promising nothing (L4). */}
              {prodDim?.hint && <div className="fm-cascade-hint">{prodDim.hint}</div>}

              <div className="fm-section-inner">
                <div className="fm-grid-scroll">
                  {isTreeProducts ? (
                    /* Hierarchical NCM/HS picker (COMEX/Comtrade): a pure view over the
                       same `products` leaf-code Set. */
                    <ProductTree
                      nodes={productTree}
                      selected={products}
                      setProducts={setProducts}
                      search={qProducts}
                    />
                  ) : (
                    <div className="fm-grid">
                      {filteredProducts.length === 0 ? (
                        <div className="fm-empty-grid">Nenhum produto corresponde a “{qProducts}”.</div>
                      ) : filteredProducts.map(p => {
                        const on = products.has(p.code);
                        return (
                          <label key={p.code} className={'fm-check' + (on ? ' is-on' : '')}>
                            <input type="checkbox" checked={on}
                                   onChange={() => setProducts(s => toggleIn(s, p.code))}/>
                            <span className="fm-name">{p.name}</span>
                            <span className="fm-code">{p.code}</span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>

                <BulkActions
                  all={()    => setProducts(prev => new Set([...prev, ...filteredProducts.map(p => p.code)]))}
                  none={()   => { const vis = new Set(filteredProducts.map(p => p.code)); setProducts(prev => new Set([...prev].filter(c => !vis.has(c)))); }}
                  invert={() => setProducts(prev => { const n = new Set(prev); filteredProducts.forEach(p => n.has(p.code) ? n.delete(p.code) : n.add(p.code)); return n; })}
                  selectedCount={filteredProducts.filter(p => products.has(p.code)).length}
                  totalCount={filteredProducts.length}
                />
              </div>
            </section>
            )}

            {/* ─── FLUXO (export/import) — FUNCTIONAL, server-side filter; trade bancos only.
                 Picking a direction re-fetches the flow-aggregated snapshot (the only
                 server-side filter; everything else narrows the loaded snapshot). ─── */}
            {hasFlow && flowOptions && (
            <section className="fm-section">
              <div className="fm-section-head">
                <div className="fm-section-head-l">
                  <span className="fm-section-label">Fluxo</span>
                </div>
                <span className="fm-section-meta">
                  {flow === 'all'
                    ? 'todos os fluxos'
                    : ((flowOptions.find(o => o.value === flow) || {}).label || '')}
                </span>
              </div>
              <div className="fm-section-inner">
                <div className="seg">
                  {flowOptions.map(o => (
                    <button key={o.value} type="button"
                            className={'seg-opt ' + (flow === o.value ? 'on' : '')}
                            aria-pressed={flow === o.value}
                            onClick={() => setFlow(o.value)}>
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            </section>
            )}

            {/* ─── PAÍSES (país reporter / parceiro) — FUNCTIONAL server-side filter, COMTRADE
                 only. Two multi-selects over the /api/countries universe: reporter = de quem é o
                 comércio (padrão Brasil; "Selecionar tudo" = mundo), parceiro = a contraparte
                 (padrão todos). Picking re-fetches the snapshot like Fluxo. ─── */}
            {hasCountries && countries && (
            <section className="fm-section">
              <div className="fm-section-head">
                <div className="fm-section-head-l">
                  <span className="fm-section-label">Países</span>
                  <span className="fm-cascade-hint">
                    Reporter = de quem é o comércio (padrão Brasil) · Parceiro = contraparte (padrão todos)
                  </span>
                </div>
                <span className="fm-section-meta">
                  {reporters.size >= reporterUniverse.length
                    ? 'mundo'
                    : `${reporters.size} reporter${reporters.size === 1 ? '' : 's'}`}
                  {' · '}
                  {partners.size === 0 || partners.size >= partnerUniverse.length
                    ? 'todos os parceiros'
                    : `${partners.size} parceiro${partners.size === 1 ? '' : 's'}`}
                </span>
              </div>
              <div className="fm-section-inner">
                <div className="fm-geo-grid cols-2">
                  <GeoColumn
                    title="País reporter" items={reporterUniverse}
                    keyAttr="iso" displayAttr="name" getMeta={(x) => x.iso}
                    selected={reporters} setSelected={setReporters}
                    search={qReporters} setSearch={setQReporters}
                    emptyAllNote="Nenhum reporter selecionado — o padrão (Brasil) será aplicado."
                  />
                  <GeoColumn
                    title="País parceiro" items={partnerUniverse}
                    keyAttr="iso" displayAttr="name" getMeta={(x) => x.iso}
                    selected={partners} setSelected={setPartners}
                    search={qPartners} setSearch={setQPartners}
                    emptyAllNote="Todos os parceiros (nenhum recorte)."
                  />
                </div>
              </div>
            </section>
            )}

            {/* ─── REGIME ADUANEIRO (customs procedure) — server-side, COMTRADE only.
                 Like Fluxo, picking a regime re-fetches the snapshot narrowed to that
                 customs_code. 'all' sums every regime (the bilateral total). ~86% of
                 trade is reported only at C00, so most cuts land in "Todos / C00". ─── */}
            {hasRegime && regimeOptions && (
            <section className="fm-section">
              <div className="fm-section-head">
                <div className="fm-section-head-l">
                  <span className="fm-section-label">Regime aduaneiro</span>
                  <span className="fm-cascade-hint">C00 = todos os regimes · ~86% dos registros (94% do valor) só é reportado nesse nível</span>
                </div>
                <span className="fm-section-meta">
                  {customs === 'all'
                    ? 'todos os regimes'
                    : ((regimeOptions.find(o => o.value === customs) || {}).label || '')}
                </span>
              </div>
              <div className="fm-section-inner">
                <div className="seg wrap">
                  {regimeOptions.map(o => (
                    <button key={o.value} type="button"
                            className={'seg-opt ' + (customs === o.value ? 'on' : '')}
                            aria-pressed={customs === o.value}
                            onClick={() => setCustoms(o.value)}>
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            </section>
            )}

            {/* ─── TIPO DE MERCADO (natureza econômica) — server-side, COMTRADE only.
                 consumo/processamento seed-classified per (regime × fluxo). 'all' sums
                 every purpose. Pairs with no natureza are excluded from a specific pick. ─── */}
            {hasMarket && marketOptions && (
            <section className="fm-section">
              <div className="fm-section-head">
                <div className="fm-section-head-l">
                  <span className="fm-section-label">Tipo de mercado</span>
                  <span className="fm-cascade-hint">natureza econômica classificada por regime × fluxo, editável em Tipo de Mercado (Engenharia de atributos)</span>
                </div>
                <span className="fm-section-meta">
                  {market === 'all'
                    ? 'todos os mercados'
                    : ((marketOptions.find(o => o.value === market) || {}).label || '')}
                </span>
              </div>
              <div className="fm-section-inner">
                <div className="seg">
                  {marketOptions.map(o => (
                    <button key={o.value} type="button"
                            className={'seg-opt ' + (market === o.value ? 'on' : '')}
                            aria-pressed={market === o.value}
                            onClick={() => setMarket(o.value)}>
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            </section>
            )}

            {/* ─── 02 · PERÍODO + FINANCEIRO ────────────────── */}
            <section className="fm-section">
              <div className="fm-section-head">
                <div className="fm-section-head-l">
                  <span className="fm-section-label"><span className="fm-section-num">02</span>Período</span>
                </div>
                <span className="fm-section-meta">
                  {formatMonth(startDate)}–{formatMonth(endDate)}
                </span>
              </div>
            <div className="fm-row-2 fm-row-solo">
              {/* PERÍODO */}
              <div className="fm-col">
                <div className="fm-col-head">
                  <span className="fm-section-label">Período de referência</span>
                  <span className="fm-section-meta">
                    {quickRange ? <strong>{QUICK_RANGES.find(r => r.id === quickRange).label}</strong> : 'Intervalo personalizado'}
                  </span>
                </div>

                <div className="fm-quick">
                  {QUICK_RANGES.map(r => (
                    <button key={r.id}
                            className={quickRange === r.id ? 'on' : ''}
                            onClick={() => applyQuick(r.id)}
                            type="button">
                      {r.id === 'all' ? 'Tudo' : 'Últimos ' + r.label}
                    </button>
                  ))}
                </div>

                <div className="fm-date-row">
                  <div className="fm-date-field">
                    <label htmlFor="fm-start">Início</label>
                    <input id="fm-start" className="fm-date" type="month"
                           value={startDate} min={`${yearStart}-01`} max={endDate}
                           onChange={(e) => onDateChange('start', e.target.value)}/>
                  </div>
                  <div className="fm-arrow">{I.arrow}</div>
                  <div className="fm-date-field">
                    <label htmlFor="fm-end">Fim</label>
                    <input id="fm-end" className="fm-date" type="month"
                           value={endDate} min={startDate} max={`${yearEnd}-12`}
                           onChange={(e) => onDateChange('end', e.target.value)}/>
                  </div>
                </div>
              </div>
            </div>
            </section>

            {/* ─── 03 · GEOGRAFIA (4 cascading columns) ────── */}
            {hasGeo && (
            <section className="fm-section">
              <div className="fm-section-head">
                <div className="fm-section-head-l">
                  <span className="fm-section-label"><span className="fm-section-num">03</span>Geografia</span>
                  <span className="fm-cascade-hint">
                    {I.cascade} Seleção em cascata · nação ▸ região ▸ estado{showMunis ? ' ▸ meso/microrregião · inter/imediata ▸ município' : ''}
                  </span>
                </div>
                <span className="fm-section-meta">
                  <strong>{nations.size}</strong> {nations.size === 1 ? 'nação' : 'nações'} ·{' '}
                  <strong>{regions.size}</strong> {regions.size === 1 ? 'região' : 'regiões'} ·{' '}
                  <strong>{states.size}</strong> {states.size === 1 ? 'UF' : 'UFs'}
                  {showMunis && (muniUniverseLive
                    ? <>{' '}·{' '}<strong>{munis.size}</strong> {munis.size === 1 ? 'município' : 'municípios'}</>
                    : <>{' '}·{' '}<span className="fm-soon-inline">municípios em breve</span></>)}
                </span>
              </div>

              <div className="fm-section-inner">
              <div className="fm-geo-grid cols-3">
                <GeoColumn
                  title="Nações"
                  items={NATIONS}
                  keyAttr="iso"
                  displayAttr="name"
                  getMeta={(x) => x.iso}
                  selected={nations}
                  setSelected={setNations}
                  search={qNations}
                  setSearch={setQNations}
                />
                <GeoColumn
                  title="Regiões"
                  items={eligibleRegions}
                  keyAttr="id"
                  displayAttr="name"
                  getMeta={(x) => x.id}
                  selected={regions}
                  setSelected={setRegions}
                  search={qRegions}
                  setSearch={setQRegions}
                  disabledReason={nations.size === 0 ? 'Selecione ao menos uma nação.' : null}
                />
                <GeoColumn
                  title="Estados"
                  items={eligibleStates}
                  keyAttr="uf"
                  displayAttr="name"
                  getMeta={(x) => x.uf}
                  selected={states}
                  setSelected={setStates}
                  search={qStates}
                  setSearch={setQStates}
                  disabledReason={eligibleRegions.length === 0 || regions.size === 0 ? 'Selecione ao menos uma região.' : null}
                />
              </div>

              {/* FILT-1: the 4 sub-UF levels + Município used to render as 4 MORE
                  always-open columns (8 total, two rows on desktop, eight stacked
                  scrollers on a phone) even though none of them mean anything before
                  a UF is picked. Collapsed by default behind this disclosure — auto-
                  expanded by the geo-seed effect above when the APPLIED filter already
                  narrows one, so a shared/deep-linked sub-UF selection is never hidden
                  from whoever opens the modal. */}
              {showMunis && (
              <div className="fm-subuf">
                <button
                  type="button"
                  className="fm-subuf-toggle"
                  aria-expanded={subUfExpanded}
                  onClick={() => setSubUfExpanded(!subUfExpanded)}
                >
                  <span aria-hidden="true">{subUfExpanded ? '▾' : '▸'}</span>
                  Refinar dentro da UF — mesorregião, microrregião, região intermediária/imediata, município
                  {subUfNarrowing && <span className="fm-subuf-badge">recorte ativo</span>}
                </button>

                {subUfExpanded && (
                <div className="fm-subuf-panel">
                  {/* FILT-2: the two IBGE divisions are ALTERNATIVE ways to slice the
                      same UF (not steps of one chain) — grouped + labelled so that
                      isn't left to the cascade-hint pill alone to explain. A município
                      passes iff it clears EVERY active facet across BOTH. */}
                  <p className="fm-subuf-note">
                    As duas divisões abaixo recortam o mesmo estado de formas
                    independentes — clássica (mesorregião/microrregião) e atual
                    (região intermediária/imediata). Um recorte em uma NÃO precisa de
                    um recorte na outra; um município só entra na seleção se passar
                    por todos os recortes ativos, nas duas.
                  </p>

                  <div className="fm-subuf-division">
                    <div className="fm-subuf-division-head">Divisão clássica (1990)</div>
                    <div className="fm-geo-grid cols-2">
                      <GeoColumn
                        title="Mesorregiões"
                        items={mesoItems}
                        keyAttr="code"
                        displayAttr="name"
                        getMeta={(x) => x.code}
                        selected={mesos}
                        setSelected={setMesos}
                        search={qMesos}
                        setSearch={setQMesos}
                        emptyAllNote="Todas as mesorregiões (nenhum recorte)."
                        disabledReason={
                          !muniUniverseLive ? 'Carregando malha do IBGE…'
                            : states.size === 0 ? 'Selecione ao menos um estado.' : null
                        }
                      />
                      <GeoColumn
                        title="Microrregiões"
                        items={microItems}
                        keyAttr="code"
                        displayAttr="name"
                        getMeta={(x) => x.code}
                        selected={micros}
                        setSelected={setMicros}
                        search={qMicros}
                        setSearch={setQMicros}
                        emptyAllNote="Todas as microrregiões (nenhum recorte)."
                        disabledReason={
                          !muniUniverseLive ? 'Carregando malha do IBGE…'
                            : states.size === 0 ? 'Selecione ao menos um estado.' : null
                        }
                      />
                    </div>
                  </div>

                  <div className="fm-subuf-division">
                    <div className="fm-subuf-division-head">Divisão atual (2017)</div>
                    <div className="fm-geo-grid cols-2">
                      <GeoColumn
                        title="Reg. intermediárias"
                        items={interItems}
                        keyAttr="code"
                        displayAttr="name"
                        getMeta={(x) => x.code}
                        selected={inters}
                        setSelected={setInters}
                        search={qInters}
                        setSearch={setQInters}
                        emptyAllNote="Todas as regiões intermediárias (nenhum recorte)."
                        disabledReason={
                          !muniUniverseLive ? 'Carregando malha do IBGE…'
                            : states.size === 0 ? 'Selecione ao menos um estado.' : null
                        }
                      />
                      <GeoColumn
                        title="Reg. imediatas"
                        items={imediataItems}
                        keyAttr="code"
                        displayAttr="name"
                        getMeta={(x) => x.code}
                        selected={imediatas}
                        setSelected={setImediatas}
                        search={qImediatas}
                        setSearch={setQImediatas}
                        emptyAllNote="Todas as regiões imediatas (nenhum recorte)."
                        disabledReason={
                          !muniUniverseLive ? 'Carregando malha do IBGE…'
                            : states.size === 0 ? 'Selecione ao menos um estado.' : null
                        }
                      />
                    </div>
                  </div>

                  <div className="fm-subuf-muni">
                    <GeoColumn
                      title="Municípios"
                      items={eligibleMunis}
                      keyAttr="code"
                      displayAttr="name"
                      getMeta={(x) => x.uf}
                      selected={munis}
                      setSelected={setMunis}
                      search={qMunis}
                      setSearch={setQMunis}
                      emptyAllNote="Todos os municípios (nenhum recorte)."
                      // Município is LIVE via the IBGE mesh (code-keyed). Gate only while
                      // the mesh loads, or when its parent UF level is empty.
                      disabledReason={
                        !muniUniverseLive
                          ? 'Carregando malha do IBGE…'
                          : eligibleStates.length === 0 || states.size === 0
                            ? 'Selecione ao menos um estado.'
                            : null
                      }
                    />
                  </div>

                  <div className="fm-geo-foot">
                    <span className="fm-section-meta">
                      {/* Footer: the IBGE mesh universe (full ~5570), driving the
                          município + the two parallel sub-UF divisions. */}
                      {muniUniverseLive
                        ? `Malha IBGE: ${MUNIS.length} municípios · mesorregião/microrregião + região intermediária/imediata.`
                        : 'Carregando a malha municipal do IBGE…'}
                    </span>
                  </div>
                </div>
                )}
              </div>
              )}
              </div>
            </section>
            )}

            {/* ─── 04 · QUALIDADE DOS DADOS (gated on the `quality` capability) ─── */}
            {hasQuality && (
            <section className="fm-section">
              <div className="fm-section-head">
                <div className="fm-section-head-l">
                  <span className="fm-section-label"><span className="fm-section-num">{hasGeo ? '04' : '03'}</span>Qualidade dos dados · <span className="mono lowercase">data_quality_flag</span></span>
                  <SearchInput value={qFlags} onChange={setQFlags} placeholder="Buscar flag…"/>
                </div>
                <span className="fm-section-meta">
                  <strong>{flags.size}</strong> de {QUALITY.length} selecionadas
                </span>
              </div>

              <div className="fm-section-inner">
                <div className="fm-grid-scroll">
                  <div className="fm-grid">
                    {filteredFlags.length === 0 ? (
                      <div className="fm-empty-grid">Nenhuma flag corresponde a “{qFlags}”.</div>
                    ) : filteredFlags.map(q => {
                      const on = flags.has(q.flag);
                      return (
                        <label key={q.flag} className={'fm-check' + (on ? ' is-on' : '')}>
                          <input type="checkbox" checked={on}
                                 onChange={() => setFlags(s => toggleIn(s, q.flag))}/>
                          <span className="fm-name">{q.label}</span>
                          <span className="fm-code mono">{q.flag}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <BulkActions
                  all={()    => setFlags(prev => new Set([...prev, ...filteredFlags.map(q => q.flag)]))}
                  none={()   => { const vis = new Set(filteredFlags.map(q => q.flag)); setFlags(prev => new Set([...prev].filter(f => !vis.has(f)))); }}
                  invert={() => setFlags(prev => { const n = new Set(prev); filteredFlags.forEach(q => n.has(q.flag) ? n.delete(q.flag) : n.add(q.flag)); return n; })}
                  selectedCount={filteredFlags.filter(q => flags.has(q.flag)).length}
                  totalCount={filteredFlags.length}
                />
              </div>
            </section>
            )}

            </div>

            {/* FOOTER */}
            <footer className="fm-foot">
              <div className="fm-foot-info">
                {/* Read the Gold table from the LIVE provenance (dataStore.meta →
                    /api/source-meta overlay), not the static bancoTable/registry
                    literal — so a backend rename of the served table propagates here. */}
                Os filtros serão aplicados sobre <strong>{window.dataStore.meta(bancoMeta?.id || banco).table || 'gold_pevs_production'}</strong>
                <span className="fm-dot"></span>
                {bancoMeta?.prov?.refresh ? `Refresh ${bancoMeta.prov.refresh}` : 'Atualização diária às 06h00 BRT'}
              </div>
              {/* "Redefinir campos" (not "Restaurar padrão") makes explicit that it
                  only resets the DRAFT form to defaults — the reset takes effect on
                  "Aplicar filtros", so Cancelar/Esc afterwards discards it (N3). */}
              <button className="btn-ghost" onClick={restoreDefaults}>Redefinir campos</button>
              <button className="btn-secondary" onClick={close}>Cancelar</button>
              <button className="btn-primary" onClick={applyAndClose}>Aplicar filtros</button>
            </footer>
            </>
            )}
      </div>
    </div>
  );
}

// ----- Preview body for soon bancos -------------------------------
// Renders the planned filter dimensions read-only, grouped by tier,
// so the researcher sees what they'll be able to filter once live.
function FilterPreview({ schema, banco, onClose }) {
  const TIER = window.TIER_LABEL || {};
  const dims = (schema && schema.dims) || [];
  const tiers = ['universal', 'shared', 'specific'];
  const byTier = tiers
    .map(t => ({ tier: t, items: dims.filter(d => d.tier === t) }))
    .filter(g => g.items.length > 0);

  return (
    <div className="fm-body fm-preview">
      <div className="fm-preview-banner">
        <span className="fm-preview-badge">Em breve</span>
        <span>
          Este banco ainda não foi liberado no backend. Abaixo estão as
          dimensões que estarão disponíveis para filtragem assim que a
          tabela <code>{window.bancoTable(banco?.id)}</code> for publicada
          {banco?.maturityDate ? ` (previsão ${banco.maturityDate})` : ''}.
        </span>
      </div>

      {byTier.map(g => (
        <section key={g.tier} className="fm-preview-group">
          <div className="fm-preview-group-head">
            <span className="fm-preview-tier">{TIER[g.tier] || g.tier}</span>
            <span className="fm-preview-tier-meta">{g.items.length} dimensão(ões)</span>
          </div>
          <div className="fm-preview-grid">
            {g.items.map(d => (
              <div key={d.id} className="fm-preview-dim">
                <div className="fm-preview-dim-head">
                  <span className="fm-preview-dim-label">{d.label}</span>
                  <span className="fm-preview-dim-type">{d.type}</span>
                </div>
                <code className="fm-preview-dim-col">{d.column}</code>
                <p className="fm-preview-dim-hint">{d.hint}</p>
                {d.options && (
                  <div className="fm-preview-opts">
                    {d.options.map(o => <span key={o} className="fm-preview-opt">{o}</span>)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}

      <footer className="fm-foot">
        <div className="fm-foot-info">
          {dims.length} dimensões previstas · scoped a <strong>{window.bancoTable(banco?.id)}</strong>
        </div>
        <button className="btn-primary" onClick={onClose}>Entendi</button>
      </footer>
    </div>
  );
}



function formatMonth(iso) {
  if (!iso) return '—';
  const [y, m] = iso.split('-');
  return `${m}/${y}`;
}

window.FilterMenu = FilterMenu;
// Test-only export surface (read solely by FilterMenu.cov.test.jsx): exposes the
// SH-prefix grouping so it can be unit-tested independently of the component. The
// live path calls buildProductTree() directly as a local function (see the useMemo
// above); no production code reads window.buildProductTree.
window.buildProductTree = buildProductTree;
