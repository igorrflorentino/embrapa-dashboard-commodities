// bancos.js — central registry for every data source the dashboard
// can consume. Adding a new banco = adding an entry here (no other
// hard-coded banco logic exists in the codebase).
//
// TWO STATUS AXES (kept separate on purpose — never let them blur):
//
//   • maturity — DATASET LIFECYCLE / maturity (how built-out the banco is).
//     A build-time property reported by the backend; the frontend only
//     displays it. One of window.MATURITY, in lifecycle order:
//       planejado · desenvolvimento · ingestao · beta · estavel ·
//       manutencao · descontinuado
//     `hasData: true` stages (desenvolvimento/beta/estavel/manutencao/
//     descontinuado) render the real perspectives (with a caveat banner where
//     caveat:true); the no-data stages (planejado/ingestao) render the
//     placeholder.
//     NOTE: "source down right now" is NOT a maturity stage — that is a
//     RUNTIME HEALTH state (shown in the UI as "Saudável" · "Verificando…" ·
//     "Falha"), derived live in ViewHealth from the REAL Gold-query outcome (a
//     live banco whose pushdown query to Gold succeeds / is in flight / errors)
//     — NOT from pipeline-run telemetry, which the page honestly reports as
//     "não monitorada". The two axes are orthogonal: an estavel banco can be in
//     a failed health state; a beta banco can be healthy.
//
//   • usage (active/inactive) — DERIVED at render time: a banco is "active"
//     when it is the source feeding what the user currently sees (the
//     selected banco in single mode; an included source in multi-fonte).
//     Never stored.
//
//   • visible (true/false) — VISIBILITY, decided by the backend. When
//     `visible: false` the frontend hides the banco's existence EVERYWHERE
//     (sidebar, About page, Health page, cross-source picker, capability
//     lists, URL restore). Default is visible. Use it to declutter the UI on
//     demand — independent of maturity (an estavel banco can be hidden; a
//     hidden banco keeps its maturity, it just isn't shown). Enumerate the shown
//     set with window.visibleBancos(); bancoById() still resolves any id.
//
// The legacy `status: 'live'|'soon'` is now DERIVED from maturity.hasData
// (defined via Object.defineProperty after the array) so existing routing,
// CSV gating and cross-source preview logic keep working unchanged.
//
// Provenance (`prov`) applies to bancos with data; `plannedScope`/`cobertura`
// describe what a not-yet-built banco will expose.

// ── Maturity registry (single source of truth) ─────────────────────────
// Ordered along the dataset lifecycle (Planejado → … → Descontinuado).
// `hasData` decides whether perspectives render real data (+ a caveat banner
// for beta/manutencao/descontinuado) or the placeholder. Industry-standard
// release-maturity vocabulary; kept strictly distinct from runtime health.
window.MATURITY = {
  planejado:       { id: 'planejado',       label: 'Planejado',          color: 'var(--pres-gray-400)', hasData: false, future: true, order: 1,
                     desc: 'No roadmap, mas sem implementação iniciada nem prazo definido.' },
  desenvolvimento: { id: 'desenvolvimento', label: 'Em desenvolvimento',  color: 'var(--status-mat-dev)', hasData: true,  order: 2,
                     desc: 'Em produção e já consultável, mas ainda em construção, cálculos podem mudar.' },
  ingestao:        { id: 'ingestao',        label: 'Ingestão',           color: 'var(--status-mat-ingest)', hasData: false, order: 3,
                     desc: 'Pipeline construído, mas os dados ainda estão sendo baixados das fontes oficiais — a cobertura pode mudar.' },
  beta:            { id: 'beta',            label: 'Beta',               color: 'var(--info)',          hasData: true,  caveat: true, order: 4,
                     desc: 'Disponível para testes e validações, resultados podem mudar.' },
  estavel:         { id: 'estavel',         label: 'Estável',            color: 'var(--ok)',            hasData: true,  order: 5,
                     desc: 'Banco em produção, 100% pronto para consumo e análise.' },
  manutencao:      { id: 'manutencao',      label: 'Em manutenção',      color: 'var(--warn)',          hasData: true,  caveat: true, order: 6,
                     desc: 'Em produção, porém em correção de cálculo/tabela ou atualização programada.' },
  descontinuado:   { id: 'descontinuado',   label: 'Descontinuado',      color: 'var(--status-mat-sunset)', hasData: true,  caveat: true, sunset: true, order: 7,
                     desc: 'Banco obsoleto, não recebe mais manutenção e será removido em breve — exporte o que precisar antes da remoção.' },
};
// Per-banco maturity is NOT defined in this file. Its single source of truth is
// BigQuery (research_inputs.banco_metadata), served via /api/source-meta and
// overlaid onto the banco object by dataStore.overlayBancoMetadata. Until that
// resolves a banco has no `maturity`, so maturityMeta returns a neutral LOADING
// stage (a "…" tag) rather than guessing — never a hardcoded per-banco default.
window.MATURITY_LOADING = {
  id: 'loading', label: '…', color: 'var(--pres-gray-300)', hasData: false, order: 0,
  desc: 'Carregando a maturidade do banco…',
};
window.maturityMeta = (b) =>
  (b && b.maturity)
    ? (window.MATURITY[b.maturity] || window.MATURITY.planejado)
    : window.MATURITY_LOADING;

