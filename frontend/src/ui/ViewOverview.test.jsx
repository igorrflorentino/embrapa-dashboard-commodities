// ViewOverview.test.jsx — render coverage for the overview digest (H3). It also
// locks two P0 details: the "X de N flags" denominator reads window.QUALITY_FLAGS
// (now 11 flags — 5 base + 4 outlier/problemático + 2 reserved inferred tiers — not the 6 prototype ones),
// and the mass/volume quantity
// KPIs render off q_mass/q_vol. We import the real data.js for the registry and
// stub the composed window.* widgets/formatters (distinctive prefixes so the KPI
// values are unambiguous in the DOM).

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/react';
// The REAL RecorteNote, registered on window exactly as main.jsx loads it: it is a pure
// four-line component, and stubbing it away would hide the very disclosure these views
// exist to carry.
import './RecorteNote.jsx';
// O registro REAL de tabelas + `labelProductRows` (filtersSchema.js). A chamada na view é
// DELIBERADAMENTE incondicional: um helper ausente tem de estourar, não voltar a rotular
// duas metades do PEVS com o mesmo nome em silêncio.
import './filtersSchema.js';

function stubGlobals(filtered) {
  window.applyFilters = () => filtered;
  window.DEFAULT_CONVENTIONS = { currency: 'BRL', correction: 'IPCA' };
  window.conventionMonetaryLabel = () => 'R$';
  window.valueAxisLabel = () => 'R$';
  window.canonCurrencyFor = () => 'BRL';
  window.convFactorFor = () => 1;
  window.formatValue = (v) => `val:${v}`;
  window.formatMassQty = (v) => `mass:${v}`;
  window.formatVolumeQty = (v) => `vol:${v}`;
  window.formatCountQty = (v) => `count:${v}`;
  window.fmtSigned = () => '+0%';
  window.fmtPct = (x) => `${Math.round((x || 0) * 100)}%`;
  window.convertSeries = (s) => s;
  window.scaleSeries = (data, _max, _conv, _key, label) => ({ data, label });
  window.isCanonicalUf = () => true;
  window.dataStore = { meta: () => null };
  // Widgets: KPI card renders its label + value so we can read them.
  window.KpiCardSpark = ({ label, value }) => (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
    </div>
  );
  window.SectionHeader = ({ title, action }) => (
    <div className="sh">
      <span className="sh-title">{title}</span>
      <span className="sh-action">{action}</span>
    </div>
  );
  window.UnitFamilyBanner = () => null;
  window.UnitFamilyTag = () => null;
  window.LineChart = () => null;
  // Expõe os rótulos que o Donut recebeu: é o que o defeito das duas metades corrompia.
  window.Donut = (props) => (
    <div className="donut" data-rotulos={(props.data || []).map((d) => d.name).join('|')} />
  );
  window.BrazilTileMap = () => null;
}

let ViewOverview;

beforeEach(async () => {
  await import('./data.js'); // sets window.QUALITY_FLAGS to the REAL 9 Gold flags
  await import('./ViewOverview.jsx'); // registers window.ViewOverview
  ViewOverview = window.ViewOverview;
});

afterEach(() => cleanup());

const FIXTURE = {
  ts: [
    { y: 2019, v: 1, q_mass: 100, q_vol: 10, q_count: 1000 },
    { y: 2020, v: 2, q_mass: 200, q_vol: 20, q_count: 2000 },
  ],
  qualityFlags: [
    { id: 'OK', label: 'OK', color: 'var(--ok)', share: 0.8, count: 800000 },
    { id: 'INCOMPLETE', label: 'Incompleto', color: 'var(--viz-7)', share: 0.2, count: 200000 },
  ],
  qualityTs: [{ y: 2020, ok: 0.8 }],
  ufData: [{ uf: 'PA', value: 5, real: true }],
  ufDataFull: [{ uf: 'PA', value: 5, real: true }],
  selectedProducts: ['P1'],
  productsTotal: 3,
  topProducts: [{ code: 'P1', name: 'Açaí', share: 1 }],
  yearStart: 2019,
  yearEnd: 2020,
  ufLatestYear: 2020,
  ufYearPartial: false,
  notFilteredByBasket: false,
  geoComboPending: false,
};

