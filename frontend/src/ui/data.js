// data.js — client-side registries + pt-BR formatters the /api deliberately
// omits, read directly by the views and joined onto the API rows in
// src/data/decorate.js. NOT data: the UF tile grid (col/row), the region and
// quality-flag taxonomies, and the unit-family conversion table.
//
// (This file used to also hold the prototype's synthetic mock series —
// OVERVIEW_TS / PRODUCT_TS / QUALITY_TS / the TOP_* tables. Those were removed
// once every view moved to the API-backed snapshot; the live series now come
// from /api via src/data/. Only the registries + formatters below remain.)
//
// IMPORTANT — unit families
//   PEVS measures volume two ways depending on the commodity:
//     · 'mass'   → t / kg            (castanha, açaí, erva-mate, carvão…)
//     · 'volume' → m³ / L            (madeira em tora, lenha)
//   Quantities of different families MUST NOT be aggregated.
//   Value (BRL real) is family-agnostic and always aggregatable.

// ────────────────────────────────────────────────────────────────────
// Products — the PEVS commodity list (a loading-frame fallback for
// familiesInBasket before a banco snapshot lands; the live list is snapshot.products).
// ────────────────────────────────────────────────────────────────────
window.PRODUCTS = [
  { code: '49101', name: 'Castanha-do-pará',  unit: 't',  family: 'mass'   },
  { code: '49103', name: 'Açaí (fruto)',      unit: 't',  family: 'mass'   },
  { code: '49105', name: 'Palmito',           unit: 't',  family: 'mass'   },
  { code: '49106', name: 'Amêndoa de babaçu', unit: 't',  family: 'mass'   },
  { code: '49108', name: 'Erva-mate',         unit: 't',  family: 'mass'   },
  { code: '49112', name: 'Pinhão',            unit: 't',  family: 'mass'   },
  { code: '49215', name: 'Madeira em tora',   unit: 'm³', family: 'volume' },
  { code: '49216', name: 'Lenha',             unit: 'm³', family: 'volume' },
  { code: '49218', name: 'Carvão vegetal',    unit: 't',  family: 'mass'   },
  { code: '49221', name: 'Borracha (látex)',  unit: 't',  family: 'mass'   },
  { code: '49222', name: 'Cera de carnaúba',  unit: 't',  family: 'mass'   },
  { code: '49224', name: 'Piaçava (fibra)',   unit: 't',  family: 'mass'   },
];