// Short availability label for banco pickers/tags, derived from maturity.
// 'Disponível' once the banco has data (this includes `desenvolvimento`, which
// is in production and consultable); `ingestao` (pipeline built, data still
// being downloaded — committed but no usable data yet) reads "Em breve"; a
// no-data stage without an ETA (planejado) reads "Sem previsão".
window.bancoAvailability = (b) => {
  if (window.maturityMeta(b).hasData) return 'Disponível';
  return (b && b.maturity === 'ingestao') ? 'Em breve' : 'Sem previsão';
};

window.BANCOS = [
  // ─── Live ────────────────────────────────────────────────────────────
  {
    id:     'ibge_pevs',
    short:  'IBGE PEVS',
    label:  'IBGE · Produção da Extração Vegetal e da Silvicultura',
    sub:    'Produção e exploração de produtos agrícolas no território brasileiro',
    // Onboarding description (ViewAbout): plain-language, non-technical — what the banco
    // IS and what it's FOR, for a researcher meeting it for the first time.
    about:  'Reúne, ano a ano, a quantidade e o valor da produção florestal brasileira nas DUAS metades da pesquisa do IBGE: a extração vegetal, de floresta nativa (castanha-do-pará, açaí, madeira em tora, lenha, carvão), e a silvicultura, de floresta plantada — de onde vem a maior parte da madeira do país. O filtro Origem da produção separa as duas; sem ele, os números somam ambas, que é o total da pesquisa. É por isso que estados de floresta plantada, como São Paulo, aparecem aqui: eles quase não têm extrativismo.',
    domain: 'Produção interna',
    scope:  'Brasil · UF · município',
    source: 'IBGE',
    table:  'gold_pevs_production',
    // Data capabilities this banco exposes (see CAPABILITIES in views.js).
    // IBGE PEVS = production only: products, geography, quality — annual,
    // no origin→destination flow, no commercial partner.
    provides: ['product', 'geo', 'quality'],
    // Canonical currency for this banco. Values are stored BRL-canonical
    // (PEVS is natively R$); changeDatabase resets the DISPLAY currency to this
    // so the right symbol shows by default. Finest geo granularity the banco
    // exposes ('municipio' | 'uf' | null) — drives the FilterMenu's geography
    // cascade depth so it never offers a level the banco lacks.
    baseCurrency: 'BRL',
    geoLevel: 'municipio',
    // Business-semantic descriptors for this banco's dimensions — display
    // labels + universe kind ('uf' = Brazilian states, 'country' = nations) +
    // product code scheme, DECLARED here so adapters/views never branch on
    // bancoId. PEVS is production-only (no flow/partner); the geo labels are
    // harmless defaults.
    dimensions: {
      origin:  { label: 'UF de origem',  kind: 'uf' },
      dest:    { label: 'UF de destino', kind: 'uf' },
      partner: { label: 'UF parceira',   kind: 'uf' },
      product: { codeLabel: 'Código PEVS' },
    },
    // Comparable ANNUAL series this banco can contribute to the cross-source
    // perspective (consumed by window.crossSeries in src/data/producers.js). Each
    // metric is a single time series
    // keyed by year. `family` groups metrics that share a physical/value
    // dimension (currency / mass / volume / ratio) so the cross view knows
    // which series can share an axis or form a ratio. `years` is the native
    // coverage; the cross view intersects coverages across selected series.
    // `unit` is the BASE physical unit (t / m³ / R$). Charts display these quantities
    // PRE-SCALED — "mil t" (×1e3) and "mi m³" (×1e6) — with the scale multipliers living
    // in MetricConventions/serializers, not here. So a chart axis can read "mil t" while
    // this registry says "t": by design, not a mismatch (see glossário "mil t" / "mi m³").
    metrics: [
      { id: 'prod_value',  label: 'Valor da produção', family: 'currency', unit: 'R$',  agg: 'Valor real (IPCA) da extração vegetal', years: [1986, 2024] },
      { id: 'prod_mass',   label: 'Quantidade produzida (massa)',  family: 'mass',   unit: 't',  agg: 'Massa colhida das espécies de família massa', years: [1986, 2024] },
      { id: 'prod_volume', label: 'Quantidade produzida (volume)', family: 'volume', unit: 'm³', agg: 'Volume das espécies de família volume',     years: [1986, 2024] },
    ],
    // Provenance: only the edition LABEL prefix lives here ("PEVS <ano>"); its YEAR
    // is overlaid live from gold_source_metadata (dataStore.meta → real yearEnd), and
    // every count (rows, products, UFs, years) + the Gold refresh stamp come SOLELY
    // from /api/source-meta. No fabricated publication date — the page never had a
    // real one (gold_source_metadata exposes no publish date), so we don't invent it;
    // it shows the live edition + the real refresh stamp instead.
    prov: {
      lastCrop: 'PEVS 2024',
    },
    cobertura: {
      years:      '1986 → presente',
      atualizacao:'anual',
      granularidade: 'produto × município × ano',
    },
  },

  // ─── Connected (representative snapshots) ─────────────────────────────
  // COMEX = estavel, Comtrade = beta (partial coverage). Both have data
  // (hasData) and render real perspectives. SEFAZ stays 'planejado'.
  {
    id:     'ibge_pam',
    short:  'IBGE PAM',
    label:  'IBGE · Produção Agrícola Municipal',
    sub:    'Área, produção e rendimento das lavouras temporárias e permanentes',
    about:  'Detalha a produção agrícola municipal — área plantada e colhida, quantidade produzida, rendimento médio e valor — das principais lavouras temporárias e permanentes do país. Ideal para analisar o desempenho de culturas como soja, milho, café, cana-de-açúcar e mandioca.',
    domain: 'Produção agrícola',
    scope:  'Brasil · UF · município',
    source: 'IBGE',
    table:  'gold_pam_production',
    // Beta: live first cut — 5 principais lavouras (soja, milho, café, cana,
    // Estável: histórico completo (1974+), 8 lavouras (incl. banana, mandioca,
    // açaí) com quantidade, valor, área e rendimento (produtividade no painel).
    // LEAN surface: product + geography + quality + yield. The PEVS-shaped views
    // AND the PAM-only Produtividade (área × rendimento) view are wired end-to-end:
    // gold_pam_production carries area_planted/harvested_ha + production, surfaced
    // via /api/productivity (rendimento = produção ÷ área colhida, server-side).
    provides: ['product', 'geo', 'quality', 'yield'],
    baseCurrency: 'BRL',
    geoLevel: 'municipio',
    dimensions: {
      origin:  { label: 'UF produtora', kind: 'uf' },
      dest:    { label: 'UF produtora', kind: 'uf' },
      partner: { label: 'UF produtora', kind: 'uf' },
      product: { codeLabel: 'Código PAM' },
    },
    // Cross-source comparador: not yet wired for PAM (the BFF cross seam serves
    // PEVS/COMEX/COMTRADE only). Empty → PAM doesn't appear in the comparator
    // picker (would return null) until its cross series builders land. PAM's own
    // production/geo/quality views are fully live regardless.
    metrics: [],
    // Provenance shown ONLY as a pre-load fallback — the live app overrides the year
    // and every counter from gold_source_metadata (dataStore.meta('ibge_pam')). Kept
    // honest to the lean window so even the fallback never overstates coverage.
    prov: {
      lastCrop: 'PAM 2024',
    },
    plannedScope: [
      { col: 'produto (lavoura)',            desc: 'Cultura agrícola — temporária ou permanente.' },
      { col: 'uf · município',               desc: 'Localização da lavoura (até o nível municipal).' },
      { col: 'area_plantada · area_colhida', desc: 'Área destinada e efetivamente colhida (ha) — no Gold; painel em seguida.' },
      { col: 'quantidade_produzida',         desc: 'Produção colhida (t) — disponível.' },
      { col: 'rendimento_medio',             desc: 'Produtividade = produção ÷ área colhida (kg/ha) — no Gold; painel em seguida.' },
      { col: 'valor_producao',               desc: 'Valor da produção (R$) — disponível.' },
    ],
    cobertura: {
      years:      '1974 → presente',
      atualizacao:'anual (atualização mensal automática)',
      granularidade: 'lavoura × município × ano',
    },
  },
  {
    id:     'ibge_ppm',
    short:  'IBGE PPM',
    label:  'IBGE · Pesquisa da Pecuária Municipal',
    sub:    'Efetivo dos rebanhos e produção de origem animal (leite, ovos, mel, lã)',
    about:  'Reúne informações anuais sobre os efetivos da pecuária — o tamanho dos rebanhos, em cabeças — e a produção de origem animal (leite, ovos, mel e lã) nos municípios brasileiros. Permite avaliar tanto o estoque de animais quanto o que eles produzem.',
    domain: 'Produção pecuária',
    scope:  'Brasil · UF · município',
    source: 'IBGE',
    table:  'gold_ppm_production',
    // PPM is LIVESTOCK — efetivo dos rebanhos (estoque, cabeças) + produção de origem
    // animal (leite/ovos/mel/lã, com valor). Capability-wise PEVS-shaped: product +
    // geography + quality, WITHOUT 'yield' (não há área plantada → a view Produtividade
    // fica escura). Múltiplas famílias de unidade (contagem/volume/massa) já existem em
    // UNIT_FAMILIES, então MetricConventions renderiza as unidades automaticamente.
    // 'herd' (efetivo, estoque em cabeças) gates the dedicated 'Rebanho' perspective —
    // PPM is the only banco that carries an animal stock (measure_kind='stock').
    provides: ['product', 'geo', 'quality', 'herd'],
    baseCurrency: 'BRL',
    geoLevel: 'municipio',
    dimensions: {
      origin:  { label: 'UF produtora', kind: 'uf' },
      dest:    { label: 'UF produtora', kind: 'uf' },
      partner: { label: 'UF produtora', kind: 'uf' },
      product: { codeLabel: 'Código PPM' },
    },
    // Cross-source comparador: not yet wired for PPM (the BFF cross seam serves
    // PEVS/COMEX/COMTRADE only). Empty → PPM doesn't appear in the comparator picker
    // until its cross series builders land. Own product/geo/quality views are live.
    metrics: [],
    prov: {
      lastCrop: 'PPM 2024',
    },
    plannedScope: [
      { col: 'rebanho / produto animal', desc: 'Tipo de rebanho (bovino, suíno…) ou produto de origem animal (leite, ovos, mel, lã).' },
      { col: 'uf · município',           desc: 'Localização (até o nível municipal).' },
      { col: 'efetivo (cabeças)',        desc: 'Efetivo dos rebanhos — um estoque, sem valor monetário.' },
      { col: 'quantidade_produzida',     desc: 'Produção animal (mil litros, mil dúzias, kg) — por produto.' },
      { col: 'valor_producao',           desc: 'Valor da produção animal (R$) — disponível.' },
    ],
    cobertura: {
      years:      '1974 → presente',
      atualizacao:'anual (atualização mensal)',
      granularidade: 'rebanho/produto × município × ano',
    },
  },
  {
    id:     'mdic_comex',
    short:  'MDIC COMEX',
    label:  'MDIC · Comércio Exterior',
    sub:    'Exportação e importação brasileiras por estado de origem, produto e parceiro comercial',
    about:  'Consolida as estatísticas oficiais do comércio exterior brasileiro: exportações e importações por produto (NCM), estado de origem e país parceiro. Fundamental para análises de balança comercial e do fluxo de mercadorias entre o Brasil e o mundo.',
    domain: 'Comércio exterior',
    scope:  'UF de origem ↔ países parceiros',
    source: 'MDIC · SECEX',
    table:  'gold_comex_flows',
    // Exports by UF of origin → partner country, monthly, with product
    // (NCM) and quality. Has flow + partner + monthly.
    provides: ['product', 'geo', 'flow', 'partner', 'monthly', 'quality'],
    // Values in USD (FOB/CIF); geography at origin-state (UF) level (no
    // municipal breakdown).
    baseCurrency: 'USD',
    geoLevel: 'uf',
    dimensions: {
      origin:  { label: 'UF de origem',  kind: 'uf' },
      dest:    { label: 'país parceiro', kind: 'country' },
      partner: { label: 'país parceiro', kind: 'country' },
      product: { codeLabel: 'Código NCM' },
    },
    metrics: [
      { id: 'exp_value',  label: 'Valor exportado (FOB)', family: 'currency', unit: 'US$', agg: 'Soma do valor FOB das exportações', years: [1997, 2024] },
      { id: 'imp_value',  label: 'Valor importado (CIF)', family: 'currency', unit: 'US$', agg: 'Soma do valor das importações',     years: [1997, 2024] },
      { id: 'exp_weight', label: 'Peso exportado',        family: 'mass',     unit: 'kg',  agg: 'Soma do peso líquido exportado',       years: [1997, 2024] },
      { id: 'exp_price',  label: 'Preço médio (US$/kg)',   family: 'ratio',    unit: 'US$/kg', agg: 'Valor FOB ÷ peso líquido', years: [1997, 2024] },
    ],
    // Provenance (live): the real Gold IS wired (gold_comex_flows). The "· Mnn"
    // suffix is a template — dataStore.meta overlays the real yearEnd and, for this
    // partial latest year, the real months elapsed (e.g. "COMEX 2026 · M05"); the
    // literal below is only the pre-resolution fallback.
    prov: {
      lastCrop: 'COMEX 2024 · M12',
    },
    plannedScope: [
      { col: 'NCM · SH4 · SH6',                 desc: 'Classificação harmonizada do produto exportado.' },
      { col: 'uf_origem',                       desc: 'UF onde a mercadoria foi produzida ou está estabelecido o exportador.' },
      { col: 'pais_destino · pais_origem',      desc: 'Parceiro comercial na operação.' },
      { col: 'via',                             desc: 'Modalidade de transporte (marítima · aérea · rodoviária).' },
      { col: 'val_fob_usd · peso_kg · qtd_est', desc: 'Valor FOB em USD, peso líquido e quantidade estatística.' },
    ],
    cobertura: {
      years:      '1997 → presente',
      atualizacao:'mensal (D+30)',
      granularidade: 'NCM × UF × país × via × ano-mês',
    },
  },
  {
    id:     'un_comtrade',
    short:  'UN COMTRADE',
    label:  'UN Comtrade · Estatísticas de Comércio Internacional',
    sub:    'Fluxos de comércio entre nações reportados à Divisão de Estatística da ONU',
    about:  'É o maior repositório global de dados oficiais de comércio internacional, compilado pelas Nações Unidas. Oferece estatísticas de importação e exportação reportadas por diversos países, permitindo situar a participação do Brasil no mercado mundial de cada produto.',
    domain: 'Comércio internacional',
    scope:  'País → país (com ou sem filtro Brasil)',
    source: 'UN Statistics Division',
    table:  'gold_comtrade_flows',
    // Estável: histórico do Brasil desde 2000 (códigos HS aposentados —
    // banana 080300, soja 120100 etc. — traduzidos para os atuais no silver). O
    // total mundial (world_exp) cobre TODO o período: o backfill all-reporters está
    // concluído — 2000–2025, 89–166 reporters por ano (medido 2026-08-28; ver
    // docs/comtrade_world_backfill.md). Ficou em [2022,2023] até então, enquanto
    // aquele backfill estava adiado, e o literal sobreviveu à conclusão dele:
    // crossCommonWindow INTERSECTA os `years` das métricas selecionadas, então
    // world_exp encolhia a janela comparável do compositor de cruzamento para dois
    // anos sobre 26 de dado real.
    // Country → country flows. Product (HS6), flow, partner, quality.
    // Geography is country-level only (no Brazilian UF/município).
    provides: ['product', 'flow', 'partner', 'quality'],
    // Values in USD; country↔country trade, no national geographic dimension.
    baseCurrency: 'USD',
    geoLevel: null,
    dimensions: {
      origin:  { label: 'país reporter', kind: 'country' },
      dest:    { label: 'país parceiro', kind: 'country' },
      partner: { label: 'país parceiro', kind: 'country' },
      product: { codeLabel: 'Código HS6' },
    },
    metrics: [
      { id: 'exp_value', label: 'Valor exportado (BR)', family: 'currency', unit: 'US$', agg: 'Exportações brasileiras declaradas à ONU', years: [2000, 2025] },
      { id: 'imp_value', label: 'Valor importado (BR)', family: 'currency', unit: 'US$', agg: 'Importações brasileiras declaradas à ONU', years: [2000, 2025] },
      { id: 'world_exp', label: 'Exportação mundial',    family: 'currency', unit: 'US$', agg: 'Total mundial do produto (todos reporters)', years: [2000, 2025] },
    ],
    // Provenance (live): the real Gold IS wired (gold_comtrade_flows, Brazil 2000+).
    // The edition YEAR below is overlaid live from gold_source_metadata (real
    // yearEnd); the literal is only the pre-resolution fallback.
    // Country-level only → no UF dimension (ufsTotal = 0).
    prov: {
      lastCrop: 'Comtrade 2023',
    },
    plannedScope: [
      { col: 'reporter · partner',          desc: 'Países envolvidos no fluxo declarado.' },
      { col: 'flow',                        desc: 'Direção do fluxo (export · import · re-export).' },
      { col: 'HS6',                         desc: 'Sistema Harmonizado a 6 dígitos.' },
      { col: 'val_usd · qty · qty_unit',    desc: 'Valor FOB/CIF, quantidade líquida e unidade estatística.' },
      { col: 'data_quality',                desc: 'Bandeira (final · preliminar · estimado · mirror).' },
    ],
    cobertura: {
      // 2000, não 1989: o redesenho totals-only da v1.13.0 passou a ingerir a partir de
      // COMTRADE_START_YEAR=2000 e o Silver tem piso rígido em var('comtrade_min_year')
      // — não existe COMTRADE pré-2000 em Bronze, Silver nem Gold. Medido: Bronze
      // 2000–2025 (21.110.724 linhas), Gold 2000–2025 (26 anos). O rótulo antigo
      // afirmava onze anos que o painel não tem.
      years:      '2000 → presente',
      atualizacao:'anual + revisões',
      granularidade: 'HS6 × par de países × ano',
    },
  },
  {
    id:     'sefaz_nf',
    short:  'SEFAZ NFe',
    label:  'SEFAZ · Fluxos de Notas Fiscais Eletrônicas',
    sub:    'Comércio interno brasileiro reconstruído a partir de NFe inter-estaduais e intermunicipais',
    about:  'Reconstrói o comércio interno brasileiro a partir das Notas Fiscais Eletrônicas, registrando operações de compra e venda entre estados e municípios. Trará uma visão de alta granularidade da movimentação econômica e fiscal — banco ainda em planejamento.',
    domain: 'Comércio interno',
    scope:  'UF ↔ UF · município ↔ município',
    source: 'Receita · SEFAZ',
    table:  'gold_nfe_flows',
    // Internal trade: UF↔UF / município↔município flows, daily, with
    // product (NCM), partner (the counterpart UF), monthly+ and quality.
    provides: ['product', 'geo', 'flow', 'partner', 'monthly', 'quality'],
    // Values in BRL; geography down to municipality level (origin/destination).
    baseCurrency: 'BRL',
    geoLevel: 'municipio',
    dimensions: {
      origin:  { label: 'UF de origem',  kind: 'uf' },
      dest:    { label: 'UF de destino', kind: 'uf' },
      partner: { label: 'UF parceira',   kind: 'uf' },
      product: { codeLabel: 'Código NCM' },
    },
    metrics: [
      { id: 'internal_value',  label: 'Valor das operações', family: 'currency', unit: 'R$', agg: 'Soma do valor das NFe inter/intraestaduais', years: [2010, 2024] },
      { id: 'internal_weight', label: 'Peso movimentado',    family: 'mass',     unit: 'kg', agg: 'Soma do peso transportado',               years: [2010, 2024] },
      { id: 'icms_total',      label: 'ICMS recolhido',      family: 'currency', unit: 'R$', agg: 'Soma do ICMS das operações',              years: [2010, 2024] },
    ],
    plannedScope: [
      { col: 'cfop',                         desc: 'Natureza da operação fiscal.' },
      { col: 'uf_origem · municipio_origem', desc: 'Localização do remetente.' },
      { col: 'uf_destino · municipio_destino', desc: 'Localização do destinatário.' },
      { col: 'ncm',                          desc: 'Classificação do produto.' },
      { col: 'val_operacao · val_icms',      desc: 'Valor total da operação e do imposto recolhido.' },
      { col: 'cnae_remetente · cnae_destino',desc: 'Setor de atividade econômica das partes.' },
    ],
    cobertura: {
      years:      '2010 → presente',
      atualizacao:'diária (defasagem 24h)',
      granularidade: 'NCM × CFOP × par UF/município × dia',
      restricoes:  'Agregação com preservação de sigilo abaixo de N=5 estabelecimentos.',
    },
  },
];

