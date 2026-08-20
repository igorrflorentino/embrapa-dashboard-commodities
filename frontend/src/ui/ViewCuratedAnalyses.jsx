// ViewCuratedAnalyses.jsx — the two Engenharia de Atributos analyses (Multi-fonte).
//   · ViewValueAdded   — exports split across the 8 industrialization levels (Commodity Pura
//                        → Manufaturado Especializado), from the researcher-editable per-code
//                        classification (subscribes to the enrichment store so editing
//                        re-renders it live).
//   · ViewMarketNature — COMTRADE value by economic purpose (consumo × processamento), from
//                        the researcher-editable (customs procedure × flow) matrix ("Tipo de
//                        Mercado"), carried as the serving mart's market_nature column. The
//                        analysis reflects a matrix edit after the next dbt build.
// Both read real Gold/COMTRADE data and degrade to an honest empty state when absent.

const { useState: useCaState, useEffect: useCaEffect } = React;

// Hoisted to module scope: it closes over nothing (series arrives via props). Defined
// inside the render body it was a NEW component type on every render, so React threw the
// legend away and rebuilt it instead of updating it (react-hooks/static-components).
function Legend({ series }) {
  return (
    <div className="pc-legend">
      {series.map(s => (
        <span key={s.name} className="pc-legend-item"><span className="pc-legend-dot" style={{ background: s.color }}></span>{s.name}</span>
      ))}
    </div>
  );
}

function useEnrichmentTick() {
  const [, force] = useCaState(0);
  useCaEffect(() => window.enrichment.subscribe(() => force(n => n + 1)), []);
}

const caNum = window.numBR, caPct = window.pctBR;

// ── Value added: exports across the 8 industrialization levels ─────────
function ViewValueAdded() {
  useEnrichmentTick();
  const [group, setGroup] = useCaState(null);
  // Per-UF scoping ('' = Brasil). The COMEX export side honours it.
  const [uf, setUf] = useCaState('');
  const data = window.valueAddedAnalysis(group, uf ? [uf] : undefined);
  const levels = data.levels || [];
  const last = data.series[data.series.length - 1];

  // One chart series per PRESENT level, in ordinal order (least→most processed),
  // coloured + labelled from the shared ENRICH_LEVELS registry.
  const levelMeta = (id) => window.ENRICH_LEVELS.find(l => l.id === id) || { label: id, color: 'var(--fg-3)' };
  const mkSeries = (byLevel) => levels.map(id => ({ name: levelMeta(id).label, color: levelMeta(id).color, data: (byLevel || {})[id] || [] }));
  const areaSeries = mkSeries(data.byLevel);       // value · US$ bi
  const areaSeriesW = mkSeries(data.byLevelWeight); // volume · mil t
  const priceSeries = mkSeries(data.byLevelPrice);  // unit price · US$/kg

  const predom = data.predominant;
  const predomLabel = predom ? levelMeta(predom.level).label : '—';


  return (
    <>
      <window.LoadErrorNote error={data.loadError} />
      <div className="pp-selector">
        <span className="pp-selector-label">Agrupamento</span>
        <div className="pp-chips">
          <button className={'pp-chip ' + (!group ? 'on' : '')} onClick={() => setGroup(null)}
            style={!group ? { background: 'var(--embrapa-green)', borderColor: 'var(--embrapa-green)', color: '#fff' } : null}>Todas curadas</button>
          {window.ENRICH_GROUPS.map(g => {
            const on = group === g.id;
            return (
              <button key={g.id} className={'pp-chip ' + (on ? 'on' : '')} onClick={() => setGroup(g.id)}
                style={on ? { background: 'var(--embrapa-green)', borderColor: 'var(--embrapa-green)', color: '#fff' } : null}>{g.label}</button>
            );
          })}
        </div>
      </div>

      <window.UfScopePicker value={uf} onChange={setUf} />

      <div className="kpi-row">
        <window.KpiCardSpark label="Níveis presentes" value={levels.length} sub={`de ${window.ENRICH_LEVELS.length} na escala`} />
        <window.KpiCardSpark label="Nível predominante" value={predomLabel} sub={predom ? `${caPct(predom.shareV)} do valor em ${last?.y ?? '—'}` : 'sem exportação classificada'} />
        <window.KpiCardSpark label="Prêmio de processamento" value={data.premium ? '×' + caNum(data.premium, 1) : '—'} sub="preço do mais ÷ menos processado" />
        <window.KpiCardSpark label="Códigos na análise" value={data.nCodes} sub="incluídos e classificados" />
      </div>

      <div className="card">
        <window.SectionHeader overline="Valor exportado por nível · US$ bi" title="Quanto sai em cada nível de industrialização"
          action={<span className="caption">classificação da Curadoria</span>} />
        {data.nCodes < 1 ? (
          // Suppress the "nenhum código classificado" claim on a settled fetch failure — the
          // LoadErrorNote above already explains it (mirrors ViewMarketNature/ViewSeasonality).
          !data.loadError && (
            <p className="caption" style={{ padding: '24px 4px', textAlign: 'center' }}>
              Nenhum código classificado incluído para esta seleção. Ajuste em <strong>Engenharia de atributos → Nível de industrialização</strong>.
            </p>
          )
        ) : (
          <>
            <window.StackedArea series={areaSeries} valueKey="v" label="US$ bi" height={300} showLegend={false} />
            <Legend series={areaSeries} />
          </>
        )}
      </div>

      {data.nCodes >= 1 && (
        <div className="card">
          <window.SectionHeader overline="Volume exportado por nível · mil t" title="Quanto sai em cada nível (em peso)"
            action={<span className="caption">composição por nível</span>} />
          <window.StackedArea series={areaSeriesW} valueKey="v" label="mil t" height={260} showLegend={false} />
          <Legend series={areaSeriesW} />
        </div>
      )}

      {data.nCodes >= 1 && (
        <div className="card">
          <window.SectionHeader overline="Preço médio por nível · US$/kg" title="Quanto vale o quilo em cada nível"
            action={<span className="caption">{data.premium ? 'prêmio ×' + caNum(data.premium, 1) : '—'}</span>} />
          <window.MultiLineChart series={priceSeries} valueKey="v" label="US$/kg" height={260} trend />
          <p className="caption" style={{ padding: '8px 4px 0' }}>
            O prêmio de processamento é o quociente entre o preço do nível <strong>mais processado</strong> e o do
            <strong> menos processado</strong> presentes — agregar valor é vender o quilo mais caro.
            Reclassifique um código em <strong>Engenharia de atributos → Nível de industrialização</strong> e esta
            análise se atualiza — é o conhecimento do pesquisador entrando no dado.
          </p>
        </div>
      )}
    </>
  );
}

