// csvExport.js — exports the data behind the ACTIVE view, honouring the
// active filters (period, basket, states, value range, quality flags).
// "Exactly what the view shows" — e.g. if the period filter excludes
// pre-2002, the file starts at 2002. Builds a CSV string and triggers a
// client-side download. (In the Cloud Run deploy, the same filtered slice
// is what's held in memory; this writes it out verbatim.)

(function () {
  // A view is exportable when its registry entry (views.js) declares
  // `exportable: true` — i.e. it has an applyFilters-backed tabular slice.
  // Selfdata preview views (fluxos, parceiros, sazonalidade), the cross-source
  // perspectives and the docs views omit the flag, so the export button is
  // hidden for them (see window.canExportView). Single source of truth: the
  // registry, not a parallel id list here.
  window.canExportView = (view) => !!(window.viewById && window.viewById(view)?.exportable);

  function toCSV(headers, rows) {
    const esc = (v) => {
      if (v == null) return '';
      let s = String(v);
      // Spreadsheet formula-injection guard (CWE-1236): a cell beginning with = + @ or a
      // control char (tab/CR) is executed as a formula by Excel/LibreOffice. Researcher-
      // editable commodity/region names flow into this CSV, so neutralize the trigger with a
      // leading apostrophe — but leave plain numbers (incl. negatives) untouched so an
      // exported numeric column stays numeric.
      if (!/^[-+]?\d[\d.,\s]*$/.test(s) && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
      return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const head = headers.join(';');                 // pt-BR friendly delimiter
    const body = rows.map(r => r.map(esc).join(';')).join('\n');
    return '\uFEFF' + head + '\n' + body;           // BOM for Excel UTF-8
  }

  function download(filename, csv) {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // Build the rows for the active view from the FILTERED datasets.
  function buildRows(ctx) {
    const { view, summary, conventions, database } = ctx;
    const conv = conventions || window.DEFAULT_CONVENTIONS;
    const f = window.applyFilters(summary || {}, database);
    const PRODS = f.products;
    const nameOf = (c) => (PRODS.find(p => p.code === c) || {}).name || c;

    // value/qty display transforms (same as the views use)
    const dispV = (vBi) => window.applyConv(vBi, conv);

    switch (view) {
      case 'value':
      case 'overview': {
        // annual aggregate series (value + qty per family)
        const headers = ['ano', `valor_${conv.currency}`, 'qtd_massa_t', 'qtd_volume_m3', 'qtd_contagem_un'];
        const rows = f.ts.map(d => [
          d.y,
          Math.round(dispV(d.v * 1e9)),
          Math.round(d.q_mass * 1e3),
          Math.round(d.q_vol * 1e6),
          Math.round((d.q_count || 0) * 1e6),  // mi un → un (livestock head / eggs)
        ]);
        return { headers, rows, subject: 'serie_agregada' };
      }
      case 'product_profile':
      case 'product_compare': {
        // per-product annual series. productTS.q is in mil t for mass but mi m³ for
        // volume — scaling both by 1e3 (the old code) mixed t and mil m³ under one
        // unitless "quantidade" header. Scale per family to its base unit (mass→t,
        // volume→m³) and emit the unit explicitly so the column is unambiguous.
        const headers = ['ano', 'codigo', 'produto', `valor_${conv.currency}`, 'quantidade', 'unidade', 'familia'];
        // Per-family base unit + multiplier: mass mil t→t, volume mi m³→m³, count mi un→un.
        // The old binary (volume?1e6:1e3 / m³:t) mislabelled a livestock headcount as TONNES
        // and scaled it 1000× wrong; map by family so the column is always correct.
        const FAM_Q = { mass: { mul: 1e3, unit: 't' }, volume: { mul: 1e6, unit: 'm³' }, count: { mul: 1e6, unit: 'un' } };
        const rows = [];
        Object.entries(f.productTS).forEach(([code, series]) => {
          const fam = (PRODS.find(p => p.code === code) || {}).family;
          const { mul: qMul, unit: qUnit } = FAM_Q[fam] || FAM_Q.mass;
          series.forEach(d => rows.push([
            d.y, code, nameOf(code),
            Math.round(dispV(d.v * 1e6)),
            Math.round((d.q || 0) * qMul),
            qUnit,
            fam,
          ]));
        });
        return { headers, rows, subject: 'series_por_produto' };
      }
      case 'geo': {
        // The geo snapshot is a SINGLE year (ufLatestYear), not the whole window, and
        // the basket may not be applied to the map (notFilteredByBasket → all-products).
        // Emit both as explicit columns so the file carries the same caveats the UI shows
        // ("no invisible filtering"): an `ano` column (flagged parcial) + an escopo column.
        const ano = f.ufYearPartial ? `${f.ufLatestYear} (parcial)` : (f.ufLatestYear ?? '');
        const escopo = f.notFilteredByBasket ? 'todos os produtos' : 'cesta selecionada';
        // CONF-4: this always exported the per-UF table even when the researcher had
        // the Granularidade control set to Região or Município — a recorte of 14
        // municípios on screen downloaded as a single PA row. ViewGeography mirrors
        // its own local scope/rows here (window.geoExportScope/geoExportMunis) so the
        // file matches what's actually on screen, exactly like the "no invisible
        // filtering" rule this view already applies everywhere else. Absent/unknown
        // scope (export triggered from elsewhere, or before the view ever mounted)
        // falls back to the per-UF table — the original, always-available shape.
        const geoScope = window.geoExportScope || 'uf';
        if (geoScope === 'region') {
          const headers = ['ano', 'regiao', `valor_${conv.currency}`, 'qtd_massa_t', 'qtd_volume_m3', 'qtd_contagem_un', 'escopo_produto'];
          const rows = (f.regionData || []).map(r => [
            ano, r.label || r.id,
            Math.round(dispV(r.value * 1e6)),
            Math.round((r.q_mass || 0) * 1e3),
            Math.round((r.q_vol || 0) * 1e6),
            Math.round((r.q_count || 0) * 1e6),
            escopo,
          ]);
          return { headers, rows, subject: 'distribuicao_por_regiao' };
        }
        if (geoScope === 'municipio') {
          const munis = Array.isArray(window.geoExportMunis) ? window.geoExportMunis : [];
          const headers = ['ano', 'municipio', 'uf', `valor_${conv.currency}`, 'qtd_massa_t', 'qtd_volume_m3', 'qtd_contagem_un', 'escopo_produto'];
          const rows = munis.map(m => [
            ano, m.city, m.uf,
            Math.round(dispV((m.value || 0) * 1e6)),
            Math.round((m.q_mass || 0) * 1e3),
            Math.round((m.q_vol || 0) * 1e6),
            Math.round((m.q_count || 0) * 1e6),
            escopo,
          ]);
          return { headers, rows, subject: 'distribuicao_por_municipio' };
        }
        const headers = ['ano', 'uf', 'nome', 'regiao', `valor_${conv.currency}`, 'qtd_massa_t', 'qtd_volume_m3', 'qtd_contagem_un', 'escopo_produto'];
        const rows = f.ufData.map(u => [
          ano, u.uf, u.name, u.region,
          Math.round(dispV(u.value * 1e6)),
          Math.round(u.q_mass * 1e3),
          Math.round(u.q_vol * 1e6),
          Math.round((u.q_count || 0) * 1e6),  // mi un → un (livestock head / eggs)
          escopo,
        ]);
        return { headers, rows, subject: 'distribuicao_geografica' };
      }
      case 'concentration': {
        const ano = f.ufYearPartial ? `${f.ufLatestYear} (parcial)` : (f.ufLatestYear ?? '');
        const escopo = f.notFilteredByBasket ? 'todos os produtos' : 'cesta selecionada';
        const headers = ['ano', 'uf', 'nome', 'regiao', `valor_${conv.currency}`, 'qtd_contagem_un', 'escopo_produto'];
        const rows = f.ufData.slice().sort((a, b) => b.value - a.value)
          .map(u => [ano, u.uf, u.name, u.region, Math.round(dispV(u.value * 1e6)), Math.round((u.q_count || 0) * 1e6), escopo]);
        return { headers, rows, subject: 'concentracao' };
      }
      case 'quality': {
        const headers = ['flag', 'descricao', 'linhas', 'participacao'];
        const rows = f.qualityFlags.map(q => [q.id, q.label, q.count, (q.share * 100).toFixed(2).replace('.', ',') + '%']);
        return { headers, rows, subject: 'qualidade' };
      }
      default:
        return null;
    }
  }

  // Public entry — called by the "Exportar CSV" button.
  window.exportActiveTableCSV = function (ctx) {
    const banco = window.bancoById ? window.bancoById(ctx.database) : null;
    // Only live bancos hold real rows; soon bancos have nothing to export.
    if (!banco || banco.status !== 'live') {
      console.warn('[csv] banco not available for export:', ctx.database);
      return;
    }
    const built = buildRows(ctx);
    if (!built || !built.rows.length) {
      console.warn('[csv] nothing to export for view', ctx.view);
      return;
    }
    const period = (ctx.summary && ctx.summary.startDate)
      ? `${ctx.summary.startDate.slice(0,4)}-${(ctx.summary.endDate||'').slice(0,4)}`
      : 'completo';
    const fname = `${banco.short.replace(/\s+/g,'_').toLowerCase()}_${built.subject}_${period}.csv`;
    download(fname, toCSV(built.headers, built.rows));
  };
})();
