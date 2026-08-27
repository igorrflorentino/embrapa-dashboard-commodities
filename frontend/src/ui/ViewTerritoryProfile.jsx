// ViewTerritoryProfile — the raio-x of ONE território.
//
// The TRANSPOSE of ViewProductProfile: that one fixes a produto and looks across
// places; this fixes a PLACE and looks across produtos. Same Gold, opposite question.
//
// Deliberately NOT folded into Geografia. Geografia answers "how is the activity
// spread ACROSS territories" — its unit of analysis is the distribution. This answers
// "what happens in THIS territory" — its unit is the place. One perspective serving
// both would mean two things at once.
//
// Entry is EXPLICIT (the pickers below, or Geografia's "Ver raio-x" action). The map
// click stays what it already is everywhere — a cheap, reversible filter toggle.
// Navigation and filtering must not share a gesture.

const { useState: useTPState, useMemo: useTPMemo } = React;

// Which grains this banco can actually answer for. COMEX is origin-UF only; COMTRADE
// has no national geography at all (and never reaches here — requires:['geo']).
// Stating this on the page is the point: silently offering only UF would read as
// "this place has no municípios", a different and false claim.
function tpGrains(database) {
  const level = window.geoLevelFor ? window.geoLevelFor(database) : 'municipio';
  return { municipio: level === 'municipio' };
}

