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
//
// HOW THIS RELATES TO THE GLOBAL GEOGRAPHY FILTER (they are NOT redundant, but they
// were until v1.29.1, and the overlap was a bug rather than clutter):
//
//     the filter  = the UNIVERSE of the analysis   ("I am studying AM and SP")
//     the picker  = the FOCUS inside that universe ("show me SP right now")
//
// The picker therefore offers ONLY territories the filter admits — the same rule
// ViewProductProfile already follows by limiting its product chips to the basket.
// Shipped the other way round, the picker listed all 27 UFs regardless, so a session
// filtered to AM+SP happily profiled Pará: a displayed value computed over a set the
// researcher had explicitly excluded.
//
// Combining territories is therefore done IN THE FILTER, and the picker exposes the
// combination as a first-class option ("Seleção atual"), which profiles the sum.

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
  const ufUniverseAll = filtered.ufDataFull || [];
  const ufYearly = filtered.ufYearlySeries || [];

  // What the FILTER admits. A state narrowing names its UFs directly; a sub-UF facet
  // (meso/micro/intermediária/imediata/município) resolves to a city set, whose UFs are
  // the admitted ones. Empty/absent ⇒ no narrowing ⇒ the whole universe.
  const scopedCities = filtered.scopedCityCodes || null;
  const meshAll = window.geoMesh ? window.geoMesh() : null;
  const allowedUfs = useTPMemo(() => {
    const fromStates = (summary && Array.isArray(summary.states) && summary.states.length)
      ? new Set(summary.states) : null;
    if (!scopedCities || !Array.isArray(meshAll)) return fromStates;
    const byCode = new Map(meshAll.map((m) => [String(m.cityCode), m.uf]));
    const fromCities = new Set(
      scopedCities.map((c) => byCode.get(String(c))).filter(Boolean),
    );
    if (!fromStates) return fromCities;
    return new Set([...fromCities].filter((u) => fromStates.has(u)));
  }, [summary, scopedCities, meshAll]);

  const ufUniverse = useTPMemo(
    () => (allowedUfs ? ufUniverseAll.filter((u) => allowedUfs.has(u.uf)) : ufUniverseAll),
    [ufUniverseAll, allowedUfs],
  );
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
    const codes = [...new Set([...named.keys(), ...ufTotals.keys()])]
      .filter((code) => !allowedUfs || allowedUfs.has(code));
    return codes
      .map((code) => ({ uf: code, name: named.get(code) || code, total: ufTotals.get(code) || 0 }))
      .sort((a, b) => b.total - a.total);
  }, [ufUniverse, ufTotals, allowedUfs]);

  // Combining territories happens in the FILTER; this is where that combination becomes
  // a thing you can profile. Offered ONLY when the filter actually named a set: with no
  // geography filter at all, "Seleção atual" would mean the whole country, which is
  // Visão geral's job — a território profile of Brazil profiles nothing.
  const canCombine = !!allowedUfs && ufOptions.length > 1;
  const COMBINED = '__combinado__';

  const [ufPick, setUfPick] = useTPState(seedUf);
  const ufValid = (v) => v === COMBINED ? canCombine : ufOptions.some((u) => u.uf === v);
  // Default to the combination when the filter names several territories: the researcher
  // asked for that set, so the set is the honest first answer — drilling into one of them
  // is one click away, but guessing which one they meant is not ours to do.
  const ufDefault = canCombine && !seedUf ? COMBINED : (ufOptions[0] && ufOptions[0].uf) || null;
  const uf = ufValid(ufPick) ? ufPick : (ufValid(seedUf) ? seedUf : ufDefault);
  const combined = uf === COMBINED;
  // The UFs actually being profiled: all admitted ones when combined, else the one.
  const activeUfs = useTPMemo(
    () => (combined ? ufOptions.map((u) => u.uf) : (uf ? [uf] : [])),
    [combined, ufOptions, uf],
  );

  // Município universe — scoped the same way. A sub-UF facet already resolved to a city
  // set; offering a município outside it would profile a place the filter excluded.
  const mesh = meshAll;
  const cityOptions = useTPMemo(() => {
    if (!Array.isArray(mesh) || !activeUfs.length) return [];
    const allowedCities = scopedCities ? new Set(scopedCities.map(String)) : null;
    return mesh
      .filter((m) => activeUfs.includes(m.uf))
      .filter((m) => !allowedCities || allowedCities.has(String(m.cityCode)))
      .map((m) => ({ code: String(m.cityCode), name: m.cityName || String(m.cityCode), uf: m.uf }))
      .sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
  }, [mesh, activeUfs, scopedCities]);

  const [cityPick, setCityPick] = useTPState(seedCity);
  // Same rule as the UF level: a combination is only meaningful when the FILTER named
  // the set. Without a sub-UF facet, "Seleção atual" would just be the whole state —
  // which is precisely what the UF level already shows.
  const cityCanCombine = !!scopedCities && cityOptions.length > 1;
  const cityValid = (v) => v === COMBINED ? cityCanCombine : cityOptions.some((c) => c.code === v);
  const cityDefault = cityCanCombine && !seedCity
    ? COMBINED : (cityOptions[0] && cityOptions[0].code) || null;
  const city = cityValid(cityPick) ? cityPick : (cityValid(seedCity) ? seedCity : cityDefault);
  const cityCombined = city === COMBINED;
  const activeCities = useTPMemo(
    () => (cityCombined ? cityOptions.map((c) => c.code) : (city ? [city] : [])),
    [cityCombined, cityOptions, city],
  );

  const cityName = (cityOptions.find((c) => c.code === city) || {}).name || city;
  const ufName = combined
    ? `${ufOptions.length} UFs selecionadas`
    : ((ufOptions.find((u) => u.uf === uf) || {}).name || uf || '—');
  const placeLabel = activeLevel === 'municipio'
    ? (cityCombined ? `${cityOptions.length} municípios selecionados` : `${cityName || '—'} · ${(cityOptions.find((c) => c.code === city) || {}).uf || ''}`)
    : ufName;

  // ── The território's trajectory ───────────────────────────────────────────
  // A combination is SUMMED, which is legitimate here: these are production values in
  // one unit and one deflation basis, so the sum is the selection's own series.
  const muniCube = (activeLevel === 'municipio' && activeCities.length && window.municipioYearly)
    ? window.municipioYearly(database, summary, activeCities, [yearStart, yearEnd])
    : null;

  const series = useTPMemo(() => {
    const rows = activeLevel === 'municipio'
      ? (muniCube || [])
      : ufYearly.filter((r) => activeUfs.includes(r.uf));
    const byYear = new Map();
    for (const r of rows) {
      if (r.year < yearStart || r.year > yearEnd) continue;
      byYear.set(r.year, (byYear.get(r.year) || 0) + (r.value || 0));
    }
    return [...byYear.entries()]
      // LineChart reads `d.y` for the x axis; the cubes carry `year`.
      .map(([y, v]) => ({ y, v: v * 1e6 * cvf }))
      .sort((a, b) => a.y - b.y);
  }, [activeLevel, muniCube, ufYearly, activeUfs, yearStart, yearEnd, cvf]);

  // ── What the território produces ──────────────────────────────────────────
  // Both cubes GROUP BY place and sum the produtos away, so neither can name what is
  // behind the trajectory. Both readers take a SET, so a combination needs no special
  // case — it is one query over the selected territories.
  const ufBreakdown = (activeLevel === 'uf' && activeUfs.length && window.productsByUf)
    ? window.productsByUf(database, { ...(summary || {}), states: activeUfs }, conv)
    : null;
  const muniBreakdown = (activeLevel === 'municipio' && activeCities.length && window.productsByMunicipio)
    ? window.productsByMunicipio(database, summary, conv, activeCities)
    : null;
  const breakdown = ufBreakdown || muniBreakdown || { products: [], loadError: null };

  // ── National weight + rank ────────────────────────────────────────────────
  // The denominator is every UF in the GRID on purpose — it deliberately ignores the
  // geography filter, because a share against only the selected states would always
  // read 100%. The KPI names both the numerator and the window so it stays checkable.
  const nationalTotal = useTPMemo(
    () => [...ufTotals.values()].reduce((s, v) => s + v, 0), [ufTotals],
  );
  const ufTotal = activeUfs.reduce((acc, code) => acc + (ufTotals.get(code) || 0), 0);

  // A sub-UF narrowing (meso/micro/intermediária/imediata/município) makes the per-UF
  // series a ROLLUP OF THE SELECTED CITIES ONLY, so summing it gives the selection's own
  // total — not the country's. Dividing by that would print ~100% and call it
  // "participação no país". There is no honest national denominator on this basis (the
  // unnarrowed grid is all-products, so it would mix bases), so the KPI says it cannot
  // be computed instead of showing a confident wrong number.
  const nationalAvailable = !filtered.subUfActive;
  const share = (nationalAvailable && nationalTotal) ? ufTotal / nationalTotal : null;
  // Rank is a position in the COUNTRY, not inside the current selection — "1º de 1 UF
  // na seleção" is honest and useless. It stays computable under a UF filter because
  // ufYearlySeries is narrowed only by SUB-UF facets, never by the state filter; under
  // a sub-UF narrowing there is no country-wide ordering to place anyone in.
  const rankable = !combined && !filtered.subUfActive;
  const countryOrder = useTPMemo(
    () => [...ufTotals.entries()].sort((a, b) => b[1] - a[1]).map(([code]) => code),
    [ufTotals],
  );
  const rank = rankable ? countryOrder.indexOf(uf) + 1 : 0;
  const rankUniverse = countryOrder.length;

  const last = series[series.length - 1] || null;
  const prev = series[series.length - 2] || null;
  const deltaV = (last && prev && prev.v) ? ((last.v - prev.v) / prev.v) * 100 : null;
  const peak = series.reduce((m, d) => (!m || d.v > m.v ? d : m), null);

  if (!uf || !activeUfs.length) {
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
            {canCombine && (
              <option value={COMBINED}>Seleção atual ({ufOptions.length} UFs somadas)</option>
            )}
            {ufOptions.map((u) => <option key={u.uf} value={u.uf}>{u.uf} · {u.name}</option>)}
          </select>
        </label>
        {activeLevel === 'municipio' && (
          <label className="uf-scope">
            <span className="caption" style={{ marginRight: 6 }}>Município</span>
            <select className="seg-opt" style={{ padding: '4px 8px', maxWidth: 260 }}
                    value={city || ''} aria-label="Município do território"
                    onChange={(e) => setCityPick(e.target.value)} disabled={!cityOptions.length}>
              {cityCanCombine && (
                <option value={COMBINED}>
                  Seleção atual ({cityOptions.length} municípios somados)
                </option>
              )}
              {cityOptions.length
                ? cityOptions.map((c) => (
                    <option key={c.code} value={c.code}>{c.name} · {c.uf}</option>
                  ))
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
          sub={nationalAvailable
            ? `${ufName} sobre o total das UFs · ${yearStart}–${yearEnd}`
            : 'indisponível sob recorte sub-UF (não há denominador nacional nesta base)'}
        />
        <window.KpiCardSpark
          label="Posição no ranking"
          value={rank ? `${rank}º` : '—'}
          sub={rankable
            ? `de ${rankUniverse} UFs no banco · por valor na janela`
            : (combined ? 'uma soma de territórios não tem posição' : 'indisponível sob recorte sub-UF')}
        />
        <window.KpiCardSpark
          label="Pico histórico"
          value={peak ? window.formatValue(peak.v, conv) : '—'}
          sub={peak ? `em ${peak.y}` : 'sem dados na janela'}
        />
      </div>

      {/* Share and rank are always UF-level: the país-wide denominator only exists per
          UF. Saying so beats letting a município reading borrow the state's number. */}
      {activeLevel === 'municipio' && (share != null || rank > 0) && (
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
