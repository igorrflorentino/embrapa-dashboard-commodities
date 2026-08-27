// views.js — registry of analytical perspectives, grouped into formal
// categories. Single source of truth for the topnav and the router.
//
// status: 'live' → component exists and renders real data.
//         'soon' → planned; router shows a perspective placeholder.
//
// Adding a perspective = add an entry here (+ its component when live).

window.VIEW_GROUPS = [
  {
    id: 'aggregate',
    label: 'Análise agregada',
    hint: 'cesta de produtos',
    views: [
      { id: 'overview', label: 'Visão geral',   status: 'live', exportable: true, requires: [],
        desc: 'Resumo consolidado: KPIs, série de valor, composição e distribuição geográfica resumida.' },
      { id: 'value',    label: 'Valor e volume', status: 'live', exportable: true, requires: [],
        desc: 'Séries históricas de valor e quantidade da cesta, segregadas por família de unidades.' },
      { id: 'rebanho',  label: 'Rebanho', status: 'live', exportable: false, requires: ['herd'],
        desc: 'O efetivo dos rebanhos (estoque em cabeças, por espécie): composição do efetivo, evolução de 50 anos por espécie e distribuição por UF da espécie em foco. Exclusivo da Pesquisa da Pecuária Municipal (IBGE PPM) — cabeças não têm valor monetário e não se somam entre espécies.',
        planned: ['Composição do efetivo por espécie', 'Evolução de 50 anos por espécie', 'Mapa de cabeças por UF', 'Pico histórico e UF líder'] },
    ],
  },
  {
    id: 'product',
    label: 'Análise por produto',
    hint: 'produto individual',
    views: [
      { id: 'product_profile', label: 'Perfil do produto', status: 'live', exportable: true, requires: ['product'],
        desc: 'Mergulho em um único produto: série de valor e quantidade, preço médio implícito (valor ÷ quantidade), evolução da participação na cesta e ranking histórico de UFs produtoras.',
        planned: ['Preço médio implícito por ano', 'Participação do produto na cesta', 'Ranking de UFs produtoras ao longo do tempo', 'Ficha técnica (código, unidade, espécie, cobertura)'] },
      { id: 'product_compare', label: 'Comparativo entre produtos', status: 'live', exportable: true, requires: ['product'],
        desc: 'Selecione 2 a 4 produtos e compare lado a lado: séries normalizadas (base 100), variação acumulada, CAGR e correlação cruzada.',
        planned: ['Séries normalizadas base 100', 'CAGR por produto', 'Correlação cruzada entre produtos', 'Tabela comparativa de métricas'] },
      // exportable:false — csvExport.buildRows has no 'productivity' case (this view is
      // selfData:true and recomputes yield=qty/area outside the standard export ctx), so a
      // true flag renders a button that hits the default→null path and silently fails. Flip
      // to true only alongside a 'productivity' buildRows case that carries the recomputed
      // rendimento (kg/ha) + área colhida series.
      { id: 'productivity', label: 'Produtividade', status: 'live', exportable: false, requires: ['yield'], selfData: true,
        desc: 'Rendimento (kg/ha) e área colhida por lavoura: trajetória nacional de produtividade e a geografia do rendimento por UF. Disponível para bancos de produção agrícola (IBGE PAM).',
        planned: ['Série de rendimento médio (kg/ha)', 'Série de área colhida', 'Mapa de produtividade por UF', 'Ranking de UFs mais produtivas'] },
    ],
  },
  {
    id: 'flows',
    label: 'Análise de fluxos',
    hint: 'origem → destino',
    views: [
      { id: 'flows_territorial', label: 'Fluxos territoriais', status: 'live', requires: ['flow'], selfData: true,
        desc: 'Reconstituição da cadeia: extração (PEVS) → comércio interno (SEFAZ) → exportação (MDIC) → comércio internacional (UN Comtrade). Diagrama Sankey origem → destino.',
        planned: ['Diagrama Sankey origem → destino', 'Cadeia extração → interno → externo', 'Saldo líquido por UF', 'Filtro por elo da cadeia'] },
      { id: 'flows_partners', label: 'Parceiros comerciais', status: 'live', requires: ['partner'], selfData: true,
        desc: 'Rankings de UFs e países de origem/destino, fluxos bilaterais e participação de cada parceiro no total comercializado.',
        planned: ['Top parceiros (país / UF)', 'Fluxos bilaterais', 'Evolução de participação por parceiro', 'Mapa de fluxos internacionais'] },
    ],
  },
  {
    id: 'distribution',
    label: 'Análise de distribuição',
    hint: 'espacial',
    views: [
      { id: 'geo',           label: 'Geografia', status: 'live', exportable: true, requires: ['geo'],
        desc: 'Distribuição territorial por valor, massa e volume, em região, UF ou município. Mapas, mapas de calor e rankings.' },
      // The TRANSPOSE of 'product_profile': that one drills into a single produto
      // across places; this one drills into a single PLACE across produtos. Kept a
      // perspective of its own rather than folded into Geografia, because Geografia
      // answers "how is it spread ACROSS places" and this answers "what happens in
      // THIS one" — same data, opposite question.
      { id: 'territory_profile', label: 'Perfil do território', status: 'live', exportable: false, requires: ['geo'],
        desc: 'Raio-x de um território: o que uma UF ou um município produz, a trajetória do lugar, sua composição por produto, seu peso no país e a qualidade do dado ali.',
        planned: ['Composição por produto do território', 'Trajetória histórica do lugar', 'Peso e posição no ranking nacional', 'Principais municípios (quando o banco tem grão municipal)'] },
      { id: 'concentration', label: 'Concentração e desigualdade', status: 'live', exportable: true, requires: [],
        desc: 'Quão concentrada é a atividade: curva de Lorenz, índice de Gini e HHI (Herfindahl-Hirschman) por geografia e por produto.',
        planned: ['Curva de Lorenz', 'Índice de Gini ao longo do tempo', 'HHI por UF e por produto', 'Participação dos top-5 produtores'] },
    ],
  },
  {
    id: 'temporal',
    label: 'Análise temporal',
    hint: 'ciclos',
    views: [
      { id: 'seasonality', label: 'Sazonalidade e tendências', status: 'live', requires: ['monthly'], selfData: true,
        desc: 'Padrões temporais além da tendência: mapa de calor mês × ano, decomposição tendência/sazonalidade/ruído e detecção de quebras estruturais. Mais informativa com dados mensais (MDIC, SEFAZ).',
        planned: ['Mapa de calor mês × ano', 'Decomposição tendência + sazonal + ruído', 'Detecção de quebras estruturais', 'Box-plot por mês'] },
    ],
  },
  {
    id: 'crosssource',
    label: 'Análise cruzada',
    hint: 'entre bancos',
    views: [
      { id: 'cross_source', label: 'Cruzamento entre fontes', status: 'live', requires: [], crossBanco: true, align: 'eixo temporal (ano)',
        desc: 'Compare séries anuais de bancos DIFERENTES no mesmo eixo de tempo — ex.: produção (IBGE) × exportação (MDIC). Escolha de 2 a 4 séries, alinhe pela janela comum e alterne entre base 100, eixo duplo e painéis.',
        planned: ['Sobreposição base 100 / eixo duplo / painéis', 'Varição acumulada e CAGR por série', 'Correlação interanual entre fontes', 'Razão entre séries (ex.: coeficiente de exportação)'] },

      { id: 'cross_export_coef', label: 'Coeficiente de exportação', status: 'live', requires: [], crossBanco: true, align: 'UF × ano',
        sources: ['ibge_pevs', 'mdic_comex'],
        desc: 'Quanto do que cada UF produz (IBGE) segue para exportação (MDIC). Mapa de orientação exportadora por estado e evolução do coeficiente nacional.' },

      { id: 'cross_market_share', label: 'Brasil no mercado mundial', status: 'live', requires: [], crossBanco: true, align: 'eixo temporal (ano)',
        sources: ['mdic_comex', 'un_comtrade'],
        desc: 'Exportação brasileira como fração da exportação mundial do agrupamento (UN Comtrade). Trajetória de participação e quebra por agrupamento.' },

      { id: 'cross_price_spread', label: 'Preço: porteira vs. FOB', status: 'live', requires: [], crossBanco: true, align: 'eixo temporal (ano)',
        sources: ['ibge_pevs', 'mdic_comex'],
        desc: 'Preço implícito na produção (IBGE) contra o preço de exportação FOB (MDIC). O spread entre porteira e porto mede a agregação de valor.' },

      { id: 'cross_mirror', label: 'Espelho comercial', status: 'live', requires: [], crossBanco: true, align: 'eixo temporal (ano)',
        sources: ['mdic_comex', 'un_comtrade'],
        desc: 'A mesma exportação vista por fontes distintas — MDIC, Comtrade e parceiros. A divergência ao longo do tempo é um diagnóstico de qualidade entre bases.' },

      { id: 'cross_chain', label: 'Balanço da cadeia', status: 'live', requires: [], crossBanco: true, dataBlocked: true, align: 'balanço físico (massa)',
        sources: ['ibge_pevs', 'sefaz_nf', 'mdic_comex', 'un_comtrade'],
        desc: 'O caminho do que se produz: produção (IBGE) → comércio interno (SEFAZ) → exportação (MDIC) → fatia do mercado mundial (Comtrade). Balanço de oferta reconciliado em massa.' },

      { id: 'cross_lag', label: 'Defasagem safra → embarque', status: 'live', requires: [], crossBanco: true, dataBlocked: true, align: 'mês (intra-anual)',
        sources: ['ibge_pevs', 'mdic_comex'],
        desc: 'Quantos meses os embarques (MDIC, mensal) seguem o pico da safra (IBGE). Perfis mensais sobrepostos e correlação cruzada por defasagem.' },
    ],
  },
  // ─── Análises curadas (Engenharia de Atributos) ──────────────────────────────
  // Two derived-attribute perspectives, BOTH researcher-EDITABLE (gated by the
  // `enable_curation` dbt var): "Valor agregado" ← the per-code industrialization editor;
  // "Finalidade econômica" ← the (customs × flow) "Tipo de Mercado" matrix editor.
  {
    id: 'curated',
    label: 'Análises curadas',
    hint: 'enriquecidas',
    views: [
      { id: 'curated_value_added', label: 'Valor agregado', status: 'live', requires: [], crossBanco: true, curated: true, align: 'nível de industrialização',
        sources: ['mdic_comex', 'un_comtrade'],
        desc: 'Exportação distribuída pelos 8 níveis de industrialização (do bruto ao manufaturado), a partir da classificação curada dos códigos. Valor, volume e preço por nível, com prêmio de processamento.' },
      // FROZEN (2026-07): "Finalidade econômica" (consumo × processamento) — depends on the
      // "Tipo de Mercado" market-nature classification, which needs the customs-procedure
      // detail the totals-only COMTRADE base (customsCode=C00) no longer carries. Removed
      // from the curated-analyses menu; the ViewMarketNature component + data fn stay as
      // scaffold. See the frozen-feature memo. Revive with the matrix editor.
      // { id: 'curated_market_nature', label: 'Finalidade econômica', status: 'live', requires: [], crossBanco: true, curated: true, align: 'finalidade (consumo/processamento)',
      //   sources: ['mdic_comex', 'un_comtrade'],
      //   desc: 'Valor comercializado por finalidade econômica (consumo × processamento)…' },
    ],
  },
  {
    id: 'documentation',
    label: 'Documentação do banco',
    hint: 'metadados',
    views: [
      { id: 'quality',  label: 'Qualidade dos dados', status: 'live', exportable: true, requires: ['quality'],
        desc: 'Diagnóstico da dimensão data_quality_flag: distribuição de flags, integridade temporal e qualidade por produto e UF.' },
      { id: 'dados',    label: 'Estrutura de dados', status: 'live', requires: [],
        desc: 'A estrutura por trás do banco: percorra as tabelas de cada camada do pipeline — Bronze (bruto), Silver (padronizado), Gold (analítico) e Serving (pronto para o painel) — e investigue qualquer uma linha a linha, com paginação, ordenação e filtros por coluna. Para conferir os dados ou rastrear de onde vem cada número.',
        planned: ['Tabelas das 4 camadas (Bronze → Serving)', 'Linhagem: da fonte oficial ao gráfico', 'Paginação no servidor', 'Ordenar por qualquer coluna', 'Filtrar por coluna (=, >, contém…)', 'Exportar o recorte em CSV'] },
      { id: 'glossary', label: 'Glossário', status: 'live', requires: [],
        desc: 'Termos, códigos e colunas do banco selecionado.' },
    ],
  },
];

