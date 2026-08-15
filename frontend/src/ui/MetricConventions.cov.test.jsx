// MetricConventions.cov.test.jsx — coverage for the display-time metric strip
// (MetricConventions.jsx): the controlled <MetricConventions> component AND the
// formatter/scaler helpers it exports on window.*. We import the real data.js so the
// unit-family registry + defaultUnitOf/unitToBase are the actual ones under test, then
// drive the component branches (currency/correction groups, the unserved USD×IGP combo
// disable, the auto-scale checkbox, physical-unit groups, the clampConvention snap on
// currency switch) and exercise every exported helper (formatValue, applyConv,
// formatMassQty/VolumeQty/CountQty, scaleSeries, scaleLabel, valueAxisLabel, …).
//
// Collapsed by default (mirrors FilterTriggerBar): the component renders a compact chip
// summary + "Editar métricas" first render, and the editable .seg-opt/.mc-check groups
// only exist in the DOM once expanded. `expanded`/`onToggleExpanded` are CONTROLLED props
// (lifted to main.jsx in the real app — see MetricConventions.jsx's top comment for why:
// DataGate unmounts this component on every conventions change, which would wipe local
// state). Most tests below render with expanded={true} directly to reach the editor
// controls; `Harness` (a tiny stateful wrapper) drives the real toggle interaction for the
// dedicated collapse/expand test.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/react';

let MetricConventions;

beforeEach(async () => {
  await import('./data.js'); // sets window.UNIT_FAMILIES / defaultUnitOf / unitToBase
  await import('./MetricConventions.jsx'); // registers window.MetricConventions + helpers
  MetricConventions = window.MetricConventions;
});

afterEach(() => cleanup());

const BASE = { currency: 'BRL', correction: 'IPCA', units: { mass: 't', volume: 'm³' }, autoScale: false };

// Stateful wrapper: drives the real expanded/onToggleExpanded contract so a test can
// click "Editar métricas" / "Recolher" and observe the panel actually toggle, the way
// main.jsx's lifted metricsExpanded state does in the real app.
function Harness(props) {
  const [expanded, setExpanded] = React.useState(false);
  return <MetricConventions {...props} expanded={expanded} onToggleExpanded={() => setExpanded((e) => !e)} />;
}

describe('MetricConventions — collapsed-by-default summary', () => {
  it('starts collapsed: chip summary + Editar métricas button, no .mc-groups in the DOM', () => {
    const { container } = render(
      <MetricConventions value={BASE} onChange={() => {}} families={['mass', 'volume']} banco="ibge_pevs"
                          expanded={false} onToggleExpanded={() => {}} />
    );
    expect(container.querySelector('.mc-groups')).toBeNull();
    expect(container.textContent).toContain('Editar métricas');
    // Chips summarize the CURRENT convention read-only (no seg-opt buttons in this state).
    const chips = [...container.querySelectorAll('.fm-chip-filter')].map((e) => e.textContent);
    expect(chips.some((c) => c.includes('R$'))).toBe(true); // Moeda chip
    expect(chips.some((c) => c.includes('IPCA'))).toBe(true); // Correção chip
    expect(chips.some((c) => c.includes('t'))).toBe(true); // Massa chip
    expect(container.querySelector('.seg-opt')).toBeNull();
  });

  it('expands on "Editar métricas" and collapses back on "Recolher" (via the lifted toggle contract)', () => {
    const { container } = render(
      <Harness value={BASE} onChange={() => {}} families={['mass']} banco="ibge_pevs" />
    );
    fireEvent.click([...container.querySelectorAll('.fm-edit-btn')].find((b) => b.textContent.includes('Editar métricas')));
    expect(container.querySelector('.mc-groups')).toBeTruthy();
    expect(container.textContent).toContain('Recolher');
    fireEvent.click([...container.querySelectorAll('.fm-edit-btn')].find((b) => b.textContent.includes('Recolher')));
    expect(container.querySelector('.mc-groups')).toBeNull();
    expect(container.textContent).toContain('Editar métricas');
  });
});