// ── Economic purpose: consume × process ───────────────────────────────
function ViewMarketNature() {
  useEnrichmentTick();
  const [group, setGroup] = useCaState(null);
  window.enrichment.worklist(); // kick the code worklist so ENRICH_GROUPS (the commodity chips) populates
  const data = window.marketNatureAnalysis(group);

  // Scope the analysis to one commodity's COMTRADE codes (or all curated).
  const selector = (
    <div className="pp-selector">
      <span className="pp-selector-label">Agrupamento</span>
      <div className="pp-chips">
        <button className={'pp-chip ' + (!group ? 'on' : '')} onClick={() => setGroup(null)}
          style={!group ? { background: 'var(--embrapa-green)', borderColor: 'var(--embrapa-green)', color: '#fff' } : null}>Todas curadas</button>
        {window.ENRICH_GROUPS.map(g => {
          const on = group === g.id;
          return (
            <button key={g.id} className={'pp-chip ' + (on ? 'on' : '')} onClick={() => setGroup(g.id)}
              style={on ? { background: 'var(--embrapa-green)', borderColor: 'var(--embrapa-green)', color: '#fff' } : null}>{g.label}</button>
          );
        })}
      </div>
    </div>
  );

  // Seed-driven: the series is empty when this commodity's COMTRADE trade has no rows whose
  // (regime × fluxo) pair maps to a market nature (or while the fetch is in flight). Guard
  // before reading series[0]/latest — show an honest empty state, never a crash.
  if (!data.series || !data.series.length) {
    return (
      <>
        {selector}
        {/* A failed fetch also lands here (empty series) — show the error, not the
            "sem finalidade classificada" claim (which would be a false statement). */}
        <window.LoadErrorNote error={data.loadError} />
        {!data.loadError && (
          <div className="card subtle">
            <window.SectionHeader overline="Valor por finalidade econômica · US$ bi"
              title="Sem finalidade econômica classificada para este recorte" />
            <p className="caption" style={{ padding: '24px 4px', textAlign: 'center' }}>
              O COMTRADE deste recorte não tem operações cujo par <strong>regime aduaneiro × fluxo</strong>
              {' '}esteja classificado como consumo ou processamento em <strong>Tipo de Mercado</strong>
              (Engenharia de atributos). A maioria do comércio é reportada apenas no agregado, sem regime.
            </p>
          </div>
        )}
      </>
    );
  }

  const L = data.latest;
  const total = window.ENRICH_MARKETS.reduce((s, m) => s + (L[m.id] || 0), 0) || 1;
  const areaSeries = window.ENRICH_MARKETS.map(m => ({
    name: m.short, color: m.color, data: data.series.map(d => ({ y: d.y, v: d[m.id] })),
  }));
  const donut = window.ENRICH_MARKETS.map(m => ({
    name: m.short, value: L[m.id], share: L[m.id] / total, color: m.color,
  }));

  return (
    <>
      {selector}

      <div className="kpi-row">
        {window.ENRICH_MARKETS.map(m => (
          <window.KpiCardSpark key={m.id} label={m.label}
            value={'US$ ' + caNum(L[m.id], 1) + ' bi'}
            sub={caPct((L[m.id] / total) * 100) + ' do total'} />
        ))}
        <window.KpiCardSpark label="Janela" value={`${data.series[0].y}–${L.y}`} sub="cobertura comparável" />
      </div>

      <div className="card">
        <window.SectionHeader overline="Valor por finalidade econômica · US$ bi" title="Comprando/vendendo para consumir ou para processar"
          action={<span className="caption">classificação em Tipo de Mercado (Engenharia de atributos)</span>} />
        <window.StackedArea series={areaSeries} valueKey="v" label="US$ bi" height={300} showLegend={false} />
        <div className="pc-legend">
          {areaSeries.map(s => (
            <span key={s.name} className="pc-legend-item"><span className="pc-legend-dot" style={{ background: s.color }}></span>{s.name}</span>
          ))}
        </div>
      </div>

      <div className="card">
        <window.SectionHeader overline={`Composição · ${L.y}`} title="Quanto vai para consumo vs. processamento" />
        <window.Donut data={donut} valueKey="share" size={170} />
        <p className="caption" style={{ padding: '8px 4px 0' }}>
          A direção (comprar/vender) vem do fluxo; a <strong>finalidade</strong> (consumo ou processamento)
          vem da classificação por par regime aduaneiro × fluxo em <strong>Tipo de Mercado</strong>.
        </p>
      </div>
    </>
  );
}

Object.assign(window, { ViewValueAdded, ViewMarketNature });
