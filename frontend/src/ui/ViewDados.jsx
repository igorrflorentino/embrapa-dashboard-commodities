// ViewDados — the "Estrutura de dados" perspective: the central place to investigate the
// tables behind a banco across ALL FOUR medallion layers (Bronze → Silver → Gold → Serving).
// The table picker is grouped by layer with a per-layer explanation (the medallion overview
// lives here, not in the onboarding "Sobre" page); for the selected table it browses the RAW
// rows with server-side pagination, ORDER BY and per-column filters. The (banco, table) pair +
// every column are validated server-side against the allowlist / the table's OWN schema (a bad
// one → 400). Browsing is free (tabledata.list); ORDER BY / filter is cost-guarded. Bronze and
// Silver are pre-curation raw lineage (shown ungated on purpose — a transparency/audit tool).
// Self-contained (its own fetch + state) — no chart, no rescaling: a faithful window onto the
// data so a researcher can verify line-by-line, trace a number's origin, or hunt a suspected bug.

const { useState: useDtState, useEffect: useDtEffect } = React;

// Filter operators the UI offers → the server's op ids (validated + bound server-side).
const _DT_OPS = [
  { id: 'eq', label: '=' }, { id: 'ne', label: '≠' },
  { id: 'gt', label: '>' }, { id: 'ge', label: '≥' },
  { id: 'lt', label: '<' }, { id: 'le', label: '≤' },
  { id: 'contains', label: 'contém' },
  { id: 'is_null', label: 'é nulo' }, { id: 'not_null', label: 'não nulo' },
];
const _DT_VALUELESS = new Set(['is_null', 'not_null']);
const _DT_PAGE = 100;       // rows per page
const _DT_EXPORT_CAP = 500; // server's RAW_TABLE_MAX_LIMIT — the most one fetch returns

// The four medallion layers, in lineage order — groups the table picker and explains what
// each layer IS (the conceptual pipeline overview, the home for medallion/table detail).
// `layer` on each /api/tables row decides which group a table falls into.
const _DT_LAYERS = [
  { id: 'bronze',  label: 'Bronze',  hint: 'bruto',                desc: 'Cópia fiel das fontes oficiais, sem nenhuma alteração — cada extração registrada com a data de coleta, para rastreabilidade.' },
  { id: 'silver',  label: 'Silver',  hint: 'padronizado',          desc: 'Códigos de produto reconciliados entre fontes, séries históricas reconstruídas, tipos corrigidos e a marca de confiabilidade de cada valor.' },
  { id: 'gold',    label: 'Gold',    hint: 'analítico completo',   desc: 'Uma tabela abrangente por fonte, já com a conversão de moeda e a correção pela inflação aplicadas — a base de toda a análise.' },
  { id: 'serving', label: 'Serving', hint: 'pronto para o painel', desc: 'Recortes pré-agregados na granularidade exata de cada gráfico, derivados do Gold — é daqui que o painel lê todos os números.' },
];
// Per-layer left-border accent (reuses the About pipeline palette tokens).
const _DT_LAYER_COLOR = { bronze: '#a87b4f', silver: '#8a8f98', gold: '#c9a227', serving: 'var(--viz-2, #2f7ed8)' };

