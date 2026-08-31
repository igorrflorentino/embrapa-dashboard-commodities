// ViewReferencias — read-only consultation of the pipeline's REFERENCE SEEDS (the
// "Referências" perspective). Banco-agnostic: the seeds are shared reference data (unit
// conversions, currency-reform factors, country/NCM/HS dimensions, the commodity
// crosswalk, the municipal mesh). Lists the consultable seeds; for the selected one it
// browses the rows with the SAME server-side pagination / ORDER BY / per-column filter
// grid as ViewDados, but READ-ONLY. Each seed shows its pt-BR description + an
// editable/read-only badge, and a researcher who spots a wrong value can REPORT it via
// the feedback channel (prefilled with the seed + the suspect row) — the consult →
// confirm → report loop, WITHOUT any edit rights here. Self-contained (its own fetch +
// state), matching the ViewDados pattern.

const { useState: useRfState, useEffect: useRfEffect } = React;

// Filter operators the UI offers → the server's op ids (validated + bound server-side);
// identical set to ViewDados (the /api/seed grid shares /api/table's contract).
const _RF_OPS = [
  { id: 'eq', label: '=' }, { id: 'ne', label: '≠' },
  { id: 'gt', label: '>' }, { id: 'ge', label: '≥' },
  { id: 'lt', label: '<' }, { id: 'le', label: '≤' },
  { id: 'contains', label: 'contém' },
  { id: 'is_null', label: 'é nulo' }, { id: 'not_null', label: 'não nulo' },
];
const _RF_VALUELESS = new Set(['is_null', 'not_null']);
const _RF_PAGE = 100;       // rows per page
const _RF_EXPORT_CAP = 500; // server's RAW_TABLE_MAX_LIMIT — the most one fetch returns

