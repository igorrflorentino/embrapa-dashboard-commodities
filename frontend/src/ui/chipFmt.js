// chipFmt.js — shared formatters for the filter trigger-bar "chips".
//
// The chip labels (products / value range / quality) were implemented THREE
// times with identical rules: FilterMenu.buildChipSummary (operates on Sets),
// Dashboard.chipsFromRestoredSummary and Dashboard.defaultChipsFor (operate on
// arrays). A divergence there means a shared URL shows different chips than the
// FilterMenu would. Centralised here as pure functions over primitives so all
// three call ONE implementation. Loaded with the other data-layer scripts.

import { magnitudeParts } from '../charts/magnitude.js';

// Compact monetary label (sym-aware): "R$ 1,2 bi" / "US$ 340 mil".
// Replaces the per-file copies (FilterMenu.formatBRLcompact + Dashboard.compactBRL).
// Negative-safe so an inverted range still reads correctly. The bi/mi/mil ladder is the
// shared kernel (magnitude.js, DEDUP-7); the per-tier decimals + sym/sign stay local.
window.fmtCompactValue = (v, sym = 'R$') => {
  if (v == null) return '—';
  const a = Math.abs(v), sign = v < 0 ? '-' : '';
  const { factor, suffix } = magnitudeParts(a);
  if (!suffix) return `${sign}${sym} ` + a.toLocaleString('pt-BR');
  const dp = factor >= 1e6 ? 1 : 0;  // bi/mi → 1 decimal, mil → 0
  return `${sign}${sym} ` + (a / factor).toFixed(dp).replace('.', ',') + ` ${suffix}`;
};

window.chipFmt = {
  // Product basket → chip. count = selected, total = catalogue size,
  // firstName = name to show when exactly one is selected.
  products(count, total, firstName) {
    if (count == null)            return `Todos (${total})`;   // null = no filter = all
    if (count === 0)              return 'Nenhum';
    if (count === total)          return `Todos (${total})`;
    if (count === 1)              return firstName || `1 de ${total}`;
    return `${count} de ${total}`;
  },

  // Year range → chip ("1986–2024").
  period(startYear, endYear) {
    return `${startYear}\u2013${endYear}`;
  },


  // Quality flags → chip. count null = no filter = all; labelOf maps id→label.
  quality(ids, total, labelOf) {
    if (ids == null)          return `Todas (${total})`;
    if (ids.length === 0)     return 'Nenhuma';
    if (ids.length === total) return `Todas (${total})`;
    const head = ids.slice(0, 2).map(labelOf).join(' \u00b7 ');
    return head + (ids.length > 2 ? ` +${ids.length - 2}` : '');
  },

  // States-only geography → chip (Dashboard's banco-aware default & restore).
  // hasGeo false = the banco has no geographic dimension.
  geoStates(stateCount, ufTotal, hasGeo) {
    if (!hasGeo) return 'Não se aplica';
    if (!stateCount || stateCount === ufTotal) return `Brasil \u00b7 ${ufTotal} UFs`;
    return `${stateCount} ${stateCount === 1 ? 'UF' : 'UFs'}`;
  },

  // COMTRADE país reporter → chip. sel = null (Brasil default) | '__all__' (world) | ISO
  // array. total = reporter universe size; nameOf(iso) → display name (single-country case).
  reporter(sel, total, nameOf) {
    if (sel == null) return 'Brasil';
    if (sel === '__all__') return total ? `Mundo (${total})` : 'Mundo';
    if (!Array.isArray(sel) || sel.length === 0) return 'Brasil';
    if (total && sel.length >= total) return `Mundo (${total})`;
    if (sel.length === 1) return (nameOf && nameOf(sel[0])) || sel[0];
    return `${sel.length} países`;
  },

  // COMTRADE país parceiro → chip. sel = null (all) | ISO array; total = partner universe.
  partner(sel, total, nameOf) {
    if (sel == null || !Array.isArray(sel) || sel.length === 0 || (total && sel.length >= total)) {
      return total ? `Todos (${total})` : 'Todos';
    }
    if (sel.length === 1) return (nameOf && nameOf(sel[0])) || sel[0];
    return `${sel.length} de ${total}`;
  },
};