function ViewTerritoryProfile({ summary, database, conventions }) {
  const conv = conventions || window.DEFAULT_CONVENTIONS;
  const fx = window.CURRENCY_FX[conv.currency];
  const cvf = window.convFactor(conv);
  const filtered = window.applyFilters(summary || {}, database);
  const grains = tpGrains(database);

  // ── Which território? ──────────────────────────────────────────────────────
  // Seeded from the global filter when it already names ONE place, so arriving from a
  // map click lands on what the researcher just picked instead of resetting on them.
  const seedUf = window.selectedSingleUf ? window.selectedSingleUf(summary) : null;
  const seedCity = (summary && Array.isArray(summary.munis) && summary.munis.length === 1)
    ? String(summary.munis[0]) : null;

  const [level, setLevel] = useTPState(seedCity && grains.municipio ? 'municipio' : 'uf');
  const activeLevel = (level === 'municipio' && grains.municipio) ? 'municipio' : 'uf';

  // The UF universe this banco reports (ufDataFull is the ALL-TIME universe — one row
  // per UF — NOT a total; totals are computed over the window below).
  const ufUniverse = filtered.ufDataFull || [];
  const ufYearly = filtered.ufYearlySeries || [];
  const yearStart = filtered.yearStart;
  const yearEnd = filtered.yearEnd;

  // Per-UF totals over the SELECTED window. Computed here rather than read off
  // `ufData`, which is latest-year-only: a share/rank taken from one year while the
  // chart beside it spans the whole window would be two different questions wearing
  // one label.
  const ufTotals = useTPMemo(() => {
    const acc = new Map();
    for (const r of ufYearly) {
      if (r.year < yearStart || r.year > yearEnd) continue;
      acc.set(r.uf, (acc.get(r.uf) || 0) + (r.value || 0));
    }
    return acc;
  }, [ufYearly, yearStart, yearEnd]);

  const ufOptions = useTPMemo(() => {
    const named = new Map(ufUniverse.map((u) => [u.uf, u.name || u.uf]));
    return [...new Set([...named.keys(), ...ufTotals.keys()])]
      .map((code) => ({ uf: code, name: named.get(code) || code, total: ufTotals.get(code) || 0 }))
      .sort((a, b) => b.total - a.total);
  }, [ufUniverse, ufTotals]);

  const [ufPick, setUfPick] = useTPState(seedUf);
  const uf = (ufPick && ufOptions.some((u) => u.uf === ufPick))
    ? ufPick
    : (seedUf || (ufOptions[0] && ufOptions[0].uf) || null);

  // Município universe within the chosen UF, from the static IBGE mesh (fetched once).
  const mesh = window.geoMesh ? window.geoMesh() : null;
  const cityOptions = useTPMemo(() => {
    if (!uf || !Array.isArray(mesh)) return [];
    return mesh
      .filter((m) => m.uf === uf)
      .map((m) => ({ code: String(m.cityCode), name: m.cityName || String(m.cityCode) }))
      .sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
  }, [mesh, uf]);
  const [cityPick, setCityPick] = useTPState(seedCity);
  const city = (cityPick && cityOptions.some((c) => c.code === cityPick))
    ? cityPick
    : (cityOptions.length ? cityOptions[0].code : null);
  const cityName = (cityOptions.find((c) => c.code === city) || {}).name || city;
  const ufName = (ufOptions.find((u) => u.uf === uf) || {}).name || uf || '—';
  const placeLabel = activeLevel === 'municipio' ? `${cityName || '—'} · ${uf || ''}` : ufName;

  // ── The place's trajectory ────────────────────────────────────────────────
  // UF: off the already-loaded, basket-aware (UF × year) cube.
  // Município: the city-scoped cube, fetched for this ONE city (Gold direct read, so
  // the city scope IS the cost control — one city is the cheapest possible request).
  const muniCube = (activeLevel === 'municipio' && city && window.municipioYearly)
    ? window.municipioYearly(database, summary, [city], [yearStart, yearEnd])
    : null;

  const series = useTPMemo(() => {
    const rows = activeLevel === 'municipio'
      ? (muniCube || [])
      : ufYearly.filter((r) => r.uf === uf);
    return rows
      .filter((r) => r.year >= yearStart && r.year <= yearEnd)
      // LineChart reads `d.y` for the x axis; the cubes carry `year`.
      .map((r) => ({ y: r.year, v: (r.value || 0) * 1e6 * cvf }))
      .sort((a, b) => a.y - b.y);
  }, [activeLevel, muniCube, ufYearly, uf, yearStart, yearEnd, cvf]);

  // ── What the place produces ───────────────────────────────────────────────
  // Both cubes GROUP BY place and sum the produtos away, so neither can name what is
  // behind the trajectory. These two readers exist for exactly that gap.
  const ufBreakdown = (activeLevel === 'uf' && uf && window.productsByUf)
    ? window.productsByUf(database, { ...(summary || {}), states: [uf] }, conv)
    : null;
  const muniBreakdown = (activeLevel === 'municipio' && city && window.productsByMunicipio)
    ? window.productsByMunicipio(database, summary, conv, [city])
    : null;
  const breakdown = ufBreakdown || muniBreakdown || { products: [], loadError: null };

  // ── National weight + rank ────────────────────────────────────────────────
  // The denominator is every UF in the grid ON PURPOSE — it ignores an active UF
  // filter, because a share against only the selected states would always be 100%.
  // The KPI says so rather than leaving the researcher to infer it.
  const nationalTotal = useTPMemo(
    () => [...ufTotals.values()].reduce((s, v) => s + v, 0), [ufTotals],
  );
  const ufTotal = uf ? (ufTotals.get(uf) || 0) : 0;
  // fmtPct takes a FRACTION and multiplies by 100 (unlike fmtSigned, which takes a
  // percentage already) — passing a percentage here rendered 4361,4%.
  const share = nationalTotal ? ufTotal / nationalTotal : null;
  const rank = uf ? ufOptions.findIndex((u) => u.uf === uf) + 1 : 0;

  const last = series[series.length - 1] || null;
  const prev = series[series.length - 2] || null;
  const deltaV = (last && prev && prev.v) ? ((last.v - prev.v) / prev.v) * 100 : null;
  const peak = series.reduce((m, d) => (!m || d.v > m.v ? d : m), null);

  if (!uf) {
    return (
      <window.EmptyCard>
        Nenhum território com dados na seleção atual. Ajuste os filtros para escolher um lugar.
      </window.EmptyCard>
    );
  }

  const scaled = window.scaleSeries(
    series, Math.max(...series.map((d) => d.v), 0), conv, 'v', fx.symbol,
  );
  // BarChart labels each row from `d.uf || d.name` — the product name is the category.
  const prodRows = (breakdown.products || []).slice()
    .sort((a, b) => (b.value || 0) - (a.value || 0)).slice(0, 12)
    .map((p) => ({ name: p.name || p.code, value: (p.value || 0) * 1e6 * cvf }));
  const prodScaled = window.scaleSeries(
    prodRows, Math.max(...prodRows.map((p) => p.value), 0), conv, 'value', fx.symbol,
  );

  return (
    <>
      {/* Território picker — explicit, so the map click stays a filter toggle. */}
      <div className="card subtle"
           style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap', padding: 12 }}>
        <span className="caption">Território em análise</span>
        {grains.municipio && (
          <div className="seg" role="group" aria-label="Nível do território">
            <button className={'seg-opt ' + (activeLevel === 'uf' ? 'on' : '')}
                    aria-pressed={activeLevel === 'uf'} onClick={() => setLevel('uf')}>UF</button>
            <button className={'seg-opt ' + (activeLevel === 'municipio' ? 'on' : '')}
                    aria-pressed={activeLevel === 'municipio'} onClick={() => setLevel('municipio')}>Município</button>
          </div>
        )}
        <label className="uf-scope">
          <span className="caption" style={{ marginRight: 6 }}>UF</span>
          <select className="seg-opt" style={{ padding: '4px 8px' }} value={uf}
                  aria-label="UF do território"
                  onChange={(e) => { setUfPick(e.target.value); setCityPick(null); }}>
            {ufOptions.map((u) => <option key={u.uf} value={u.uf}>{u.uf} · {u.name}</option>)}
          </select>
        </label>
        {activeLevel === 'municipio' && (
          <label className="uf-scope">
            <span className="caption" style={{ marginRight: 6 }}>Município</span>
            <select className="seg-opt" style={{ padding: '4px 8px', maxWidth: 260 }}
                    value={city || ''} aria-label="Município do território"
                    onChange={(e) => setCityPick(e.target.value)} disabled={!cityOptions.length}>
              {cityOptions.length
                ? cityOptions.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)
                : <option value="">carregando municípios…</option>}
            </select>
          </label>
        )}
      </div>

      {/* What this banco can and cannot answer for a território — stated, not implied. */}
      {!grains.municipio && (
        <window.NotApplicableNote>
          Este banco tem grão geográfico apenas por <strong>UF</strong>, então não há
          raio-x municipal aqui. O recorte por UF abaixo é completo.
        </window.NotApplicableNote>
      )}

      <window.LoadErrorNote error={breakdown.loadError} />

      <div className="kpi-row">
        <window.KpiCardSpark
          label={<>Valor · {placeLabel}</>}
          value={last ? window.formatValue(last.v, conv) : '—'}
          delta={deltaV != null ? window.fmtSigned(deltaV) : null}
          deltaPositive={deltaV != null && deltaV >= 0}
          sub={last && prev ? `${last.y} vs. ${prev.y}` : (last ? String(last.y) : 'sem dados')}
          spark={series}
        />
        <window.KpiCardSpark
          label="Participação no país"
          value={share != null ? window.fmtPct(share) : '—'}
          sub={`${ufName} sobre o total das UFs · ${yearStart}–${yearEnd}`}
        />
        <window.KpiCardSpark
          label="Posição no ranking"
          value={rank ? `${rank}º` : '—'}
          sub={`de ${ufOptions.length} UFs no banco · por valor na janela`}
        />
        <window.KpiCardSpark
          label="Pico histórico"
          value={peak ? window.formatValue(peak.v, conv) : '—'}
          sub={peak ? `em ${peak.y}` : 'sem dados na janela'}
        />
      </div>

      {/* Share and rank are always UF-level: the país-wide denominator only exists per
          UF. Saying so beats letting a município reading borrow the state's number. */}
      {activeLevel === 'municipio' && (
        <p className="caption" style={{ margin: '4px 2px 12px' }}>
          Participação e posição referem-se a <strong>{ufName}</strong> — o denominador
          nacional existe por UF, não por município.
        </p>
      )}

      <div className="card">
        <window.SectionHeader
          overline={`Trajetória · ${window.conventionMonetaryLabel(conv)}`}
          title={`Evolução de ${placeLabel}`}
        />
        {series.length
          ? <window.LineChart data={scaled.data} valueKey="v" label={scaled.label} />
          : <window.EmptyCard>Sem série para este território na janela selecionada.</window.EmptyCard>}
      </div>

      <div className="card">
        <window.SectionHeader overline="Composição" title={`O que ${placeLabel} produz`} />
        {prodRows.length
          ? <window.BarChart data={prodScaled.data} valueKey="value" label={prodScaled.label} />
          : <window.EmptyCard>Sem produtos registrados para este território na seleção atual.</window.EmptyCard>}
      </div>
    </>
  );
}

window.ViewTerritoryProfile = ViewTerritoryProfile;