window.bancoById = (id) => window.BANCOS.find(b => b.id === id) || window.BANCOS[0];

// Canonical / default DISPLAY currency for a banco. COMEX/Comtrade are USD-native
// trade bancos, so they default their display to USD and the real US$ figures
// render (the BFF still serves any requested currency from the Gold column). Used
// to reset the display currency on banco switch and to label the value filter.
// Falls back to BRL.
window.canonCurrencyFor = (id) => {
  const b = window.bancoById ? window.bancoById(id) : null;
  return (b && b.baseCurrency) || 'BRL';
};
// Does this banco carry a monetary value? → the currency + monetary-correction
// conventions (MetricConventions) only apply when true. DERIVED so a new banco
// needs no extra flag: monetary iff it declares a base currency OR any metric in
// the `currency` family. (All 5 current bancos are monetary; this gates out a
// future physical-only source, e.g. a pure energy-volume series.) The 'monetary'
// CAPABILITIES token (views.js) labels it for missingCapsLabel / the schema lint.
window.isMonetaryBanco = (b) => {
  const banco = (typeof b === 'string') ? (window.bancoById && window.bancoById(b)) : b;
  if (!banco) return false;
  return !!(banco.baseCurrency || (banco.metrics || []).some(m => m.family === 'currency'));
};
// Business-semantic descriptor for a banco DIMENSION (origin/dest/partner geo
// + product code scheme). Declared per banco in `dimensions` — adapters/views
// read labels & universe kind from HERE instead of branching on bancoId.
window.bancoDim = (id, dim) => {
  const b = window.bancoById ? window.bancoById(id) : null;
  return (b && b.dimensions && b.dimensions[dim]) || {};
};
// Finest geographic granularity a banco exposes ('municipio' | 'uf' | null).
window.geoLevelFor = (id) => {
  const b = window.bancoById ? window.bancoById(id) : null;
  if (!b) return null;
  if (b.geoLevel !== undefined) return b.geoLevel;
  return (b.provides || []).includes('geo') ? 'municipio' : null;
};