function _dtCsv(columns, rows) {
  const esc = (v) => {
    if (v == null) return '';
    const s = String(v);
    return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const head = columns.map((c) => esc(c.name)).join(';');
  const body = rows.map((r) => r.map(esc).join(';')).join('\n');
  return '﻿' + head + '\n' + body; // BOM for Excel UTF-8; pt-BR-friendly ';'
}

function _dtDownload(name, csv) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function _dtTableQs(database, table, { limit, offset, order, filters }) {
  const qs = new URLSearchParams({ banco: database, table, limit, offset });
  if (order && order.by) { qs.set('order_by', order.by); qs.set('order_dir', order.dir); }
  if (filters && filters.length) qs.set('filters', JSON.stringify(filters));
  return qs;
}

function ViewDados({ database }) {
  const [tables, setTables] = useDtState([]);
  const [table, setTable] = useDtState(null);
  // The banco the current `table` belongs to. On a banco switch the rows effect fires
  // once with the PREVIOUS banco's table (stale closure) before the new table list lands;
  // gating on tableBanco === database refuses that stale pairing (no transient 400 flash).
  const [tableBanco, setTableBanco] = useDtState(null);
  const [page, setPage] = useDtState({ columns: [], rows: [], total: 0, loading: true, error: null });
  const [offset, setOffset] = useDtState(0);
  const [order, setOrder] = useDtState({ by: null, dir: 'asc' });
  const [filters, setFilters] = useDtState([]);
  const [draft, setDraft] = useDtState({ col: '', op: 'eq', val: '' });
  const [exportErr, setExportErr] = useDtState(null);

  // Reset the per-table state (offset/order/filters) — used on banco or table change.
  const resetView = () => { setOffset(0); setOrder({ by: null, dir: 'asc' }); setFilters([]); setDraft({ col: '', op: 'eq', val: '' }); };

  // 1) the allowlisted table list for the banco
  useDtEffect(() => {
    let alive = true;
    resetView();
    fetch(`/api/tables?banco=${encodeURIComponent(database)}`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list) => {
        if (!alive) return;
        setTables(Array.isArray(list) ? list : []);
        setTable(list && list[0] ? list[0].id : null);
        setTableBanco(database);
      })
      .catch(() => { if (alive) { setTables([]); setTable(null); setTableBanco(database); } });
    return () => { alive = false; };
  }, [database]);

  // 2) one page of rows for the selected table + pagination/sort/filter
  useDtEffect(() => {
    // Skip until a table is chosen FOR THIS banco (tableBanco===database) — avoids a
    // stale (new banco, old table) fetch flashing a 400 during a banco switch.
    if (!table || tableBanco !== database) { setPage({ columns: [], rows: [], total: 0, loading: false, error: null }); return undefined; }
    let alive = true;
    setPage((p) => ({ ...p, loading: true, error: null }));
    const qs = _dtTableQs(database, table, { limit: _DT_PAGE, offset, order, filters });
    fetch(`/api/table?${qs}`)
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => null);
          throw new Error((body && body.error) || `HTTP ${r.status}`);
        }
        return r.json();
      })
      .then((d) => { if (alive) setPage({ columns: d.columns || [], rows: d.rows || [], total: d.total || 0, label: d.label, grain: d.grain, loading: false, error: null }); })
      .catch((e) => { if (alive) setPage({ columns: [], rows: [], total: 0, loading: false, error: String(e.message || e) }); });
    return () => { alive = false; };
  }, [database, table, tableBanco, offset, order, filters]);

  const meta = tables.find((t) => t.id === table) || {};
  const cols = page.columns;
  const total = page.total;
  const pageNum = Math.floor(offset / _DT_PAGE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / _DT_PAGE));

  const toggleSort = (name) => {
    setOffset(0);
    setOrder((o) =>
      o.by !== name ? { by: name, dir: 'asc' }
        : o.dir === 'asc' ? { by: name, dir: 'desc' }
          : { by: null, dir: 'asc' }); // third click clears the sort
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
    // Export the CURRENT filter/sort (not just the visible page) up to the server cap.
    const qs = _dtTableQs(database, table, { limit: _DT_EXPORT_CAP, offset: 0, order, filters });
    fetch(`/api/table?${qs}`)
      // Surface an export failure (a click with no download and no message is a dead end).
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d) => { _dtDownload(`${database}_${table}.csv`, _dtCsv(d.columns || [], d.rows || [])); })
      .catch(() => setExportErr('Falha ao exportar CSV. Tente novamente.'));
  };

  return (
    <>
      {/* Medallion-layer table explorer — the lineage behind this banco, Bronze → Serving.
          Each layer's tables are browsable line-by-line; this is the home for table + layer detail. */}
      <div className="card">
        <window.SectionHeader
          overline="Estrutura de dados"
          title="As tabelas por trás deste banco, camada a camada"
        />
        <p className="caption" style={{ margin: '0 2px 14px' }}>
          Os dados percorrem quatro camadas, da cópia bruta da fonte oficial (Bronze) ao recorte
          que o painel consome (Serving). Escolha qualquer tabela para investigá-la linha a linha.
          As camadas <strong>Bronze</strong> e <strong>Silver</strong> são o dado cru, anterior à
          curadoria — úteis para auditar a origem de um número.
        </p>
        {_DT_LAYERS.map((L) => {
          const layerTables = tables.filter((t) => t.layer === L.id);
          if (!layerTables.length) return null;
          return (
            <div key={L.id} className="dt-layer"
                 style={{ borderLeft: `3px solid ${_DT_LAYER_COLOR[L.id]}`, padding: '4px 0 4px 12px', margin: '0 0 14px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <strong style={{ fontSize: 13, letterSpacing: '0.04em' }}>{L.label}</strong>
                <span className="caption" style={{ textTransform: 'uppercase', fontSize: 10 }}>{L.hint}</span>
              </div>
              <p className="caption" style={{ margin: '2px 0 8px' }}>{L.desc}</p>
              <div className="pp-chips">
                {layerTables.map((t) => (
                  <button key={t.id} type="button" title={t.grain}
                          className={'pp-chip ' + (t.id === table ? 'on' : '')}
                          onClick={() => { setTable(t.id); setTableBanco(database); resetView(); }}>
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
        {!tables.length && <span className="caption">Nenhuma tabela inspecionável para este banco.</span>}
      </div>

      {table && (
        <div className="card">
          <window.SectionHeader
            overline={`Inspeção tabular · ${meta.label || table}`}
            title={`${(total || 0).toLocaleString('pt-BR')} linhas · ${cols.length} colunas`}
            action={
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                {exportErr && <span className="caption" role="alert" style={{ color: 'var(--err, #b71c1c)' }}>{exportErr}</span>}
                <button type="button" className="btn-secondary" onClick={exportCsv} disabled={!cols.length}>
                  Exportar CSV (até {_DT_EXPORT_CAP})
                </button>
              </span>
            }
          />
          {meta.grain && <p className="caption" style={{ margin: '0 2px 8px' }}>{meta.grain}</p>}

          {/* Filter builder */}
          <div className="dt-filterbar">
            <select aria-label="Coluna do filtro" value={draft.col} onChange={(e) => setDraft((d) => ({ ...d, col: e.target.value }))}>
              <option value="">coluna…</option>
              {cols.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
            <select aria-label="Operador do filtro" value={draft.op} onChange={(e) => setDraft((d) => ({ ...d, op: e.target.value }))}>
              {_DT_OPS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            {!_DT_VALUELESS.has(draft.op) && (
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
                  {f.col} {(_DT_OPS.find((o) => o.id === f.op) || {}).label} {!_DT_VALUELESS.has(f.op) ? f.val : ''}
                  <button type="button" onClick={() => removeFilter(i)} aria-label="remover filtro">×</button>
                </span>
              ))}
            </div>
          )}

          {/* Grid */}
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
                      onClick={() => setOffset(Math.max(0, offset - _DT_PAGE))}>‹ Anterior</button>
              <span className="caption tnum">
                Página {pageNum.toLocaleString('pt-BR')} de {pageCount.toLocaleString('pt-BR')} ·
                {' '}linhas {(offset + 1).toLocaleString('pt-BR')}–{Math.min(offset + _DT_PAGE, total).toLocaleString('pt-BR')}
                {' '}de {total.toLocaleString('pt-BR')}
              </span>
              <button type="button" className="btn-secondary" disabled={offset + _DT_PAGE >= total}
                      onClick={() => setOffset(offset + _DT_PAGE)}>Próxima ›</button>
            </div>
          )}
        </div>
      )}
    </>
  );
}

window.ViewDados = ViewDados;
