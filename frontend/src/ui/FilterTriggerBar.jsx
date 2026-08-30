// FilterTriggerBar — active-filter chip row that opens the FilterMenu modal.
// Replaces the legacy <FilterBar> dropdown row.

function FilterTriggerBar({ summary, onOpen, live = true, banco = null }) {
  // Soon banco → slim preview trigger (no real filters/data to export yet).
  if (!live) {
    return (
      <div className="fm-trigger-bar preview">
        <div className="fm-tb-chips">
          <span className="fm-tb-label">Filtros</span>
          <span className="fm-tb-preview-note">
            Disponíveis quando <strong>{banco ? banco.short : 'o banco'}</strong> for liberado
            {banco?.maturityDate ? ` · previsão ${banco.maturityDate}` : ''}
          </span>
        </div>
        <div className="fm-tb-acoes">
        <button className="fm-edit-btn" onClick={onOpen}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>
          </svg>
          Ver dimensões previstas
        </button>
        </div>
      </div>
    );
  }

  // Chips are CAPABILITY-DRIVEN: only the dimensions the active banco actually
  // exposes get a chip (the menu shows the same set), so we never label a filter
  // the banco can't use. Período is universal; Fluxo (export/import) is a server-
  // side filter shown only for trade bancos. Faixa de valor is intentionally absent
  // — it has no backed filter path, so it is hidden rather than shown inert.
  const provides = (banco && banco.provides) || [];
  const has = (c) => provides.includes(c);
  // The five trade-axis labels come from the shared resolver (scopeChips.js) — the
  // ABNT citation states the same recorte from the same rule, so the chip row and the
  // reference cannot describe one selection two different ways.
  const trade = window.axisScopeChips ? window.axisScopeChips(summary, banco) : {};
  const origemChip   = trade.origem   && trade.origem.label;
  const flowChip     = trade.flow     && trade.flow.label;
  const regimeOpts   = !!trade.regime;
  const regimeChip   = trade.regime   && trade.regime.label;
  const marketOpts   = !!trade.mercado;
  const marketChip   = trade.mercado  && trade.mercado.label;
  const hasCountry   = !!trade.reporter;
  const reporterChip = trade.reporter && trade.reporter.label;
  const partnerChip  = trade.parceiro && trade.parceiro.label;

  const chips = [
    has('product') && { k: 'Produtos',  v: summary.products },
    { k: 'Período', v: summary.period },
    summary.nivel  && { k: 'Industrialização', v: summary.nivel },
    origemChip     && { k: 'Origem',     v: origemChip },
    has('flow')    && { k: 'Fluxo',      v: flowChip },
    regimeOpts     && { k: 'Regime',     v: regimeChip },
    marketOpts     && { k: 'Mercado',    v: marketChip },
    hasCountry     && { k: 'Reporter',   v: reporterChip },
    hasCountry     && { k: 'Parceiro',   v: partnerChip },
    has('geo')     && { k: 'Geografia',  v: summary.geo },
    has('quality') && { k: 'Qualidade',  v: summary.quality },
  ].filter(Boolean);

  // Duas áreas, não uma fila só: os chips ficam num contêiner que quebra sozinho e a ação
  // num contêiner que não quebra. Antes tudo era irmão numa `flex-wrap`, então quando os
  // chips enchiam a linha o botão descia junto com o último chip — a posição do "Editar
  // filtros" dependia de QUANTOS chips o banco expõe, e mudava de perspectiva para
  // perspectiva. Agora ele ancora no topo à direita do bloco, em qualquer banco.
  return (
    <div className="fm-trigger-bar">
      <div className="fm-tb-chips">
        <span className="fm-tb-label">Filtros ativos</span>
        {chips.map((c, i) => (
          <span key={i} className="fm-chip-filter">
            <span className="fm-chip-k">{c.k}</span>{c.v}
          </span>
        ))}
      </div>
      {/* "Exportar CSV" saiu daqui para o topbar (AppShell), junto de Citar/Compartilhar:
          os três levam o MESMO estado embora — como citação, como URL e como arquivo — e o
          export é montado de {view, banco, filtros, convenções}, dos quais o filtro é só
          uma parte. Aqui ele era o único botão sólido de uma faixa que só descreve estado,
          e sua posição vertical variava com a altura dos chips. */}
      <div className="fm-tb-acoes">
        <button className="fm-edit-btn" onClick={onOpen}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 20h4l10-10-4-4L4 16zM14 6l4 4"/>
          </svg>
          Editar filtros
        </button>
      </div>
    </div>
  );
}

window.FilterTriggerBar = FilterTriggerBar;