// ── Unit families registry ───────────────────────────────────────────
// REGISTRY-DRIVEN: each family is a physical DIMENSION. Quantities of
// different families are incommensurable and MUST NEVER be aggregated
// together (value/currency is the only family-agnostic aggregate).
// Each family declares a `base` unit and member `units` with `toBase`
// (multiply a quantity in that unit by toBase to get the base unit).
// Adding a unit = one entry; adding a family = one block. The data must
// tell each product its `family` + native `unit` (see SNAPSHOT_CONTRACTS).
//
// `unit`/`long` are kept for back-compat with existing views (default
// display unit + long name). Brazilian agribusiness set below.
window.UNIT_FAMILIES = {
  mass: {
    id: 'mass', label: 'Massa', unit: 't', long: 'toneladas', base: 't', color: 'var(--embrapa-green-darker)',
    units: [
      { id: 'kg', label: 'kg',  long: 'quilograma', toBase: 0.001 },
      { id: 't',  label: 't',   long: 'tonelada',   toBase: 1 },
      { id: '@',  label: '@',   long: 'arroba (15 kg)', toBase: 0.015 },
      { id: 'sc', label: 'sc',  long: 'saca (60 kg)',   toBase: 0.06, note: 'Saca de 60 kg (convenção; varia por produto).' },
    ],
  },
  volume: {
    id: 'volume', label: 'Volume', unit: 'm³', long: 'metros cúbicos', base: 'm³', color: 'var(--pres-yale-blue)',
    units: [
      { id: 'L',  label: 'L',  long: 'litro',       toBase: 0.001 },
      { id: 'hL', label: 'hL', long: 'hectolitro',  toBase: 0.1 },
      { id: 'm³', label: 'm³', long: 'metro cúbico', toBase: 1 },
    ],
  },
  energia: {
    id: 'energia', label: 'Energia', unit: 'MWh', long: 'megawatt-hora', base: 'MWh', color: 'var(--viz-3)',
    units: [
      { id: 'kWh', label: 'kWh', long: 'quilowatt-hora', toBase: 0.001 },
      { id: 'MWh', label: 'MWh', long: 'megawatt-hora',  toBase: 1 },
      { id: 'GJ',  label: 'GJ',  long: 'gigajoule',      toBase: 0.277778 },
      { id: 'boe', label: 'boe', long: 'barril equiv. petróleo', toBase: 1.62803 },
    ],
  },
  // key is the JS family token the serializer emits (massa→'mass', contagem→'count'),
  // NOT the pt word — so UNIT_FAMILIES[pt.family] resolves for livestock head/eggs.
  count: {
    id: 'count', label: 'Contagem', unit: 'un', long: 'unidades', base: 'un', color: 'var(--viz-9)',
    units: [
      { id: 'un',       label: 'un',       long: 'unidade',          toBase: 1 },
      { id: 'dz',       label: 'dz',       long: 'dúzia',            toBase: 12 },
      { id: 'milheiro', label: 'milheiro', long: 'milheiro (1.000)', toBase: 1000 },
      { id: 'cab',      label: 'cab',      long: 'cabeça',           toBase: 1 },
    ],
  },
  area: {
    id: 'area', label: 'Área', unit: 'ha', long: 'hectares', base: 'ha', color: 'var(--viz-10)',
    units: [
      { id: 'm²',  label: 'm²',  long: 'metro quadrado',     toBase: 0.0001 },
      { id: 'ha',  label: 'ha',  long: 'hectare',            toBase: 1 },
      { id: 'alq', label: 'alq', long: 'alqueire (~2,42 ha)', toBase: 2.42, note: 'Alqueire paulista; varia por região.' },
    ],
  },
  // INTENSITY family (a ratio: production per unit area). Like every other
  // family it is incommensurable with the rest and MUST NEVER be summed — a
  // yield is averaged (area-weighted), never added. Base = kg/ha; t/ha and
  // sc/ha (60 kg sack per hectare) convert by their mass-per-hectare factor.
  rendimento: {
    id: 'rendimento', label: 'Rendimento', unit: 'kg/ha', long: 'quilogramas por hectare', base: 'kg/ha', color: 'var(--viz-6)',
    intensity: true,
    units: [
      { id: 'kg/ha', label: 'kg/ha', long: 'quilograma por hectare', toBase: 1 },
      { id: 't/ha',  label: 't/ha',  long: 'tonelada por hectare',   toBase: 1000 },
      { id: 'sc/ha', label: 'sc/ha', long: 'saca (60 kg) por hectare', toBase: 60, note: 'Saca de 60 kg/ha (convenção; varia por produto).' },
    ],
  },
};

// Default display unit per family (used to seed conventions).
window.defaultUnitOf = (familyId) => (window.UNIT_FAMILIES[familyId] || {}).unit || '';
// Lookup a unit's toBase factor within its family.
window.unitToBase = (familyId, unitId) => {
  const fam = window.UNIT_FAMILIES[familyId];
  const u = fam && (fam.units || []).find(x => x.id === unitId);
  return u ? u.toBase : 1;
};
// Convert a quantity from one unit to another WITHIN the same family.
// NOTE: contract/test-only surface — read solely by data_contracts.cov.test.js. The live
// unit-conversion path goes through window.unitToBase (via massQtyMul/volumeQtyMul/
// countQtyMul in MetricConventions.jsx); no production view calls window.convertUnit.
window.convertUnit = (value, familyId, fromUnit, toUnit) => {
  if (value == null) return null;
  const inBase = value * window.unitToBase(familyId, fromUnit);
  return inBase / window.unitToBase(familyId, toUnit);
};

window.familiesInBasket = (productCodes, bancoId) => {
  // Banco-aware: resolve the ACTIVE banco's product list (snapshot first, then
  // the PEVS fallback list above for pre-load). This keeps a mass-only banco
  // (COMEX/Comtrade) from showing spurious volume controls.
  const snap = (bancoId && window.dataStore && window.dataStore.get && window.dataStore.get(bancoId))
            || (bancoId && window.snapshotFor && window.snapshotFor(bancoId))
            || null;
  const products = (snap && snap.products) || window.PRODUCTS || [];
  const famOf = (c) => { const p = products.find(x => x.code === c); return p ? p.family : null; };
  // Keep only DISPLAYABLE unit families (present in UNIT_FAMILIES). A product whose
  // source unit isn't one of the 5 known families gets 'desconhecida' from Silver
  // (common in COMTRADE's varied HS6 units); that sentinel is not a real family and
  // must not reach UnitFamilyBanner/MetricConventions (UNIT_FAMILIES['desconhecida']
  // is undefined → would crash the banner). Its qty_base is NULL anyway (unsummable).
  const known = (f) => !!(f && window.UNIT_FAMILIES && window.UNIT_FAMILIES[f]);
  // null/undefined = "no product filter" → all families present in the banco.
  // An explicit (possibly empty) selection is honoured literally: zero
  // products → zero families (nothing to measure).
  if (productCodes == null) return [...new Set(products.map(p => p.family).filter(known))];
  return [...new Set(productCodes.map(c => famOf(c)).filter(known))];
};