describe('ViewOverview — KPI strip + quality digest (H3 + P0 lock-in)', () => {
  it('renders mass AND volume quantity KPIs off q_mass/q_vol when both families present', () => {
    stubGlobals(FIXTURE);
    const { container } = render(
      <ViewOverview families={['mass', 'volume']} summary={{}} database="ibge_pevs" conventions={{}} />
    );
    const values = [...container.querySelectorAll('.kpi-value')].map((e) => e.textContent);
    expect(values).toContain('mass:200'); // latest q_mass via formatMassQty
    expect(values).toContain('vol:20'); // latest q_vol via formatVolumeQty
  });

  it('the quality digest denominator counts the REAL registry (11 flags)', () => {
    stubGlobals(FIXTURE);
    const { container } = render(
      <ViewOverview families={['mass']} summary={{}} database="ibge_pevs" conventions={{}} />
    );
    // "{qualityFlags.length} de {QUALITY_FLAGS.length} flags" → "2 de 12 flags". 12 = the 5
    // base flags + the 4 outlier/problemático tiers + the 2 reserved inferred tiers + the
    // PAM-only AREA_INCONSISTENT (all in the registry regardless of the dbt var / pipeline state).
    expect(container.textContent).toContain('de 12 flags');
    expect(container.textContent).not.toContain('de 6 flags'); // the old prototype count
  });

  it('renders the count (efetivo) KPI off q_count for a livestock (count) basket', () => {
    stubGlobals(FIXTURE);
    const { container } = render(
      <ViewOverview families={['count']} summary={{}} database="ibge_ppm" conventions={{}} />
    );
    const values = [...container.querySelectorAll('.kpi-value')].map((e) => e.textContent);
    expect(values).toContain('count:2000'); // latest q_count via formatCountQty (keystone)
    expect(values).not.toContain('mass:200'); // mass KPI absent — no mass family in the basket
  });

  it('SUPPRESSES the blended count KPI when the basket has a stock (herd), pointing to Rebanho', () => {
    // The count KPI sums the whole count family (herd STOCK + egg FLOW + every species),
    // which is not additive — for a stock basket it must NOT be shown as one headline.
    stubGlobals({
      ...FIXTURE,
      products: [{ code: '2670', name: 'Bovino', measure_kind: 'stock' }],
      selectedProducts: ['2670'],
    });
    const { container } = render(
      <ViewOverview families={['count']} summary={{}} database="ibge_ppm" conventions={{}} />
    );
    const values = [...container.querySelectorAll('.kpi-value')].map((e) => e.textContent);
    expect(values).not.toContain('count:2000'); // blended count KPI suppressed for a stock basket
    expect(container.textContent).toContain('Rebanho'); // redirect note instead
  });

  it('o Donut não mostra duas fatias com o MESMO rótulo quando o nome se repete', () => {
    // Madeira em tora existe nas DUAS tabelas do PEVS com o mesmo nome. O Donut usa índice
    // como chave, então não FUNDE as fatias — mas mostrava "Madeira em tora 57%" e
    // "Madeira em tora 7%", e o leitor não tinha como saber qual metade era qual.
    // A desambiguação vem da tabela, que é o terceiro componente da identidade do produto.
    stubGlobals({
      ...FIXTURE,
      topProducts: [
        { code: '3457', name: 'Madeira em tora', tabela: '291', share: 0.57 },
        { code: '3435', name: 'Madeira em tora', tabela: '289', share: 0.07 },
        { code: '3403', name: 'Açaí (fruto)', tabela: '289', share: 0.02 },
      ],
    });
    const { container } = render(
      <ViewOverview families={['mass']} summary={{}} database="ibge_pevs" conventions={{}} />
    );
    const rotulos = container.querySelector('.donut').getAttribute('data-rotulos').split('|');
    expect(new Set(rotulos).size, `rótulos repetidos: ${rotulos}`).toBe(rotulos.length);
    expect(rotulos).toEqual([
      'Madeira em tora · silvicultura',
      'Madeira em tora · extração',
      'Açaí (fruto)',   // nome único → sem sufixo
    ]);
  });

  it('omits the volume KPI when the banco has no volume family', () => {
    stubGlobals(FIXTURE);
    const { container } = render(
      <ViewOverview families={['mass']} summary={{}} database="ibge_pevs" conventions={{}} />
    );
    const values = [...container.querySelectorAll('.kpi-value')].map((e) => e.textContent);
    expect(values).toContain('mass:200');
    expect(values).not.toContain('vol:20');
  });
});
