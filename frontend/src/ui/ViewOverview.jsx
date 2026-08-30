// ViewOverview — a digest of the other three perspectives.
// All datasets pass through window.applyFilters(summary) so KPIs,
// charts and the donut only reflect the rows the researcher selected.

function ViewOverview({ families, summary, database, conventions }) {
  const conv      = conventions || window.DEFAULT_CONVENTIONS;
  const monLabel  = window.conventionMonetaryLabel(conv);
  const valAxis   = window.valueAxisLabel(conv);
  // ufData is in the banco's OWN base currency (USD for COMEX/Comtrade), so scale
  // it with the base-aware factor — convFactor alone leaves a US$ magnitude under
  // R$ when a USD-native banco switches display to BRL. base=BRL → unchanged.
  const baseCcy   = window.canonCurrencyFor ? window.canonCurrencyFor(database) : 'BRL';
  const ufFactor  = window.convFactorFor(baseCcy, conv);

  const filtered = window.applyFilters(summary || {}, database);

  // ts.v is in R$ bi; scale to absolute.
  const ts        = filtered.ts.map(d => ({ ...d, v: d.v * 1e9 }));

  // Partial-latest-year detection. A monthly banco (COMEX) publishes the current
  // year month-by-month, so its latest year covers only a few months; a raw YoY of
  // that partial year vs a full prior year looks like a crash. We do NOT hide it by
  // computing on an earlier "complete" year — that would show a value for a period
  // the researcher did not select. Per the product rule, the KPI/YoY ALWAYS reflect
  // the user's selected window (latest year included); when that year is partial we
  // only MARK it "(parcial)" and explain the comparison is not like-for-like.
  const meta        = (window.dataStore && window.dataStore.meta)
    ? window.dataStore.meta(database) : null;
  const latestMeta  = (meta && meta.latest) || null;
  const lastPoint   = ts[ts.length - 1] || { v: 0, q_mass: 0, q_vol: 0, q_count: 0, y: null };
  const partialLatest =
    !!latestMeta &&
    latestMeta.yearComplete === false &&
    lastPoint.y != null &&
    (latestMeta.completeYear == null || lastPoint.y > latestMeta.completeYear) &&
    ts.length >= 2;
  const partialYr = partialLatest ? lastPoint.y : null;
  // Compute over EXACTLY the selected window — latest year included, never dropped.
  const last      = ts[ts.length - 1] || { v: 0, q_mass: 0, q_vol: 0, q_count: 0, y: null };
  const prev      = ts[ts.length - 2] || last;
  const first     = ts[0] || last;
  const deltaV    = prev.v ? ((last.v - prev.v) / prev.v) * 100 : 0;
  const deltaTotV = first.v ? ((last.v - first.v) / first.v) * 100 : 0;
  const spark12   = ts.slice(-12);
  // Year tag that marks the latest year "(parcial)" wherever it is shown.
  const yTag      = (y) => `${y ?? ''}${partialLatest && y === partialYr ? ' (parcial)' : ''}`;
  // basket × UF can't be combined until the product×UF cube loads (dataFilters.js):
  // the value would silently drop the basket, so hold it at a loading state instead.
  const comboPending = !!filtered.geoComboPending;
  const kpiVal = (fmt) => (comboPending ? '…' : fmt);

  // Quality digest from filtered flag set
  const okFlag    = filtered.qualityFlags.find(f => f.id === 'OK');
  const okShare   = okFlag ? okFlag.share : 0;
  const okCount   = okFlag ? okFlag.count : 0;

  // "UFs cobertas" must count REAL Brazilian states only. For a trade banco
  // (COMEX) ufData includes non-state pseudo-origins (ND/EX/ZN/CB/RE/MC…) that
  // are not UFs, so counting every row with value>0 yielded a nonsensical 32/27.
  // The backend now flags each row `real` (true = Brazilian UF); we count those.
  // Fallback (older payloads / synthetic data lacking `real`): intersect with the
  // canonical 27-UF registry (window.UF_DATA) so pseudo-codes never inflate it.
  const isRealUf  = u => (u.real != null ? u.real : window.isCanonicalUf(u.uf));
  const realUfs   = filtered.ufData.filter(isRealUf);
  // A value-less basket (the livestock herd — a stock) has R$ 0 everywhere, so the geo
  // digest must read HEADCOUNT (q_count); reading value would give an empty map + 0/27
  // UFs covered. A value-bearing basket is unaffected (onCount stays false).
  const anyValue  = realUfs.some(u => u.value > 0) || ts.some(d => d.v > 0);
  const onCount   = !anyValue && families.includes('count');
  const geoVal    = u => (onCount ? (u.q_count || 0) : u.value);
  const ufCovered = realUfs.filter(u => geoVal(u) > 0).length;
  // Denominator = real UFs in the banco's full set, capped at the canonical 27.
  const ufTotalReal = Math.min(
    27,
    filtered.ufDataFull.filter(isRealUf).length || 27,
  );
  const top3      = realUfs.slice().sort((a, b) => geoVal(b) - geoVal(a)).slice(0, 3);
  const hasGeo    = filtered.ufDataFull.length > 0;
  // The tile map is scoped to the latest UF year IN the window, which can fall short
  // of yearEnd (future/partial endDate). Label it with the data's OWN year so the
  // caption never diverges from what's plotted (FINDING #1).
  const mapYear    = filtered.ufLatestYear != null ? filtered.ufLatestYear : filtered.yearEnd;
  // Mark "(parcial)" when EITHER the UF data lags the window end (ufYearPartial)
  // OR the map year is the calendar-partial latest year (FINDING #3 signal), so
  // the spatial snapshot is as honest as the time-series point.
  const mapPartial = filtered.ufYearPartial || (partialLatest && mapYear === partialYr);
  const mapYearTag = mapPartial ? `${mapYear} (parcial)` : `${mapYear}`;
  // The composition donut shows the latest year (yearEnd); mark it partial too when
  // that trailing year is incomplete, consistent with the map + series.
  const compYearTag = (partialLatest && filtered.yearEnd === partialYr)
    ? `${filtered.yearEnd} (parcial)`
    : `${filtered.yearEnd}`;

  const massFamily = families.includes('mass');
  const volFamily  = families.includes('volume');
  const countFamily = families.includes('count');  // PPM livestock head / eggs
  // The aggregate count KPI sums the WHOLE count family (herd STOCK + egg FLOW + every
  // species) — heads are not additive, so that headline is a meaningless blend. Suppress
  // it when a stock is in the basket and point researchers to the per-species Rebanho view.
  const hasStock = (filtered.products || []).some(
    p => p.measure_kind === 'stock' && (filtered.selectedProducts || []).includes(p.code));

  return (
    <>
      <window.UnitFamilyBanner families={families} />
      <window.RecorteNote recorte={filtered.recorte} />

      {/* KPI strip */}
      <div className="kpi-row">
        <window.KpiCardSpark
          label={`Valor total · ${monLabel}`}
          value={kpiVal(window.formatValue(last.v, conv))}
          delta={comboPending ? null : window.fmtSigned(deltaV)}
          deltaPositive={deltaV >= 0}
          sub={comboPending ? 'cruzando produto × UF…' : `${yTag(last.y)} vs. ${prev.y || ''}`}
          spark={comboPending ? null : window.convertSeries(spark12, conv)}
          sparkKey="v"
          sparkColor="var(--viz-1)"
        />
        {massFamily && (
          <window.KpiCardSpark
            label={<>Quantidade · <window.UnitFamilyTag family="mass" conv={conv}/></>}
            value={kpiVal(window.formatMassQty(last.q_mass, conv))}
            delta={comboPending ? null : window.fmtSigned(prev.q_mass ? ((last.q_mass - prev.q_mass) / prev.q_mass) * 100 : 0)}
            deltaPositive={last.q_mass >= prev.q_mass}
            sub={comboPending ? 'cruzando produto × UF…' : `${yTag(last.y)} vs. ${prev.y || ''}`}
            spark={comboPending ? null : spark12}
            sparkKey="q_mass"
            sparkColor="var(--viz-2)"
          />
        )}
        {volFamily && (
          <window.KpiCardSpark
            label={<>Quantidade · <window.UnitFamilyTag family="volume" conv={conv}/></>}
            value={kpiVal(window.formatVolumeQty(last.q_vol, conv))}
            delta={comboPending ? null : window.fmtSigned(prev.q_vol ? ((last.q_vol - prev.q_vol) / prev.q_vol) * 100 : 0)}
            deltaPositive={last.q_vol >= prev.q_vol}
            sub={comboPending ? 'cruzando produto × UF…' : `${yTag(last.y)} vs. ${prev.y || ''}`}
            spark={comboPending ? null : spark12}
            sparkKey="q_vol"
            sparkColor="var(--viz-4)"
          />
        )}
        {countFamily && !hasStock && (
          <window.KpiCardSpark
            label={<>Quantidade · <window.UnitFamilyTag family="count" conv={conv}/></>}
            value={kpiVal(window.formatCountQty(last.q_count, conv))}
            delta={comboPending ? null : window.fmtSigned(prev.q_count ? ((last.q_count - prev.q_count) / prev.q_count) * 100 : 0)}
            deltaPositive={last.q_count >= prev.q_count}
            sub={comboPending ? 'cruzando produto × UF…' : `${yTag(last.y)} vs. ${prev.y || ''}`}
            spark={comboPending ? null : spark12}
            sparkKey="q_count"
            sparkColor="var(--viz-9)"
          />
        )}
        {/* Quality is a banco-wide (acervo) figure: applyFilters narrows quality
            ONLY by the flag chips, never by basket/UF/period (the API has no
            per-basket quality). The other KPIs in this strip ARE filtered, so we
            mark the scope here rather than present an acervo % as if it were
            scoped to the active selection ("no invisible filtering"). */}
        <window.KpiCardSpark
          label="Linhas íntegras (Normais)"
          value={window.fmtPct(okShare)}
          sub={okCount
            ? (okCount / 1e6).toFixed(1).replace('.', ',') + ' mi linhas · acervo do banco'
            : 'OK não selecionada · acervo do banco'}
          spark={filtered.qualityTs.slice(-12)}
          sparkKey="ok"
          sparkColor="var(--ok)"
        />
      </div>

      {countFamily && hasStock && (
        <p className="caption" style={{ margin: '-4px 2px 8px' }}>
          ⓘ O <strong>efetivo dos rebanhos</strong> (cabeças) não entra como um KPI agregado aqui —
          cabeças não são somáveis entre espécies. Veja a perspectiva <strong>Rebanho</strong> para a
          composição e a evolução por espécie.
        </p>
      )}

      {/* Hero: timeseries + composition */}
      <div className="grid-2">
        <div className="card">
          {(() => {
            const series = window.convertSeries(ts, conv);
            const max = Math.max(...series.map(d => d.v), 0);
            const { data, label } = window.scaleSeries(series, max, conv, 'v', valAxis);
            return (
              <>
                <window.SectionHeader
                  overline={`Série histórica · ${filtered.yearStart}–${yTag(filtered.yearEnd)} · ${monLabel}`}
                  title={comboPending ? 'Variação acumulada: …' : 'Variação acumulada: ' + window.fmtSigned(deltaTotV, 0)}
                />
                {comboPending ? (
                  <p className="caption" style={{ padding: '24px 4px', textAlign: 'center' }}>
                    Cruzando o filtro de <strong>produtos</strong> com o de <strong>UFs</strong>…
                  </p>
                ) : (
                  <window.LineChart data={data} label={label} valueKey="v" color="var(--viz-1)" height={240} />
                )}
                {!comboPending && partialLatest && (
                  <p className="caption" style={{ padding: '8px 4px 0' }}>
                    <strong>{partialYr} (parcial):</strong> o ano mais recente cobre apenas
                    {' '}{latestMeta?.monthsInLatestYear ? `${latestMeta.monthsInLatestYear} ${latestMeta.monthsInLatestYear === 1 ? 'mês' : 'meses'}` : 'parte do ano'}.
                    Os valores e a variação anual acima refletem esse ano parcial, conforme o período que você
                    selecionou — a comparação com o ano anterior (completo) não é direta.
                  </p>
                )}
              </>
            );
          })()}
        </div>

        <div className="card">
          <window.SectionHeader
            overline={`Composição · ${compYearTag}`}
            title="Participação por produto"
            action={<span className="caption">{filtered.selectedProducts.length} de {filtered.productsTotal} produtos</span>}
          />
          {filtered.topProducts.length === 0 ? (
            <p className="caption" style={{ padding: '24px 4px', textAlign: 'center' }}>
              Nenhum produto selecionado nos filtros.
            </p>
          ) : (
            // O Donut rotula cada fatia por `name`. Sem desambiguar, duas metades do
            // PEVS que dividem o nome viram duas fatias com o MESMO rótulo — "Madeira em
            // tora 57%" e "Madeira em tora 7%" — e o leitor não sabe qual é qual. Não
            // funde nada (a chave é o índice), mas informa igualmente mal.
            <window.Donut data={window.labelProductRows(filtered.topProducts, database)}
                          size={180} valueKey="share" />
          )}
        </div>
      </div>

      {/* Geo digest + quality digest */}
      <div className="grid-2">
        {hasGeo && (
        <div className="card">
          {(() => {
            // Only REAL UFs reach the tile map: a trade banco's ufData carries
            // non-state pseudo-origins (ND/EX/ZN…) with no tile col/row, which the
            // BrazilTileMap would position at `undefined * cell = NaN` (FINDING #4/#5).
            // Measure-aware: a value-less herd basket maps HEADCOUNT (q_count → cabeças)
            // instead of an all-zero value. geoVal already selects the right field.
            const geoMul  = onCount ? window.countQtyMul(conv) : (1e6 * ufFactor);
            const geoUnit = onCount ? window.countAxisLabel(conv) : valAxis;
            const ufRows = realUfs.map(u => ({
              ...u,
              value: geoVal(u) * geoMul,
            }));
            return (
              <>
                <window.SectionHeader
                  overline={`Distribuição geográfica · ${mapYearTag}`}
                  title={`${onCount ? 'Cabeças' : 'Valor'} por UF · ${geoUnit}`}
                  action={
                    <span className="caption">
                      {top3.length ? 'Top 3: ' + top3.map(u => u.uf).join(' · ') : '—'}
                    </span>
                  }
                />
                {/* RAW values + base unit: the tile map formats each UF with its OWN compact
                    magnitude (per-tile), so the global auto-scale — which floored small UFs to
                    "0" when ON — is intentionally NOT applied to the map. */}
                {/* Clicking a UF filters the whole dashboard to it (click again to
                    clear) — the same gesture the Geografia map offers. Safe here
                    because this map reads applyFilters' state-filtered ufData, so it
                    actually reacts to the click. */}
                <window.BrazilTileMap
                  data={ufRows}
                  valueKey="value"
                  label={geoUnit}
                  onSelect={window.tileSelectHandler && window.tileSelectHandler(summary)}
                  selectedUf={window.selectedSingleUf && window.selectedSingleUf(summary)}
                />
                {filtered.ufYearPartial && (
                  <p className="caption" style={{ padding: '8px 4px 0' }}>
                    <strong>{mapYear} (parcial):</strong> o último ano com dados por UF fica antes do
                    fim do período ({filtered.yearEnd}); o mapa mostra {mapYear}.
                  </p>
                )}
                {filtered.notFilteredByBasket && (
                  <p className="caption" style={{ padding: '8px 4px 0' }}>
                    O mapa reflete <strong>todos os produtos</strong> — a cesta selecionada não
                    recorta a distribuição por UF (sem grão produto × UF nesta agregação).
                  </p>
                )}
              </>
            );
          })()}
        </div>
        )}

        <div className="card">
          <window.SectionHeader
            overline="Qualidade dos dados · agregado"
            title={hasGeo
              ? ('Cobertura geográfica: ' + ufCovered + ' / ' + ufTotalReal + ' UFs')
              : 'Distribuição de flags de qualidade'}
            action={<span className="caption">{filtered.qualityFlags.length} de {window.QUALITY_FLAGS.length} flags</span>}
          />
          <div className="qa-summary">
            {filtered.qualityFlags.map(f => (
              <div key={f.id} className="qa-row">
                <span className="qa-dot" style={{ background: f.color }}></span>
                <span className="qa-label">{f.label}</span>
                <span className="qa-count tnum">{(f.count / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}k</span>
                <span className="qa-share tnum">{window.fmtPct(f.share)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

window.ViewOverview = ViewOverview;