// Flattened lookup helpers ------------------------------------------------
window.VIEW_BY_ID = (() => {
  const map = {};
  window.VIEW_GROUPS.forEach(g => g.views.forEach(v => { map[v.id] = { ...v, group: g }; }));
  return map;
})();

window.viewById = (id) => window.VIEW_BY_ID[id] || null;
window.viewLabel = (id) => window.VIEW_BY_ID[id]?.label || id;
window.isViewLive = (id) => window.VIEW_BY_ID[id]?.status === 'live';

// View → component registry. The component globals (window.ViewXxx) are
// defined by each perspective's JSX file and resolved LAZILY via window[name]
// at render time (views.js loads before those files). This is the single
// source of truth for routing a view id to its React component — adding a
// perspective = one entry here + its component file. Replaces the per-view
// ternary chains that used to live (scattered) inside MainScreen.
window.VIEW_COMPONENTS = {
  overview:              'ViewOverview',
  value:                 'ViewValueVolume',
  rebanho:               'ViewRebanho',
  product_profile:       'ViewProductProfile',
  product_compare:       'ViewProductCompare',
  productivity:          'ViewProductivity',
  flows_territorial:     'ViewFlows',
  flows_partners:        'ViewPartners',
  geo:                   'ViewGeography',
  territory_profile:     'ViewTerritoryProfile',
  concentration:         'ViewConcentration',
  seasonality:           'ViewSeasonality',
  quality:               'ViewQuality',
  dados:                 'ViewDados',
  glossary:              'Glossary',
  cross_source:          'ViewCrossSource',
  cross_export_coef:     'ViewExportCoef',
  cross_market_share:    'ViewMarketShare',
  cross_price_spread:    'ViewPriceSpread',
  cross_mirror:          'ViewMirror',
  cross_chain:           'ViewChainBalance',
  cross_lag:             'ViewHarvestLag',
  // Análises curadas (Engenharia de Atributos): só "Valor agregado" está live. "Finalidade
  // econômica" (curated_market_nature) está CONGELADA/removida do menu — deliberadamente NÃO
  // mapeada aqui para que um deep link obsoleto (?v=curated_market_nature) não roteie para o
  // ViewMarketNature congelado (main.jsx também valida o ?v contra o menu e cai em overview).
  curated_value_added:   'ViewValueAdded',
};