// ────────────────────────────────────────────────────────────────────
// Geography — Brazilian states and regions
// ────────────────────────────────────────────────────────────────────
window.REGIONS = [
  { id: 'N',  label: 'Norte',         color: 'var(--viz-1)' },
  { id: 'NE', label: 'Nordeste',      color: 'var(--viz-3)' },
  { id: 'CO', label: 'Centro-Oeste',  color: 'var(--viz-5)' },
  { id: 'SE', label: 'Sudeste',       color: 'var(--viz-2)' },
  { id: 'S',  label: 'Sul',           color: 'var(--viz-4)' },
];

// 27 UFs · grid position for the tile map (col, row) + region. These are the
// tile coordinates the /api omits (decorate.js joins them onto the API ufData).
window.UF_DATA = [
  // North
  { uf: 'RR', name: 'Roraima',       region: 'N',  col: 3, row: 0 },
  { uf: 'AP', name: 'Amapá',         region: 'N',  col: 5, row: 0 },
  { uf: 'AM', name: 'Amazonas',      region: 'N',  col: 2, row: 1 },
  { uf: 'PA', name: 'Pará',          region: 'N',  col: 4, row: 1 },
  { uf: 'AC', name: 'Acre',          region: 'N',  col: 1, row: 2 },
  { uf: 'RO', name: 'Rondônia',      region: 'N',  col: 2, row: 2 },
  { uf: 'TO', name: 'Tocantins',     region: 'N',  col: 4, row: 2 },
  // Northeast
  { uf: 'MA', name: 'Maranhão',      region: 'NE', col: 5, row: 1 },
  { uf: 'CE', name: 'Ceará',         region: 'NE', col: 6, row: 1 },
  { uf: 'RN', name: 'Rio Grande do Norte', region: 'NE', col: 7, row: 1 },
  { uf: 'PI', name: 'Piauí',         region: 'NE', col: 5, row: 2 },
  { uf: 'PB', name: 'Paraíba',       region: 'NE', col: 7, row: 2 },
  { uf: 'BA', name: 'Bahia',         region: 'NE', col: 5, row: 3 },
  { uf: 'PE', name: 'Pernambuco',    region: 'NE', col: 6, row: 3 },
  { uf: 'AL', name: 'Alagoas',       region: 'NE', col: 6, row: 4 },
  { uf: 'SE', name: 'Sergipe',       region: 'NE', col: 5, row: 5 },
  // Center-West
  { uf: 'MT', name: 'Mato Grosso',   region: 'CO', col: 3, row: 3 },
  { uf: 'MS', name: 'Mato Grosso do Sul', region: 'CO', col: 3, row: 4 },
  { uf: 'GO', name: 'Goiás',         region: 'CO', col: 4, row: 4 },
  { uf: 'DF', name: 'Distrito Federal', region: 'CO', col: 4, row: 5 },
  // Southeast
  { uf: 'MG', name: 'Minas Gerais',  region: 'SE', col: 5, row: 4 },
  { uf: 'ES', name: 'Espírito Santo', region: 'SE', col: 6, row: 5 },
  { uf: 'RJ', name: 'Rio de Janeiro', region: 'SE', col: 5, row: 6 },
  { uf: 'SP', name: 'São Paulo',     region: 'SE', col: 4, row: 6 },
  // South
  { uf: 'PR', name: 'Paraná',        region: 'S',  col: 3, row: 6 },
  { uf: 'SC', name: 'Santa Catarina', region: 'S', col: 3, row: 7 },
  { uf: 'RS', name: 'Rio Grande do Sul', region: 'S', col: 3, row: 8 },
];

