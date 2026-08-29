// filtersSchema.js — declarative per-banco filter dimensions.
//
// The FilterMenu is scoped to the banco selected in the sidebar and
// renders the dimensions declared here. Adding/curating a banco's
// filterable dimensions = editing this file (no FilterMenu rewrite).
//
// tier:
//   'universal' → exists in every banco (e.g. período)
//   'shared'    → exists in several, possibly at different granularity
//   'specific'  → unique to this banco
//
// type: hints how the dimension is rendered / what control it uses.
//   'products' | 'date-range' | 'period-value' | 'value-range'
//   'geo-cascade' | 'flags' | 'multi' | 'multi-search' | 'multi-tree' | 'segment'
//
// ── CAPABILITY METADATA (the "make every filter dynamic" contract) ───────
// Each dim self-declares what makes it APPLICABLE and whether it is actually
// FILTERABLE today, so the FilterMenu can gate purely from the schema (one
// source of truth) instead of hard-coding sections:
//
//   requires : capability token (window.CAPABILITIES) the banco must `provides`
//              for this dim to even apply — null/absent = universal (every banco,
//              e.g. período). Mirrors the view requires/provides crossing in
//              views.js (window.viewAppliesTo).
//   backed   : true  → a real, working filter path exists (client-side narrowing
//                       in dataFilters.js, or a server param — see serverParam).
//              false → the dimension EXISTS in the source but is NOT filterable
//                       yet (the snapshot/serving mart doesn't carry it as a
//                       filter axis — e.g. via/CFOP/CNAE summed away in Silver,
//                       partner/reporter only in the dedicated flow/partner
//                       endpoints). A non-backed dim is HIDDEN (we only show what
//                       the user can actually use) rather than shown read-only.
//   serverParam : for SERVER-SIDE filters (the snapshot is pre-aggregated over
//                 this axis, so changing it re-fetches the snapshot). 'flow' is
//                 the first: the serving marts carry `flow` in their grain and the
//                 gateway already accepts a flow param, so picking export/import
//                 re-queries the snapshot. Client-side dims (product/geo/quality/
//                 period) have no serverParam.

// ── Value-range quick presets (single source of truth) ───────────────────
// Used BOTH by the FilterMenu "valor mínimo" shortcut buttons AND by the
// row-counter heuristic in dataFilters.js (valueShareForRange, which reads
// `rowShare`). `suffix` builds the label as `≥ <symbol> <suffix>` at render
// time (symbol depends on the active currency); `none` has no threshold.
//
// HONESTY (#7): the per-threshold `rowShare` fractions used to be 0.81 / 0.52 /
// 0.18 / 0.04 — fabricated guesses, since there is NO real COUNT of rows that
// clear a value threshold (no backend aggregate exists for it). They scaled the
// "Linhas X de Y" hero counter, making it assert a made-up filtered count. They
// are now all 1.00, so a value-threshold preset leaves the counter at the
// UNFILTERED total rather than parading an invented number. `rowShare` stays on
// each preset (kept at 1.00) so dataFilters.js's `preset.rowShare` lookup keeps
// returning a valid number — never undefined/NaN — and the real, snapshot-derived
// share dimensions (product/flag/year/state) are untouched.
window.VALUE_PRESETS = [
  { id: 'none', min: null,      max: null, suffix: null,      rowShare: 1.00 },
  { id: '1k',   min: 1_000,     max: null, suffix: '1 mil',   rowShare: 1.00 },
  { id: '10k',  min: 10_000,    max: null, suffix: '10 mil',  rowShare: 1.00 },
  { id: '100k', min: 100_000,   max: null, suffix: '100 mil', rowShare: 1.00 },
  { id: '1M',   min: 1_000_000, max: null, suffix: '1 mi',    rowShare: 1.00 },
];

// Flow (fluxo) option universes per banco — the segment control reads these so
// the menu offers exactly the directions the source declares. `value` is the
// canonical Gold `flow` token the serving query filters on; `label` is pt-BR.
// `all` (no filter) sums the directions the snapshot defaults to.
window.FLOW_OPTIONS = {
  mdic_comex: [
    { value: 'all',    label: 'Todos' },
    { value: 'export', label: 'Exportação' },
    { value: 'import', label: 'Importação' },
  ],
  // TOTALS-ONLY (2026-07): the base ingests only the two direction TOTALS — X→export,
  // M→import. The sub-flows (re-export/re-import/…) are subsets of X/M and are no longer
  // ingested (they would double-count), so the picker offers only the two totals; 'all'
  // sums export+import (total turnover). Values are the readable `flow` tokens Gold/serving
  // carry verbatim (silver_comtrade_flows maps X/M → export/import).
  un_comtrade: [
    { value: 'all',        label: 'Todos' },
    { value: 'export',     label: 'Exportação' },
    { value: 'import',     label: 'Importação' },
  ],
};

