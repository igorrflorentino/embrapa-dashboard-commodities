// ViewRebanho — the livestock HERD perspective (PPM 'herd' capability).
//
// The efetivo dos rebanhos is a STOCK in cabeças (head counted at year-end): it has
// NO monetary value and is NOT additive across species (a head of cattle and a head
// of poultry are not comparable). So this view is cabeças-only — composition, the
// 50-year per-species evolution, and a per-UF map of the focused species — with the
// value/price machinery of the production views deliberately absent. The herd is
// ~⅔ of PPM's Gold rows yet was invisible until the `q_count` quantity track landed;
// this is its home.

const { useState: useRbState, useEffect: useRbEffect } = React;

function ViewRebanho({ summary, conventions, database }) {
  const conv     = conventions || window.DEFAULT_CONVENTIONS;
  const filtered = window.applyFilters(summary || {}, database);

  // Herd = STOCK products (measure_kind='stock', count family). Animal-product flows
  // (eggs, milk) share the count/volume families but belong to the value views — the
  // measure_kind discriminator is exactly what separates them.
  const herdCodes = filtered.products.filter(p => p.measure_kind === 'stock').map(p => p.code);
  const available = herdCodes.filter(c => filtered.allProductTS[c]);

  const yearStart = filtered.yearStart, yearEnd = filtered.yearEnd;
  const qtyMul = window.countQtyMul(conv);
  const unitAx = window.countAxisLabel(conv);
  const PALETTE = ['var(--viz-1)', 'var(--viz-2)', 'var(--viz-3)', 'var(--viz-4)',
                   'var(--viz-5)', 'var(--viz-6)', 'var(--viz-7)', 'var(--viz-9)'];
  const hasGeo = filtered.ufDataFull.length > 0;

  // Focused species (drives the KPIs + the per-UF map) — default = largest by latest
  // headcount. Hooks sit ABOVE the early return so their order is stable (Rules of Hooks).
  const defaultCode = available
    .map(c => ({ c, q: filtered.allProductTS[c].slice(-1)[0]?.q || 0 }))
    .sort((a, b) => b.q - a.q)[0]?.c || null;
  const [focus, setFocus] = useRbState(defaultCode);
  const activeFocus = (focus && available.includes(focus)) ? focus : defaultCode;

  // REAL per-UF headcount for the focused species (Gold product×UF via /api/product-uf,
  // which now carries q_count). A value-less stock would rank all-zero by `value`.
  // Stable primitive for the fetch effect's deps: the states ARRAY is a new
  // identity every render, so depending on it directly would refetch forever.
  // `null` (no UF filter) is kept distinct from '' (explicitly none selected) —
  // the same null-vs-empty contract the other producers honour.
  const ufScopeKey = summary?.states == null ? null : summary.states.join(',');
  const [ufRank, setUfRank] = useRbState({ rows: null, loading: true });
  useRbEffect(() => {
    if (!activeFocus || !hasGeo) return undefined;
    let alive = true;
    setUfRank({ rows: null, loading: true });
    const qs = new URLSearchParams({
      banco: database, code: activeFocus, currency: conv.currency, correction: conv.correction,
    });
    if (summary?.startDate) qs.set('startDate', summary.startDate);
    if (summary?.endDate) qs.set('endDate', summary.endDate);
    // The UF filter reaches this reader now. Without it the ranking/map showed all 27
    // states while the rest of the screen was narrowed to the researcher's selection.
    // Read from ufScopeKey (not summary.states) so the effect depends ONLY on the
    // stable primitive that is in its deps array.
    if (ufScopeKey != null) qs.set('states', ufScopeKey);
    fetch(`/api/product-uf?${qs}`)
      // Distinguish a LOAD FAILURE from a legitimately empty ranking (else "Sem dados por UF
      // para esta espécie" would read as a false claim when the fetch merely failed).
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { if (alive) setUfRank({ rows: (d && d.uf) || [], loading: false, error: false }); })
      .catch(() => { if (alive) setUfRank({ rows: null, loading: false, error: true }); });
    return () => { alive = false; };
    // `states` joined, not the array: a fresh array identity every render would
    // refetch on every render, while omitting it entirely would never refetch when
    // the researcher changes the UF filter — the map would keep the old scope.
  }, [database, activeFocus, hasGeo, conv.currency, conv.correction, summary?.startDate, summary?.endDate, ufScopeKey]);

  if (!available.length) {
    return (
      <window.EmptyCard>
        Nenhum rebanho (estoque) na seleção atual. Ajuste os filtros para incluir
        espécies do efetivo dos rebanhos.
      </window.EmptyCard>
    );
  }

  // Latest-year composition: each species' headcount share. A cross-species comparison
  // shown ONLY as relative composition (the caveat note makes the non-additivity explicit).
  const latestByCode = {};
  available.forEach(c => {
    const s = filtered.allProductTS[c].filter(d => d.y <= yearEnd);
    latestByCode[c] = s.length ? s[s.length - 1] : null;
  });
  const totalLatest = available.reduce((s, c) => s + ((latestByCode[c]?.q || 0) * qtyMul), 0) || 1;
  const compData = available
    .map((c, i) => {
      const p = filtered.products.find(x => x.code === c);
      const q = (latestByCode[c]?.q || 0) * qtyMul;
      return { name: p.name, color: PALETTE[i % PALETTE.length], share: q / totalLatest, q };
    })
    .sort((a, b) => b.q - a.q);

  // 50-year evolution — one line per species (absolute cabeças). NOT stacked: heads of
  // different species are not additive. Plotly zoom/hover handles the scale disparity
  // (poultry in the billions vs caprinos in the millions).
  const evoSeries = available.map((c, i) => {
    const p = filtered.products.find(x => x.code === c);
    return {
      name: p.name,
      color: PALETTE[i % PALETTE.length],
      data: filtered.allProductTS[c]
        .filter(d => d.y >= yearStart && d.y <= yearEnd)
        .map(d => ({ y: d.y, v: (d.q || 0) * qtyMul })),
    };
  });

  // Focused-species KPIs (current efetivo, YoY, historical peak).
  const focusProd = filtered.products.find(p => p.code === activeFocus);
  const focusWin  = filtered.allProductTS[activeFocus].filter(d => d.y >= yearStart && d.y <= yearEnd);
  const fLast = focusWin[focusWin.length - 1] || { y: yearEnd, q: 0 };
  const fPrev = focusWin[focusWin.length - 2] || fLast;
  const fDelta = fPrev.q ? ((fLast.q - fPrev.q) / fPrev.q) * 100 : 0;
  const fPeak = focusWin.reduce((m, d) => (d.q > m.q ? d : m), focusWin[0] || fLast);

  // Per-UF map of the focused species — decorate product-uf rows with tile col/row
  // from the UF registry (the BrazilTileMap positions tiles by col/row).
  const UF_POS = window.UF_DATA ? Object.fromEntries(window.UF_DATA.map(u => [u.uf, u])) : {};
  const ufMapRows = (ufRank.rows || [])
    .map(u => {
      const pos = UF_POS[u.uf];
      return pos ? { uf: u.uf, col: pos.col, row: pos.row, region: pos.region, value: (u.q_count || 0) * qtyMul } : null;
    })
    .filter(Boolean);
  const ufTop = ufMapRows.slice().sort((a, b) => b.value - a.value).slice(0, 3);

  return (
    <>
      {/* Intro + caveat */}
      <div className="card subtle">
        <window.SectionHeader
          overline="Pecuária · efetivo dos rebanhos (PPM)"
          title="Rebanho brasileiro · cabeças"
        />
        <p className="caption" style={{ margin: '2px 2px 0' }}>
          O efetivo é um <strong>estoque</strong> (nº de cabeças no fim do ano), não uma produção: não
          tem valor monetário, e <strong>não deve ser somado entre espécies</strong> — cabeças de bovino
          e de galináceo não são comparáveis. As séries abaixo são por espécie, em cabeças.
        </p>
      </div>

      {/* Focused-species selector */}
      <div className="pp-selector">
        <span className="pp-selector-label">Espécie em foco <small className="pc-cap">(indicadores + mapa)</small></span>
        <div className="pp-chips">
          {available.map(c => {
            const p = filtered.products.find(x => x.code === c);
            return (
              <button key={c}
                      className={'pp-chip ' + (c === activeFocus ? 'on' : '')}
                      onClick={() => setFocus(c)}>
                <span className="pp-chip-fam count"></span>
                {p.name}
              </button>
            );
          })}
        </div>
      </div>

      {/* KPI strip — focused species */}
      <div className="kpi-row">
        <window.KpiCardSpark
          label={<>Efetivo · {focusProd.name}</>}
          value={window.formatCountQty(fLast.q, conv)}
          delta={window.fmtSigned(fDelta)}
          deltaPositive={fLast.q >= fPrev.q}
          sub={`${fLast.y} vs. ${fPrev.y}`}
          spark={focusWin.slice(-12).map(d => ({ y: d.y, q: d.q }))}
          sparkKey="q"
          sparkColor="var(--viz-9)"
        />
        <window.KpiCardSpark
          label="Pico histórico"
          value={window.formatCountQty(fPeak.q, conv)}
          sub={`em ${fPeak.y}`}
          spark={focusWin.slice(-12).map(d => ({ y: d.y, q: d.q }))}
          sparkKey="q"
          sparkColor="var(--viz-7)"
        />
        <window.KpiCardSpark
          label="Espécies no efetivo"
          value={String(available.length)}
          sub={`${yearStart}–${yearEnd}`}
        />
        {hasGeo && ufTop.length > 0 && (
          <window.KpiCardSpark
            label={<>UF líder · {focusProd.name}</>}
            value={ufTop[0].uf}
            sub={`${ufTop[0].value.toLocaleString('pt-BR', { maximumFractionDigits: 0 })} ${unitAx}`}
          />
        )}
      </div>

      {/* Composition + evolution */}
      <div className="grid-2">
        <div className="card">
          <window.SectionHeader
            overline={`Composição do efetivo · ${yearEnd}`}
            title="Participação por espécie (cabeças)"
            action={<span className="caption">{available.length} espécies</span>}
          />
          <window.Donut data={compData} size={180} valueKey="share" />
        </div>
        <div className="card">
          <window.SectionHeader
            overline={<>Evolução por espécie · {yearStart}–{yearEnd} · <window.UnitFamilyTag family="count" conv={conv}/></>}
            title="Efetivo ao longo do tempo"
            action={<span className="caption">use o zoom para as espécies menores</span>}
          />
          <window.MultiLineChart series={evoSeries} label={unitAx} valueKey="v" height={300} />
        </div>
      </div>

      {/* Per-UF map of the focused species */}
      {hasGeo && (
        <div className="card">
          <window.SectionHeader
            overline={`Distribuição por UF · ${focusProd.name} · ${yearStart}–${yearEnd}`}
            title={`Onde ${focusProd.name} é criado`}
            action={<span className="caption">{ufTop.length ? 'Top 3: ' + ufTop.map(u => u.uf).join(' · ') : '—'}</span>}
          />
          {ufRank.loading ? (
            <p className="caption" style={{ padding: '40px 4px', textAlign: 'center' }}>
              Carregando distribuição por UF…
            </p>
          ) : ufRank.error ? (
            <p className="caption" style={{ padding: '40px 4px', textAlign: 'center', color: 'var(--err, #b71c1c)' }}>
              Não foi possível carregar a distribuição por UF. Tente novamente.
            </p>
          ) : ufMapRows.length ? (
            <window.BrazilTileMap data={ufMapRows} valueKey="value" label={unitAx} />
          ) : (
            <p className="caption" style={{ padding: '40px 4px', textAlign: 'center' }}>
              Sem dados por UF para esta espécie.
            </p>
          )}
        </div>
      )}
    </>
  );
}

window.ViewRebanho = ViewRebanho;
