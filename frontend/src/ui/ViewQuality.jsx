// ViewQuality — data-quality diagnostics across the banco.
// Scope is stated HONESTLY per panel (the backend exposes quality only as a
// banco-level summary, not per product/UF/year): the flag KPI strip is the banco's
// FULL-coverage distribution (all products, UFs and years), narrowed only by the
// flag chips; the per-product / per-UF panels are a fixed snapshot summary, narrowed
// by the product / UF chips but NOT year-windowed; only the time-series panels honour
// the selected year window. We never present a whole-acervo figure as if it were
// scoped to the active product/UF/year filter.

// Maps each data_quality_flag id to its key in window.QUALITY_TS (the qualityTs
// contract keys — see contracts.js). Every real Gold flag is just the lowercased
// id; the map is kept explicit so a future flag must be added deliberately rather
// than silently rendering flat-zero in the temporal stack.
const QTS_KEY = {
  OK: 'ok',
  MISSING_VALUE: 'missing_value', MISSING_QUANTITY: 'missing_quantity',
  MISSING_WEIGHT: 'missing_weight', INCOMPLETE: 'incomplete',
  OUTLIER_VALUE: 'outlier_value', OUTLIER_QUANTITY: 'outlier_quantity',
  PROBLEMATIC_VALUE: 'problematic_value', PROBLEMATIC_QUANTITY: 'problematic_quantity',
  // Reserved for a future auto-fill pipeline (0 today) — added deliberately so the
  // temporal stack resolves their series-key when a pipeline finally emits them.
  INFERRED_VALUE: 'inferred_value', INFERRED_QUANTITY: 'inferred_quantity',
  // PAM-only: planted < harvested area (a SIDRA source error surfaced in-product).
  AREA_INCONSISTENT: 'area_inconsistent',
};