// Customs-procedure (regime aduaneiro) options for the COMTRADE server-side regime
// Customs-procedure (regime aduaneiro) options for the COMTRADE server-side regime filter.
// FROZEN (2026-07, totals-only): the base now ingests ONLY customsCode=C00, so customs_code
// is a constant — a regime filter would offer a single value. Empty ⇒ customsOptionsFor()
// returns null ⇒ FilterMenu never renders the "Regime aduaneiro" segment (it gates on the
// options, not the schema dim). The option list is kept, commented, for easy revival.
window.CUSTOMS_OPTIONS = {
  // un_comtrade: [
  //   { value: 'all', label: 'Todos os regimes' },
  //   { value: 'C00', label: 'C00 · Total' }, { value: 'C01', label: 'C01' },
  //   { value: 'C02', label: 'C02' }, { value: 'C03', label: 'C03' },
  //   { value: 'C04', label: 'C04' }, { value: 'C05', label: 'C05' },
  //   { value: 'C06', label: 'C06' }, { value: 'C07', label: 'C07' },
  //   { value: 'C08', label: 'C08' }, { value: 'C14', label: 'C14' },
  //   { value: 'C15', label: 'C15' }, { value: 'C20', label: 'C20' },
  // ],
};

// Tipo de mercado (economic purpose) options for the COMTRADE server-side market filter.
// FROZEN (2026-07): "Tipo de mercado" needs the customs-procedure detail the totals-only
// base no longer carries. Empty ⇒ marketOptionsFor() returns null ⇒ FilterMenu never renders
// the "Tipo de mercado" segment. See the frozen-feature memo. Kept, commented, for revival.
window.MARKET_OPTIONS = {
  // un_comtrade: [
  //   { value: 'all', label: 'Todos' },
  //   { value: 'consumo', label: 'Consumo' },
  //   { value: 'processamento', label: 'Processamento' },
  // ],
};

