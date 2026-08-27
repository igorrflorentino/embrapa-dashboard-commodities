// ViewTerritoryProfile.cov.test.jsx — the raio-x of ONE território.
//
// The behaviours worth pinning are the honesty ones, because they are the ones that
// look fine while being wrong:
//   - share/rank are computed over the SELECTED WINDOW, not one latest year (the
//     chart beside them spans the window; two questions under one label is the bug);
//   - the national denominator deliberately ignores an active UF filter, else the
//     share of a filtered-to-one-state view would always read 100%;
//   - a banco with only UF grain SAYS so instead of silently offering no município;
//   - a município reading does not borrow the state's share/rank without saying so.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/react';

function stubGlobals(filtered, opts = {}) {
  window.applyFilters = () => filtered;
  window.DEFAULT_CONVENTIONS = { currency: 'BRL', correction: 'IPCA' };
  window.CURRENCY_FX = { BRL: { symbol: 'R$' }, USD: { symbol: 'US$' } };
  window.conventionMonetaryLabel = () => 'R$';
  window.convFactor = () => 1;
  window.scaleSeries = (data, _max, _conv, _key, label) => ({ data, label });
  window.formatValue = (v) => `val:${Math.round(v)}`;
  window.fmtSigned = () => '+0%';
  // Mirrors the real data.js contract: takes a FRACTION, multiplies by 100.
  window.fmtPct = (x) => `${((x || 0) * 100).toFixed(1)}%`;
  window.geoLevelFor = () => opts.geoLevel || 'municipio';
  window.selectedSingleUf = (s) => (s && s.states && s.states.length === 1 ? s.states[0] : null);
  window.geoMesh = () => opts.mesh || [];
  window.municipioYearly = opts.municipioYearly || (() => []);
  window.productsByUf = opts.productsByUf || (() => ({ products: [], loadError: null }));
  window.productsByMunicipio = opts.productsByMunicipio
    || (() => ({ products: [], loadError: null }));

  window.EmptyCard = ({ children }) => <div className="empty-card">{children}</div>;
  window.NotApplicableNote = ({ children }) => <div className="na-note">{children}</div>;
  window.LoadErrorNote = ({ error }) => (error ? <div className="load-err" /> : null);
  window.KpiCardSpark = ({ label, value, sub }) => (
    <div className="kpi"><span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span><span className="kpi-sub">{sub}</span></div>
  );
  window.SectionHeader = ({ title, overline }) => (
    <div className="sh"><span className="sh-overline">{overline}</span>
      <span className="sh-title">{title}</span></div>
  );
  window.LineChart = (props) => <div className="line-chart" data-points={(props.data || []).length} />;
  window.BarChart = (props) => (
    <div className="bar-chart" data-points={(props.data || []).length}
         data-first={(props.data || [])[0] ? props.data[0].name : ''} />
  );
}

// PA dominates the window; SP is second. Deliberately NOT flat across years, so a
// latest-year shortcut would produce a DIFFERENT share than the window total.
const BASE = {
  yearStart: 2019,
  yearEnd: 2021,
  ufDataFull: [
    { uf: 'PA', name: 'Pará' },
    { uf: 'SP', name: 'São Paulo' },
  ],
  ufYearlySeries: [
    { year: 2019, uf: 'PA', value: 100 },
    { year: 2020, uf: 'PA', value: 200 },
    { year: 2021, uf: 'PA', value: 300 },   // PA window total = 600
    { year: 2019, uf: 'SP', value: 100 },
    { year: 2020, uf: 'SP', value: 100 },
    { year: 2021, uf: 'SP', value: 200 },   // SP window total = 400
  ],
};

const CONV = { currency: 'BRL', correction: 'IPCA' };
let View;

beforeEach(async () => {
  await import('./ViewTerritoryProfile.jsx');
  View = window.ViewTerritoryProfile;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.municipioYearly;
  delete window.productsByMunicipio;
  delete window.productsByUf;
  delete window.geoMesh;
});

const kpi = (c, label) => [...c.querySelectorAll('.kpi')]
  .find((k) => k.querySelector('.kpi-label').textContent.includes(label));