// Visibility axis (backend-controlled). `visible: false` hides a banco from the
// whole UI; default (undefined/true) shows it. UI enumerations use this helper;
// bancoById stays over the full list so an id can always be resolved.
window.isBancoVisible = (b) => {
  const banco = (typeof b === 'string') ? window.bancoById(b) : b;
  return !!banco && banco.visible !== false;
};
window.visibleBancos = () => (window.BANCOS || []).filter(b => b.visible !== false);

// Gold table name to DISPLAY: prefer the backend-reported name (dataStore),
// fall back to the registry literal (declared/planned, e.g. for not-connected
// bancos). One resolver so a backend rename propagates to the whole UI.
window.bancoTable = (id) => {
  const fromBackend = (window.dataStore && window.dataStore.table) ? window.dataStore.table(id) : null;
  return fromBackend || ((window.bancoById && window.bancoById(id)) || {}).table || null;
};

// Provenance metadata resolver: the registry banco (UI declaration + fallback)
// OVERLAID with whatever the backend reports (dataStore.meta). The UI reads
// provenance through this — never registry literals directly — so any field
// the backend reports (table, source, granularity, coverage, refresh, counts,
// expected-completion) is authoritative and can't diverge from reality.
window.bancoMeta = (id) => {
  const b = (window.bancoById && window.bancoById(id)) || {};
  const back = (window.dataStore && window.dataStore.meta) ? (window.dataStore.meta(id) || {}) : {};
  const clean = {}; Object.keys(back).forEach(k => { if (back[k] != null) clean[k] = back[k]; });
  return { ...b, ...clean };
};