// Resolve a view's React component (or null). Dev guard: a LIVE view with no
// mapping / missing global warns loudly instead of silently rendering the
// wrong screen — the failure mode of the old `: window.ViewOverview` default.
window.viewComponent = (id) => {
  const name = window.VIEW_COMPONENTS[id];
  const comp = name ? window[name] : null;
  if (!comp && window.isViewLive && window.isViewLive(id)) {
    console.warn(`[views] no component for live perspective "${id}" (mapped to ${name || 'nothing'})`);
  }
  return comp;
};

// The source banco whose maturity gates a cross-perspective into PREVIEW mode —
// i.e. the LEAST-MATURE source among the view's `sources` (ties broken toward the
// downstream source = later array position). Single-sourced from the view
// registry so a PreviewBanner never re-literals a banco id; if a view's `sources`
// change, the banner follows automatically. Returns null for non-cross views.
window.crossPreviewBanco = (viewId) => {
  const v = window.viewById ? window.viewById(viewId) : null;
  const srcs = (v && v.sources) || [];
  if (!srcs.length) return null;
  let bestId = null, bestOrder = Infinity;
  srcs.forEach(id => {
    const b = window.bancoById ? window.bancoById(id) : null;
    const order = (b && window.MATURITY[b.maturity] && window.MATURITY[b.maturity].order) || 0;
    if (order <= bestOrder) { bestOrder = order; bestId = id; } // <= → ties prefer later index
  });
  return window.bancoById ? window.bancoById(bestId) : null;
};