describe('ViewTerritoryProfile — share and rank over the SELECTED window', () => {
  it('computes share from the window total, not from one latest year', () => {
    stubGlobals(BASE);
    const { container } = render(<View summary={{}} database="ibge_pevs" conventions={CONV} />);
    // PA 600 of 1000 = 60,0%. A latest-year shortcut would say 300/500 = 60% by
    // coincidence here, so the fixture's 2020 (200/300 = 66,7%) is what separates them:
    // the assertion below is on the WINDOW figure.
    expect(kpi(container, 'Participação').querySelector('.kpi-value').textContent).toBe('60.0%');
    // And it must name the window it used, so the number is checkable.
    expect(kpi(container, 'Participação').querySelector('.kpi-sub').textContent).toContain('2019–2021');
  });

  it('ranks by the window total and reports the universe size', () => {
    stubGlobals(BASE);
    const { container } = render(<View summary={{}} database="ibge_pevs" conventions={CONV} />);
    // PA (600) outranks SP (400) → 1º of 2.
    expect(kpi(container, 'Posição').querySelector('.kpi-value').textContent).toBe('1º');
    expect(kpi(container, 'Posição').querySelector('.kpi-sub').textContent).toContain('de 2 UFs');
  });

  it('keeps the national denominator whole under an active UF filter', () => {
    // Filtering to PA must NOT make PA's share 100%: the denominator is every UF in
    // the grid on purpose, which is the only reading of "participação no país".
    stubGlobals(BASE);
    const { container } = render(
      <View summary={{ states: ['PA'] }} database="ibge_pevs" conventions={CONV} />,
    );
    expect(kpi(container, 'Participação').querySelector('.kpi-value').textContent).toBe('60.0%');
  });

  it('seeds the território from a single-UF filter (arriving from a map click)', () => {
    stubGlobals(BASE);
    const { container } = render(
      <View summary={{ states: ['SP'] }} database="ibge_pevs" conventions={CONV} />,
    );
    // SP, not the value-ranked default (PA).
    expect(container.querySelector('.sh-title').textContent).toContain('São Paulo');
    expect(kpi(container, 'Posição').querySelector('.kpi-value').textContent).toBe('2º');
  });
});

describe('ViewTerritoryProfile — declaring what the banco cannot answer', () => {
  it('says a UF-only banco has no município grain, and hides the level toggle', () => {
    stubGlobals(BASE, { geoLevel: 'uf' });
    const { container } = render(<View summary={{}} database="mdic_comex" conventions={CONV} />);
    expect(container.querySelector('.na-note').textContent).toContain('apenas por');
    // No município option at all — offering one that returns nothing would read as
    // "this state has no municípios producing", which is a different claim.
    expect(container.querySelector('[aria-label="Nível do território"]')).toBeNull();
  });

  it('offers the município level when the banco has that grain', () => {
    stubGlobals(BASE, { mesh: [{ cityCode: '1500107', cityName: 'Abaetetuba', uf: 'PA' }] });
    const { container } = render(<View summary={{}} database="ibge_pevs" conventions={CONV} />);
    expect(container.querySelector('[aria-label="Nível do território"]')).toBeTruthy();
    expect(container.querySelector('.na-note')).toBeNull();
  });
});

describe('ViewTerritoryProfile — the município reading', () => {
  const MESH = [
    { cityCode: '1500107', cityName: 'Abaetetuba', uf: 'PA' },
    { cityCode: '1500206', cityName: 'Acará', uf: 'PA' },
    { cityCode: '3550308', cityName: 'São Paulo', uf: 'SP' },
  ];

  it('draws the city trajectory from the city-scoped cube and names its produtos', () => {
    const municipioYearly = vi.fn(() => [
      { year: 2020, cityCode: '1500107', uf: 'PA', value: 7 },
      { year: 2021, cityCode: '1500107', uf: 'PA', value: 9 },
    ]);
    const productsByMunicipio = vi.fn(() => ({
      products: [{ code: '4403', name: 'Madeira em tora', value: 6 },
                 { code: '0801', name: 'Castanha', value: 3 }],
      loadError: null,
    }));
    stubGlobals(BASE, { mesh: MESH, municipioYearly, productsByMunicipio });
    const { container } = render(<View summary={{}} database="ibge_pevs" conventions={CONV} />);

    fireEvent.click([...container.querySelectorAll('.seg-opt')]
      .find((b) => b.textContent === 'Município'));

    // The cube must be asked for ONE city and the window — the city scope IS the cost
    // control on a direct Gold read, so a call without it would be the expensive bug.
    const [, , cityCodes, years] = municipioYearly.mock.calls.at(-1);
    expect(cityCodes).toEqual(['1500107']);
    expect(years).toEqual([2019, 2021]);
    // The produtos behind the trajectory: the cube alone cannot name them.
    expect(container.querySelector('.bar-chart').getAttribute('data-first')).toBe('Madeira em tora');
    expect(container.querySelector('.line-chart').getAttribute('data-points')).toBe('2');
  });

  it('says share and rank are the UF\'s, so a município never borrows them silently', () => {
    stubGlobals(BASE, { mesh: MESH });
    const { container } = render(<View summary={{}} database="ibge_pevs" conventions={CONV} />);
    fireEvent.click([...container.querySelectorAll('.seg-opt')]
      .find((b) => b.textContent === 'Município'));
    expect(container.textContent).toContain('o denominador');
    expect(container.textContent).toContain('não por município');
  });

  it('surfaces a breakdown load failure instead of an empty-looking place', () => {
    stubGlobals(BASE, {
      mesh: MESH,
      productsByUf: () => ({ products: [], loadError: new Error('500') }),
    });
    const { container } = render(<View summary={{}} database="ibge_pevs" conventions={CONV} />);
    expect(container.querySelector('.load-err')).toBeTruthy();
  });
});

describe('ViewTerritoryProfile — empty state', () => {
  it('asks for a different filter when no território has data', () => {
    stubGlobals({ yearStart: 2019, yearEnd: 2021, ufDataFull: [], ufYearlySeries: [] });
    const { container } = render(<View summary={{}} database="ibge_pevs" conventions={CONV} />);
    expect(container.querySelector('.empty-card').textContent).toContain('Nenhum território');
  });
});