// ────────────────────────────────────────────────────────────────────
// Quality dimension — flag taxonomy (id → label + colour). The per-flag
// COUNTS come from the API (snapshot.quality); this is just the display map.
// ────────────────────────────────────────────────────────────────────
// The REAL Gold data_quality_flag taxonomy (dbt/macros/data_quality_flag.sql
// emits OK/MISSING_VALUE/MISSING_QUANTITY/INCOMPLETE for PEVS/PAM/COMTRADE; the
// COMEX inline CASE in gold_comex_flows.sql adds MISSING_WEIGHT). Labels mirror
// the backend's _FLAG_LABEL_PT (serializers.py) so the donut/legend stays pt-BR.
// The earlier ESTIMATED/BOUNDARY_HISTORIC/OUTLIER ids were the prototype's
// synthetic taxonomy — Gold never emits them, and listing them here silently
// dropped the real INCOMPLETE/MISSING_WEIGHT rows out of the quality charts and
// the quality filter. Keep this in sync with serializers._FLAG_LABEL_PT.
// Labels follow the "Contrato de Dados" spreadsheet's pt-BR "Qualidade dos dados"
// wording: the healthy row is "Normais" (not the English "OK"); the missing-value
// rung is split quantidade vs financeiro. The outlier/problemático tiers are emitted
// by Gold only when the dbt var enable_quality_outliers is on (implied-price detection,
// data_quality_flag.sql + quality_outlier_ctes.sql) — off by default, so they're
// accepted-but-absent until an operator validates per source. The Sheet's "inferidos"
// (auto-preenchido) tier is RESERVED for a future auto-fill pipeline: the two INFERRED_*
// flags below are accepted-but-absent (render 0 today, exactly like a Gold flag with no
// rows), so the structure is ready when such a pipeline is built — nothing emits them yet.
// `desc` is the plain-pt-BR legend shown in the Qualidade window ("O que significa cada flag?").
// Keep labels + desc in sync with serializers._FLAG_LABEL_PT.
window.QUALITY_FLAGS = [
  { id: 'OK',                   label: 'Normais',                                 color: 'var(--ok)',     desc: 'Todas as dimensões do registro (quantidade e valor) estão preenchidas e dentro do esperado.' },
  { id: 'MISSING_VALUE',        label: 'Valor financeiro ausente',                color: 'var(--warn)',   desc: 'O valor financeiro do registro (FOB, vendas, faturamento, etc.) veio em branco na fonte; a quantidade existe.' },
  { id: 'MISSING_QUANTITY',     label: 'Quantidade ausente',                      color: 'var(--info)',   desc: 'A quantidade do registro (m³, kg, saca, cabeças, etc.) veio em branco na fonte; o valor existe.' },
  { id: 'MISSING_WEIGHT',       label: 'Peso ausente',                            color: 'var(--viz-4)',  desc: 'Registro de comércio exterior sem peso líquido — impede o cálculo de preço médio por quilo (US$/kg).' },
  { id: 'INCOMPLETE',           label: 'Incompleto',                              color: 'var(--viz-7)',  desc: 'O registro veio sem quantidade e sem valor — não há grandeza mensurável para analisar.' },
  { id: 'OUTLIER_QUANTITY',     label: 'Quantidade atípica (válida)',             color: 'var(--viz-3)',  desc: 'Quantidade bem acima do esperado, mas com preço implícito coerente — considerada válida, não um erro.' },
  { id: 'PROBLEMATIC_QUANTITY', label: 'Quantidade problemática (provável erro)', color: 'var(--viz-9)',  desc: 'Quantidade bem acima do esperado e com preço implícito (valor÷quantidade) muito fora da mediana do produto — provável erro de digitação ou inserção.' },
  { id: 'OUTLIER_VALUE',        label: 'Valor atípico (válido)',                  color: 'var(--viz-5)',  desc: 'Valor financeiro bem acima do esperado, mas com preço implícito coerente — considerado válido, não um erro.' },
  { id: 'PROBLEMATIC_VALUE',    label: 'Valor problemático (provável erro)',      color: 'var(--err)',    desc: 'Valor financeiro bem acima do esperado e com preço implícito muito fora da mediana do produto — provável erro de digitação ou inserção.' },
  // PAM-only: a SIDRA source error preserved faithfully and now surfaced in-product.
  { id: 'AREA_INCONSISTENT',    label: 'Área inconsistente (plantada < colhida)', color: 'var(--viz-6)',  desc: 'A área plantada reportada pelo IBGE é menor que a área colhida — agronomicamente impossível (não se colhe mais terra do que se planta). É um erro da fonte (SIDRA), preservado fielmente e sinalizado aqui em vez de silenciosamente corrigido. Ocorre apenas em lavouras (PAM).' },
  // Reserved for a FUTURE auto-fill pipeline (accepted-but-absent — render 0 today).
  { id: 'INFERRED_QUANTITY',    label: 'Quantidade inferida',                     color: 'var(--viz-8)',  reserved: true, desc: 'Quantidade que veio em branco e seria preenchida automaticamente por uma etapa do pipeline. Reservada para preenchimento automático futuro; ainda não utilizada (sempre 0 hoje).' },
  { id: 'INFERRED_VALUE',       label: 'Valor financeiro inferido',               color: 'var(--viz-10)', reserved: true, desc: 'Valor financeiro que veio em branco e seria preenchido automaticamente por uma etapa do pipeline. Reservado para preenchimento automático futuro; ainda não utilizado (sempre 0 hoje).' },
];