// Derive the legacy `status` ('live'|'soon') from maturity.hasData so all
// existing routing / CSV gating / cross-source preview logic keeps working while
// the UI reads the richer maturity stage. `maturity` itself is NOT seeded here —
// it is overlaid from BigQuery (/api/source-meta); until it resolves the banco
// has no maturity, so `status` reads 'soon' and the DataGate waits on the live
// metadata (it never shows a placeholder before the real maturity is known).
window.BANCOS.forEach(b => {
  Object.defineProperty(b, 'status', {
    get() { return (window.MATURITY[b.maturity] || {}).hasData ? 'live' : 'soon'; },
    enumerable: true, configurable: true,
  });
});

// Cross-source helpers: every (banco, metric) pair the dashboard can plot
// side by side. `metricById` resolves one pair; `allMetricRefs` enumerates
// them for the series picker.
window.metricById = (bancoId, metricId) => {
  const b = window.bancoById(bancoId);
  return (b && b.metrics) ? b.metrics.find(m => m.id === metricId) || null : null;
};
window.allMetricRefs = () =>
  (window.visibleBancos ? window.visibleBancos() : (window.BANCOS || [])).flatMap(b =>
    (b.metrics || []).map(m => ({ banco: b.id, metric: m.id, bancoMeta: b, metricMeta: m })));