window.FILTER_SCHEMAS = {
  ibge_pevs: {
    table: 'gold_pevs_production',
    dims: [
      { id: 'produtos',  tier: 'shared',    type: 'products',
        requires: 'product', backed: true,
        label: 'Produtos · PEVS',          column: 'codigo_pevs',
        hint: 'Produtos da extração vegetal (floresta nativa).' },
      { id: 'periodo',   tier: 'universal', type: 'period-value',
        requires: null, backed: true,
        label: 'Período & faixa de valor', column: 'ano · val_real_ipca',
        hint: 'Janela temporal e corte por valor monetário da linha.' },
      { id: 'geografia', tier: 'shared',    type: 'geo-cascade',
        requires: 'geo', backed: true,
        label: 'Geografia',                column: 'uf · municipio',
        hint: 'Cascata nação ▸ região ▸ estado ▸ meso/microrregião · intermediária/imediata ▸ município.' },
      { id: 'qualidade', tier: 'specific',  type: 'flags',
        requires: 'quality', backed: true,
        label: 'Qualidade dos dados',      column: 'data_quality_flag',
        hint: 'Bandeira de qualidade por linha.' },
    ],
  },

  ibge_pam: {
    table: 'gold_pam_production',
    dims: [
      { id: 'produtos',  tier: 'shared',    type: 'products',
        requires: 'product', backed: true,
        label: 'Lavouras · PAM',           column: 'produto_pam',
        hint: 'Culturas temporárias e permanentes da Produção Agrícola Municipal.' },
      { id: 'periodo',   tier: 'universal', type: 'period-value',
        requires: null, backed: true,
        label: 'Período & faixa de valor', column: 'ano · valor_producao',
        hint: 'Janela temporal (anual) e corte por valor da produção.' },
      { id: 'geografia', tier: 'shared',    type: 'geo-cascade',
        requires: 'geo', backed: true,
        label: 'Geografia',                column: 'uf · municipio',
        hint: 'Cascata nação ▸ região ▸ estado ▸ meso/microrregião · intermediária/imediata ▸ município.' },
      { id: 'qualidade', tier: 'specific',  type: 'flags',
        requires: 'quality', backed: true,
        label: 'Qualidade dos dados',      column: 'data_quality_flag',
        hint: 'Bandeira de qualidade por linha.' },
    ],
  },

  ibge_ppm: {
    table: 'gold_ppm_production',
    dims: [
      { id: 'produtos',  tier: 'shared',    type: 'products',
        requires: 'product', backed: true,
        label: 'Rebanho/Produtos · PPM',   column: 'produto_ppm',
        hint: 'Tipos de rebanho e produtos de origem animal da Pesquisa da Pecuária Municipal.' },
      { id: 'periodo',   tier: 'universal', type: 'period-value',
        requires: null, backed: true,
        label: 'Período & faixa de valor', column: 'ano · valor_producao',
        hint: 'Janela temporal (anual) e corte por valor da produção animal.' },
      { id: 'geografia', tier: 'shared',    type: 'geo-cascade',
        requires: 'geo', backed: true,
        label: 'Geografia',                column: 'uf · municipio',
        hint: 'Cascata nação ▸ região ▸ estado ▸ meso/microrregião · intermediária/imediata ▸ município.' },
      { id: 'qualidade', tier: 'specific',  type: 'flags',
        requires: 'quality', backed: true,
        label: 'Qualidade dos dados',      column: 'data_quality_flag',
        hint: 'Bandeira de qualidade por linha.' },
    ],
  },

  mdic_comex: {
    table: 'gold_comex_flows',
    dims: [
      { id: 'periodo',   tier: 'universal', type: 'date-range',
        requires: null, backed: true,
        label: 'Período',                  column: 'ano_mes',
        hint: 'Mensal, de 1997 ao presente.' },
      { id: 'ncm',       tier: 'shared',    type: 'multi-tree',
        requires: 'product', backed: true,
        label: 'Produto · NCM / SH',       column: 'ncm',
        hint: 'Hierarquia SH2 ▸ SH4 ▸ SH6 ▸ NCM 8 dígitos.' },
      { id: 'fluxo',     tier: 'specific',  type: 'segment',
        requires: 'flow', backed: true, serverParam: 'flow',
        label: 'Fluxo',                    column: 'flow',
        hint: 'Direção da operação (exportação ou importação).' },
      { id: 'uf_origem', tier: 'shared',    type: 'multi',
        requires: 'geo', backed: true,
        label: 'UF de origem',             column: 'uf_origem',
        // Always the BRAZILIAN side of the operation (the establishment UF), for both
        // flows — not the foreign counterpart. On import there is no Brazilian
        // "exporter", so spell out the per-flow meaning to avoid a directional misread.
        hint: 'UF brasileira da operação — origem na exportação, destino na importação (sempre o lado nacional).' },
      // ── Declared in the source but NOT filterable yet (backed:false → hidden) ──
      // País parceiro lives only in the dedicated flows/partners endpoints, not as
      // a filter axis of the pre-aggregated snapshot; `via` (transport route) is
      // summed away at the SERVING layer (serving_comex_annual) — Silver and Gold both
      // keep transport_route_code. Surfaced here for documentation + a future backend
      // pass, but hidden from the menu until a real filter path exists.
      { id: 'pais',      tier: 'specific',  type: 'multi-search',
        requires: 'partner', backed: false,
        label: 'País parceiro',            column: 'pais_destino · pais_origem',
        hint: 'Destino (exportação) ou origem (importação).' },
      { id: 'via',       tier: 'specific',  type: 'multi',
        requires: 'flow', backed: false,
        label: 'Via de transporte',        column: 'via',
        options: ['Marítima', 'Aérea', 'Rodoviária', 'Ferroviária', 'Fluvial', 'Dutos'],
        hint: 'Modalidade logística da operação.' },
      { id: 'valor',     tier: 'universal', type: 'value-range',
        requires: null, backed: false,
        label: 'Faixa de valor (FOB)',     column: 'val_fob_usd',
        hint: 'Corte por valor FOB em dólares.' },
    ],
  },

  un_comtrade: {
    table: 'gold_comtrade_flows',
    dims: [
      { id: 'periodo',  tier: 'universal', type: 'date-range',
        requires: null, backed: true,
        label: 'Período',                  column: 'ano',
        hint: 'Anual, de 2000 ao presente.' },
      { id: 'hs6',      tier: 'shared',    type: 'multi-tree',
        requires: 'product', backed: true,
        label: 'Produto · HS6',            column: 'hs6',
        hint: 'Sistema Harmonizado a 6 dígitos.' },
      { id: 'flow',     tier: 'specific',  type: 'segment',
        requires: 'flow', backed: true, serverParam: 'flow',
        label: 'Fluxo',                    column: 'flow',
        hint: 'Direção do fluxo internacional.' },
      // FROZEN (2026-07, totals-only): the base now ingests ONLY the customsCode=C00
      // ("todos os regimes / total") aggregate, so customs_code is a constant — a filter
      // over it would offer a single value. Hidden until/unless the base carries the
      // per-regime customs breakdown again. Kept as scaffold; CUSTOMS_OPTIONS stays defined.
      // { id: 'regime',   tier: 'specific',  type: 'segment',
      //   requires: 'flow', backed: true, serverParam: 'customs',
      //   label: 'Regime aduaneiro',         column: 'customs_code',
      //   hint: 'Procedimento aduaneiro (customsCode). C00 = todos os regimes / total.' },
      // FROZEN (2026-07): "Tipo de mercado" (natureza econômica consumo/processamento) —
      // needs the customs-procedure detail the totals-only base no longer carries. See the
      // frozen-feature memo. Scaffold (MARKET_OPTIONS, the matrix editor) kept dormant.
      // { id: 'mercado',  tier: 'specific',  type: 'segment',
      //   requires: 'flow', backed: true, serverParam: 'market',
      //   label: 'Tipo de mercado',          column: 'market_nature',
      //   hint: 'Natureza econômica (consumo/processamento) classificada por regime×fluxo.' },
      // reporter/partner are only resolved in the partner-level endpoints, not as
      // snapshot filter axes.
      { id: 'reporter', tier: 'specific',  type: 'multi-search',
        requires: 'partner', backed: true, serverParam: 'reporters',
        label: 'País reporter',            column: 'reporter',
        hint: 'País cujo comércio é analisado (quem declarou à UNSD). Padrão: Brasil.' },
      { id: 'partner',  tier: 'specific',  type: 'multi-search',
        requires: 'partner', backed: true, serverParam: 'partners',
        label: 'País parceiro',            column: 'partner',
        hint: 'Contraparte do fluxo (destino/origem). Padrão: todos.' },
      { id: 'valor',    tier: 'universal', type: 'value-range',
        requires: null, backed: false,
        label: 'Faixa de valor (US$)',     column: 'val_usd',
        hint: 'Corte por valor declarado.' },
    ],
  },

  sefaz_nf: {
    table: 'gold_nfe_flows',
    dims: [
      { id: 'periodo',     tier: 'universal', type: 'date-range',
        requires: null, backed: false,
        label: 'Período',                column: 'ano_mes',
        hint: 'Diária (defasagem 24h), de 2010 ao presente.' },
      // SEFAZ NFe is not yet ingested (maturity 'planejado' → the menu shows the
      // read-only preview anyway), so every dim is declared-but-not-backed.
      { id: 'ncm',         tier: 'shared',    type: 'multi-tree',
        requires: 'product', backed: false,
        label: 'Produto · NCM',          column: 'ncm',
        hint: 'Classificação fiscal da mercadoria.' },
      { id: 'cfop',        tier: 'specific',  type: 'multi',
        requires: 'flow', backed: false,
        label: 'Natureza · CFOP',        column: 'cfop',
        hint: 'Código fiscal de operações e prestações.' },
      { id: 'geo_origem',  tier: 'shared',    type: 'geo-cascade',
        requires: 'geo', backed: false,
        label: 'Origem',                 column: 'uf_origem · municipio_origem',
        hint: 'Localização do remetente da NFe.' },
      { id: 'geo_destino', tier: 'shared',    type: 'geo-cascade',
        requires: 'geo', backed: false,
        label: 'Destino',                column: 'uf_destino · municipio_destino',
        hint: 'Localização do destinatário da NFe.' },
      { id: 'cnae',        tier: 'specific',  type: 'multi-search',
        requires: 'partner', backed: false,
        label: 'Setor · CNAE',           column: 'cnae_remetente · cnae_destino',
        hint: 'Atividade econômica das partes.' },
      { id: 'valor',       tier: 'universal', type: 'value-range',
        requires: null, backed: false,
        label: 'Faixa de valor (R$)',    column: 'val_operacao',
        hint: 'Corte pelo valor total da operação.' },
    ],
  },
};

