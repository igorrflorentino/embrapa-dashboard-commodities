// ViewProductCompare.cov.test.jsx — render coverage for the multi-commodity compare
// view (normalized base-100 series, accumulated change / CAGR table, pairwise Pearson
// correlation). The view composes a handful of window.* metric/series helpers + chart
// widgets and branches on the selection (top-3 default, ≤4 cap, single-product → no
// correlation), the stock-vs-flow basis (q vs v, value-less herd indexes on headcount),
// and the mixed-basis honesty note. Following the ViewGeography/ViewRebanho .cov pattern
// we stub every window.* dependency so each branch is exercised deterministically.
//
// ViewProductCompare reads React hooks off the GLOBAL `React` (the prototype convention —
// `const { useState: usePCState } = React` runs at import time), so we set
// globalThis.React / window.React BEFORE importing the view.

import * as React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/react';
// O registro REAL de tabelas + `labelProductRows` (filtersSchema.js). A chamada na view é
// DELIBERADAMENTE incondicional: um helper ausente tem de estourar, não voltar a rotular
// duas metades do PEVS com o mesmo nome em silêncio.
import './filtersSchema.js';

let multiLineProps;

function stubGlobals(filtered) {
  window.applyFilters = () => filtered;
  window.DEFAULT_CONVENTIONS = { currency: 'BRL', correction: 'IPCA' };

  // Metric/series helpers — simple, predictable math so branches are assertable.
  window.cagrPct = (m0, mT, span) => (m0 && span ? ((mT / m0) ** (1 / span) - 1) * 100 : 0);
  window.spanYears = (win) => (win.length ? win[win.length - 1].y - win[0].y : 0);
  window.accumPct = (m0, mT) => (m0 ? ((mT - m0) / m0) * 100 : 0);
  window.pearsonByYear = (a, b) => (a === b ? 1 : 0.5);
  window.corrColor = () => 'var(--ok)';
  window.formatValue = (v) => `val:${v}`;
  window.formatCountQty = (v) => `count:${v}`;
  window.fmtSigned = (x, d) => (x >= 0 ? '+' : '') + (x || 0).toFixed(d ?? 0) + '%';
  window.UNIT_FAMILIES = {
    mass: { label: 'Massa' },
    volume: { label: 'Volume' },
    count: { label: 'Contagem' },
  };

  // Composed widgets — capture / render markers.
  window.SectionHeader = ({ overline, title, action }) => (
    <div className="sh">
      <span className="sh-ov">{overline}</span>
      <span className="sh-title">{title}</span>
      <span className="sh-action">{action}</span>
    </div>
  );
  window.MultiLineChart = (props) => {
    multiLineProps = props;
    return <div className="mlc" />;
  };
}

let ViewProductCompare;

