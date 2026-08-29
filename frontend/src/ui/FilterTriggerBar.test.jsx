// FilterTriggerBar.test.jsx — the active-filter chip row is now CAPABILITY-DRIVEN:
// only the dimensions the active banco actually exposes get a chip, so the user is
// never shown a filter it can't use. Also locks the Fluxo chip (server-side filter)
// and the deliberate absence of the unbacked "Faixa de valor" chip.

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/react';

// The REAL trade-label resolver, registered on window exactly as main.jsx loads it.
// Stubbing it would let the chip row and the ABNT citation — which now read the SAME
// resolver — disagree in a test while agreeing in the product, or the reverse.
import './scopeChips.js';

let FilterTriggerBar;

beforeEach(async () => {
  await import('./FilterTriggerBar.jsx'); // registers window.FilterTriggerBar
  FilterTriggerBar = window.FilterTriggerBar;
  window.canExportView = () => false; // keep the CSV button out of the assertions
  window.flowOptionsFor = (id) =>
    id === 'mdic_comex'
      ? [{ value: 'export', label: 'Exportação' }, { value: 'import', label: 'Importação' }]
      : null;
});

afterEach(() => cleanup());

const SUMMARY = {
  products: 'Todos (5)',
  period: '1997–2024',
  valueRange: '—',
  geo: 'Brasil · 27 UFs',
  quality: 'Todas (5)',
  fluxo: 'Exportação',
};

const chipKeys = (container) =>
  [...container.querySelectorAll('.fm-chip-k')].map((n) => n.textContent);

describe('FilterTriggerBar — capability-driven chips', () => {
  it('production banco (no flow): product/period/geo/quality — never Fluxo or Faixa de valor', () => {
    const banco = { id: 'ibge_pevs', short: 'IBGE PEVS', provides: ['product', 'geo', 'quality'] };
    const { container } = render(<FilterTriggerBar summary={SUMMARY} banco={banco} live />);
    expect(chipKeys(container)).toEqual(['Produtos', 'Período', 'Geografia', 'Qualidade']);
  });

  it('trade banco with flow but no geo (COMTRADE): shows Fluxo, hides Geografia', () => {
    const banco = { id: 'un_comtrade', short: 'UN COMTRADE', provides: ['product', 'flow', 'quality'] };
    const { container } = render(<FilterTriggerBar summary={SUMMARY} banco={banco} live />);
    expect(chipKeys(container)).toEqual(['Produtos', 'Período', 'Fluxo', 'Qualidade']);
  });

  it('never renders a "Faixa de valor" chip (no backed filter path → hidden, not inert)', () => {
    const banco = { id: 'mdic_comex', short: 'MDIC COMEX', provides: ['product', 'flow', 'geo', 'quality'] };
    const { container } = render(<FilterTriggerBar summary={SUMMARY} banco={banco} live />);
    expect(chipKeys(container)).not.toContain('Faixa de valor');
  });

  it('resolves the Fluxo chip from the raw summary.flow on a restored deep-link', () => {
    const banco = { id: 'mdic_comex', short: 'MDIC COMEX', provides: ['product', 'flow', 'geo', 'quality'] };
    const restored = { ...SUMMARY, fluxo: undefined, flow: 'import' }; // no chip string, only raw flow
    const { container } = render(<FilterTriggerBar summary={restored} banco={banco} live />);
    expect(container.textContent).toContain('Importação'); // resolved via window.flowOptionsFor
  });
});