window.filterSchemaFor = (bancoId) =>
  window.FILTER_SCHEMAS[bancoId] || window.FILTER_SCHEMAS.ibge_pevs;

window.TIER_LABEL = {
  universal: 'Universal',
  shared:    'Compartilhada',
  specific:  'Específica do banco',
};

// ── Capability gating (the single source of truth for dim availability) ──
// A dim APPLIES to a banco when the banco `provides` the dim's `requires`
// capability (null requires = universal). It is FILTERABLE (shown as a live
// control) only when it ALSO `backed` is true. Mirrors window.viewAppliesTo.
window.dimAppliesTo = (banco, dim) => {
  const b = (typeof banco === 'string') ? (window.bancoById && window.bancoById(banco)) : banco;
  if (!b || !dim) return false;
  if (!dim.requires) return true;               // universal (e.g. período)
  return (b.provides || []).includes(dim.requires);
};

// The dims a banco can actually FILTER ON today: applies AND backed. This is
// what the menu renders — nothing the user can't use. Non-backed dims (declared
// but data-blocked) and non-applicable dims (capability the banco lacks) drop out.
window.bancoFilterDims = (bancoId) => {
  const b = window.bancoById ? window.bancoById(bancoId) : null;
  const schema = window.filterSchemaFor(bancoId);
  return (schema.dims || []).filter(d => d.backed && window.dimAppliesTo(b, d));
};

