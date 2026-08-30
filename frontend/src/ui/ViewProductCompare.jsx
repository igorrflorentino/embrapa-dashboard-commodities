// ViewProductCompare — compare 2–4 commodities side by side.
// Normalized series (base 100), accumulated change, CAGR, and pairwise
// correlation. Honours active filters (selectable products limited to
// the basket) and conventions (currency for the absolute table column).

const { useState: usePCState } = React;

function ViewProductCompare({ summary, conventions, database }) {
  const conv     = conventions || window.DEFAULT_CONVENTIONS;

  const filtered  = window.applyFilters(summary || {}, database);
  const available = filtered.selectedProducts.filter(c => filtered.allProductTS[c]);

  const COLORS = ['var(--viz-1)', 'var(--viz-3)', 'var(--viz-5)', 'var(--viz-7)'];
  const MAX = 4;

  // Default: top 3 by latest value
  const defaultSel = available
    .map(c => ({ c, v: filtered.allProductTS[c].slice(-1)[0]?.v || 0 }))
    .sort((a, b) => b.v - a.v)
    .slice(0, 3)
    .map(x => x.c);
  const [sel, setSel] = usePCState(defaultSel);

  // Keep selection valid against the current basket
  const active = sel.filter(c => available.includes(c)).slice(0, MAX);
  const activeSel = active.length ? active : defaultSel;

  const toggle = (c) => {
    setSel(prev => {
      const cur = prev.filter(x => available.includes(x));
      if (cur.includes(c)) return cur.filter(x => x !== c);
      if (cur.length >= MAX) return cur; // cap at 4
      return [...cur, c];
    });
  };

  const yearStart = filtered.yearStart, yearEnd = filtered.yearEnd;

  // Build per-product windows + metrics. A STOCK (herd) has no value → normalize and
  // rank on headcount (q); flows on value (v). Indexing (base 100) keeps the two
  // comparable as GROWTH even when the absolute magnitudes are not.
  const items = activeSel.map((code, i) => {
    const prod = filtered.products.find(p => p.code === code);
    const win = filtered.allProductTS[code].filter(d => d.y >= yearStart && d.y <= yearEnd);
    const isStock = prod.measure_kind === 'stock' || !win.some(d => d.v > 0);
    const mkey = isStock ? 'q' : 'v';
    const m0 = win[0]?.[mkey] || 0, mT = win[win.length - 1]?.[mkey] || 0;
    return {
      code, prod, win, isStock, mkey,
      color: COLORS[i % COLORS.length],
      m0, mT,
      vT: win[win.length - 1]?.v || 0,
      qT: win[win.length - 1]?.q || 0,
      cagr: window.cagrPct(m0, mT, window.spanYears(win)),
      accum: window.accumPct(m0, mT),
    };
  });

  // O rótulo de exibição, desambiguado UMA vez e reusado nos três lugares que o mostram
  // (legenda, tabela de métricas, nome da série). Escolher as DUAS metades do mesmo produto
  // é possível — o seletor de cesta mostra os códigos —, e sem isto as três superfícies
  // exibiriam "Carvão vegetal" duas vezes, sem dizer qual é qual. A matriz de correlação
  // logo abaixo já mostrava o CÓDIGO e por isso nunca teve o problema.
  const rotulos = window.labelProductRows(items.map((it) => it.prod), database);
  items.forEach((it, i) => { it.label = rotulos[i].name; });

  // Normalized series (base 100 at yearStart) — on each product's own measure, so a
  // value-less herd traces real growth instead of a flat-zero line.
  const normSeries = items.map(it => ({
    name: it.label,
    color: it.color,
    data: it.win.map(d => ({ y: d.y, v: it.m0 ? ((d[it.mkey] || 0) / it.m0) * 100 : 0 })),
  }));

  // Pairwise Pearson correlation on YoY growth, aligned BY YEAR (not array index): a
  // product with an internal year gap would otherwise correlate mismatched years.
  // Correlate on headcount for an all-herd basket, on value otherwise.
  const corrKey = items.every(it => it.isStock) ? 'q' : 'v';
  const corrMatrix = items.map(a => items.map(b => window.pearsonByYear(a.win, b.win, corrKey)));
  const corrColor = window.corrColor;

  // Indexing makes mixed families / stock+flow comparable as growth, but their ABSOLUTE
  // magnitudes are not — flag that honestly above the table.
  const mixedBasis = new Set(items.map(it => it.prod.family)).size > 1
    || new Set(items.map(it => it.isStock)).size > 1;
  // The normalized series indexes value for flows, but headcount for an all-herd basket —
  // so label it honestly instead of hardcoding "do valor".
  const allStock = items.length > 0 && items.every(it => it.isStock);
  const indexBasis = allStock ? 'do efetivo (cabeças)' : 'do valor';

  return (
    <>
      {/* Selector */}
      <div className="pp-selector">
        <span className="pp-selector-label">Comparar produtos <small className="pc-cap">(até {MAX})</small></span>
        <div className="pp-chips">
          {available.map(c => {
            const p = filtered.products.find(x => x.code === c);
            const on = activeSel.includes(c);
            const idx = activeSel.indexOf(c);
            const atCap = !on && activeSel.length >= MAX;
            return (
              <button key={c}
                      className={'pp-chip ' + (on ? 'on' : '') + (atCap ? ' disabled' : '')}
                      onClick={() => !atCap && toggle(c)}
                      style={on ? { background: COLORS[idx % COLORS.length], borderColor: COLORS[idx % COLORS.length], color: '#fff' } : null}
                      title={atCap ? `Máximo de ${MAX} produtos` : p.name}>
                <span className={'pp-chip-fam ' + p.family}></span>
                {p.name}
              </button>
            );
          })}
        </div>
      </div>

      {/* Normalized series */}
      <div className="card">
        <window.SectionHeader
          overline={`Séries normalizadas · base 100 em ${yearStart}`}
          title={`Evolução relativa ${indexBasis}`}
          action={<span className="caption">{items.length} produtos</span>}
        />
        <window.MultiLineChart series={normSeries} label={`índice (${yearStart}=100)`} valueKey="v" height={300} showLegend={false} />
        <div className="pc-legend">
          {items.map(it => (
            <span key={it.code} className="pc-legend-item">
              <span className="pc-legend-dot" style={{ background: it.color }}></span>
              {it.label}
            </span>
          ))}
        </div>
      </div>

      {/* Metrics table */}
      <div className="card">
        <window.SectionHeader
          overline={`Métricas comparativas · ${yearStart}–${yearEnd}`}
          title="Crescimento e magnitude"
        />
        {mixedBasis && (
          <p className="caption" style={{ margin: '0 2px 8px' }}>
            ⓘ A seleção mistura famílias ou estoque/fluxo: as séries são indexadas (base 100) e
            comparáveis como crescimento, mas as magnitudes absolutas (coluna ao lado) não são.
          </p>
        )}
        <div className="pc-table-wrap">
          <table className="pc-table">
            <thead>
              <tr>
                <th>Produto</th>
                <th className="num">Magnitude ({yearEnd})</th>
                <th className="num">Variação acumulada</th>
                <th className="num">CAGR (a.a.)</th>
                <th className="num">Família</th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.code}>
                  <td>
                    <span className="pc-row-dot" style={{ background: it.color }}></span>
                    {it.label}
                  </td>
                  <td className="num tnum">{it.isStock ? window.formatCountQty(it.qT, conv) : window.formatValue(it.vT * 1e6, conv)}</td>
                  <td className="num tnum" style={{ color: it.accum >= 0 ? 'var(--ok)' : 'var(--err)' }}>
                    {window.fmtSigned(it.accum, 0)}
                  </td>
                  <td className="num tnum" style={{ color: it.cagr >= 0 ? 'var(--ok)' : 'var(--err)' }}>
                    {window.fmtSigned(it.cagr, 1)}
                  </td>
                  <td className="num">{window.UNIT_FAMILIES[it.prod.family].label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Correlation matrix */}
      <div className="card">
        <window.SectionHeader
          overline="Correlação cruzada · variação interanual"
          title="Quão sincronizadas são as trajetórias"
          action={<span className="caption">Pearson · −1 a +1</span>}
        />
        {items.length < 2 ? (
          <p className="caption" style={{ padding: '20px 4px', textAlign: 'center' }}>
            Selecione ao menos 2 produtos para calcular correlação.
          </p>
        ) : (
          <div className="pc-corr-wrap">
            <table className="pc-corr">
              <thead>
                <tr>
                  <th></th>
                  {items.map(it => (
                    <th key={it.code} title={it.prod.name}>
                      <span className="pc-corr-dot" style={{ background: it.color }}></span>
                      {it.prod.code}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((rowIt, i) => (
                  <tr key={rowIt.code}>
                    <th title={rowIt.prod.name}>
                      <span className="pc-corr-dot" style={{ background: rowIt.color }}></span>
                      {rowIt.prod.name}
                    </th>
                    {items.map((colIt, j) => {
                      const r = corrMatrix[i][j];
                      return (
                        <td key={colIt.code}
                            className="tnum"
                            style={{ background: i === j ? 'var(--bg-surface-2)' : corrColor(r), color: Math.abs(r) > 0.6 ? '#fff' : 'var(--fg-1)' }}>
                          {i === j ? '—' : r.toFixed(2).replace('.', ',')}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="caption pc-corr-note">
              Verde: trajetórias que sobem e descem juntas. Vermelho: movimentos opostos.
            </p>
          </div>
        )}
      </div>
    </>
  );
}

window.ViewProductCompare = ViewProductCompare;