// Family display labels shared by the cross-source view.
window.METRIC_FAMILIES = {
  currency:   { label: 'valor monetário' },
  mass:       { label: 'massa' },
  volume:     { label: 'volume' },
  ratio:      { label: 'razão / índice' },
  area:       { label: 'área' },
  rendimento: { label: 'rendimento / produtividade' },
};

// ── Dev-time COVERAGE LINT ───────────────────────────────────────────────
// A few per-banco maps are CURATED, not derived from this registry: the
// glossary (glossary.js), the cross-source series builders (window.crossSeries
// in src/data/producers.js) and the health table/sources (ViewHealth.jsx). When
// a new visible banco is
// plugged in, those are the spots most likely to be forgotten. This helper
// warns ONCE per map (console only — never touches data) when a visible banco
// has no entry, mirroring viewComponent's "warn loudly instead of failing
// silently". `hasEntry(banco)` returns whether the map covers that banco.
window.__bancoCoverageWarned = window.__bancoCoverageWarned || {};
window.auditBancoCoverage = (mapLabel, hasEntry, opts) => {
  opts = opts || {};
  if (window.__bancoCoverageWarned[mapLabel]) return;        // once per map
  window.__bancoCoverageWarned[mapLabel] = true;
  const list = window.visibleBancos ? window.visibleBancos() : (window.BANCOS || []);
  const missing = list
    .filter(b => !opts.onlyLive || b.status === 'live')
    .filter(b => { try { return !hasEntry(b); } catch { return true; } })
    .map(b => b.id);
  if (missing.length) {
    console.warn(
      `[coverage] ${mapLabel}: visible banco(s) with no entry → ${missing.join(', ')}. ` +
      `Add the matching entry (see CLAUDE.md · "plug in a banco from a new domain").`
    );
  }
};
