// formatterContracts.test.js — the ONE place that states, in executable form, what each
// numeric formatter expects to be given.
//
// Why this file exists. The project has two percent formatters with OPPOSITE input
// conventions and names that do not say which is which:
//
//     fmtPct(0.6)  → '60,0%'   takes a FRACTION and multiplies by 100
//     pctBR(60)    → '60,0%'   takes a PERCENTAGE and only appends '%'
//
// A view passed a percentage to fmtPct and rendered "4361,4%" in production (v1.29.0).
// The view's unit test passed, because it stubbed fmtPct with the convention the author
// assumed rather than the one that exists — so the test blessed the bug.
//
// A stub can always drift from the real function. What must NOT drift silently is the
// contract itself: this file pins it against real values, so anyone writing a call site
// (or a stub) has one authoritative place to read, and a change to any convention breaks
// here — loudly, next to the explanation — instead of somewhere downstream.
//
// Audited on 2026-08-27: every call site of fmtPct / pctBR / fmtSigned in src/ passes the
// correct kind of number. The `*Frac` (fraction) vs `*Share`/`*Pct` (percentage) naming in
// the payloads is the convention that keeps them apart; call sites that cross the boundary
// multiply explicitly (e.g. `chPct(data.expFrac * 100)`).

import { beforeAll, describe, expect, it } from 'vitest';

beforeAll(async () => {
  await import('./data.js'); // registers the window.* formatters (no dependencies)
});

describe('fmtPct — takes a FRACTION', () => {
  it('multiplies by 100 and formats pt-BR with one decimal by default', () => {
    expect(window.fmtPct(0.6)).toBe('60,0%');
    expect(window.fmtPct(0.0355)).toBe('3,5%');   // see the rounding note below
    expect(window.fmtPct(1)).toBe('100,0%');
  });

  it('honours the digits argument', () => {
    expect(window.fmtPct(0.6, 0)).toBe('60%');
    expect(window.fmtPct(0.12345, 2)).toBe('12,35%');
  });

  it('renders an em dash for null rather than "NaN%"', () => {
    expect(window.fmtPct(null)).toBe('—');
    expect(window.fmtPct(undefined)).toBe('—');
  });

  it('a PERCENTAGE passed here is the 4361,4% bug — pinned so the trap stays visible', () => {
    // Not an endorsement: this documents what the wrong call produces, so the next
    // person recognises the symptom instantly instead of re-deriving it from a screenshot.
    expect(window.fmtPct(43.614)).toBe('4361,4%');
  });
});

describe('pctBR — takes a PERCENTAGE', () => {
  it('appends % WITHOUT scaling', () => {
    expect(window.pctBR(60)).toBe('60,0%');
    expect(window.pctBR(3.55)).toBe('3,6%');
  });

  it('honours the digits argument', () => {
    expect(window.pctBR(60, 0)).toBe('60%');
  });

  it('ROUNDS DIFFERENTLY from fmtPct on the same displayed quantity', () => {
    // fmtPct uses toFixed (binary, so 3.55 is really 3.5499… → down); pctBR goes through
    // toLocaleString (→ up). The same figure can therefore render 3,5% on one screen and
    // 3,6% on another. Harmless per se, but it looks like a data discrepancy to a
    // researcher comparing two views, so it is pinned rather than left to be rediscovered.
    expect(window.fmtPct(0.0355)).toBe('3,5%');
    expect(window.pctBR(3.55)).toBe('3,6%');
  });

  it('renders a bare em dash for null — not "—%"', () => {
    // numBR(null) is '—'; appending '%' to it produced "—%", which reads as a value.
    expect(window.pctBR(null)).toBe('—');
  });
});

describe('fmtSigned — takes a PERCENTAGE (like pctBR, unlike fmtPct)', () => {
  it('prefixes the sign and does not scale', () => {
    expect(window.fmtSigned(60)).toBe('+60,0%');
    expect(window.fmtSigned(-3.5)).toBe('-3,5%');
    expect(window.fmtSigned(0)).toBe('+0,0%');
  });

  it('takes a custom suffix, used for percentage-POINT differences', () => {
    expect(window.fmtSigned(60, 1, ' p.p.')).toBe('+60,0 p.p.');
  });

  it('renders an em dash for null', () => {
    expect(window.fmtSigned(null)).toBe('—');
  });
});

describe('numBR / fmtRows — plain numbers', () => {
  it('numBR groups pt-BR with the requested decimals', () => {
    expect(window.numBR(1234.5, 1)).toBe('1.234,5');
    expect(window.numBR(1234.5)).toBe('1.235');   // default 0 digits ROUNDS
    expect(window.numBR(null)).toBe('—');
  });

  it('fmtRows compacts row counts, and ROUNDS the mil tier to whole thousands', () => {
    // 1500 → "2 mil", not "1,5 mil": the mil tier takes 0 decimals. Worth pinning —
    // it surprises, and it is the readout under a provenance "Linhas" figure.
    expect(window.fmtRows(1500)).toBe('2 mil');
    expect(window.fmtRows(2400000)).toBe('2,4 mi');
    expect(window.fmtRows(999)).toBe('999');
  });
});
