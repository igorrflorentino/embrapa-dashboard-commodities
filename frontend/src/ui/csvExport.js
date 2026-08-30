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
    // The sub-UF recorte (meso / micro / intermediária / imediata) narrows the rows
    // WITHOUT removing a UF, so a state's row silently carries a fraction of that state
    // and nothing in the file says so. This header promises "exactly what the view
    // shows"; a downloaded table has no permalink or chip beside it to make up the
    // difference, so it has to carry the recorte itself — the geographic sibling of the
    // escopo_produto column that already rides along.
    // Which half of the PEVS survey the rows cover. A downloaded table has no chip and
    // no permalink beside it, so an axis that changes what a number MEANS has to ride in
    // the file — the same reason escopo_produto and recorte_geografico already do.
    // O recorte por nível de industrialização também sai do produto com o arquivo.
    const nivel = (() => {
      const opts = (window.nivelOptionsFor && window.nivelOptionsFor(database)) || null;
      if (!opts) return null;
      const sel = (summary || {}).niveis;
      if (!sel || !sel.length || sel.length >= opts.length) return 'todos os níveis';
      return sel.map((v) => (opts.find((o) => o.value === v) || {}).label || v).join(' + ');
    })();
    const origem = (() => {
      const opts =
        (window.tabelaOptionsFor && window.tabelaOptionsFor(database)) || null;
      if (!opts) return null;                       // banco has no origem column
      const raw = (summary || {}).tabela;
      if (!raw || raw === 'all') return 'ambas as metades';
      return (opts.find((o) => o.value === raw) || {}).label || raw;
    })();
    const recorte = (window.subUfChipText
      && window.subUfChipText(summary || {}, (window.geoMesh && window.geoMesh()) || []))
      || 'sem recorte sub-UF';
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
          const headers = ['ano', 'regiao', `valor_${conv.currency}`, 'qtd_massa_t', 'qtd_volume_m3', 'qtd_contagem_un', 'escopo_produto', 'recorte_geografico'].concat(origem ? ['tabela_sidra'] : []).concat(nivel ? ['nivel_industrializacao'] : []);
          const rows = (f.regionData || []).map(r => [
            ano, r.label || r.id,
            Math.round(dispV(r.value * 1e6)),
            Math.round((r.q_mass || 0) * 1e3),
            Math.round((r.q_vol || 0) * 1e6),
            Math.round((r.q_count || 0) * 1e6),
            escopo, recorte, ...(origem ? [origem] : []), ...(nivel ? [nivel] : []),
          ]);
          return { headers, rows, subject: 'distribuicao_por_regiao' };
        }
        if (geoScope === 'municipio') {
          const munis = Array.isArray(window.geoExportMunis) ? window.geoExportMunis : [];
          const headers = ['ano', 'municipio', 'uf', `valor_${conv.currency}`, 'qtd_massa_t', 'qtd_volume_m3', 'qtd_contagem_un', 'escopo_produto', 'recorte_geografico'].concat(origem ? ['tabela_sidra'] : []).concat(nivel ? ['nivel_industrializacao'] : []);
          const rows = munis.map(m => [
            ano, m.city, m.uf,
            Math.round(dispV((m.value || 0) * 1e6)),
            Math.round((m.q_mass || 0) * 1e3),
            Math.round((m.q_vol || 0) * 1e6),
            Math.round((m.q_count || 0) * 1e6),
            escopo, recorte, ...(origem ? [origem] : []), ...(nivel ? [nivel] : []),
          ]);
          return { headers, rows, subject: 'distribuicao_por_municipio' };
        }
        const headers = ['ano', 'uf', 'nome', 'regiao', `valor_${conv.currency}`, 'qtd_massa_t', 'qtd_volume_m3', 'qtd_contagem_un', 'escopo_produto', 'recorte_geografico'].concat(origem ? ['tabela_sidra'] : []).concat(nivel ? ['nivel_industrializacao'] : []);
        const rows = f.ufData.map(u => [
          ano, u.uf, u.name, u.region,
          Math.round(dispV(u.value * 1e6)),
          Math.round(u.q_mass * 1e3),
          Math.round(u.q_vol * 1e6),
          Math.round((u.q_count || 0) * 1e6),  // mi un → un (livestock head / eggs)
          escopo, recorte, ...(origem ? [origem] : []), ...(nivel ? [nivel] : []),
        ]);
        return { headers, rows, subject: 'distribuicao_geografica' };
      }
      case 'concentration': {
        const ano = f.ufYearPartial ? `${f.ufLatestYear} (parcial)` : (f.ufLatestYear ?? '');
        const escopo = f.notFilteredByBasket ? 'todos os produtos' : 'cesta selecionada';
        const headers = ['ano', 'uf', 'nome', 'regiao', `valor_${conv.currency}`, 'qtd_contagem_un', 'escopo_produto', 'recorte_geografico'].concat(origem ? ['tabela_sidra'] : []).concat(nivel ? ['nivel_industrializacao'] : []);
        const rows = f.ufData.slice().sort((a, b) => b.value - a.value)
          .map(u => [ano, u.uf, u.name, u.region, Math.round(dispV(u.value * 1e6)), Math.round((u.q_count || 0) * 1e6), escopo, recorte, ...(origem ? [origem] : []), ...(nivel ? [nivel] : [])]);
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

  // O que cada `subject` significa em português, para a janela de confirmação poder dizer
  // ao pesquisador O QUE ele vai baixar. Fica ao lado dos `return { subject }` acima, de
  // modo que um assunto novo sem verbete apareça como o próprio identificador — feio, mas
  // honesto — em vez de sumir.
  const ASSUNTO = {
    serie_agregada: 'Série anual agregada (valor e quantidade por ano)',
    series_por_produto: 'Série anual por produto',
    distribuicao_geografica: 'Distribuição por UF',
    distribuicao_por_regiao: 'Distribuição por região',
    distribuicao_por_municipio: 'Distribuição por município',
    concentracao: 'Concentração por UF, da maior para a menor',
    qualidade: 'Contagem de linhas por marca de qualidade',
  };

  /**
   * O período que vai no NOME do arquivo, lido dos próprios dados.
   *
   * Antes vinha de `summary.startDate`, que é vazio enquanto ninguém mexe no filtro de
   * período — então o arquivo saía "…_completo.csv" ao lado de um chip dizendo "1986–2024".
   * Coerente ("completo" = sem recorte de período), mas a janela de confirmação passou a
   * mostrar as duas coisas juntas, e juntas elas leem como contradição.
   *
   * A coluna `ano` do arquivo é a fonte certa porque é a única que NÃO pode discordar do
   * conteúdo: qualquer outra (o filtro, o chip) descreve a intenção, não o que saiu. Em
   * `geo` o ano vem como "2024 (parcial)", daí extrair os 4 dígitos em vez de converter a
   * célula inteira. Um assunto sem coluna `ano` (qualidade) cai nos fallbacks abaixo.
   */
  function periodoDosDados(headers, rows) {
    const i = headers.indexOf('ano');
    if (i < 0) return null;
    let min = Infinity, max = -Infinity;
    for (const r of rows) {                       // laço, não Math.min(...anos): a versão
      const m = /\d{4}/.exec(String(r[i] ?? ''));  // espalhada estoura a pilha em arquivos
      if (!m) continue;                            // grandes (município pode passar de 10k)
      const y = Number(m[0]);
      if (y < min) min = y;
      if (y > max) max = y;
    }
    if (!isFinite(min)) return null;
    return min === max ? String(min) : `${min}-${max}`;
  }

  /**
   * MONTA o arquivo e devolve um descritor — sem baixar nada.
   *
   * O `baixar()` que volta aqui escreve o CSV JÁ MONTADO, byte a byte. É de propósito: a
   * janela de confirmação mostra estes mesmos números, e reconstruir na hora do "Baixar"
   * abriria a porta para a tela dizer uma coisa e o arquivo trazer outra — o oposto do que
   * a confirmação existe para garantir.
   *
   * Devolve `null` quando não há o que baixar, com `motivo` dizendo por quê: um banco ainda
   * não liberado não tem linhas, e uma view pode render zero linhas sob o recorte atual.
   */
  window.prepareTableCSV = function (ctx) {
    const banco = window.bancoById ? window.bancoById(ctx.database) : null;
    // Only live bancos hold real rows; soon bancos have nothing to export.
    if (!banco || banco.status !== 'live') {
      console.warn('[csv] banco not available for export:', ctx.database);
      return { erro: true, motivo: 'banco-indisponivel', banco: banco ? banco.short : ctx.database };
    }
    const built = buildRows(ctx);
    if (!built || !built.rows.length) {
      console.warn('[csv] nothing to export for view', ctx.view);
      return { erro: true, motivo: 'sem-linhas', banco: banco.short };
    }
    // Ordem de preferência: o que o arquivo REALMENTE contém; depois as datas do filtro;
    // depois o chip de período já formatado na tela (normalizando o travessão, que não é
    // um caractere para nome de arquivo); e só então "completo".
    const doChip = (ctx.summary && ctx.summary.period || '')
      .replace(/[–—]/g, '-').replace(/\s+/g, '');
    const period = periodoDosDados(built.headers, built.rows)
      || ((ctx.summary && ctx.summary.startDate)
            ? `${ctx.summary.startDate.slice(0,4)}-${(ctx.summary.endDate||'').slice(0,4)}`
            : null)
      || (/^\d{4}(-\d{4})?$/.test(doChip) ? doChip : null)
      || 'completo';
    const fname = `${banco.short.replace(/\s+/g,'_').toLowerCase()}_${built.subject}_${period}.csv`;
    const csv = toCSV(built.headers, built.rows);
    return {
      erro: false,
      arquivo: fname,
      banco: banco.short,
      assunto: ASSUNTO[built.subject] || built.subject,
      colunas: built.headers,
      linhas: built.rows.length,
      // Tamanho do arquivo REAL (a string já montada), não uma estimativa por linha.
      bytes: new Blob([csv]).size,
      baixar: () => download(fname, csv),
    };
  };

  // Entrada direta — monta E baixa, sem confirmação. Mantida para quem chama o export por
  // fora da janela (e é o caminho que os testes do exportador exercitam).
  window.exportActiveTableCSV = function (ctx) {
    const p = window.prepareTableCSV(ctx);
    if (!p || p.erro) return;
    p.baixar();
  };
})();