// ── Capability system ───────────────────────────────────────────────────
// A view declares which data capabilities it `requires`; each banco
// declares which it `provides` (in bancos.js). Crossing the two tells us
// whether a perspective is even meaningful for the active banco — distinct
// from whether the component has been built yet (status live/soon).
window.CAPABILITIES = {
  product: { label: 'dimensão de produto' },
  geo:     { label: 'dimensão geográfica (UF/município)' },
  flow:    { label: 'fluxo origem → destino' },
  partner: { label: 'dimensão de parceiro comercial' },
  monthly: { label: 'granularidade temporal mensal/diária' },
  quality: { label: 'dimensão de qualidade' },
  // Agricultural-production capabilities (IBGE PAM and any future crop banco).
  area:    { label: 'área plantada / colhida' },
  yield:   { label: 'rendimento (produtividade kg/ha)' },
  // Livestock: the banco carries an animal STOCK (efetivo, head counted at year-end),
  // gating the dedicated 'Rebanho' perspective. Only IBGE PPM provides it today.
  herd:    { label: 'efetivo de rebanho (estoque em cabeças)' },
  // Monetary: the banco carries a value in currency, so the currency +
  // monetary-correction conventions apply. DERIVED, not stored per banco —
  // see window.isMonetaryBanco (bancos.js); listed here so the filter-schema
  // lint and missingCapsLabel resolve the token.
  monetary: { label: 'valor monetário (moeda / correção)' },
};