describe('MetricConventions — controlled component (expanded)', () => {
  it('renders moeda + correção + physical-unit groups for a monetary banco', () => {
    const { container } = render(
      <MetricConventions value={BASE} onChange={() => {}} families={['mass', 'volume']} banco="ibge_pevs"
                          expanded={true} onToggleExpanded={() => {}} />
    );
    const labels = [...container.querySelectorAll('.mc-label')].map((e) => e.textContent);
    expect(labels).toContain('Moeda');
    expect(labels).toContain('Correção monetária');
    expect(labels).toContain('Massa'); // mass family group
    expect(labels).toContain('Volume'); // volume family group
    // The active currency option is marked.
    const onBtn = container.querySelector('.seg-opt.on');
    expect(onBtn).toBeTruthy();
  });

  it('disables the USD × IGP-M / IGP-DI combos (unserved) and keeps them under USD', () => {
    const usd = { ...BASE, currency: 'USD' };
    const { container } = render(
      <MetricConventions value={usd} onChange={() => {}} families={['mass']} banco="mdic_comex"
                          expanded={true} onToggleExpanded={() => {}} />
    );
    const disabled = [...container.querySelectorAll('.seg-opt.disabled')].map((e) => e.textContent);
    // IGP-M and IGP-DI buttons are disabled under USD.
    expect(disabled.join(' ')).toContain('IGP-M');
    expect(disabled.join(' ')).toContain('IGP-DI');
  });

  it('snaps an unserved correction back to IPCA when switching currency to USD (clampConvention)', () => {
    const onChange = vi.fn();
    const igpm = { ...BASE, currency: 'BRL', correction: 'IGP-M' };
    const { container } = render(
      <MetricConventions value={igpm} onChange={onChange} families={['mass']} banco="mdic_comex"
                          expanded={true} onToggleExpanded={() => {}} />
    );
    // Click the USD currency button.
    const usdBtn = [...container.querySelectorAll('.seg-opt')].find((b) => b.textContent.startsWith('USD'));
    fireEvent.click(usdBtn);
    expect(onChange).toHaveBeenCalled();
    const next = onChange.mock.calls[0][0];
    expect(next.currency).toBe('USD');
    expect(next.correction).toBe('IPCA'); // IGP-M was clamped away in the same update
  });

  it('toggles the auto-scale checkbox through onChange', () => {
    const onChange = vi.fn();
    const { container } = render(
      <MetricConventions value={BASE} onChange={onChange} families={['mass']} banco="ibge_pevs"
                          expanded={true} onToggleExpanded={() => {}} />
    );
    const check = container.querySelector('.mc-check input[type="checkbox"]');
    fireEvent.click(check);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ autoScale: true }));
  });

  it('picks a correction and a physical unit via onChange', () => {
    const onChange = vi.fn();
    const { container } = render(
      <MetricConventions value={BASE} onChange={onChange} families={['mass']} banco="ibge_pevs"
                          expanded={true} onToggleExpanded={() => {}} />
    );
    // Click the Nominal correction.
    const nominal = [...container.querySelectorAll('.seg-opt')].find((b) => b.textContent.startsWith('Nominal'));
    fireEvent.click(nominal);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ correction: 'Nominal' }));
    onChange.mockClear();
    // Click the kg mass unit.
    const kg = [...container.querySelectorAll('.seg-opt')].find((b) => b.textContent.startsWith('kg'));
    fireEvent.click(kg);
    const next = onChange.mock.calls[0][0];
    expect(next.units.mass).toBe('kg');
  });

  it('hides moeda/correção for a non-monetary banco, showing only unit groups', () => {
    window.isMonetaryBanco = () => false; // force the physical-only branch
    const { container } = render(
      <MetricConventions value={BASE} onChange={() => {}} families={['mass']} banco="future_physical"
                          expanded={true} onToggleExpanded={() => {}} />
    );
    const labels = [...container.querySelectorAll('.mc-label')].map((e) => e.textContent);
    expect(labels).not.toContain('Moeda');
    expect(labels).not.toContain('Correção monetária');
    expect(labels).toContain('Massa');
    delete window.isMonetaryBanco; // restore the real (data.js) helper for other tests
  });

  it('defaults the physical families to [mass, volume] when none are passed', () => {
    const { container } = render(
      <MetricConventions value={BASE} onChange={() => {}} banco="ibge_pevs"
                          expanded={true} onToggleExpanded={() => {}} />
    );
    const labels = [...container.querySelectorAll('.mc-label')].map((e) => e.textContent);
    expect(labels).toContain('Massa');
    expect(labels).toContain('Volume');
  });
});

