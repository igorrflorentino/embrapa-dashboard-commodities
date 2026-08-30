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

  // A lista de chips vem do resolvedor compartilhado (scopeChips.js). Ela morava aqui, o
  // que fazia desta faixa o único lugar capaz de dizer qual é o recorte — e a janela de
  // confirmação do CSV precisa dizer a MESMA coisa. Duas cópias da regra é como as duas
  // superfícies passam a descrever uma seleção só de dois jeitos.
  const chips = window.activeFilterChips ? window.activeFilterChips(summary, banco) : [];

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