beforeEach(async () => {
  multiLineProps = undefined;
  globalThis.React = React;
  window.React = React;
  await import('./ViewProductCompare.jsx'); // registers window.ViewProductCompare
  ViewProductCompare = window.ViewProductCompare;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Three flow commodities with full value series. P3 has the lowest latest value so the
// top-3 default keeps all three (each over a 2018→2020 window).
function flowFixture(overrides = {}) {
  return {
    selectedProducts: ['P1', 'P2', 'P3'],
    allProductTS: {
      P1: [
        { y: 2018, v: 100, q: 10 },
        { y: 2019, v: 150, q: 12 },
        { y: 2020, v: 200, q: 14 },
      ],
      P2: [
        { y: 2018, v: 80, q: 8 },
        { y: 2019, v: 90, q: 9 },
        { y: 2020, v: 120, q: 11 },
      ],
      P3: [
        { y: 2018, v: 40, q: 4 },
        { y: 2019, v: 50, q: 5 },
        { y: 2020, v: 60, q: 6 },
      ],
    },
    products: [
      { code: 'P1', name: 'Açaí', family: 'mass' },
      { code: 'P2', name: 'Castanha', family: 'mass' },
      { code: 'P3', name: 'Pó de carnaúba', family: 'mass' },
    ],
    yearStart: 2018,
    yearEnd: 2020,
  };
}

describe('ViewProductCompare — smoke + default top-3 selection', () => {
  it('renders the selector, normalized chart, metrics table and correlation matrix', () => {
    stubGlobals(flowFixture());
    const { container } = render(
      <ViewProductCompare summary={{}} conventions={{}} database="ibge_pevs" />
    );
    // Selector chips for every available product.
    const chips = [...container.querySelectorAll('.pp-chip')];
    expect(chips.length).toBe(3);
    expect(container.textContent).toContain('Comparar produtos');
    // Normalized series fed to MultiLineChart — base 100 at yearStart for each product.
    expect(multiLineProps).toBeTruthy();
    expect(multiLineProps.series.length).toBe(3);
    expect(multiLineProps.series[0].data[0].v).toBe(100); // base 100 at yearStart
    // Metrics table renders one row per default-selected product (top 3).
    const rows = container.querySelectorAll('.pc-table tbody tr');
    expect(rows.length).toBe(3);
    // Flow rows show value magnitude (vT * 1e6 via formatValue).
    expect(container.textContent).toContain('val:'); // formatValue marker present
    // Correlation matrix rendered (≥2 products) — diagonal dashes.
    expect(container.querySelector('.pc-corr')).toBeTruthy();
    expect(container.textContent).toContain('—'); // diagonal cell
  });

  it('desambigua duas metades do PEVS que dividem o nome, nos TRÊS lugares que o exibem', () => {
    // Escolher as duas metades do mesmo produto é possível — o seletor de cesta mostra os
    // códigos —, e a legenda, a tabela de métricas e o nome da série exibiam "Carvão
    // vegetal" duas vezes, sem dizer qual é qual. (A matriz de correlação já mostrava o
    // CÓDIGO e por isso nunca teve o problema.) A desambiguação vem da tabela, o terceiro
    // componente da identidade do produto.
    const fx = flowFixture();
    fx.products = [
      { code: 'P1', name: 'Carvão vegetal', family: 'mass', sidra_tabela: '291' },
      { code: 'P2', name: 'Carvão vegetal', family: 'mass', sidra_tabela: '289' },
      { code: 'P3', name: 'Açaí (fruto)', family: 'mass', sidra_tabela: '289' },
    ];
    stubGlobals(fx);
    const { container } = render(
      <ViewProductCompare summary={{}} conventions={{}} database="ibge_pevs" />
    );

    const legenda = [...container.querySelectorAll('.pc-legend-item')].map((n) => n.textContent.trim());
    expect(new Set(legenda).size, `legenda repetida: ${legenda}`).toBe(legenda.length);
    expect(legenda).toEqual([
      'Carvão vegetal · silvicultura',
      'Carvão vegetal · extração',
      'Açaí (fruto)',   // nome único → sem sufixo
    ]);

    // A tabela de MÉTRICAS usa o mesmo rótulo — três superfícies, um cálculo só. Escopada
    // à primeira tabela: a matriz de correlação logo abaixo é outra, e ela sempre mostrou
    // o CÓDIGO (por isso nunca teve o defeito).
    const metricas = container.querySelectorAll('table')[0];
    const primeiraColuna = [...metricas.querySelectorAll('tbody tr')]
      .map((r) => r.cells[0]?.textContent.trim()).filter(Boolean);
    expect(primeiraColuna).toEqual(legenda);
    expect(new Set(primeiraColuna).size).toBe(primeiraColuna.length);
  });

  it('flags a mixed-family basket with the honest indexing caveat', () => {
    const fx = flowFixture();
    // Make P2 a different family → mixedBasis true → caveat note rendered.
    fx.products = [
      { code: 'P1', name: 'Açaí', family: 'mass' },
      { code: 'P2', name: 'Castanha', family: 'volume' },
      { code: 'P3', name: 'Pó de carnaúba', family: 'mass' },
    ];
    stubGlobals(fx);
    const { container } = render(
      <ViewProductCompare summary={{}} conventions={{}} database="ibge_pevs" />
    );
    expect(container.textContent).toContain('mistura famílias');
  });
});

describe('ViewProductCompare — selection toggling', () => {
  it('deselecting a product drops it from the metrics table', () => {
    stubGlobals(flowFixture());
    const { container } = render(
      <ViewProductCompare summary={{}} conventions={{}} database="ibge_pevs" />
    );
    expect(container.querySelectorAll('.pc-table tbody tr').length).toBe(3);
    // Click the first (selected) chip → toggle it off.
    const firstChip = container.querySelector('.pp-chip.on');
    fireEvent.click(firstChip);
    expect(container.querySelectorAll('.pc-table tbody tr').length).toBe(2);
  });

  it('caps the active selection at 4 — a 5th product cannot be added', () => {
    const fx = flowFixture();
    // Five products, all with series; default keeps top-3, two are off.
    fx.selectedProducts = ['P1', 'P2', 'P3', 'P4', 'P5'];
    fx.allProductTS = {
      ...fx.allProductTS,
      P4: [
        { y: 2018, v: 30, q: 3 },
        { y: 2020, v: 35, q: 4 },
      ],
      P5: [
        { y: 2018, v: 20, q: 2 },
        { y: 2020, v: 25, q: 3 },
      ],
    };
    fx.products = [
      ...fx.products,
      { code: 'P4', name: 'Babaçu', family: 'mass' },
      { code: 'P5', name: 'Buriti', family: 'mass' },
    ];
    stubGlobals(fx);
    const { container } = render(
      <ViewProductCompare summary={{}} conventions={{}} database="ibge_pevs" />
    );
    // Default top-3 active. Add P4 (off chip) → now 4 active.
    const offChips = [...container.querySelectorAll('.pp-chip:not(.on)')];
    expect(offChips.length).toBe(2);
    fireEvent.click(offChips[0]);
    expect(container.querySelectorAll('.pc-table tbody tr').length).toBe(4);
    // The remaining off chip is now at-cap → disabled, clicking is a no-op.
    const stillOff = container.querySelector('.pp-chip:not(.on)');
    expect(stillOff.className).toContain('disabled');
    fireEvent.click(stillOff);
    expect(container.querySelectorAll('.pc-table tbody tr').length).toBe(4); // capped
  });
});

describe('ViewProductCompare — single-product + value-less herd branches', () => {
  it('shows the "select ≥2" note instead of a correlation matrix for one product', () => {
    const fx = flowFixture();
    fx.selectedProducts = ['P1'];
    fx.allProductTS = { P1: fx.allProductTS.P1 };
    fx.products = [{ code: 'P1', name: 'Açaí', family: 'mass' }];
    stubGlobals(fx);
    const { container } = render(
      <ViewProductCompare summary={{}} conventions={{}} database="ibge_pevs" />
    );
    expect(container.querySelectorAll('.pc-table tbody tr').length).toBe(1);
    // < 2 products → correlation matrix replaced by the prompt note.
    expect(container.querySelector('.pc-corr')).toBeFalsy();
    expect(container.textContent).toContain('ao menos 2 produtos');
  });

  it('indexes an all-stock (herd) basket on headcount and labels it "do efetivo"', () => {
    const fx = {
      selectedProducts: ['2670', '2675'],
      allProductTS: {
        2670: [
          { y: 2018, v: 0, q: 200 },
          { y: 2020, v: 0, q: 240 },
        ],
        2675: [
          { y: 2018, v: 0, q: 40 },
          { y: 2020, v: 0, q: 42 },
        ],
      },
      products: [
        { code: '2670', name: 'Bovino', family: 'count', measure_kind: 'stock' },
        { code: '2675', name: 'Suíno', family: 'count', measure_kind: 'stock' },
      ],
      yearStart: 2018,
      yearEnd: 2020,
    };
    stubGlobals(fx);
    const { container } = render(
      <ViewProductCompare summary={{}} conventions={{}} database="ibge_ppm" />
    );
    // All stock → normalized basis label switches to "do efetivo (cabeças)".
    expect(container.textContent).toContain('do efetivo (cabeças)');
    // Stock rows render headcount magnitude (qT via formatCountQty), not value.
    expect(container.textContent).toContain('count:');
    expect(container.textContent).not.toContain('val:');
  });
});
