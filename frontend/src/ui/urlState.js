// urlState.js — the shared deep-link codec contract.
//
// The app state travels in the share URL. The ENCODER lives in
// AppShell.onShare and the DECODER in Dashboard.readStateFromURL — two halves
// of the same wire format. The param-key list and the array sentinel rules
// were duplicated as literals on both sides; a typo on one half silently
// breaks shared links. This module is the single source of truth for the keys
// and the array encode/decode, so the two halves can't drift.

// Every query param the dashboard owns. Used by the encoder (to know what to
// emit) and by the decoder (to detect whether a URL carries OUR state at all,
// so unrelated params like ?t=… stay inert).
window.URL_STATE_KEYS = [
  'v', 'b', 'ip', 'cur', 'corr', 'mu', 'vu', 'as',
  'pb', 'fl', 'st', 'vmn', 'vmx', 'sd', 'ed', 'fx', 'cx', 'mk', 'or', 'ni',
  // COMTRADE país reporter (rp) / país parceiro (pt). rp is 3-state: 'ALL' = mundo, a CSV
  // of ISO codes, or absent = Brasil (default). pt is the standard array encoding (all/subset).
  'rp', 'pt',
  // Sub-UF / município geography (v1.5.2): mesorregião (me), microrregião (mc),
  // região intermediária (it), região imediata (im), município (mn). null="all"
  // (omitted), so a non-narrowing selection never bloats the URL — only an actual
  // sub-UF/município narrowing travels (and the município subset stays small, the
  // 414-safe counterpart to the POST /api/municipio-yearly query path).
  'me', 'mc', 'it', 'im', 'mn',
  'xs', 'xm', 'xy0', 'xy1',
];

// Array dimension → param. null = "no filter" (omitted → all on restore); an
// explicit empty selection travels as the sentinel "-" so "Nenhum"/"Nenhuma"
// survives the round-trip instead of silently restoring as "all".
window.urlEncodeArr = (a) => (a == null ? '' : (a.length ? a.join(',') : '-'));

// Inverse of urlEncodeArr, reading from a URLSearchParams.
//   absent/'' → null (no filter, all) · '-' → [] (explicit none) · csv → array
window.urlDecodeArr = (q, key) => {
  const v = q.get(key);
  if (v === null || v === '') return null;
  if (v === '-') return [];
  return v.split(',').filter(Boolean);
};

// Numeric param: absent/'' → null, else a FINITE number. A malformed value
// (?vmn=abc) decodes to null rather than NaN, so a hand-edited/garbage share URL
// can't propagate NaN into value-range filters or the cross-view year bounds.
window.urlDecodeNum = (q, key) => {
  const v = q.get(key);
  if (v === null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

// Does this query string carry any of OUR keys? (Decoder gate.)
window.urlHasOwnState = (q) => window.URL_STATE_KEYS.some(k => q.has(k));

// Build the share query string from the flat state object the encoder
// assembles (keys = URL_STATE_KEYS). Drops empty/undefined/null values.
window.urlEncodeState = (state) =>
  Object.entries(state)
    .filter(([, v]) => v !== '' && v !== undefined && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&');

// Cap the município list embedded in a share URL: a large selection (≈ thousands of
// 7-digit codes) would overflow the ~8 KB request-line limit of proxies/Cloud Run/IAP
// → the link 414s or truncates. Past the cap we omit `mn` and let the higher sub-UF
// facets (me/mc/it/im) reconstruct the scope (the common parent-driven case).
window.MN_URL_CAP = 200;

// ── SINGLE encoder: assemble the flat URL-state object from the app state ──────
// Used by BOTH url writers — the address-bar write-back (main.jsx) AND the
// Compartilhar/ABNT permalink (AppShell.buildPermalink) — so a dimension can never
// be added to one encoder and forgotten in the other (the H1 drift: the sub-UF/
// município keys me/mc/it/im/mn were in the permalink but missing from the write-
// back, so a reload silently dropped the geo narrowing). Returns the object; each
// caller runs urlEncodeState() on it. Value-range (vmn/vmx) is INTENTIONALLY not
// emitted here: it has no backend filter path, so persisting it would let a stale
// URL re-assert a phantom "Faixa de valor" in the citation.
window.buildUrlState = ({ view, database, infoPage, conventions, summary, crossState, isCross }) => {
  const arr = window.urlEncodeArr || (() => '');
  const conv = conventions || {};
  const s = summary || {};
  const munis = s.munis;
  const mnParam =
    Array.isArray(munis) && munis.length > window.MN_URL_CAP ? '' : arr(munis);
  return {
    v: view,
    b: database,
    ip: infoPage,
    cur: conv.currency,
    corr: conv.correction,
    mu: conv.units?.mass,
    vu: conv.units?.volume,
    as: conv.autoScale ? 1 : 0,
    pb: arr(s.basket),
    fl: arr(s.flags),
    st: arr(s.states),
    // Sub-UF / município geography (v1.5.2). null = "all" → arr yields '' → dropped.
    me: arr(s.mesos),
    mc: arr(s.micros),
    it: arr(s.inters),
    im: arr(s.imediatas),
    mn: mnParam,
    sd: s.startDate || '',
    ed: s.endDate || '',
    // Server-side flow filter (export/import); omitted when 'all'/absent.
    fx: s.flow && s.flow !== 'all' ? s.flow : '',
    // Server-side SIDRA-table filter (t289 extração | t291 silvicultura); omitted when
    // 'all'/absent, so a permalink to an unfiltered panel keeps meaning "every table" —
    // the survey's own total — rather than freezing today's default into the link.
    // Escreve `tb` desde v1.46.0; o decodificador ainda ACEITA o `or=extrativa|silvicultura`
    // dos links antigos (ver main.jsx) para que nenhum permalink já compartilhado pare de
    // restaurar o recorte.
    tb: s.tabela && s.tabela !== 'all' ? s.tabela : '',
    // Níveis de industrialização; omitido quando nada está selecionado.
    ni: window.urlEncodeArr(s.niveis),
    // Server-side customs-procedure filter (regime aduaneiro, COMTRADE); omitted when
    // 'all'/absent so a non-narrowed request stays clean.
    cx: s.customs && s.customs !== 'all' ? s.customs : '',
    // Server-side tipo-de-mercado filter (COMTRADE); omitted when 'all'/absent.
    mk: s.market && s.market !== 'all' ? s.market : '',
    // COMTRADE país reporter (3-state): 'ALL' = mundo (world total), a CSV of ISO codes for a
    // specific set, or '' for Brazil/absent (the default → dropped). The distinct 'ALL' literal
    // keeps "world" separate from the '-' empty sentinel. País parceiro (pt) uses the standard
    // array encoding (null → '' = all; CSV subset; '-' = none, coerced back to all on restore).
    rp: s.reporters === '__all__' ? 'ALL' : Array.isArray(s.reporters) ? arr(s.reporters) : '',
    pt: arr(s.partners),
    xs: isCross && crossState?.series ? crossState.series.map((r) => `${r.b}:${r.m}`).join('|') : '',
    xm: isCross ? crossState?.mode || '' : '',
    xy0: isCross && crossState?.y0 ? crossState.y0 : '',
    xy1: isCross && crossState?.y1 ? crossState.y1 : '',
  };
};