function ViewQuality({ summary, database }) {
  const filtered = window.applyFilters(summary || {}, database);
  const flags    = filtered.qualityFlags;
  const ts       = filtered.qualityTs;
  const total    = flags.reduce((s, f) => s + f.count, 0) || 1;
  const okFlag   = flags.find(f => f.id === 'OK');
  const okCount  = okFlag ? okFlag.count : 0;

  // Plain-pt-BR description per flag (from the QUALITY_FLAGS registry) → hover tooltips
  // + the always-on legend panel below. Empty string when a flag has no desc.
  const flagDesc = (id) => (window.QUALITY_FLAGS.find(x => x.id === id) || {}).desc || '';

  const flagSet = new Set(flags.map(f => f.id));
  // Restrict per-product breakdown to selected products AND selected flags.
  // We zero out unselected flag columns and re-normalize each row.
  const selectedProductNames = new Set(
    filtered.selectedProducts
      .map(c => (filtered.products.find(p => p.code === c) || {}).name)
      .filter(Boolean)
  );
  const qaByProduct = filtered.qualityByProduct
    .filter(r => selectedProductNames.has(r.name))
    .map(r => {
      const row = { code: r.code, name: r.name };
      let sum = 0;
      window.QUALITY_FLAGS.forEach(f => {
        const v = flagSet.has(f.id) ? (r[f.id] || 0) : 0;
        row[f.id] = v; sum += v;
      });
      // re-normalize to 100% of the selected flag world
      if (sum > 0) window.QUALITY_FLAGS.forEach(f => { row[f.id] = row[f.id] / sum; });
      return row;
    });

  // Restrict geographic quality map to selected UFs. null = no filter (all);
  // explicit empty = none (consistent with the data layer).
  const stateSet = (summary && summary.states != null)
    ? new Set(summary.states) : null;
  const qaByUf = filtered.qualityByUf.filter(u => !stateSet || stateSet.has(u.uf));

  // Stock/flow facet: when the banco carries measure_kind (livestock), split the
  // per-product breakdown into Estoque (herd — value-less, so its quality story is the
  // HEADCOUNT: OK vs MISSING_QUANTITY) vs Fluxo (animal products — value + quantity, so
  // MISSING_VALUE applies). The two have structurally different flag profiles, so
  // reading them in one list blurs the diagnosis. Hook-free: measure_kind rides on
  // filtered.products (PPM-only); other bancos fall through to the single list.
  const mkOf = (code) => (filtered.products.find(p => p.code === code) || {}).measure_kind;
  const facetByMeasureKind = qaByProduct.some(r => mkOf(r.code));
  const stockRows = facetByMeasureKind ? qaByProduct.filter(r => mkOf(r.code) === 'stock') : [];
  const flowRows  = facetByMeasureKind ? qaByProduct.filter(r => mkOf(r.code) !== 'stock') : [];

  return (
    <>
      {/* Flag KPI strip */}
      <div className="qa-flag-row">
        {flags.length === 0 ? (
          <div className="qa-flag-card" style={{ gridColumn: '1 / -1' }}>
            <span className="qa-flag-label">Nenhuma flag selecionada nos filtros.</span>
          </div>
        ) : flags.map(f => (
          <div key={f.id} className="qa-flag-card" title={flagDesc(f.id)}>
            <div className="qa-flag-head">
              <span className="qa-dot" style={{ background: f.color }}></span>
              <span className="qa-flag-label">{f.label}</span>
            </div>
            <div className="qa-flag-val tnum" style={{ color: f.id === 'OK' ? 'var(--ok)' : 'var(--fg-1)' }}>
              {window.fmtPct(f.share)}
            </div>
            <div className="qa-flag-sub tnum">
              {f.count.toLocaleString('pt-BR')} linhas
            </div>
          </div>
        ))}
      </div>
      {flags.length > 0 && (
        <p className="caption" style={{ padding: '0 4px 4px', marginTop: -4 }}>
          Distribuição no <strong>acervo completo</strong> do banco (todos os produtos, UFs e anos),
          recortada apenas pelas <strong>flags</strong> selecionadas. Os filtros de produto, UF e ano
          não recortam estes percentuais — a evolução temporal abaixo respeita a janela de anos.
        </p>
      )}

      {/* Always-on taxonomy legend — documents EVERY flag (iterating the full registry,
          not the present-only `flags`), so the reserved INFERRED_* tiers and any tier
          with 0 linhas are still explained. This is the canonical "o que cada flag
          significa" reference in the Qualidade window. */}
      <details className="qa-flag-legend card">
        <summary className="qa-flag-legend-summary">
          <span>O que significa cada flag?</span>
          <span className="caption">{window.QUALITY_FLAGS.length} marcas de qualidade</span>
        </summary>
        <div className="qa-flag-legend-grid">
          {window.QUALITY_FLAGS.map(f => (
            <div key={f.id} className="qa-flag-legend-item">
              <span className="qa-dot" style={{ background: f.color }}></span>
              <div className="qa-flag-legend-text">
                <span className="qa-flag-legend-label">
                  {f.label}
                  {f.reserved && <span className="qa-flag-legend-badge">reservada</span>}
                </span>
                <span className="qa-flag-legend-desc caption">{f.desc}</span>
              </div>
            </div>
          ))}
        </div>
      </details>

      {/* Quality over time */}
      <div className="card">
        <window.SectionHeader
          overline="Evolução temporal · qualidade dos dados"
          title={`% de linhas íntegras (Normais) · ${filtered.yearStart}–${filtered.yearEnd}`}
          action={
            <span className="caption">
              {okCount ? okCount.toLocaleString('pt-BR') : '—'} de {total.toLocaleString('pt-BR')} linhas íntegras no acervo
            </span>
          }
        />
        {okFlag ? (
          <window.LineChart
            data={ts.map(d => ({ y: d.y, v: d.ok * 100 }))}
            label="% OK"
            valueKey="v"
            color="var(--ok)"
            height={240}
          />
        ) : (
          <p className="caption" style={{ padding: '24px 4px', textAlign: 'center' }}>
            Flag <code>OK</code> não está entre as selecionadas nos filtros.
          </p>
        )}
      </div>

      {/* Quality flag distribution by product */}
      <div className="card">
        <window.SectionHeader
          overline="Distribuição de flags · acervo"
          title="Por produto"
          action={<span className="caption">{qaByProduct.length} de {filtered.qualityByProduct.length} produtos</span>}
        />
        {qaByProduct.length === 0 ? (
          <p className="caption" style={{ padding: '24px 4px', textAlign: 'center' }}>
            Nenhum produto selecionado nos filtros.
          </p>
        ) : facetByMeasureKind ? (
          <>
            {stockRows.length > 0 && (
              <div className="qa-facet">
                <p className="caption" style={{ margin: '2px 2px 6px' }}>
                  <strong>Estoque · efetivo dos rebanhos</strong> — qualidade da contagem de cabeças
                  (um estoque não tem valor, então a flag é OK vs quantidade ausente).
                </p>
                <window.FlagBars rows={stockRows} flags={flags} labelKey="name" showLegend={false} />
              </div>
            )}
            {flowRows.length > 0 && (
              <div className="qa-facet" style={{ marginTop: 14 }}>
                <p className="caption" style={{ margin: '2px 2px 6px' }}>
                  <strong>Fluxo · produção de origem animal</strong> — qualidade de valor + quantidade
                  (leite, ovos, mel, lã).
                </p>
                <window.FlagBars rows={flowRows} flags={flags} labelKey="name" showLegend={false} />
              </div>
            )}
          </>
        ) : (
          <window.FlagBars rows={qaByProduct} flags={flags} labelKey="name" showLegend={false} />
        )}
        <div className="qa-legend">
          {flags.map(f => (
            <span key={f.id} className="qa-legend-item" title={flagDesc(f.id)}>
              <span className="qa-dot" style={{ background: f.color }}></span>
              {f.label}
            </span>
          ))}
        </div>
      </div>

      {/* Quality by UF (geo bancos only) */}
      {filtered.qualityByUf.length > 0 && (
      <div className="card">
        <window.SectionHeader
          overline="Qualidade geográfica · acervo"
          title="% de linhas não-íntegras por UF"
          action={<span className="caption">{qaByUf.length} de {filtered.qualityByUf.length} UFs</span>}
        />
        {/* Clicking a UF filters the dashboard to it (click again to clear) — safe
            here because qaByUf is itself narrowed by the state filter, so the map
            reacts to its own click. */}
        <window.BrazilTileMap
          data={qaByUf.map(u => ({ ...u, v: Math.round(u.not_ok * 1000) / 10 }))}
          valueKey="v"
          label="% ≠ OK"
          onSelect={window.tileSelectHandler && window.tileSelectHandler(summary)}
          selectedUf={window.selectedSingleUf && window.selectedSingleUf(summary)}
        />
        <p className="caption" style={{ padding: '8px 4px 0' }}>
          Participação de linhas não-íntegras no acervo do banco, por UF (todos os anos e produtos);
          recortada apenas pelo filtro de UF.
        </p>
      </div>
      )}

      {/* Stacked area of flag share over time */}
      {flags.length > 0 && (
        <div className="card">
          <window.SectionHeader
            overline="Composição temporal · flags"
            title={`Share por flag · ${filtered.yearStart}–${filtered.yearEnd}`}
          />
          <window.StackedArea
            series={flags.slice().reverse().map(f => ({
              code: f.id,
              name: f.label,
              color: f.color,
              data: ts.map(d => ({ y: d.y, v: (d[QTS_KEY[f.id] || f.id.toLowerCase()] || 0) * 100 })),
            }))}
            valueKey="v"
            label="% linhas"
            height={260}
            showLegend={false}
          />
          <div className="qa-legend">
            {flags.map(f => (
              <span key={f.id} className="qa-legend-item">
                <span className="qa-dot" style={{ background: f.color }}></span>
                {f.label}
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

window.ViewQuality = ViewQuality;
