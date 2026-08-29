// ViewConcentration — how concentrated production is, geographically
// and by product. Lorenz curve + Gini + HHI. Applies to any banco
// (requires no special capability). Honours active filters.
//
// Gini: 0 = perfectly even, 1 = all in one unit.
// HHI:  sum of squared percentage shares (0–10000). >2500 = highly
//       concentrated (US DoJ convention).

function ViewConcentration({ summary, conventions, database }) {
  const filtered = window.applyFilters(summary || {}, database);
  const hasGeo = filtered.ufDataFull.length > 0;

  // Concentration is a point-in-time cross-section. Label each panel with the year
  // it is ACTUALLY computed over (never a different year): the geo distribution uses
  // the latest UF year present in the window (filtered.ufLatestYear, which can lag the
  // requested yearEnd); the product distribution uses each product's latest in-window
  // value (≈ yearEnd). Mark "(parcial)" when that latest year is incomplete (a monthly
  // banco's current year) or when the UF data stops short of the window end.
  const meta = (window.dataStore && window.dataStore.meta) ? window.dataStore.meta(database) : null;
  const lm = (meta && meta.latest) || null;
  // Align with ViewOverview/ViewGeography: a null completeYear still counts as partial
  // (the backend never emits yearComplete=false with completeYear=null today, but keep
  // the three views robust to that) (DOC-8).
  const yearPartialCal = !!lm && lm.yearComplete === false
    && (lm.completeYear == null || filtered.yearEnd > lm.completeYear);
  // The product cross-section takes each product's LATEST in-window value; a product
  // discontinued before yearEnd contributes an EARLIER year, so — unlike the geo panel,
  // a true single-year snapshot — this can MIX terminal years. Only claim the exact year
  // when every product actually reaches yearEnd; otherwise label it honestly as the most
  // recent available per product (avoids over-claiming a synchronized yearEnd cross-section).
  const prodTerminalYears = Object.values(filtered.productTS)
    .map((s) => s[s.length - 1]?.y)
    .filter((y) => y != null);
  const prodRagged = prodTerminalYears.some((y) => y !== filtered.yearEnd);
  const prodYearTag = prodRagged
    ? `mais recente disponível · ≤ ${filtered.yearEnd}`
    : `${filtered.yearEnd}${yearPartialCal ? ' (parcial)' : ''}`;
  const geoYear = filtered.ufLatestYear;
  const geoPartial = filtered.ufYearPartial || (yearPartialCal && geoYear === filtered.yearEnd);
  const geoYearTag = `${geoYear}${geoPartial ? ' (parcial)' : ''}`;

  // ── Geographic distribution (by UF) ─────────────────────────────────
  // Count ONLY real Brazilian UFs. Trade bancos (COMEX) carry non-state pseudo-
  // origins (EX/ND/ZN/MN/RE…) flagged real:false; folding them in would inflate
  // the unit count and distort the geographic Gini/HHI/top-5/Lorenz. Mirrors the
  // isRealUf guard ViewOverview already applies; falls back to the canonical 27-UF
  // registry for older payloads lacking the `real` flag.
  const isRealUf = u => (u.real != null ? u.real : window.isCanonicalUf(u.uf));
  const realUf   = filtered.ufData.filter(isRealUf);

  // Concentration is computed on VALUE by default. A value-less basket (the livestock
  // herd — a stock with no money) falls back to HEADCOUNT so the Gini/HHI/Lorenz are
  // real instead of all-zero. The metric formulas are measure-agnostic; we just feed
  // them the headcount and relabel "valor" → "cabeças".
  const anyValue = realUf.some(u => u.value > 0)
    || Object.values(filtered.productTS).some(s => (s[s.length - 1]?.v || 0) > 0);
  const onCount = !anyValue && (
    realUf.some(u => (u.q_count || 0) > 0)
    || Object.values(filtered.productTS).some(s => (s[s.length - 1]?.q || 0) > 0)
  );
  const measureLabel = onCount ? 'cabeças' : 'valor';
  const ufMeasure   = u => (onCount ? (u.q_count || 0) : u.value);
  const prodMeasure = last => (onCount ? (last?.q || 0) : (last ? last.v : 0));

  const ufValues = realUf.map(ufMeasure).filter(v => v > 0);
  // Override `value` with the active measure so every downstream consumer (bars,
  // topNShare, Lorenz) reads the same field regardless of the value-vs-headcount basis.
  const ufSorted = realUf.filter(u => ufMeasure(u) > 0)
    .map(u => ({ ...u, value: ufMeasure(u) }))
    .sort((a, b) => b.value - a.value);

  // ── Product distribution (latest year, by product) ──────────────────
  const prodValues = Object.entries(filtered.productTS).map(([code, s]) => {
    const last = s[s.length - 1];
    return { code, name: (filtered.products.find(p => p.code === code) || {}).name || code, value: prodMeasure(last) };
  }).filter(p => p.value > 0).sort((a, b) => b.value - a.value);

  // ── Metrics ──────────────────────────────────────────────────────────
  const gini = (vals) => {
    const s = vals.slice().filter(v => v > 0).sort((a, b) => a - b);
    const n = s.length;
    if (n < 2) return 0;
    const total = s.reduce((a, b) => a + b, 0);
    if (!total) return 0;
    let cum = 0;
    s.forEach((v, i) => { cum += (i + 1) * v; });
    return (2 * cum) / (n * total) - (n + 1) / n;
  };
  const hhi = (vals) => {
    const total = vals.reduce((a, b) => a + b, 0);
    if (!total) return 0;
    return vals.reduce((s, v) => s + Math.pow((v / total) * 100, 2), 0);
  };
  const topNShare = (sorted, n) => {
    const total = sorted.reduce((s, x) => s + x.value, 0) || 1;
    return sorted.slice(0, n).reduce((s, x) => s + x.value, 0) / total;
  };

  const ufGini = gini(ufValues);
  const ufHHI  = hhi(ufValues);
  const prodGini = gini(prodValues.map(p => p.value));
  const prodHHI  = hhi(prodValues.map(p => p.value));
  const top5UF = topNShare(ufSorted, 5);
  const top3Prod = topNShare(prodValues, 3);

  const hhiBand = (h) =>
    h > 2500 ? { label: 'alta concentração', color: 'var(--err)' }
    : h > 1500 ? { label: 'concentração moderada', color: 'var(--warn)' }
    : { label: 'baixa concentração', color: 'var(--ok)' };
  const giniBand = (g) =>
    g > 0.6 ? { label: 'muito desigual', color: 'var(--err)' }
    : g > 0.4 ? { label: 'desigual', color: 'var(--warn)' }
    : { label: 'relativamente uniforme', color: 'var(--ok)' };

  // Gini/Lorenz need ≥2 units to mean anything. With a single product/UF the
  // formula degenerates to 0 ("relativamente uniforme"), which contradicts the
  // HHI reading (max concentration). Surface "n/d" instead of a false reading.
  const giniInfo = (count, g) => count < 2
    ? { value: 'n/d', label: count === 1 ? 'unidade única' : 'sem dados', color: 'var(--fg-4)' }
    : { value: g.toFixed(2).replace('.', ','), ...giniBand(g) };
  const ufG   = giniInfo(ufValues.length, ufGini);
  const prodG = giniInfo(prodValues.length, prodGini);

  return (
    <>
      <window.RecorteNote recorte={filtered.recorte} />
      {onCount && (
        <p className="caption" style={{ margin: '0 2px 4px' }}>
          ⓘ Esta cesta não tem valor monetário (efetivo dos rebanhos) — a concentração
          é calculada sobre as <strong>cabeças</strong>.
        </p>
      )}

      {/* The per-UF concentration reads the all-products UF grid until the product×UF
          cube lands (or when no basket narrows it), so under a basket chip the geographic
          Gini/HHI reflect ALL products — surface that honestly instead of letting the
          number read as basket-specific (mirrors ViewGeography's notFilteredByBasket note). */}
      {filtered.notFilteredByBasket && (
        <div className="card subtle" style={{ marginBottom: 12 }}>
          <p className="caption" style={{ padding: '10px 12px' }}>
            A concentração <strong>geográfica (UF)</strong> reflete <strong>todos os produtos</strong>
            do banco — a cesta selecionada não recorta a distribuição territorial (não há grão
            produto × UF nesta agregação). A concentração <strong>por produto</strong> abaixo já
            considera a cesta.
          </p>
        </div>
      )}

      {/* KPI strip */}
      <div className="kpi-row">
        {hasGeo ? (
        <>
        <window.KpiCardSpark
          label="Gini · geográfico (UF)"
          value={ufG.value}
          sub={ufG.label}
        />
        <window.KpiCardSpark
          label="HHI · geográfico (UF)"
          value={Math.round(ufHHI).toLocaleString('pt-BR')}
          sub={hhiBand(ufHHI).label}
        />
        <window.KpiCardSpark
          label="Concentração top-5 UFs"
          value={window.fmtPct(top5UF)}
          sub={`de ${ufSorted.length} ${ufSorted.length === 1 ? 'UF' : 'UFs'} com produção`}
        />
        <window.KpiCardSpark
          label="Concentração top-3 produtos"
          value={window.fmtPct(top3Prod)}
          sub={`de ${prodValues.length} ${prodValues.length === 1 ? 'produto' : 'produtos'} na cesta`}
        />
        </>
        ) : (
        <>
        <window.KpiCardSpark
          label="Gini · por produto"
          value={prodG.value}
          sub={prodG.label}
        />
        <window.KpiCardSpark
          label="HHI · por produto"
          value={Math.round(prodHHI).toLocaleString('pt-BR')}
          sub={hhiBand(prodHHI).label}
        />
        <window.KpiCardSpark
          label="Concentração top-3 produtos"
          value={window.fmtPct(top3Prod)}
          sub={`de ${prodValues.length} ${prodValues.length === 1 ? 'produto' : 'produtos'} na cesta`}
        />
        </>
        )}
      </div>

      {/* Lorenz curves */}
      <div className="grid-2">
        {hasGeo && (
        <div className="card">
          <window.SectionHeader
            overline={`Curva de Lorenz · geográfica · ${geoYearTag}`}
            title={`Desigualdade entre UFs · Gini ${ufG.value}`}
            action={<span className="caption" style={{ color: ufG.color }}>{ufG.label}</span>}
          />
          <window.LorenzCurve values={ufValues} color="var(--viz-2)" xLabel="UFs" yLabel={measureLabel} height={300} />
        </div>
        )}
        <div className="card">
          <window.SectionHeader
            overline={`Curva de Lorenz · por produto · ${prodYearTag}`}
            title={`Desigualdade entre produtos · Gini ${prodG.value}`}
            action={<span className="caption" style={{ color: prodG.color }}>{prodG.label}</span>}
          />
          <window.LorenzCurve values={prodValues.map(p => p.value)} color="var(--viz-5)" xLabel="produtos" yLabel={measureLabel} height={300} />
        </div>
      </div>

      {/* Top-5 UF concentration bars + HHI gauges */}
      <div className="grid-2">
        {hasGeo && (
        <div className="card">
          <window.SectionHeader
            overline={`Participação acumulada · UFs · ${geoYearTag}`}
            title="Quem concentra a produção"
          />
          <div className="conc-list">
            {(() => {
              const total = ufSorted.reduce((s, u) => s + u.value, 0) || 1;
              let acc = 0;
              return ufSorted.slice(0, 10).map((u, i) => {
                const share = u.value / total;
                acc += share;
                return (
                  <div key={u.uf} className="conc-row">
                    <span className="conc-rank tnum">#{i + 1}</span>
                    <span className="conc-name">{u.uf} · {u.name}</span>
                    <div className="conc-bar"><div style={{ width: (share * 100).toFixed(1) + '%', background: 'var(--viz-2)' }}></div></div>
                    <span className="conc-share tnum">{window.fmtPct(share)}</span>
                    <span className="conc-acc tnum">{window.fmtPct(acc)}</span>
                  </div>
                );
              });
            })()}
            <div className="conc-head-note">
              <span></span><span></span><span></span>
              <span className="caption">indiv.</span>
              <span className="caption">acum.</span>
            </div>
          </div>
        </div>
        )}

        <div className="card">
          <window.SectionHeader
            overline="Índice Herfindahl-Hirschman (HHI)"
            title="Leitura da concentração"
          />
          <div className="conc-hhi">
            {hasGeo && (
            <div className="conc-hhi-row">
              <span className="conc-hhi-label">Geográfico (UF)</span>
              <div className="conc-hhi-track">
                <div className="conc-hhi-fill" style={{ width: Math.min(100, (ufHHI / 10000) * 100) + '%', background: hhiBand(ufHHI).color }}></div>
                <span className="conc-hhi-mark" style={{ left: '15%' }} title="1500"></span>
                <span className="conc-hhi-mark" style={{ left: '25%' }} title="2500"></span>
              </div>
              <span className="conc-hhi-val tnum">{Math.round(ufHHI).toLocaleString('pt-BR')}</span>
            </div>
            )}
            <div className="conc-hhi-row">
              <span className="conc-hhi-label">Por produto</span>
              <div className="conc-hhi-track">
                <div className="conc-hhi-fill" style={{ width: Math.min(100, (prodHHI / 10000) * 100) + '%', background: hhiBand(prodHHI).color }}></div>
                <span className="conc-hhi-mark" style={{ left: '15%' }}></span>
                <span className="conc-hhi-mark" style={{ left: '25%' }}></span>
              </div>
              <span className="conc-hhi-val tnum">{Math.round(prodHHI).toLocaleString('pt-BR')}</span>
            </div>
            <dl className="conc-scale">
              <dt><span className="conc-dot" style={{ background: 'var(--ok)' }}></span>&lt; 1500</dt><dd>baixa concentração</dd>
              <dt><span className="conc-dot" style={{ background: 'var(--warn)' }}></span>1500–2500</dt><dd>concentração moderada</dd>
              <dt><span className="conc-dot" style={{ background: 'var(--err)' }}></span>&gt; 2500</dt><dd>alta concentração</dd>
            </dl>
            <p className="caption conc-note">
              HHI = soma dos quadrados das participações percentuais. As marcas no trilho indicam os limiares 1500 e 2500 (convenção US DoJ).
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

window.ViewConcentration = ViewConcentration;
