// ViewConcentration.test.jsx — render coverage for the concentration view (H3).
// It carries REAL math (Gini/HHI/top-N), so this exercises that computation end to
// end, and it confirms the P3 dead-code removal (the unused `conv`) didn't break
// rendering. Worked fixture: UF values [75, 25] → HHI = 75² + 25² = 6250, Gini =
// 0.25; product values [60, 40].

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/react';
// The REAL RecorteNote, registered on window exactly as main.jsx loads it: it is a pure
// four-line component, and stubbing it away would hide the very disclosure these views
// exist to carry.
import './RecorteNote.jsx';

function stubGlobals(filtered) {
  window.applyFilters = () => filtered;
  window.fmtPct = (x) => `${Math.round((x || 0) * 100)}%`;
  window.isCanonicalUf = () => true;
  window.dataStore = { meta: () => null };
  window.KpiCardSpark = ({ label, value, sub }) => (
    <div className="kpi" data-label={label}>
      <span className="kpi-value">{value}</span>
      <span className="kpi-sub">{sub}</span>
    </div>
  );
  window.SectionHeader = () => null;
  window.LorenzCurve = () => null;
}

let ViewConcentration;

beforeEach(async () => {
  await import('./ViewConcentration.jsx'); // registers window.ViewConcentration
  ViewConcentration = window.ViewConcentration;
});

afterEach(() => cleanup());

const FIXTURE = {
  ufDataFull: [
    { uf: 'PA', value: 75, real: true },
    { uf: 'SP', value: 25, real: true },
  ],
  ufData: [
    { uf: 'PA', value: 75, real: true },
    { uf: 'SP', value: 25, real: true },
  ],
  productTS: { P1: [{ y: 2020, v: 60 }], P2: [{ y: 2020, v: 40 }] },
  products: [
    { code: 'P1', name: 'Açaí' },
    { code: 'P2', name: 'Castanha' },
  ],
  yearEnd: 2020,
  ufLatestYear: 2020,
  ufYearPartial: false,
};

describe('ViewConcentration — Gini/HHI computation renders (H3)', () => {
  it('computes the geographic HHI and Gini from the UF distribution', () => {
    stubGlobals(FIXTURE);
    const { container } = render(<ViewConcentration summary={{}} conventions={{}} database="ibge_pevs" />);
    const byLabel = (l) =>
      container.querySelector(`.kpi[data-label="${l}"] .kpi-value`)?.textContent;
    expect(byLabel('HHI · geográfico (UF)')).toBe('6.250'); // 75² + 25², pt-BR thousands
    expect(byLabel('Gini · geográfico (UF)')).toBe('0,25'); // [25,75] Gini
    expect(byLabel('Concentração top-5 UFs')).toBe('100%'); // both UFs cover the total
  });

  it('falls back to product-only KPIs when the banco has no geography', () => {
    stubGlobals({ ...FIXTURE, ufDataFull: [], ufData: [] });
    const { container } = render(<ViewConcentration summary={{}} conventions={{}} database="ibge_pevs" />);
    // No geo → the product-distribution KPIs are shown instead (HHI 60² + 40² = 5200).
    const hhiProd = container.querySelector('.kpi[data-label="HHI · por produto"] .kpi-value');
    expect(hhiProd?.textContent).toBe('5.200');
  });
});

// A value-less herd basket (a stock, R$ 0 every year) must compute concentration on
// HEADCOUNT (q_count) instead of an all-zero value — else Gini/HHI/Lorenz collapse.
const HERD_FIXTURE = {
  ufDataFull: [
    { uf: 'MT', value: 0, q_count: 75, real: true },
    { uf: 'SP', value: 0, q_count: 25, real: true },
  ],
  ufData: [
    { uf: 'MT', value: 0, q_count: 75, real: true },
    { uf: 'SP', value: 0, q_count: 25, real: true },
  ],
  productTS: { P1: [{ y: 2020, v: 0, q: 60 }], P2: [{ y: 2020, v: 0, q: 40 }] },
  products: [
    { code: 'P1', name: 'Bovino', measure_kind: 'stock' },
    { code: 'P2', name: 'Suíno', measure_kind: 'stock' },
  ],
  yearEnd: 2020,
  ufLatestYear: 2020,
  ufYearPartial: false,
};

describe('ViewConcentration — value-less herd falls back to cabeças', () => {
  it('computes geographic Gini/HHI on q_count when the basket has no value', () => {
    stubGlobals(HERD_FIXTURE);
    const { container } = render(<ViewConcentration summary={{}} conventions={{}} database="ibge_ppm" />);
    const byLabel = (l) =>
      container.querySelector(`.kpi[data-label="${l}"] .kpi-value`)?.textContent;
    // same [75,25] distribution as the value case, now read from q_count → HHI 6250, Gini 0,25
    expect(byLabel('HHI · geográfico (UF)')).toBe('6.250');
    expect(byLabel('Gini · geográfico (UF)')).toBe('0,25');
    // the onCount note explains the basis is headcount, not value
    expect(container.textContent).toContain('cabeças');
  });
});