// Flow (server-side filter) options for a banco, or null when the banco has no
// flow dimension (its snapshot isn't flow-separated → no fluxo control).
window.flowOptionsFor = (bancoId) => window.FLOW_OPTIONS[bancoId] || null;

// Customs-procedure (regime aduaneiro) options for a banco, or null when the banco has
// no customs_code dimension (only COMTRADE carries it). Mirrors flowOptionsFor.
window.customsOptionsFor = (bancoId) => window.CUSTOMS_OPTIONS[bancoId] || null;

// Tipo de mercado (consumo/processamento) options, or null when the banco has no
// market_nature dimension (only COMTRADE carries it). Mirrors flowOptionsFor.
window.marketOptionsFor = (bancoId) => window.MARKET_OPTIONS[bancoId] || null;

// COMTRADE país reporter / parceiro country multi-selects. Gated to un_comtrade — the only
// banco whose mart carries the reporter/partner ISO columns (it declares provides:['partner']
// AND has no Brazilian geo cascade, geoLevel=null). The FilterMenu renders the two GeoColumn
// pickers when this is true AND window.comtradeCountries() has loaded the universe. Unlike
// flow/customs/market, the option list is NOT a static OPTIONS map — it comes from the
// /api/countries endpoint (203 reporters × 246 partners).
window.hasCountryFilters = (bancoId) => bancoId === 'un_comtrade';

// ── Dev-time COVERAGE LINT (mirrors window.auditBancoCoverage) ────────────
// Catches the drift the dual capability sources invite: a dim whose `requires`
// is not a known capability token, a banco that `provides` a filterable
// capability but has no backed dim for it, or a serverParam dim missing its
// FLOW_OPTIONS. Console-only, once per run — never touches data.
window.__filterSchemaAudited = false;
window.auditFilterSchemaCoverage = () => {
  if (window.__filterSchemaAudited) return;
  window.__filterSchemaAudited = true;
  const caps = window.CAPABILITIES || {};
  const problems = [];
  Object.entries(window.FILTER_SCHEMAS).forEach(([bancoId, schema]) => {
    (schema.dims || []).forEach(d => {
      if (d.requires && !caps[d.requires]) {
        problems.push(`${bancoId}.${d.id}: requires '${d.requires}' is not a known capability (CAPABILITIES in views.js)`);
      }
      if (d.serverParam === 'flow' && !window.flowOptionsFor(bancoId)) {
        problems.push(`${bancoId}.${d.id}: serverParam 'flow' but no FLOW_OPTIONS[${bancoId}]`);
      }
    });
  });
  if (problems.length) {
    console.warn(
      '[filter-schema] coverage drift detected:\n  ' + problems.join('\n  ') +
      '\n→ align filtersSchema.js requires/backed/serverParam with CAPABILITIES (views.js) + bancos.js provides.'
    );
  }
};

// Run the coverage lint once the registries have loaded (window 'load', mirroring
// contracts.js). views.js (CAPABILITIES) imports before this file in main.jsx, so
// the token check is valid even on an immediate run. Console-only; never blocks.
if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  if (document.readyState === 'complete') window.auditFilterSchemaCoverage();
  else window.addEventListener('load', () => window.auditFilterSchemaCoverage());
}