// { applies: bool, missing: ['flow', ...] } — does view work for banco?
window.viewAppliesTo = (viewId, bancoId) => {
  const v = window.VIEW_BY_ID[viewId];
  const b = window.bancoById ? window.bancoById(bancoId) : null;
  if (!v || !b) return { applies: true, missing: [] };
  // Cross-source perspectives operate ACROSS bancos, not against the active
  // one — they always apply regardless of which banco is selected.
  if (v.crossBanco) return { applies: true, missing: [] };
  const provides = b.provides || [];
  const requires = v.requires || [];
  const missing = requires.filter(r => !provides.includes(r));
  return { applies: missing.length === 0, missing };
};

// Which bancos DO support a given view (inverse indicator).
window.bancosSupporting = (viewId) => {
  const v = window.VIEW_BY_ID[viewId];
  if (!v) return [];
  const requires = v.requires || [];
  return (window.visibleBancos ? window.visibleBancos() : (window.BANCOS || [])).filter(b =>
    requires.every(r => (b.provides || []).includes(r))
  );
};

// Human phrase for a list of missing capabilities.
window.missingCapsLabel = (missing) =>
  (missing || []).map(c => window.CAPABILITIES[c]?.label || c).join(' · ');

// ── Cross-perspective usability (the multi-fonte analog of viewAppliesTo) ──
// viewAppliesTo SHORT-CIRCUITS crossBanco views (they don't map to the single
// active banco's requires/provides), so cross perspectives need their OWN gate to
// honour "only show what the user can use". Three orthogonal axes, all from data
// that already exists:
//   1. DATA-BLOCKED — `dataBlocked:true` (authored: the source data doesn't exist
//      at the needed shape — SEFAZ inter-UF flows; monthly PEVS — so the view can
//      only show demo/preview data). A repo fact, not client-detectable.
//   2. SOURCE-AVAILABILITY — every declared `sources` banco must be visible AND
//      have data. Unknown maturity (not yet overlaid from /api/source-meta) counts
//      as LOADING → treated as available so we never flicker-hide a usable view.
//   3. COMPARABILITY — the free-form comparator (cross_source, no `sources`) needs
//      ≥2 comparable (banco, metric) refs; allMetricRefs already excludes the
//      metric-less bancos (PAM/SEFAZ).
// Returns { usable, state:'ok'|'preview'|'na', reason }. curated:true views are a
// SEPARATE 'needs activation' concern (they self-guard with an honest empty state
// and can be live in prod), so they are NOT gated here.
window.crossViewApplies = (viewId) => {
  const v = window.viewById ? window.viewById(viewId) : null;
  if (!v || !v.crossBanco) return { usable: true, state: 'ok', reason: '' };
  if (v.dataBlocked) {
    return { usable: false, state: 'preview',
      reason: 'Demonstração — a fonte necessária ainda não existe no pipeline (valores ilustrativos).' };
  }
  const sources = v.sources || [];
  const missing = sources.filter((id) => {
    const b = window.bancoById ? window.bancoById(id) : null;
    if (!b) return true;
    if (window.isBancoVisible && !window.isBancoVisible(b)) return true;
    const m = window.maturityMeta ? window.maturityMeta(b) : null;
    // null/loading maturity → neutral (don't hide on first paint); else need data.
    return !!(m && m.id !== 'loading' && !m.hasData);
  });
  if (missing.length) {
    const names = missing.map((id) => (window.bancoById(id) || {}).short || id).join(' · ');
    return { usable: false, state: 'na', reason: 'Fonte indisponível: ' + names + '.' };
  }
  if (!sources.length && window.allMetricRefs && window.allMetricRefs().length < 2) {
    return { usable: false, state: 'na', reason: 'Requer ao menos 2 séries comparáveis.' };
  }
  return { usable: true, state: 'ok', reason: '' };
};