describe('MetricConventions — exported window helpers', () => {
  const conv = { currency: 'BRL', correction: 'IPCA', units: { mass: 't', volume: 'm³', count: 'un' }, autoScale: false };

  it('clampConvention snaps only the unserved USD×IGP combos', () => {
    expect(window.clampConvention({ currency: 'USD', correction: 'IGP-M' }).correction).toBe('IPCA');
    expect(window.clampConvention({ currency: 'USD', correction: 'IGP-DI' }).correction).toBe('IPCA');
    // A servable combo passes through untouched.
    expect(window.clampConvention({ currency: 'USD', correction: 'IPCA' }).correction).toBe('IPCA');
    expect(window.clampConvention({ currency: 'EUR', correction: 'IGP-M' }).correction).toBe('IGP-M');
    expect(window.clampConvention(null)).toBeNull(); // guards null
  });

  it('convFactor / applyConv are server-native pass-throughs (always factor 1)', () => {
    expect(window.convFactor(conv)).toBe(1);
    expect(window.convFactorFor('USD', conv)).toBe(1);
    expect(window.applyConv(1234, conv)).toBe(1234);
    expect(window.applyConv(null, conv)).toBeNull();
  });

  it('formatValue prefixes the currency symbol and respects auto-scale', () => {
    expect(window.formatValue(null, conv)).toBe('—');
    expect(window.formatValue(1500, conv)).toBe('R$ 1.500'); // plain pt-BR
    const scaled = window.formatValue(2_500_000, { ...conv, autoScale: true });
    expect(scaled).toContain('R$');
    expect(scaled).toContain('mi'); // 2.5 mi
    // A different currency symbol comes from CURRENCY_FX.
    expect(window.formatValue(100, { ...conv, currency: 'USD' })).toContain('US$');
    expect(window.formatValue(100, { ...conv, currency: 'EUR' })).toContain('€');
  });

  it('unitOf falls back to the registry default and reads the picked unit', () => {
    expect(window.unitOf(conv, 'mass')).toBe('t');
    expect(window.unitOf({ units: {} }, 'mass')).toBe('t'); // registry default
  });

  it('mass/volume/count formatters convert internal scale to the picked unit', () => {
    // internal mass = mil t; t selected → ×1000 (massQtyMul). 2 mil t → 2.000 t.
    expect(window.formatMassQty(2, conv)).toContain('2.000');
    expect(window.formatMassQty(2, conv)).toContain('t');
    expect(window.formatMassQty(null, conv)).toBe('—');
    // kg selected → ×1e6.
    expect(window.formatMassQty(1, { ...conv, units: { ...conv.units, mass: 'kg' } })).toContain('kg');
    // internal volume = mi m³; m³ selected → ×1e6.
    expect(window.formatVolumeQty(1, conv)).toContain('m³');
    expect(window.formatVolumeQty(null, conv)).toBe('—');
    // internal count = mi un; un selected → ×1e6.
    expect(window.formatCountQty(1, conv)).toContain('un');
    expect(window.formatCountQty(null, conv)).toBe('—');
  });

  it('quantity multipliers + axis labels match the registry conversions', () => {
    expect(window.massQtyMul(conv)).toBe(1000); // mil t → t
    expect(window.volumeQtyMul(conv)).toBe(1e6); // mi m³ → m³
    expect(window.countQtyMul(conv)).toBe(1e6); // mi un → un
    expect(window.massAxisLabel(conv)).toBe('t');
    expect(window.volumeAxisLabel(conv)).toBe('m³');
    expect(window.countAxisLabel(conv)).toBe('un');
  });

  it('valueAxisLabel appends a magnitude suffix only under auto-scale', () => {
    expect(window.valueAxisLabel(conv)).toBe('R$');
    expect(window.valueAxisLabel({ ...conv, autoScale: true }, 5_000_000)).toBe('R$ mi');
    expect(window.valueAxisLabel({ ...conv, autoScale: true }, 5)).toBe('R$'); // no suffix below 1e3
  });

  it('conventionMonetaryLabel reads currency + correction', () => {
    expect(window.conventionMonetaryLabel(conv)).toBe('BRL · IPCA');
    expect(window.conventionMonetaryLabel({ ...conv, correction: 'Nominal' })).toBe('BRL · nominal');
  });

  it('scaleLabel orders the symbol before a currency, after a physical unit', () => {
    expect(window.scaleLabel('R$', 'bi')).toBe('R$ bi'); // currency: symbol first
    expect(window.scaleLabel('t', 'mil')).toBe('mil t'); // physical: suffix first
    expect(window.scaleLabel('t', '')).toBe('t'); // empty suffix trims clean
  });

  it('scaleSeries divides + relabels only under auto-scale', () => {
    const series = [{ v: 2_000_000 }, { v: 4_000_000 }];
    // auto-scale OFF → data untouched, label is the bare unit.
    const off = window.scaleSeries(series, 4_000_000, { ...conv, autoScale: false }, 'v', 'R$');
    expect(off.data).toBe(series);
    expect(off.label).toBe('R$');
    // auto-scale ON → ÷1e6, label "R$ mi".
    const on = window.scaleSeries(series, 4_000_000, { ...conv, autoScale: true }, 'v', 'R$');
    expect(on.data[0].v).toBe(2);
    expect(on.label).toBe('R$ mi');
    // ON but magnitude below 1e3 → no suffix → data untouched, bare label.
    const small = window.scaleSeries([{ v: 5 }], 5, { ...conv, autoScale: true }, 'v', 'R$');
    expect(small.data[0].v).toBe(5);
    expect(small.label).toBe('R$');
  });

  it('convertSeries multiplies each value by convFactor (1)', () => {
    const out = window.convertSeries([{ v: 10 }, { v: 20 }], conv);
    expect(out.map((d) => d.v)).toEqual([10, 20]);
  });

  it('DEFAULT_CONVENTIONS + CURRENCY_FX + autoScaleNum are exported', () => {
    expect(window.DEFAULT_CONVENTIONS.currency).toBe('BRL');
    expect(window.CURRENCY_FX.USD.symbol).toBe('US$');
    expect(window.autoScaleNum(1_500_000)).toEqual({ factor: 1e6, suffix: 'mi' });
  });
});