function _rfCsv(columns, rows) {
  const esc = (v) => {
    if (v == null) return '';
    const s = String(v);
    return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const head = columns.map((c) => esc(c.name)).join(';');
  const body = rows.map((r) => r.map(esc).join(';')).join('\n');
  return '﻿' + head + '\n' + body; // BOM for Excel UTF-8; pt-BR-friendly ';'
}

function _rfDownload(name, csv) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function _rfSeedQs(seedId, { limit, offset, order, filters }) {
  const qs = new URLSearchParams({ id: seedId, limit, offset });
  if (order && order.by) { qs.set('order_by', order.by); qs.set('order_dir', order.dir); }
  if (filters && filters.length) qs.set('filters', JSON.stringify(filters));
  return qs;
}

function ViewReferencias() {
  const [seeds, setSeeds] = useRfState([]);
  const [seedsError, setSeedsError] = useRfState(false);
  const [exportErr, setExportErr] = useRfState(null);
  const [seedId, setSeedId] = useRfState(null);
  const [page, setPage] = useRfState({ columns: [], rows: [], total: 0, loading: true, error: null, editable: false });
  const [offset, setOffset] = useRfState(0);
  const [order, setOrder] = useRfState({ by: null, dir: 'asc' });
  const [filters, setFilters] = useRfState([]);
  const [draft, setDraft] = useRfState({ col: '', op: 'eq', val: '' });

  const resetView = () => { setOffset(0); setOrder({ by: null, dir: 'asc' }); setFilters([]); setDraft({ col: '', op: 'eq', val: '' }); };

  // 1) the consultable seed catalog (static, banco-agnostic)
  useRfEffect(() => {
    let alive = true;
    fetch('/api/seeds')
      // The seed catalog is STATIC (no BigQuery round-trip) so it is never legitimately
      // empty — an empty result can only be a load failure. Route non-ok/network into an
      // explicit error state instead of the misleading "Nenhuma tabela disponível".
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((list) => {
        if (!alive) return;
        setSeeds(Array.isArray(list) ? list : []);
        setSeedId(list && list[0] ? list[0].id : null);
        setSeedsError(false);
      })
      .catch(() => { if (alive) { setSeeds([]); setSeedId(null); setSeedsError(true); } });
    return () => { alive = false; };
  }, []);

  // 2) one page of rows for the selected seed + pagination/sort/filter
  useRfEffect(() => {
    if (!seedId) { setPage({ columns: [], rows: [], total: 0, loading: false, error: null, editable: false }); return undefined; }
    let alive = true;
    setPage((p) => ({ ...p, loading: true, error: null }));
    const qs = _rfSeedQs(seedId, { limit: _RF_PAGE, offset, order, filters });
    fetch(`/api/seed?${qs}`)
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => null);
          throw new Error((body && body.error) || `HTTP ${r.status}`);
        }
        return r.json();
      })
      .then((d) => { if (alive) setPage({ columns: d.columns || [], rows: d.rows || [], total: d.total || 0, label: d.label, grain: d.grain, editable: !!d.editable, loading: false, error: null }); })
      .catch((e) => { if (alive) setPage({ columns: [], rows: [], total: 0, loading: false, error: String(e.message || e), editable: false }); });
    return () => { alive = false; };
  }, [seedId, offset, order, filters]);

  const meta = seeds.find((s) => s.id === seedId) || {};
  const cols = page.columns;
  const total = page.total;
  const pageNum = Math.floor(offset / _RF_PAGE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / _RF_PAGE));

  const toggleSort = (name) => {
    setOffset(0);
    setOrder((o) =>
      o.by !== name ? { by: name, dir: 'asc' }
        : o.dir === 'asc' ? { by: name, dir: 'desc' }
          : { by: null, dir: 'asc' });
  };
  const addFilter = () => {
    if (!draft.col) return;
    setOffset(0);
    setFilters((fs) => [
      ...fs.filter((f) => !(f.col === draft.col && f.op === draft.op)),
      { col: draft.col, op: draft.op, val: draft.val },
    ]);
    setDraft((d) => ({ ...d, val: '' }));
  };
  const removeFilter = (i) => { setOffset(0); setFilters((fs) => fs.filter((_, j) => j !== i)); };

  const exportCsv = () => {
    setExportErr(null);
    const qs = _rfSeedQs(seedId, { limit: _RF_EXPORT_CAP, offset: 0, order, filters });
    fetch(`/api/seed?${qs}`)
      // Don't swallow an export failure: a click with no download and no message is a dead
      // end. Surface a pt-BR error so the researcher knows the export failed (vs succeeded).
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d) => { _rfDownload(`referencia_${seedId}.csv`, _rfCsv(d.columns || [], d.rows || [])); })
      .catch(() => setExportErr('Falha ao exportar CSV. Tente novamente.'));
  };

  // Report a value that looks wrong → opens the feedback dialog PREFILLED with the seed
  // + the suspect row. No edit rights are granted here: the report is an immutable,
  // IAP-attributed audit row the dev team triages and fixes in the version-controlled CSV.
  const reportRow = (row) => {
    if (!window.openFeedback) return;
    const pairs = cols.map((c, i) => `${c.name}: ${row[i] == null ? '∅' : row[i]}`).join(' · ');
    window.openFeedback({
      view: 'referencias',
      category: 'bug',
      message:
        `[Referência: ${meta.label || seedId} (${seedId})]\n` +
        `Valor que parece incorreto, na linha:\n${pairs}\n\n` +
        `O que está errado e qual seria o valor esperado? `,
    });
  };

  return (
    <>
      {/* Seed picker — the consultable reference tables (shared across bancos) */}
      <div className="pp-selector">
        <span className="pp-selector-label">
          Tabela de referência <small className="pc-cap">(valores de referência usados pelo pipeline)</small>
        </span>
        <div className="pp-chips">
          {seeds.map((s) => (
            <button key={s.id} type="button" title={s.description}
                    className={'pp-chip ' + (s.id === seedId ? 'on' : '')}
                    onClick={() => { setSeedId(s.id); resetView(); }}>
              {s.label}
            </button>
          ))}
          {!seeds.length && (
            <span className="caption" style={seedsError ? { color: 'var(--err, #b71c1c)' } : undefined}>
              {seedsError
                ? 'Não foi possível carregar as tabelas de referência. Recarregue a página.'
                : 'Nenhuma tabela de referência disponível.'}
            </span>
          )}
        </div>
      </div>

      {seedId && (
        <div className="card">
          <window.SectionHeader
            overline={`Referência · ${meta.label || seedId}`}
            title={`${(total || 0).toLocaleString('pt-BR')} linhas · ${cols.length} colunas`}
            action={
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                {exportErr && <span className="caption" style={{ color: 'var(--err, #b71c1c)' }}>{exportErr}</span>}
                <button type="button" className="btn-secondary" onClick={exportCsv} disabled={!cols.length}>
                  Exportar CSV (até {_RF_EXPORT_CAP})
                </button>
              </span>
            }
          />

          {/* Editable / read-only badge + the seed's pt-BR description ("Sobre esta tabela") */}
          <div className="rf-about" style={{ margin: '0 2px 10px' }}>
            <span
              className="badge"
              style={{
                display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px',
                borderRadius: 10, marginBottom: 6,
                background: meta.editable ? 'var(--info-bg, #e6f0ff)' : 'var(--subtle-bg, #f1f1f1)',
                color: meta.editable ? 'var(--info, #1457b8)' : 'var(--muted, #555)',
              }}>
              {meta.editable ? 'Editável pelo cadastro de produtos' : 'Somente leitura · calibração'}
            </span>
            {meta.description && <p className="caption" style={{ margin: 0 }}>{meta.description}</p>}
            {!meta.editable && (
              <p className="caption" style={{ margin: '4px 0 0' }}>
                Este valor é mantido pela equipe de desenvolvimento. Encontrou algo errado? Use o
                botão <strong>⚠</strong> na linha para avisar a equipe.
              </p>
            )}
          </div>

          {/* Filter builder (same contract as a Dados table) */}
          <div className="dt-filterbar">
            <select aria-label="Coluna do filtro" value={draft.col} onChange={(e) => setDraft((d) => ({ ...d, col: e.target.value }))}>
              <option value="">coluna…</option>
              {cols.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
            <select aria-label="Operador do filtro" value={draft.op} onChange={(e) => setDraft((d) => ({ ...d, op: e.target.value }))}>
              {_RF_OPS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            {!_RF_VALUELESS.has(draft.op) && (
              <input type="text" placeholder="valor" aria-label="Valor do filtro" value={draft.val}
                     onChange={(e) => setDraft((d) => ({ ...d, val: e.target.value }))}
                     onKeyDown={(e) => e.key === 'Enter' && addFilter()} />
            )}
            <button type="button" className="btn-secondary" onClick={addFilter} disabled={!draft.col}>Filtrar</button>
          </div>
          {filters.length > 0 && (
            <div className="dt-chips">
              {filters.map((f, i) => (
                <span key={i} className="dt-chip">
                  {f.col} {(_RF_OPS.find((o) => o.id === f.op) || {}).label} {!_RF_VALUELESS.has(f.op) ? f.val : ''}
                  <button type="button" onClick={() => removeFilter(i)} aria-label="remover filtro">×</button>
                </span>
              ))}
            </div>
          )}

          {/* Grid (read-only) with a per-row "reportar valor" action */}
          {page.error ? (
            <p className="caption" style={{ padding: '20px 4px', color: 'var(--err)' }}>
              Erro ao carregar: {page.error}
            </p>
          ) : page.loading ? (
            <p className="caption" style={{ padding: '40px 4px', textAlign: 'center' }}>Carregando linhas…</p>
          ) : !page.rows.length ? (
            <p className="caption" style={{ padding: '40px 4px', textAlign: 'center' }}>
              Nenhuma linha para os filtros atuais.
            </p>
          ) : (
            <div className="dt-wrap">
              <table className="dt-table">
                <thead>
                  <tr>
                    <th aria-label="reportar" style={{ width: 28 }}></th>
                    {cols.map((c) => (
                      <th key={c.name} onClick={() => toggleSort(c.name)} title={`${c.type} · clique para ordenar`}>
                        {c.name}{order.by === c.name ? (order.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {page.rows.map((row, ri) => (
                    <tr key={ri}>
                      <td>
                        <button type="button" className="rf-report" title="Reportar um valor incorreto nesta linha"
                                aria-label="Reportar um valor incorreto nesta linha"
                                onClick={() => reportRow(row)}
                                style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--muted, #888)' }}>
                          ⚠
                        </button>
                      </td>
                      {row.map((v, ci) => (
                        <td key={ci} className={typeof v === 'number' ? 'num tnum' : ''}>
                          {v == null ? <span className="dt-null">∅</span> : String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {!page.loading && !page.error && total > 0 && (
            <div className="dt-pager">
              <button type="button" className="btn-secondary" disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - _RF_PAGE))}>‹ Anterior</button>
              <span className="caption tnum">
                Página {pageNum.toLocaleString('pt-BR')} de {pageCount.toLocaleString('pt-BR')} ·
                {' '}linhas {(offset + 1).toLocaleString('pt-BR')}–{Math.min(offset + _RF_PAGE, total).toLocaleString('pt-BR')}
                {' '}de {total.toLocaleString('pt-BR')}
              </span>
              <button type="button" className="btn-secondary" disabled={offset + _RF_PAGE >= total}
                      onClick={() => setOffset(offset + _RF_PAGE)}>Próxima ›</button>
            </div>
          )}
        </div>
      )}
    </>
  );
}

window.ViewReferencias = ViewReferencias;