// ────────────────────────────────────────────────────────────────────
// Formatters
// ────────────────────────────────────────────────────────────────────
// bi/mi/mil ladder kept local on purpose (per-tier decimals), but buckets on the MAGNITUDE
// (|n|) and re-applies the sign — aligned with magnitude.js's abs-based kernel (DEDUP-7), so
// a large negative (e.g. a net balance) abbreviates to "-2,50 bi" instead of falling through
// to the unabbreviated locale string.
// NOTE: window.fmtBRL and window.fmtNum below are a contract/test-only surface — read solely
// by data_contracts.cov.test.js. Live value formatting goes through window.formatValue /
// window.applyConv (MetricConventions.jsx); no production view reads these two.
window.fmtBRL = (n) => {
  if (n == null) return '—';
  const a = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (a >= 1e9) return 'R$ ' + sign + (a / 1e9).toFixed(2).replace('.', ',') + ' bi';
  if (a >= 1e6) return 'R$ ' + sign + (a / 1e6).toFixed(1).replace('.', ',') + ' mi';
  if (a >= 1e3) return 'R$ ' + sign + (a / 1e3).toFixed(0).replace('.', ',') + ' mil';
  return 'R$ ' + n.toLocaleString('pt-BR');
};
window.fmtNum = (n, unit) => {
  if (n == null) return '—';
  return n.toLocaleString('pt-BR') + (unit ? ' ' + unit : '');
};
// ── Percentages: THREE formatters, TWO opposite input conventions ────────────
//
//     fmtPct(0.6)   → '60,0%'   takes a FRACTION   (multiplies by 100)
//     pctBR(60)     → '60,0%'   takes a PERCENTAGE (only appends '%')
//     fmtSigned(60) → '+60,0%'  takes a PERCENTAGE (like pctBR)
//
// The names do not say which is which, and passing a percentage to fmtPct renders
// something like "4361,4%" — which shipped once (v1.29.0). The payload field names are
// the guardrail: `*Frac` is a fraction, `*Share`/`*Pct` is a percentage, and a call site
// crossing the boundary multiplies EXPLICITLY (`chPct(data.expFrac * 100)`).
//
// formatterContracts.test.js pins all of this against real values — change a convention
// there first, and read it there before writing a call site or a test stub.
window.fmtPct = (n, digits = 1) => {
  if (n == null) return '—';
  return (n * 100).toFixed(digits).replace('.', ',') + '%';
};
window.fmtSigned = (n, digits = 1, suffix = '%') => {
  if (n == null) return '—';
  return (n >= 0 ? '+' : '') + n.toFixed(digits).replace('.', ',') + suffix;
};

// pt-BR number with a FIXED number of decimals (min = max), or '—' for null.
// Shared by the multi-source / curated views (was copy-pasted as caNum / msNum
// / chNum). `pctBR` appends '%' to an ALREADY-percentage value — distinct from
// fmtPct above, which multiplies a fraction by 100 (see the note there).
//
// The null guard is on pctBR itself, not inherited from numBR: appending '%' to numBR's
// em dash rendered "—%", which reads as a value rather than as absence.
window.numBR = (v, d = 0) =>
  (v == null ? '—' : v.toLocaleString('pt-BR', { maximumFractionDigits: d, minimumFractionDigits: d }));
window.pctBR = (v, d = 1) => (v == null ? '—' : window.numBR(v, d) + '%');

// Compact row-counter label (mi / mil) for provenance "Linhas" readouts.
// Shared by MainScreen + ViewHealth (was duplicated verbatim in both). Deliberately a
// 2-tier SUBSET of magnitude.js (no 'bi' — row counts never reach 1e9), so it keeps its
// own ladder (DEDUP-7).
window.fmtRows = (n) => {
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.', ',') + ' mi';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + ' mil';
  return n.toLocaleString('pt-BR');
};
